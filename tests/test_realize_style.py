# -*- coding: utf-8 -*-
"""v4.9.7：风格实现层单元测试（不读数据库）。"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_core.realize import realize_question, realize_style, should_short_bubble

FP = {
    "sample_size": 1105,
    "ellipsis_ratio": 0.43,
    "particle_ratio": 0.47,
}


class TestRealizeStyle(unittest.TestCase):
    def test_no_fingerprint_returns_original(self):
        text = "今天有点累。"
        self.assertEqual(realize_style(text, None), text)
        self.assertEqual(realize_style(text, {"sample_size": 5}), text)

    def test_question_and_code_untouched(self):
        self.assertEqual(realize_style("你吃了吗？", FP), "你吃了吗？")
        self.assertEqual(realize_style("```\ncode\n```", FP), "```\ncode\n```")
        self.assertEqual(realize_style("看这个 https://x.test", FP), "看这个 https://x.test")

    def test_ellipsis_or_particle_only(self):
        texts = [f"今天有点累，想先躺一会儿{i}。" for i in range(40)]
        changed = [realize_style(t, FP) for t in texts if realize_style(t, FP) != t]
        self.assertGreater(len(changed), 0)
        for out in changed:
            self.assertTrue(
                out.endswith("……")
                or out.endswith("啊。")
                or out.endswith("哦。")
                or out.endswith("啦。")
                or out.endswith("呀。")
            )

    def test_idempotent(self):
        texts = [f"今天有点累{i}。" for i in range(40)]
        for t in texts:
            once = realize_style(t, FP)
            self.assertEqual(realize_style(once, FP), once)

    def test_long_text_untouched(self):
        text = "今天" + "很累" * 40 + "。"
        self.assertEqual(realize_style(text, FP), text)

    def test_ellipsis_can_follow_particle(self):
        """v4.9.9：句中已有语气词时仍可能得到省略号（两者常共现）。"""
        texts = [f"啊，今天有点累{i}。" for i in range(80)]
        changed = [realize_style(t, FP) for t in texts if realize_style(t, FP) != t]
        self.assertTrue(changed)
        self.assertTrue(any(out.endswith("……") for out in changed))

    def test_no_particle_after_existing_final_particle(self):
        """v4.11.1：句尾已有「吧/吗/呀…」时不能再补，否则出现「吧哦」。"""
        for ending in ("吧", "吗", "呀", "哦", "啦", "嘛", "哈"):
            for i in range(40):
                text = f"那就这样{ending}{i}。"
                out = realize_style(text, FP)
                for suffix in ("啊", "哦", "啦", "呀"):
                    self.assertFalse(out.endswith(ending + suffix + "。"), out)

    def test_question_suffix_fraction(self):
        """v4.9.13：少量陈述句末尾补反问，问句占比可达目标。"""
        fp = dict(FP, question_ratio=0.22)
        texts = [f"今天有点累，想先躺一会儿{i}。" for i in range(120)]
        outs = [realize_question(t, fp) for t in texts]
        changed = [o for t, o in zip(texts, outs) if o != t]
        self.assertTrue(changed)
        self.assertTrue(all(o.endswith("？") for o in changed))
        self.assertEqual(realize_question(changed[0], fp), changed[0])

    def test_question_skips_code_and_question(self):
        self.assertEqual(realize_question("你说呢？", FP), "你说呢？")
        self.assertEqual(realize_question("```x```。", FP), "```x```。")
        self.assertEqual(realize_question("看 https://a.b。", FP), "看 https://a.b。")

    def test_short_bubble_budget(self):
        """v4.9.11：少量 13–30 字回复会被选中拆成短气泡。"""
        fp = {"sample_size": 1105, "short_ratio": 0.16}
        texts = [f"今天有点累，想先躺一会儿{i}。" for i in range(120)]
        picked = [t for t in texts if should_short_bubble(t, fp)]
        self.assertTrue(picked)
        self.assertLess(len(picked), len(texts) // 2)
        self.assertFalse(should_short_bubble("好。", fp))
        self.assertFalse(should_short_bubble("这是一段超过三十个字的回复，用来确认不会被短气泡逻辑错误地切分掉。", fp))

    def test_short_bubble_split_keeps_content(self):
        from humanizer_core.send_pipeline import split_plan

        text = "今天有点累，想先躺一会儿。"
        bubbles = split_plan(text, enabled=True, threshold=12, max_segments=2, min_part=4)
        self.assertIsNotNone(bubbles)
        self.assertGreaterEqual(len(bubbles), 2)
        self.assertEqual("".join(bubbles), text)

    def test_custom_low_targets_untouched(self):
        fp = {"sample_size": 100, "ellipsis_ratio": 0.05, "particle_ratio": 0.05}
        self.assertEqual(realize_style("今天有点累。", fp), "今天有点累。")

    def test_hook_runs_before_humanize_guard(self):
        """接线契约：风格实现必须在 humanize 总开关判断之前，否则 live 关了去痕就不生效。"""
        source = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        start = source.index("async def humanize_response")
        end = source.index("async def ", start + 10)
        block = source[start:end]
        self.assertIn("_realize_style_text(text)", block)
        self.assertIn("resp.completion_text = realized", block)
        self.assertLess(
            block.index("_realize_style_text(text)"),
            block.index('if not self._h("enabled", True)'),
        )

    def test_runtime_does_not_apply_mechanical_style(self):
        """v4.11.2：运行时不得再调用 realize_style（不补语气词/省略号）。"""
        source = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        start = source.index("def _realize_style_text")
        end = source.index("async def _produce_style_text", start)
        block = source[start:end]
        self.assertNotIn("from style_core.realize", block)
        self.assertNotIn("realize_style(text", block)

    def test_runtime_does_not_force_short_bubble_split(self):
        """v4.12.1：运行时不得再按概率强制拆 13–30 字短气泡。"""
        source = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("should_short_bubble", source)


if __name__ == "__main__":
    unittest.main()
