# -*- coding: utf-8 -*-
"""v3.9.5 可靠性接线契约（AST，不 import main.py）。

钉住：防抖组修复、KB 指纹/代际/分页/失效、检索缓存、改写预算与 QC 单轮、
承诺单飞、生活按日期单飞、任务注册表 terminate 收尾、主动防重复生成护栏。
排序断言一律用 node.lineno（ast.walk BFS 序不可靠的历史教训）。
"""

import ast
import os
import unittest

_MAIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"
)


def _parse():
    with open(_MAIN, encoding="utf-8") as f:
        return ast.parse(f.read(), filename=_MAIN)


def _find_func(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"main.py 中找不到函数 {name}")


def _find_service_tree():
    """Parse services/kb_service.py AST (shared by KB contracts)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "services", "kb_service.py"), encoding="utf-8") as f:
        return ast.parse(f.read())


class TestDebounceFix(unittest.TestCase):
    def test_d_num_typing_group(self):
        fn = _find_func(_parse(), "_d_num")
        src = ast.dump(fn)
        self.assertIn("typing", src)
        self.assertIn("_DEBOUNCE_KEY_MAP", src)
        self.assertNotIn(
            'Constant(value="debounce")', src, "不得再读已废弃的 debounce 组"
        )


class TestKbReliability(unittest.TestCase):
    def _service_tree(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "services", "kb_service.py"), encoding="utf-8") as f:
            return ast.parse(f.read())

    def test_sync_job_signature_and_counts(self):
        # v4.0：同步实现下沉 KBService.sync_job；source grouping 与 fingerprint
        # 由服务的有效行为测试覆盖，main 只保留 generation 委托入口。
        fn = _find_func(self._service_tree(), "sync_job")
        args = [a.arg for a in fn.args.args]
        self.assertIn("generation", args)
        src = ast.dump(fn)
        self.assertIn("builtin_texts", src)
        self.assertIn("user_texts", src)
        self.assertIn("current_index_fingerprint", src)

    def test_sync_job_generation_guards(self):
        fn = _find_func(self._service_tree(), "sync_job")
        src = ast.dump(fn)
        self.assertGreaterEqual(src.count("_current_generation"), 2, "进入与收尾都要守卫")

    def test_pagination_helper(self):
        # v4.0 Phase 4：分页控制流下沉 kb_state.iter_all_documents
        # （count_documents/offset/limit 行为契约迁移至
        # tests/test_kb_pagination.py）；此处钉 main 入口仍委托下沉实现。
        fn = _find_func(_parse(), "_list_all_kb_docs")
        src = ast.dump(fn)
        self.assertIn("kb_iter_all_documents", src, "_list_all_kb_docs 必须委托下沉实现")

    def test_ensure_kb_freshness_gate(self):
        # v4.0：ready/指纹闸门下沉 KBService.ensure；main 入口只委托。
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "services", "kb_service.py"), encoding="utf-8") as f:
            service = ast.parse(f.read())
        fn = _find_func(service, "ensure")
        src = ast.dump(fn)
        self.assertIn("index_fresh", src, "就绪短路必须先过指纹新鲜度")

    def test_invalidation_wired(self):
        tree = _parse()
        for fname in ("style_import", "style_refine"):
            self.assertIn("_invalidate_kb_index", ast.dump(_find_func(tree, fname)))

    def test_style_index_keeps_marker_clear_and_no_discard(self):
        # v4.0：状态清理收口到 KBService.forget（清就绪表 + rerank 对账标记 +
        # 持久化指纹并落盘）；行为契约见
        # tests/test_kb_state_ownership.py::test_forget_clears_and_persists。
        fn = _find_func(_parse(), "style_index")
        src = ast.dump(fn)
        self.assertIn("forget", src, "手动重建必须经服务清指纹")
        self.assertNotIn("discard", src, "不得再无条件 discard syncing（防双同步）")


class TestRetrieveCacheWiring(unittest.TestCase):
    def test_examples_use_cache(self):
        fn = _find_func(_parse(), "_retrieve_examples")
        src = ast.dump(fn)
        self.assertIn("_retrieve_cache", src)
        self.assertIn("retrieve_cache_enable", src)
        self.assertIn("unified_msg_origin", src, "缓存 key 必须含会话隔离")




class TestTaskLifecycle(unittest.TestCase):

    def test_life_date_single_flight(self):
        fn = _find_func(_parse(), "_ensure_life_state")
        src = ast.dump(fn)
        self.assertIn("_life_gen_tasks", src)
        self.assertIn("_bg_tasks", src)
        # 置位必须在 create_task 之前（消除并发窗口）
        set_ln = next(
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            and ast.dump(n).find("_life_generating") != -1
        )
        create_ln = next(
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "create_task"
        )
        self.assertLess(set_ln, create_ln, "标志置位必须先于任务创建")

    def test_terminate_closes_registry(self):
        fn = _find_func(_parse(), "terminate")
        src = ast.dump(fn)
        close_ln = next(
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "close"
        )
        cancel_ln = next(
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "cancel_all"
        )
        self.assertLess(close_ln, cancel_ln, "先 close 再 cancel_all")


class TestProactiveRegenGuard(unittest.TestCase):
    def test_guard_present_before_light_path(self):
        fn = _find_func(_parse(), "_proactive_chat")
        src = ast.dump(fn)
        self.assertIn("_pipeline_failed", src)
        self.assertIn("proactive_regen_guard", src)


class TestReviewFixes(unittest.TestCase):
    """v3.9.5 审查修复：认领逻辑 / 缓存 key 摘要 / 信号量顺序 / 超时标记。"""

    def _src(self, name):
        return ast.dump(_find_func(_parse(), name))

    def test_marker_absent_claims_existing_batches(self):
        """marker 缺失但批数齐全 → 认领（写指纹不重传），避免升级后全量重建。

        v4.0：同步实现下沉 KBService.sync_job；中文日志与 marker 判定
        由 tests/test_kb_service.py::test_marker_claim_without_upload 行为钉死。
        这里钉结构：服务实现存在 marker=None 语义对应的
        `marker = self.index_state.get(kb_name)` + complete 分支。
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "services", "kb_service.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        fn = _find_func(tree, "sync_job")
        src = ast.dump(fn)
        self.assertIn("index_state", src)
        self.assertIn("complete", src)
        self.assertIn("persist_index_state", src)

    def test_cache_key_uses_full_query_digest(self):
        """缓存 key 必须用完整查询摘要，不得用前缀截断。

        v4.0 Phase 8：摘要计算下沉 retrieval_plan.query_digest（sha256 前 24 位，
        非 [:64] 前缀截断）；_retrieve_examples 经该函数生成 key。
        """
        src = self._src("_retrieve_examples")
        self.assertIn("query_digest", src, "检索缓存 key 必须走完整查询摘要")
        self.assertNotIn("[:64]", src, "不得再用前缀截断做 key")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(
            os.path.join(root, "humanizer_core", "retrieval_plan.py"), encoding="utf-8"
        ) as f:
            plan_src = f.read()
        self.assertIn("sha256", plan_src)
        self.assertIn(".hexdigest()[:24]", plan_src, "摘要取 sha256 前 24 位")

    def test_cache_key_corpus_dimension_reads_service(self):
        """检索缓存 key 的语料维度必须读服务权威指纹（回归防线）。

        真回归：main 曾各自维护 _corpus_fp_cache 副本，但服务的
        current_index_fingerprint 只写服务自己的缓存 → main 副本永远为空，
        缓存 key 丢失语料维度。改为经 _corpus_fingerprint() 读 KBService。
        ⚠️ 只扫 AST 访问节点，不用字面量（docstring 提到旧名会误伤）。
        """
        fn = _find_func(_parse(), "_retrieve_examples")
        attrs = {
            n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)
        }
        self.assertIn(
            "_corpus_fingerprint", attrs, "key 必须经 _corpus_fingerprint 读服务"
        )
        self.assertNotIn(
            "_corpus_fp_cache", attrs, "不得再直读已删除的 main 副本"
        )
        helper = _find_func(_parse(), "_corpus_fingerprint")
        hattrs = {n.attr for n in ast.walk(helper) if isinstance(n, ast.Attribute)}
        self.assertIn(
            "corpus_fingerprint_cache", hattrs, "必须读服务权威缓存"
        )


    def test_pipeline_timeout_marks_failure(self):
        src = self._src("_generate_proactive_reply")
        self.assertIn("_humanizer_pipeline_failed", src, "超时须标记失败")
        caller = self._src("_proactive_chat")
        self.assertIn("_humanizer_pipeline_failed", caller, "调用方须读取标记")

    def test_kb_log_messages_keep_humanstyle_tag_and_chinese(self):
        """KB 诊断日志必须保留 [HumanStyle] 标签与中文（审查发现曾整体英文化）。

        真回归（诊断面）：下沉 KBService 时把中文日志改成英文并丢标签，导致
        用户排障时找不到既有日志线索（"已同步检测失败"/"重启自愈"/"/style_index
        重试" 等可操作指引消失）。锁：服务内 _log 调用的消息不得为纯英文。
        """
        svc = _find_service_tree()
        msgs = []
        for n in ast.walk(svc):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "_log"
                and len(n.args) >= 2
            ):
                arg = n.args[1]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    msgs.append(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    # f-string：拼接所有常量片段
                    msgs.append(
                        "".join(
                            v.value for v in arg.values
                            if isinstance(v, ast.Constant) and isinstance(v.value, str)
                        )
                    )
        self.assertTrue(msgs, "服务应有 _log 调用")
        for m in msgs:
            if "HumanStyle" not in m:
                # 允许的例外：无标签的纯技术性 debug（如启动竞态）
                continue
            self.assertTrue(
                any("\u4e00" <= c <= "\u9fff" for c in m),
                f"[HumanStyle] 日志必须为中文（审查曾英文化）: {m!r}",
            )

    def test_kb_actionable_log_hints_present(self):
        """审查发现丢失的可操作排障提示必须回归（用户依赖这些字符串定位问题）。"""
        svc = ast.dump(_find_service_tree())
        for hint in (
            "重启自愈",
            "/style_index 重试",
            "框架不支持 kb_manager",
            "未配置 embedding provider",
        ):
            self.assertIn(hint, svc, f"KB 排障提示丢失: {hint}")


if __name__ == "__main__":
    unittest.main()
