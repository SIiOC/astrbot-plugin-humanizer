# -*- coding: utf-8 -*-
"""v4.0 Phase 4/8：检索规划纯函数（humanizer_core.retrieval_plan）。

钉死从 main._retrieve_examples 下沉的参数派生语义：top_k 夹逼、
rerank 候选池、检索超时校验、查询摘要稳定性。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import retrieval_plan as rp


class TestClampTopK(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(rp.clamp_top_k(3), 3)

    def test_upper_bound(self):
        self.assertEqual(rp.clamp_top_k(99), 5)

    def test_lower_bound(self):
        self.assertEqual(rp.clamp_top_k(0), 1)
        self.assertEqual(rp.clamp_top_k(-4), 1)

    def test_bad_falls_back_then_clamps(self):
        self.assertEqual(rp.clamp_top_k("x"), 3)
        self.assertEqual(rp.clamp_top_k(None), 3)


class TestResolveCandidates(unittest.TestCase):
    def test_non_rerank_equals_topk(self):
        self.assertEqual(rp.resolve_candidates(False, 3, 20), 3)

    def test_rerank_uses_configured(self):
        self.assertEqual(rp.resolve_candidates(True, 3, 12), 12)

    def test_rerank_caps_at_30(self):
        self.assertEqual(rp.resolve_candidates(True, 3, 99), 30)

    def test_rerank_floored_at_topk(self):
        self.assertEqual(rp.resolve_candidates(True, 8, 4), 8)

    def test_rerank_zero_or_bad_defaults_12(self):
        self.assertEqual(rp.resolve_candidates(True, 3, 0), 12)
        self.assertEqual(rp.resolve_candidates(True, 3, None), 12)
        self.assertEqual(rp.resolve_candidates(True, 3, "x"), 12)


class TestRetrievalTimeout(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(rp.resolve_retrieval_timeout(5.0), 5.0)
        self.assertEqual(rp.resolve_retrieval_timeout("3.5"), 3.5)

    def test_zero_negative_bad_default_5(self):
        self.assertEqual(rp.resolve_retrieval_timeout(0), 5.0)
        self.assertEqual(rp.resolve_retrieval_timeout(-1), 5.0)
        self.assertEqual(rp.resolve_retrieval_timeout(None), 5.0)
        self.assertEqual(rp.resolve_retrieval_timeout("x"), 5.0)


class TestQueryDigest(unittest.TestCase):
    def test_stable_and_whitespace_folded(self):
        self.assertEqual(rp.query_digest("a  b   c"), rp.query_digest("a b c"))

    def test_length_24(self):
        self.assertEqual(len(rp.query_digest("hello")), 24)

    def test_distinct_queries_distinct(self):
        self.assertNotEqual(rp.query_digest("今天天气"), rp.query_digest("明天天气"))

    def test_empty_ok(self):
        self.assertEqual(len(rp.query_digest("")), 24)


if __name__ == "__main__":
    unittest.main()
