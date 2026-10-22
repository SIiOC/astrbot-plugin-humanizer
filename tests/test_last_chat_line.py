# -*- coding: utf-8 -*-
"""v3.8.0 双向间隔感知纯函数单测（render_last_chat_line）。

相对时间分档移植自时笺 time_awareness（MIT），语义钉死：
刚刚(<60s)/X 分钟前/X 小时前/X 天前/超一周回落 MM-DD；时钟倒走兜底刚刚。
"""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from humanizer_core.state import TimeStateStore
from humanizer_core.time_flow import (
    build_state_block,
    render_last_chat_line,
)

NOW = datetime(2026, 9, 8, 12, 0).timestamp()


def _ago(seconds, now=NOW):
    return now - seconds


class TestRenderLastChatLine(unittest.TestCase):
    def test_both_recent_silent(self):
        # 双侧都在 1 分钟内 = 即时对话中，不注入（噪音）
        self.assertEqual(render_last_chat_line(_ago(10), _ago(5), NOW), "")

    def test_both_missing(self):
        self.assertEqual(render_last_chat_line(None, None, NOW), "")

    def test_user_only(self):
        out = render_last_chat_line(_ago(3 * 3600), None, NOW)
        self.assertEqual(out, "对方最后发言 3 小时前")

    def test_ai_only(self):
        out = render_last_chat_line(None, _ago(90), NOW)
        self.assertEqual(out, "你最后发言 1 分钟前")

    def test_asymmetric_proactive_blindspot(self):
        # 核心场景：Bot 刚主动发过（你=刚刚），对方其实已沉默 3 天
        out = render_last_chat_line(_ago(3 * 86400), _ago(20), NOW)
        self.assertEqual(out, "对方最后发言 3 天前 · 你最后发言 刚刚")

    def test_minute_hour_day_buckets(self):
        self.assertEqual(
            render_last_chat_line(_ago(61), _ago(7200), NOW),
            "对方最后发言 1 分钟前 · 你最后发言 2 小时前",
        )
        self.assertEqual(
            render_last_chat_line(_ago(6 * 3600), _ago(2 * 86400 + 3600), NOW),
            "对方最后发言 6 小时前 · 你最后发言 2 天前",
        )

    def test_beyond_one_week_falls_back_to_date(self):
        # 10 天前 = 08-29（超一周回落 MM-DD，数字间隔失去语感）
        out = render_last_chat_line(_ago(10 * 86400), None, NOW)
        self.assertEqual(out, "对方最后发言 08-29")

    def test_single_side_just_now_suppressed(self):
        # 新会话第一条用户消息：对方"刚刚"+本侧无记录 = 零信息量噪音，不注入
        self.assertEqual(render_last_chat_line(_ago(20), None, NOW), "")
        self.assertEqual(render_last_chat_line(None, _ago(20), NOW), "")

    def test_clock_skew_negative(self):
        # 时钟倒走（user_ts 在未来）兜底"刚刚"，不显示负数
        out = render_last_chat_line(_ago(-500), _ago(3 * 3600), NOW)
        self.assertEqual(out, "对方最后发言 刚刚 · 你最后发言 3 小时前")

    def test_garbage_inputs(self):
        self.assertEqual(render_last_chat_line("abc", {}, NOW), "")
        self.assertEqual(render_last_chat_line(float("nan"), -1, NOW), "")
        self.assertEqual(render_last_chat_line(None, float("nan"), NOW), "")


class TestBuildStateBlockLastChat(unittest.TestCase):
    def test_line_injected_after_gap(self):
        now = datetime(2026, 9, 8, 12, 0)
        block = build_state_block(
            now,
            gap_text="3 小时12分钟",
            last_chat_line="对方最后发言 3 小时前 · 你最后发言 刚刚",
        )
        lines = block.splitlines()
        self.assertIn("<time_context>", lines)
        gap_i = next(i for i, l in enumerate(lines) if l.startswith("距上次交流"))
        chat_i = next(i for i, l in enumerate(lines) if l.startswith("对方最后发言"))
        self.assertEqual(chat_i, gap_i + 1, "双向行必须紧跟 gap 行（同为间隔类信息）")

    def test_empty_line_no_injection(self):
        now = datetime(2026, 9, 8, 12, 0)
        block = build_state_block(now, gap_text="隔了一天", last_chat_line="")
        self.assertNotIn("最后发言", block)


class TestTimeStateStoreV3(unittest.TestCase):
    """v3 落盘格式与 v2 兼容读写（tempfile 隔离）。"""

    def _store(self, tmp):
        return TimeStateStore(Path(tmp) / "time_state.json")

    def test_roundtrip_all_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            store.save(
                {"a:1": 100.0, "b:2": 200.0},
                {"a:1": 10.0, "b:2": 20.0},
                {"a:1": 90.0, "b:2": 150.0},
                {"a:1": 100.0},
            )
            self.assertEqual(store.load(), {"a:1": 100.0, "b:2": 200.0})
            self.assertEqual(store.load_first_seen(), {"a:1": 10.0, "b:2": 20.0})
            self.assertEqual(
                store.load_sides(),
                ({"a:1": 90.0, "b:2": 150.0}, {"a:1": 100.0}),
            )
            raw = json.loads(
                (Path(tmp) / "time_state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(raw["version"], 3)

    def test_v2_file_backcompat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "time_state.json"
            path.write_text(
                json.dumps(
                    {"version": 2, "last_seen": {"a:1": 100.0}, "first_seen": {"a:1": 5.0}}
                ),
                encoding="utf-8",
            )
            store = self._store(tmp)
            self.assertEqual(store.load(), {"a:1": 100.0})
            self.assertEqual(store.load_first_seen(), {"a:1": 5.0})
            self.assertEqual(store.load_sides(), ({}, {}))  # 缺键 → 空表，调用方回填

    def test_garbage_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "time_state.json"
            path.write_text("{ not json", encoding="utf-8")
            store = self._store(tmp)
            self.assertEqual(store.load_sides(), ({}, {}))

    def test_restrict_syncs_keysets(self):
        kept = {"a:1": 100.0}
        self.assertEqual(TimeStateStore.restrict({"a:1": 90.0, "z:9": 1.0}, kept), {"a:1": 90.0})


if __name__ == "__main__":
    unittest.main()
