# -*- coding: utf-8 -*-
"""v4.0 Phase 4：style_core.retrieve.retrieve_section 行为契约（自 main 下沉）。

检索编排是 v3.4.5 事故同型（无超时挂起卡死 on_llm_request 钩子）的最后
一道防线，下沉后用 fake kb_manager 直接覆盖超时/扁平化/渲染/异常传播四类
行为，不再依赖宿主框架。
"""

import asyncio
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from style_core.retrieve import retrieve_section


class FakeKbManager:
    def __init__(self, result=None, delay=0.0, raises=None):
        self.result = result
        self.delay = delay
        self.raises = raises
        self.calls = []

    async def retrieve(self, query, *, kb_names, top_k_fusion, top_m_final):
        self.calls.append(
            {
                "query": query,
                "kb_names": list(kb_names),
                "top_k_fusion": top_k_fusion,
                "top_m_final": top_m_final,
            }
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        return self.result


def _run(coro):
    return asyncio.run(coro)


class TestRetrieveSection(unittest.TestCase):
    def test_passes_expected_args_and_renders(self):
        km = FakeKbManager(result={"results": [{"content": "你好呀"}, {"content": "在的"}]})
        out = _run(
            retrieve_section(
                km, kb_name="kb1", query="q", candidates=9, top_k=3, timeout=5.0
            )
        )
        self.assertEqual(
            km.calls,
            [{
                "query": "q",
                "kb_names": ["kb1"],
                "top_k_fusion": 9,
                "top_m_final": 3,
            }],
        )
        self.assertIn("你好呀", out)

    def test_empty_results_return_empty_string(self):
        km = FakeKbManager(result={"results": []})
        self.assertEqual(
            _run(retrieve_section(km, kb_name="k", query="q", candidates=5, top_k=3, timeout=5.0)),
            "",
        )

    def test_none_result_returns_empty(self):
        km = FakeKbManager(result=None)
        self.assertEqual(
            _run(retrieve_section(km, kb_name="k", query="q", candidates=5, top_k=3, timeout=5.0)),
            "",
        )

    def test_timeout_propagates_for_caller_fallback(self):
        km = FakeKbManager(result={"results": [{"content": "x"}]}, delay=5.0)
        with self.assertRaises(asyncio.TimeoutError):
            _run(
                retrieve_section(
                    km, kb_name="k", query="q", candidates=5, top_k=3, timeout=0.01
                )
            )

    def test_exception_propagates_not_swallowed(self):
        km = FakeKbManager(raises=RuntimeError("provider down"))
        with self.assertRaises(RuntimeError):
            _run(
                retrieve_section(
                    km, kb_name="k", query="q", candidates=5, top_k=3, timeout=5.0
                )
            )

    def test_content_rows_kept_unroled(self):
        # 与 flatten_content_rows 契约一致：渲染段不得出现伪造角色标记
        km = FakeKbManager(result={"results": [{"content": "甲"}, {"content": "乙"}]})
        out = _run(
            retrieve_section(km, kb_name="k", query="q", candidates=5, top_k=3, timeout=5.0)
        )
        self.assertNotIn("user:", out)


class TestMainDelegation(unittest.TestCase):
    def test_main_helper_delegates(self):
        import ast

        src = open(os.path.join(_ROOT, "main.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_kb_retrieve_section"
        )
        src = ast.dump(fn)
        self.assertIn("retrieve_section", src, "必须委托下沉实现")
        self.assertIn("kb_manager", src, "必须把 kb_manager 注入下沉实现（依赖注入）")
        # 旧内联编排不得回潮：函数体内不得再有 wait_for **调用**（只看调用节点，
        # 不误伤说明"wait_for 已下沉"的文档字符串）
        wait_calls = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and (
                (isinstance(n.func, ast.Attribute) and n.func.attr == "wait_for")
                or (isinstance(n.func, ast.Name) and n.func.id == "wait_for")
            )
        ]
        self.assertEqual(wait_calls, [], "wait_for 编排必须留在下游实现")


if __name__ == "__main__":
    unittest.main()
