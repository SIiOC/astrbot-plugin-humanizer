# -*- coding: utf-8 -*-
"""提炼/融合提示词构造与 LLM 输出 JSON 解析测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_core import extract_prompt


class TestBuildExtractPrompt(unittest.TestCase):
    def test_contains_sample_sentences(self):
        sents = ["你好呀", "吃了吗", "哈哈哈"]
        prompt = extract_prompt.build_extract_prompt(sents)
        for s in sents:
            self.assertIn(s, prompt)

    def test_contains_field_guide(self):
        prompt = extract_prompt.build_extract_prompt(["你好"])
        self.assertIn("catchphrases", prompt)
        self.assertIn("sentence_patterns", prompt)
        self.assertIn("examples", prompt)

    def test_contains_v230_fields(self):
        """v2.3.0：_FIELD_GUIDE 含决策/人际/纠错字段。"""
        prompt = extract_prompt.build_extract_prompt(["你好"])
        self.assertIn("decision_rules", prompt)
        self.assertIn("interaction_scripts", prompt)
        self.assertIn("corrections", prompt)

    def test_source_note(self):
        prompt = extract_prompt.build_extract_prompt(["你好"], source_note="LCCC")
        self.assertIn("LCCC", prompt)

    def test_numbered_lines(self):
        sents = ["a", "b", "c"]
        prompt = extract_prompt.build_extract_prompt(sents)
        self.assertIn("1. a", prompt)
        self.assertIn("3. c", prompt)

    def test_empty_sents(self):
        prompt = extract_prompt.build_extract_prompt([])
        self.assertIn("----------", prompt)


class TestBuildRefinePrompt(unittest.TestCase):
    def test_contains_old_profile_json(self):
        old = {"name": "旧风", "catchphrases": ["旧口癖"], "avoid": ["书面语"]}
        prompt = extract_prompt.build_refine_prompt(old, ["新句子"])
        self.assertIn("旧风", prompt)
        self.assertIn("旧口癖", prompt)
        self.assertIn("新句子", prompt)

    def test_contains_preservation_rules(self):
        prompt = extract_prompt.build_refine_prompt({"name": "风"}, ["句"])
        self.assertIn("保留旧档案", prompt)
        self.assertIn("name 保持不变", prompt)

    def test_no_markdown_codeblock_rule(self):
        prompt = extract_prompt.build_refine_prompt({"name": "风"}, ["句"])
        self.assertIn("不要用 markdown 代码块", prompt)


class TestParseProfileJson(unittest.TestCase):
    def test_plain_json(self):
        data = extract_prompt.parse_profile_json('{"name": "风", "catchphrases": ["嗯"]}')
        self.assertEqual(data["name"], "风")
        self.assertEqual(data["catchphrases"], ["嗯"])

    def test_markdown_fenced(self):
        text = '```json\n{"name": "风"}\n```'
        data = extract_prompt.parse_profile_json(text)
        self.assertEqual(data["name"], "风")

    def test_text_surrounding(self):
        text = '分析完毕。\n{"name": "风", "persona": "好"} 就是这样。'
        data = extract_prompt.parse_profile_json(text)
        self.assertEqual(data["persona"], "好")

    def test_invalid(self):
        self.assertIsNone(extract_prompt.parse_profile_json(""))
        self.assertIsNone(extract_prompt.parse_profile_json("not json"))
        self.assertIsNone(extract_prompt.parse_profile_json("[1,2,3]"))
        self.assertIsNone(extract_prompt.parse_profile_json(None))

    def test_no_brace(self):
        self.assertIsNone(extract_prompt.parse_profile_json("没有花括号"))


if __name__ == "__main__":
    unittest.main()
