# -*- coding: utf-8 -*-
"""v4.0.3 回归钉子：2026-09-19 审查修复批（v4.0.6 对账更新）。

覆盖（每条对应审查报告编号）：
- W-2 僵尸端点清理：v4.0.4 有意恢复 styles/build 与 models 两族兼容入口
  （路由表 17→20），唯一不得回潮的是已并入 styles/generate 的
  styles/import-colleague；
- W-4 KBService 单一入口：v4.0.4 服务化反转——实现本体搬入服务，
  私有名从"禁止"变"锚定"（别名必须是同引用绑定，防再出第二套副本）；
- W-1 凭据副本护栏：插件目录出现 data/cmd_config.json 时启动必须告警
  （v4.0.4 重构时被误删，v4.0.6 恢复）；
- W-5 旧知识库提示：新建 `human_style_*` 库时给出旧库残留提示
  （v4.0.4 重写时丢失，v4.0.6 补回）；
- W-3 承诺簿 docstring：不得再引用从未实现的 `main._life_commitment_check`。

约定与既有接线测试一致：main.py 用 AST/源码文本断言，不 import（本机无 astrbot 包）。
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from web_api import ROUTE_SPECS, HumanizerWebAPI  # noqa: E402

_MAIN_SRC = (_ROOT / "main.py").read_text(encoding="utf-8")
_MAIN_TREE = ast.parse(_MAIN_SRC)
_SERVICE_SRC = (_ROOT / "services" / "kb_service.py").read_text(encoding="utf-8")
_SERVICE_TREE = ast.parse(_SERVICE_SRC)


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 未找到")


class TestZombieEndpointsRemoved:
    """W-2（v4.0.6 对账）：路由表 20 条；唯一真僵尸是已并入
    styles/generate(source=colleague) 的 styles/import-colleague。
    styles/build 与 models 两族是 v4.0.4 有意恢复的兼容入口，不再视为僵尸。"""

    ZOMBIES = (
        "styles/import-colleague",
    )

    def test_route_count_is_19(self):
        assert len(ROUTE_SPECS) == 19, f"路由表应为 19 条，实际 {len(ROUTE_SPECS)}"

    def test_zombie_suffixes_absent_from_route_specs(self):
        suffixes = {s for s, _, _, _ in ROUTE_SPECS}
        assert not (set(self.ZOMBIES) & suffixes), "僵尸端点回流到路由表"

    def test_every_route_method_exists(self):
        """路由表引用的方法必须都在类体里（v2.9.4 编辑错位事故防线）。"""
        class _P:
            pass

        api = HumanizerWebAPI(_P())
        for suffix, attr, _methods, _desc in ROUTE_SPECS:
            assert callable(getattr(api, attr, None)), f"缺少端点方法: {attr}（{suffix}）"

    def test_zombie_handlers_deleted_from_web_api(self):
        handlers = {n.name for n in ast.walk(ast.parse(
            (_ROOT / "web_api.py").read_text(encoding="utf-8")
        )) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        # v4.0.4 恢复了 build_style/list_models 兼容入口；v4.1.0 移除深度改写后
        # models/set-rewrite 一并撤除。import_colleague 已并入
        # styles/generate(source=colleague)，不得回流。
        assert "import_colleague" not in handlers, "僵尸端点方法未删除: import_colleague"

    def test_kept_endpoints_still_present(self):
        suffixes = {s for s, _, _, _ in ROUTE_SPECS}
        for keep in ("styles/generate", "styles/correct", "config", "dashboard", "rules", "rules/save"):
            assert keep in suffixes, f"在用的端点被误删: {keep}"


class TestKbServiceSingleEntryPoint:
    """W-4（v4.0.6 对账）：v4.0.4 服务化把实现本体搬入 KBService，
    私有名从"禁止出现"反转为"结构锚定"——别名必须与公开名**同引用绑定**
    （`self._kb_ready = self.ready`），且状态容器别名只在 __init__ 绑定，
    防止将来某处再赋新对象造出第二套状态。"""

    STATE_ALIASES = {
        "_kb_ready": "ready",
        "_kb_syncing": "syncing",
        "_kb_rerank_applied": "rerank_applied",
        "_kb_generations": "generations",
        "_kb_index_state": "index_state",
        "_retrieve_cache": "retrieve_cache",
        "_kb_tasks": "tasks",
    }
    # 值缓存（非状态容器）：__init__ 别名绑定 + 方法内允许更新值
    VALUE_CACHE_ALIASES = {
        "_corpus_hint_cache": "corpus_hint_cache",
        "_corpus_fp_cache": "corpus_fingerprint_cache",
    }
    IMPL_METHODS = (
        "_current_index_fingerprint", "_kb_index_fresh", "_invalidate_kb_index",
        "_persist_kb_state", "_kb_name", "_kb_desc", "_resolve_embedding_provider",
        "_list_all_kb_docs", "_ensure_kb", "_kick_kb_sync", "_rerank_drift",
        "_kb_sync_job", "_kb_retrieve_section",
    )

    def test_state_aliases_are_same_object_bindings(self):
        init = _func(_SERVICE_TREE, "__init__")
        bindings = {}
        for node in ast.walk(init):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr in (
                        set(self.STATE_ALIASES.values())
                        | set(self.VALUE_CACHE_ALIASES.values())
                    )
                ):
                    bindings[target.attr] = node.value.attr
        for alias, public in (
            self.STATE_ALIASES | self.VALUE_CACHE_ALIASES
        ).items():
            assert bindings.get(alias) == public, (
                f"别名 {alias} 必须在 __init__ 与公开名 {public} 同引用绑定，"
                f"实际绑定: {bindings.get(alias)!r}"
            )

    def test_state_container_aliases_bound_only_in_init(self):
        """状态容器别名不得在方法体内再赋值（值缓存除外）。"""
        init = _func(_SERVICE_TREE, "__init__")
        init_lo, init_hi = init.lineno, init.end_lineno
        offenders = []
        for node in ast.walk(_SERVICE_TREE):
            if not isinstance(node, ast.Assign):
                continue
            if init_lo <= node.lineno <= init_hi:
                continue  # __init__ 的同引用绑定是唯一合法落点
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr in self.STATE_ALIASES
                ):
                    offenders.append(f"L{node.lineno}: {target.attr}")
        assert not offenders, f"状态容器别名在方法体内被再赋值: {offenders}"

    def test_private_impl_methods_present(self):
        """v4.0.4 服务化：实现本体在服务内，这些私有方法必须存在。"""
        defined = {
            n.name for n in ast.walk(_SERVICE_TREE)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = sorted(set(self.IMPL_METHODS) - defined)
        assert not missing, f"服务实现方法缺失: {missing}"

    def test_public_api_intact(self):
        from services.kb_service import KBService

        for name in (
            "ensure", "kick_sync", "sync_job", "rerank_drift", "invalidate_index",
            "invalidate_ready", "forget", "shutdown", "index_fresh",
            "current_index_fingerprint", "persist_index_state", "retrieve_section",
            "list_all_kb_docs", "kb_name_for_style", "kb_description_for_rows",
            "resolve_embedding_provider",
        ):
            assert callable(getattr(KBService, name, None)), f"公开入口缺失: {name}"

    def test_state_objects_are_public_names(self):
        from services.kb_service import KBService

        svc = KBService()
        svc.ready["a"] = True
        svc.syncing.add("a")
        assert "a" in svc.ready and "a" in svc.syncing


class TestStrayRuntimeConfigGuard:
    """W-1：插件目录残留含凭据的主配置副本时，启动必须告警（不自动删文件）。"""

    def test_helper_defined_and_called(self):
        init = _func(_MAIN_TREE, "__init__")
        called = {
            n.func.attr for n in ast.walk(init)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert "_warn_stray_runtime_config" in called, "启动未调用残留配置护栏"

    def test_warning_mentions_path_and_advice(self):
        fn = _func(_MAIN_TREE, "_warn_stray_runtime_config")
        texts = [
            n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        joined = " ".join(texts)
        assert "data" in joined and "cmd_config.json" in joined, "告警未指出残留路径"
        assert "打包" in joined or "分享" in joined, "告警缺少可操作建议"
        # 只告警不删除：方法体内不得出现 unlink/remove/rmtree
        dumped = ast.dump(fn)
        for danger in ("unlink", "rmtree", "os.remove"):
            assert danger not in dumped, f"护栏不得自动删除文件（发现 {danger}）"


class TestOrphanKbHint:
    """W-5：新建知识库时提示旧 human_style_* 库残留（只提示不删除）。"""

    def test_hint_present_in_sync_job(self):
        assert "旧的 human_style_* 知识库不会自动清理" in _SERVICE_SRC

    def test_no_kb_deletion_api_called(self):
        dumped = ast.dump(_func(_SERVICE_TREE, "sync_job"))
        for danger in ("delete_kb", "remove_kb", "rmtree"):
            assert danger not in dumped, f"知识库生命周期不得自动删除（发现 {danger}）"




if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
