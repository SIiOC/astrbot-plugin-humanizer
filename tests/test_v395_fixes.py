# -*- coding: utf-8 -*-
"""v3.9.5 审查修复回归测试。

本轮全面审查发现的问题，逐项钉住（AST 契约 + 纯函数行为 + 真实 __init__ 执行）：

1. 阻断：`_kb_state_path` / `_kb_index_state` 在 `_init_time_stores()` 之后被
   重新赋值，覆盖掉刚加载的持久化指纹 → 指纹永不落盘、每次重启都全量重建。
2. `_proactive_chat` 中 `cron_event` 仅在 `HAS_AGENT_PIPELINE` 分支赋值，却在
   分支外被读取 → 旧框架下 NameError 直接 return False，轻量回退永不执行。
3. `humaneness_rules._gen_id()` 同毫秒碰撞 → 按 id 匹配的命令一次命中多条。
4. `lang_mirror` 对损坏画像的计数器直接 int() → ValueError（违背"安全回落"）。
5. 语言画像剪枝只写文件不回写内存 → 长期运行内存无界。
6. `retrieval_timeout` 代码回落默认值 30.0 与 schema 的 5 不一致。
7. 分组迁移丢弃显式清单之外的剩余键。
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _ast_helpers import find_func as _find_func, parse_main as _parse


def _src(node) -> str:
    return ast.dump(node)


_ASSIGN_NODES = (ast.Assign, ast.AnnAssign)


def _target_attrs(node) -> list:
    """取赋值语句的目标属性名（兼容带注解的 AnnAssign）。"""
    if isinstance(node, ast.Assign):
        targets = node.targets
    else:  # AnnAssign
        targets = [node.target]
    return [t.attr for t in targets if isinstance(t, ast.Attribute)]


class TestKbStateNotClobbered(unittest.TestCase):
    """F1：指纹状态必须在 _init_time_stores() 之前预声明，之后不得再赋值。"""

    def test_predeclare_before_init_stores(self):
        init = _find_func(_parse(), "__init__")
        call_line = None
        for n in ast.walk(init):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "_init_time_stores"
            ):
                call_line = n.lineno
                break
        self.assertIsNotNone(call_line, "__init__ 应调用 _init_time_stores()")

        decls = []
        for n in ast.walk(init):
            if isinstance(n, _ASSIGN_NODES):
                for attr in _target_attrs(n):
                    if attr in ("_kb_state_path", "_kb_index_state"):
                        decls.append((attr, n.lineno))
        self.assertTrue(decls, "必须在 __init__ 中声明 KB 指纹状态属性")
        for attr, line in decls:
            self.assertLess(
                line,
                call_line,
                f"self.{attr} 的赋值必须在 _init_time_stores()（行 {call_line}）之前，"
                f"否则会覆盖该方法加载到的持久化指纹（实际在行 {line}）",
            )
        self.assertEqual(
            len(decls), 2, f"每个属性只应赋值一次（预声明），实际 {decls}"
        )

    def test_no_assign_after_call(self):
        """反向断言：调用点之后不存在对这两个属性的赋值。"""
        init = _find_func(_parse(), "__init__")
        call_line = min(
            n.lineno
            for n in ast.walk(init)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_init_time_stores"
        )
        after = [
            (attr, n.lineno)
            for n in ast.walk(init)
            if isinstance(n, _ASSIGN_NODES) and n.lineno > call_line
            for attr in _target_attrs(n)
            if attr in ("_kb_state_path", "_kb_index_state")
        ]
        self.assertEqual(after, [], f"_init_time_stores() 之后不得再赋值指纹状态：{after}")


class TestProactiveCronEventBound(unittest.TestCase):
    """F2：cron_event 必须在 pipeline 分支之外先绑定为 None。"""

    def _proactive_chat(self):
        return _find_func(_parse(), "_proactive_chat")

    def test_bound_before_use(self):
        fn = self._proactive_chat()
        none_assign = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Constant)
            and n.value.value is None
            and any(
                isinstance(t, ast.Name) and t.id == "cron_event" for t in n.targets
            )
        ]
        self.assertTrue(
            none_assign, "_proactive_chat 必须存在 `cron_event = None` 前置绑定"
        )
        first_assign = min(none_assign)

        # 读取点：cron_event 作为 getattr 实参出现的位置
        reads = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "getattr"
            and n.args
            and isinstance(n.args[0], ast.Name)
            and n.args[0].id == "cron_event"
        ]
        self.assertTrue(reads, "应存在对 cron_event 的 getattr 读取")
        self.assertGreater(
            min(reads),
            first_assign,
            "cron_event 的读取必须晚于前置绑定（否则旧框架下 NameError）",
        )

    def test_guard_read_is_outside_pipeline_branch(self):
        """读取 cron_event 的语句不得位于 `if HAS_AGENT_PIPELINE:` 体内。"""
        fn = self._proactive_chat()
        guarded = None
        for n in ast.walk(fn):
            if (
                isinstance(n, ast.If)
                and isinstance(n.test, ast.Name)
                and n.test.id == "HAS_AGENT_PIPELINE"
            ):
                guarded = n
                break
        self.assertIsNotNone(guarded, "应存在 `if HAS_AGENT_PIPELINE:` 分支")
        span = (guarded.lineno, max(getattr(s, "lineno", 0) for s in ast.walk(guarded)))
        inner_reads = [
            n.lineno
            for n in ast.walk(guarded)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "getattr"
            and n.args
            and isinstance(n.args[0], ast.Name)
            and n.args[0].id == "cron_event"
        ]
        all_reads = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "getattr"
            and n.args
            and isinstance(n.args[0], ast.Name)
            and n.args[0].id == "cron_event"
        ]
        self.assertLess(
            len(inner_reads),
            len(all_reads),
            "至少有一个 cron_event 读取点必须位于 HAS_AGENT_PIPELINE 分支之外"
            "（防重复生成护栏），不能全在分支内",
        )


class TestRuleIdUnique(unittest.TestCase):
    """F3：_gen_id 同毫秒连续调用必须唯一。"""

    def test_unique_within_same_ms(self):
        from humanizer_core import humaneness_rules as hr

        ids = [hr._gen_id() for _ in range(50)]
        self.assertEqual(len(set(ids)), 50, f"rule id 出现碰撞: {ids}")

    def test_prefix_contract(self):
        from humanizer_core import humaneness_rules as hr

        self.assertTrue(hr._gen_id().startswith("r-"))


class TestLangMirrorCorruptProfile(unittest.TestCase):
    """F4：损坏画像的计数器不得抛异常（模块承诺的安全回落）。"""

    def test_observe_bad_counters(self):
        from humanizer_core import lang_mirror as lm

        p = lm.observe(
            {"phrase_freq": {}, "msg_count": "abc", "len_sum": None, "laugh_msgs": "x"},
            "哈哈哈哈哈 hello",
        )
        self.assertEqual(p["msg_count"], 1)
        self.assertIsInstance(p["len_sum"], int)

    def test_render_bad_counters(self):
        from humanizer_core import lang_mirror as lm

        # 不应抛异常；样本量解析失败按 0 处理 → 空串
        self.assertEqual(lm.build_lang_mirror_text({"msg_count": "x", "phrase_freq": {}}), "")

    def test_convergence_bad_counters(self):
        from humanizer_core import lang_mirror as lm

        self.assertEqual(lm.convergence({"msg_count": "abc", "phrase_freq": {}}), 0.0)


class TestLangProfileMemoryPruned(unittest.TestCase):
    """F5：语言画像剪枝结果必须回写内存，避免长期运行无界增长。

    v4.0 Phase 6：剪枝下沉 LangMirrorState.prune；回写改为**原地**
    clear+update（保持 main._lang_profiles 别名对象标识稳定，语义等价且
    更安全——旧写法重新赋值会让别名悬空）。契约钉在服务源码 + main 走服务。
    """

    _SVC = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "services",
        "lang_service.py",
    )

    def _svc_func(self, name):
        with open(self._SVC, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=self._SVC)
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == name:
                return n
        raise AssertionError(f"lang_service.py 缺函数 {name}")

    def test_prune_result_assigned_back(self):
        fn = _find_func(_parse(), "_time_flush_loop")
        src = _src(fn)
        # main 刷盘循环必须经状态服务剪枝
        self.assertIn("_lang_mirror", src, "刷盘循环应经状态服务剪枝")
        self.assertIn("prune", src, "刷盘循环应调用剪枝")
        # 服务内必须把剪枝结果回写内存（原地 clear+update 同一对象）
        prune_fn = self._svc_func("prune")
        calls = [
            n
            for n in ast.walk(prune_fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "profiles"
        ]
        attrs = {c.func.attr for c in calls}
        self.assertIn("clear", attrs, "剪枝结果必须回写内存（清空旧项）")
        self.assertIn("update", attrs, "剪枝结果必须回写内存（写入保留项）")


class TestRetrievalTimeoutDefault(unittest.TestCase):
    """F6：代码回落默认值必须与 _conf_schema.json 的 5 秒一致。"""

    def test_code_default_is_5(self):
        """只看 `self._cfg("retrieval_timeout", <默认>)` 与 `rt_timeout = <默认>` 两处。"""
        fn = _find_func(_parse(), "_retrieve_examples")
        defaults = []
        for n in ast.walk(fn):
            # self._cfg("retrieval_timeout", <默认>)
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "_cfg"
                and n.args
                and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == "retrieval_timeout"
                and len(n.args) > 1
                and isinstance(n.args[1], ast.Constant)
            ):
                defaults.append(n.args[1].value)
            # rt_timeout = <默认>（try/except 与非法值回落分支）
            if (
                isinstance(n, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "rt_timeout" for t in n.targets
                )
                and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, (int, float))
            ):
                defaults.append(n.value.value)
        self.assertTrue(defaults, "应能找到 retrieval_timeout 的回落默认值")
        for d in defaults:
            self.assertEqual(
                float(d), 5.0, f"retrieval_timeout 回落默认值应为 5.0，实际 {d}"
            )

    def test_schema_default_is_5(self):
        import json

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "_conf_schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        item = (schema.get("style") or {}).get("items", {}).get("retrieval_timeout", {})
        self.assertEqual(item.get("default"), 5, "schema 默认值应为 5")


class TestGroupMergeKeepsUnknownKeys(unittest.TestCase):
    """F7：旧组里未列入搬运清单的键必须兜底搬入目标组，不得静默丢失。"""

    def test_unknown_key_survives(self):
        from humanizer_core.config_migrate import migrate_group_merges

        cfg = {
            "life": {"enable_life": True, "some_future_key": "keepme"},
            "debounce": {"debounce_time": 3, "extra_key": 7},
        }
        changed = migrate_group_merges(cfg)
        self.assertTrue(changed)
        self.assertNotIn("life", cfg)
        self.assertNotIn("debounce", cfg)
        self.assertEqual(cfg["time"]["some_future_key"], "keepme")
        self.assertEqual(cfg["typing"]["extra_key"], 7)
        self.assertEqual(cfg["typing"]["debounce_time"], 3)

    def test_existing_target_not_overwritten(self):
        from humanizer_core.config_migrate import migrate_group_merges

        cfg = {"life": {"some_future_key": "old"}, "time": {"some_future_key": "new"}}
        migrate_group_merges(cfg)
        self.assertEqual(cfg["time"]["some_future_key"], "new")


class TestGroupMergeRenamedKeyNotDuplicated(unittest.TestCase):
    """v4.0.2：改名键搬运后不得在目标组以旧名再兜底抄一份（同义键并存）。

    v4.0.1 修复的回归钉子——此前只测「未知键存活」，未测「改名键不双写」。
    改名例：commitments.extract_model → proactive.commitments_extract_model。
    """

    def test_renamed_key_not_duplicated(self):
        from humanizer_core.config_migrate import migrate_group_merges

        cfg = {"commitments": {"extract_model": "cm", "extract_timeout": 90}}
        self.assertTrue(migrate_group_merges(cfg))
        proactive = cfg["proactive"]
        self.assertEqual(proactive["commitments_extract_model"], "cm")
        self.assertEqual(proactive["commitments_extract_timeout"], 90)
        self.assertNotIn("extract_model", proactive, "旧名不得兜底搬入（同义键并存）")
        self.assertNotIn("extract_timeout", proactive)
        self.assertNotIn("commitments", cfg)

    def test_renamed_and_kept_name_mix(self):
        """同组内改名键（extract_model）与保名键（llm_confirm）混合：都不双写。"""
        from humanizer_core.config_migrate import migrate_group_merges

        cfg = {"commitments": {"llm_confirm": True, "extract_model": "m2"}}
        migrate_group_merges(cfg)
        proactive = cfg["proactive"]
        self.assertEqual(proactive["llm_confirm"], True)
        self.assertEqual(proactive["commitments_extract_model"], "m2")
        self.assertNotIn("extract_model", proactive)

    def test_life_extract_model_rename(self):
        """life.extract_model → time.life_extract_model（另一改名例，防单点覆盖）。"""
        from humanizer_core.config_migrate import migrate_group_merges

        cfg = {"life": {"extract_model": "lm"}}
        migrate_group_merges(cfg)
        self.assertEqual(cfg["time"]["life_extract_model"], "lm")
        self.assertNotIn("extract_model", cfg["time"])

    def test_unknown_key_still_carried_alongside_rename(self):
        """改名的同时未知键照旧兜底（两机制互不吞噬）。"""
        from humanizer_core.config_migrate import migrate_group_merges

        cfg = {"commitments": {"extract_model": "cm", "brand_new_key": 1}}
        migrate_group_merges(cfg)
        proactive = cfg["proactive"]
        self.assertEqual(proactive["commitments_extract_model"], "cm")
        self.assertEqual(proactive["brand_new_key"], 1)


class TestDeadCodeRemoved(unittest.TestCase):
    """清理类：死方法与未用 import 不应回潮。"""

    def test_commit_pending_removed(self):
        tree = _parse()
        names = {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("_commit_pending", names, "死方法 _commit_pending 应已删除")

    def test_unused_imports_removed(self):
        tree = _parse()
        imported = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                for a in n.names:
                    imported.add(a.asname or a.name)
        self.assertNotIn("due_for_date", imported, "due_for_date 未使用，应移除")
        self.assertNotIn("ProviderRequest", imported, "ProviderRequest 未使用，应移除")

    def test_kb_desc_not_duplicated_in_ensure_kb(self):
        fn = _find_func(_parse(), "_ensure_kb")
        calls = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_kb_desc"
        ]
        self.assertEqual(
            calls, [], f"_ensure_kb 不应再重复计算 _kb_desc（后台任务会算）：行 {calls}"
        )


if __name__ == "__main__":
    unittest.main()
