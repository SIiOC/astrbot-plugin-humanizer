# -*- coding: utf-8 -*-
"""插件页面后端（v2.7）纯函数测试：会话历史解析。"""

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from web_api import ROUTE_SPECS, HumanizerWebAPI, _parse_conversation_history  # noqa: E402


class TestRouteTableIntegrity(unittest.TestCase):
    """v2.9.4 事故防御：路由表与类方法必须一一对应。

    曾因编辑错位使 get_stats 脱离类体（被吞进模块级辅助函数），
    注册循环 AttributeError 静默吞掉 → 全部端点 404。
    """

    def test_every_route_method_exists(self):
        class _P:  # 不需要真实插件实例
            pass

        api = HumanizerWebAPI(_P())
        for suffix, attr, _methods, _desc in ROUTE_SPECS:
            self.assertTrue(
                callable(getattr(api, attr, None)),
                f"ROUTE_SPECS 引用的方法缺失于 HumanizerWebAPI: {attr}（/…/{suffix}）",
            )

    def test_unique_paths_and_methods(self):
        paths = [f"{s}:{tuple(m)}" for s, _, m, _ in ROUTE_SPECS]
        self.assertEqual(len(paths), len(set(paths)), "存在重复的 path+methods 路由")

    def test_min_route_count(self):
        # v4.0.3：清理 4 个前端不再调用的僵尸端点后为 17 条
        # （styles/build、styles/import-colleague、models、models/set-rewrite）。
        self.assertGreaterEqual(len(ROUTE_SPECS), 17)


class TestParseConversationHistory(unittest.TestCase):
    """v2.7：记录回看的历史解析（旧 dict 格式 / 新版 ThinkPart 格式）。"""

    def test_empty_inputs(self):
        self.assertEqual(_parse_conversation_history(""), [])
        self.assertEqual(_parse_conversation_history(None), [])
        self.assertEqual(_parse_conversation_history("not json"), [])
        self.assertEqual(_parse_conversation_history({}), [])
        self.assertEqual(_parse_conversation_history([]), [])

    def test_legacy_dict_format(self):
        history = json.dumps(
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好呀"},
            ]
        )
        msgs = _parse_conversation_history(history)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0], {"role": "user", "text": "你好"})
        self.assertEqual(msgs[1], {"role": "assistant", "text": "你好呀"})

    def test_think_part_extracted(self):
        history = [
            {
                "role": "assistant",
                "content": [
                    {"type": "think", "think": "用户今天心情不好，要温柔"},
                    {"type": "text", "text": "今天辛苦啦，好好休息"},
                ],
            }
        ]
        msgs = _parse_conversation_history(history)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["text"], "今天辛苦啦，好好休息")
        self.assertEqual(msgs[0]["thinking"], "用户今天心情不好，要温柔")

    def test_proactive_marker(self):
        history = json.dumps(
            [
                {"role": "user", "content": "[主动消息] 请自然地延续对话。"},
                {"role": "assistant", "content": "在忙什么呀？"},
            ]
        )
        msgs = _parse_conversation_history(history)
        self.assertTrue(msgs[0].get("proactive"))
        self.assertNotIn("proactive", msgs[1])

    def test_plain_prefix_not_marked_proactive(self):
        """v4.1.9：用户自发同前缀文本不得被误标为插件主动消息。"""
        history = json.dumps(
            [{"role": "user", "content": "[主动消息] 这是我自己的口头禅"}]
        )
        msgs = _parse_conversation_history(history)
        self.assertNotIn("proactive", msgs[0])

    def test_content_dict_form(self):
        history = [
            {"role": "assistant", "content": {"think": "思考", "text": "回复"}}
        ]
        msgs = _parse_conversation_history(history)
        self.assertEqual(msgs[0]["text"], "回复")
        self.assertEqual(msgs[0]["thinking"], "思考")

    def test_skip_empty_messages(self):
        history = [
            {"role": "user", "content": ""},
            {"role": "user", "content": "   "},
            {"role": "user", "content": "有效"},
        ]
        msgs = _parse_conversation_history(history)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["text"], "有效")

    def test_multiple_text_parts_joined(self):
        history = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "第一句"},
                    {"type": "text", "text": "第二句"},
                ],
            }
        ]
        msgs = _parse_conversation_history(history)
        self.assertEqual(msgs[0]["text"], "第一句第二句")


if __name__ == "__main__":
    unittest.main()
