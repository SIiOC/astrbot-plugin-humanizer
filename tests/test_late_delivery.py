# -*- coding: utf-8 -*-
"""v3.8.0 主动消息迟到补发（late_delivery_block）单测 + AST 接线契约。

素材参考时笺 time_awareness <LATE_PROMPT>（MIT），改写为主动消息语境。
"""

import ast
import os
import sys as _sys
import unittest

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func  # noqa: E402

from humanizer_core.proactive import late_delivery_block


class TestLateDeliveryBlock(unittest.TestCase):
    def test_below_threshold_silent(self):
        self.assertEqual(late_delivery_block(14, 15), "")
        self.assertEqual(late_delivery_block(0, 15), "")

    def test_at_threshold_fires(self):
        out = late_delivery_block(15, 15)
        self.assertIn("15 分钟前", out)
        self.assertIn("来晚了", out)

    def test_hours_late(self):
        out = late_delivery_block(300, 15)
        self.assertIn("300 分钟前", out)

    def test_beyond_12h_cap_silent(self):
        # 宕机整夜/跨天：隔夜的"来晚了"比不提更怪，静默丢弃
        self.assertEqual(late_delivery_block(721, 15), "")
        self.assertEqual(late_delivery_block(100000, 15), "")

    def test_zero_threshold_disables(self):
        self.assertEqual(late_delivery_block(999, 0), "")
        self.assertEqual(late_delivery_block(999, -5), "")

    def test_garbage_inputs(self):
        self.assertEqual(late_delivery_block("x", 15), "")
        self.assertEqual(late_delivery_block(None, 15), "")
        self.assertEqual(late_delivery_block(20, "y"), "")


class TestLateWiring(unittest.TestCase):
    def test_loop_captures_due_before_reschedule(self):
        """due_ts 必须在重排之前捕获（迟到度量依赖重排前的原定时刻）。

        v4.0 Phase 6：重排已下沉 `ProactiveState.reschedule_next`，不再是
        `_next_trigger_ts[...] = ...` 下标赋值；这里同时接受两种形态——
        下标赋值（旧）或服务重排调用（新）——并保持行号先后断言。
        """
        func = _find_func(_parse(), "_proactive_loop")
        assign_due = None
        reschedule_lines = []
        for n in ast.walk(func):
            if isinstance(n, ast.Assign):
                targets = [t.id for t in n.targets if isinstance(t, ast.Name)]
                if "due_ts" in targets:
                    assign_due = n.lineno
                for t in n.targets:
                    if (
                        isinstance(t, ast.Subscript)
                        and isinstance(t.value, ast.Attribute)
                        and t.value.attr == "_next_trigger_ts"
                    ):
                        reschedule_lines.append(n.lineno)
            # 新形态：self._proactive_state.reschedule_next(...) 调用
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "reschedule_next"
            ):
                reschedule_lines.append(n.lineno)
        self.assertIsNotNone(assign_due, "必须捕获刚到期时刻 due_ts")
        self.assertTrue(reschedule_lines, "必须存在重排（下标赋值或服务调用）")
        self.assertLess(assign_due, max(reschedule_lines), "due_ts 必须在重排之前捕获")

    def test_chat_passes_due_and_builds_block(self):
        """v4.0 Phase 6：迟到块渲染下沉 proactive_prompt.late_block。

        _proactive_chat 仍必须接收 due_ts 并调用 late_block（阈值可配置）。
        """
        func = _find_func(_parse(), "_proactive_chat")
        src = ast.dump(func)
        self.assertIn("late_block", src)
        self.assertIn("proactive_late_threshold_minutes", src, "阈值必须可配置")
        # 签名带 due_ts 且默认 None（手动/其他调用零改动）
        args = {a.arg for a in func.args.args}
        self.assertIn("due_ts", args)
        self.assertTrue(any(isinstance(d, ast.Constant) and d.value is None
                            for d in func.args.defaults))

    def test_imported_by_prompt_module(self):
        """迟到块渲染函数必须被 proactive_prompt 引用（运行路径可达）。"""
        import os as _os

        path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "humanizer_core",
            "proactive_prompt.py",
        )
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("late_delivery_block", src)
        self.assertIn("due_ts", src)


if __name__ == "__main__":
    unittest.main()
