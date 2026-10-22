# -*- coding: utf-8 -*-
"""v3.8.0 双向间隔（LAST_CHAT）接线的源码契约测试（AST，不 import main.py）。

钉五条契约（main.py + time_flow.py + state.py）：
1. _init_time_stores 加载双向表且带 v2 回填（user 侧兜底、ai 侧不回填）；
2. 三个打点位：_track_time_activity 写 user 侧、_on_bot_sent 与
   _on_bot_response 写 ai 侧（旧框架降级路径不能漏）；
3. 两个落盘路径（_time_flush_loop/_flush_time_state）都带 restrict 同步收缩；
4. _time_context_block 有 include_last_chat 开关守卫、读原始双向表（非
   _prev_seen）、传进 build_state_block，且早退门纳入 last_chat_line；
5. 纯函数层：build_state_block 签名含 last_chat_line；state 具备
   load_sides/restrict 且版本号为 3。
"""

import ast
import os
import sys as _sys
import unittest

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func  # noqa: E402

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse_file(relpath):
    with open(os.path.join(_PLUGIN_ROOT, relpath), encoding="utf-8") as f:
        return ast.parse(f.read())


class TestStoreWiring(unittest.TestCase):
    def test_init_loads_sides_with_backfill(self):
        func = _find_func(_parse(), "_init_time_stores")
        src = ast.dump(func)
        self.assertIn("load_sides", src, "启动必须加载双向表")
        self.assertIn("_user_last_ts", src)
        self.assertIn("_ai_last_ts", src)

    def test_record_points(self):
        user_func = _find_func(_parse(), "_track_time_activity")
        self.assertIn("_user_last_ts", ast.dump(user_func), "用户打点缺 user 侧记录")
        for name in ("_on_bot_sent", "_on_bot_response"):
            func = _find_func(_parse(), name)
            self.assertIn("_ai_last_ts", ast.dump(func), f"{name} 缺 ai 侧记录")

    def test_both_flush_paths_save_sides(self):
        for name in ("_time_flush_loop", "_flush_time_state"):
            func = _find_func(_parse(), name)
            src = ast.dump(func)
            self.assertIn("_user_last_ts", src, f"{name} 落盘缺 user 表")
            self.assertIn("_ai_last_ts", src, f"{name} 落盘缺 ai 表")
            self.assertIn("restrict", src, f"{name} 必须按主表键集收缩双向表")


class TestInjectionWiring(unittest.TestCase):
    def test_context_block_guards_and_passes(self):
        func = _find_func(_parse(), "_time_context_block")
        src = ast.dump(func)
        self.assertIn("include_last_chat", src, "必须有默认关的配置开关")
        self.assertIn("render_last_chat_line", src)
        self.assertIn("last_chat_line", src, "必须传进 build_state_block")
        self.assertIn("_user_last_ts", src, "必须读原始双向表（非 _prev_seen）")

    def test_gate_includes_last_chat_line(self):
        # 早退门 `if not (gap_text or state_text or last_chat_line)`：
        # 双向行单独存在时不得被门吞掉
        func = _find_func(_parse(), "_time_context_block")
        for n in ast.walk(func):
            if (
                isinstance(n, ast.If)
                and isinstance(n.test, ast.UnaryOp)
                and isinstance(n.test.op, ast.Not)
            ):
                inner = ast.dump(n.test.operand)
                if "state_text" in inner:
                    self.assertIn(
                        "last_chat_line", inner, "早退门必须纳入双向行（防被吞）"
                    )
                    return
        self.fail("未找到 gap/state 早退门（结构变更需同步本契约）")


class TestPureModuleContracts(unittest.TestCase):
    def test_build_state_block_signature(self):
        tree = _parse_file(os.path.join("humanizer_core", "time_flow.py"))
        func = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "build_state_block"
        )
        args = [a.arg for a in func.args.args]
        self.assertIn("last_chat_line", args)
        names = {
            n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
        }
        self.assertIn("render_last_chat_line", names)

    def test_state_store_v3(self):
        tree = _parse_file(os.path.join("humanizer_core", "state.py"))
        names = {
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
        }
        self.assertIn("load_sides", names)
        self.assertIn("restrict", names)
        src = ast.dump(tree)
        self.assertIn("'user_seen'", src, "save 落盘必须含 user_seen 键")
        self.assertIn("'ai_seen'", src, "save 落盘必须含 ai_seen 键")
        # 版本号 = 3
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "_TIME_STATE_VERSION"
                    for t in n.targets
                )
            ):
                self.assertEqual(n.value.value, 3)
                return
        self.fail("未找到 _TIME_STATE_VERSION 赋值")


if __name__ == "__main__":
    unittest.main()
