# -*- coding: utf-8 -*-
"""v4.1.0 功能裁剪 + 发送链修复的回归钉子（AST 契约，不 import main）。

覆盖：
1. 已下线的 LLM 改写 / 故障切换 / 应声虫复读函数与模块确实消失；
2. 配置 schema 收敛为 6 组 135 键，route 表 19 条；
3. P0 修复：`_humanizer_llm_replied` 标记早于润色总闸（否则打字延迟/分段连坐失效）；
4. P0 修复：`<time_context>` 墙钟行自动跟随宿主 `datetime_system_prompt`；
5. 承诺簿整体移除（配置键 / 命令 / 模块）。
"""

import ast
import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_MAIN = os.path.join(_ROOT, "main.py")
_SCHEMA = os.path.join(_ROOT, "_conf_schema.json")
_WEB_API = os.path.join(_ROOT, "web_api.py")


def _parse(path):
    with open(path, encoding="utf-8") as f:
        return ast.parse(f.read(), filename=path)


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"main.py 中找不到函数 {name}")


class TestTrimmedFeatures(unittest.TestCase):
    def setUp(self):
        self.tree = _parse(_MAIN)

    def test_removed_functions_gone(self):
        names = {
            n.name
            for n in ast.walk(self.tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for gone in (
            "_llm_rewrite",
            "_rewrite_once",
            "_rewrite_state_line",
            "_parrot_consider",
            "_parrot_judge",
            "_parrot_takeover",
            "web_read_model",
            "list_models",
            "set_rewrite_model",
            "_capture_commitment",
            "_commitment_line",
            "commitment_list",
            "commitment_done",
            "commitment_drop",
        ):
            self.assertNotIn(gone, names, f"{gone} 应随 v4.1.0 功能裁剪移除")

    def test_removed_modules_gone(self):
        for mod in ("parrot", "prompt", "llm_budget"):
            path = os.path.join(_ROOT, "humanizer_core", mod + ".py")
            self.assertFalse(os.path.exists(path), f"humanizer_core/{mod}.py 应已移除")

    def test_schema_shape(self):
        with open(_SCHEMA, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(
            sorted(d.keys()),
            ["emotion", "humanize", "proactive", "style", "time", "typing"],
            "配置分组应为 6 组（parrot 组已移除）",
        )
        total = sum(len(v.get("items") or {}) for v in d.values())
        self.assertEqual(total, 130, f"配置键应为 130（含 v4.1.1 三个档位键），实际 {total}")
        hum = d["humanize"]["items"]
        self.assertEqual(set(hum), {"enabled", "remove_emoji", "min_length", "debug"})
        pro = d["proactive"]["items"]
        for gone in (
            "commitments_enable",
            "commitments_track_groups",
            "llm_confirm",
            "inject_in_chat",
            "remind_grace_days",
            "commitments_extract_model",
            "commitments_extract_timeout",
            "commitments_debug",
        ):
            self.assertNotIn(gone, pro, f"承诺簿键 {gone} 应已移除")

    def test_route_specs_trimmed(self):
        tree = _parse(_WEB_API)
        routes = None
        for node in tree.body:
            target = None
            if isinstance(node, ast.Assign) and node.targets:
                target = node.targets[0]
            elif isinstance(node, ast.AnnAssign):
                target = node.target
            if getattr(target, "id", "") == "ROUTE_SPECS":
                routes = ast.literal_eval(node.value)
        self.assertIsNotNone(routes, "web_api.py 缺少 ROUTE_SPECS")
        self.assertEqual(len(routes), 19, f"路由表应为 19 条，实际 {len(routes)}")
        attrs = {r[1] for r in routes}
        self.assertNotIn("set_rewrite_model", attrs, "改写模型端点应已移除")


class TestP0Fixes(unittest.TestCase):
    def setUp(self):
        self.tree = _parse(_MAIN)

    def test_mark_before_enabled_gate(self):
        """P0①：人格聊天标记必须早于润色总闸，否则打字延迟/分段被连坐关闭。"""
        fn = _find_func(self.tree, "humanize_response")
        mark_lineno = None
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "set_extra"
            ):
                consts = [a.value for a in node.args if isinstance(a, ast.Constant)]
                if "_humanizer_llm_replied" in consts:
                    mark_lineno = node.lineno
                    break
        gate_lineno = None
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
                gate_lineno = node.lineno
                break
        self.assertIsNotNone(mark_lineno, "humanize_response 缺 _humanizer_llm_replied 标记")
        self.assertIsNotNone(gate_lineno, "humanize_response 缺 enabled 开关判断")
        self.assertLess(mark_lineno, gate_lineno, "标记必须早于 enabled 判断")

    def test_wall_clock_follows_host(self):
        """P0④：墙钟行必须检测宿主 datetime_system_prompt 后自动跳过。"""
        fn = _find_func(self.tree, "_time_context_block")
        self.assertIn("_framework_injects_datetime", ast.unparse(fn))
        helper = _find_func(self.tree, "_framework_injects_datetime")
        self.assertIn("datetime_system_prompt", ast.unparse(helper))


if __name__ == "__main__":
    unittest.main()
