# -*- coding: utf-8 -*-
"""v4.9.4：风格指纹（用户语料 → 数字约束）单元测试。"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_core import inject
from style_core.fingerprint import (
    MIN_SAMPLE,
    collect_user_texts,
    compute_fingerprint,
    exemplar_prompt,
    fingerprint_prompt,
    select_exemplars,
)


def _texts(n=40):
    return ["嗯嗯……今天好累啊" for _ in range(n)]


class TestFingerprint(unittest.TestCase):
    def test_empty_returns_zero(self):
        fp = compute_fingerprint([])
        self.assertEqual(fp["sample_size"], 0)
        self.assertEqual(fingerprint_prompt(fp), "")

    def test_too_few_samples_no_prompt(self):
        fp = compute_fingerprint(_texts(MIN_SAMPLE - 1))
        self.assertEqual(fp["sample_size"], MIN_SAMPLE - 1)
        self.assertEqual(fingerprint_prompt(fp), "")

    def test_stats_are_computed(self):
        texts = ["嗯。"] * 10 + ["今天真的好累啊……不想动了，想躺一会儿。"] * 10
        fp = compute_fingerprint(texts)
        self.assertEqual(fp["sample_size"], 20)
        self.assertGreater(fp["avg_chars"], 0)
        self.assertGreater(fp["question_ratio"], 0) if any("？" in t for t in texts) else None
        self.assertGreater(fp["ellipsis_ratio"], 0)
        self.assertIn("嗯", fp["top_particles"])

    def test_prompt_uses_numbers(self):
        fp = compute_fingerprint(_texts(40))
        prompt = fingerprint_prompt(fp)
        self.assertIn("真实说话数据", prompt)
        self.assertIn("40 条", prompt)
        self.assertIn("平均", prompt)
        self.assertIn("语气词", prompt)

    def test_collect_filters_assistant(self):
        rows = [
            {"role": "user", "content": "用户一句"},
            {"role": "assistant", "content": "助手一句"},
            {"role": "user", "content": "用户二句"},
        ]
        self.assertEqual(collect_user_texts(rows), ["用户一句", "用户二句"])

    def test_collect_falls_back_to_content(self):
        self.assertEqual(collect_user_texts([{"content": "无角色"}]), ["无角色"])

    def test_style_section_includes_fingerprint(self):
        fp = compute_fingerprint(_texts(40))
        sec = inject.build_style_section(
            {"name": "风", "persona": "像朋友"}, fingerprint=fp
        )
        self.assertIn("真实说话数据", sec)
        self.assertIn("发送前自检", sec)

    def test_style_section_without_fingerprint_ok(self):
        sec = inject.build_style_section({"name": "风", "persona": "像朋友"})
        self.assertNotIn("真实说话数据", sec)

    def test_fingerprint_alone_can_inject(self):
        """没有风格档案、只有语料指纹时也应注入（数据本身有价值）。"""
        fp = compute_fingerprint(_texts(40))
        sec = inject.build_style_section({"name": "空风"}, fingerprint=fp)
        self.assertIn("真实说话数据", sec)
        self.assertIn(inject.SECTION_FOOTER, sec)

    def test_exemplars_are_selected(self):
        texts = ["嗯"] + ["今天好累啊……"] * 5 + ["其实我昨天也没怎么睡好，今天整个人都是飘的，下午还要开会。"] * 2
        fp = compute_fingerprint(texts)
        ex = select_exemplars(texts, fp)
        self.assertGreaterEqual(len(ex), 1)
        self.assertLessEqual(len(ex), 3)
        self.assertTrue(all(len(x) <= 80 for x in ex))

    def test_exemplars_include_ellipsis_when_available(self):
        texts = [
            "今天好累啊……",
            "其实我昨天也没睡好……",
            "有点想你了……",
            "普通一句话",
            "嗯",
        ]
        fp = compute_fingerprint(texts)
        ex = select_exemplars(texts, fp)
        self.assertGreaterEqual(sum(1 for x in ex if "……" in x or "..." in x), 2)

    def test_exemplars_prefer_style_signal(self):
        texts = ["普通一句话"] * 10 + ["今天好累啊……"] * 10
        fp = compute_fingerprint(texts)
        ex = select_exemplars(texts, fp)
        self.assertTrue(any(("……" in x) or ("啊" in x) for x in ex))

    def test_prompt_has_hard_style_quotas(self):
        prompt = fingerprint_prompt(compute_fingerprint(_texts(40)))
        self.assertIn("硬性表达习惯", prompt)
        self.assertIn("每 3 条回复至少 1 条少于 10 字", prompt)
        self.assertIn("每 2 条至少 1 条带语气词", prompt)
        self.assertIn("每 2–3 条至少 1 条用「……」", prompt)

    def test_exemplar_prompt_rendered(self):
        prompt = exemplar_prompt(["嗯", "今天好累啊……"])
        self.assertIn("语气锚点", prompt)
        self.assertIn("模仿节奏", prompt)

    def test_style_section_includes_exemplars(self):
        sec = inject.build_style_section(
            {"name": "风", "persona": "像朋友"},
            fingerprint=compute_fingerprint(_texts(40)),
            exemplars=["嗯", "今天好累啊……"],
        )
        self.assertIn("语气锚点", sec)
        self.assertIn("今天好累啊", sec)

    def test_main_passes_fingerprint_and_exemplars(self):
        """接线契约：风格注入必须真的把指纹/锚点传给 build_style_section。"""
        source = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("fingerprint=self._style_fingerprint()", source)
        self.assertIn("exemplars=self._style_exemplars()", source)
        self.assertIn("_style_fp_cache = (mtime, fp, exemplars)", source)


if __name__ == "__main__":
    unittest.main()
