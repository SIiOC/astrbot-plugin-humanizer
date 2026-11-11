# -*- coding: utf-8 -*-
"""风格审计工具的纯函数测试（不读真实数据库）。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tools.style_audit import (
    assistant_texts,
    check_goal,
    compare,
    parse_sent_texts,
    _within,
)


class TestStyleAudit(unittest.TestCase):
    def test_parse_sent_texts(self):
        lines = [
            "[2026-11-07 20:37:28.567] [Core] [INFO] [respond.stage:233]: Prepare to send - A/1: 今天有点累……\n",
            "[2026-11-07 20:38:50.543] [Core] [INFO] [respond.stage:233]: Prepare to send - A/1: 套厚点，别冻着。\n",
            "[2026-11-07 20:39:01] unrelated line\n",
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.log"
            path.write_text("".join(lines), encoding="utf-8")
            self.assertEqual(
                parse_sent_texts(str(path), 10),
                ["今天有点累……", "套厚点，别冻着。"],
            )

    def test_assistant_texts_filters_and_limits(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "用户"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "回复一"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "回复二"}]},
            {"role": "assistant", "content": "回复三"},
            {"role": "assistant", "content": [{"type": "think", "think": "思考"}]},
        ]
        self.assertEqual(assistant_texts(messages, 2), ["回复二", "回复三"])

    def test_assistant_texts_after_index(self):
        messages = [
            {"role": "assistant", "content": "旧回复"},
            {"role": "user", "content": "新用户"},
            {"role": "assistant", "content": "新回复"},
        ]
        self.assertEqual(assistant_texts(messages, 10, after_index=1), ["新回复"])

    def test_check_goal_pass(self):
        rows = [{"status": "ok"}] * 6 + [{"status": "偏差"}] * 2
        target = {"avg_chars": 20.0}
        actual = {
            "avg_chars": 22.0,
            "ellipsis_ratio": 0.4,
            "particle_ratio": 0.4,
            "short_ratio": 0.15,
        }
        checks = check_goal(target, actual, rows)
        self.assertTrue(all(item["pass"] for item in checks))

    def test_check_goal_fail(self):
        rows = [{"status": "偏差"}] * 8
        target = {"avg_chars": 20.0}
        actual = {"avg_chars": 40.0, "ellipsis_ratio": 0.0, "particle_ratio": 0.1, "short_ratio": 0.0}
        checks = check_goal(target, actual, rows)
        self.assertFalse(all(item["pass"] for item in checks))

    def test_compare_reports_deviation(self):
        target = {"avg_chars": 20.0, "ellipsis_ratio": 0.4, "particle_ratio": 0.4}
        actual = {"avg_chars": 40.0, "ellipsis_ratio": 0.0, "particle_ratio": 0.1}
        rows = compare(target, actual)
        keys = {r["key"]: r for r in rows}
        self.assertEqual(keys["avg_chars"]["status"], "偏差")
        self.assertEqual(keys["ellipsis_ratio"]["status"], "偏差")

    def test_within_tolerance(self):
        self.assertTrue(_within("avg_chars", 20, 24))
        self.assertFalse(_within("avg_chars", 20, 40))
        self.assertTrue(_within("ellipsis_ratio", 0.4, 0.5))
        self.assertFalse(_within("ellipsis_ratio", 0.4, 0.1))


if __name__ == "__main__":
    unittest.main()
