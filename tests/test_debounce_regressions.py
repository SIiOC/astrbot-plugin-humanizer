"""已知问题修复的回归测试（对应本次调查发现的缺陷）。"""

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
        enable_adaptive_debounce=True,
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


# ============ 缺陷 1：撤回清空遗留计时器 ============

def test_regression_recall_clear_does_not_leak_timer():
    """原版 main.py:317-320 全部撤回只 set 不 cancel，遗留计时器会误触发新会话。

    新实现：_request_flush 统一先取消计时器；即使计时器泄漏，代际守卫拦截。
    """
    async def scenario():
        engine = make_engine(debounce_time=0.1, max_session_wait=60.0)
        # 第一轮：发 2 条 → 全部撤回 → 触发结算
        engine.submit("u1", text="第一轮A", message_id=1)
        engine.submit("u1", text="第一轮B", message_id=2)
        session1 = engine.get_session("u1")
        old_task = session1["timer_task"]

        engine.remove_message("u1", 1)
        removed, emptied = engine.remove_message("u1", 2)
        assert emptied is True
        # 全部撤回路径走统一结算入口：计时器必须已被取消
        engine.request_flush("u1")
        await asyncio.sleep(0)
        assert old_task.done()
        engine.pop_session("u1")

        # 立刻开新一轮
        engine.submit("u1", text="第二轮", message_id=3)
        session2 = engine.get_session("u1")
        assert session1 is not session2

        # 旧计时器窗口已过，新会话不应被提前结算
        await asyncio.sleep(0.15)
        assert not session2["flush_event"].is_set()
        # 清理
        engine.request_flush("u1")
        await asyncio.sleep(0)

    run(scenario())


def test_regression_recall_all_rebuilt_empty_then_flush_noop():
    """撤回全部消息后：buffer/images 为空，结算入口对空会话安全（无崩溃）。"""
    async def scenario():
        engine = make_engine()
        engine.submit("u1", text="A", message_id=1)
        removed, emptied = engine.remove_message("u1", 1)
        assert removed == 1 and emptied is True
        session = engine.get_session("u1")
        assert session["buffer"] == []
        assert session["images"] == []
        # 结算后 pop 出空会话，由 main.py 静默终止
        engine.request_flush("u1")
        popped = engine.pop_session("u1")
        assert popped["buffer"] == [] and popped["images"] == []

    run(scenario())


# ============ 缺陷 2：空内容消息在会话期间被吸收 ============

def test_regression_empty_activity_absorbed_and_timer_reset():
    """会话期间的表情/语音等空内容消息应被吸收并重置计时器，不绕过防抖。"""
    async def scenario():
        engine = make_engine(debounce_time=0.2)
        engine.submit("u1", text="在吗", message_id=1)
        session = engine.get_session("u1")
        wait_before = session["last_wait"]

        # 表情消息（无文本无图）→ 吸收
        assert engine.absorb_activity("u1", message_id=2) is True
        assert len(session["items"]) == 2
        # 计时器重置为固定防抖
        assert session["last_wait"] == pytest.approx(0.2)

        # 无会话时空内容放行（返回 False，由 main.py 决定）
        engine.pop_session("u1")
        assert engine.absorb_activity("u1", message_id=3) is False

    run(scenario())


# ============ 缺陷 3：硬死线兜底 ============

def test_regression_hard_deadline_with_typing_loop():
    """用户持续'正在输入'（保护计时器不断续期）时，硬死线必须兜底结算。"""
    async def scenario():
        engine = make_engine(debounce_time=0.05, max_session_wait=0.3)
        engine.submit("u1", text="你好", message_id=1)
        session = engine.get_session("u1")
        session["started_at"] = 0.0
        engine._now = lambda: 0.1

        # 第一次暂停：余量 0.2s
        protection = engine.pause_for_typing("u1", max_typing_wait=60.0)
        assert protection == pytest.approx(0.2)

        # 模拟时间推进 + 持续输入通知
        engine._now = lambda: 0.3  # 已到硬死线
        protection = engine.pause_for_typing("u1", max_typing_wait=60.0)
        assert protection == 0.0  # 余量为 0 → 直接结算
        assert session["flush_event"].is_set()

    run(scenario())


def test_regression_resume_preserves_remaining_wait():
    """输入状态恢复应保留被打断前的剩余等待，而非恢复全量 debounce_time。

    resume 实现为「剩余时长重新计时」：从当前时刻起再等剩余时长。
    因此返回的即是从当前时刻起的剩余等待（= 0.4s），会话的 timer_started_at 被重置。
    """
    async def scenario():
        engine = make_engine(debounce_time=1.0, enable_adaptive_debounce=False)
        engine.submit("u1", text="你好", message_id=1)
        session = engine.get_session("u1")
        session["is_typing"] = True  # 模拟正处于输入状态
        session["timer_started_at"] = 0.0
        session["pending_wait"] = 2.0
        engine._now = lambda: 0.6  # 已过 0.6s，剩余 1.4s

        resumed = engine.resume_after_typing("u1")
        # 剩余 1.4s > RESUME_MIN_WAIT(0.5)，不被钳制：保留剩余而非恢复全量 2.0s
        assert resumed == pytest.approx(1.4, abs=0.01)
        # 恢复后重新计时，起点更新为当前时刻（真实时钟下 >= 0.6）
        assert session["timer_started_at"] >= 0.6
        engine.shutdown()

    run(scenario())


# ============ 配置一致性 ============

def test_regression_adaptive_default_true():
    """enable_adaptive_debounce 默认值：schema 与代码回退统一为 true。"""
    engine = DebounceEngine()  # 不传任何参数
    assert engine.enable_adaptive_debounce is True
    # 未传配置时走自适应
    wait, flush_now, reason = engine.calculate_wait("短")
    assert flush_now is False
    assert "fixed_debounce" not in reason



class TestDeadSessionSelfHeal:
    """自愈守卫（2026-09-03 全量审查）：结算事件已置位但无等待协程的残留会话，
    submit() 应丢弃并重开防抖轮，而不是继续追加导致该会话永久吞消息。"""

    def test_submit_discards_dead_session(self):
        async def scenario():
            engine = make_engine()
            r1 = engine.submit("u", text="hello")
            assert r1.action == "started"
            # 模拟首条协程被取消后的残留：结算事件置位但无人 wait_flush
            assert engine.request_flush("u") is True
            assert engine.get_session("u")["flush_event"].is_set()
            r2 = engine.submit("u", text="second")
            assert r2.action == "started"
            session = engine.get_session("u")
            assert session is not None
            assert session["buffer"] == ["second"]
            engine.request_flush("u")
            engine.pop_session("u")

        run(scenario())

    def test_live_session_not_discarded(self):
        """正常流不误伤：结算事件未置位时，追加语义保持不变。"""

        async def scenario():
            engine = make_engine()
            r1 = engine.submit("u", text="hello")
            assert r1.action == "started"
            assert not engine.get_session("u")["flush_event"].is_set()
            r2 = engine.submit("u", text="second")
            assert r2.action == "appended"
            session = engine.get_session("u")
            assert session["buffer"] == ["hello", "second"]
            engine.request_flush("u")
            engine.pop_session("u")

        run(scenario())
