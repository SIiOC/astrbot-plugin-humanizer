# -*- coding: utf-8 -*-
"""v3.4.7 启动期 embedding provider 时序竞态修复的源码契约测试。

回归背景（2026-09-03 日志 15:50:52 / 23:29:47 两例）：embedding provider
异步实例化必然晚于插件 initialize 的启动预同步，预同步探测拿空即打 WARN
「未配置 embedding provider，检索功能禁用」；自愈重试的成功判断又停留在
v3.4.6 建库后台化前的返回值语义，连打第二条 WARN「检索索引重试未成功」，
而检索实际已后台就绪。

契约（main.py）：
- `__init__` 初始化 `self._framework_loaded = False`。
- `_ensure_kb` provider 空分支含 `if not self._framework_loaded:` 守卫：
  守卫体内 debug 静默返回 None、**不得**写负缓存；守卫外（运行期）保留
  WARN + `_kb_ready[...] = False` 负缓存。
- `_on_astrbot_loaded`：置 `self._framework_loaded = True`；不再扫描
  负缓存（`stale`）决定是否重试（启动期不写负缓存后该前提失效）；
  `_resync` 受理后台同步（`kb_name in self._kb_syncing`）即视为成功。

不 import main.py（本机无 astrbot 包），用 ast 直接钉源码结构。
"""

import ast
import os
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN = os.path.join(_ROOT, "main.py")
_SERVICE = os.path.join(_ROOT, "services", "kb_service.py")


def _parse_service():
    with open(_SERVICE, encoding="utf-8") as f:
        return ast.parse(f.read())


def _kb_ready_false_writes(node):
    """收集 node 子树内 `self._kb_ready[...] = False` 赋值（下标任意表达式）。"""
    hits = []
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Assign)
            and isinstance(sub.value, ast.Constant)
            and sub.value.value is False
        ):
            for t in sub.targets:
                if (
                    isinstance(t, ast.Subscript)
                    and isinstance(t.value, ast.Attribute)
                    and t.value.attr in ("_kb_ready", "ready")
                ):
                    hits.append(t)
    return hits


def _writes_kb_ready_false(node):
    """兼容旧断言：收集 `self._kb_ready['<字面量>'] = False` 的下标常量。"""
    keys = []
    for t in _kb_ready_false_writes(node):
        sl = t.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            keys.append(sl.value)
    return keys


class TestFrameworkLoadedFlag(unittest.TestCase):
    def test_init_defaults_false(self):
        tree = _parse()
        init = _find_func(tree, "__init__")
        found = any(
            isinstance(sub, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "_framework_loaded"
                for t in sub.targets
            )
            and isinstance(sub.value, ast.Constant)
            and sub.value.value is False
            for sub in ast.walk(init)
        )
        self.assertTrue(found, "__init__ 必须初始化 self._framework_loaded = False")

    def test_loaded_hook_sets_true(self):
        tree = _parse()
        hook = _find_func(tree, "_on_astrbot_loaded")
        found = any(
            isinstance(sub, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "_framework_loaded"
                for t in sub.targets
            )
            and isinstance(sub.value, ast.Constant)
            and sub.value.value is True
            for sub in ast.walk(hook)
        )
        self.assertTrue(found, "_on_astrbot_loaded 必须置 self._framework_loaded = True")


class TestEnsureKbStartupSilence(unittest.TestCase):
    """启动期（_framework_loaded=False）拿空 provider：静默返回，不写负缓存。"""

    @classmethod
    def setUpClass(cls):
        cls.branch = None
        func = _find_func(_parse_service(), "ensure")
        for sub in ast.walk(func):
            if (
                isinstance(sub, ast.If)
                and isinstance(sub.test, ast.UnaryOp)
                and isinstance(sub.test.op, ast.Not)
                and isinstance(sub.test.operand, ast.Attribute)
                and sub.test.operand.attr in ("_framework_loaded", "framework_loaded")
            ):
                cls.branch = sub
                break
        if cls.branch is None:
            raise AssertionError("_ensure_kb 缺少 `if not self._framework_loaded:` 守卫")

    def test_startup_branch_silent_return(self):
        # v4.0：日志由 KBService._log(level, message) 端口统一处理；
        # 契约钉 level 字面量而非 logger.debug 具体实现。
        levels = [
            sub.args[0].value
            for sub in ast.walk(self.branch)
            if isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "_log"
            and sub.args
            and isinstance(sub.args[0], ast.Constant)
        ]
        self.assertIn("debug", levels, "启动期分支必须走 debug 日志（不打 WARN）")
        self.assertNotIn("warning", levels, "启动期分支不得打 warning")
        returns = [s for s in ast.walk(self.branch) if isinstance(s, ast.Return)]
        self.assertTrue(
            any(r.value is None or (isinstance(r.value, ast.Constant) and r.value.value is None) for r in returns),
            "启动期分支必须 return None",
        )

    def test_startup_branch_no_negative_cache(self):
        self.assertEqual(
            _writes_kb_ready_false(self.branch), [],
            "启动期分支不得写 _kb_ready 负缓存（自愈重试依赖可再探测）",
        )

    def test_runtime_branch_warn_and_negative_cache_preserved(self):
        """守卫之外（真·未配置）保留 WARN + 负缓存，防每条消息重跑探测。"""
        func = _find_func(_parse_service(), "ensure")
        self.assertTrue(
            _kb_ready_false_writes(func),
            "KBService.ensure 运行期必须保留 ready 负缓存回退",
        )
        warn_texts = []
        for sub in ast.walk(func):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "_log"
                and sub.args
                and isinstance(sub.args[0], ast.Constant)
                and sub.args[0].value == "warning"
            ):
                for a in sub.args[1:]:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        warn_texts.append(a.value)
        self.assertTrue(
            warn_texts,
            "运行期必须保留 warning 日志端口",
        )


class TestOnLoadedSelfHeal(unittest.TestCase):
    def test_no_stale_scan(self):
        """启动期不写负缓存后，扫 stale 决定重试恒空转——必须已移除。"""
        hook = _find_func(_parse(), "_on_astrbot_loaded")
        for sub in ast.walk(hook):
            if isinstance(sub, ast.Assign):
                for t in sub.targets:
                    if isinstance(t, ast.Name) and t.id == "stale":
                        raise AssertionError(
                            "_on_astrbot_loaded 不得再扫 stale 负缓存决定是否重试"
                        )

    def test_resync_accepts_background_handoff(self):
        """v3.4.6 建库后台化后 _ensure_kb 受理即返回 None——受理即成功。"""
        hook = _find_func(_parse(), "_on_astrbot_loaded")
        resync = None
        for sub in ast.walk(hook):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == "_resync":
                resync = sub
                break
        self.assertIsNotNone(resync, "_on_astrbot_loaded 内缺少 _resync 任务体")
        found = any(
            isinstance(sub, ast.Compare)
            and isinstance(sub.ops[0], ast.In)
            and isinstance(sub.comparators[0], ast.Attribute)
            and sub.comparators[0].attr == "_kb_syncing"
            for sub in ast.walk(resync)
            if isinstance(sub, ast.Compare)
        )
        self.assertTrue(
            found,
            "_resync 成功判断必须含 `kb_name in self._kb_syncing`（后台受理即成功）",
        )


if __name__ == "__main__":
    unittest.main()
