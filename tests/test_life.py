# -*- coding: utf-8 -*-
"""动态一天状态（v2.5）纯函数测试。"""

import unittest
from datetime import datetime

from humanizer_core.life import (
    DEFAULT_MOOD_POOL,
    DEFAULT_SCHEDULE,
    LifeSnapshot,
    build_life_context,
    mood_for_day,
    parse_schedule,
    resolve_doing,
    time_slot_of,
)


class TestParseSchedule(unittest.TestCase):
    def test_default_schedule_parses(self):
        entries = parse_schedule(DEFAULT_SCHEDULE)
        self.assertGreater(len(entries), 5)
        # 首条 00:00，逐条时间递增
        self.assertEqual(entries[0][0], 0)
        times = [e[0] for e in entries]
        self.assertEqual(times, sorted(times))

    def test_invalid_lines_skipped(self):
        text = "08:00 吃早饭\nnot a line\n9:99 非法\n24:00 非法\n\n12:30\n"
        entries = parse_schedule(text)
        self.assertEqual(entries, [(8 * 60, "吃早饭")])

    def test_empty_returns_empty(self):
        self.assertEqual(parse_schedule(""), [])
        self.assertEqual(parse_schedule(None), [])


class TestResolveDoing(unittest.TestCase):
    def setUp(self):
        self.schedule = parse_schedule(DEFAULT_SCHEDULE)

    def test_morning_breakfast(self):
        now = datetime(2026, 8, 18, 9, 15)
        self.assertEqual(resolve_doing(self.schedule, now), "在吃早饭")

    def test_noon_lunch(self):
        now = datetime(2026, 8, 18, 12, 30)
        self.assertEqual(resolve_doing(self.schedule, now), "午饭时间，在吃饭")

    def test_evening_free_time(self):
        now = datetime(2026, 8, 18, 21, 35)
        self.assertEqual(resolve_doing(self.schedule, now), "自由时间，在刷手机/看书")

    def test_deep_night_fallback(self):
        now = datetime(2026, 8, 18, 2, 0)
        # 00:00 之后第一条是 08:00，02:00 落在 00:00 条目之后 → 休息
        self.assertEqual(resolve_doing(self.schedule, now), "夜深了，在休息")

    def test_before_first_entry_uses_first(self):
        schedule = [(8 * 60, "起床"), (12 * 60, "午饭")]
        now = datetime(2026, 8, 18, 6, 30)
        self.assertEqual(resolve_doing(schedule, now), "起床")

    def test_exact_boundary_inclusive(self):
        now = datetime(2026, 8, 18, 9, 0)
        self.assertEqual(resolve_doing(self.schedule, now), "在吃早饭")

    def test_empty_schedule(self):
        self.assertEqual(resolve_doing([], datetime(2026, 8, 18, 9, 0)), "")


class TestMoodForDay(unittest.TestCase):
    def test_same_day_stable(self):
        a = mood_for_day(datetime(2026, 8, 18, 8, 0))
        b = mood_for_day(datetime(2026, 8, 18, 23, 0))
        self.assertEqual(a, b)

    def test_cross_day_varies(self):
        a = mood_for_day(datetime(2026, 8, 18, 12, 0))
        b = mood_for_day(datetime(2026, 8, 19, 12, 0))
        self.assertNotEqual(a, b)

    def test_in_pool(self):
        for d in range(1, 32):
            mood = mood_for_day(datetime(2026, 8, d, 10, 0))
            self.assertIn(mood, DEFAULT_MOOD_POOL)

    def test_empty_pool(self):
        self.assertEqual(mood_for_day(datetime(2026, 8, 18, 10, 0), ()), "")


class TestTimeSlotOf(unittest.TestCase):
    def test_slots(self):
        cases = [
            (2, "深夜"),
            (6, "凌晨"),
            (10, "上午"),
            (12, "中午"),
            (15, "下午"),
            (18, "傍晚"),
            (21, "晚上"),
            (23, "深夜"),
        ]
        for hour, expected in cases:
            self.assertEqual(time_slot_of(datetime(2026, 8, 18, hour, 0)), expected)


class TestBuildLifeContext(unittest.TestCase):
    def test_render_contains_parts(self):
        ctx = build_life_context(datetime(2026, 8, 18, 21, 35))
        self.assertIn("【你的当前状态】", ctx)
        self.assertIn("8月18日 周二", ctx)
        self.assertIn("晚上 21:35", ctx)
        self.assertIn("你正在：", ctx)
        self.assertIn("心情：", ctx)

    def test_fallback_doing_when_empty_schedule(self):
        ctx = build_life_context(
            datetime(2026, 8, 18, 10, 0), schedule="", fallback_doing="在发呆"
        )
        self.assertIn("你正在：在发呆", ctx)

    def test_mood_disabled(self):
        ctx = build_life_context(datetime(2026, 8, 18, 10, 0), enable_mood=False)
        self.assertNotIn("心情：", ctx)

    def test_life_snapshot_bool(self):
        self.assertTrue(LifeSnapshot(doing="x", mood="y", date_label="a", time_label="b"))
        self.assertFalse(LifeSnapshot())

    def test_life_snapshot_render_empty(self):
        self.assertEqual(LifeSnapshot().render(), "【你的当前状态】")


if __name__ == "__main__":
    unittest.main()
