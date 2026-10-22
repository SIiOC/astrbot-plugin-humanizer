# -*- coding: utf-8 -*-
"""v3.5.2 真人感规则集接线的源码契约测试（AST，不 import main.py）。

钉六条接线契约（main.py + _conf_schema.json + web_api.py）：
1. 注入点在 on_llm_request 内、style.enabled 早退之前（独立通道，
   与发送纪律/情绪同位），且在情绪注入之后；
2. QC 点在 humanize_response 内、罩住两条收尾路径（在 _llm_rewrite
   与机械清洗之后）；
3. 改写链贯通：_llm_rewrite 与 _rewrite_once 都接收 extra_instruction
   并传递，_rewrite_once 用 prompt_text 组装（两分支生效）；
4. 命令族六个全部注册（rules_list/add/del/on/off/reload，ADMIN）；
5. 规则库加载与预置迁移在 _init_time_stores（load_rules +
   migrate_builtins + save_rules），stats 有 qc_hits/qc_fixed；
6. schema 有 humaneness 组（qc_enable 默认 False、rules_enable 默认
   True），web_api 注册 rules 两端点。

⚠️ AST 断言"谁先谁后"必须用 node.lineno（ast.walk 的 BFS 序号 ≠
源码顺序——v3.5.1 两起假失败的教训）。
"""

import ast
import json
import os
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN = os.path.join(_ROOT, "main.py")
_SCHEMA = os.path.join(_ROOT, "_conf_schema.json")
_WEB_API = os.path.join(_ROOT, "web_api.py")


def _call_lineno(func, attr, as_attr=True):
    """函数内第一个 `xxx.attr(...)`（as_attr）或 `attr(...)` 调用的行号。"""
    for n in ast.walk(func):
        if isinstance(n, ast.Call):
            f = n.func
            if as_attr and isinstance(f, ast.Attribute) and f.attr == attr:
                return n.lineno
            if not as_attr and isinstance(f, ast.Name) and f.id == attr:
                return n.lineno
    raise AssertionError(f"{getattr(func, 'name', '?')} 内找不到调用 {attr}")


def _command_names(tree):
    """收集所有 @filter.command("xxx") 的名字。"""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "command"
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                ):
                    names.add(dec.args[0].value)
    return names


class TestInjectPoint(unittest.TestCase):
    """契约1：注入型规则在 style 早退之前、情绪注入之后。"""

    @classmethod
    def setUpClass(cls):
        cls.func = _find_func(_parse(), "on_llm_request")

    def _gate_lineno(self):
        for n in ast.walk(self.func):
            if (
                isinstance(n, ast.If)
                and "_cfg" in ast.dump(n.test)
                and "enabled" in ast.dump(n.test)
                and any(isinstance(s, ast.Return) for s in ast.walk(n))
            ):
                return n.lineno
        raise AssertionError("on_llm_request 必须保留 style.enabled 早退")

    def test_rules_injected_before_style_gate(self):
        rules_lineno = _call_lineno(self.func, "_rules_inject_text")
        self.assertLess(rules_lineno, self._gate_lineno(), "规则注入必须在 enabled 早退之前")

    def test_rules_after_emotion(self):
        rules_lineno = _call_lineno(self.func, "_rules_inject_text")
        emo_lineno = _call_lineno(self.func, "_emotion_directive_for")
        self.assertGreater(rules_lineno, emo_lineno, "规则注入应与情绪同区（情绪之后）")


class TestQcPoint(unittest.TestCase):
    """契约2：QC 在 humanize_response 内、罩住两条收尾路径。"""

    @classmethod
    def setUpClass(cls):
        cls.func = _find_func(_parse(), "humanize_response")

    def test_qc_called_once(self):
        calls = [
            n for n in ast.walk(self.func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_qc_rules_pass"
        ]
        # v4.1.1：QC 改为只读观测并与润色开关解耦——关闭分支与清洗后各一处，
        # 两条互斥路径各自只调用一次（不是同一路径重复）。
        self.assertEqual(len(calls), 2, "QC 应在两条互斥路径各调用一次")

    def test_qc_after_cleanup(self):
        qc_lineno = _call_lineno(self.func, "_qc_rules_pass")
        clean_lineno = _call_lineno(self.func, "humanize_text_detailed", as_attr=False)
        self.assertGreater(qc_lineno, clean_lineno, "QC 必须在机械清洗路径之后")




class TestCommands(unittest.TestCase):
    """契约4：六个命令全部注册。"""

    def test_all_six_registered(self):
        names = _command_names(_parse())
        for cmd in ("rules_list", "rules_add", "rules_del", "rules_on", "rules_off", "rules_reload"):
            self.assertIn(cmd, names, f"缺少命令 /{cmd}")


class TestLoadAndStats(unittest.TestCase):
    """契约5：规则库加载迁移 + stats 键。"""

    def test_init_stores_loads_and_migrates(self):
        func = _find_func(_parse(), "_init_time_stores")
        src = ast.dump(func)
        for token in ("load_rules", "migrate_builtins", "save_rules", "_rules_path"):
            self.assertIn(token, src, f"_init_time_stores 缺 {token}")

    def test_stats_keys(self):
        with open(_MAIN, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"qc_hits"', src)
        # v4.1.0：LLM 改写链移除，qc_fixed 计数随之下线。
        self.assertNotIn('"qc_fixed"', src)


class TestSchemaAndWebApi(unittest.TestCase):
    """契约6：schema 组 + web_api 端点。"""

    def test_schema_group(self):
        with open(_SCHEMA, encoding="utf-8") as f:
            d = json.load(f)
        # v3.8.1 分组重构：真人感规则开关并入 style 组（原 humaneness 组已删）
        g = d.get("style")
        self.assertIsInstance(g, dict, "schema 缺 style 组")
        items = g.get("items", {})
        self.assertTrue(items.get("rules_enable", {}).get("default") is True)
        self.assertTrue(items.get("qc_enable", {}).get("default") is False)
        # ⚠️ 另起一行规范
        for it in items.values():
            hint = it.get("hint", "")
            for i, line in enumerate(hint.split("\n")):
                if "⚠️" in line:
                    self.assertTrue(i > 0 and line.startswith("⚠️"), f"hint ⚠️ 未另起一行: {it.get('description')}")

    def test_web_api_routes(self):
        with open(_WEB_API, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('("rules", "get_rules"', src)
        self.assertIn('("rules/save", "post_rules"', src)


if __name__ == "__main__":
    unittest.main()
