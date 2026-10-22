# -*- coding: utf-8 -*-
"""v4.0 Phase 6：ProactiveState 容器与持久化行为契约。

从 main 下沉的 load/save 必须保持 proactive_state.json v3 结构与全部语义：
过期触发点顺延（非自适应延迟）、过期追问顺延随机周期、topic_used 剪枝
30 天、原子写入与旧扁平/v2 文件迁移。
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from services.proactive_state import ProactiveState


class _LogCapture:
    def __init__(self):
        self.records = []

    def _add(self, level):
        def fn(message):
            self.records.append((level, message))

        return fn

    def __getattr__(self, item):
        return self._add(item)


class TestRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "proactive_state.json"
        self.config = {
            "silence_after_minutes": 45,
            "silence_fluctuation_minutes": 15,
            "proactive_followup_delay_min_minutes": 12,
            "proactive_followup_delay_max_minutes": 20,
        }
        self.state = ProactiveState(
            state_file=self.path,
            config_getter=lambda k, d=None: self.config.get(k, d),
            logger=_LogCapture(),
            clock=lambda: 1_000_000.0,
            randint=lambda lo, hi: lo,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_writes_v3_schema_and_five_keys(self):
        self.state.triggers["u1"] = 123.0
        self.state.unanswered["u1"] = 2
        self.state.last_user_ts["u1"] = 120.0
        self.state.followups["u1"] = {"stage": 1, "due_ts": 200.0, "armed_ts": 150.0}
        self.state.topic_used["t"] = 99.0
        self.assertTrue(self.state.save())
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["v"], 3, "写入必须是 v3（键名 v，非 version）")
        for key in ("triggers", "unanswered", "last_user_ts", "followups", "topic_used"):
            self.assertIn(key, raw, f"v3 payload 缺 {key}")
        self.assertNotIn("version", raw)

    def test_save_no_path_returns_false(self):
        state = ProactiveState(state_file=None, clock=lambda: 0.0)
        self.assertFalse(state.save())
        # 无路径 load 也不得抛异常
        state.load()

    def test_save_missing_file_load_is_noop(self):
        self.state.load()  # 文件不存在
        self.assertEqual(self.state.triggers, {})

    def test_round_trip_restores_dicts(self):
        # 用未来时间戳：load() 会把过期触发点顺延（自身行为，见 LoadSemantics）
        future = 1_000_000.0 + 5000
        self.state.triggers["u1"] = future
        self.state.unanswered["u1"] = 3
        self.state.save()
        fresh = ProactiveState(
            state_file=self.path,
            config_getter=lambda k, d=None: self.config.get(k, d),
            logger=_LogCapture(),
            clock=lambda: 1_000_000.0,
            randint=lambda lo, hi: lo,
        )
        fresh.load()
        self.assertEqual(fresh.triggers["u1"], future)
        self.assertEqual(fresh.unanswered["u1"], 3)


class TestLoadSemantics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "proactive_state.json"
        self.now = 1_000_000.0
        self.config = {
            "silence_after_minutes": 45,
            "silence_fluctuation_minutes": 15,
            "proactive_followup_delay_min_minutes": 12,
            "proactive_followup_delay_max_minutes": 20,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _state(self, randint=None):
        return ProactiveState(
            state_file=self.path,
            config_getter=lambda k, d=None: self.config.get(k, d),
            logger=_LogCapture(),
            clock=lambda: self.now,
            randint=randint or (lambda lo, hi: lo),
        )

    def test_expired_trigger_rescheduled_into_future(self):
        # 45/15 周期：compute_next_delay 非自适应 → 未来时刻
        self.path.write_text(
            json.dumps({"v": 3, "triggers": {"u1": self.now - 100}}), encoding="utf-8"
        )
        st = self._state()
        st.load()
        self.assertGreater(st.triggers["u1"], self.now)

    def test_future_trigger_preserved(self):
        future = self.now + 5000
        self.path.write_text(
            json.dumps({"v": 3, "triggers": {"u1": future}}), encoding="utf-8"
        )
        st = self._state()
        st.load()
        self.assertEqual(st.triggers["u1"], float(future))

    def test_expired_followup_rescheduled(self):
        self.path.write_text(
            json.dumps(
                {
                    "v": 3,
                    "followups": {
                        "u1": {"stage": 1, "due_ts": self.now - 10, "armed_ts": 1.0}
                    },
                }
            ),
            encoding="utf-8",
        )
        st = self._state(randint=lambda lo, hi: lo)
        st.load()
        self.assertEqual(st.followups["u1"]["due_ts"], self.now + 12 * 60)
        self.assertEqual(st.followups["u1"]["stage"], 1, "顺延不得改动 stage")

    def test_topic_used_pruned_beyond_30_days(self):
        fresh = self.now - 5 * 86400
        stale = self.now - 40 * 86400
        self.path.write_text(
            json.dumps({"v": 3, "topic_used": {"fresh": fresh, "stale": stale}}),
            encoding="utf-8",
        )
        st = self._state()
        st.load()
        self.assertIn("fresh", st.topic_used)
        self.assertNotIn("stale", st.topic_used)

    def test_legacy_flat_file_migrates(self):
        # ≤v2.1.2 扁平 {umo: ts}：过期 → 顺延（迁移后 triggers 非空且在未来）
        self.path.write_text(
            json.dumps({"u1": self.now - 50}), encoding="utf-8"
        )
        st = self._state()
        st.load()
        self.assertIn("u1", st.triggers)
        self.assertGreater(st.triggers["u1"], self.now)

    def test_corrupt_file_keeps_empty_state(self):
        self.path.write_text("{not json", encoding="utf-8")
        st = self._state()
        st.load()
        self.assertEqual(st.triggers, {})
        self.assertEqual(st.followups, {})


class TestSchedulingOperations(unittest.TestCase):
    """v4.0 Phase 6 第二片：排程/清理/作废操作下沉后的行为契约。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "proactive_state.json"
        self.config = {
            "silence_after_minutes": 45,
            "silence_fluctuation_minutes": 15,
            "proactive_silence_scale_enable": True,
            "proactive_silence_scale_step": 0.3,
            "proactive_silence_scale_cap_minutes": 240,
        }
        self.now = 1_000_000.0
        self.state = ProactiveState(
            state_file=self.path,
            config_getter=lambda k, d=None: self.config.get(k, d),
            logger=_LogCapture(),
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_note_user_message_clears_and_schedules(self):
        self.state.unanswered["u1"] = 3
        self.state.followups["u1"] = {"stage": 2, "due_ts": 1.0, "armed_ts": 0.0}
        delay = self.state.note_user_message("u1", self.now)
        self.assertEqual(self.state.unanswered["u1"], 0, "用户发言必须清零计数")
        self.assertEqual(self.state.last_user_ts["u1"], self.now)
        self.assertNotIn("u1", self.state.followups, "用户回复必须作废追问链")
        self.assertGreater(delay, 0)
        self.assertEqual(self.state.triggers["u1"], self.now + delay * 60)

    def test_note_user_message_clears_before_computing_delay(self):
        """顺序契约：先清零再算延迟——刚回复不得吃未回复缩放。"""
        self.state.unanswered["u1"] = 5
        delay = self.state.note_user_message("u1", self.now)
        # 计数已清零 → 延迟应等于 base（45 附近，不含 1.3/1.6/1.9 放大）
        self.assertLess(delay, 45 * 1.3 + 15)

    def test_reschedule_next_scales_with_unanswered(self):
        self.state.unanswered["u1"] = 3
        delay = self.state.reschedule_next("u1", self.now)
        self.assertEqual(self.state.triggers["u1"], self.now + delay * 60)
        # 未回复 3 次 → 间隔已被放大（严格大于无放大时的 45）
        self.assertGreater(delay, 45)

    def test_reschedule_scale_disabled(self):
        self.config["proactive_silence_scale_enable"] = False
        self.state.unanswered["u1"] = 3
        delay = self.state.reschedule_next("u1", self.now)
        self.assertGreaterEqual(delay, 45 - 15)
        self.assertLessEqual(delay, 45 + 15)

    def test_prune_stale_removes_only_old(self):
        # v4.0.1：过期判据是 last_user_ts（用户最后发言）而非 triggers
        self.state.triggers["old"] = self.now - 25 * 3600
        self.state.unanswered["old"] = 1
        self.state.last_user_ts["old"] = self.now - 25 * 3600
        self.state.followups["old"] = {"stage": 1}
        self.state.triggers["fresh"] = self.now - 60
        self.state.last_user_ts["fresh"] = self.now - 60
        removed = self.state.prune_stale(self.now)
        self.assertEqual(removed, ["old"])
        for table in (
            self.state.triggers,
            self.state.unanswered,
            self.state.last_user_ts,
            self.state.followups,
        ):
            self.assertNotIn("old", table, "过期会话必须四表整体回收")
        self.assertIn("fresh", self.state.triggers)

    def test_prune_stale_noop_returns_empty(self):
        self.state.triggers["u1"] = self.now
        self.state.last_user_ts["u1"] = self.now
        self.assertEqual(self.state.prune_stale(self.now), [])

    def test_drop_session_clears_all_four(self):
        self.state.triggers["u1"] = self.now + 10
        self.state.unanswered["u1"] = 2
        self.state.last_user_ts["u1"] = self.now
        self.state.followups["u1"] = {"stage": 1}
        self.state.drop_session("u1")
        self.assertNotIn("u1", self.state.triggers)
        self.assertNotIn("u1", self.state.unanswered)
        self.assertNotIn("u1", self.state.last_user_ts)
        self.assertNotIn("u1", self.state.followups)

    def test_drop_followup_leaves_other_state(self):
        self.state.triggers["u1"] = self.now + 10
        self.state.followups["u1"] = {"stage": 1}
        self.state.drop_followup("u1")
        self.assertNotIn("u1", self.state.followups)
        self.assertIn("u1", self.state.triggers, "只作废追问，不动常规排程")

    def test_prune_topic_used_is_in_place_and_saved(self):
        """容量护栏必须原地裁剪（回归：main 曾重新赋值导致服务落盘过期数据）。"""
        # 250 条（超 200 上限）→ 丢最旧一半语义
        for i in range(250):
            self.state.topic_used[f"t{i}"] = float(i)
        alias = self.state.topic_used
        changed = self.state.prune_topic_used(200)
        self.assertTrue(changed)
        self.assertIs(self.state.topic_used, alias, "裁剪必须原地，对象标识不变")
        self.assertLess(len(self.state.topic_used), 250)
        # 落盘数据必须反映裁剪结果（同一 dict → save 读到的即裁剪后的）
        self.state.triggers["u1"] = self.now + 10
        self.state.save()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["topic_used"], self.state.topic_used)

    def test_prune_topic_used_noop_below_cap(self):
        self.state.topic_used["t"] = 1.0
        self.assertFalse(self.state.prune_topic_used(200))
        self.assertEqual(self.state.topic_used, {"t": 1.0})


class TestUnansweredAndFollowup(unittest.TestCase):
    """Phase 6 第三片：未回复计数 / sulky 喂点 / 追问布防（可注入端口）。"""

    def setUp(self):
        self.fed = []

    def _state(self, config=None, **ports):
        kwargs = dict(
            state_file=None,
            config_getter=lambda k, d=None: (config or {}).get(k, d),
            logger=_LogCapture(),
            clock=lambda: 1_000_000.0,
            randint=lambda lo, hi: lo,
        )
        kwargs.update(ports)
        return ProactiveState(**kwargs)

    # -- bump_unanswered 竞态守卫 --
    def test_bump_increments(self):
        st = self._state()
        self.assertEqual(st.bump_unanswered("u1"), {"race": False})
        self.assertEqual(st.unanswered["u1"], 1)
        st.bump_unanswered("u1")
        self.assertEqual(st.unanswered["u1"], 2)

    def test_bump_race_guard_skips_when_user_replied_after_send(self):
        st = self._state()
        st.last_user_ts["u1"] = 200.0
        # 发送开始于 100.0，用户 200.0 已回复 → 递增作废（不递增）
        self.assertEqual(st.bump_unanswered("u1", started_ts=100.0), {"race": True})
        self.assertNotIn("u1", st.unanswered)
        # 用户发言早于发送开始 → 正常递增
        self.assertEqual(st.bump_unanswered("u1", started_ts=300.0), {"race": False})
        self.assertEqual(st.unanswered["u1"], 1)

    def test_bump_coerces_corrupt_counter(self):
        st = self._state()
        st.unanswered["u1"] = "bad"  # type: ignore[assignment]
        st.bump_unanswered("u1")
        self.assertEqual(st.unanswered["u1"], 1)

    # -- sulky 喂点 --
    def test_feed_sulky_double_gate(self):
        st = self._state(
            {"proactive_pout_on_unanswered": True, "emotion_enable": True},
            sulky_feed=lambda umo: self.fed.append(umo),
        )
        st.feed_sulky("u1")
        self.assertEqual(self.fed, ["u1"])
        # pout 总闸关 → 不喂
        st2 = self._state(
            {"proactive_pout_on_unanswered": False, "emotion_enable": True},
            sulky_feed=lambda umo: self.fed.append(umo),
        )
        st2.feed_sulky("u2")
        self.assertEqual(self.fed, ["u1"])
        # emotion_enable 关 → 不喂
        st3 = self._state(
            {"proactive_pout_on_unanswered": True, "emotion_enable": False},
            sulky_feed=lambda umo: self.fed.append(umo),
        )
        st3.feed_sulky("u3")
        self.assertEqual(self.fed, ["u1"])

    def test_feed_sulky_swallows_port_exception(self):
        def boom(_umo):
            raise RuntimeError("x")

        st = self._state(
            {"proactive_pout_on_unanswered": True, "emotion_enable": True},
            sulky_feed=boom,
        )
        st.feed_sulky("u1")  # 不得抛出

    def test_feed_sulky_no_port_is_noop(self):
        st = self._state({"proactive_pout_on_unanswered": True, "emotion_enable": True})
        st.feed_sulky("u1")  # 端口缺省时静默

    # -- 冷落弧线抽离信号 --
    def test_cold_withdraw_guard_and_detector(self):
        calls = []

        def detector(last_ts, now_ts, thresholds):
            calls.append((last_ts, now_ts, thresholds))
            return "withdraw"

        cfg = {"emotion_cold_war": True, "cold_war_thresholds_days": "1,3,7"}
        st = self._state(cfg, cold_withdraw_detector=detector)
        st.last_user_ts["u1"] = 500.0
        self.assertTrue(st.cold_withdraw("u1"))
        self.assertEqual(calls[0][0], 500.0)
        self.assertEqual(calls[0][2], "1,3,7")
        # 开关关 → 不判定
        st2 = self._state(
            {"emotion_cold_war": False}, cold_withdraw_detector=detector
        )
        st2.last_user_ts["u1"] = 500.0
        self.assertFalse(st2.cold_withdraw("u1"))
        # 无用户打点 → 不判定
        st3 = self._state(cfg, cold_withdraw_detector=detector)
        self.assertFalse(st3.cold_withdraw("u1"))

    def test_cold_withdraw_exception_falls_back_false(self):
        def boom(*_a, **_k):
            raise RuntimeError("x")

        st = self._state(
            {"emotion_cold_war": True}, cold_withdraw_detector=boom
        )
        st.last_user_ts["u1"] = 500.0
        self.assertFalse(st.cold_withdraw("u1"))

    # -- 追问布防 --
    def test_arm_followup_writes_due_and_armed(self):
        st = self._state(
            {
                "proactive_followup_enable": True,
                "proactive_followup_delay_min_minutes": 12,
                "proactive_followup_delay_max_minutes": 20,
            },
            followup_decision=lambda *_a, **_k: (1, 12),
        )
        self.assertTrue(st.arm_followup("u1", 0, False))
        fu = st.followups["u1"]
        self.assertEqual(fu["stage"], 1)
        self.assertEqual(fu["due_ts"], 1_000_000.0 + 12 * 60)
        self.assertEqual(fu["armed_ts"], 1_000_000.0)

    def test_arm_followup_disabled_clears_existing_chain(self):
        st = self._state({"proactive_followup_enable": False})
        st.followups["u1"] = {"stage": 1}
        self.assertTrue(st.arm_followup("u1", 0, False), "清理残留链=状态变更")
        self.assertNotIn("u1", st.followups)
        # 已无残留 → 无变更
        self.assertFalse(st.arm_followup("u1", 0, False))

    def test_arm_followup_none_decision_clears(self):
        st = self._state(
            {"proactive_followup_enable": True},
            followup_decision=lambda *_a, **_k: None,
        )
        st.followups["u1"] = {"stage": 1}
        self.assertTrue(st.arm_followup("u1", 0, False))
        self.assertNotIn("u1", st.followups)

    def test_arm_followup_passes_cold_withdraw_to_decision(self):
        seen = {}

        def decision(_stage, **kw):
            seen.update(kw)
            return None

        st = self._state(
            {"proactive_followup_enable": True}, followup_decision=decision
        )
        st.unanswered["u1"] = 3
        st.arm_followup("u1", 1, True)
        self.assertTrue(seen["cold_withdraw"])
        self.assertEqual(seen["unanswered_after"], 3)
        self.assertTrue(seen["enabled"])


class TestMainDelegation(unittest.TestCase):
    def test_main_binds_shared_objects_and_delegates(self):
        import ast

        with open(os.path.join(_ROOT, "main.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        init = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "__init__"
        )
        # legacy 属性必须绑定容器持有的同名 dict（同一对象）
        bound = {}
        for n in ast.walk(init):
            if (
                isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Attribute)
                and isinstance(n.value.value, ast.Attribute)
                and n.value.value.attr == "_proactive_state"
            ):
                for t in n.targets:
                    if isinstance(t, ast.Attribute):
                        bound[t.attr] = n.value.attr
        expected = {
            "_next_trigger_ts": "triggers",
            "_proactive_unanswered": "unanswered",
            "_last_user_ts": "last_user_ts",
            "_proactive_followups": "followups",
            "_topic_used": "topic_used",
        }
        for legacy, attr in expected.items():
            self.assertEqual(bound.get(legacy), attr, f"{legacy} 必须绑定容器 .{attr}")

        for name, delegate in (
            ("_load_proactive_state", "load"),
            ("_save_proactive_state", "save"),
        ):
            fn = next(
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
            )
            self.assertIn(delegate, ast.dump(fn), f"{name} 必须委托 {delegate}")

    def test_aliases_never_rebound_outside_init(self):
        """服务持有的五个 dict 别名在 __init__ 之外不得被重新赋值。

        回归防线（v4.0 Phase 6 真回归）：_topic_used 曾在容量护栏里被重新赋值，
        使服务持有的同一 dict 失联 → save() 落盘过期数据。任何 `self._<alias> =`
        形式的赋值只允许出现在 __init__ 的绑定处。
        """
        import ast

        aliases = {
            "_next_trigger_ts",
            "_proactive_unanswered",
            "_last_user_ts",
            "_proactive_followups",
            "_topic_used",
        }
        with open(os.path.join(_ROOT, "main.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        offenders = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name == "__init__":
                continue
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign):
                    for t in n.targets:
                        if isinstance(t, ast.Attribute) and t.attr in aliases:
                            offenders.append((fn.name, t.attr, n.lineno))
        self.assertEqual(
            offenders, [], f"这些别名不得在 __init__ 外重新赋值（会造成服务状态失联）: {offenders}"
        )


if __name__ == "__main__":
    unittest.main()
