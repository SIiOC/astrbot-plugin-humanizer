# -*- coding: utf-8 -*-
"""v4.0 Phase 4：kb_state.iter_all_documents 分页行为契约（自 main 下沉后钉死）。

容错语义是 _kb_sync_job 判定「已有分组文档=已同步」的数据基础，任何
终止条件变更都必须先改本文件的预期。
"""

import asyncio
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from humanizer_core.kb_state import iter_all_documents


class FakeKb:
    def __init__(self, pages, total=None, count_raises=False, fail_after=None):
        self._pages = pages  # list[list[str]]
        self._total = total
        self._count_raises = count_raises
        self._fail_after = fail_after  # 第 N 次 list 请求后抛异常
        self.calls = []  # (offset, limit)

    async def count_documents(self):
        if self._count_raises:
            raise RuntimeError("count boom")
        if self._total is not None:
            return self._total
        return sum(len(p) for p in self._pages)

    async def list_documents(self, offset=0, limit=100):
        self.calls.append((offset, limit))
        if self._fail_after is not None and len(self.calls) > self._fail_after:
            raise RuntimeError("page boom")
        page = self._pages[offset // limit] if offset // limit < len(self._pages) else []
        return page


class TestIterAllDocuments(unittest.TestCase):
    def test_multi_page_aggregation(self):
        kb = FakeKb([["a", "b", "c"], ["d", "e", "f"], ["g"]], total=7)
        docs = asyncio.run(iter_all_documents(kb, page_size=3))
        self.assertEqual(docs, ["a", "b", "c", "d", "e", "f", "g"])
        self.assertEqual(kb.calls, [(0, 3), (3, 3), (6, 3)])

    def test_stops_at_total_before_short_page(self):
        # 每页都满页长，但 total 先到 → 两页即停（不再多发第三次）
        kb = FakeKb([["a", "b"], ["c", "d"], ["e", "f"]], total=4)
        docs = asyncio.run(iter_all_documents(kb, page_size=2))
        self.assertEqual(docs, ["a", "b", "c", "d"])
        self.assertEqual(len(kb.calls), 2)

    def test_no_list_documents_returns_empty(self):
        class Bare:
            pass

        self.assertEqual(asyncio.run(iter_all_documents(Bare())), [])

    def test_count_failure_falls_back_to_page_length(self):
        kb = FakeKb([["a"], []], count_raises=True)
        docs = asyncio.run(iter_all_documents(kb, page_size=5))
        # total 未知：短页(<5)即停 → 第一页后 offset=1，第二页空 → 停
        self.assertEqual(docs, ["a"])

    def test_page_failure_keeps_accumulated(self):
        kb = FakeKb([["a", "b"], ["c", "d"]], total=10, fail_after=2)
        docs = asyncio.run(iter_all_documents(kb, page_size=2))
        # 第 2 页正常、第 3 页请求抛异常 → 保留已累计的 4 条
        self.assertEqual(docs, ["a", "b", "c", "d"])

    def test_empty_first_page(self):
        kb = FakeKb([[]])
        self.assertEqual(asyncio.run(iter_all_documents(kb, page_size=10)), [])


if __name__ == "__main__":
    unittest.main()
