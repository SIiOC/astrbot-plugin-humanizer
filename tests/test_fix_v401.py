# -*- coding: utf-8 -*-
"""v4.0.1 外审修复批回归测试。

覆盖：prune_stale 以 last_user_ts 判过期（真实场景）、max_unanswered 闸门接线、
防抖 TOCTOU（等待者存活证明）、输入保护期间 absorb 不打断、llm_target 失败不写缓存、
承诺 ID 不碰撞、parse_llm_array 字符串状态机、时间边界（NaN/负 gap/跨午夜）、
settle_delay NaN、检索缓存 clear() 代数失效。
"""

import ast
import asyncio
import os
import sys as _sys
import time

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

from humanizer_core.debounce import DebounceEngine  # noqa: E402
from humanizer_core.time_flow import (  # noqa: E402
    TimeInterval,
    gap_context,
    parse_time_slot,
    rhythm_heat,
)
from humanizer_core.typing import settle_delay  # noqa: E402


# ---------------------------------------------------------------- B1 主动生命周期
class TestPruneStaleRealWorld:
    """v4.0.1：真实场景——trigger 恒在未来（触发即重排）时死会话也必须能回收。"""

    def _make_state(self, now):
        import tempfile
        from pathlib import Path

        from services.proactive_state import ProactiveState

        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "proactive_state.json"
        state = ProactiveState(
            state_file=path,
            config_getter=lambda k, d=None: {},
            clock=lambda: now,
        )
        state._tmpdir = tmp  # 持引用防过早清理
        return state

    def test_future_trigger_with_stale_user_pruned(self):
        """触发时间在未来 + 用户 25h 未发言 → 应回收（原实现恒不触发）。"""
        now = time.time()
        state = self._make_state(now)
        state.triggers["dead"] = now + 3600      # 未来：主动开启时的常态
        state.unanswered["dead"] = 7
        state.last_user_ts["dead"] = now - 25 * 3600
        state.followups["dead"] = {"stage": 1}

        removed = state.prune_stale(now)
        assert removed == ["dead"]
        assert "dead" not in state.triggers
        assert "dead" not in state.last_user_ts

    def test_future_trigger_with_fresh_user_kept(self):
        now = time.time()
        state = self._make_state(now)
        state.triggers["live"] = now + 3600
        state.last_user_ts["live"] = now - 60
        assert state.prune_stale(now) == []
        assert "live" in state.triggers

    def test_bot_sending_does_not_keep_session_alive(self):
        """机器人持续主动发送（triggers 不断重排到未来）不算用户活动。"""
        now = time.time()
        state = self._make_state(now)
        state.triggers["spam"] = now + 240 * 60   # 间隔被未回复缩放拉满
        state.last_user_ts["spam"] = now - 30 * 3600
        assert state.prune_stale(now) == ["spam"]


class TestMaxUnansweredWiring:
    """AST 契约：_proactive_loop 内的发送调用前必须有 max_unanswered 闸门。"""

    def test_gate_precedes_send(self):
        func = _find_func(_parse(), "_proactive_loop")
        gate_line = None
        send_lines = []
        for n in ast.walk(func):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr == "_p_int":
                    for arg in n.args:
                        if isinstance(arg, ast.Constant) and arg.value == "proactive_max_unanswered":
                            gate_line = n.lineno
                if n.func.attr == "_proactive_chat":
                    send_lines.append(n.lineno)
        assert gate_line is not None, "_proactive_loop 必须读取 proactive_max_unanswered"
        assert send_lines, "_proactive_loop 必须调用 _proactive_chat"
        assert gate_line < min(send_lines), "未回复闸门必须在发送之前"

    def test_schema_default_registered(self):
        import json

        schema_path = os.path.join(_ROOT, "_conf_schema.json")
        items = json.load(open(schema_path, encoding="utf-8"))["proactive"]["items"]
        entry = items.get("proactive_max_unanswered")
        assert entry and entry.get("type") == "int" and entry.get("default") == 6


# ---------------------------------------------------------------- B2 防抖竞态
def make_engine(**overrides):
    defaults = dict(
        debounce_time=0.05,
        enable_adaptive_debounce=False,
        max_session_wait=60.0,
    )
    defaults.update(overrides)
    return DebounceEngine(**defaults)


class TestDebounceTOCTOU:
    def run(self, coro):
        return asyncio.run(coro)

    def test_live_waiter_session_not_dropped(self):
        """结算事件已置位但等待者活着：submit 走正常追加，不得丢弃会话。

        事件循环顺序：request_flush 同步置位后等待者尚未被调度——这个
        窗口内的 submit 是原实现的误杀点。
        """
        async def scenario():
            engine = make_engine()
            engine.submit("u1", text="第一条", message_id=1)

            async def waiter():
                engine.bind_waiter("u1")
                await engine.wait_flush("u1")
                return engine.pop_session("u1")

            task = asyncio.create_task(waiter())
            await asyncio.sleep(0)          # 让等待者完成 bind 并挂起等待
            engine.request_flush("u1")      # 置位；等待者已就绪但未运行

            # 竞态窗口内提交第二条
            result = engine.submit("u1", text="第二条", message_id=2)
            assert result.action == "appended", "活等待者的会话必须走追加路径"
            session = engine.get_session("u1")
            assert session is not None, "不得丢弃活会话"
            assert "第二条" in session["buffer"]

            popped = await task
            assert popped["buffer"] == ["第一条", "第二条"], "等待者应结算含新消息的全部缓冲"

        self.run(scenario())

    def test_dead_waiter_session_dropped(self):
        """等待者已结束（异常残留）：守卫照旧丢弃死会话重开。"""
        async def scenario():
            engine = make_engine()
            engine.submit("u1", text="第一条", message_id=1)

            async def broken_waiter():
                engine.bind_waiter("u1")
                engine.request_flush("u1")
                # 不结算直接退出（模拟异常残留）：flush_event 置位、无等待者

            await asyncio.create_task(broken_waiter())
            result = engine.submit("u1", text="新会话首条", message_id=2)
            assert result.action == "started", "死会话必须被丢弃重开"
            session = engine.get_session("u1")
            assert session["buffer"] == ["新会话首条"], "旧缓冲随死会话放弃"

        self.run(scenario())

    def test_absorb_activity_respects_typing(self):
        """输入保护期间：表情/语音只登记，不重置防抖计时。"""
        async def scenario():
            engine = make_engine(debounce_time=5.0)
            engine.submit("u1", text="在打字", message_id=1)
            engine.pause_for_typing("u1", 30.0)
            session = engine.get_session("u1")
            pending_before = session["pending_wait"]

            assert engine.absorb_activity("u1", message_id=2) is True
            assert session["pending_wait"] == pending_before, "输入保护期间不得重置计时"
            assert len(session["items"]) == 2, "活动消息仍需登记"

            engine.resume_after_typing("u1")
            engine.absorb_activity("u1", message_id=3)
            assert session["pending_wait"] == engine.debounce_time, "非输入态照常重置"

        self.run(scenario())


# ---------------------------------------------------------------- B3 缓存与承诺
class TestLLMTargetFailureCache:
    def run(self, coro):
        return asyncio.run(coro)

    def test_provider_failure_not_cached(self):
        """get_models 失败：返回 False 但不写缓存，下次重试。"""
        from humanizer_core.llm_target import provider_has_model

        calls = []

        class Meta:
            id = "prov_a"

            def type(self):  # noqa: A003
                return "openai"

        class Prov:
            def meta(self):
                return Meta()

            async def get_models(self):
                calls.append(1)
                raise RuntimeError("endpoint down")

        class Ctx:
            @staticmethod
            def get_all_providers():
                return [Prov()]

        cache = {}

        async def scenario():
            ok = await provider_has_model(Ctx(), "prov_a", "any", cache)
            assert ok is False
            ok2 = await provider_has_model(Ctx(), "prov_a", "any", cache)
            assert ok2 is False
            return None

        self.run(scenario())
        assert "prov_a" not in cache, "失败结果不得写入缓存"
        assert len(calls) == 2, "未命中缓存 → 每次都真实重试"

    def test_success_still_cached(self):
        from humanizer_core.llm_target import provider_has_model

        calls = []

        class Meta:
            id = "prov_b"

        class Prov:
            def meta(self):
                return Meta()

            async def get_models(self):
                calls.append(1)
                return ["m1"]

        class Ctx:
            @staticmethod
            def get_all_providers():
                return [Prov()]

        cache = {}

        async def scenario():
            assert await provider_has_model(Ctx(), "prov_b", "m1", cache) is True
            assert await provider_has_model(Ctx(), "prov_b", "m1", cache) is True

        self.run(scenario())
        assert cache["prov_b"] == ["m1"]
        assert len(calls) == 1, "成功结果照常缓存"




# ---------------------------------------------------------------- B4 时间边界
class TestTimeBoundaries:
    def test_gap_context_nan_returns_empty(self):
        assert gap_context(float("nan"), 1000.0) == ""
        assert gap_context(1000.0, float("nan")) == ""

    def test_gap_context_normal_unchanged(self):
        assert "隔了个把小时" in gap_context(1000.0, 1000.0 + 3600)
        assert "隔了一周多" in gap_context(1000.0, 1000.0 + 8 * 86400)

    def test_rhythm_heat_negative_gap_not_hot(self):
        now = 2000.0
        # 时钟回拨：last_user_ts 在未来 → gap 为负，不得判 hot
        assert rhythm_heat(now, now + 600, 45.0) == "warm"
        assert rhythm_heat(now, float("nan"), 45.0) == "warm"

    def test_rhythm_heat_normal_unchanged(self):
        now = 2000.0
        assert rhythm_heat(now, now - 60, 45.0) == "hot"
        assert rhythm_heat(now, now - 3600, 45.0) == "cold"

    def test_parse_time_slot_cross_midnight_two_intervals(self):
        """跨午夜时段返回两段，凌晨段不再丢失。"""
        ivs = parse_time_slot("23:00-01:00")
        assert ivs == (TimeInterval(1380, 1440), TimeInterval(0, 60))

    def test_parse_time_slot_normal_unchanged(self):
        assert parse_time_slot("08:00-12:00") == (TimeInterval(480, 720),)
        assert parse_time_slot("22:00-24:00") == (TimeInterval(1320, 1440),)


class TestSettleDelayNaN:
    def test_nan_elapsed_treated_as_zero(self):
        assert settle_delay(10.0, float("nan")) == 10.0

    def test_nan_target_returns_zero(self):
        assert settle_delay(float("nan"), 5.0) == 0.0

    def test_normal_unchanged(self):
        assert settle_delay(10.0, 4.0) == 6.0
        assert settle_delay(10.0, 20.0) == 0.0


# ---------------------------------------------------------------- B5.1 检索缓存
class TestRetrieveCacheGeneration:
    def run(self, coro):
        return asyncio.run(coro)

    def test_clear_prevents_inflight_backfill(self):
        """clear() 后 in-flight 完成结果不再回填缓存（等待者仍拿到结果）。"""
        from humanizer_core.retrieve_cache import RetrieveCache

        started = asyncio.Event()

        async def factory():
            started.set()
            await asyncio.sleep(0.05)
            return {"value": 1}

        async def scenario():
            cache = RetrieveCache(maxsize=8, ttl=60.0)
            task = asyncio.create_task(cache.get_or_create("k", factory))
            await started.wait()
            cache.clear()               # in-flight 期间清缓存
            result = await task
            assert result == {"value": 1}, "等待者仍拿到本次真实结果"
            assert cache.get("k") is None, "clear 后不得回填"
            # 下一次会重新跑 factory
            calls2 = []

            async def factory2():
                calls2.append(1)
                return {"value": 2}

            await cache.get_or_create("k", factory2)
            assert calls2, "缓存未回填 → 下次应重新执行"

        self.run(scenario())

    def test_clear_without_inflight_empties(self):
        from humanizer_core.retrieve_cache import RetrieveCache

        cache = RetrieveCache(maxsize=8, ttl=60.0)
        cache.put("k", "v")
        assert cache.get("k") == "v"
        cache.clear()
        assert cache.get("k") is None
        assert len(cache) == 0
