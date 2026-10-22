# -*- coding: utf-8 -*-
"""控制台构建产物契约（v4.1.1：webui 源码可构建后钉死产物完整性）。

只做静态检查，不依赖浏览器：index.html 必须引用相对路径的 assets/*.js|css，
且被引用的文件真实存在、体积非空；产物里必须含 7 个页面标题。
"""

import os
import re
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIST = os.path.join(_ROOT, "pages", "humanizer-console")


class TestConsoleDistContract(unittest.TestCase):
    def test_index_references_existing_assets(self):
        index = os.path.join(_DIST, "index.html")
        self.assertTrue(os.path.isfile(index), "缺少 pages/humanizer-console/index.html")
        html = open(index, encoding="utf-8").read()
        refs = re.findall(r'(?:src|href)="\./([^"]+)"', html)
        self.assertGreaterEqual(len(refs), 2, "index.html 应引用 js 与 css")
        for rel in refs:
            p = os.path.join(_DIST, rel)
            self.assertTrue(os.path.isfile(p), f"index.html 引用了不存在的资源: {rel}")
            self.assertGreater(os.path.getsize(p), 1000, f"资源疑似空文件: {rel}")

    def test_bundle_contains_all_pages(self):
        assets = os.path.join(_DIST, "assets")
        js = [f for f in os.listdir(assets) if f.endswith(".js")]
        self.assertTrue(js, "缺少构建后的 js 产物")
        blob = "".join(
            open(os.path.join(assets, f), encoding="utf-8", errors="ignore").read()
            for f in js
        )
        for title in ("总览", "配置", "语料与风格", "主动聊天", "记录回看", "真人感规则", "统计"):
            self.assertIn(title, blob, f"产物缺少页面标题: {title}")
        # 桥接协议必须保留（apiGet/apiPost 从宿主注入的 AstrBotPluginPage 走）
        self.assertIn("AstrBotPluginPage", blob)

    def test_webui_source_scaffold_present(self):
        for rel in (
            "webui/package.json",
            "webui/vite.config.ts",
            "webui/index.html",
            "webui/src/composables/useBridge.ts",
            "webui/src/views/RulesView.vue",
        ):
            self.assertTrue(
                os.path.isfile(os.path.join(_ROOT, rel)), f"缺少前端源码: {rel}"
            )


if __name__ == "__main__":
    unittest.main()
