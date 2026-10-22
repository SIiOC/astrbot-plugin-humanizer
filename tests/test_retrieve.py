# -*- coding: utf-8 -*-
"""检索结果格式化/兜底测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_core import retrieve


class TestFlattenResults(unittest.TestCase):
    def test_framework_dict(self):
        raw = {"results": [{"content": "a"}, {"content": "b"}]}
        rows = retrieve.flatten_results(raw)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["role"], "user")
        self.assertEqual(rows[1]["role"], "assistant")

    def test_plain_list(self):
        raw = [{"content": "a"}, {"content": "b"}]
        self.assertEqual(len(retrieve.flatten_results(raw)), 2)

    def test_none_and_garbage(self):
        self.assertEqual(retrieve.flatten_results(None), [])
        self.assertEqual(retrieve.flatten_results("str"), [])
        self.assertEqual(retrieve.flatten_results(42), [])
        self.assertEqual(retrieve.flatten_results({"no_results": 1}), [])
        self.assertEqual(retrieve.flatten_results([1, 2, "x"]), [])

    def test_chunk_and_text_keys(self):
        raw = {"results": [{"chunk": "chunk内容"}, {"text": "text内容"}]}
        rows = retrieve.flatten_results(raw)
        self.assertEqual(rows[0]["content"], "chunk内容")
        self.assertEqual(rows[1]["content"], "text内容")

    def test_cap_at_max(self):
        raw = {"results": [{"content": f"c{i}"} for i in range(100)]}
        rows = retrieve.flatten_results(raw)
        self.assertLessEqual(len(rows), retrieve.MAX_RESULTS)

    def test_strip_content(self):
        rows = retrieve.flatten_results({"results": [{"content": "  有空白  "}]})
        self.assertEqual(rows[0]["content"], "有空白")


class TestToExampleRows(unittest.TestCase):
    def test_truncate_to_top_k(self):
        rows = [{"role": "user", "content": f"u{i}"} for i in range(10)]
        out = retrieve.to_example_rows(rows, 3)
        self.assertEqual(len(out), 6)  # 3 对 = 6 行

    def test_empty(self):
        self.assertEqual(retrieve.to_example_rows([], 3), [])

    def test_fewer_than_k(self):
        rows = [{"role": "user", "content": "u1"}]
        out = retrieve.to_example_rows(rows, 3)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
