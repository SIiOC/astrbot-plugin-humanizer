# -*- coding: utf-8 -*-
"""P0 语风学习：会话库采集与清洗测试（不读真实数据库）。"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from style_core.corpus import append_learned_pairs, read_pool
from style_core.history import (
    clean_assistant_text,
    clean_user_text,
    collect_pairs_from_db,
    filter_new_pairs,
    pairs_from_messages,
    summarize_pairs,
)


class TestClean(unittest.TestCase):
    def test_removes_system_reminder(self):
        raw = "今天好累\n<system_reminder>Current datetime: 2026-11-10</system_reminder>"
        self.assertEqual(clean_user_text(raw), "今天好累")

    def test_skips_commands_urls_and_emoji(self):
        self.assertIsNone(clean_user_text("/style_learn"))
        self.assertIsNone(clean_user_text("看 https://example.com"))
        self.assertIsNone(clean_user_text("😭😭😭"))
        self.assertIsNone(clean_user_text(""))

    def test_keeps_short_and_typos(self):
        self.assertEqual(clean_user_text("好累啊"), "好累啊")
        self.assertEqual(clean_user_text("这是错别字"), "这是错别字")

    def test_assistant_truncates(self):
        self.assertEqual(len(clean_assistant_text("啊" * 500)), 200)


class TestPairs(unittest.TestCase):
    def test_pairs_user_with_next_assistant(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "今天好累"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "那早点睡"}]},
            {"role": "user", "content": [{"type": "text", "text": "/命令"}]},
            {"role": "user", "content": [{"type": "text", "text": "晚安"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "晚安啦"}]},
        ]
        pairs = pairs_from_messages(messages)
        self.assertEqual(pairs, [("今天好累", "那早点睡"), ("晚安", "晚安啦")])

    def test_summary_does_not_expose_text(self):
        stats = summarize_pairs([("短", "x"), ("这一句稍微长一点", "y")])
        self.assertEqual(stats["count"], 2)
        self.assertNotIn("这一句", str(stats))


class TestCollectFromDb(unittest.TestCase):
    def _make_db(self, path):
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TABLE conversations ("
            "conversation_id TEXT, platform_id TEXT, user_id TEXT, "
            "updated_at TEXT, content TEXT)"
        )
        old = json.dumps(
            [
                {"role": "user", "content": [{"type": "text", "text": "旧消息"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "旧回复"}]},
            ],
            ensure_ascii=False,
        )
        new = json.dumps(
            [
                {"role": "user", "content": [{"type": "text", "text": "新消息"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "新回复"}]},
            ],
            ensure_ascii=False,
        )
        con.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?)",
            ("c1", "qq", "qq:FriendMessage:42", "2026-11-01", old),
        )
        con.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?)",
            ("c2", "qq", "qq:FriendMessage:42", "2026-11-02", new),
        )
        con.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?)",
            ("c3", "qq", "qq:FriendMessage:99", "2026-11-03", new),
        )
        con.commit()
        con.close()

    def test_collects_only_target_user_in_time_order(self):
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "data_v4.db")
            self._make_db(db)
            pairs = collect_pairs_from_db(db, user_id_like="42", platform_id="qq")
            self.assertEqual([p[0] for p in pairs], ["旧消息", "新消息"])

    def test_dedupes_same_user_text(self):
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "data_v4.db")
            self._make_db(db)
            con = sqlite3.connect(db)
            dup = json.dumps(
                [
                    {"role": "user", "content": [{"type": "text", "text": "新消息"}]},
                    {"role": "assistant", "content": [{"type": "text", "text": "另一个回复"}]},
                ],
                ensure_ascii=False,
            )
            con.execute(
                "INSERT INTO conversations VALUES (?,?,?,?,?)",
                ("c4", "qq", "qq:FriendMessage:42", "2026-11-04", dup),
            )
            con.commit()
            con.close()
            pairs = collect_pairs_from_db(db, user_id_like="42", platform_id="qq")
            self.assertEqual([p[0] for p in pairs], ["旧消息", "新消息"])


class TestCorpusAppend(unittest.TestCase):
    def test_filter_and_append_dedupes_by_user_text(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "user_corpus.jsonl")
            first = [("今天好累", "那早点睡")]
            self.assertEqual(append_learned_pairs(path, first), 1)
            rows = read_pool(path)
            self.assertEqual([r["role"] for r in rows], ["user", "assistant"])
            # 同一条用户文本、不同助手回复，不应重复入池。
            again = [("今天好累", "另一种回复")]
            self.assertEqual(append_learned_pairs(path, again), 0)
            fresh = filter_new_pairs(path, [("今天好累", "x"), ("晚安", "好梦")])
            self.assertEqual(fresh, [("晚安", "好梦")])


if __name__ == "__main__":
    unittest.main()
