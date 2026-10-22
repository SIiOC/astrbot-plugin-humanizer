# -*- coding: utf-8 -*-
"""colleague-skill 产物导入器测试（parse_colleague_meta / build_colleague_import_prompt）。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_core import colleague_import


class TestParseColleagueMeta(unittest.TestCase):
    def test_plain_json(self):
        text = '{"name": "张三", "slug": "example_zhangsan", "impression": "评审会上抛问题"}'
        meta = colleague_import.parse_colleague_meta(text)
        self.assertEqual(meta["name"], "张三")
        self.assertEqual(meta["impression"], "评审会上抛问题")

    def test_markdown_fenced(self):
        text = '```json\n{"slug": "example_zhangsan"}\n```'
        meta = colleague_import.parse_colleague_meta(text)
        self.assertEqual(meta["slug"], "example_zhangsan")

    def test_text_surrounding(self):
        text = '这是 meta：\n{"profile": {"level": "2-1"}} 结束'
        meta = colleague_import.parse_colleague_meta(text)
        self.assertEqual(meta["profile"]["level"], "2-1")

    def test_invalid(self):
        self.assertIsNone(colleague_import.parse_colleague_meta(""))
        self.assertIsNone(colleague_import.parse_colleague_meta("not json"))
        self.assertIsNone(colleague_import.parse_colleague_meta("[1,2,3]"))
        self.assertIsNone(colleague_import.parse_colleague_meta(None))
        self.assertIsNone(colleague_import.parse_colleague_meta("没有花括号"))


class TestBuildColleagueImportPrompt(unittest.TestCase):
    def _persona(self):
        return (
            "# 张三 — Persona\n"
            "## Layer 2 表达风格\n"
            "口头禅：「先对齐一下」\n"
            "## Layer 3 决策\n"
            "数据 > 人情\n"
        )

    def test_contains_persona_text(self):
        prompt = colleague_import.build_colleague_import_prompt(None, self._persona())
        self.assertIn("先对齐一下", prompt)
        self.assertIn("数据 > 人情", prompt)

    def test_contains_meta_brief(self):
        meta = {"impression": "评审会上抛问题", "profile": {"level": "2-1"}}
        prompt = colleague_import.build_colleague_import_prompt(meta, self._persona())
        self.assertIn("评审会上抛问题", prompt)
        self.assertIn("2-1", prompt)

    def test_meta_none_no_crash(self):
        prompt = colleague_import.build_colleague_import_prompt(None, self._persona())
        self.assertIn("五层人格档案", prompt)

    def test_contains_field_guide_and_rules(self):
        prompt = colleague_import.build_colleague_import_prompt(None, self._persona())
        self.assertIn("decision_rules", prompt)
        self.assertIn("interaction_scripts", prompt)
        self.assertIn("corrections", prompt)
        self.assertIn("映射规则", prompt)
        self.assertIn("原文照抄", prompt)

    def test_empty_persona(self):
        prompt = colleague_import.build_colleague_import_prompt(None, "")
        self.assertIn("（空）", prompt)

    def test_source_note(self):
        prompt = colleague_import.build_colleague_import_prompt(None, self._persona(), source_note="同事张三")
        self.assertIn("同事张三", prompt)


if __name__ == "__main__":
    unittest.main()
