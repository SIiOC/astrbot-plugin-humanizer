# -*- coding: utf-8 -*-
"""v3.8.0 情绪体系深化纯函数单测：冷落弧线 + 恢复曲线分档。

零 astrbot 依赖，直接 import humanizer_core.emotion。
"""

import unittest

from humanizer_core.emotion import (
    COLD_WAR_STAGES,
    DEFAULT_COLD_WAR_THRESHOLDS_DAYS,
    _make,
    cold_war_proactive_directive,
    cold_war_stage,
    decay_time,
    parse_thresholds_days,
    resolve_half_life_hours,
)

DAY = 86400.0
NOW = 1_800_000_000.0


class TestColdWarStage(unittest.TestCase):
    def test_below_first_threshold_no_stage(self):
        # 沉默 12 小时 < 1 天 → 空串（无弧线）
        self.assertEqual(cold_war_stage(NOW - 12 * 3600, NOW), "")

    def test_four_stages(self):
        self.assertEqual(cold_war_stage(NOW - 1.5 * DAY, NOW), "miss")
        self.assertEqual(cold_war_stage(NOW - 4 * DAY, NOW), "probe")
        self.assertEqual(cold_war_stage(NOW - 8 * DAY, NOW), "disappoint")
        self.assertEqual(cold_war_stage(NOW - 20 * DAY, NOW), "withdraw")

    def test_exact_boundaries(self):
        self.assertEqual(cold_war_stage(NOW - 3 * DAY, NOW), "probe")
        self.assertEqual(cold_war_stage(NOW - 3 * DAY + 1, NOW), "miss")
        self.assertEqual(cold_war_stage(NOW - 1 * DAY, NOW), "miss")

    def test_custom_thresholds(self):
        # 自定义两档：2 天 / 5 天 → 只映射前两档 (miss/probe)
        self.assertEqual(
            cold_war_stage(NOW - 6 * DAY, NOW, thresholds_days="2,5"), "probe"
        )
        self.assertEqual(
            cold_war_stage(NOW - 3 * DAY, NOW, thresholds_days="2,5"), "miss"
        )

    def test_missing_or_invalid_ts(self):
        self.assertEqual(cold_war_stage(None, NOW), "")
        self.assertEqual(cold_war_stage(0, NOW), "")
        self.assertEqual(cold_war_stage("x", NOW), "")
        # 时钟回拨（last_user_ts 在未来）→ 空串
        self.assertEqual(cold_war_stage(NOW + DAY, NOW), "")

    def test_stage_count_matches_thresholds(self):
        # 档位数不能超过 COLD_WAR_STAGES 长度（阈值再多也不越界）
        self.assertEqual(
            cold_war_stage(NOW - 100 * DAY, NOW, thresholds_days="1,2,3,4,5,6,7,8"),
            "withdraw",
        )


class TestParseThresholds(unittest.TestCase):
    def test_valid_sorted_dedup(self):
        self.assertEqual(parse_thresholds_days("7,1,3,3"), (1.0, 3.0, 7.0))

    def test_chinese_comma_and_spaces(self):
        self.assertEqual(parse_thresholds_days("1， 3 ，7"), (1.0, 3.0, 7.0))

    def test_fallback_when_too_few(self):
        self.assertEqual(
            parse_thresholds_days("3"), DEFAULT_COLD_WAR_THRESHOLDS_DAYS
        )
        self.assertEqual(parse_thresholds_days(""), DEFAULT_COLD_WAR_THRESHOLDS_DAYS)
        self.assertEqual(parse_thresholds_days(None), DEFAULT_COLD_WAR_THRESHOLDS_DAYS)

    def test_negative_and_garbage_ignored(self):
        self.assertEqual(
            parse_thresholds_days("-1,0,2,4"), (2.0, 4.0)
        )
        self.assertEqual(
            parse_thresholds_days("a,b"), DEFAULT_COLD_WAR_THRESHOLDS_DAYS
        )


class TestColdWarDirective(unittest.TestCase):
    def test_each_stage_has_text(self):
        for stg in COLD_WAR_STAGES:
            text = cold_war_proactive_directive(stg)
            self.assertTrue(text, stg)
            self.assertLessEqual(len(text), 120, f"{stg} 弧线指令过长会挤占 prompt")

    def test_empty_stage_no_text(self):
        self.assertEqual(cold_war_proactive_directive(""), "")
        self.assertEqual(cold_war_proactive_directive("nonexistent"), "")

    def test_appy_suppresses_arc(self):
        # appy 心情与降温弧线矛盾：正情绪下不注入
        appy = _make("appy", 0.5)
        for stg in COLD_WAR_STAGES:
            self.assertEqual(cold_war_proactive_directive(stg, appy), "", stg)

    def test_sulky_or_neutral_keeps_arc(self):
        sulky = _make("sulky", 0.4)
        neutral = {"emotion": "neutral", "intensity": 0.0}
        self.assertTrue(cold_war_proactive_directive("probe", sulky))
        self.assertTrue(cold_war_proactive_directive("disappoint", neutral))


class TestResolveHalfLife(unittest.TestCase):
    def test_short_absence_uses_base(self):
        # 缺席 1 天（<2 天阈值）→ base 8h
        self.assertEqual(resolve_half_life_hours(1 * DAY, 8.0, 2.0, 48.0), 8.0)

    def test_long_absence_uses_tier(self):
        # 缺席 3 天（≥2 天）→ 48h 慢衰
        self.assertEqual(resolve_half_life_hours(3 * DAY, 8.0, 2.0, 48.0), 48.0)

    def test_tier_never_faster_than_base(self):
        # absent_hours 配得比 base 小 → 取 max，不允许更快衰减
        self.assertEqual(resolve_half_life_hours(3 * DAY, 8.0, 2.0, 2.0), 8.0)

    def test_base_zero_means_off(self):
        self.assertEqual(resolve_half_life_hours(10 * DAY, 0.0, 2.0, 48.0), 0.0)

    def test_invalid_args_fallback(self):
        # 阈值非法 → 回落默认 2 天档：缺席 1 天仍是 base
        self.assertEqual(resolve_half_life_hours(1 * DAY, 8.0, "x", "y"), 8.0)
        # 非法阈值(<=0) → 回落默认 2/48：缺席 3 天命中慢档
        self.assertEqual(resolve_half_life_hours(3 * DAY, 8.0, -1, 0), 48.0)

    def test_invalid_elapsed_uses_base(self):
        self.assertEqual(resolve_half_life_hours("nan", 8.0, 2.0, 48.0), 8.0)
        self.assertEqual(resolve_half_life_hours(-100, 8.0, 2.0, 48.0), 8.0)


class TestDecayTimeWithTieredHalfLifeIntegration(unittest.TestCase):
    """端到端：久别的 sulky 用慢半衰期，衰减后强度更高（残留更久）。"""

    def test_long_absence_retains_more_than_short_half_life(self):
        state = _make("sulky", 0.8)
        elapsed = 3 * DAY
        # 慢半衰期（48h）残留 > 快半衰期（8h）：0.8*0.5^1.5≈0.28 vs 0.8*0.5^9≈0.002
        slow = decay_time(state, elapsed, 48.0)
        fast = decay_time(state, elapsed, 8.0)
        self.assertGreater(slow["intensity"], fast["intensity"])
        # 快衰直接归零到 neutral
        self.assertEqual(fast["emotion"], "neutral")
        # 慢衰留在 sulky（远高于 NEUTRAL_FLOOR=0.15）——"淡了但痕迹还在"
        self.assertEqual(slow["emotion"], "sulky")
        self.assertGreater(slow["intensity"], 0.15)


if __name__ == "__main__":
    unittest.main()
