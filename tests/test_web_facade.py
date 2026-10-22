# -*- coding: utf-8 -*-
"""v4.0 Phase 5：Web 控制台只读 facade 契约。

控制台状态/统计两页此前直接读取插件私有成员（_h/_p/_cfg/_life/
_next_trigger_ts/_stats）。本契约钉死：
1. main.py 提供 web_status()/web_stats() 两个公开只读出口；
2. web_api.get_status/get_stats 只经 facade，不再直读那些私有成员；
3. facade 不写配置、统计返回副本（读写隔离）。
"""

import ast
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _parse(name):
    with open(os.path.join(_ROOT, name), encoding="utf-8") as f:
        return ast.parse(f.read())


def _func(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} 未找到")


class TestMainFacade(unittest.TestCase):
    def test_facade_methods_exist(self):
        tree = _parse("main.py")
        names = {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("web_stats", names)
        self.assertIn("web_proactive_view", names)

    def test_web_stats_returns_copy(self):
        # dict(self._stats) 形态：返回副本而非原对象
        fn = _func(_parse("main.py"), "web_stats")
        calls = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "dict"
        ]
        self.assertTrue(calls, "web_stats 必须返回 dict(...) 副本")


class TestWebApiUsesFacade(unittest.TestCase):
    PRIVATE_ATTRS = (("_h", False), ("_p", False), ("_cfg", False), ("_life", False))
    PRIVATE_NAMES = ("_next_trigger_ts", "_stats")

    def _accesses(self, fn):
        """收集对私有成员的访问（属性节点 + 私有下划线函数调用），
        只看 AST 节点、不扫 docstring 字面量（否则说明性文案会误伤）。"""
        attrs = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute):
                attrs.add(n.attr)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                attrs.add(n.func.attr)
        return attrs

    def test_get_status_uses_facade_only(self):
        fn = _func(_parse("web_api.py"), "get_status")
        self.assertIn("web_status", ast.dump(fn))
        touched = self._accesses(fn)
        for priv in ("_h", "_p", "_cfg", "_life", "_next_trigger_ts"):
            self.assertNotIn(priv, touched, f"get_status 不应再访问 {priv}")

    def test_get_stats_uses_facade_only(self):
        fn = _func(_parse("web_api.py"), "get_stats")
        self.assertIn("web_stats", ast.dump(fn))
        self.assertNotIn("_stats", self._accesses(fn), "get_stats 不应再访问 _stats")

    def test_no_private_config_or_state_access_left(self):
        """web_api 全文件不得再访问配置/状态/路径类私有成员（v4.0 Phase 5 目标）。"""
        tree = _parse("web_api.py")
        accessed = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute):
                accessed.add(n.attr)
        forbidden = (
            "_h", "_p", "_cfg", "_life", "_p_int", "_p_f",
            "_set_cfg", "_set_h", "_building", "_bump_stats",
            "_inject_schema_options", "_effective_active_style",
            "_effective_corpus_rows", "_next_trigger_ts",
            "_proactive_unanswered", "_last_user_ts", "_stats",
            "_styles_dir", "_corpora_dir", "_user_corpus_path",
            "_model_cache", "_build_profile", "_rules_list", "_rules_apply",
            "_embedding_provider_id",
        )
        left = sorted(set(forbidden) & accessed)
        self.assertEqual(left, [], f"web_api 仍访问私有成员: {left}")

    def test_only_pinned_private_methods_remain(self):
        """仅剩两个被 test_colleague_flow 用 inspect.getsource 钉死的私有方法：
        _load_colleague_input（async 元组契约）与 _call_llm_for_profile
        （返回已解析 dict 契约）。二者是刻意保留的公开化例外，不得再增。"""
        tree = _parse("web_api.py")
        accessed = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr.startswith("_") and not n.attr.startswith("__"):
                accessed.add(n.attr)
        # 过滤掉本类自身的方法/局部变量（非 plugin.xxx 形态）
        plugin_privates = set()
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Attribute)
                and n.attr.startswith("_")
                and isinstance(n.value, ast.Attribute)
                and n.value.attr == "plugin"
            ):
                plugin_privates.add(n.attr)
        allowed = {"_load_colleague_input", "_call_llm_for_profile"}
        self.assertEqual(
            plugin_privates,
            allowed,
            f"plugin 私有方法访问应仅剩 {allowed}，实际 {sorted(plugin_privates)}",
        )

    def test_facade_entry_points_used(self):
        tree = _parse("web_api.py")
        called = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
        for facade in (
            "web_status", "web_stats", "web_styles_dir", "web_corpora_dir",
            "web_user_corpus_path", "web_active_style", "web_effective_corpus_rows",
            "web_building", "web_bump_stat", "web_refresh_schema_options",
            "web_set_active_style", "web_proactive_view", "web_model_cache",
            "web_provider_id", "web_rules_list", "web_rules_apply", "web_build_profile",
        ):
            self.assertIn(facade, called, f"web_api 应使用 {facade}()")
        # v4.1.0：深度改写与 models/set-rewrite 端点移除后，web_read_model /
        # web_set_rewrite_model / web_rewrite_model 三个 facade 一并下线。


if __name__ == "__main__":
    unittest.main()
