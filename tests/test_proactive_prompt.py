# -*- coding: utf-8 -*-
"""v4.0 Phase 6 第三片：主动 prompt 组装纯函数（proactive_prompt）。

钉死从 _proactive_chat 下沉的组装契约：静默估算、情绪块优先级
（弧线 > 追问 > pout）、迟到块、顺序拼接、{life} 条件注入。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import proactive_prompt as pp


class TestSilenceHours(unittest.TestCase):
    def test_from_real_ts_rounds(self):
        # 45 分钟周期第 1 次 → 约 1 小时（round 不是 int 截断为 0）
        self.assertEqual(
            pp.silence_hours_estimate(1000.0, 1000.0 + 45 * 60, 1, 45), 1
        )

    def test_no_ts_falls_back_to_period_estimate(self):
        self.assertEqual(pp.silence_hours_estimate(None, 0.0, 2, 45), 2)

    def test_future_ts_clamps_zero(self):
        self.assertEqual(pp.silence_hours_estimate(2000.0, 1000.0, 0, 45), 0)

    def test_bad_ts_falls_back(self):
        self.assertEqual(pp.silence_hours_estimate("x", 1000.0, 1, 45), 0)


class TestEmotionBlock(unittest.TestCase):
    _NOW = 2_000_000_000.0

    def test_arc_wins_and_prefixes(self):
        text, kind = pp.emotion_block(
            followup_stage=1,
            unanswered=5,
            silence_hours=200,
            pout_on=True,
            cold_war_enabled=True,
            last_user_ts=self._NOW - 20 * 86400,
            now_ts=self._NOW,
            thresholds="1,3,7,14",
            emotion_state={"emotion": "neutral", "intensity": 0.0},
        )
        self.assertEqual(kind, pp.ARC)
        self.assertTrue(text.startswith("\n\n【冷落降温】"))

    def test_followup_when_no_arc(self):
        text, kind = pp.emotion_block(
            followup_stage=1,
            unanswered=1,
            silence_hours=1,
            pout_on=True,
            cold_war_enabled=False,
            last_user_ts=None,
            now_ts=self._NOW,
        )
        self.assertEqual(kind, pp.FOLLOWUP)
        self.assertIn("轻轻带一句", text)

    def test_pout_when_enabled_no_followup(self):
        text, kind = pp.emotion_block(
            followup_stage=0,
            unanswered=1,
            silence_hours=1,
            pout_on=True,
            cold_war_enabled=False,
            last_user_ts=None,
            now_ts=self._NOW,
        )
        self.assertEqual(kind, pp.POUT)
        self.assertTrue(text)

    def test_none_when_pout_off(self):
        text, kind = pp.emotion_block(
            followup_stage=0,
            unanswered=1,
            silence_hours=1,
            pout_on=False,
            cold_war_enabled=False,
            last_user_ts=None,
            now_ts=self._NOW,
        )
        self.assertEqual((text, kind), ("", pp.NONE))

    def test_arc_disabled_with_ts_skips_arc(self):
        # 有打点但弧线开关关 → 不注入弧线，回落到 pout
        text, kind = pp.emotion_block(
            followup_stage=0,
            unanswered=1,
            silence_hours=1,
            pout_on=True,
            cold_war_enabled=False,
            last_user_ts=self._NOW - 20 * 86400,
            now_ts=self._NOW,
        )
        self.assertEqual(kind, pp.POUT)

    def test_arc_detector_exception_does_not_break(self):
        # 非法 thresholds 由 cold_war_stage 内部安全回落 → stage "" → 无弧线
        text, kind = pp.emotion_block(
            followup_stage=0,
            unanswered=0,
            silence_hours=0,
            pout_on=False,
            cold_war_enabled=True,
            last_user_ts=self._NOW,
            now_ts=self._NOW,
            thresholds=None,
        )
        self.assertEqual(kind, pp.NONE)


class TestLateBlock(unittest.TestCase):
    def test_threshold(self):
        self.assertEqual(pp.late_block(1000.0, 1000.0 + 14 * 60, 15), "")
        self.assertNotEqual(pp.late_block(1000.0, 1000.0 + 15 * 60, 15), "")

    def test_no_due_is_empty(self):
        self.assertEqual(pp.late_block(None, 1_000_000.0, 15), "")

    def test_bad_due_is_empty(self):
        self.assertEqual(pp.late_block("x", 1_000_000.0, 15), "")


class TestAssemble(unittest.TestCase):
    def test_order_base_topic_emotion_late(self):
        out = pp.assemble_prompt(
            "BASE",
            topic_block="[T]",
            emotion_block_text="[E]",
            late_block_text="[L]",
        )
        self.assertEqual(out, "BASE[T][E][L]")

    def test_empty_blocks_skipped(self):
        self.assertEqual(pp.assemble_prompt("BASE"), "BASE")
        self.assertEqual(pp.assemble_prompt("BASE", topic_block=""), "BASE")


class TestLifeForTemplate(unittest.TestCase):
    def test_with_placeholder(self):
        self.assertEqual(pp.life_for_template("a {life} b", "LIFE"), "LIFE")

    def test_without_placeholder(self):
        self.assertEqual(pp.life_for_template("a b", "LIFE"), "")


if __name__ == "__main__":
    unittest.main()
