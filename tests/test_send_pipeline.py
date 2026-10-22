# -*- coding: utf-8 -*-
"""v4.0 Phase 7：发送前决策纯函数（humanizer_core.send_pipeline）。

从 main._typing_delay_before_send 下沉的三类判定：语音纯语音抑制、
复读拦截、用户延迟区间裁剪（顺序契约）。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import send_pipeline as sp


class TestVoiceOnlySent(unittest.TestCase):
    def test_record_key_detected(self):
        self.assertTrue(sp.voice_only_sent(["record:/a/b.mp3"]))
        self.assertTrue(sp.voice_only_sent(["text:x", "record:/a.wav"]))

    def test_no_record_key(self):
        self.assertFalse(sp.voice_only_sent(["text:x", "image:y"]))
        self.assertFalse(sp.voice_only_sent([]))

    def test_non_list_or_bad_items(self):
        self.assertFalse(sp.voice_only_sent(None))
        self.assertFalse(sp.voice_only_sent("record:x"))
        self.assertFalse(sp.voice_only_sent([123, None]))
        # 非字符串元素不炸
        self.assertFalse(sp.voice_only_sent([1, 2, {}]))


class TestDedupeHit(unittest.TestCase):
    def test_identical_above_threshold(self):
        score = sp.dedupe_hit("今天天气真不错啊", ["今天天气真不错啊"], 0.82)
        self.assertGreater(score, 0.0)

    def test_different_below_threshold(self):
        self.assertEqual(
            sp.dedupe_hit("今天天气真不错啊", ["完全不同的一句话内容"], 0.82), 0.0
        )

    def test_empty_candidates_zero(self):
        self.assertEqual(sp.dedupe_hit("x", [], 0.82), 0.0)
        self.assertEqual(sp.dedupe_hit("x", None, 0.82), 0.0)

    def test_blank_text_zero(self):
        self.assertEqual(sp.dedupe_hit("   ", ["x"], 0.82), 0.0)


class TestResolveDelayBounds(unittest.TestCase):
    def test_swap_when_min_gt_max(self):
        # min=30 max=10 → 互换后夹到 [10,30]；delay 50 → 先裁 10 → 再抬 30
        self.assertEqual(sp.resolve_delay_bounds(50.0, 30.0, 10.0, 90.0), 30.0)

    def test_max_clip(self):
        self.assertEqual(sp.resolve_delay_bounds(50.0, 0.0, 20.0, 90.0), 20.0)

    def test_min_lift(self):
        self.assertEqual(sp.resolve_delay_bounds(3.0, 10.0, 0.0, 90.0), 10.0)

    def test_total_cap(self):
        self.assertEqual(sp.resolve_delay_bounds(200.0, 0.0, 0.0, 90.0), 90.0)

    def test_zero_means_unlimited(self):
        self.assertEqual(sp.resolve_delay_bounds(40.0, 0.0, 0.0, 90.0), 40.0)

    def test_order_swap_before_clip(self):
        # 顺序契约实证：若先裁剪（delay 50 裁到 max=10）再互换（min30→max10，
        # 结果 10）与先互换（10/30）再裁剪结果应为 30。断言先互换。
        self.assertEqual(sp.resolve_delay_bounds(50.0, 30.0, 10.0, 90.0), 30.0)

    def test_never_negative(self):
        self.assertEqual(sp.resolve_delay_bounds(-5.0, 0.0, 0.0, 90.0), 0.0)

    def test_cap_zero_clamps_to_zero(self):
        self.assertEqual(sp.resolve_delay_bounds(40.0, 0.0, 0.0, 0.0), 0.0)


class TestSplitPlan(unittest.TestCase):
    def test_disabled_returns_none(self):
        long_text = "字" * 500
        self.assertIsNone(sp.split_plan(long_text, enabled=False))

    def test_short_text_no_split(self):
        self.assertIsNone(sp.split_plan("好的", enabled=True, threshold=40))

    def test_long_text_splits(self):
        text = "第一句话在这里。第二句话也在这里。第三句话还在这里。"
        plan = sp.split_plan(
            text, enabled=True, threshold=10, max_segments=3, min_part=4
        )
        self.assertIsNotNone(plan)
        self.assertGreater(len(plan), 1)
        self.assertEqual("".join(plan), text, "拆分不得丢字")

    def test_empty_text_none(self):
        self.assertIsNone(sp.split_plan("   ", enabled=True))


class TestBackfill(unittest.TestCase):
    def test_no_failure_empty(self):
        self.assertEqual(sp.backfill_bubbles(["a", "b"], None), [])

    def test_from_failed_index_inclusive(self):
        self.assertEqual(sp.backfill_bubbles(["a", "b", "c"], 1), ["b", "c"])

    def test_index_zero_returns_all(self):
        self.assertEqual(sp.backfill_bubbles(["a", "b"], 0), ["a", "b"])

    def test_negative_clamps_zero(self):
        self.assertEqual(sp.backfill_bubbles(["a", "b"], -3), ["a", "b"])

    def test_bad_index_empty(self):
        self.assertEqual(sp.backfill_bubbles(["a"], "x"), [])


if __name__ == "__main__":
    unittest.main()
