# -*- coding: utf-8 -*-
"""v3.7.0 历法感知单测：build_calendar_line 纯格式化 + calendar_facts 实测。

lunar_python 相关用例在库缺失时自动跳过（与 HAS_HOST 模式一致）；
节日覆盖断言用「由库自身反推日期」的自洽写法，不硬编码公历日。
"""

import unittest
from datetime import datetime
from unittest.mock import patch

from humanizer_core import time_flow
from humanizer_core.time_flow import (
    DEFAULT_SENSITIVE_KEYWORDS,
    build_calendar_line,
    calendar_facts,
)

try:
    from lunar_python import Solar, Lunar  # noqa: F401

    HAS_LUNAR = True
except Exception:  # noqa: BLE001
    HAS_LUNAR = False


def _facts(lunar="", festival="", term="", sensitive=""):
    return {
        "date": "2026-09-07",
        "lunar_text": lunar,
        "festival_text": festival,
        "term_text": term,
        "sensitive_name": sensitive,
    }


class TestBuildCalendarLine(unittest.TestCase):
    def test_empty_facts_empty_line(self):
        self.assertEqual(build_calendar_line(_facts()), "")

    def test_non_dict_empty_line(self):
        self.assertEqual(build_calendar_line(None), "")
        self.assertEqual(build_calendar_line("x"), "")

    def test_normal_day_line(self):
        line = build_calendar_line(_facts(lunar="农历七月廿六", term="白露"))
        self.assertEqual(line, "今天是农历七月廿六 · 白露")

    def test_festival_line(self):
        line = build_calendar_line(_facts(lunar="农历八月十五", festival="中秋节"))
        self.assertEqual(line, "今天是农历八月十五 · 中秋节")

    def test_sensitive_day_guard_replaces_line(self):
        line = build_calendar_line(
            _facts(lunar="农历七月十五", festival="中元节", sensitive="中元节")
        )
        self.assertIn("中元节", line)
        self.assertIn("别庆祝", line)
        self.assertIn("别开玩笑", line)
        self.assertFalse(line.startswith("今天是农历"))

    def test_sensitive_guard_off_keeps_normal_line(self):
        line = build_calendar_line(
            _facts(lunar="农历七月十五", festival="中元节", sensitive="中元节"),
            sensitive_guard=False,
        )
        self.assertEqual(line, "今天是农历七月十五 · 中元节")
        self.assertNotIn("别庆祝", line)


class TestCalendarFactsNoLib(unittest.TestCase):
    def test_missing_lib_returns_date_only(self):
        with patch.object(time_flow, "Solar", None):
            facts = calendar_facts(datetime(2026, 9, 7))
        self.assertEqual(facts["date"], "2026-09-07")
        self.assertEqual(facts["lunar_text"], "")
        self.assertEqual(facts["festival_text"], "")
        self.assertEqual(facts["term_text"], "")
        self.assertEqual(facts["sensitive_name"], "")


@unittest.skipUnless(HAS_LUNAR, "需要 lunar_python 库")
class TestCalendarFactsWithLib(unittest.TestCase):
    def test_solar_term_day(self):
        # 2026-09-07 实测为白露交割日：注入节气、无敏感命中
        facts = calendar_facts(datetime(2026, 9, 7))
        self.assertEqual(facts["term_text"], "白露")
        self.assertIn("七月", facts["lunar_text"])
        self.assertEqual(facts["sensitive_name"], "")

    def test_plain_day_no_sensitive(self):
        facts = calendar_facts(datetime(2026, 6, 15))
        self.assertEqual(facts["sensitive_name"], "")
        self.assertNotEqual(facts["lunar_text"], "")

    def test_zhongyuan_via_fixed_lunar_table(self):
        """中元节（农历七月十五）：lunar_python 节日库不覆盖，靠固定农历表命中。"""
        solar = Lunar.fromYmd(2026, 7, 15).getSolar()
        dt = datetime.strptime(solar.toYmd(), "%Y-%m-%d")
        facts = calendar_facts(dt)
        self.assertEqual(facts["sensitive_name"], "中元节")
        line = build_calendar_line(facts)
        self.assertIn("别庆祝", line)

    def test_hanyi_via_fixed_lunar_table(self):
        solar = Lunar.fromYmd(2026, 10, 1).getSolar()
        dt = datetime.strptime(solar.toYmd(), "%Y-%m-%d")
        facts = calendar_facts(dt)
        self.assertEqual(facts["sensitive_name"], "寒衣节")

    def test_qingming_via_keyword_text_match(self):
        # 清明既是节气也是农历节日库成员；关键词文本包含应命中
        solar = Solar.fromYmd(2026, 4, 5)
        self.assertEqual(solar.getLunar().getJieQi(), "清明")
        facts = calendar_facts(datetime(2026, 4, 5))
        self.assertEqual(facts["sensitive_name"], "清明")

    def test_fixed_solar_sensitive_date(self):
        facts = calendar_facts(datetime(2026, 12, 13))
        self.assertEqual(facts["sensitive_name"], "国家公祭日")

    def test_extra_keywords_append(self):
        # 自定义词表（替换式传入）：内置词不再生效、自定义词生效
        solar = Lunar.fromYmd(2026, 5, 5).getSolar()  # 端午节
        dt = datetime.strptime(solar.toYmd(), "%Y-%m-%d")
        facts = calendar_facts(dt, sensitive_keywords=("端午节",))
        self.assertEqual(facts["sensitive_name"], "端午节")
        # 默认表不含端午
        facts_default = calendar_facts(dt)
        self.assertEqual(facts_default["sensitive_name"], "")

    def test_default_keywords_table_shape(self):
        for kw in ("清明", "中元节", "寒衣节", "国家公祭日"):
            self.assertIn(kw, DEFAULT_SENSITIVE_KEYWORDS)


if __name__ == "__main__":
    unittest.main()
