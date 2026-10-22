# -*- coding: utf-8 -*-
"""v4.0 Phase 2：两套自然时段表的边界行为钉死（合并 life/time_flow 前置契约）。

背景：插件内存在两张**刻意不同**的时段划分表——
- humanizer_core/life.py  _NATURAL_SLOTS（basic_life_slot，tuple 表）：
  深夜 00:00-05:00 / 凌晨 05:00-08:00 / 上午 08:00-11:00 / 中午 11:00-13:00 /
  下午 13:00-17:00 / 傍晚 17:00-19:00 / 晚上 19:00-23:00 / 深夜 23:00-24:00；
  `time_slot_of(now: datetime)`。
- humanizer_core/time_flow.py _NATURAL_SLOTS（timeline_slot，dict 表，
  proactive.py 投递表与之同界）：
  凌晨 00:00-06:00 / 早上 06:00-09:00 / 上午 09:00-12:00 / 中午 12:00-14:00 /
  下午 14:00-18:00 / 傍晚 18:00-20:00 / 晚上 20:00-23:00 / 深夜 23:00-24:00；
  `section_of(minute: int)`。

同一时刻在两表下归属可不同（如 06:30：life=凌晨 / timeline=早上），
且命名集合不同（life 无「早上」）。这是历史演进出的**行为差异**而非 bug：
v3.0 LLM 时间线沿用 proactive 投递表，v2.5 basic 模式保留独立表。
现有 test_life/test_time_flow 各自钉过抽样点，但缺两表全景对照与
差异点的显式记录——Phase 4+ 若做合并，必须先改本文件的预期并同步
CHANGELOG，不得静默漂移。
"""

import os
import sys
import unittest
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from humanizer_core.life import time_slot_of as life_slot
from humanizer_core.time_flow import section_of as timeline_section


def _minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _dt(hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(2026, 9, 11, h, m)


class TestLifeBasicSlots(unittest.TestCase):
    """basic_life_slot（life.py）：0/5/8/11/13/17/19/23 点边界，datetime 入参。"""

    CASES = {
        "00:00": "深夜",
        "04:59": "深夜",
        "05:00": "凌晨",   # life 系凌晨起点=05:00（timeline 系为 00:00）
        "07:59": "凌晨",
        "08:00": "上午",   # life 无「早上」档
        "10:59": "上午",
        "11:00": "中午",
        "12:59": "中午",
        "13:00": "下午",
        "16:59": "下午",
        "17:00": "傍晚",
        "18:59": "傍晚",
        "19:00": "晚上",
        "22:59": "晚上",
        "23:00": "深夜",   # 深夜跨 0 点：23:00 起
        "23:59": "深夜",
    }

    def test_boundaries(self):
        for hhmm, want in self.CASES.items():
            with self.subTest(hhmm):
                self.assertEqual(life_slot(_dt(hhmm)), want)


class TestTimelineSections(unittest.TestCase):
    """timeline_slot（time_flow.section_of）：0/6/9/12/14/18/20/23 点边界，分钟入参。"""

    CASES = {
        "00:00": "凌晨",
        "05:59": "凌晨",
        "06:00": "早上",   # 与 life 系关键差异点（life=凌晨）
        "08:59": "早上",
        "09:00": "上午",
        "11:59": "上午",
        "12:00": "中午",
        "13:59": "中午",
        "14:00": "下午",
        "17:59": "下午",
        "18:00": "傍晚",
        "19:59": "傍晚",
        "20:00": "晚上",
        "22:59": "晚上",
        "23:00": "深夜",
        "23:59": "深夜",
    }

    def test_boundaries(self):
        for hhmm, want in self.CASES.items():
            with self.subTest(hhmm):
                self.assertEqual(timeline_section(_minutes(hhmm)), want)


class TestCrossTableDivergence(unittest.TestCase):
    """两表差异的显式记录点（合并/统一前这些就是行为规格）。"""

    def test_zero_hour(self):
        # 00:30：life=深夜，timeline=凌晨 —— 命名集合不重叠的代表点
        self.assertEqual(life_slot(_dt("00:30")), "深夜")
        self.assertEqual(timeline_section(_minutes("00:30")), "凌晨")

    def test_morning_boundary_0630(self):
        # 06:30：life=凌晨（5-8），timeline=早上（6-9）
        self.assertEqual(life_slot(_dt("06:30")), "凌晨")
        self.assertEqual(timeline_section(_minutes("06:30")), "早上")

    def test_noon_boundary_1330(self):
        # 13:30：life=下午（13-17），timeline=中午（12-14）
        self.assertEqual(life_slot(_dt("13:30")), "下午")
        self.assertEqual(timeline_section(_minutes("13:30")), "中午")

    def test_dusk_boundary_1730(self):
        # 17:30：life=傍晚（17-19），timeline=下午（14-18）
        self.assertEqual(life_slot(_dt("17:30")), "傍晚")
        self.assertEqual(timeline_section(_minutes("17:30")), "下午")

    def test_dusk_boundary_1930(self):
        # 19:30：life=晚上（19-23），timeline=傍晚（18-20）
        self.assertEqual(life_slot(_dt("19:30")), "晚上")
        self.assertEqual(timeline_section(_minutes("19:30")), "傍晚")

    def test_agree_only_around_23(self):
        # 23:30 两表同为深夜（收敛区代表）
        self.assertEqual(life_slot(_dt("23:30")), "深夜")
        self.assertEqual(timeline_section(_minutes("23:30")), "深夜")


if __name__ == "__main__":
    unittest.main()
