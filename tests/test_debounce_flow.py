"""DebounceEngine 异步流程测试：合并、追加重置、立即结算、输入状态、撤回。"""

import asyncio

import sys

import pytest

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.debounce import DebounceEngine


def make_engine(**overrides):
    defaults = dict(
        debounce_time=0.05,
        enable_adaptive_debounce=False,  # 流程测试用固定短防抖，保证确定性
        adaptive_min_wait=1.0,
        adaptive_max_wait=6.0,
        adaptive_max_total_wait=12.0,
        adaptive_short_message_threshold=10,
        max_session_wait=60.0,
    )
    defaults.update(overrides)
    return DebounceEngine(**defaults)


def run(coro):
    return asyncio.run(coro)


# ---------------- 基本合并流程 ----------------

def test_start_and_flush_single_message():
    async def scenario():
        engine = make_engine()
        result = engine.submit("u1", text="第一条", message_id=1)
        assert result.action == "started"

        # 手动等待超过 debounce_time 后计时器触发结算
        await asyncio.sleep(0.08)
        session = engine.get_session("u1")
        assert session["flush_event"].is_set()
        assert session["buffer"] == ["第一条"]
        assert session["items"][0]["message_id"] == 1

        # 结算后 pop
        popped = engine.pop_session("u1")
        assert popped["buffer"] == ["第一条"]
        assert engine.has_session("u1") is False

    run(scenario())


def test_multiple_messages_merge_with_separator():
    async def scenario():
        engine = make_engine()
        engine.submit("u1", text="第一条", message_id=1)
        result2 = engine.submit("u1", text="第二条", message_id=2)
        assert result2.action == "appended"
        result3 = engine.submit("u1", text="第三条", message_id=3)
        assert result3.action == "appended"

        session = engine.get_session("u1")
        assert session["buffer"] == ["第一条", "第二条", "第三条"]
        assert session["images"] == []

        await asyncio.sleep(0.08)
        popped = engine.pop_session("u1")
        assert popped["buffer"] == ["第一条", "第二条", "第三条"]

    run(scenario())


def test_append_resets_timer():
    """追加消息应重置计时器：距离首条 0.03s 追加，仍需完整防抖窗口后才结算。"""
    async def scenario():
        engine = make_engine(debounce_time=0.1)
        engine.submit("u1", text="第一条", message_id=1)
        await asyncio.sleep(0.05)
        engine.submit("u1", text="第二条", message_id=2)
        await asyncio.sleep(0.05)
        # 距追加仅 0.05s，不应已结算
        session = engine.get_session("u1")
        assert not session["flush_event"].is_set()
        await asyncio.sleep(0.06)
        session = engine.get_session("u1")
        assert session["flush_event"].is_set()

    run(scenario())


def test_wait_flush_returns_after_set():
    async def scenario():
        engine = make_engine(debounce_time=0.05)
        engine.submit("u1", text="你好", message_id=1)
        await engine.wait_flush("u1")
        assert engine.get_session("u1")["flush_event"].is_set()

    run(scenario())


# ---------------- 立即结算路径 ----------------

def test_request_flush_from_outside():
    async def scenario():
        engine = make_engine(debounce_time=60.0)  # 正常等不到结算
        engine.submit("u1", text="你好", message_id=1)
        assert engine.request_flush("u1") is True
        await engine.wait_flush("u1")
        assert engine.get_session("u1")["flush_event"].is_set()

        # 无会话时无害
        assert engine.request_flush("no_such_user") is False

    run(scenario())


def test_request_flush_cancels_timer():
    """请求结算后旧计时器任务必须已取消（防泄漏）。"""
    async def scenario():
        engine = make_engine(debounce_time=60.0)
        engine.submit("u1", text="你好", message_id=1)
        session = engine.get_session("u1")
        old_task = session["timer_task"]
        assert old_task is not None and not old_task.done()

        engine.request_flush("u1")
        # cancel() 后任务需一次事件循环切换才真正结束
        await asyncio.sleep(0)
        assert old_task.done()  # 被 cancel
        assert session["timer_task"] is None

    run(scenario())


# ---------------- 输入状态 ----------------

def test_pause_and_resume_typing():
    async def scenario():
        engine = make_engine(debounce_time=0.2)
        engine.submit("u1", text="第一条", message_id=1)
        session = engine.get_session("u1")

        # 暂停：挂起原计时，起保护计时器
        protection = engine.pause_for_typing("u1", max_typing_wait=5.0)
        assert protection == pytest.approx(5.0)
        assert session["is_typing"] is True
        assert session["timer_task"] is not None

        # 恢复：回到剩余等待；debounce_time=0.2 的剩余被 RESUME_MIN_WAIT(0.5) 钳制
        resumed = engine.resume_after_typing("u1")
        assert resumed is not None
        assert session["is_typing"] is False
        assert resumed == pytest.approx(0.5, abs=0.05)  # 下限钳制

        # 重复恢复是空操作（天然过滤重复停止输入通知）
        assert engine.resume_after_typing("u1") is None

    run(scenario())


def test_pause_typing_capped_by_hard_deadline():
    async def scenario():
        engine = make_engine(max_session_wait=3.0)
        engine.submit("u1", text="你好", message_id=1)
        session = engine.get_session("u1")
        session["started_at"] = 0.0  # 人为把首条时间拨早
        engine._now = lambda: 2.5

        # 已用 2.5s，剩余硬死线 0.5s：保护时长被钳到 0.5
        protection = engine.pause_for_typing("u1", max_typing_wait=60.0)
        assert protection == pytest.approx(0.5)

    run(scenario())


# ---------------- 撤回 ----------------

def test_remove_message_rebuilds_buffers():
    async def scenario():
        engine = make_engine(debounce_time=0.05)
        engine.submit("u1", text="第一条", message_id=1)
        engine.submit("u1", text="第二条", image_urls=["http://a/b.png"], message_id=2)

        removed, emptied = engine.remove_message("u1", 1)
        assert removed == 1
        assert emptied is False
        session = engine.get_session("u1")
        assert session["buffer"] == ["第二条"]
        assert session["images"] == ["http://a/b.png"]

        # message_id 类型兼容（str vs int）
        removed, emptied = engine.remove_message("u1", "2")
        assert removed == 1
        assert emptied is True
        session = engine.get_session("u1")
        assert session["buffer"] == []
        assert session["images"] == []

    run(scenario())


def test_remove_unknown_message_noop():
    async def scenario():
        engine = make_engine()
        engine.submit("u1", text="第一条", message_id=1)
        removed, emptied = engine.remove_message("u1", 999)
        assert removed == 0
        assert emptied is False

    run(scenario())


# ---------------- 吸收活动（表情等） ----------------

def test_absorb_activity_with_session():
    async def scenario():
        engine = make_engine(debounce_time=0.1)
        engine.submit("u1", text="你好", message_id=1)
        assert engine.absorb_activity("u1", message_id=2) is True
        session = engine.get_session("u1")
        assert len(session["items"]) == 2
        assert session["items"][1]["text"] == ""
        # 计时器被重置为固定防抖
        assert session["timer_task"] is not None

    run(scenario())


def test_absorb_activity_without_session_rejected():
    engine = make_engine()
    assert engine.absorb_activity("u1") is False


# ---------------- 代际守卫（陈旧计时器） ----------------

def test_stale_timer_cannot_flush_new_session():
    """修复缺陷 1：旧计时器泄漏（未取消）时，代际守卫阻止其触发新一轮会话。"""
    async def scenario():
        engine = make_engine(debounce_time=0.1, max_session_wait=60.0)
        engine.submit("u1", text="第一轮", message_id=1)
        session1 = engine.get_session("u1")
        stale_task = session1["timer_task"]  # 0.1s 后唤醒

        # 模拟外部路径泄漏：直接 pop 而不取消计时器（对应原版撤回清空场景）
        engine.pop_session("u1")

        # 第二轮：把防抖调长，使旧计时器先于新计时器唤醒
        engine.debounce_time = 0.3
        engine.submit("u1", text="第二轮", message_id=2)
        session2 = engine.get_session("u1")
        assert session1 is not session2

        # 旧计时器在 ~0.1s 时唤醒 → 代际守卫必须拦截（不得 set 新会话）
        await asyncio.sleep(0.15)
        assert not session2["flush_event"].is_set()

        # 新会话自己的计时器在 ~0.3s 唤醒 → 正常结算
        await asyncio.sleep(0.2)
        assert session2["flush_event"].is_set()

        # 清理
        engine.request_flush("u1")
        await asyncio.sleep(0)

    run(scenario())


def test_stale_timer_guard_active():
    """真实路径：_request_flush 已先 cancel，旧任务 done()。"""
    async def scenario():
        engine = make_engine(debounce_time=0.2)
        engine.submit("u1", text="第一轮", message_id=1)
        session1 = engine.get_session("u1")
        old_task = session1["timer_task"]
        engine.request_flush("u1")
        engine.pop_session("u1")
        await asyncio.sleep(0)
        assert old_task.done()

        engine.submit("u1", text="第二轮", message_id=2)
        session2 = engine.get_session("u1")
        await asyncio.sleep(0.03)
        assert not session2["flush_event"].is_set()
        # 清理
        engine.request_flush("u1")
        await asyncio.sleep(0)

    run(scenario())


# ---------------- 硬死线兜底 ----------------

def test_hard_deadline_flushes_without_timer():
    """修复缺陷 3：计时器丢失（无人 set）时，wait_flush 到硬死线强制结算。"""
    async def scenario():
        engine = make_engine(max_session_wait=0.1, debounce_time=0.05)
        engine.submit("u1", text="你好", message_id=1)
        session = engine.get_session("u1")
        # 模拟计时器丢失：取消任务且无人再 set
        session["timer_task"].cancel()
        session["timer_task"] = None

        # 硬死线 0.1s 后 wait_flush 自行请求结算
        await engine.wait_flush("u1")
        assert session["flush_event"].is_set()

    run(scenario())


def test_shutdown_clears_sessions():
    async def scenario():
        engine = make_engine(debounce_time=60.0)
        engine.submit("u1", text="你好", message_id=1)
        engine.submit("u2", text="你好", message_id=2)
        assert engine.shutdown() == 2
        assert engine.sessions == {}

    run(scenario())
