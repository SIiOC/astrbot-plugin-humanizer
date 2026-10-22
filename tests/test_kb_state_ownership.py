# -*- coding: utf-8 -*-
"""v4.0：KB 状态所有权收口契约。

背景：KBService 接入后，main 仍残留三处直接改 KB 状态（rerank 漂移置
ready=False、/style_index 手动清状态、terminate 清就绪表+取消任务）。
本文件钉死"状态变更必须经服务方法"，并验证：
- main 的 legacy 别名与服务持有的是**同一对象**（不是副本）；
- forget/invalidate_ready/shutdown 三个所有权出口的行为；
- 运行期未配置 embedding 的 warning 文案含配置指引（v3.4.7 语义不缩水）。
"""

import ast
import asyncio
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from services.kb_service import KBPorts, KBService


def _main_tree():
    with open(os.path.join(_ROOT, "main.py"), encoding="utf-8") as f:
        return ast.parse(f.read())


def _service_tree():
    with open(os.path.join(_ROOT, "services", "kb_service.py"), encoding="utf-8") as f:
        return ast.parse(f.read())


def _func(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} 未找到")


class TestMainNoDirectKbMutation(unittest.TestCase):
    """main 不得再直接 pop/clear/下标赋值 KB 状态；只允许只读 get 与别名绑定。"""

    MUTATING = ("_kb_ready", "_kb_syncing", "_kb_rerank_applied", "_kb_generations", "_kb_tasks")

    def test_no_direct_state_mutation_outside_init(self):
        tree = _main_tree()
        init = _func(tree, "__init__")
        # ast.arguments 等节点没有 lineno（子节点继承父行号），故用 getattr 过滤
        init_lines = {
            n.lineno for n in ast.walk(init) if getattr(n, "lineno", None) is not None
        }
        offenders = []
        for n in ast.walk(tree):
            lineno = getattr(n, "lineno", None)
            if lineno is None or lineno in init_lines:
                continue
            # X[...] = ... 形式的下标赋值
            if isinstance(n, (ast.Assign, ast.AnnAssign)):
                targets = [n.target] if isinstance(n, ast.AnnAssign) else n.targets
                for t in targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute):
                        if t.value.attr in self.MUTATING:
                            offenders.append((t.value.attr, lineno))
            # X.pop(...) / X.clear() 形式
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                recv = n.func.value
                if isinstance(recv, ast.Attribute) and recv.attr in self.MUTATING:
                    if n.func.attr in ("pop", "clear", "discard", "add", "update"):
                        offenders.append((recv.attr + "." + n.func.attr, lineno))
        self.assertEqual(offenders, [], f"main 仍直接变更 KB 状态: {offenders}")

    def test_attribute_aliases_are_same_objects(self):
        """618-622 行只是把 legacy 名绑到服务同一对象，不是新建容器。"""
        init = _func(_main_tree(), "__init__")
        pairs = {"_kb_ready": "ready", "_kb_syncing": "syncing"}
        seen = {}
        for n in ast.walk(init):
            if (
                isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Attribute)
                and isinstance(n.value.value, ast.Attribute)
                and n.value.value.attr == "_kb_service"
            ):
                for t in n.targets:
                    if isinstance(t, ast.Attribute) and t.attr in pairs:
                        seen[t.attr] = n.value.attr
        for legacy, svc_name in pairs.items():
            self.assertEqual(
                seen.get(legacy), svc_name, f"{legacy} 必须绑定服务同名属性（同一对象）"
            )

    def test_terminate_and_style_index_go_through_service(self):
        tree = _main_tree()
        term = ast.dump(_func(tree, "terminate"))
        self.assertIn("_kb_service", term)
        self.assertIn("shutdown", term)
        style_index = ast.dump(_func(tree, "style_index"))
        self.assertIn("forget", style_index)


class TestServiceOwnershipMethods(unittest.TestCase):
    def setUp(self):
        self.persisted = []
        self.service = KBService(
            KBPorts(
                config_getter=lambda k, d=None: d,
                persist_index_state=lambda state: self.persisted.append(dict(state)),
            )
        )
        self.name = "kb_x"

    def test_invalidate_ready_marks_false(self):
        self.service.ready[self.name] = True
        self.service.invalidate_ready(self.name)
        self.assertFalse(self.service.ready[self.name])

    def test_forget_clears_all_and_persists(self):
        self.service.ready[self.name] = True
        self.service.rerank_applied[self.name] = "rr"
        self.service.index_state[self.name] = {"fingerprint": "fp"}
        self.service.forget(self.name)
        self.assertNotIn(self.name, self.service.ready)
        self.assertNotIn(self.name, self.service.rerank_applied)
        self.assertNotIn(self.name, self.service.index_state)
        self.assertEqual(len(self.persisted), 1, "forget 必须落盘一次（清指纹生效）")

    def test_shutdown_clears_and_returns_tasks(self):
        self.service.ready[self.name] = True
        self.service.syncing.add(self.name)
        marker = object()
        self.service.tasks.add(marker)
        tasks = self.service.shutdown()
        self.assertEqual(tasks, [marker], "shutdown 必须交回待取消任务")
        self.assertEqual(self.service.ready, {})
        self.assertEqual(self.service.syncing, set())
        self.assertEqual(self.service.tasks, set())


class TestRuntimeWarningKeepsGuidance(unittest.TestCase):
    def test_warning_mentions_astrbot_setting(self):
        fn = _func(_service_tree(), "ensure")
        texts = []
        for n in ast.walk(fn):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "_log"
                and len(n.args) >= 2
                and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == "warning"
            ):
                for a in n.args[1:]:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        texts.append(a.value)
        joined = " ".join(texts)
        self.assertIn("未配置 embedding provider", joined)
        self.assertIn("AstrBot 设置中配置 embedding", joined, "运行期提示必须保留配置指引")


if __name__ == "__main__":
    unittest.main()
