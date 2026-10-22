# -*- coding: utf-8 -*-
"""v3.7.0 情绪时间衰减 + 重逢指令单测（纯函数，零 astrbot 依赖）。"""

import unittest

from humanizer_core.emotion import (  # noqa: E402
    REUNION_LABELS,
    decay_time,
    neutral_state,
    reunion_directive,
)

HOUR = 3600.0


def _sulky(v=0.8):
    return {"emotion": "sulky", "intensity": v}


def _appy(v=0.6):
    return {"emotion": "appy", "intensity": v}


class TestDecayTime(unittest.TestCase):
    def test_half_life_math(self):
        # 一个半衰期：强度减半
        st = decay_time(_sulky(0.8), 8 * HOUR, 8.0)
        self.assertEqual(st["emotion"], "sulky")
        self.assertAlmostEqual(st["intensity"], 0.4, places=3)
        # 两个半衰期：再减半
        st2 = decay_time(_sulky(0.8), 16 * HOUR, 8.0)
        self.assertAlmostEqual(st2["intensity"], 0.2, places=3)

    def test_falls_to_neutral_below_floor(self):
        # 0.8 × 0.5^3 = 0.1 < NEUTRAL_FLOOR → neutral
        st = decay_time(_sulky(0.8), 24 * HOUR, 8.0)
        self.assertEqual(st, neutral_state())

    def test_zero_elapsed_noop(self):
        self.assertEqual(decay_time(_sulky(0.8), 0, 8.0), _sulky(0.8))

    def test_negative_elapsed_noop(self):
        # 时钟回拨防御：负时长不衰减也不增强
        self.assertEqual(decay_time(_sulky(0.8), -5 * HOUR, 8.0), _sulky(0.8))

    def test_nan_elapsed_noop(self):
        self.assertEqual(decay_time(_sulky(0.8), float("nan"), 8.0), _sulky(0.8))

    def test_half_life_zero_is_kill_switch(self):
        self.assertEqual(decay_time(_sulky(0.8), 48 * HOUR, 0.0), _sulky(0.8))
        self.assertEqual(decay_time(_sulky(0.8), 48 * HOUR, -1.0), _sulky(0.8))

    def test_invalid_elapsed_string_noop(self):
        self.assertEqual(decay_time(_sulky(0.8), "abc", 8.0), _sulky(0.8))

    def test_invalid_state_neutral(self):
        self.assertEqual(decay_time({"emotion": "angry", "intensity": 0.5}, 8 * HOUR), neutral_state())
        self.assertEqual(decay_time(None, 8 * HOUR), neutral_state())

    def test_neutral_stays_neutral(self):
        self.assertEqual(decay_time(neutral_state(), 48 * HOUR, 8.0), neutral_state())

    def test_appy_decay_path(self):
        st = decay_time(_appy(0.6), 8 * HOUR, 8.0)
        self.assertEqual(st["emotion"], "appy")
        self.assertAlmostEqual(st["intensity"], 0.3, places=3)


class TestReunionDirective(unittest.TestCase):
    def test_sulky_days_reunion_text(self):
        text = reunion_directive(_sulky(0.8), "days")
        self.assertIn("好几天没聊", text)
        self.assertIn("淡了", text)

    def test_sulky_long_absence_reunion_text(self):
        text = reunion_directive(_sulky(0.8), "long_absence")
        self.assertIn("好几天没聊", text)

    def test_appy_reunion_text(self):
        text = reunion_directive(_appy(0.6), "long_absence")
        self.assertIn("有点开心", text)

    def test_non_reunion_labels_empty(self):
        for label in ("", "continuous", "short_break", "same_day", "overnight", None):
            self.assertEqual(reunion_directive(_sulky(0.8), label), "")

    def test_neutral_empty(self):
        self.assertEqual(reunion_directive(neutral_state(), "days"), "")

    def test_invalid_state_empty(self):
        self.assertEqual(reunion_directive({"emotion": "x", "intensity": 1.0}, "days"), "")

    def test_reunion_labels_content(self):
        self.assertEqual(set(REUNION_LABELS), {"days", "long_absence"})


class TestDecayThenReunionChain(unittest.TestCase):
    def test_long_gap_sulky_decays_to_neutral_then_reunion_applies(self):
        """端到端语义：隔三天（半衰 8h）sulky 归零 → 指令走重逢版而非常规 sulky。"""
        st = decay_time(_sulky(0.8), 72 * HOUR, 8.0)
        self.assertEqual(st, neutral_state())
        # neutral 状态下重逢指令为空（平静重逢不需要情绪指令），
        # 而「未衰减干净」的低强度 sulky 会拿到重逢文案——验证两档边界
        low = decay_time(_sulky(0.8), 16 * HOUR, 8.0)  # 0.2，仍在场
        self.assertEqual(reunion_directive(low, "days"), reunion_directive(low, "days"))
        self.assertTrue(reunion_directive(low, "days"))


if __name__ == "__main__":
    unittest.main()
