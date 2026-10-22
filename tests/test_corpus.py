# -*- coding: utf-8 -*-
"""语料解析/去重/采样/语料池管理测试。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_core import corpus


class TestParseTxt(unittest.TestCase):
    def test_adjacent_lines_pair(self):
        pairs = corpus.parse_txt("你好\n我很好\n吃了吗\n吃了\n")
        self.assertEqual(pairs, [("你好", "我很好"), ("吃了吗", "吃了")])

    def test_odd_lines_drop_last(self):
        pairs = corpus.parse_txt("你好\n我很好\n孤句")
        self.assertEqual(pairs, [("你好", "我很好")])

    def test_blank_lines_removed(self):
        pairs = corpus.parse_txt("你好\n\n我很好\n")
        self.assertEqual(pairs, [("你好", "我很好")])

    def test_too_short_dropped(self):
        pairs = corpus.parse_txt("你好\n我很好\nOK\n啊")
        self.assertEqual(len(pairs), 1)

    def test_empty(self):
        self.assertEqual(corpus.parse_txt(""), [])


class TestParseJsonl(unittest.TestCase):
    def test_role_alternating(self):
        text = '\n'.join([
            '{"role": "user", "content": "在吗"}',
            '{"role": "assistant", "content": "在呢"}',
            '{"role": "user", "content": "忙啥"}',
            '{"role": "assistant", "content": "写代码"}',
        ])
        pairs = corpus.parse_jsonl(text)
        self.assertEqual(pairs, [("在吗", "在呢"), ("忙啥", "写代码")])

    def test_content_only_pairs(self):
        text = '\n'.join([
            '{"content": "你好"}',
            '{"content": "你也好"}',
        ])
        pairs = corpus.parse_jsonl(text)
        self.assertEqual(pairs, [("你好", "你也好")])

    def test_user_assistant_single_row(self):
        pairs = corpus.parse_jsonl('{"user": "你好", "assistant": "你也好"}')
        self.assertEqual(pairs, [("你好", "你也好")])

    def test_bad_line_skipped(self):
        pairs = corpus.parse_jsonl('not json\n{"content": "你好"}')
        self.assertEqual(len(pairs), 0)


class TestParseJsonArray(unittest.TestCase):
    def test_str_array_pairs(self):
        pairs = corpus.parse_json_array('["你好", "你也好", "吃了吗", "吃了"]')
        self.assertEqual(pairs, [("你好", "你也好"), ("吃了吗", "吃了")])

    def test_dict_array(self):
        pairs = corpus.parse_json_array('[{"user": "你好", "assistant": "你也好"}]')
        self.assertEqual(pairs, [("你好", "你也好")])

    def test_content_dict_array(self):
        pairs = corpus.parse_json_array('[{"content": "你好"}, {"content": "你也好"}]')
        self.assertEqual(pairs, [("你好", "你也好")])

    def test_invalid(self):
        self.assertEqual(corpus.parse_json_array("not json"), [])
        self.assertEqual(corpus.parse_json_array('{"a": 1}'), [])


class TestParseCsv(unittest.TestCase):
    def test_query_response_cols(self):
        text = "query,response\n你好,你也好\n吃了吗,吃了\n"
        pairs = corpus.parse_csv(text)
        self.assertEqual(pairs, [("你好", "你也好"), ("吃了吗", "吃了")])

    def test_content_col_fallback(self):
        text = "content\n你好\n你也好\n"
        pairs = corpus.parse_csv(text)
        self.assertEqual(pairs, [("你好", "你也好")])

    def test_no_known_cols(self):
        text = "a,b\n1,2\n"
        self.assertEqual(corpus.parse_csv(text), [])


class TestParseCorpusText(unittest.TestCase):
    def test_by_extension(self):
        self.assertEqual(corpus.parse_corpus_text("你好\n我也好", "a.txt"), [("你好", "我也好")])
        self.assertEqual(
            corpus.parse_corpus_text('{"role":"user","content":"你好"}\n{"role":"assistant","content":"我也好"}', "a.jsonl"),
            [("你好", "我也好")],
        )
        self.assertEqual(corpus.parse_corpus_text('["你好", "我也好"]', "a.json"), [("你好", "我也好")])

    def test_heuristic_no_extension(self):
        # 看起来像 json 数组
        self.assertEqual(corpus.parse_corpus_text('["你好", "我也好"]'), [("你好", "我也好")])
        # 纯文本按行
        self.assertEqual(corpus.parse_corpus_text("你好\n我也好"), [("你好", "我也好")])

    def test_empty(self):
        self.assertEqual(corpus.parse_corpus_text("  \n "), [])


class TestPoolManagement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pool_path = os.path.join(self.tmp.name, "pool.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_dedup(self):
        pairs = [("你好", "你也好"), ("在吗", "在呢")]
        n1 = corpus.append_pairs_to_pool(self.pool_path, pairs)
        self.assertEqual(n1, 2)
        # 重复追加：不新增
        n2 = corpus.append_pairs_to_pool(self.pool_path, pairs)
        self.assertEqual(n2, 0)
        stats = corpus.pool_stats(self.pool_path)
        self.assertEqual(stats["pairs"], 2)

    def test_append_mixed_new_dup(self):
        corpus.append_pairs_to_pool(self.pool_path, [("你好", "你也好")])
        n = corpus.append_pairs_to_pool(self.pool_path, [("你好", "你也好"), ("新的", "新的答")])
        self.assertEqual(n, 1)

    def test_read_missing_file(self):
        self.assertEqual(corpus.read_pool(os.path.join(self.tmp.name, "nope.jsonl")), [])

    def test_pool_stats_empty(self):
        stats = corpus.pool_stats(os.path.join(self.tmp.name, "nope.jsonl"))
        self.assertTrue(stats["empty"])
        self.assertEqual(stats["pairs"], 0)

    def test_corrupt_lines_skipped(self):
        with open(self.pool_path, "w", encoding="utf-8") as f:
            f.write('{"role": "user", "content": "你好"}\nnot json\n')
        rows = corpus.read_pool(self.pool_path)
        self.assertEqual(len(rows), 1)

    def test_read_pool_invalid_utf8_returns_empty(self):
        """v2.8.1：半写坏的非 UTF-8 文件读取返回空池，不抛 UnicodeDecodeError。"""
        with open(self.pool_path, "wb") as f:
            f.write(b'{"content": "\xff\xfe broken"}\n{"content": "ok"}\n')
        self.assertEqual(corpus.read_pool(self.pool_path), [])

    def test_read_pool_dir_returns_empty(self):
        """v2.8.1：路径是目录时读取返回空池，不抛 IsADirectoryError。"""
        self.assertEqual(corpus.read_pool(self.tmp.name), [])

    def test_write_pool_atomic(self):
        """v2.8.1：write_pool 原子写（temp + os.replace），不留 .tmp 残留。"""
        corpus.write_pool(
            self.pool_path,
            [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你也好"}],
        )
        self.assertFalse(os.path.exists(self.pool_path + ".tmp"))
        rows = corpus.read_pool(self.pool_path)
        self.assertEqual(len(rows), 2)


class TestSamplePool(unittest.TestCase):
    def test_sample_size(self):
        rows = [{"role": "user", "content": f"句{i}"} for i in range(100)]
        sampled = corpus.sample_pool(rows, 20)
        self.assertEqual(len(sampled), 20)

    def test_sample_reproducible(self):
        rows = [{"role": "user", "content": f"句{i}"} for i in range(100)]
        s1 = corpus.sample_pool(rows, 10, seed=42)
        s2 = corpus.sample_pool(rows, 10, seed=42)
        self.assertEqual([r["content"] for r in s1], [r["content"] for r in s2])

    def test_sample_more_than_rows(self):
        rows = [{"role": "user", "content": "句1"}, {"role": "user", "content": "句2"}]
        sampled = corpus.sample_pool(rows, 10)
        self.assertEqual(len(sampled), 2)

    def test_empty(self):
        self.assertEqual(corpus.sample_pool([], 10), [])


class TestMergePoolRows(unittest.TestCase):
    def _rows(self, contents):
        return [{"role": "user", "content": c} for c in contents]

    def test_merge_dedup(self):
        base = self._rows(["a", "b", "c"])
        user = self._rows(["b", "d", "a"])  # b/a 重复
        merged = corpus.merge_pool_rows(base, user)
        contents = [r["content"] for r in merged]
        self.assertEqual(sorted(contents), ["a", "b", "c", "d"])

    def test_merge_empty(self):
        self.assertEqual(corpus.merge_pool_rows([], []), [])
        self.assertEqual(corpus.merge_pool_rows(None, []), [])

    def test_merge_first_wins_order(self):
        base = self._rows(["a", "b"])
        user = self._rows(["b", "c"])
        merged = corpus.merge_pool_rows(base, user)
        contents = [r["content"] for r in merged]
        self.assertEqual(contents, ["a", "b", "c"])  # 先到者保留，b 不重复

    def test_merge_ignores_non_dict(self):
        merged = corpus.merge_pool_rows([{"role": "user", "content": "a"}, "junk", None])
        self.assertEqual(len(merged), 1)


class TestSampleMerged(unittest.TestCase):
    def _rows(self, contents):
        return [{"role": "user", "content": c} for c in contents]

    def test_user_first_when_enough(self):
        base = self._rows([f"b{i}" for i in range(100)])
        user = self._rows([f"u{i}" for i in range(60)])
        picked = corpus.sample_merged(base, user, 50, seed=42)
        contents = [r["content"] for r in picked]
        self.assertTrue(all(c.startswith("u") for c in contents), "用户语料够时全采用户")

    def test_base_fills_when_user_short(self):
        base = self._rows([f"b{i}" for i in range(100)])
        user = self._rows([f"u{i}" for i in range(10)])
        picked = corpus.sample_merged(base, user, 50, seed=42)
        contents = [r["content"] for r in picked]
        user_count = sum(1 for c in contents if c.startswith("u"))
        base_count = sum(1 for c in contents if c.startswith("b"))
        self.assertEqual(user_count, 10, "用户语料全采")
        self.assertEqual(base_count, 40, "不足部分用 base 补")
        self.assertEqual(len(picked), 50)

    def test_odd_n_lines_floored_to_even(self):
        base = self._rows([f"b{i}" for i in range(100)])
        user = self._rows([f"u{i}" for i in range(60)])
        picked = corpus.sample_merged(base, user, 51, seed=42)
        self.assertEqual(len(picked), 50)

    def test_n_zero_or_negative(self):
        base = self._rows(["b"])
        user = self._rows(["u"])
        self.assertEqual(corpus.sample_merged(base, user, 0), [])
        self.assertEqual(corpus.sample_merged(base, user, -3), [])

    def test_no_user_corpus(self):
        base = self._rows([f"b{i}" for i in range(20)])
        picked = corpus.sample_merged(base, [], 10, seed=42)
        self.assertEqual(len(picked), 10)
        self.assertTrue(all(r["content"].startswith("b") for r in picked))

    def test_reproducible(self):
        base = self._rows([f"b{i}" for i in range(100)])
        user = self._rows([f"u{i}" for i in range(30)])
        p1 = [r["content"] for r in corpus.sample_merged(base, user, 40, seed=7)]
        p2 = [r["content"] for r in corpus.sample_merged(base, user, 40, seed=7)]
        self.assertEqual(p1, p2)


class TestNewFiles(unittest.TestCase):
    def test_returns_only_new(self):
        self.assertEqual(corpus.new_files(["a.txt", "b.txt"], ["a.txt"]), ["b.txt"])

    def test_no_new_returns_empty(self):
        self.assertEqual(corpus.new_files(["a.txt"], ["a.txt"]), [])

    def test_all_new_first_time(self):
        self.assertEqual(corpus.new_files(["a.txt", "b.txt"], []), ["a.txt", "b.txt"])

    def test_empty_config(self):
        self.assertEqual(corpus.new_files([], ["a.txt"]), [])
        self.assertEqual(corpus.new_files(None, ["a.txt"]), [])

    def test_none_imported(self):
        self.assertEqual(corpus.new_files(["a.txt"], None), ["a.txt"])

    def test_dupes_in_config_kept(self):
        # 配置内重复文件会原样返回（导入阶段会去重，不重复落库）
        self.assertEqual(corpus.new_files(["a.txt", "a.txt"], []), ["a.txt", "a.txt"])

    def test_non_str_ignored(self):
        self.assertEqual(corpus.new_files(["a.txt", 123, None], []), ["a.txt"])


if __name__ == "__main__":
    unittest.main()
