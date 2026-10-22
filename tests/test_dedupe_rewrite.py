# -*- coding: utf-8 -*-
"""复读拦截（dedupe）单元测试 + 接线契约测试。

背景（2026-09-06 日志实证，当天 5 对样本）：agent 模式下模型调
send_message_to_user 发送后，续轮又生成内容几乎相同的「最终回复」被
RespondStage 再发一遍，QQ 侧收到两条复读。框架 respond 原生防护是
strip 后逐字相等，差一个尾句号就漏（当天 3/5 对属此类）。

三部分：
1. 纯函数（humanizer_core.dedupe）——真实日志样本做正例/反例；
2. main.py 接线契约（AST，不 import main.py，本机无 astrbot 包）；
3. 框架补丁在位自检——v20260831 登记 + respond 原生防护/空链跳过，
   防 AstrBot 升级静默冲掉补丁后拦截静默失效（dashboard CSS 补丁先例）。
"""

import ast
import os
import sys
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse_main, find_func as _find_func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import dedupe
from humanizer_core.dedupe import MIN_NORM_LEN, match_sent_text, normalize

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN = os.path.join(_PLUGIN_ROOT, "main.py")
_ASTRBOT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_PLUGIN_ROOT)))
_MESSAGE_TOOLS = os.path.join(
    _ASTRBOT_ROOT, "astrbot", "core", "tools", "message_tools.py"
)
_RESPOND_STAGE = os.path.join(
    _ASTRBOT_ROOT, "astrbot", "core", "pipeline", "respond", "stage.py"
)

_DEFAULT_THRESHOLD = 0.82

# ---- 真实日志样本（2026-09-06 提取，见 astrbot.log 当天 Prepare to send
#      与「使用工具：send_message_to_user，参数」行）----

# 案例1/2：同文+尾句号（框架原生逐字匹配漏，归一化后完全相同）
SENT_TUPIAN = "三张参考图的效果，你看看脸自然了没"
RESP_TUPIAN = "三张参考图的效果，你看看脸自然了没。"

SENT_QUBA = "去吧去吧，吃完记得报备就行"
RESP_QUBA = "去吧去吧，吃完记得报备就行。"

# 案例3：同文+句中多一个空格
SENT_ZHUJIAOFAN = (
    "不撑就对了嘛，猪脚饭也没那么罪恶。拼豆等室友一起呗，"
    "省点是点，反正你上次拼的那些又不会跑。"
)
RESP_ZHUJIAOFAN = (
    "不撑就对了嘛，猪脚饭也没那么罪恶。 拼豆等室友一起呗，"
    "省点是点，反正你上次拼的那些又不会跑。"
)

# 案例4（反例）：强改写有增量（冰美式梗为新信息），字面相似度极低，
# 设计上放行——拦截的是复读，不是同话题的第二条补充。
SENT_RUxing = "诶不错嘛，以后早八课有救了，瑞幸9.9安排上。"
RESP_RUxing = "嘿嘿是吧～早八人的精神支柱，9块9的冰美式直接安排！"

# 案例5（反例）：分段发送后 respond 输出的是英文图片说明，非复读
SENT_SEG1 = "行啊，拿性感自拍换你修bug，这买卖不亏。等着。"
SENT_SEG2 = "黑色蕾丝吊带睡裙，够性感了吧。现在该你了，去修bug！"
RESP_ENGLISH = (
    "Done and sent it — it's a pic of the girl in that black lace cami "
    "dress with purple-highlighted hair, dorm room background, warm "
    "lighting. Now remember that bug fix you mentioned."
)


class TestNormalize(unittest.TestCase):
    def test_strips_punct_space_emoji_keeps_cjk(self):
        self.assertEqual(normalize("去吧去吧，吃完记得报备就行。"), "去吧去吧吃完记得报备就行")
        self.assertEqual(normalize("罪恶。 拼"), "罪恶拼")
        self.assertEqual(normalize("来个猪脚饭😡"), "来个猪脚饭")
        self.assertEqual(normalize("OK！ Go_1"), "okgo1")

    def test_empty(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize(None), "")


class TestMatchSentTextRealSamples(unittest.TestCase):
    def test_case1_same_text_trailing_period_hits(self):
        score = match_sent_text(RESP_TUPIAN, [SENT_TUPIAN], _DEFAULT_THRESHOLD)
        self.assertGreaterEqual(score, 0.99)

    def test_case2_quba_trailing_period_hits(self):
        score = match_sent_text(RESP_QUBA, [SENT_QUBA], _DEFAULT_THRESHOLD)
        self.assertGreaterEqual(score, 0.99)

    def test_case3_inner_space_hits(self):
        score = match_sent_text(RESP_ZHUJIAOFAN, [SENT_ZHUJIAOFAN], _DEFAULT_THRESHOLD)
        self.assertGreaterEqual(score, 0.99)

    def test_case4_paraphrase_with_increment_passes(self):
        """强改写有增量：设计上放行（有新信息，非复读）。"""
        self.assertEqual(
            match_sent_text(RESP_RUxing, [SENT_RUxing], _DEFAULT_THRESHOLD), 0.0
        )

    def test_case5_english_summary_after_segs_passes(self):
        self.assertEqual(
            match_sent_text(
                RESP_ENGLISH, [SENT_SEG1, SENT_SEG2], _DEFAULT_THRESHOLD
            ),
            0.0,
        )

    def test_one_char_rewrite_of_short_line_hits(self):
        """一字之差改写（12 字短句，ratio≈0.83）在 0.82 阈值下命中。"""
        sent = "去吧去吧，吃完记得报备就行"
        resp = "去吧去吧，吃完记得汇报就行。"  # 报→汇
        score = match_sent_text(resp, [sent], _DEFAULT_THRESHOLD)
        self.assertGreaterEqual(score, _DEFAULT_THRESHOLD)


class TestMatchSentTextEdges(unittest.TestCase):
    def test_too_short_not_judged(self):
        self.assertEqual(match_sent_text("好呀", ["好呀", "好呀宝"], 0.82), 0.0)
        self.assertEqual(
            match_sent_text("好" * (MIN_NORM_LEN - 1), ["好" * MIN_NORM_LEN], 0.82),
            0.0,
        )

    def test_empty_sent_list(self):
        self.assertEqual(match_sent_text(RESP_QUBA, [], 0.82), 0.0)
        self.assertEqual(match_sent_text(RESP_QUBA, None, 0.82), 0.0)
        self.assertEqual(match_sent_text(RESP_QUBA, ["", "  "], 0.82), 0.0)

    def test_empty_text(self):
        self.assertEqual(match_sent_text("", [SENT_QUBA], 0.82), 0.0)

    def test_concatenated_resend_hits(self):
        """分段发送后把全文拼着重发：拼接判定命中。"""
        resp = SENT_SEG1 + SENT_SEG2
        score = match_sent_text(resp, [SENT_SEG1, SENT_SEG2], _DEFAULT_THRESHOLD)
        self.assertGreaterEqual(score, 0.99)

    def test_rewrite_plus_append_hits(self):
        """改写+追加型：待发文本包含已发全文 → 命中。"""
        resp = SENT_QUBA + "，路上买杯冰美式。"
        score = match_sent_text(resp, [SENT_QUBA], _DEFAULT_THRESHOLD)
        self.assertGreaterEqual(score, 0.99)

    def test_pure_expansion_passes(self):
        """respond 是大量新内容、仅开头呼应已发短句 → 放行。"""
        sent = "去吃吧"
        resp = "去吃吧。对了，明天早上我有个会要开，可能起得早，你到时候别发消息吵我，我怕睡过头，闹钟定了三个呢。"
        self.assertEqual(match_sent_text(resp, [sent], _DEFAULT_THRESHOLD), 0.0)

    def test_unrelated_text_passes(self):
        self.assertEqual(
            match_sent_text("今天天气不错", [SENT_QUBA], _DEFAULT_THRESHOLD), 0.0
        )

    def test_long_text_autojunk_off(self):
        """autojunk=False：>200 字符的同文复读仍命中（默认值会失真）。"""
        sent = "这是一段比较长的测试文本，" * 25  # ~300 字
        resp = sent + "。"  # 原文+尾句号
        score = match_sent_text(resp, [sent], _DEFAULT_THRESHOLD)
        self.assertGreaterEqual(score, 0.99)

    def test_threshold_semantics(self):
        """达到阈值返回分数，未达到返回 0——分数透传给日志。

        用同长度差一字的用例（ratio=0.9，不触发包含判定），只走
        单条相似判定路径。
        """
        sent = "一二三四五六七八九十"
        resp = "一二三四五六七八九啊"
        self.assertEqual(match_sent_text(resp, [sent], 0.99), 0.0)
        self.assertGreater(match_sent_text(resp, [sent], 0.80), 0.80)


# ---- main.py 接线契约（AST，不 import main.py）----


class TestMainWiring(unittest.TestCase):
    _SEND_PIPELINE = os.path.join(_PLUGIN_ROOT, "humanizer_core", "send_pipeline.py")

    def test_import_exists(self):
        """v4.0 Phase 7：判定下沉 send_pipeline，导入点随之迁移（可达即通过）。"""
        with open(self._SEND_PIPELINE, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("from humanizer_core.dedupe import match_sent_text", src)

    def test_hook_reads_framework_extra_key(self):
        fn = _find_func(_parse_main(), "_typing_delay_before_send")
        self.assertIsNotNone(fn, "main.py 应有 _typing_delay_before_send 钩子")
        keys = [
            n.args[0].value
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get_extra"
            and n.args
            and isinstance(n.args[0], ast.Constant)
        ]
        self.assertIn(
            "_send_message_to_user_current_session_plain_texts",
            keys,
            "钩子应读取框架 v20260831 补丁登记的已发文本",
        )

    def test_hook_calls_dedupe_and_clears_chain(self):
        """v4.0 Phase 7：相似度判定下沉 send_pipeline.dedupe_hit。

        钩子仍必须调用判定（dedupe_hit）、阈值可配置、命中清空待发链。
        """
        fn = _find_func(_parse_main(), "_typing_delay_before_send")
        src = ast.get_source_segment(open(_MAIN, encoding="utf-8").read(), fn)
        self.assertIn("dedupe_hit(", src, "钩子应调用 dedupe_hit")
        self.assertIn(
            "dedupe_rewrite_threshold", src, "阈值应可配置"
        )
        self.assertIn(
            ".chain = []", src, "命中后应清空待发链（RespondStage 空链跳过发送）"
        )

    def test_dedupe_block_before_enable_gate(self):
        """复读拦截在 typing.enable 总闸之前——修 bug 性质独立于总闸。"""
        fn = _find_func(_parse_main(), "_typing_delay_before_send")
        src = ast.get_source_segment(open(_MAIN, encoding="utf-8").read(), fn)
        i_dedupe = src.find('self._t("dedupe_rewrite", True)')
        i_enable = src.find('if not self._t("enable", True):')
        self.assertGreater(i_dedupe, -1, "缺少 dedupe_rewrite 开关")
        self.assertGreater(i_enable, -1, "缺少 enable 总闸")
        self.assertLess(
            i_dedupe,
            i_enable,
            "复读拦截应位于 enable 总闸之前（不受总闸影响）",
        )

    def test_schema_has_both_fields(self):
        import json

        with open(os.path.join(_PLUGIN_ROOT, "_conf_schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        items = schema["typing"]["items"]
        self.assertTrue(items["dedupe_rewrite"]["default"], "复读拦截默认开")
        self.assertAlmostEqual(
            float(items["dedupe_rewrite_threshold"]["default"]), 0.82
        )


class TestFrameworkPatchInPlace(unittest.TestCase):
    """框架自检：AstrBot 升级冲掉补丁会让拦截静默失效（登记键消失），
    本组测试在框架文件缺失时 skip、在补丁缺失时 fail。"""

    @unittest.skipUnless(
        os.path.exists(_MESSAGE_TOOLS), "框架 message_tools.py 不在预期路径，跳过"
    )
    def test_message_tools_registers_plain_texts(self):
        with open(_MESSAGE_TOOLS, encoding="utf-8") as f:
            src = f.read()
        self.assertIn(
            "_send_message_to_user_current_session_plain_texts",
            src,
            "框架 v20260831 补丁（已发文本登记）缺失——AstrBot 升级后需重打，"
            "否则复读拦截与语音抑制均静默失效（存档：框架补丁/message_tools_send_dedupe）",
        )

    @unittest.skipUnless(
        os.path.exists(_RESPOND_STAGE), "框架 respond/stage.py 不在预期路径，跳过"
    )
    def test_respond_stage_has_native_guard_and_empty_skip(self):
        with open(_RESPOND_STAGE, encoding="utf-8") as f:
            src = f.read()
        self.assertIn(
            "_send_message_to_user_current_session_plain_texts",
            src,
            "respond 原生重复防护（逐字精确匹配层）缺失",
        )
        self.assertIn(
            "_is_empty_message_chain", src, "respond 空链跳过分支缺失"
        )


if __name__ == "__main__":
    unittest.main()
