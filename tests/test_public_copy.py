# -*- coding: utf-8 -*-
"""对外文案纪律回归（2026-10-21 用户规则）。

用户可见文件（metadata 简介/help、README、安装说明、CHANGELOG、schema 描述/提示、
控制台前端文案）不得出现其它插件名称，也不得出现「可替代某插件」表述；内部代码
注释、测试与提交历史不受此限。

本测试对「用户可见文件」做静态扫描，防止后续改动把其它插件名带回来。
"""

import json
import os
import re
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_VISIBLE = [
    "metadata.yaml",
    "README.md",
    "CHANGELOG.md",
    "安装说明.txt",
    "_conf_schema.json",
]

# 明确点名过的外部插件/项目名称（内部注释可出现，用户可见文件不可）
_FOREIGN_NAMES = [
    "mnemoria",
    "好想记住你",
    "时笺",
    "time_awareness",
    "chat_debounce",
    "continuous_message",
    "blader",
    "im-not-ai",
    "no-ai-slop",
    "petergyang",
    "xiyu-ai",
    "Heartbeat-Memories",
    "bili_scroll",
]

# 本插件自有插件名（含历史名）在白名单内
_FOREIGN_PLUGIN_RE = re.compile(
    r"astrbot_plugin_(?!wanna_be_human|humanizer)[a-z0-9_]+"
)
_REPLACEMENT_PHRASE = re.compile(r"可替代|替代某插件|替代其它插件")


def _read(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _webui_texts():
    base = os.path.join(_ROOT, "webui", "src")
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            if fn.endswith((".vue", ".ts", ".css", ".html")):
                p = os.path.join(dirpath, fn)
                yield os.path.relpath(p, _ROOT), open(p, encoding="utf-8").read()


class TestPublicCopy(unittest.TestCase):
    def test_no_foreign_plugin_names(self):
        for rel in _VISIBLE:
            text = _read(rel)
            for name in _FOREIGN_NAMES:
                self.assertNotIn(
                    name, text, f"{rel} 出现其它插件/项目名称: {name!r}"
                )
            m = _FOREIGN_PLUGIN_RE.search(text)
            self.assertIsNone(
                m, f"{rel} 出现外部 AstrBot 插件名: {m.group(0) if m else ''!r}"
            )

    def test_no_replacement_phrasing(self):
        for rel in _VISIBLE:
            text = _read(rel)
            m = _REPLACEMENT_PHRASE.search(text)
            self.assertIsNone(
                m, f"{rel} 出现「可替代某插件」类表述: {m.group(0) if m else ''!r}"
            )

    def test_webui_copy_clean(self):
        for rel, text in _webui_texts():
            for name in _FOREIGN_NAMES:
                self.assertNotIn(name, text, f"{rel} 出现其它插件/项目名称: {name!r}")
            m = _FOREIGN_PLUGIN_RE.search(text)
            self.assertIsNone(m, f"{rel} 出现外部 AstrBot 插件名")

    def test_schema_group_docs_current(self):
        d = json.loads(_read("_conf_schema.json"))
        self.assertEqual(d["proactive"]["description"], "主动 · 聊天与追问")
        self.assertTrue(
            d["proactive"]["hint"].startswith("用户沉默后的主动消息"),
            d["proactive"]["hint"],
        )
        # 承诺簿已移除（v4.1.1），配置面板不应再宣传该能力
        self.assertNotIn("承诺簿", d["proactive"]["hint"])
        self.assertNotIn("承诺簿", d["proactive"]["description"])


if __name__ == "__main__":
    unittest.main()
