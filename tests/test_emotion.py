# -*- coding: utf-8 -*-
"""情绪惯性引擎纯函数（humanizer_core.emotion）单元测试。

零 astrbot 依赖、零 mock；钉三档转移/衰减/安抚词/指令文案分档的全部边界。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import emotion as em


class TestBumpSulky(unittest.TestCase):
    def test_from_neutral(self):
        st = em.bump_sulky(em.neutral_state(), 0.35)
        self.assertEqual(st["emotion"], "sulky")
        self.assertAlmostEqual(st["intensity"], 0.35)

    def test_accumulates_while_sulky(self):
        st = em.bump_sulky(em.neutral_state(), 0.35)
        st = em.bump_sulky(st, 0.35)
        self.assertAlmostEqual(st["intensity"], 0.70)

    def test_overrides_appy(self):
        """被冷落以更新的为准：appy 被覆盖为 sulky、从 0 重算。"""
        st = {"emotion": "appy", "intensity": 0.8}
        st = em.bump_sulky(st, 0.35)
        self.assertEqual(st["emotion"], "sulky")
        self.assertAlmostEqual(st["intensity"], 0.35)

    def test_caps_at_one(self):
        st = em.neutral_state()
        for _ in range(10):
            st = em.bump_sulky(st, 0.35)
        self.assertEqual(st["emotion"], "sulky")
        self.assertLessEqual(st["intensity"], 1.0)

    def test_invalid_amount_falls_back(self):
        st = em.bump_sulky(em.neutral_state(), "abc")
        self.assertAlmostEqual(st["intensity"], 0.35)
        st = em.bump_sulky(em.neutral_state(), 0)  # 非正数回落默认
        self.assertAlmostEqual(st["intensity"], 0.35)

    def test_invalid_state_resets(self):
        st = em.bump_sulky(None)
        self.assertEqual(st["emotion"], "sulky")
        st = em.bump_sulky({"emotion": "angry", "intensity": 2.0})
        self.assertEqual(st["emotion"], "sulky")


class TestBumpAppy(unittest.TestCase):
    def test_from_neutral(self):
        st = em.bump_appy(em.neutral_state(), 0.4)
        self.assertEqual(st["emotion"], "appy")
        self.assertAlmostEqual(st["intensity"], 0.4)

    def test_overrides_sulky(self):
        """被哄了就是被哄了：sulky 被覆盖为 appy。"""
        st = {"emotion": "sulky", "intensity": 0.9}
        st = em.bump_appy(st, 0.4)
        self.assertEqual(st["emotion"], "appy")
        self.assertAlmostEqual(st["intensity"], 0.4)

    def test_accumulates_and_caps(self):
        st = em.bump_appy(em.neutral_state(), 0.4)
        st = em.bump_appy(st, 0.4)
        self.assertAlmostEqual(st["intensity"], 0.8)
        st = em.bump_appy(st, 0.4)
        self.assertLessEqual(st["intensity"], 1.0)


class TestDecay(unittest.TestCase):
    def test_decays_multiplicative(self):
        st = {"emotion": "sulky", "intensity": 1.0}
        st = em.decay(st, 0.6)
        self.assertAlmostEqual(st["intensity"], 0.6)
        st = em.decay(st, 0.6)
        self.assertAlmostEqual(st["intensity"], 0.36)

    def test_below_floor_returns_neutral(self):
        st = {"emotion": "sulky", "intensity": 0.2}
        st = em.decay(st, 0.6)  # 0.12 < 0.15
        self.assertEqual(st["emotion"], "neutral")
        self.assertEqual(st["intensity"], 0.0)

    def test_neutral_stays_neutral(self):
        self.assertEqual(em.decay(em.neutral_state()), em.neutral_state())

    def test_invalid_factor_falls_back(self):
        st = {"emotion": "appy", "intensity": 1.0}
        st = em.decay(st, 1.5)  # >1 非法回落 0.6
        self.assertAlmostEqual(st["intensity"], 0.6)
        st = em.decay(st, "x")
        self.assertAlmostEqual(st["intensity"], 0.36)

    def test_does_not_mutate_input(self):
        st = {"emotion": "sulky", "intensity": 1.0}
        em.decay(st, 0.6)
        self.assertAlmostEqual(st["intensity"], 1.0)


class TestHitSoothe(unittest.TestCase):
    def test_default_pool_hits(self):
        for t in ("哈哈哈哈", "谢谢你呀", "来个抱抱", "辛苦了", "辛苦啦~"):
            self.assertTrue(em.hit_soothe(t))

    def test_miss(self):
        self.assertFalse(em.hit_soothe("今天天气如何"))

    def test_custom_words(self):
        self.assertTrue(em.hit_soothe("你真乖", ["乖"]))
        self.assertFalse(em.hit_soothe("你真乖", ["可爱"]))

    def test_garbage_inputs(self):
        self.assertFalse(em.hit_soothe(None))
        self.assertFalse(em.hit_soothe(""))
        self.assertFalse(em.hit_soothe("   "))
        self.assertFalse(em.hit_soothe(12345))
        # 词池全是非字符串 → 回落默认池
        self.assertTrue(em.hit_soothe("谢谢", [None, 42]))


class TestEmotionDirective(unittest.TestCase):
    def test_neutral_empty(self):
        self.assertEqual(em.emotion_directive(em.neutral_state()), "")

    def test_low_intensity_empty(self):
        """强度低于阈值不占 token。"""
        self.assertEqual(
            em.emotion_directive({"emotion": "sulky", "intensity": 0.1}), ""
        )

    def test_sulky_tiers(self):
        light = em.emotion_directive({"emotion": "sulky", "intensity": 0.35})
        strong = em.emotion_directive({"emotion": "sulky", "intensity": 0.8})
        self.assertTrue(light)
        self.assertNotEqual(light, strong)
        self.assertIn("绝不", strong, "高强度档必须含克制约束（绝不指责）")

    def test_appy_directive(self):
        text = em.emotion_directive({"emotion": "appy", "intensity": 0.5})
        self.assertTrue(text)

    def test_directive_avoids_quotes(self):
        """指令文案不含引号——防模型从指令学到问候校验拦截特征（pout 同款纪律）。"""
        for st in (
            {"emotion": "sulky", "intensity": 0.3},
            {"emotion": "sulky", "intensity": 0.9},
            {"emotion": "appy", "intensity": 0.6},
        ):
            for ch in ("\"", "'", "「", "」", "\""):
                self.assertNotIn(ch, em.emotion_directive(st))

    def test_garbage_state_empty(self):
        for bad in (None, {}, {"emotion": "x", "intensity": 1}, "sulky"):
            self.assertEqual(em.emotion_directive(bad), "")


class TestEmotionShort(unittest.TestCase):
    def test_neutral_empty(self):
        self.assertEqual(em.emotion_short(em.neutral_state()), "")

    def test_tiers_nonempty_and_distinct(self):
        s = em.emotion_short({"emotion": "sulky", "intensity": 0.5})
        a = em.emotion_short({"emotion": "appy", "intensity": 0.5})
        self.assertTrue(s and a and s != a)

    def test_low_intensity_empty(self):
        self.assertEqual(
            em.emotion_short({"emotion": "appy", "intensity": 0.1}), ""
        )


class TestDecayAndSoothePipeline(unittest.TestCase):
    """v4.0 Phase 6：从 main._track_activity 下沉的纯推进（顺序契约）。"""

    def test_soothe_promotes_to_appy(self):
        st = em.decay_and_soothe(
            em.bump_sulky(em.neutral_state()),
            "别生气啦，抱抱",
            now_ts=1000.0,
            soothe_words=["抱抱"],
        )
        self.assertEqual(st["emotion"], "appy")

    def test_no_soothe_keeps_sulky_decayed(self):
        st = em.decay_and_soothe(
            em.bump_sulky(em.neutral_state()),
            "在吗",
            now_ts=1000.0,
        )
        self.assertEqual(st["emotion"], "sulky")

    def test_time_decay_applied_before_message_decay(self):
        # ts 距今 8 小时（1 个半衰期）后强度约减半，再逐条衰减
        base = {"emotion": "appy", "intensity": 0.8, "ts": 1000.0}
        st = em.decay_and_soothe(base, "在吗", now_ts=1000.0 + 8 * 3600)
        self.assertLess(st["intensity"], 0.8 * 0.6 + 1e-9)

    def test_half_life_zero_disables_time_decay(self):
        base = {"emotion": "appy", "intensity": 0.8, "ts": 1000.0}
        st = em.decay_and_soothe(
            base, "在吗", now_ts=1000.0 + 8 * 3600, half_life_base_hours=0.0
        )
        # 时间衰减关闭 → 仅逐条衰减：0.8*0.6
        self.assertAlmostEqual(st["intensity"], 0.48, places=6)

    def test_nan_clock_does_not_crash(self):
        st = em.decay_and_soothe(
            em.neutral_state(), "在吗", now_ts=float("nan")
        )
        self.assertIn("emotion", st)


class TestHeatDrift(unittest.TestCase):
    """v4.1.0 情绪×对话热度耦合（漂移叠加式；二次调参：热度主导、关键词降格）。

    语义：hot 每条向 appy 漂移 +0.2（单条即注入，稳态 ≈0.50——主导来源）、
    cold 每条向 sulky 漂移 +0.10（两条起注入，负面建得比正面慢，稳态 ≈0.25）；
    安抚词降格为加分项（可配 soothe_boost，默认 +0.2 ≈ 一条热聊消息的量级，
    仍最后执行、方向获胜，设 0 = 安抚词完全不参与——审查轮修复的契约）；
    初见（无 prev_seen 记录）不当冷场。
    """

    def _run(self, heat, n, text="嗯", prev=100.0, **kw):
        st = em.neutral_state()
        for _ in range(n):
            st = em.decay_and_soothe(st, text, now_ts=0.0, heat=heat, prev_seen_ts=prev, **kw)
        return st

    def test_hot_accumulates_to_equilibrium(self):
        st = self._run("hot", 50, text="普通消息")
        self.assertEqual(st["emotion"], "appy")
        self.assertAlmostEqual(st["intensity"], 0.2 / (1 - 0.6), places=3)

    def test_cold_accumulates_to_equilibrium(self):
        st = self._run("cold", 50)
        self.assertEqual(st["emotion"], "sulky")
        self.assertAlmostEqual(st["intensity"], 0.10 / (1 - 0.6), places=3)

    def test_hot_first_message_visible(self):
        """灵敏度钉（v4.1.0 调参）：热聊第一条即越过渲染地板。"""
        st = self._run("hot", 1, text="普通消息")
        self.assertEqual(st["emotion"], "appy")
        self.assertAlmostEqual(st["intensity"], 0.2, places=6)
        self.assertNotEqual(em.emotion_directive(st), "", "单条热聊应立即注入轻快指令")

    def test_soothe_boost_matches_one_hot_message(self):
        """权重钉（v4.1.0 二次调参）：一个关键词 ≈ 一条热聊消息的量级。

        安抚命中（默认 boost 0.2）与单条 hot 漂移（默认 0.2）产生相同的
        appy 强度——关键词不再是一锤定音的主导事件（旧实现固定 +0.4）。
        """
        soothed = em.decay_and_soothe(
            em.neutral_state(), "哈哈", now_ts=0.0, heat="warm", prev_seen_ts=100.0
        )
        heated = em.decay_and_soothe(
            em.neutral_state(), "嗯", now_ts=0.0, heat="hot", prev_seen_ts=100.0
        )
        self.assertEqual(soothed["emotion"], "appy")
        self.assertAlmostEqual(soothed["intensity"], heated["intensity"], places=6)
        self.assertAlmostEqual(soothed["intensity"], 0.2, places=6)

    def test_soothe_boost_configurable(self):
        st = em.decay_and_soothe(
            em.neutral_state(), "哈哈", now_ts=0.0, heat="warm",
            prev_seen_ts=100.0, soothe_boost=0.3,
        )
        self.assertAlmostEqual(st["intensity"], 0.3, places=6)

    def test_zero_boost_disables_soothe(self):
        """权重钉（审查轮）：boost 非正 = 安抚词完全不参与——不增量、
        不转方向（sulky 会话里说"哈哈"也维持原状），与 heat_drift 的
        "0=关方向"同契约；面板填 0 就是关，不是回落默认量。"""
        for bad in (0, 0.0, -1.0, float("nan")):
            st = em.decay_and_soothe(
                {"emotion": "sulky", "intensity": 0.3}, "哈哈", now_ts=0.0,
                heat="warm", prev_seen_ts=100.0, soothe_boost=bad,
            )
            self.assertEqual(st["emotion"], "sulky", f"boost={bad!r} 不得转方向")
            self.assertAlmostEqual(st["intensity"], 0.3 * 0.6, places=6,
                                   msg=f"boost={bad!r} 不得产生安抚增量")
            st2 = em.decay_and_soothe(
                em.neutral_state(), "哈哈", now_ts=0.0, heat="warm",
                prev_seen_ts=100.0, soothe_boost=bad,
            )
            self.assertEqual(st2, em.neutral_state())

    def test_invalid_boost_falls_back_to_default(self):
        """无法解析（非数字）才回落默认 0.2——与"非正=关"区分开。"""
        st = em.decay_and_soothe(
            em.neutral_state(), "哈哈", now_ts=0.0, heat="warm",
            prev_seen_ts=100.0, soothe_boost="x",
        )
        self.assertEqual(st["emotion"], "appy")
        self.assertAlmostEqual(st["intensity"], 0.2, places=6)

    def test_warm_is_noop(self):
        st = self._run("warm", 30, text="普通消息")
        self.assertEqual(st, em.neutral_state())

    def test_unknown_heat_is_noop(self):
        self.assertEqual(self._run("scorching", 5), em.neutral_state())
        self.assertEqual(self._run(None, 5), em.neutral_state())

    def test_first_contact_guard(self):
        """prev_seen 缺失/非正 → heat 一律按 warm（初见不是冷场）。"""
        for prev in (None, 0, -1.0, "x"):
            st = em.decay_and_soothe(
                em.neutral_state(), "你好", now_ts=0.0, heat="cold", prev_seen_ts=prev
            )
            self.assertEqual(st, em.neutral_state(), f"prev={prev!r} 不应产生冷场漂移")

    def test_zero_drift_disables_direction(self):
        self.assertEqual(self._run("hot", 10, hot_drift=0.0), em.neutral_state())
        self.assertEqual(self._run("cold", 10, cold_drift=0.0), em.neutral_state())

    def test_hot_flips_sulky_to_appy(self):
        """热聊一条即冲淡小情绪（对方回得快，气性就该消）。"""
        st = em.decay_and_soothe(
            {"emotion": "sulky", "intensity": 0.5}, "嗯", now_ts=0.0,
            heat="hot", prev_seen_ts=100.0,
        )
        self.assertEqual(st["emotion"], "appy")

    def test_soothe_beats_cold_drift(self):
        """安抚命中保持在最后：冷场中的好话依然直转 appy（量级=可配 boost）。"""
        st = em.decay_and_soothe(
            em.neutral_state(), "哈哈", now_ts=0.0,
            heat="cold", prev_seen_ts=100.0,
        )
        self.assertEqual(st["emotion"], "appy")
        self.assertAlmostEqual(st["intensity"], 0.2, places=6)

    def test_subfloor_residue_persists_but_not_rendered(self):
        """单条 cold=0.10 低于渲染地板：状态存而不显，下一条继续累加（惯性）。

        hot 单条 0.2 已越过地板（灵敏度调参后首条即注入，见
        test_hot_first_message_visible），亚地板残值场景由 cold 方向覆盖。
        """
        st = self._run("cold", 1)
        self.assertEqual((st["emotion"], st["intensity"]), ("sulky", 0.10))
        self.assertEqual(em.emotion_directive(st), "", "亚地板状态不得注入指令")
        st2 = em.decay_and_soothe(st, "嗯", now_ts=0.0, heat="cold", prev_seen_ts=100.0)
        self.assertAlmostEqual(st2["intensity"], 0.10 * 0.6 + 0.10, places=6)
        self.assertNotEqual(em.emotion_directive(st2), "", "第二条冷场应进入注入区间")

    def test_heat_drift_pure_function(self):
        st = em.heat_drift({"emotion": "sulky", "intensity": 0.5}, "hot")
        self.assertEqual(st["emotion"], "appy")
        st = em.heat_drift({"emotion": "appy", "intensity": 0.5}, "cold")
        self.assertEqual(st["emotion"], "sulky")
        same = {"emotion": "appy", "intensity": 0.5}
        out = em.heat_drift(same, "warm")
        self.assertEqual(out, same)
        self.assertIsNot(out, same)  # 返回新对象（纯函数约定）

    def test_real_protocol_hot_climbs_above_floor(self):
        """真实写回协议仿真（v4.1.0 审查修复的回归钉）。

        复刻 main 的写入协议：写回盖 ts（_set_emotion_state）、仅在
        (emotion, intensity) 变化时写——若组合链的时间衰减步带地板
        （回归形态：decay_time 替代 decay_time_raw），亚地板残值每条
        被清零，状态将钉死在首条漂移值（0.2）永不爬升；修复后应收敛
        至约 0.50。
        """
        store = em.neutral_state()
        now = 1000.0
        for _ in range(40):
            now += 30.0  # 热聊节奏：30 秒一条
            baseline = dict(store)
            st = em.decay_and_soothe(
                baseline, "普通消息", now_ts=now, heat="hot", prev_seen_ts=100.0
            )
            if (st.get("emotion"), st.get("intensity")) != (
                baseline.get("emotion"), baseline.get("intensity")
            ):
                st = dict(st)
                st["ts"] = now  # 写回盖时间戳（prune/时间衰减依赖）
                store = st
        self.assertEqual(store["emotion"], "appy")
        self.assertGreaterEqual(store["intensity"], em.NEUTRAL_FLOOR)
        self.assertAlmostEqual(store["intensity"], 0.50, delta=0.01)
        self.assertNotAlmostEqual(store["intensity"], 0.2, delta=0.02,
                                   msg="钉死在 0.2 = 时间衰减地板回归")

    def test_real_protocol_cold_climbs_above_floor(self):
        store = em.neutral_state()
        now = 1000.0
        for _ in range(40):
            now += 1800.0  # 冷场节奏：半小时一条
            baseline = dict(store)
            st = em.decay_and_soothe(
                baseline, "嗯", now_ts=now, heat="cold", prev_seen_ts=100.0
            )
            if (st.get("emotion"), st.get("intensity")) != (
                baseline.get("emotion"), baseline.get("intensity")
            ):
                st = dict(st)
                st["ts"] = now
                store = st
        self.assertEqual(store["emotion"], "sulky")
        self.assertGreaterEqual(store["intensity"], em.NEUTRAL_FLOOR)
        self.assertLess(store["intensity"], 0.30)

    def test_reunion_directive_ignores_subfloor_residue(self):
        """v4.1.0 地板守卫：亚地板残值与 neutral 同权，不触发重逢指令。"""
        sub = {"emotion": "sulky", "intensity": 0.08}
        self.assertEqual(em.reunion_directive(sub, "days"), "")
        self.assertEqual(em.reunion_directive(sub, "long_absence"), "")
        self.assertNotEqual(em.reunion_directive({"emotion": "sulky", "intensity": 0.4}, "days"), "")

    def test_cold_war_appy_suppression_respects_floor(self):
        """v4.1.0 地板守卫：亚地板 appy 不抑制冷落弧线；达标 appy 才抑制。"""
        sub = {"emotion": "appy", "intensity": 0.12}
        ok = {"emotion": "appy", "intensity": 0.4}
        self.assertNotEqual(em.cold_war_proactive_directive("withdraw", sub), "")
        self.assertEqual(em.cold_war_proactive_directive("withdraw", ok), "")



class TestParseSootheWords(unittest.TestCase):
    def test_comma_and_cjk_comma(self):
        self.assertEqual(
            em.parse_soothe_words("抱抱, 别生气，乖"),
            ["抱抱", "别生气", "乖"],
        )

    def test_empty_and_none(self):
        self.assertEqual(em.parse_soothe_words(""), [])
        self.assertEqual(em.parse_soothe_words(None), [])

    def test_whitespace_only_items_dropped(self):
        self.assertEqual(em.parse_soothe_words(" , ,抱抱, "), ["抱抱"])


if __name__ == "__main__":
    unittest.main()
