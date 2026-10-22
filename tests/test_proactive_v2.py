# -*- coding: utf-8 -*-
"""主动消息 v2（v3.9.0）纯逻辑测试：话题来源选择 / 分阶段追问 / 沉默自适应间隔。

对应 humanizer_core/proactive.py 尾部的 v2 函数层；接线契约（AST）一并钉死。
"""

import ast
import json
import random
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.proactive import (
    MIN_DELAY_MINUTES,
    arm_followup_decision,
    build_followup_directive,
    build_topic_block,
    compute_next_delay,
    compute_next_delay_adaptive,
    extract_recent_turns,
    parse_proactive_extras,
    parse_topic_pool,
    parse_topic_weights,
    pick_preset_topic,
    pick_topic_source,
    recent_window_digest,
)


class _Seq:
    """伪随机源：按序吐出固定值（抽签/延迟全可控）。"""

    def __init__(self, *vals):
        self._vals = list(vals)
        self._i = 0

    def random(self):
        v = self._vals[self._i] if self._i < len(self._vals) else 0.5
        self._i += 1
        return v

    def randint(self, a, b):
        return a


# ---- 话题来源 ----


class TestParseTopicPool(unittest.TestCase):
    def test_basic_and_weights(self):
        pool = parse_topic_pool("今天有点冷\n下班路上看到一只猫|3\n\n看月亮 | 2")
        self.assertEqual(pool, [("今天有点冷", 1), ("下班路上看到一只猫", 3), ("看月亮", 2)])

    def test_bad_weight_falls_to_one(self):
        self.assertEqual(parse_topic_pool("话题|x"), [("话题", 1)])
        self.assertEqual(parse_topic_pool("话题|0"), [("话题", 1)])  # 0 收敛到 1

    def test_dedupe_and_empty(self):
        self.assertEqual(parse_topic_pool("a\na\nb"), [("a", 1), ("b", 1)])
        self.assertEqual(parse_topic_pool(""), [])
        self.assertEqual(parse_topic_pool(None), [])
        self.assertEqual(parse_topic_pool("\n \n"), [])


class TestParseTopicWeights(unittest.TestCase):
    def test_default_format(self):
        self.assertEqual(
            parse_topic_weights("history=4,life=3,preset=3"),
            {"history": 4.0, "life": 3.0, "preset": 3.0},
        )

    def test_colon_and_cn_separators(self):
        self.assertEqual(
            parse_topic_weights("history:2，life=1；preset=0.5"),
            {"history": 2.0, "life": 1.0, "preset": 0.5},
        )

    def test_invalid_skipped(self):
        self.assertEqual(parse_topic_weights("history=abc,preset=1,foo=9,life"), {"preset": 1.0})
        self.assertEqual(parse_topic_weights(""), {})


class TestPickTopicSource(unittest.TestCase):
    def test_single_mode_with_material(self):
        self.assertEqual(
            pick_topic_source("history", None, has_history=True, has_life=True, has_preset=True),
            "history",
        )

    def test_single_mode_without_material_falls_free(self):
        self.assertEqual(
            pick_topic_source("history", None, has_history=False, has_life=True, has_preset=True),
            "free",
        )

    def test_unknown_mode_is_free(self):
        for m in ("", "free", "off", "whatever"):
            self.assertEqual(
                pick_topic_source(m, None, has_history=True, has_life=True, has_preset=True),
                "free",
            )

    def test_mixed_weighted_pick(self):
        rng = _Seq(0.0)  # 落在第一段 → history
        self.assertEqual(
            pick_topic_source(
                "mixed",
                {"history": 4, "life": 3, "preset": 3},
                has_history=True,
                has_life=True,
                has_preset=True,
                rng=rng,
            ),
            "history",
        )
        rng = _Seq(0.99)  # 落在最后段 → preset
        self.assertEqual(
            pick_topic_source(
                "mixed",
                {"history": 4, "life": 3, "preset": 3},
                has_history=True,
                has_life=True,
                has_preset=True,
                rng=rng,
            ),
            "preset",
        )

    def test_mixed_excludes_unavailable(self):
        # history 无素材：即使权重最高也只能在 life/preset 里抽
        for r in (0.0, 0.3, 0.6, 0.9, 0.99):
            self.assertEqual(
                pick_topic_source(
                    "mixed",
                    {"history": 100, "life": 1, "preset": 1},
                    has_history=False,
                    has_life=True,
                    has_preset=True,
                    rng=_Seq(r),
                )
                in ("life", "preset"),
                True,
            )

    def test_mixed_all_unavailable_is_free(self):
        self.assertEqual(
            pick_topic_source("mixed", None, has_history=False, has_life=False, has_preset=False),
            "free",
        )

    def test_mixed_zero_weight_excluded(self):
        # history 权重 0：任何抽签值都到不了它
        for r in (0.0, 0.999):
            self.assertNotEqual(
                pick_topic_source(
                    "mixed",
                    {"history": 0, "life": 1, "preset": 1},
                    has_history=True,
                    has_life=True,
                    has_preset=True,
                    rng=_Seq(r),
                ),
                "history",
            )


class TestPickPresetTopic(unittest.TestCase):
    def test_weighted_pick(self):
        pool = [("a", 1), ("b", 3)]
        self.assertEqual(pick_preset_topic(pool, {}, 0, rng=_Seq(0.0)), "a")
        self.assertEqual(pick_preset_topic(pool, {}, 0, rng=_Seq(0.9)), "b")

    def test_cooldown_decay(self):
        pool = [("a", 4), ("b", 1)]
        now = 1_000_000.0
        # a 刚用过（冷却期内）：权重 4×0.25=1 与 b 的 1 同权，r=0.9 落在 b 段
        picked = pick_preset_topic(pool, {"a": now - 100}, now, 7.0, rng=_Seq(0.9))
        self.assertEqual(picked, "b")
        # a 用过很久（超出冷却）：权重恢复 4（总 5），r=0.7×5=3.5 落在 a 段 [0,4)
        picked = pick_preset_topic(pool, {"a": now - 8 * 86400}, now, 7.0, rng=_Seq(0.7))
        self.assertEqual(picked, "a")
        # 对照：a 在冷却期内时 r=0.7×2=1.4 落在 b 段
        picked = pick_preset_topic(pool, {"a": now - 100}, now, 7.0, rng=_Seq(0.7))
        self.assertEqual(picked, "b")

    def test_empty_pool(self):
        self.assertIsNone(pick_preset_topic([], {}, 0))


class TestRecentWindow(unittest.TestCase):
    def _history(self):
        return json.dumps(
            [
                {"role": "user", "content": "第一条"},
                {"role": "assistant", "content": "回一"},
                {"role": "user", "content": "[主动消息] 请自然地延续对话。"},
                {"role": "assistant", "content": "主动开口"},
                {"role": "user", "content": "后来这句"},
                {"role": "assistant", "content": "回二"},
            ]
        )

    def test_turns_skip_proactive_marker_and_keep_order(self):
        # 倒序取最近 3 条有效消息（含"主动开口"——它是 assistant 真实发言），
        # 时间正序返回
        turns = extract_recent_turns(self._history(), max_turns=3)
        self.assertEqual(
            turns,
            [
                ("assistant", "主动开口"),
                ("user", "后来这句"),
                ("assistant", "回二"),
            ],
        )
        # 放大窗口：[主动消息] 代发 user 行被跳过，只剩 5 条真实往来
        turns_all = extract_recent_turns(self._history(), max_turns=10)
        self.assertEqual(len(turns_all), 5)
        self.assertNotIn(("[主动消息] 请自然地延续对话。",), [tuple(t) for t in turns_all])

    def test_digest_renders_roles_and_escapes(self):
        digest = recent_window_digest(
            json.dumps(
                [
                    {"role": "user", "content": '说「引号」\n换行'},
                    {"role": "assistant", "content": "回"},
                ]
            )
        )
        self.assertIn("用户：", digest)
        self.assertIn("你：", digest)
        self.assertIn(" 换行", digest)  # 换行折叠为空格
        self.assertNotIn("「引号」", digest)  # 引号被转义为全角

    def test_digest_empty_on_bad_input(self):
        self.assertEqual(recent_window_digest("not-json"), "")
        self.assertEqual(recent_window_digest(None), "")
        self.assertEqual(recent_window_digest([]), "")


class TestBuildTopicBlock(unittest.TestCase):
    def test_history_requires_instruction_against_quotes(self):
        blk = build_topic_block("history", history_digest="用户：「xx」")
        self.assertIn("转述", blk)
        self.assertIn("不要用引号引用", blk)
        self.assertIn("用户：「xx」", blk)

    def test_life_embeds_text(self):
        self.assertIn("在阳台浇花", build_topic_block("life", life_text="在阳台浇花"))

    def test_preset_embeds_topic(self):
        self.assertIn("看月亮", build_topic_block("preset", topic="看月亮"))

    def test_free_and_missing_material_empty(self):
        self.assertEqual(build_topic_block("free"), "")
        self.assertEqual(build_topic_block("history", history_digest=""), "")
        self.assertEqual(build_topic_block("life", life_text=""), "")
        self.assertEqual(build_topic_block("preset", topic=""), "")


# ---- 分阶段追问 ----


class TestBuildFollowupDirective(unittest.TestCase):
    def test_stages(self):
        self.assertEqual(build_followup_directive(0), "")
        self.assertEqual(build_followup_directive(-1), "")
        self.assertEqual(build_followup_directive("x"), "")
        self.assertIn("轻轻带一句", build_followup_directive(1))
        self.assertIn("最后一次", build_followup_directive(2))
        self.assertIn("不再追", build_followup_directive(3))  # ≥2 都按收尾措辞


class TestArmFollowupDecision(unittest.TestCase):
    def _ok(self, **kw):
        base = dict(
            enabled=True,
            unanswered_after=1,
            max_unanswered=2,
            max_stage=2,
            prob=1.0,
            delay_min_minutes=12,
            delay_max_minutes=20,
            cold_withdraw=False,
            rng=_Seq(0.0, 0),
        )
        base.update(kw)
        return arm_followup_decision(0, **base)

    def test_stage0_arms_stage1(self):
        self.assertEqual(self._ok(), (1, 12))

    def test_disabled_or_withdraw_rejected(self):
        self.assertIsNone(self._ok(enabled=False))
        self.assertIsNone(self._ok(cold_withdraw=True))

    def test_stage_cap(self):
        # 刚发的已是收尾 stage（2）→ 链到头，不再布防
        self.assertIsNone(self._arm(sent=2))

    def _arm(self, sent, **kw):
        base = dict(
            enabled=True,
            unanswered_after=2,
            max_unanswered=2,
            max_stage=2,
            prob=1.0,
            delay_min_minutes=12,
            delay_max_minutes=20,
            rng=_Seq(0.0, 0),
        )
        base.update(kw)
        return arm_followup_decision(sent, **base)

    def test_stage1_arms_stage2_with_halved_prob(self):
        # prob=0.4：stage2 阈值 0.2，r=0.1 命中
        base = dict(
            enabled=True,
            unanswered_after=2,
            max_unanswered=2,
            prob=0.4,
            delay_min_minutes=12,
            delay_max_minutes=20,
            rng=_Seq(0.1, 0),
        )
        self.assertEqual(arm_followup_decision(1, **base), (2, 12))
        # r=0.3 > 0.2 不命中
        base["rng"] = _Seq(0.3, 0)
        self.assertIsNone(arm_followup_decision(1, **base))

    def test_unanswered_cap(self):
        self.assertIsNone(self._ok(unanswered_after=3, max_unanswered=2))

    def test_prob_lottery(self):
        # stage1 概率 0.6，r=0.7 不中
        self.assertIsNone(self._ok(prob=0.6, rng=_Seq(0.7, 0)))

    def test_delay_bounds_respected(self):
        out = arm_followup_decision(
            0,
            enabled=True,
            unanswered_after=1,
            prob=1.0,
            delay_min_minutes=5,
            delay_max_minutes=9,
            rng=_Seq(0.0, 7),  # randint 恒返回下限 5
        )
        self.assertEqual(out, (1, 5))


# ---- 状态 v3 兼容 ----


class TestParseProactiveExtras(unittest.TestCase):
    def test_v3_fields(self):
        data = {
            "v": 3,
            "triggers": {"a": 1.0},
            "unanswered": {"a": 1},
            "last_user_ts": {"a": 2.0},
            "followups": {
                "a": {"stage": 1, "due_ts": 3.0, "armed_ts": 2.5},
                "bad": {"stage": "x"},  # 条目级非法剔除
                "b": "not-a-dict",
            },
            "topic_used": {"看月亮": 123.0, "": 1.0, "x": "bad"},
        }
        fu, used = parse_proactive_extras(data)
        self.assertEqual(fu, {"a": {"stage": 1, "due_ts": 3.0, "armed_ts": 2.5}})
        self.assertEqual(used, {"看月亮": 123.0})

    def test_v2_and_garbage(self):
        self.assertEqual(parse_proactive_extras({"v": 2, "triggers": {}}), ({}, {}))
        self.assertEqual(parse_proactive_extras(None), ({}, {}))
        self.assertEqual(parse_proactive_extras("junk"), ({}, {}))


# ---- 沉默自适应间隔 ----


class TestComputeNextDelayAdaptive(unittest.TestCase):
    def test_zero_unanswered_equals_base(self):
        rng_a = random.Random(7)
        base = [compute_next_delay(45, 15, rng=rng_a) for _ in range(20)]
        rng_b = random.Random(7)
        adapt = [
            compute_next_delay_adaptive(45, 15, 0, scale_step=0.3, cap_minutes=240, rng=rng_b)
            for _ in range(20)
        ]
        self.assertEqual(base, adapt)

    def test_scaling_and_cap(self):
        # 固定 rng 让 compute_next_delay 取到已知值：base=45（fluctuation=0）
        for n, expect_factor in ((1, 1.3), (2, 1.6), (3, 1.9), (5, 1.9)):
            out = compute_next_delay_adaptive(
                45, 0, n, scale_step=0.3, cap_minutes=240, rng=random.Random(1)
            )
            self.assertEqual(out, int(round(45 * expect_factor)))
        # cap 生效：45×1.9=85.5→86 > cap 60 → 60
        self.assertEqual(
            compute_next_delay_adaptive(45, 0, 3, scale_step=0.3, cap_minutes=60, rng=random.Random(1)),
            60,
        )

    def test_step_zero_disables(self):
        self.assertEqual(
            compute_next_delay_adaptive(45, 0, 5, scale_step=0.0, rng=random.Random(1)), 45
        )

    def test_floor_respected(self):
        out = compute_next_delay_adaptive(
            30, 0, 1, scale_step=0.3, cap_minutes=31, rng=random.Random(1)
        )
        self.assertGreaterEqual(out, MIN_DELAY_MINUTES)


# ---- AST 接线契约（防重构断链） ----


class TestWiringContract(unittest.TestCase):
    """钉死 main.py 对 v2 函数层的接线点与状态文件 v3 结构。"""

    def setUp(self):
        self.tree = ast.parse((_ROOT / "main.py").read_text(encoding="utf-8"))

    def _imports_from_proactive(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == "humanizer_core.proactive":
                return {a.name for a in node.names}
        return set()

    def test_new_functions_imported(self):
        imported = self._imports_from_proactive()
        for fn in (
            "build_topic_block",
            "parse_topic_pool",
            "parse_topic_weights",
            "pick_preset_topic",
            "pick_topic_source",
            "recent_window_digest",
        ):
            self.assertIn(fn, imported, f"main.py 未导入 {fn}")

    def test_moved_functions_still_reachable(self):
        """v4.0 Phase 6：随实现下沉迁移的导入点必须仍可达（防重构断链）。

        - build_followup_directive → humanizer_core/proactive_prompt.py
        - compute_next_delay_adaptive / parse_proactive_extras →
          services/proactive_state.py
        """
        def _imports(path, module):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == module:
                    names |= {a.name for a in node.names}
            return names

        prompt_imports = _imports(
            _ROOT / "humanizer_core" / "proactive_prompt.py",
            "humanizer_core.proactive",
        )
        self.assertIn("build_followup_directive", prompt_imports)

        svc_imports = _imports(
            _ROOT / "services" / "proactive_state.py",
            "humanizer_core.proactive",
        )
        for fn in ("compute_next_delay_adaptive", "parse_proactive_extras"):
            self.assertIn(fn, svc_imports, f"服务未导入 {fn}")

    def test_arm_followup_decision_imported_by_service(self):
        """v4.0 Phase 6：追问布防判定下沉 ProactiveState，导入点随之迁移。

        运行路径仍必须可达：服务源码须从 humanizer_core.proactive 导入
        arm_followup_decision（或按名引用），防重构断链。
        """
        svc = ast.parse(
            (_ROOT / "services" / "proactive_state.py").read_text(encoding="utf-8")
        )
        imported = set()
        for node in ast.walk(svc):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "humanizer_core.proactive"
            ):
                imported |= {a.name for a in node.names}
        self.assertIn(
            "arm_followup_decision", imported, "服务未导入 arm_followup_decision"
        )

    def test_proactive_chat_has_followup_stage(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_proactive_chat":
                args = [a.arg for a in node.args.args]
                self.assertIn("followup_stage", args)
                return
        self.fail("_proactive_chat 不存在")

    def test_followup_state_fields(self):
        # v4.0 Phase 6：save 实现下沉 services/proactive_state.py——
        # v3 payload 的键与 "v": 3 在服务内钉定（行为契约另见
        # tests/test_proactive_state_service.py::test_save_writes_v3_schema_and_five_keys）。
        service = (_ROOT / "services" / "proactive_state.py").read_text(encoding="utf-8")
        self.assertIn('"followups": self.followups', service)
        self.assertIn('"topic_used": self.topic_used', service)
        self.assertIn('"v": 3', service)

    def test_schema_has_new_keys(self):
        schema = json.loads((_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        items = schema["proactive"]["items"]
        for key in (
            "proactive_topic_mode",
            "proactive_topic_weights",
            "proactive_topic_pool",
            "proactive_topic_repeat_cooldown_days",
            "proactive_followup_enable",
            "proactive_followup_prob",
            "proactive_followup_delay_min_minutes",
            "proactive_followup_delay_max_minutes",
            "proactive_followup_max_unanswered",
            "proactive_silence_scale_enable",
            "proactive_silence_scale_step",
            "proactive_silence_scale_cap_minutes",
        ):
            self.assertIn(key, items, f"schema 缺 {key}")
        # 追问默认关（主动消息总闸本身默认关，追问再单独默认关）
        self.assertFalse(items["proactive_followup_enable"]["default"])
        # 话题模式默认 mixed 但素材缺失自动回 free；缩放默认开
        self.assertEqual(items["proactive_topic_mode"]["default"], "mixed")
        self.assertTrue(items["proactive_silence_scale_enable"]["default"])


if __name__ == "__main__":
    unittest.main()
