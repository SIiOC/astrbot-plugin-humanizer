# -*- coding: utf-8 -*-
"""v3.6.0 分段发送 + 连续性注入接线的源码契约测试（回归钉）。

不 import main.py（本机无 astrbot 包），用 ast 直接钉源码结构：

分段发送契约：
- 拆分必须挂在 on_decorating_result（_typing_delay_before_send）内，
  且在补足延迟结算之后（split 调用位于 settle_delay 之后）；
- _split_send_bubbles 必须含三重防护：split_reply_bubbles 拆分、
  result.chain 清空（拦截手法）、_new_inbound_since 插话中止；
- segment_gap 必须被接线（v3.4 预留的死代码正式启用）。

连续性注入契约：
- 必须读 self._prev_seen（与节奏/gap 文案同源），绝不能读
  _last_user_ts（本次到达即刷新 → 会把「刚回复完」误判成隔夜）。
"""

import ast
import json
import os
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA = os.path.join(_ROOT, "_conf_schema.json")
_TIME_FLOW = os.path.join(_ROOT, "humanizer_core", "time_flow.py")


def _func_def(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _calls_in(node, func_name):
    """收集 node 子树内函数名为 func_name 的调用。"""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if (isinstance(f, ast.Attribute) and f.attr == func_name) or (
                isinstance(f, ast.Name) and f.id == func_name
            ):
                out.append(n)
    return out


class TestSplitWiring(unittest.TestCase):
    def test_hook_calls_split_send(self):
        hook = _func_def(_parse(), "_typing_delay_before_send")
        self.assertIsNotNone(hook, "main.py 缺少 _typing_delay_before_send")
        self.assertTrue(
            _calls_in(hook, "_split_send_bubbles"),
            "on_decorating_result 钩子内必须调用 _split_send_bubbles",
        )

    def test_split_helper_has_safety_triad(self):
        helper = _func_def(_parse(), "_split_send_bubbles")
        self.assertIsNotNone(helper, "main.py 缺少 _split_send_bubbles 辅助方法")
        src = ast.dump(helper)
        # v4.0 Phase 7：拆分+「>1 段才拆」判定下沉 send_pipeline.split_plan；
        # 回到填下沉 send_pipeline.backfill_bubbles。其余三重防护仍在 main。
        self.assertIn("split_plan", src, "必须走拆分方案（split_plan 委托纯函数）")
        self.assertIn("segment_gap", src, "段间必须用 segment_gap 拟人间隙")
        self.assertIn("_new_inbound_since", src, "必须有新入站消息中止检查")
        self.assertIn("Plain", src, "必须跳过非纯文本待发链（防丢图片/语音）")
        self.assertIn("split_sent", src, "必须打 split_sent 统计点")
        self.assertIn("backfill_bubbles", src, "失败段回填必须走 backfill_bubbles")
        # 下沉后的纯函数归属：split_plan/backfill_bubbles 在 send_pipeline
        sp = ast.parse(
            open(
                os.path.join(_ROOT, "humanizer_core", "send_pipeline.py"),
                encoding="utf-8",
            ).read()
        )
        names = {
            n.name for n in ast.walk(sp) if isinstance(n, ast.FunctionDef)
        }
        self.assertIn("split_plan", names)
        self.assertIn("backfill_bubbles", names)

    def test_segment_gap_imported(self):
        for node in ast.walk(_parse()):
            if isinstance(node, ast.ImportFrom) and node.module == "humanizer_core.typing":
                names = {a.name for a in node.names}
                self.assertIn("segment_gap", names)
                return
        self.fail("main.py 缺少 humanizer_core.typing 导入")

    def test_split_reply_bubbles_reachable(self):
        """split_reply_bubbles 经 send_pipeline.split_plan 调用（运行路径可达）。"""
        sp = open(
            os.path.join(_ROOT, "humanizer_core", "send_pipeline.py"),
            encoding="utf-8",
        ).read()
        self.assertIn("split_reply_bubbles", sp)
        self.assertIn("from humanizer_core.typing import split_reply_bubbles", sp)

    def test_schema_split_keys(self):
        schema = json.loads(open(_SCHEMA, encoding="utf-8").read())
        items = schema["typing"]["items"]
        for key in ("split_enable", "split_threshold", "split_max_segments", "split_min_part"):
            self.assertIn(key, items, f"typing 组缺配置键 {key}")
        self.assertIs(items["split_enable"]["default"], False, "split_enable 必须默认关")


class TestContinuityWiring(unittest.TestCase):
    def test_time_block_injects_continuity(self):
        block = _func_def(_parse(), "_time_context_block")
        self.assertIsNotNone(block, "main.py 缺少 _time_context_block")
        src = ast.dump(block)
        self.assertIn("continuity_text", src, "时间块必须调用 continuity_text")
        self.assertIn("continuity_inject", src, "连续性注入必须有配置守卫")
        self.assertIn("continuity_line", src, "结果必须以 continuity_line 传入 build_state_block")

    def test_continuity_reads_prev_seen(self):
        """continuity_text 第 1 参必须读 self._prev_seen（同源防误判）。

        v4.0 Phase 2：允许快照单源读法 snap.prev_seen——_time_snapshot 的
        previous_seen←self._prev_seen 构造契约由
        tests/test_rhythm_wiring.py::test_snapshot_factory_single_source 钉死。
        """
        block = _func_def(_parse(), "_time_context_block")
        calls = _calls_in(block, "continuity_text")
        self.assertTrue(calls, "时间块缺少 continuity_text 调用")

        def _attr_chain(node):
            # self._prev_seen.get(umo) → "self._prev_seen"（展开 .get 调用）
            if isinstance(node, ast.Call):
                return _attr_chain(node.func)
            parts = []
            cur = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            return ".".join(reversed(parts))

        for call in calls:
            self.assertGreaterEqual(len(call.args), 1)
            dotted = _attr_chain(call.args[0])
            self.assertTrue(
                dotted.startswith("self._prev_seen")
                or dotted in ("snap.prev_seen", "snapshot.prev_seen"),
                f"continuity_text 第 1 参应读 _prev_seen/快照单源，实为 {dotted}",
            )
            self.assertNotIn("_last_user_ts", dotted, "禁止读 _last_user_ts（本次到达即刷新）")

    def test_time_flow_exports(self):
        src = open(_TIME_FLOW, encoding="utf-8").read()
        tree = ast.parse(src)
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for fn in ("continuity_label", "continuity_text"):
            self.assertIn(fn, names, f"time_flow.py 缺少 {fn}")
        self.assertIn("CONTINUITY_DIRECTIVES", src)
        # build_state_block 必须有 continuity_line 参数
        bsb = _func_def(tree, "build_state_block")
        self.assertIsNotNone(bsb)
        kwargs = {a.arg for a in bsb.args.kwonlyargs} if bsb.args.kwonlyargs else set()
        kwargs |= {a.arg for a in bsb.args.args}
        self.assertIn("continuity_line", kwargs, "build_state_block 缺 continuity_line 参数")

    def test_schema_continuity_key(self):
        schema = json.loads(open(_SCHEMA, encoding="utf-8").read())
        self.assertIn("continuity_inject", schema["time"]["items"])


if __name__ == "__main__":
    unittest.main()
