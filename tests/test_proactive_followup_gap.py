# -*- coding: utf-8 -*-
"""v4.9.2：追问时钟不得让常规时钟在追问后紧接着再发。

历史问题：常规轮在发送前先重排下一次触发，追问链独立计时；追问成功后
旧常规触发仍保留，于是出现「常规 → 19 分钟后追问 → 51 分钟后常规」。
本测试钉住两个契约：
1. `ProactiveState.reschedule_regular_after_followup` 存在且只向更晚取 max；
2. `main._bump_unanswered` 仅在 followup_stage > 0 时调用它。
"""

import ast
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _func_source(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment((_ROOT / "main.py").read_text(encoding="utf-8"), node) or ""
    return ""


class TestFollowupRegularClockGap(unittest.TestCase):
    def test_main_only_pushes_regular_clock_for_followup(self):
        source = (_ROOT / "main.py").read_text(encoding="utf-8")
        body = _func_source(ast.parse(source), "_bump_unanswered")
        self.assertTrue(body, "main.py 缺少 _bump_unanswered")
        self.assertIn("reschedule_regular_after_followup", body)
        self.assertIn("followup_stage > 0", body)

    def test_state_method_only_moves_later(self):
        source = (_ROOT / "services/proactive_state.py").read_text(encoding="utf-8")
        self.assertIn("def reschedule_regular_after_followup", source)
        tree = ast.parse(source)
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "reschedule_regular_after_followup"
        )
        body = ast.get_source_segment(source, method) or ""
        self.assertIn("candidate > float(existing)", body)
        self.assertIn("self.triggers[umo] = candidate", body)


if __name__ == "__main__":
    unittest.main()
