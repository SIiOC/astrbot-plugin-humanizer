# -*- coding: utf-8 -*-
"""辅助 LLM 站点 provider 解析的源码接线契约（v4.0.1 回归钉）。

缺陷（2026-09-15 运行日志实证）：AstrBot v4.28 把框架
`Context.llm_generate` 的 `chat_provider_id` 改为**必填** keyword-only。
插件 `invoke_llm` 在 `provider_id=None` 时省略该键（旧"跟随会话"语义），
于是当 `parse_configured_target` 对裸模型名返回 `(None, model)` 时——
`_call_llm_for_timeline`（life_extract_model）等辅助 LLM 站点——批量模型名为裸名时
调用必然 `TypeError: missing 1 required keyword-only argument: 'chat_provider_id'`，
被静默 except 吞掉，功能静默失效。

修复＝这些站点在转发 `configured_provider` 前必须 `or` 回退
`_resolve_aux_provider_id(...)` 解析出真实 provider。

契约（main.py，AST 钉死，不 import main.py——本机可能无 astrbot 包）：
1. 任何 `invoke_llm(...)` 调用都不得把 `configured_provider` 以**裸 Name**
   传给 `provider_id=`——必须是 `or` 回退（BoolOp）等已解析形态。
2. `_call_llm_for_timeline` / `_call_llm_for_profile` 必须引用
   `_resolve_aux_provider_id`（保留回退，不许删）。
4. `_resolve_aux_provider_id` 必须存在，且同时含
   `get_current_chat_provider_id` 与 `get_all_providers` 两级解析。
"""

import ast
import os
import sys as _sys
import unittest

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import find_func as _find_func, parse_main as _parse


def _iter_invoke_llm_calls(tree):
    """产出所有 ``invoke_llm(...)`` 的 ast.Call 节点。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "invoke_llm":
                yield node


def _kwarg(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _dotted(node) -> str:
    """把 `self.context.llm_generate` 这类属性链摊平成点分字符串。"""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


class TestAuxProviderWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _parse()

    def test_no_bare_configured_provider_forwarded(self):
        """回归钉：invoke_llm 的 provider_id 绝不能是裸 `configured_provider`。

        该形态在 v4.28 下必然省略必填键 → TypeError 静默失败。所有此类站点
        必须改为 `configured_provider or await self._resolve_aux_provider_id(...)`。
        """
        offenders = []
        for call in _iter_invoke_llm_calls(self.tree):
            value = _kwarg(call, "provider_id")
            if isinstance(value, ast.Name) and value.id == "configured_provider":
                offenders.append(getattr(call, "lineno", "?"))
        self.assertEqual(
            offenders,
            [],
            f"main.py 第 {offenders} 行：provider_id=configured_provider 裸传，"
            "v4.28 下会 TypeError；须加 `or` 回退解析 provider。",
        )

    def test_every_llm_generate_site_passes_provider_id(self):
        """每个 `self.context.llm_generate` 调用点都必须显式传 provider_id。"""
        missing = []
        for call in _iter_invoke_llm_calls(self.tree):
            if not call.args:
                continue
            if _dotted(call.args[0]) != "self.context.llm_generate":
                continue
            if _kwarg(call, "provider_id") is None:
                missing.append(getattr(call, "lineno", "?"))
        self.assertEqual(
            missing, [], f"main.py 第 {missing} 行的 llm_generate 调用缺 provider_id。"
        )

    def test_fixed_sites_reference_resolver(self):
        """v4.28 必填键防护：辅助 LLM 站点必须保留 `_resolve_aux_provider_id` 回退。

        v4.1.0 移除应声虫复读后，仅承诺簿复核站点仍在。
        """
        for fname in ("_call_llm_for_timeline", "_call_llm_for_profile"):
            func = _find_func(self.tree, fname)
            names = {
                n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", "")
                for n in ast.walk(func)
                if isinstance(n, (ast.Attribute, ast.Name))
            }
            self.assertIn(
                "_resolve_aux_provider_id", names,
                f"{fname} 缺少 _resolve_aux_provider_id 回退（v4.28 必填键防护）",
            )


    def test_resolver_has_two_tier_fallback(self):
        """_resolve_aux_provider_id 必须含会话级 + 首个 provider 两级解析。"""
        func = _find_func(self.tree, "_resolve_aux_provider_id")
        names = {
            n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", "")
            for n in ast.walk(func)
            if isinstance(n, (ast.Attribute, ast.Name))
        }
        self.assertIn("get_current_chat_provider_id", names)
        self.assertIn("get_all_providers", names)


if __name__ == "__main__":
    unittest.main()
