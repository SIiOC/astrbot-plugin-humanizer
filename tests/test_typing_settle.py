# -*- coding: utf-8 -*-
"""补足式打字延迟（typing.settle_delay）单元测试 + 钩子接线契约。

背景（2026-09-06 日志 112 轮实证）：v3.5 链路自然耗时（防抖等待+记忆
检索+agent 工具循环）中位约 49s、p90 约 95s；旧「额外叠加」式打字延迟
（中位 7s，占总延迟中位仅 12%）只推高总响应，hot 快回窗口被完全淹没
（自然耗时 >> 4s），cold 附加使 p90 总延迟逼近两分钟。语义改为「目标
总延迟补足」：实际 sleep = max(0, 目标 − 已自然耗时)。
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core.typing import apply_rhythm_delay, compute_delay, settle_delay

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN = os.path.join(_PLUGIN_ROOT, "main.py")


class TestSettleDelay(unittest.TestCase):
    def test_zero_when_elapsed_exceeds_target(self):
        """自然耗时已超目标 → 零补足（重链路常态，2026-09-06 实证中位 49s）。"""
        self.assertEqual(settle_delay(12.0, 49.0), 0.0)
        self.assertEqual(settle_delay(4.0, 95.0), 0.0)

    def test_supplements_gap_on_fast_pipeline(self):
        """快链路（自然耗时短）→ 补足差额。"""
        self.assertAlmostEqual(settle_delay(12.0, 3.0), 9.0)
        self.assertAlmostEqual(settle_delay(15.0, 0.0), 15.0)

    def test_elapsed_zero_returns_target(self):
        self.assertAlmostEqual(settle_delay(7.5, 0.0), 7.5)

    def test_never_negative(self):
        self.assertEqual(settle_delay(0.0, 100.0), 0.0)
        self.assertEqual(settle_delay(5.0, 5.0), 0.0)
        self.assertEqual(settle_delay(3.0, 3.0001), 0.0)

    def test_tolerates_none_and_negative_inputs(self):
        """防御：None/负值输入不炸、不产生负 sleep。"""
        self.assertEqual(settle_delay(None, 10.0), 0.0)
        self.assertEqual(settle_delay(10.0, None), 10.0)
        self.assertEqual(settle_delay(-5.0, 1.0), 0.0)
        self.assertEqual(settle_delay(10.0, -1.0), 10.0)


class TestDelaySemanticsStillValid(unittest.TestCase):
    """compute_delay / apply_rhythm_delay 的输出现在是「目标总延迟」，
    数值语义不变——只确认接口契约未漂移，供补足逻辑消费。"""

    def test_compute_delay_positive_and_length_correlated(self):
        short = compute_delay("好", inbound_len=2, hour=14)
        long = compute_delay("字" * 200, inbound_len=2, hour=14)
        self.assertGreater(short, 0)
        # 长度相关性：长回复目标大于短回复（上限裁剪由钩子做，函数不裁）
        self.assertGreater(long, short)

    def test_rhythm_delay_hot_overrides_cold_stacks(self):
        hot = apply_rhythm_delay(10.0, "hot", n_chars=0, hot_window=(1.5, 4.0))
        self.assertGreaterEqual(hot, 1.5)
        self.assertLessEqual(hot, 4.0)
        cold = apply_rhythm_delay(10.0, "cold", cold_window=(10.0, 25.0))
        self.assertGreaterEqual(cold, 20.0)


# ---- main.py 接线契约（AST，不 import main.py）----


def _find_hook_src():
    with open(_MAIN, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename=_MAIN)
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if node.name == "_typing_delay_before_send":
                return ast.get_source_segment(src, node)
    return None


class TestHookWiring(unittest.TestCase):
    def setUp(self):
        self.src = _find_hook_src()
        self.assertIsNotNone(self.src, "_typing_delay_before_send 钩子应存在")

    def test_uses_settle_delay(self):
        self.assertIn("settle_delay(", self.src, "钩子应调用 settle_delay 补足")

    def test_reads_message_timestamp(self):
        self.assertIn(
            "message_obj",
            self.src,
            "自然耗时起点应取消息到达时间戳（防抖轮=第一条消息到达）",
        )
        self.assertIn("timestamp", self.src)

    def test_sleep_only_when_wait_positive(self):
        i_if = self.src.find("if wait > 0:")
        i_sleep = self.src.find("await asyncio.sleep(wait)")
        self.assertGreater(i_if, -1, "应仅在有差额时 sleep")
        self.assertGreater(i_sleep, i_if, "sleep 应在补足判断之内")

    def test_zero_wait_logged_debug(self):
        """零补足走 debug（重链路常态，避免每轮刷 info）。"""
        self.assertIn("零补足", self.src)
        self.assertIn("logger.debug", self.src)

    def test_dedupe_check_before_delay(self):
        """复读拦截先于延迟补足——命中复读时不应白等（哪怕补足为 0）。"""
        i_dedupe = self.src.find('self._t("dedupe_rewrite", True)')
        i_settle = self.src.find("settle_delay(")
        self.assertGreater(i_dedupe, -1)
        self.assertLess(i_dedupe, i_settle)


if __name__ == "__main__":
    unittest.main()
