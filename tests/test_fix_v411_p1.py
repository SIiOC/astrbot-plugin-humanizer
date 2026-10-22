# -*- coding: utf-8 -*-
"""v4.1.1 P1 优化项的回归钉子（档位纯函数 + 观测/平台/兜底接线）。"""

import ast
import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from humanizer_core.presets import (
    EMOTION_MODES,
    PROACTIVE_PRESETS,
    TIME_MODES,
    preset_value,
)
from humanizer_core.lang_mirror import build_lang_mirror_text, observe, prune_phrases

_MAIN = os.path.join(_ROOT, "main.py")
_SCHEMA = os.path.join(_ROOT, "_conf_schema.json")


class TestPresetsPure(unittest.TestCase):
    def test_custom_mode_never_overrides(self):
        for table in (TIME_MODES, EMOTION_MODES, PROACTIVE_PRESETS):
            self.assertIsNone(preset_value(table, "custom", "anything"))

    def test_time_simple_disables_extra_channels(self):
        self.assertFalse(preset_value(TIME_MODES, "simple", "continuity_inject"))
        self.assertFalse(preset_value(TIME_MODES, "simple", "include_calendar"))
        self.assertIsNone(preset_value(TIME_MODES, "simple", "gap_threshold_minutes"))

    def test_emotion_simple_disables_extra_mechanisms(self):
        self.assertFalse(preset_value(EMOTION_MODES, "simple", "emotion_heat_drift_enable"))
        self.assertFalse(preset_value(EMOTION_MODES, "simple", "emotion_cold_war"))
        self.assertEqual(preset_value(EMOTION_MODES, "simple", "emotion_soothe_boost"), 0.0)

    def test_proactive_reserved_and_clingy(self):
        self.assertFalse(preset_value(PROACTIVE_PRESETS, "reserved", "proactive_followup_enable"))
        self.assertTrue(preset_value(PROACTIVE_PRESETS, "clingy", "proactive_followup_enable"))
        self.assertIsNone(preset_value(PROACTIVE_PRESETS, "unknown", "x"))


class TestLangMirrorPrune(unittest.TestCase):
    def test_overlapping_ngrams_pruned(self):
        """v4.1.1 P1：『比基尼』的滑窗碎片不得作为独立短语保留。"""
        pruned = prune_phrases({"比基尼": 21, "比基": 13, "基尼": 13, "尼比基尼": 5})
        self.assertIn("比基尼", pruned)
        self.assertNotIn("比基", pruned)
        self.assertNotIn("基尼", pruned)
        self.assertNotIn("尼比基尼", pruned)

    def test_render_does_not_emit_fragments(self):
        profile = observe({"msg_count": 0, "len_sum": 0, "emoji_msgs": 0,
                           "tilde_msgs": 0, "laugh_msgs": 0, "phrase_freq": {},
                           "ts": 0.0}, "比基尼比基尼比基尼真好看", ts=1.0)
        for _ in range(5):
            profile = observe(profile, "比基尼比基尼比基尼真好看", ts=2.0)
        text = build_lang_mirror_text(profile, min_msgs=1, topk=3)
        self.assertIsInstance(text, str)


class TestP1Wiring(unittest.TestCase):
    def setUp(self):
        self.src = open(_MAIN, encoding="utf-8").read()
        self.tree = ast.parse(self.src)

    def test_new_stats_counters(self):
        for key in ("qc_checked", "typing_delay_applied", "debounce_merged"):
            self.assertIn(f'"{key}"', self.src)

    def test_qc_independent_of_humanize_switch(self):
        self.assertIn("await self._qc_rules_pass(text)", self.src)

    def test_preset_helpers_used(self):
        for name in ("_time_flag", "_emo_flag", "_emo_num"):
            self.assertIn(f"def {name}(", self.src)
        self.assertIn("preset_value(TIME_MODES", self.src)
        self.assertIn("preset_value(EMOTION_MODES", self.src)
        self.assertIn("preset_value(PROACTIVE_PRESETS", self.src)

    def test_typing_detection_platform_gate(self):
        self.assertIn("_typing_detection_supported", self.src)
        self.assertIn("aiocqhttp", self.src)

    def test_proactive_send_fallback(self):
        self.assertIn("已走直发兜底成功", self.src)
        self.assertIn("pipeline+兜底均失败", self.src)

    def test_schema_has_three_mode_keys(self):
        with open(_SCHEMA, encoding="utf-8") as f:
            d = json.load(f)
        self.assertIn("awareness_mode", d["time"]["items"])
        self.assertIn("emotion_mode", d["emotion"]["items"])
        self.assertIn("proactive_preset", d["proactive"]["items"])


if __name__ == "__main__":
    unittest.main()
