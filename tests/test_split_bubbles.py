# -*- coding: utf-8 -*-
"""v3.6.0 分段发送纯函数测试（humanizer_core.typing.split_reply_bubbles）。

零 astrbot 依赖。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import typing as ht


class TestSplitReplyBubbles(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ht.split_reply_bubbles(""), [])
        self.assertEqual(ht.split_reply_bubbles("   "), [])

    def test_short_text_single(self):
        self.assertEqual(ht.split_reply_bubbles("好的，明天见"), ["好的，明天见"])

    def test_content_preserved(self):
        """所有段拼回与原文一致（仅去首尾空白）——不丢字不造字。"""
        texts = [
            "今天去了趟图书馆，看了一下午书。累死了但很充实。顺便还借了两本书，一本小说一本散文集，下周应该够看了。",
            "嗯嗯。今天在图书馆坐了一整天，腰都直不起来了，晚上回来还想再看看那本书，结果看着看着就睡着了，醒来已经十一点了。",
            "我跟你讲今天发生了一件特别特别离谱的事情，我到现在都还没缓过来，真的，我都不知从何说起啊",
        ]
        for t in texts:
            out = ht.split_reply_bubbles(t)
            self.assertGreaterEqual(len(out), 1)
            self.assertEqual("".join(out), "".join(t.split()), t)
            for b in out:
                self.assertTrue(b.strip(), t)

    def test_sentence_split_multi(self):
        t = "今天去了趟图书馆，看了一下午书。累死了但是很充实。晚上回来还写了会儿笔记，今天早点睡！"
        out = ht.split_reply_bubbles(t)
        self.assertGreaterEqual(len(out), 2)
        self.assertTrue(out[0].endswith("。") or out[0].endswith("！"))

    def test_short_piece_not_alone_in_middle_or_tail(self):
        # 「看书。」（3 字 < min_part 8）应并入相邻段，不单独成段
        t = "今天去了趟图书馆看了很多书做了笔记还借了两本。看书。累死了但很充实，躺下就睡着了。"
        out = ht.split_reply_bubbles(t)
        self.assertGreaterEqual(len(out), 2)
        for b in out[1:]:
            self.assertGreaterEqual(len(b), ht.SPLIT_MIN_PART, out)

    def test_no_sentence_end_falls_back_to_comma(self):
        # 无句末标点的长句在逗号处兜底切
        t = "我跟你讲今天发生了一件特别特别离谱的事情，我到现在都还没缓过来，真的，我都不知从何说起啊"
        out = ht.split_reply_bubbles(t)
        self.assertGreaterEqual(len(out), 2)
        self.assertEqual("".join(out), t)

    def test_no_marks_at_all_hard_cut(self):
        # 连逗号都没有的超长句按长度硬切，内容仍守恒
        t = "版本号升级到了3.5.2然后又顺手修了几个小问题稳定性也提高了不少性能也比之前好了一些你记得更新一下试试看效果"
        out = ht.split_reply_bubbles(t)
        self.assertGreaterEqual(len(out), 2)
        self.assertEqual("".join(out), t)
        self.assertTrue(any("3.5.2" in b for b in out), out)

    def test_english_dot_not_a_sentence_end(self):
        # 英文句点不是句末切点：含小数点的文本不被切碎
        t = "版本号升级到了3.5.2然后又顺手修了几个小问题稳定性也提高了不少，性能也比之前好了一些你记得更新一下试试看效果"
        out = ht.split_reply_bubbles(t)
        self.assertTrue(any("3.5.2" in b for b in out), out)

    def test_closing_quote_stays_with_period(self):
        # 句末标点后的引号/括号闭合归属前句，不出现在段首
        t = "她说「今天真的好累啊。」然后就回去睡了，我猜她现在应该已经到家了吧，希望她好好休息。"
        out = ht.split_reply_bubbles(t)
        self.assertGreaterEqual(len(out), 2)
        for b in out:
            self.assertFalse(b.startswith("」"), out)

    def test_max_segments_cap(self):
        t = "第一句话在这里。第二句话在这里。第三句话在这里。第四句话在这里。第五句话在这里。"
        out = ht.split_reply_bubbles(t, max_segments=3)
        self.assertLessEqual(len(out), 3)
        self.assertEqual("".join(out), t.replace(" ", ""))

    def test_threshold_respected(self):
        t = "今天去了趟图书馆。看书。累死了但很充实。"
        self.assertEqual(len(ht.split_reply_bubbles(t, threshold=1000)), 1)

    def test_min_part_larger_than_threshold_clamped(self):
        # min_part > threshold 自动钳制，不出空结果、内容守恒
        t = "第一句话在这里。第二句话在这里。第三句话在这里。第四句话在这里。"
        out = ht.split_reply_bubbles(t, threshold=10, min_part=50)
        self.assertTrue(out)
        self.assertEqual("".join(out), t.replace(" ", ""))

    def test_deterministic(self):
        t = "今天去了趟图书馆，看了一下午书。累死了但很充实。晚上早点睡！"
        self.assertEqual(ht.split_reply_bubbles(t), ht.split_reply_bubbles(t))


if __name__ == "__main__":
    unittest.main()


class TestSplitExtremeThreshold(unittest.TestCase):
    """2026-09-07 审查修复守护：threshold=1（含配置 0/负被钳到 1）曾是死循环。

    修复前：threshold=1 时 `cut < threshold//2` 即 `0 < 0` 恒 False，
    window 无切点标记时 cut=0 空切不前进，纯 CPU 死循环卡死事件循环
    （实测复现）。修复后 cut<=0 也走硬切，每轮至少前进 1 字符。
    """

    def test_threshold_one_terminates(self):
        t = "你好世界" * 10
        out = ht.split_reply_bubbles(t, threshold=1)
        self.assertTrue(all(out))
        self.assertEqual("".join(out), "".join(t.split()))

    def test_threshold_one_with_marks_terminates(self):
        t = "你，好，世，界，再，来，一，遍" * 3
        out = ht.split_reply_bubbles(t, threshold=1)
        self.assertTrue(all(out))
        self.assertEqual("".join(out), "".join(t.split()))

    def test_threshold_zero_negative_clamped_not_loop(self):
        # 0/负 → max(1, ...) 钳到 1 → 不再死循环
        self.assertTrue(ht.split_reply_bubbles("无标点长句" * 12, threshold=0))
        self.assertTrue(ht.split_reply_bubbles("无标点长句" * 12, threshold=-3))

    def test_threshold_two_still_correct(self):
        out = ht.split_reply_bubbles("今天天气很好，出去走走吧。", threshold=2, max_segments=5)
        self.assertEqual("".join(out), "今天天气很好，出去走走吧。")
