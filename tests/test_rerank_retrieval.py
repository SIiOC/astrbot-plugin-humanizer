# -*- coding: utf-8 -*-
"""v3.5.0 检索重排（rerank）支持 + 配置文案 ⚠️ 换行的契约测试。

背景（2026-09-03 用户需求 + 09-04 实测修正）：
1. 插件配置 hint 中的 ⚠️ 应另起一行。插件配置面板（ExtensionPage →
   旧版 AstrBotConfig 组件）hint 是纯文本插值，`\n` 默认塌成空格，
   需配合框架 dist 主 CSS 的 `white-space:pre-line` 补丁
   （见 TestDashboardCssPatch 与 本机框架补丁存档（dashboard-hint-newline-css 目录））。
   schema 侧契约：所有 ⚠️ 用 `\n` 转义放行首。
2. 「语料提炼说话风格，注入 LLM 提示词」的检索注入部分经由框架知识库
   管线（kb_manager.create_kb / retrieve），框架原生支持按库挂 rerank
   （KnowledgeBase.rerank_provider_id），插件此前未配置——需向用户告知
   并提供 rerank 供应商下拉 + 候选池参数。

契约（main.py + _conf_schema.json）：
- schema style 组新增 rerank_provider_id / rerank_candidates；
  所有 hint 的 ⚠️ 都位于行首。
- 语义（关键）：插件配置空 = 不干预，尊重知识库级 rerank 配置
  （用户已在框架 WebUI 给 human_style KB 挂了 local_rerank，插件
  绝不因配置为空而拆除）；选定 = 强制同步到该提供商。
- _inject_schema_options 注入 rerank provider 下拉
  （provider_manager.rerank_provider_insts）。
- _kb_sync_job 建库传 rerank_provider_id；存量库仅插件显式配置时
  用 update_kb 同步（必须带框架必填的 kb_name 位置参数——旧调用
  漏传被 except 吞掉，描述刷新从未生效）。
- _retrieve_examples：检索链路上有 rerank（插件或知识库级）时扩大
  候选池（top_k_fusion），无 rerank 时保持候选池 = top_k（行为与
  v3.4.6 完全一致）。
- rerank 配置漂移检测放 _retrieve_examples（库就绪路径），
  不得放 _ensure_kb（那里位于 create_kb/embedding 闸门之前，
  会绕过禁用条件）。
- /style_index 清 _kb_rerank_applied 强制重新对账。

不 import main.py（本机无 astrbot 包），用 ast 直接钉源码结构。
"""

import ast
import json
import os
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN = os.path.join(_ROOT, "main.py")
_SCHEMA = os.path.join(_ROOT, "_conf_schema.json")


def _load_schema():
    with open(_SCHEMA, encoding="utf-8") as f:
        return json.load(f)


def _call_attr_names(node):
    """node 子树内所有属性调用名（logger.info 里的 info 等）。"""
    return [
        sub.func.attr
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
    ]


class TestSchemaWarnOnOwnLine(unittest.TestCase):
    """任务1：所有 hint 中的 ⚠️ 必须另起一行（\n 转义前缀）。"""

    def test_all_warns_line_prefixed(self):
        schema = _load_schema()
        offenders = []

        def walk(o, path):
            if isinstance(o, dict):
                hint = o.get("hint")
                if isinstance(hint, str) and "⚠️" in hint:
                    for i, line in enumerate(hint.split("\n")):
                        if "⚠️" in line and i > 0 and not line.startswith("⚠️"):
                            offenders.append(path)
                        if "⚠️" in line and i == 0:
                            offenders.append(path + "（首行）")
                for k, v in o.items():
                    walk(v, path + "/" + str(k))
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")

        walk(schema, "")
        self.assertEqual(offenders, [], f"⚠️ 未另起一行的 hint: {offenders}")

    def test_warn_count_unchanged(self):
        """换行改造不得增删 ⚠️（防误伤其他文案）。"""
        with open(_SCHEMA, encoding="utf-8") as f:
            raw = f.read()
        self.assertEqual(raw.count("⚠️"), raw.count("\\n⚠️"), "每个 ⚠️ 前都应有 \\n")


class TestSchemaRerankItems(unittest.TestCase):
    """任务2：style 组新增 rerank 配置项 + 告知文案。"""

    @classmethod
    def setUpClass(cls):
        cls.style = _load_schema()["style"]["items"]

    def test_rerank_provider_id_item(self):
        item = self.style.get("rerank_provider_id")
        self.assertIsInstance(item, dict, "style 组缺 rerank_provider_id")
        self.assertEqual(item.get("type"), "string")
        self.assertEqual(item.get("default"), "")

    def test_rerank_provider_hint_informs(self):
        hint = self.style["rerank_provider_id"].get("hint", "")
        self.assertIn("rerank", hint)
        self.assertIn("模型供应商", hint, "hint 应告知从 AstrBot 模型供应商中选择")
        self.assertIn("不干预", hint, "留空必须是不干预语义（不拆知识库级 rerank）")
        self.assertIn("知识库", hint, "hint 应告知知识库级 rerank 配置的存在")

    def test_rerank_candidates_item(self):
        item = self.style.get("rerank_candidates")
        self.assertIsInstance(item, dict, "style 组缺 rerank_candidates")
        self.assertEqual(item.get("type"), "int")
        self.assertEqual(item.get("default"), 12)

    def test_enable_retrieval_hint_mentions_rerank(self):
        hint = self.style["enable_retrieval"].get("hint", "")
        self.assertIn("rerank", hint, "检索开关 hint 应告知可用 rerank 精排")


class TestDropdownInjection(unittest.TestCase):
    def test_rerank_options_injected(self):
        func = _find_func(_parse(), "_inject_schema_options")
        src = ast.dump(func)
        self.assertIn("rerank_provider_insts", src, "必须读 provider_manager.rerank_provider_insts")
        self.assertIn("rerank_provider_id", src, "必须写入 style 组 rerank_provider_id 的 options")


class TestKbSyncRerankWiring(unittest.TestCase):
    def _sync_job(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "services", "kb_service.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        return _find_func(tree, "sync_job")

    def _find_call(self, func, attr):
        for sub in ast.walk(func):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == attr
            ):
                yield sub

    def test_create_kb_passes_rerank(self):
        calls = list(self._find_call(self._sync_job(), "create_kb"))
        self.assertEqual(len(calls), 1)
        kws = {kw.arg for kw in calls[0].keywords}
        self.assertIn("rerank_provider_id", kws, "create_kb 必须传 rerank_provider_id")
        self.assertIn("embedding_provider_id", kws)

    def test_update_kb_passes_kb_name_positional(self):
        """回归：旧调用 update_kb(kb_id, description=...) 漏传框架必填的
        kb_name 位置参数，TypeError 被 except 吞掉，描述刷新从未生效。"""
        calls = list(self._find_call(self._sync_job(), "update_kb"))
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertGreaterEqual(
            len(call.args), 2, "update_kb 必须按位置传 kb_id 和 kb_name"
        )
        self.assertIsInstance(
            call.args[1], ast.Name, "第二个位置参数必须是 kb_name 变量"
        )
        kws = {kw.arg for kw in call.keywords}
        self.assertIn("rerank_provider_id", kws, "update_kb 必须传 rerank_provider_id")

    def test_update_kb_only_when_plugin_configured(self):
        """空配置 = 不干预：need_rr 必须以 want_rr 真值为前提，
        防止插件配置为空时把知识库级已挂的 rerank（用户 WebUI 配的）
        拆掉。"""
        func = self._sync_job()
        found = any(
            isinstance(sub, ast.Assign)
            and isinstance(sub.value, ast.BoolOp)
            and any(
                isinstance(v, ast.Call)
                and isinstance(v.func, ast.Name)
                and v.func.id == "bool"
                for v in sub.value.values
            )
            for sub in ast.walk(func)
        )
        self.assertTrue(found, "need_rr 必须 bool(want_rr) and ... 短路")

    def test_rerank_applied_marker_recorded(self):
        func = self._sync_job()
        src = ast.dump(func)
        self.assertIn("rerank_applied", src, "同步完成必须记录已对账的 rerank 目标值")

    def test_marker_uses_none_sentinel(self):
        """rerank 未配置用 None 哨兵，避免空串与库实况 None 永远漂移。

        v4.0：下沉 KBService.rerank_applied；行为由
        test_kb_service::test_rerank_drift_reads_reality_once +
        sync 结构的 `wanted_rerank = ... or None` 共同钉死。
        """
        func = self._sync_job()
        src = ast.dump(func)
        self.assertIn("wanted_rerank", src)
        self.assertIn("rerank_applied", src)


class TestRetrieveCandidates(unittest.TestCase):
    def test_candidates_widened_only_with_rerank(self):
        func = _find_func(_parse(), "_retrieve_examples")
        src = ast.dump(func)
        self.assertIn("_configured_rerank_id", src, "候选池扩宽必须感知插件配置的 rerank")
        self.assertIn("rerank_candidates", src, "候选池大小必须可配置")
        self.assertIn(
            "rerank_provider_id", src, "知识库级 rerank（WebUI 配置）也必须扩宽候选池"
        )

    def test_candidates_clamped(self):
        """上限 30、下限 top_k 的钳制必须存在。

        v4.0 Phase 8：钳制下沉 retrieval_plan.resolve_candidates——
        `max(top_k, min(val, 30))`；_retrieve_examples 经该函数取候选池。
        """
        func = _find_func(_parse(), "_retrieve_examples")
        has_call = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "resolve_candidates"
            for n in ast.walk(func)
        )
        self.assertTrue(has_call, "候选池必须经 resolve_candidates 钳制")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(
            os.path.join(root, "humanizer_core", "retrieval_plan.py"), encoding="utf-8"
        ) as f:
            plan_tree = ast.parse(f.read())

        def _is_name_call(node, name):
            return (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
            )

        fn = next(
            n
            for n in ast.walk(plan_tree)
            if isinstance(n, ast.FunctionDef) and n.name == "resolve_candidates"
        )
        found = any(
            _is_name_call(sub, "max") and any(_is_name_call(a, "min") for a in sub.args)
            for sub in ast.walk(fn)
        )
        self.assertTrue(found, "候选池必须 max(top_k, min(candidates, 30)) 钳制")
        # 上限 30 提为模块常量 _RERANK_CANDIDATES_MAX（函数内引用它）
        consts = [
            sub.value
            for sub in ast.walk(plan_tree)
            if isinstance(sub, ast.Constant) and sub.value == 30
        ]
        self.assertIn(30, consts, "候选池上限 30")

    def test_drift_check_in_retrieve_not_in_ensure_kb(self):
        """漂移检测必须放 _retrieve_examples（库就绪路径），不得放
        _ensure_kb——那里位于 create_kb/embedding 闸门之前，会绕过禁用条件。"""
        ensure = ast.dump(_find_func(_parse(), "_ensure_kb"))
        retrieve = ast.dump(_find_func(_parse(), "_retrieve_examples"))
        self.assertNotIn("_rerank_drift", ensure, "_ensure_kb 不得做漂移检测")
        self.assertIn("_rerank_drift", retrieve, "_retrieve_examples 必须做漂移检测")


class TestRerankDriftFunction(unittest.TestCase):
    def test_empty_config_never_drifts(self):
        """配置空 = 不干预：want 为 None 时必须立即 False，不得读库比对
        （否则会把知识库级已挂的 rerank 误判为漂移并拆除）。"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "services", "kb_service.py"), encoding="utf-8") as f:
            service_tree = ast.parse(f.read())
        func = _find_func(service_tree, "rerank_drift")
        stmts = [s for s in func.body if isinstance(s, ast.If)]
        self.assertTrue(stmts, "_rerank_drift 必须有 want 空值守卫")
        first_test = stmts[0].test
        self.assertIsInstance(first_test, ast.Compare)
        self.assertIsInstance(first_test.ops[0], ast.Is)
        self.assertIsInstance(first_test.comparators[0], ast.Constant)
        self.assertIsNone(first_test.comparators[0].value)
        self.assertTrue(
            any(isinstance(s, ast.Return) for s in ast.walk(stmts[0])),
            "want 为 None 时必须直接 return False",
        )

    def test_reconciles_from_kb_on_missing_marker(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "services", "kb_service.py"), encoding="utf-8") as f:
            service_tree = ast.parse(f.read())
        func = _find_func(service_tree, "rerank_drift")
        calls = _call_attr_names(func)
        self.assertIn("get_kb_by_name", calls, "无对账记录时必须读库实况")


class TestStyleIndexResets(unittest.TestCase):
    def test_style_index_clears_rerank_marker(self):
        # v4.0：清理由 KBService.forget 统一执行（含 rerank 对账标记）。
        fn = _find_func(_parse(), "style_index")
        src = ast.dump(fn)
        self.assertIn("_kb_service", src, "/style_index 必须经服务清理状态")
        self.assertIn("forget", src, "/style_index 必须清 rerank 对账标记（force re-reconcile）")



class TestDashboardCssPatch(unittest.TestCase):
    """⚠️ 换行的另一半：插件配置面板（旧版 AstrBotConfig）hint 是纯文本
    插值，需框架 dist 主 CSS 打 `white-space:pre-line` 补丁才换行。
    dashboard 更新会丢补丁——dist 存在时自动检查，缺失 FAIL（无 dist
    环境如插件开发机 SKIP）。存档：本机框架补丁存档（dashboard-hint-newline-css 目录）
    """

    def test_preline_patch_present(self):
        dist = os.path.join(
            os.path.dirname(_ROOT), "..", "..", "data", "dist", "assets"
        )
        dist = os.path.normpath(dist)
        if not os.path.isdir(dist):
            self.skipTest(f"本机无 dashboard dist（{dist}），跳过框架补丁检查")
        candidates = [
            f for f in os.listdir(dist)
            if f.startswith("index-") and f.endswith(".css")
        ]
        # 取 index.html 实际引用的主 css（防多版本 chunk 共存时检查错文件）
        html_path = os.path.normpath(os.path.join(dist, "..", "index.html"))
        targets = []
        if os.path.isfile(html_path):
            with open(html_path, encoding="utf-8", errors="ignore") as f:
                html = f.read()
            targets = [
                os.path.join(dist, name)
                for name in candidates
                if name in html
            ]
        if not targets:
            targets = [os.path.join(dist, f) for f in candidates]
        self.assertTrue(targets, "dist 中找不到 index-*.css 主样式")
        patched = any(
            "white-space:pre-line" in open(t, encoding="utf-8", errors="ignore").read()
            for t in targets
        )
        self.assertTrue(
            patched,
            "dashboard 主 CSS 缺少 white-space:pre-line 补丁（配置 hint 的 \\n 不会换行）；"
            "重打方法见 本机框架补丁存档（dashboard-hint-newline-css 目录）/README.md",
        )


if __name__ == "__main__":
    unittest.main()
