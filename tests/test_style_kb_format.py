# -*- coding: utf-8 -*-
"""v4.0 Phase 4：style_core.retrieve KB 纯函数下沉的契约测试。

三件套（sanitize_kb_name / build_kb_desc / flatten_content_rows）自 main.py
下沉，要求**逐字等价**；同时钉死 flatten_content_rows（无角色 content 行）
与 flatten_results（交替 user/assistant 行）两种输出形态刻意不同、各自稳定
——历史上 v2.2.2 曾因给分数排序结果贴假角色导致注入段误导模型，禁止合并。
"""

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from style_core.retrieve import (
    build_kb_desc,
    flatten_content_rows,
    flatten_results,
    sanitize_kb_name,
)


class TestSanitizeKbName(unittest.TestCase):
    def test_prefix_and_sanitization(self):
        # 与 main._kb_name 旧实现逐字一致
        self.assertEqual(sanitize_kb_name("日常口语风"), "human_style_日常口语风")
        self.assertEqual(sanitize_kb_name("a b/c.d"), "human_style_a_b_c_d")
        self.assertEqual(sanitize_kb_name(""), "human_style_")
        self.assertEqual(sanitize_kb_name("ok123"), "human_style_ok123")


class TestBuildKbDesc(unittest.TestCase):
    def test_counts_and_shape(self):
        rows = [
            {"source": "builtin", "content": "x"},
            {"source": "user", "content": "y"},
            {"source": "user", "content": "z"},
        ]
        desc = build_kb_desc("我的风格", rows)
        self.assertIn("风格「我的风格」", desc)
        self.assertIn("内置 1 + 用户 2 = 3 条", desc)
        self.assertIn("请勿手动删除", desc)

    def test_empty_rows(self):
        desc = build_kb_desc("空", [])
        self.assertIn("内置 0 + 用户 0 = 0 条", desc)


class TestFlattenContentRows(unittest.TestCase):
    def test_dict_results_no_role(self):
        rows = flatten_content_rows(
            {"results": [{"content": " 甲 "}, {"chunk": "乙"}, {"text": "丙"}]}
        )
        self.assertEqual(rows, [{"content": "甲"}, {"content": "乙"}, {"content": "丙"}])
        for r in rows:
            self.assertNotIn("role", r, "content 行禁止携带 role 标签（v2.2.2 教训）")

    def test_accepts_plain_list(self):
        self.assertEqual(
            flatten_content_rows([{"content": "a"}]), [{"content": "a"}]
        )

    def test_garbage_inputs_empty(self):
        for bad in (None, "str", 42, {}, {"results": "no"}, [1, "x", None], [{"nope": 1}]):
            self.assertEqual(flatten_content_rows(bad), [], f"输入 {bad!r} 应得空列表")


class TestRoleFormsDivergeIntentionally(unittest.TestCase):
    """flatten_content_rows 与 flatten_results 输出形态刻意不同，禁止互相替换。"""

    def test_role_alternation_kept_on_legacy_form(self):
        legacy = flatten_results({"results": [{"content": "a"}, {"content": "b"}]})
        self.assertEqual(legacy[0]["role"], "user")
        self.assertEqual(legacy[1]["role"], "assistant")
        content = flatten_content_rows({"results": [{"content": "a"}, {"content": "b"}]})
        self.assertTrue(all("role" not in r for r in content))
        self.assertNotEqual(
            [tuple(sorted(r)) for r in legacy],
            [tuple(sorted(r)) for r in content],
            "两形态键集合必须保持差异（角色 vs 无角色）",
        )


class TestMainDelegationWiring(unittest.TestCase):
    """main.py 三方法必须已改为委托（防旧实现回潮造成双事实源）。"""

    def setUp(self):
        import ast

        self.ast = ast
        src = open(os.path.join(_ROOT, "main.py"), encoding="utf-8").read()
        self.tree = ast.parse(src)

    def _func(self, name):
        for n in self.ast.walk(self.tree):
            if isinstance(n, (self.ast.FunctionDef, self.ast.AsyncFunctionDef)) and n.name == name:
                return n
        self.fail(f"main.py 缺 {name}")

    def test_bodies_delegate(self):
        for fname, helper in (
            ("_kb_name", "sanitize_kb_name"),
            ("_kb_desc", "build_kb_desc"),
            ("_flatten_kb_results", "flatten_content_rows"),
        ):
            src = self.ast.dump(self._func(fname))
            self.assertIn(helper, src, f"{fname} 必须委托 {helper}")

    def test_single_return_statement(self):
        """委托体必须是单一 return（不允许残留本地实现）。"""
        for fname in ("_kb_name", "_flatten_kb_results"):
            body = [
                n for n in self._func(fname).body
                if not (isinstance(n, self.ast.Expr) and isinstance(n.value, self.ast.Constant))
            ]
            self.assertEqual(len(body), 1, f"{fname} 委托体应只有一条语句")
            self.assertIsInstance(body[0], self.ast.Return)


if __name__ == "__main__":
    unittest.main()
