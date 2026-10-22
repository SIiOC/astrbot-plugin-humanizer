# -*- coding: utf-8 -*-
"""v4.1.3：三组档位可见性回归（web_status 出口 + 控制台展示接线）。

档位（awareness_mode / emotion_mode / proactive_preset）默认 custom，用户很难在
配置页深处发现；v4.1.3 要求：状态出口带出当前值、总览页以 chip 展示、配置页档位键置顶。
"""

import ast
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse(rel):
    return ast.parse(open(os.path.join(_ROOT, rel), encoding="utf-8").read())


def _func(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} 未找到")


class TestStatusPresetFields(unittest.TestCase):
    def test_web_status_exposes_modes(self):
        fn = _func(_parse("main.py"), "web_status")
        dumped = ast.dump(fn)
        for key in ("awareness_mode", "emotion_mode", "proactive_preset"):
            self.assertIn(key, dumped, f"web_status 应暴露 {key}")

    def test_console_overview_shows_modes(self):
        src = open(os.path.join(_ROOT, "webui", "src", "views", "OverviewView.vue"),
                   encoding="utf-8").read()
        for key in ("awareness_mode", "emotion_mode", "proactive_preset"):
            self.assertIn(f"status.{key}", src, f"总览页应展示 {key}")
        self.assertIn("modeLabel(status.awareness_mode)", src)

    def test_console_config_mode_keys_first(self):
        src = open(os.path.join(_ROOT, "webui", "src", "views", "ConfigView.vue"),
                   encoding="utf-8").read()
        self.assertIn("MODE_KEYS", src)
        self.assertIn("orderedKeys", src)


if __name__ == "__main__":
    unittest.main()
