# -*- coding: utf-8 -*-
"""v3.5.0 节奏引擎接线的源码契约测试（回归钉）。

缺陷（2026-09-04 用户「节奏感知不强」→ 追查实证）：
节奏引擎两处调用 `rhythm_heat(now, last_user_ts, ...)`，第二参数曾传
`self._last_user_ts.get(umo)`。但 `_last_user_ts[umo]` 在用户消息到达时
被 `_track_activity` 立即刷成 now（main.py:1044），回复计算延迟时读到的
就是「本次到达时刻」→ gap = 发送 − 本次到达 ≈ 十几秒处理时间，恒 < 热聊
阈值 → **永远判 hot，cold/warm 分支从第一次实测起就从未触发**。

而人类可读的 gap 文案（`_gap_for_req`）读的是 `self._prev_seen`：
`_track_time_activity` 在消息到达时先把上一条 `_last_seen` 挪进
`_prev_seen`（main.py:604）再刷新 `_last_seen`，故 `_prev_seen[umo]` 是
「上一条消息」时间，不会被本次覆盖。节奏引擎必须与之同源。

契约（main.py）：
- 每一个 `rhythm_heat(...)` 调用，其第 2 个位置参数必须是
  `self._prev_seen.get(umo)`，且**绝不能**是 `self._last_user_ts...`。

不 import main.py（本机无 astrbot 包），用 ast 直接钉源码结构。
"""

import ast
import os
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import find_func as _find_func, parse_main as _parse

_MAIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"
)


def _attr_chain(node):
    """把 `self._prev_seen.get(umo)` / `self._last_user_ts` 这类表达式摊平成
    点分字符串（`.get(...)` 调用的接收者链）。"""
    if isinstance(node, ast.Call):
        # self.X.get(umo) → 关注 self.X 部分
        return _attr_chain(node.func)
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _rhythm_heat_calls():
    calls = []
    for node in ast.walk(_parse()):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "rhythm_heat"
        ):
            calls.append(node)
    return calls


class TestRhythmHeatReadsPrevSeen(unittest.TestCase):
    def test_rhythm_heat_is_called(self):
        # 至少注入点 + 延迟融合点两处
        self.assertGreaterEqual(
            len(_rhythm_heat_calls()), 2, "main.py 应有多处 rhythm_heat 调用（注入+延迟）"
        )

    def test_second_arg_is_prev_seen(self):
        # v4.0 Phase 2：第二参数允许两种等价形态——
        #   self._prev_seen.get(umo)（原始读法）
        #   snap.prev_seen（_time_snapshot 快照读法，单源由下方构造点契约钉死）
        for i, call in enumerate(_rhythm_heat_calls()):
            self.assertGreaterEqual(
                len(call.args), 2, f"rhythm_heat 调用#{i} 缺少第 2 个位置参数 last_user_ts"
            )
            chain = _attr_chain(call.args[1])
            self.assertTrue(
                chain.startswith("self._prev_seen")
                or chain in ("snap.prev_seen", "snapshot.prev_seen"),
                f"rhythm_heat 调用#{i} 第 2 参数应为 _prev_seen/快照 prev_seen，实为 {chain}",
            )

    def test_snapshot_factory_single_source(self):
        """_time_snapshot 的 previous_seen 必须读 self._prev_seen——
        快照读法的「与 gap 文案同源」由此构造点契约保证（恒-hot 防线等价迁移）。"""
        func = _find_func(_parse(), "_time_snapshot")
        calls = [
            n for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "from_mappings"
        ]
        self.assertTrue(calls, "_time_snapshot 必须经 TimeContextSnapshot.from_mappings 构建")
        for call in calls:
            kw = {k.arg: k.value for k in call.keywords}
            self.assertIn("previous_seen", kw, "必须显式传 previous_seen")
            self.assertTrue(
                _attr_chain(kw["previous_seen"]).startswith("self._prev_seen"),
                "快照 previous_seen 唯一来源必须是 self._prev_seen",
            )

    def test_never_reads_last_user_ts(self):
        for i, call in enumerate(_rhythm_heat_calls()):
            for j, a in enumerate(call.args):
                chain = _attr_chain(a)
                self.assertNotIn(
                    "_last_user_ts",
                    chain,
                    f"rhythm_heat 调用#{i} 第 {j} 参数误用 _last_user_ts（会导致恒 hot）",
                )
        # 快照工厂同样不得把 user_last_ts 喂进 previous_seen
        func = _find_func(_parse(), "_time_snapshot")
        for call in ast.walk(func):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "from_mappings"
            ):
                for k in call.keywords:
                    if k.arg == "previous_seen":
                        self.assertNotIn("_last_user_ts", _attr_chain(k.value))


class TestDelayFusionWiring(unittest.TestCase):
    """apply_rhythm_delay 接线：延迟融合必须在 rhythm_enable 守卫内、
    且在 cron/命令/空文本早退之后（这些已在 _typing_delay_before_send 顶部，
    这里只钉融合调用本身读热度的方式与既有 rhythm_heat 一致）。"""

    def test_apply_rhythm_delay_used(self):
        tree = _parse()
        found = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "apply_rhythm_delay"
            for n in ast.walk(tree)
        )
        self.assertTrue(found, "main.py 必须调用 apply_rhythm_delay 做延迟融合")

    def test_window_keys_read_via_time_f(self):
        """4 个窗口键必须经 _time_f（float 安全读取）取值，非法回落默认。"""
        tree = _parse()
        timef = None
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == "_time_f":
                timef = n
                break
        self.assertIsNotNone(timef, "main.py 缺少 _time_f 助手")
        src = ast.dump(_parse())
        for key in (
            "rhythm_delay_hot_min",
            "rhythm_delay_hot_max",
            "rhythm_delay_cold_min",
            "rhythm_delay_cold_max",
        ):
            self.assertIn(key, src, f"窗口键 {key} 未在 main.py 中被读取")
        self.assertNotIn("rhythm_delay_factor", src, "旧乘法系数键必须彻底移除")


class TestSegmentGapWiring(unittest.TestCase):
    """v3.7.1 段间隔可配置接线：调用点必须传五键配置参数。"""

    def test_call_site_reads_config(self):
        with open(_MAIN, encoding="utf-8") as f:
            src = f.read()
        for key in ("split_gap_min", "split_gap_max", "split_gap_long_prob",
                    "split_gap_long_min", "split_gap_long_max"):
            self.assertIn(key, src, f"segment_gap 调用点缺 {key}")
        # 调用必须发生在 _split_send_bubbles 内
        func = _find_func(_parse(), "_split_send_bubbles")
        fsrc = ast.dump(func)
        self.assertIn("segment_gap", fsrc, "分段发送必须经 segment_gap 取间隔")
        self.assertIn("split_gap_min", fsrc)


if __name__ == "__main__":
    unittest.main()
