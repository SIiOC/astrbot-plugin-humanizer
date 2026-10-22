# -*- coding: utf-8 -*-
"""
问题清单回归测试（对应《问题.txt》12 条，覆盖已修复项 + 本次修复项）。

运行：python -m pytest tests/ -v
"""

import sys
import unittest
from pathlib import Path

# 确保插件根目录在 sys.path，与 main.py 的加载方式一致
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core import (
    detect_language,
    humanize_text,
    humanize_text_detailed,
    is_blank,
)
from humanizer_core import rules_en, rules_zh


class TestWhitespaceStructure(unittest.TestCase):
    """#1 空白折叠不误伤换行 / Markdown 结构。"""

    def test_zh_newlines_collapsed_but_kept(self):
        # 3+ 连续换行收敛为 2 个，但不会压成单行
        self.assertEqual(humanize_text("第一段。\n\n\n第二段。"), "第一段。\n\n第二段。")

    def test_en_newlines_kept(self):
        self.assertEqual(humanize_text("line1\nline2\nline3"), "line1\nline2\nline3")

    def test_md_table_kept(self):
        table = "| a | b |\n|---|---|\n| 1 | 2 |"
        self.assertEqual(humanize_text(table), table)

    def test_code_block_kept(self):
        code = "```python\ndef f():\n    return 1\n```"
        self.assertEqual(humanize_text(code), code)


class TestChineseDashes(unittest.TestCase):
    """#2 中文破折号：数字区间保留，插入式才收敛。"""

    def test_single_range_kept(self):
        self.assertEqual(humanize_text("从2020——2026年增长明显。"), "从2020——2026年增长明显。")

    def test_multi_ranges_kept(self):
        # 修复前：多区间被当成高频插入式破折号替换成逗号
        self.assertEqual(
            humanize_text("从2020——2025年，再到2030——2035年。"),
            "从2020——2025年，再到2030——2035年。",
        )

    def test_num_unit_range_kept(self):
        self.assertEqual(humanize_text("预计5——10人参加。"), "预计5——10人参加。")

    def test_insertion_dashes_converted(self):
        self.assertEqual(
            humanize_text("它很快——也很稳——但我们还是放弃了。"),
            "它很快，也很稳，但我们还是放弃了。",
        )

    def test_sound_extension_kept(self):
        self.assertEqual(humanize_text("啊——太好了"), "啊——太好了")


class TestEnglishDashes(unittest.TestCase):
    """#3 en-dash 数字区间保留，em-dash 才替换。"""

    def test_en_dash_range_kept(self):
        self.assertEqual(humanize_text("The years 2020–2026 saw growth."), "The years 2020–2026 saw growth.")

    def test_em_dash_replaced(self):
        self.assertEqual(humanize_text("It was fast — but also risky."), "It was fast, but also risky.")

    def test_chinese_dash_not_touched_by_en_rules(self):
        # 语言误判防护：中文破折号即使走英文规则也不被破坏
        self.assertEqual(humanize_text("从2020——2026年增长明显。"), "从2020——2026年增长明显。")


class TestDisclaimers(unittest.TestCase):
    """#4 免责声明：正常句子不误删，免责句只删声明部分。"""

    def test_plain_knowledge_sentence_kept(self):
        self.assertEqual(humanize_text("根据我的知识，太阳从东边升起。"), "根据我的知识，太阳从东边升起。")

    def test_disclaimer_tail_kept(self):
        # 修复前："因此无法回答" 被吞掉只剩 "答。"
        self.assertEqual(humanize_text("我的知识截止日期是2024年10月，因此无法回答。"), "因此无法回答。")

    def test_parenthesized_date_removed(self):
        self.assertEqual(humanize_text("根据我的知识截止日期（2024年10月），我无法确认。"), "我无法确认。")

    def test_limited_knowledge_removed(self):
        self.assertEqual(humanize_text("由于我的知识有限，无法回答这个问题。"), "无法回答这个问题。")


class TestEnglishAdverbs(unittest.TestCase):
    """#6 英文副词删除副作用。"""

    def test_simply_put_whole_phrase_removed(self):
        # 修复前：只删副词残留大写 "Put,"
        self.assertEqual(humanize_text("Simply put, this works."), "this works.")

    def test_simply_put_fullwidth_colon(self):
        self.assertEqual(humanize_text("Simply put：this works."), "this works.")

    def test_sentence_start_adverb_capitalized(self):
        self.assertEqual(humanize_text("Fundamentally, the plan is sound."), "The plan is sound.")

    def test_mid_sentence_adverb_removed(self):
        self.assertEqual(humanize_text("This is literally the best."), "This is the best.")

    def test_meaningful_adverbs_kept(self):
        # truly/deeply/honestly/genuinely 等有实义的词不删
        for t in [
            "I am truly sorry for that.",
            "I deeply care about this.",
            "Honestly, I think this is fine.",
            "She is genuinely interested.",
        ]:
            self.assertEqual(humanize_text(t), t)


class TestLanguageDetection(unittest.TestCase):
    """#7 语言检测：数字/标点不稀释比例，混排与纯英文正确判型。"""

    def test_mixed_with_punctuation(self):
        # 修复前：逗号稀释 CJK 比例误判为英文，中文规则不生效
        self.assertEqual(detect_language("你好，world!"), "zh")

    def test_mixed_with_numbers(self):
        # 修复前：数字稀释比例，"从2020——2026" 被判成英文
        self.assertEqual(detect_language("从2020——2026年"), "zh")

    def test_pure_english(self):
        self.assertEqual(detect_language("Just a normal English sentence here."), "en")

    def test_cjk_word_in_english(self):
        # 单汉字不算中文文本
        self.assertEqual(detect_language("I love 猫"), "en")

    def test_empty(self):
        self.assertEqual(detect_language(""), "en")


class TestHits(unittest.TestCase):
    """#10 命中阶段日志信息可用。"""

    def test_hits_reported(self):
        text = "您好！值得注意的是，希望这对您有帮助。"
        cleaned, hits = humanize_text_detailed(text)
        self.assertNotEqual(cleaned, text)
        self.assertTrue(hits)

    def test_no_change_no_hits(self):
        text = "今天天气不错。"
        cleaned, hits = humanize_text_detailed(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(hits, [])


class TestGuards(unittest.TestCase):
    """整段删空防御。"""

    def test_zh_not_emptied(self):
        self.assertEqual(humanize_text("好的呢"), "好的呢")

    def test_en_not_emptied(self):
        self.assertEqual(humanize_text("Thanks!"), "Thanks!")


class TestBugFixes(unittest.TestCase):
    """本次修复的两个 bug 回归用例。"""

    def test_courtesy_ending_keeps_previous_sentence_period(self):
        # Bug1 修复前：结尾客套规则前缀匹配句号+换行，把前一句的「。」一并吞掉
        self.assertEqual(humanize_text("方案可行。\n希望这对您有帮助！"), "方案可行。")

    def test_neg_contrast_keeps_second_half(self):
        # Bug2 修复前：整句被删空，触发防御返回原文，规则不生效
        self.assertEqual(humanize_text("不只是工具，更是伙伴。"), "更是伙伴。")


class TestBlankGuard(unittest.TestCase):
    """需求2：空白输入防御，改写链路禁止无中生有。"""

    def test_is_blank_variants(self):
        self.assertTrue(is_blank(None))
        self.assertTrue(is_blank(""))
        self.assertTrue(is_blank("   "))
        self.assertTrue(is_blank("\t\n "))

    def test_non_blank_text(self):
        self.assertFalse(is_blank("你好"))
        self.assertFalse(is_blank(" 你好 "))

    def test_blank_reply_produces_no_new_text(self):
        # 验收用例2：正常用户消息 + 空/纯空白回复 → 原样返回空，不产生任何新文本。
        # 钩子层由 is_blank 直接放行；即使漏进规则管线，空白也原样返回
        self.assertEqual(humanize_text(""), "")
        self.assertEqual(humanize_text("   "), "   ")
        self.assertEqual(humanize_text("\t\n "), "\t\n ")

    def test_normal_reply_pipeline_still_works(self):
        # 验收用例3：正常用户消息 + 正常回复 → 清理照常生效
        cleaned, hits = humanize_text_detailed("您好！值得注意的是，希望这对您有帮助。")
        self.assertNotEqual(cleaned, "您好！值得注意的是，希望这对您有帮助。")
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()
