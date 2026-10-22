# -*- coding: utf-8 -*-
"""humanizer_core/time_flow.py 纯函数单测（v3.0 对话间时间流动感知）。"""

import unittest
from datetime import datetime

from humanizer_core.time_flow import (
    CHINA_TZ,
    CONTINUITY_DIRECTIVES,
    LifeState,
    TimelineEntry,
    TimeInterval,
    basic_schedule_to_timeline,
    build_life_slot_text,
    build_state_block,
    build_time_block,
    continuity_label,
    continuity_text,
    extract_json_object,
    format_wall_clock,
    gap_context,
    gap_context_mixed,
    minute_of_day,
    mood_for_slot,
    parse_schedule_template,
    parse_time_slot,
    section_of,
    select_current_slot,
)

_BASE = 1_000_000.0


def ts(minutes: float) -> float:
    """距基准点偏移 minutes 分钟的墙钟秒。"""
    return _BASE + minutes * 60.0


class TestGapContext(unittest.TestCase):
    def test_none_or_missing(self):
        self.assertEqual(gap_context(None, ts(0)), "")
        self.assertEqual(gap_context(ts(0), None), "")

    def test_below_threshold_not_injected(self):
        self.assertEqual(gap_context(ts(0), ts(29)), "")
        # 语义与配置 hint 一致："不足该分钟数时不注入"（严格小于），恰好等于阈值开始注入
        self.assertEqual(gap_context(ts(0), ts(30)), "隔了个把小时")

    def test_slightly_above_threshold(self):
        self.assertEqual(gap_context(ts(0), ts(40)), "隔了个把小时")

    def test_hours(self):
        self.assertEqual(gap_context(ts(0), ts(150)), "隔了几个小时")
        self.assertEqual(gap_context(ts(0), ts(359)), "隔了几个小时")

    def test_most_of_day(self):
        self.assertEqual(gap_context(ts(0), ts(360)), "隔了大半天")
        self.assertEqual(gap_context(ts(0), ts(1439)), "隔了大半天")

    def test_days(self):
        self.assertEqual(gap_context(ts(0), ts(1440)), "隔了一天")
        self.assertEqual(gap_context(ts(0), ts(2.5 * 1440)), "隔了两天")
        self.assertEqual(gap_context(ts(0), ts(5 * 1440)), "隔了好几天")
        self.assertEqual(gap_context(ts(0), ts(9 * 1440)), "隔了一周多")

    def test_custom_threshold(self):
        self.assertEqual(gap_context(ts(0), ts(10), threshold_minutes=5), "隔了个把小时")
        self.assertEqual(gap_context(ts(0), ts(4), threshold_minutes=5), "")

    def test_clock_skew_negative(self):
        self.assertEqual(gap_context(ts(100), ts(0)), "")

    def test_garbage_input(self):
        self.assertEqual(gap_context("abc", ts(0)), "")
        self.assertEqual(gap_context(ts(0), "abc"), "")


class TestGapMixed(unittest.TestCase):
    def test_none_or_missing(self):
        self.assertEqual(gap_context_mixed(None, ts(0)), "")
        self.assertEqual(gap_context_mixed(ts(0), None), "")

    def test_below_threshold_not_injected(self):
        # 混合同样：不足阈值视为连续对话（严格小于）
        self.assertEqual(gap_context_mixed(ts(0), ts(29)), "")
        self.assertEqual(gap_context_mixed(ts(0), ts(30)), "30分钟")

    def test_precise_under_hour(self):
        self.assertEqual(gap_context_mixed(ts(0), ts(5)), "")
        self.assertEqual(gap_context_mixed(ts(0), ts(5), threshold_minutes=1), "5分钟")
        self.assertEqual(gap_context_mixed(ts(0), ts(40)), "40分钟")
        self.assertEqual(gap_context_mixed(ts(0), ts(59)), "59分钟")

    def test_precise_seconds_under_minute(self):
        # 阈值 1 分钟时，30 秒=0.5分钟<1分钟→视为连续对话空串（与 main.py 阈值语义一致）
        base = 1_000_000.0
        self.assertEqual(gap_context_mixed(base, base + 30, threshold_minutes=1), "")
        self.assertEqual(gap_context_mixed(base, base + 90, threshold_minutes=1), "1分钟")

    def test_precise_hour_with_remainder(self):
        self.assertEqual(gap_context_mixed(ts(0), ts(90)), "1小时30分钟")
        self.assertEqual(gap_context_mixed(ts(0), ts(120)), "2小时")
        self.assertEqual(gap_context_mixed(ts(0), ts(150)), "2小时30分钟")

    def test_day_plus_hours_precise(self):
        # 混合：同 day 内精确到分钟，跨天切粗（避免 1天3小时/3天5小时 的机器味）
        self.assertEqual(gap_context_mixed(ts(0), ts(1439)), "23小时59分钟")
        self.assertEqual(gap_context_mixed(ts(0), ts(24 * 60)), "隔了一天")

    def test_cross_day_coarse(self):
        # ≥1天切粗粒度（不再精确到分钟，避免"3天12小时"式机器味）
        self.assertEqual(gap_context_mixed(ts(0), ts(1440)), "隔了一天")
        self.assertEqual(gap_context_mixed(ts(0), ts(2.5 * 1440)), "隔了两天")
        self.assertEqual(gap_context_mixed(ts(0), ts(5 * 1440)), "隔了好几天")
        self.assertEqual(gap_context_mixed(ts(0), ts(9 * 1440)), "隔了一周多")

    def test_float_noise_boundary_not_lost(self):
        # 两时钟源相减的微秒级浮点噪声不得丢分钟（7499.9999 → 仍应 2小时5分钟）
        base = 1_000_000.0
        self.assertEqual(gap_context_mixed(base, base + 7499.9999, threshold_minutes=30), "2小时5分钟")
        self.assertEqual(gap_context_mixed(base, base + 299.9999, threshold_minutes=1), "5分钟")

    def test_clock_skew_and_garbage(self):
        self.assertEqual(gap_context_mixed(ts(100), ts(0)), "")
        self.assertEqual(gap_context_mixed("abc", ts(0)), "")
        self.assertEqual(gap_context_mixed(ts(0), "abc"), "")
        self.assertEqual(gap_context_mixed(float("nan"), ts(0)), "")


class TestWallClock(unittest.TestCase):
    def test_format_2026_08_20_thursday(self):
        dt = datetime(2026, 8, 20, 14, 32, tzinfo=CHINA_TZ)
        self.assertEqual(format_wall_clock(dt), "2026年08月20日 周四 14:32")

    def test_format_sunday_zero_padding(self):
        dt = datetime(2026, 8, 23, 0, 5, tzinfo=CHINA_TZ)
        self.assertEqual(format_wall_clock(dt), "2026年08月23日 周日 00:05")

    def test_minute_of_day(self):
        self.assertEqual(minute_of_day(datetime(2026, 8, 20, 14, 32)), 872)
        self.assertEqual(minute_of_day(datetime(2026, 8, 20, 0, 0)), 0)

    def test_section_of(self):
        self.assertEqual(section_of(0), "凌晨")
        self.assertEqual(section_of(720), "中午")
        self.assertEqual(section_of(872), "下午")
        self.assertEqual(section_of(1439), "深夜")


class TestBuildStateBlock(unittest.TestCase):
    """v3.0 融合点：统一时间上下文块（墙钟 + 间隙 + 生活状态单一事实源）。"""

    def setUp(self):
        self.now = datetime(2026, 8, 20, 14, 32, tzinfo=CHINA_TZ)

    def test_full_block_merge(self):
        block = build_state_block(self.now, "隔了两天", "下午 · 咖啡店打工")
        self.assertTrue(block.startswith("<time_context>"))
        self.assertTrue(block.endswith("</time_context>"))
        self.assertIn("当前时间：2026年08月20日 周四 14:32", block)
        self.assertIn("距上次交流：隔了两天", block)
        self.assertIn("当前状态：下午 · 咖啡店打工", block)
        self.assertIn("以此为准", block)
        # 墙钟只出现一次（合并块单一事实源）
        self.assertEqual(block.count("当前时间"), 1)

    def test_gap_only(self):
        block = build_state_block(self.now, "隔了一天")
        self.assertIn("距上次交流：隔了一天", block)
        self.assertNotIn("当前状态：", block)

    def test_state_only(self):
        block = build_state_block(self.now, "", "正在吃早饭 · 心情平静")
        self.assertNotIn("距上次交流", block)
        self.assertIn("当前状态：正在吃早饭 · 心情平静", block)

    def test_no_wall_clock(self):
        block = build_state_block(self.now, "隔了一天", "", include_wall_clock=False)
        self.assertNotIn("当前时间", block)
        self.assertIn("距上次交流：隔了一天", block)

    def test_timeline_label(self):
        block = build_state_block(self.now, "", "下午 · 咖啡店打工", state_label="当前时段")
        self.assertIn("当前时段：下午 · 咖啡店打工", block)
        self.assertNotIn("当前状态：", block)


class TestBuildTimeBlock(unittest.TestCase):
    """历史兼容：LLM 时间线模式时段行标签为「当前时段」。"""

    def setUp(self):
        self.now = datetime(2026, 8, 20, 14, 32, tzinfo=CHINA_TZ)

    def test_full_block(self):
        block = build_time_block(self.now, "隔了两天", "下午 · 咖啡店打工")
        self.assertTrue(block.startswith("<time_context>"))
        self.assertTrue(block.endswith("</time_context>"))
        self.assertIn("当前时间：2026年08月20日 周四 14:32", block)
        self.assertIn("距上次交流：隔了两天", block)
        self.assertIn("当前时段：下午 · 咖啡店打工", block)
        self.assertIn("以此为准", block)

    def test_minimal_block_no_gap_no_slot(self):
        block = build_time_block(self.now)
        self.assertIn("当前时间：", block)
        self.assertNotIn("距上次交流", block)
        self.assertNotIn("当前时段", block)

    def test_no_wall_clock(self):
        block = build_time_block(self.now, "隔了一天", "", include_wall_clock=False)
        self.assertNotIn("当前时间", block)
        self.assertIn("距上次交流：隔了一天", block)


class TestParseTimeSlot(unittest.TestCase):
    def test_specific_range(self):
        self.assertEqual(parse_time_slot("08:00-12:00"), (TimeInterval(480, 720),))

    def test_dash_variants_and_spaces(self):
        self.assertEqual(parse_time_slot("08:00 – 12:00"), (TimeInterval(480, 720),))
        self.assertEqual(parse_time_slot("08:00~12:00"), (TimeInterval(480, 720),))

    def test_end_24(self):
        self.assertEqual(parse_time_slot("22:00-24:00"), (TimeInterval(1320, 1440),))

    def test_cross_midnight_returns_two_intervals(self):
        # v4.0.1：跨午夜不再截断丢凌晨段——返回当日段 + 次日凌晨段
        self.assertEqual(
            parse_time_slot("23:00-01:00"),
            (TimeInterval(1380, 1440), TimeInterval(0, 60)),
        )

    def test_invalid(self):
        self.assertIsNone(parse_time_slot("25:00-26:00"))
        self.assertIsNone(parse_time_slot("10:00-10:00"))
        self.assertIsNone(parse_time_slot("12:00"))
        self.assertIsNone(parse_time_slot("abc"))
        self.assertIsNone(parse_time_slot(""))

    def test_natural_keyword(self):
        self.assertEqual(parse_time_slot("下午"), (TimeInterval(840, 1080),))
        self.assertEqual(parse_time_slot("下午茶时间"), (TimeInterval(840, 1080),))


class TestSelectCurrentSlot(unittest.TestCase):
    def setUp(self):
        self.timeline = [
            TimelineEntry("08:00-12:00", "居家休息", {"mood": "平静"}),
            TimelineEntry("下午", "咖啡店打工", {"location": "咖啡店"}),
            TimelineEntry("晚上", "追剧", {}),
        ]

    def test_specific_range_wins(self):
        m = select_current_slot(self.timeline, 9 * 60)
        self.assertIsNotNone(m)
        self.assertEqual(m.entry.schedule, "居家休息")
        self.assertEqual(m.slot_name, "上午")
        self.assertFalse(m.synthesized)

    def test_specific_over_natural_priority(self):
        tl = [
            TimelineEntry("上午", "自然时段上午", {}),
            TimelineEntry("09:00-10:00", "具体区间", {}),
        ]
        m = select_current_slot(tl, 9 * 60 + 30)
        self.assertEqual(m.entry.schedule, "具体区间")

    def test_natural_slot_match(self):
        m = select_current_slot(self.timeline, 15 * 60)
        self.assertEqual(m.entry.schedule, "咖啡店打工")
        self.assertEqual(m.slot_name, "下午")

    def test_miss_synthesizes_idle(self):
        m = select_current_slot(self.timeline, 13 * 60)  # 12:00-14:00 无命中
        self.assertTrue(m.synthesized)
        self.assertEqual(m.entry.schedule, "空闲")
        self.assertEqual(m.slot_name, "中午")
        self.assertEqual(m.entry.extra_fields, {})  # 不继承旧时段字段

    def test_late_night_synthesizes(self):
        m = select_current_slot(self.timeline, 23 * 60 + 30)
        self.assertTrue(m.synthesized)
        self.assertEqual(m.slot_name, "深夜")

    def test_empty_timeline(self):
        self.assertIsNone(select_current_slot([], 100))


class TestTimelineEntryAndLifeState(unittest.TestCase):
    def test_from_dict_filters_and_orders_extras(self):
        e = TimelineEntry.from_dict(
            {"time": "下午", "schedule": "打工", "mood": "平静", "junk": "x", "location": "  "}
        )
        self.assertIsNotNone(e)
        self.assertEqual(e.extra_fields, {"mood": "平静"})

    def test_from_dict_invalid(self):
        self.assertIsNone(TimelineEntry.from_dict({"time": "下午"}))
        self.assertIsNone(TimelineEntry.from_dict({"time": "abc", "schedule": "x"}))
        self.assertIsNone(TimelineEntry.from_dict("not a dict"))

    def test_life_state_roundtrip(self):
        raw = {
            "date": "2026-08-20",
            "schedule_summary": "周四日常",
            "timeline": [
                {"time": "08:00-12:00", "schedule": "居家休息", "mood": "平静"},
                {"time": "下午", "schedule": "咖啡店打工", "location": "咖啡店"},
            ],
        }
        st = LifeState.from_dict(raw)
        self.assertEqual(st.status, "ok")
        self.assertEqual(len(st.timeline), 2)
        again = LifeState.from_dict(st.to_dict())
        self.assertEqual(again.to_dict(), st.to_dict())

    def test_life_state_failed_without_timeline(self):
        st = LifeState.from_dict({"date": "2026-08-20", "timeline": []})
        self.assertEqual(st.status, "failed")

    def test_life_state_bad_date(self):
        self.assertIsNone(LifeState.from_dict({"date": "2026/08/20", "timeline": []}))


class TestParseScheduleTemplate(unittest.TestCase):
    def test_multi_line_with_extras(self):
        text = (
            "# 注释行\n"
            "08:00-12:00 居家休息 | 心情:平静 | 地点:家\n"
            "\n"
            "下午 咖啡店打工 | 地点：咖啡店\n"
            "坏行\n"
            "25:00-26:00 非法时间\n"
        )
        entries = parse_schedule_template(text)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].schedule, "居家休息")
        self.assertEqual(entries[0].extra_fields, {"mood": "平静", "location": "家"})
        self.assertEqual(entries[1].extra_fields, {"location": "咖啡店"})

    def test_empty(self):
        self.assertEqual(parse_schedule_template(""), [])
        self.assertEqual(parse_schedule_template("# 只有注释"), [])


class TestBasicScheduleToTimeline(unittest.TestCase):
    """v3.0 融合点：基础格式日程模板（HH:MM 描述）转时间线（回退链第二级）。"""

    def test_conversion_covers_to_next_and_last_to_24(self):
        text = "08:00 在吃早饭\n09:30 开始工作\n23:30 准备睡觉"
        entries = basic_schedule_to_timeline(text)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].time, "08:00-09:30")
        self.assertEqual(entries[0].schedule, "在吃早饭")
        self.assertEqual(entries[1].time, "09:30-23:30")
        self.assertEqual(entries[2].time, "23:30-24:00")
        for e in entries:
            self.assertTrue(e.valid)

    def test_converted_entries_selectable(self):
        entries = basic_schedule_to_timeline("08:00 在吃早饭\n12:00 午饭")
        m = select_current_slot(entries, 9 * 60)
        self.assertIsNotNone(m)
        self.assertEqual(m.entry.schedule, "在吃早饭")
        self.assertFalse(m.synthesized)
        # 22:00 落在 12:00-24:00 段
        m2 = select_current_slot(entries, 22 * 60)
        self.assertEqual(m2.entry.schedule, "午饭")

    def test_bad_lines_skipped(self):
        entries = basic_schedule_to_timeline("坏行\n08:00 有效\n25:99 非法\n")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].schedule, "有效")

    def test_empty(self):
        self.assertEqual(basic_schedule_to_timeline(""), [])
        self.assertEqual(basic_schedule_to_timeline("没有时间行"), [])


class TestMoodForSlot(unittest.TestCase):
    def test_deterministic(self):
        a = mood_for_slot("2026-08-20", "下午")
        self.assertEqual(a, mood_for_slot("2026-08-20", "下午"))

    def test_in_default_pool(self):
        self.assertIn(mood_for_slot("2026-08-20", "上午"), ("平静", "还行", "有点困", "蛮好", "期待"))

    def test_custom_pool(self):
        self.assertEqual(mood_for_slot("2026-08-20", "晚上", "甲，乙"), mood_for_slot("2026-08-20", "晚上", "甲,乙"))
        self.assertIn(mood_for_slot("2026-08-20", "晚上", "甲,乙"), ("甲", "乙"))


class TestBuildLifeSlotText(unittest.TestCase):
    def _state(self) -> LifeState:
        return LifeState(
            date="2026-08-20",
            schedule_summary="周四日常",
            timeline=[
                TimelineEntry("08:00-12:00", "居家休息", {"mood": "平静"}),
                TimelineEntry("下午", "咖啡店打工", {"location": "咖啡店", "mood": "带劲"}),
                TimelineEntry("晚上", "追剧", {}),
            ],
        )

    def test_specific_with_range_and_summary(self):
        st = self._state()
        m = select_current_slot(st.timeline, 9 * 60)
        text = build_life_slot_text(st, m, mood_enabled=False)
        self.assertIn("上午（08:00-12:00） · 居家休息", text)
        self.assertIn("心情平静", text)
        self.assertIn("（今日：周四日常）", text)

    def test_natural_with_location(self):
        st = self._state()
        m = select_current_slot(st.timeline, 15 * 60)
        text = build_life_slot_text(st, m, mood_enabled=False)
        self.assertIn("下午 · 咖啡店打工", text)
        self.assertIn("心情带劲", text)
        self.assertIn("在咖啡店", text)

    def test_mood_backfill_when_missing(self):
        st = self._state()
        m = select_current_slot(st.timeline, 21 * 60)  # 晚上 追剧，无心情
        text = build_life_slot_text(st, m, mood_enabled=True)
        self.assertIn("心情", text)
        text2 = build_life_slot_text(st, m, mood_enabled=False)
        self.assertNotIn("心情", text2)

    def test_synthesized_idle_gets_mood(self):
        st = self._state()
        m = select_current_slot(st.timeline, 13 * 60)  # 合成空闲
        text = build_life_slot_text(st, m, mood_enabled=True)
        self.assertIn("中午 · 空闲", text)
        self.assertIn("心情", text)

    def test_none_match(self):
        self.assertEqual(build_life_slot_text(self._state(), None), "")


class TestExtractJsonObject(unittest.TestCase):
    def test_fenced(self):
        self.assertEqual(extract_json_object('```json\n{"a": 1}\n```'), {"a": 1})

    def test_with_surrounding_text_and_nested(self):
        s = '前文 {"a": {"b": "x{y}"}, "c": "}" } 后文'
        self.assertEqual(extract_json_object(s), {"a": {"b": "x{y}"}, "c": "}"})

    def test_escaped_quote_in_string(self):
        self.assertEqual(extract_json_object('{"a": "say \\"hi\\""}'), {"a": 'say "hi"'})

    def test_invalid_returns_none(self):
        self.assertIsNone(extract_json_object('{"a": 1'))
        self.assertIsNone(extract_json_object(""))
        self.assertIsNone(extract_json_object("no json here"))
        self.assertIsNone(extract_json_object(None))

    def test_first_object_recovered_when_broken(self):
        # 第一个 { 不平衡时应继续找下一个候选 {
        s = 'broken { "a":  then valid {"b": 2}'
        self.assertEqual(extract_json_object(s), {"b": 2})


# ============================================================
# v3.5.0 节奏引擎：rhythm_heat 纯派生分档 + build_state_block 节奏行
# ============================================================
from humanizer_core.time_flow import rhythm_heat, RHYTHM_DIRECTIVES, build_state_block as _bsb


class TestRhythmHeat(unittest.TestCase):
    """热度分档：阈值 = silence_after_minutes 的 1/5 与 2/3。"""

    SILENCE = 45  # 分钟，默认主动消息触发间隔
    NOW = 1_000_000.0

    def ts(self, minutes_ago: float) -> float:
        return self.NOW - minutes_ago * 60

    def test_hot_below_one_fifth(self):
        # 45/5 = 9 分钟内 → hot
        self.assertEqual(rhythm_heat(self.NOW, self.ts(0), self.SILENCE), "hot")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(8.99), self.SILENCE), "hot")

    def test_warm_between_boundaries(self):
        # 9 ~ 30 分钟 → warm（45×2/3=30）
        self.assertEqual(rhythm_heat(self.NOW, self.ts(9.01), self.SILENCE), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(20), self.SILENCE), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(29.99), self.SILENCE), "warm")

    def test_cold_above_two_thirds(self):
        # >30.015 分钟（45×0.667，≈2/3）→ cold；主动消息触发点（45±波动）落在 cold 段末尾
        self.assertEqual(rhythm_heat(self.NOW, self.ts(30.1), self.SILENCE), "cold")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(45), self.SILENCE), "cold")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(300), self.SILENCE), "cold")

    def test_boundaries_exact(self):
        # 边界值：恰好 9 分钟 → warm（<9 不含 9）；30 整点 → warm（默认 0.667 的
        # 分界在 30.015，≈2/3 但非精确——亚秒级差异，行为无感）；30.1 → cold
        self.assertEqual(rhythm_heat(self.NOW, self.ts(9), self.SILENCE), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(30), self.SILENCE), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(30.1), self.SILENCE), "cold")

    def test_missing_last_user_ts_is_cold(self):
        self.assertEqual(rhythm_heat(self.NOW, None, self.SILENCE), "cold")
        self.assertEqual(rhythm_heat(self.NOW, 0, self.SILENCE), "cold")
        self.assertEqual(rhythm_heat(self.NOW, -1, self.SILENCE), "cold")

    def test_invalid_silence_is_warm(self):
        # silence 非法（<=0/非数字）→ warm（等价禁用节奏）
        self.assertEqual(rhythm_heat(self.NOW, self.ts(1), 0), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(1), -5), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(1), "abc"), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(1), None), "warm")

    def test_scaling_with_silence(self):
        # 用户改 silence=240 → 分档自动缩放为 0~48 / 48~160 / 160+
        self.assertEqual(rhythm_heat(self.NOW, self.ts(40), 240), "hot")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(100), 240), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(200), 240), "cold")

    def test_directives_shape(self):
        # hot/cold 有指令，warm 为空（不占行）
        self.assertTrue(RHYTHM_DIRECTIVES["hot"])
        self.assertTrue(RHYTHM_DIRECTIVES["cold"])
        self.assertEqual(RHYTHM_DIRECTIVES["warm"], "")


class TestBuildStateBlockRhythm(unittest.TestCase):
    """build_state_block 的 rhythm_text 参数行为。"""

    def test_rhythm_line_appended(self):
        block = _bsb(
            datetime(2026, 9, 3, 14, 0),
            gap_text="隔了2小时",
            state_text="在喝咖啡",
            rhythm_text="你们正在连续聊天中：回复保持轻快。",
        )
        # 指令文本原样出现在块内（无额外前缀）
        self.assertIn("你们正在连续聊天中：回复保持轻快。", block)
        self.assertIn("</time_context>", block)

    def test_empty_rhythm_no_line(self):
        block = _bsb(datetime(2026, 9, 3, 14, 0), gap_text="隔了1小时", rhythm_text="")
        self.assertNotIn("连续聊天", block)


class TestRhythmHeatCustomRatios(unittest.TestCase):
    """v3.5.0：用户可调分界比例（默认 0.2/0.667 仅是未调整时的方案）。"""

    NOW = 1_000_000.0

    def ts(self, minutes_ago: float) -> float:
        return self.NOW - minutes_ago * 60

    def test_custom_ratios_apply(self):
        # 自定义 0.5/0.9：45 分钟触发 → hot 0~22.5 / warm 22.5~40.5 / cold 40.5+
        self.assertEqual(rhythm_heat(self.NOW, self.ts(20), 45, hot_ratio=0.5, cold_ratio=0.9), "hot")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(30), 45, hot_ratio=0.5, cold_ratio=0.9), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(42), 45, hot_ratio=0.5, cold_ratio=0.9), "cold")

    def test_default_ratios_unchanged(self):
        # 不传比例 → 默认 0.2/0.667（原 1/5 与 2/3 方案）
        self.assertEqual(rhythm_heat(self.NOW, self.ts(8), 45), "hot")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(9.5), 45), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(31), 45), "cold")

    def test_invalid_ratios_fall_back(self):
        # 比例非法（hot≥cold / 越界 / 非数字）→ 回落默认 0.2/0.667
        # （8 分钟 < 9 → hot；31 分钟 > 30.015 → cold）
        self.assertEqual(rhythm_heat(self.NOW, self.ts(8), 45, hot_ratio=0.8, cold_ratio=0.3), "hot")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(8), 45, hot_ratio=0, cold_ratio=0.5), "hot")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(8), 45, hot_ratio="x", cold_ratio="y"), "hot")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(31), 45, hot_ratio=0.8, cold_ratio=0.3), "cold")

    def test_boundary_at_custom_ratio(self):
        # 恰好落在自定义分界：gap=45×0.5=22.5min → hot 不含（< 才是 hot）
        self.assertEqual(rhythm_heat(self.NOW, self.ts(22.5), 45, hot_ratio=0.5, cold_ratio=0.9), "warm")
        self.assertEqual(rhythm_heat(self.NOW, self.ts(40.5), 45, hot_ratio=0.5, cold_ratio=0.9), "cold")


def _cday_ts(y: int, m: int, d: int, hh: int, mm: int = 0) -> float:
    """确定性墙钟秒（东八区），供连续性分级的跨日用例。"""
    return datetime(y, m, d, hh, mm, tzinfo=CHINA_TZ).timestamp()


class TestContinuityLabel(unittest.TestCase):
    """v3.6.0 连续性分级：绝对间隔优先，跨自然日次之。"""

    def test_continuous_below_threshold(self):
        base = _cday_ts(2026, 9, 6, 14, 0)
        self.assertEqual(continuity_label(base - 600, base), "continuous")
        self.assertEqual(continuity_label(base - 29 * 60, base), "continuous")
        self.assertEqual(continuity_text(base - 600, base), "")

    def test_short_break(self):
        base = _cday_ts(2026, 9, 6, 14, 0)
        self.assertEqual(continuity_label(base - 30 * 60, base), "short_break")
        self.assertEqual(continuity_label(base - 119 * 60, base), "short_break")
        self.assertTrue(continuity_text(base - 60 * 60, base))

    def test_short_break_crosses_midnight(self):
        # 深夜连聊跨午夜：间隔 1 小时仍算短中断（绝对间隔优先于跨日）
        prev = _cday_ts(2026, 9, 5, 23, 30)
        now = _cday_ts(2026, 9, 6, 0, 30)
        self.assertEqual(continuity_label(prev, now), "short_break")

    def test_same_day(self):
        prev = _cday_ts(2026, 9, 6, 9, 0)
        now = _cday_ts(2026, 9, 6, 15, 0)
        self.assertEqual(continuity_label(prev, now), "same_day")

    def test_overnight(self):
        prev = _cday_ts(2026, 9, 5, 21, 0)
        now = _cday_ts(2026, 9, 6, 9, 0)
        self.assertEqual(continuity_label(prev, now), "overnight")

    def test_days_and_long_absence(self):
        now = _cday_ts(2026, 9, 6, 12, 0)
        self.assertEqual(continuity_label(_cday_ts(2026, 9, 1, 12, 0), now), "days")
        self.assertEqual(continuity_label(_cday_ts(2026, 8, 1, 12, 0), now), "long_absence")

    def test_unknown_and_clock_regress(self):
        base = _cday_ts(2026, 9, 6, 12, 0)
        self.assertEqual(continuity_label(None, base), "")
        self.assertEqual(continuity_label("x", base), "")
        self.assertEqual(continuity_label(base + 100, base), "")  # 时钟回拨
        self.assertEqual(continuity_text(base + 100, base), "")

    def test_custom_threshold(self):
        base = _cday_ts(2026, 9, 6, 14, 0)
        self.assertEqual(
            continuity_label(base - 45 * 60, base, threshold_minutes=60), "continuous"
        )
        self.assertEqual(
            continuity_label(base - 45 * 60, base, threshold_minutes=30), "short_break"
        )

    def test_directives_cover_all_injectable_labels(self):
        for lab in ("short_break", "same_day", "overnight", "days", "long_absence"):
            self.assertTrue(CONTINUITY_DIRECTIVES.get(lab), lab)


class TestBuildStateBlockContinuity(unittest.TestCase):
    def test_continuity_line_appended(self):
        blk = build_state_block(
            datetime(2026, 9, 6, 12, 0), "2小时", "",
            rhythm_text="节奏行", continuity_line="连续性行",
        )
        self.assertIn("距上次交流：2小时", blk)
        self.assertIn("节奏行", blk)
        self.assertIn("连续性行", blk)
        # 顺序：节奏行在连续性行之前
        self.assertLess(blk.index("节奏行"), blk.index("连续性行"))

    def test_empty_continuity_no_line(self):
        blk = build_state_block(datetime(2026, 9, 6, 12, 0), "", "", continuity_line="")
        self.assertNotIn("连续性行", blk)


if __name__ == "__main__":
    unittest.main()
