"""拟人打字延迟（humanizer_core.typing）单元测试。

零 astrbot 依赖；随机注入固定种子验证确定性与上下界。
"""

import asyncio
import random
import unittest

from humanizer_core import typing as ht


class TestComputeDelay(unittest.TestCase):
    """compute_delay：上下界、单调性、确定性。"""

    def test_bounds_always_within_cap(self):
        rng = random.Random(20260901)
        for _ in range(500):
            d = ht.compute_delay("x" * random.randint(1, 500), inbound_len=200, hour=3, rng=rng)
            self.assertGreaterEqual(d, 0.0)
            self.assertLessEqual(d, ht.TOTAL_DELAY_CAP)

    def test_deterministic_with_seed(self):
        d1 = ht.compute_delay("你好呀", inbound_len=10, hour=12, rng=random.Random(42))
        d2 = ht.compute_delay("你好呀", inbound_len=10, hour=12, rng=random.Random(42))
        self.assertEqual(d1, d2)

    def test_longer_reply_takes_longer_on_average(self):
        """长回复的期望延迟应大于短回复（统计意义上）。"""
        rng = random.Random(7)
        short = sum(ht.compute_delay("嗯", 10, 12, rng) for _ in range(300)) / 300
        long = sum(ht.compute_delay("这" * 120, 10, 12, rng) for _ in range(300)) / 300
        self.assertGreater(long, short * 1.5)

    def test_longer_inbound_reads_longer(self):
        rng = random.Random(9)
        s = sum(ht.compute_delay("ok", 5, 12, rng) for _ in range(300)) / 300
        l = sum(ht.compute_delay("ok", 400, 12, rng) for _ in range(300)) / 300
        self.assertGreater(l, s)

    def test_night_slower_than_day_on_average(self):
        rng = random.Random(11)
        day = sum(ht.compute_delay("一" * 40, 30, 14, rng) for _ in range(300)) / 300
        night = sum(ht.compute_delay("一" * 40, 30, 4, rng) for _ in range(300)) / 300
        self.assertGreater(night, day)

    def test_empty_reply_nonzero_but_small(self):
        d = ht.compute_delay("", 0, 12, rng=random.Random(3))
        self.assertGreaterEqual(d, 0.0)


class TestTimeFactor(unittest.TestCase):
    def test_day_is_one(self):
        self.assertEqual(ht.time_factor(14), 1.0)

    def test_night_hours_slowed(self):
        for h in (23, 0, 2, 4):
            self.assertGreater(ht.time_factor(h), 1.0)

    def test_none_no_factor(self):
        self.assertEqual(ht.time_factor(None), 1.0)

    def test_cross_midnight_range(self):
        # 23~24 与 0~3 都算深夜
        self.assertEqual(ht.time_factor(23), ht.time_factor(1))


class TestSegmentGap(unittest.TestCase):
    def test_first_segment_no_gap(self):
        rng = random.Random(5)
        for _ in range(50):
            self.assertEqual(ht.segment_gap(0, rng=rng), 0.0)

    def test_later_segments_positive(self):
        rng = random.Random(6)
        for _ in range(50):
            g = ht.segment_gap(2, rng=rng)
            self.assertGreaterEqual(g, ht.SEGMENT_GAP_RANGE[0])
            self.assertLessEqual(g, ht.SEGMENT_GAP_LONG_RANGE[1])

    def test_custom_gap_range(self):
        """v3.7.1：自定义段间隔区间生效。"""
        rng = random.Random(21)
        for _ in range(200):
            g = ht.segment_gap(1, rng=rng, gap_range=(0.1, 0.2), long_prob=0.0)
            self.assertGreaterEqual(g, 0.1)
            self.assertLessEqual(g, 0.2)

    def test_custom_long_tail(self):
        """长尾概率 1.0 时必落长尾区间；0 时必落常规区间。"""
        rng = random.Random(22)
        for _ in range(100):
            g = ht.segment_gap(2, rng=rng, long_prob=1.0,
                               long_range=(5.0, 6.0), gap_range=(0.1, 0.2))
            self.assertGreaterEqual(g, 5.0)
            self.assertLessEqual(g, 6.0)
        for _ in range(100):
            g = ht.segment_gap(2, rng=rng, long_prob=0.0,
                               long_range=(5.0, 6.0), gap_range=(0.1, 0.2))
            self.assertLessEqual(g, 0.2)

    def test_invalid_params_fall_back(self):
        """非法区间/概率回落内置默认（不炸、不产生负值）。"""
        rng = random.Random(23)
        for _ in range(100):
            g = ht.segment_gap(1, rng=rng, gap_range=(0, 0),
                               long_prob="x", long_range=(-1, -2))
            self.assertGreaterEqual(g, ht.SEGMENT_GAP_RANGE[0])
            self.assertLessEqual(g, ht.SEGMENT_GAP_LONG_RANGE[1])

    def test_swapped_range_autocorrect(self):
        rng = random.Random(24)
        for _ in range(100):
            g = ht.segment_gap(1, rng=rng, gap_range=(2.0, 1.0), long_prob=0.0)
            self.assertGreaterEqual(g, 1.0)
            self.assertLessEqual(g, 2.0)

    def test_defaults_unchanged(self):
        """无参调用=旧常量行为（向后兼容）。"""
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        vals = [ht.segment_gap(1, rng=rng1) for _ in range(50)]
        vals2 = [
            ht.segment_gap(1, rng=rng2,
                           gap_range=ht.SEGMENT_GAP_RANGE,
                           long_prob=ht.SEGMENT_GAP_LONG_PROB,
                           long_range=ht.SEGMENT_GAP_LONG_RANGE)
            for _ in range(50)
        ]
        self.assertEqual(vals, vals2)


class TestApplyRhythmDelay(unittest.TestCase):
    """v3.5.0 delay-状态融合：hot 覆盖快回窗口 / cold 叠加拾起延迟 / warm 基线。"""

    def test_hot_replaces_with_window(self):
        """hot 覆盖式生效：结果落在窗口 + 快打耗时区间内，与原延迟无关。"""
        rng = random.Random(11)
        for _ in range(200):
            d = ht.apply_rhythm_delay(
                60.0, "hot", n_chars=30,
                hot_window=(1.5, 4.0), rng=rng,
            )
            self.assertGreaterEqual(d, 1.5)
            self.assertLessEqual(d, 4.0 + 30 * ht.RHYTHM_HOT_TYPE_SPEED)

    def test_hot_ignores_delay_min_respects_max(self):
        """快回意图优先：delay_min 被忽略；delay_max 仍约束。"""
        rng = random.Random(12)
        for _ in range(100):
            d = ht.apply_rhythm_delay(
                60.0, "hot", n_chars=0,
                hot_window=(1.5, 4.0), delay_min=30.0, delay_max=90.0, rng=rng,
            )
            self.assertLess(d, 5.0, "hot 必须忽略 delay_min")
        d = ht.apply_rhythm_delay(
            60.0, "hot", n_chars=0,
            hot_window=(1.5, 4.0), delay_max=2.0, rng=random.Random(13),
        )
        self.assertLessEqual(d, 2.0, "hot 必须尊重 delay_max")

    def test_cold_adds_window(self):
        """cold 叠加式生效：结果 = 原延迟 + 窗口随机值。"""
        rng = random.Random(14)
        for _ in range(200):
            d = ht.apply_rhythm_delay(
                20.0, "cold", cold_window=(10.0, 25.0), rng=rng,
            )
            self.assertGreaterEqual(d, 30.0)
            self.assertLessEqual(d, 45.0)

    def test_cold_respects_delay_max(self):
        d = ht.apply_rhythm_delay(
            20.0, "cold", cold_window=(10.0, 25.0),
            delay_max=35.0, rng=random.Random(15),
        )
        self.assertLessEqual(d, 35.0)

    def test_warm_and_invalid_window_unchanged(self):
        """warm 维持基线；窗口非法（<=0）时不动作。"""
        for heat in ("warm", "hot", "cold"):
            self.assertEqual(
                ht.apply_rhythm_delay(20.0, heat, hot_window=(0, 4), cold_window=(-1, 5)),
                20.0,
            )
        self.assertEqual(ht.apply_rhythm_delay(20.0, "warm"), 20.0)

    def test_window_min_max_swapped(self):
        """min>max 自动互换，不产生空窗口。"""
        rng = random.Random(16)
        d = ht.apply_rhythm_delay(
            60.0, "hot", n_chars=0, hot_window=(4.0, 1.5), rng=rng,
        )
        self.assertGreaterEqual(d, 1.5)
        self.assertLessEqual(d, 4.0)

    def test_cap_and_non_negative(self):
        rng = random.Random(17)
        for _ in range(200):
            d = ht.apply_rhythm_delay(
                80.0, "cold", cold_window=(10.0, 25.0), total_cap=90.0, rng=rng,
            )
            self.assertLessEqual(d, 90.0)
            self.assertGreaterEqual(d, 0.0)

    def test_deterministic_with_seed(self):
        a = ht.apply_rhythm_delay(60.0, "hot", n_chars=10, rng=random.Random(42))
        b = ht.apply_rhythm_delay(60.0, "hot", n_chars=10, rng=random.Random(42))
        self.assertEqual(a, b)
