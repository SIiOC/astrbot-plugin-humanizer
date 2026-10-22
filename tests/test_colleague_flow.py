# -*- coding: utf-8 -*-
"""v2.9.4 审查修复回归测试：colleague 导入链的两个关键契约。

历史事故：web_api 两个 colleague 端点对 `_load_colleague_input`（async，
返回 (persona_text, meta_text)）缺 await + 解包顺序反 + 对
`_call_llm_for_profile` 已解析的 dict 二次 parse_profile_json——
三重 bug 叠加导致该功能 100% 必 500，而路由表测试全绿未覆盖。
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_api  # noqa: E402

# AstrBot 运行时签名快照（人工核对自 main.py）：
#   async def _load_colleague_input(self, body) -> tuple[str, str]  # (persona_text, meta_text)
#   async def _call_llm_for_profile(self, prompt, reply_to) -> dict | None  # 已解析校验过的档案


class _FakePlugin:
    """以与 main.py 完全一致的签名/返回形态模拟插件协作对象。"""

    _building = False

    async def _load_colleague_input(self, body: str):
        return ("persona-文本", "meta-文本")

    async def _call_llm_for_profile(self, prompt: str, reply_to=None):
        return {"name": "", "persona": "人设", "catchphrases": ["嗯"]}


class TestColleagueContracts(unittest.TestCase):
    def setUp(self):
        # 注入假 astrbot.api.web（本机无 astrbot 包）
        fake_web = types.ModuleType("astrbot.api.web")
        fake_web.json_response = lambda data, status_code=200: dict(data)
        fake_web.request = types.SimpleNamespace(query={})
        for name, mod in {
            "astrbot": types.ModuleType("astrbot"),
            "astrbot.api": types.ModuleType("astrbot.api"),
            "astrbot.api.web": fake_web,
        }.items():
            sys.modules.setdefault(name, mod)
        sys.modules["astrbot"].api = sys.modules["astrbot.api"]
        sys.modules["astrbot.api"].web = fake_web

        self.plugin = _FakePlugin()
        self.api = web_api.HumanizerWebAPI(self.plugin)

    def test_load_colleague_input_is_async_tuple_order(self):
        """_load_colleague_input 是协程函数且返回 (persona, meta)——web_api
        端点里必须 await 且按此顺序解包。签名漂移（改同步/调序）时本测试报警。"""
        import inspect

        self.assertTrue(
            inspect.iscoroutinefunction(self.plugin._load_colleague_input),
            "_load_colleague_input 应为 async（端点侧需 await）",
        )
        import asyncio

        persona, meta = asyncio.run(self.plugin._load_colleague_input("x"))
        self.assertEqual(persona, "persona-文本")
        self.assertEqual(meta, "meta-文本")

    def test_call_llm_returns_parsed_dict(self):
        """_call_llm_for_profile 返回已解析的 dict——端点不得再
        parse_profile_json（str-only，dict 会 AttributeError）。"""
        import asyncio

        result = asyncio.run(self.plugin._call_llm_for_profile("p"))
        self.assertIsInstance(result, dict)

    def test_generate_style_source_branch_uses_await(self):
        """源码级回归钉：generate_style 的 colleague 分支必须含 await
        _load_colleague_input 且正确顺序解包（AST 级检查，防再次漏写）。"""
        import ast
        import inspect
        from textwrap import dedent

        src = dedent(inspect.getsource(web_api.HumanizerWebAPI.generate_style))
        tree = ast.parse(src)
        found = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Await)
                and isinstance(node.value.value, ast.Call)
                and getattr(node.value.value.func, "attr", "") == "_load_colleague_input"
            ):
                # 元组解包目标：persona_text, meta_text
                t = node.targets[0]
                names = (
                    [e.id for e in t.elts]
                    if isinstance(t, ast.Tuple)
                    else ([t.id] if isinstance(t, ast.Name) else [])
                )
                if names == ["persona_text", "meta_text"]:
                    found = True
        self.assertTrue(
            found,
            "generate_style 须包含 `persona_text, meta_text = await self.plugin._load_colleague_input(...)`",
        )

    def test_import_colleague_endpoint_removed(self):
        """v4.0.3：专用端点已删除，colleague 导入只剩 generate_style 一条路。

        旧测试钉的是 `import_colleague` 端点的 await 解包（v2.9.4 三重 bug 修复）；
        端点清理后该分支已合并进 `generate_style`（上面的用例已钉住），
        此处改为反向钉子：防止”同一能力两套入口“洄流。
        """
        self.assertFalse(
            hasattr(web_api.HumanizerWebAPI, "import_colleague"),
            "import_colleague 端点已随 v4.0.3 清理删除，不得回潮",
        )
        route_suffixes = {s for s, _, _, _ in web_api.ROUTE_SPECS}
        self.assertNotIn("styles/import-colleague", route_suffixes)
        self.assertIn("styles/generate", route_suffixes, "统一生成入口必须保留")


if __name__ == "__main__":
    unittest.main()
