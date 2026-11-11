# -*- coding: utf-8 -*-
"""v4.6.0 回归：对比度、KPI 网格、导入校验、dev 依赖固化。"""

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _lum(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    l1, l2 = sorted((_lum(a), _lum(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _token(css: str, name: str) -> str:
    match = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", css)
    if not match:
        raise AssertionError(f"tokens.css 缺少 --{name}")
    return match.group(1)


class TestWarmSandContrast(unittest.TestCase):
    """暖沙主题的主要文字组合需达到 WCAG AA（≥ 4.5:1）。"""

    def setUp(self):
        self.css = (_ROOT / "webui" / "src" / "styles" / "tokens.css").read_text(
            encoding="utf-8"
        )
        self.app = (_ROOT / "webui" / "src" / "App.vue").read_text(encoding="utf-8")

    def test_secondary_text_on_page(self):
        ratio = _contrast(_token(self.css, "hz-text-3"), _token(self.css, "hz-bg"))
        self.assertGreaterEqual(ratio, 4.5, f"text-3 对比度 {ratio:.2f}")

    def test_accent_text_on_page(self):
        ratio = _contrast(_token(self.css, "hz-pink"), _token(self.css, "hz-bg"))
        self.assertGreaterEqual(ratio, 4.5, f"accent 对比度 {ratio:.2f}")

    def test_placeholder_on_card(self):
        match = re.search(r"placeholderColor:\s*'(#[0-9a-fA-F]{6})'", self.app)
        self.assertIsNotNone(match, "App.vue 缺少 placeholderColor")
        ratio = _contrast(match.group(1), "#fffdf7")
        self.assertGreaterEqual(ratio, 4.5, f"placeholder 对比度 {ratio:.2f}")


class TestLayoutAndValidation(unittest.TestCase):
    def _read(self, rel: str) -> str:
        return (_ROOT / rel).read_text(encoding="utf-8")

    def test_overview_four_column_grid(self):
        source = self._read("webui/src/views/OverviewView.vue")
        self.assertIn(':cols="4"', source)
        self.assertIn('span="4 s:2 m:1"', source)

    def test_stats_stagger_shorter(self):
        self.assertIn("i * 25", self._read("webui/src/views/StatsView.vue"))

    def test_config_import_preview_and_validation(self):
        source = self._read("webui/src/views/ConfigView.vue")
        for token in (
            "pendingImport",
            "validateImportValue",
            "应用导入",
            "不在可选范围内",
            "需要布尔值",
        ):
            self.assertIn(token, source)


class TestDevDependencies(unittest.TestCase):
    def test_requirements_dev_exists(self):
        text = (_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("pytest", text)
        self.assertIn("playwright", text)

    def test_release_preflights_pytest(self):
        source = (_ROOT / "tools" / "release.py").read_text(encoding="utf-8")
        self.assertIn('find_spec("pytest")', source)


if __name__ == "__main__":
    unittest.main()
