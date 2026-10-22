# -*- coding: utf-8 -*-
"""Behavioral tests for the dependency-injected KB service."""

import asyncio
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from humanizer_core.kb_state import corpus_signature, index_fingerprint
from services.kb_service import KBPorts, KBService


class FakeDoc:
    def __init__(self, name, doc_id=None):
        self.doc_name = name
        self.doc_id = doc_id or name + "-id"


class FakeKbInfo:
    def __init__(self, description="old", rerank_provider_id=None, kb_id="id"):
        self.description = description
        self.rerank_provider_id = rerank_provider_id
        self.kb_id = kb_id


class FakeKb:
    def __init__(self, name, description="old", rerank_provider_id=None):
        self.name = name
        self.kb = FakeKbInfo(description, rerank_provider_id, name + "-id")
        self.docs = []
        self.uploads = []
        self.deletes = []
        self.fail_upload = False
        self.list_error = None

    async def list_documents(self, offset=0, limit=100):
        if self.list_error is not None:
            raise self.list_error
        return self.docs[offset : offset + limit]

    async def count_documents(self):
        return len(self.docs)

    async def delete_document(self, doc_id):
        self.deletes.append(doc_id)
        self.docs = [d for d in self.docs if d.doc_id != doc_id]

    async def upload_document(self, **kwargs):
        if self.fail_upload:
            raise RuntimeError("upload failed")
        self.uploads.append(kwargs)
        self.docs.append(FakeDoc(kwargs["file_name"]))


class FakeManager:
    def __init__(self, kb=None):
        self.kb = kb
        self.create_calls = []
        self.update_calls = []
        self.get_calls = []
        self.create_error = None
        self.update_returns_new = False

    async def get_kb_by_name(self, name):
        self.get_calls.append(name)
        return self.kb

    async def create_kb(self, name, **kwargs):
        if self.create_error is not None:
            raise self.create_error
        self.create_calls.append((name, kwargs))
        self.kb = FakeKb(
            name,
            description=kwargs.get("description"),
            rerank_provider_id=kwargs.get("rerank_provider_id"),
        )
        return self.kb

    async def update_kb(self, kb_id, name, **kwargs):
        self.update_calls.append((kb_id, name, kwargs))
        if self.update_returns_new:
            new = FakeKb(
                name,
                description=kwargs.get("description"),
                rerank_provider_id=kwargs.get("rerank_provider_id"),
            )
            new.docs = list(self.kb.docs)
            self.kb = new
            return new
        self.kb.kb.description = kwargs.get("description")
        self.kb.kb.rerank_provider_id = kwargs.get("rerank_provider_id")
        return self.kb


class FakeTask:
    def __init__(self):
        self.callbacks = []
        self.done = False

    def add_done_callback(self, callback):
        self.callbacks.append(callback)


class TestKBService(unittest.TestCase):
    def setUp(self):
        self.config = {"create_kb": True, "rerank_provider_id": ""}
        self.rows = [
            {"source": "builtin", "content": "builtin one"},
            {"source": "builtin", "content": "builtin two"},
            {"source": "user", "content": "user one"},
        ]
        self.manager = FakeManager()
        self.persisted = []
        self.hint = ["initial"]

        def fingerprint(rows, embedding):
            return embedding + "|" + "|".join(
                str(row.get("content", "")) for row in rows
            )

        self.service = KBService(
            KBPorts(
                config_getter=lambda key, default=None: self.config.get(key, default),
                effective_corpus_rows=lambda: list(self.rows),
                kb_name=lambda style: "kb_" + style,
                kb_description=lambda style, rows: "desc:" + style + ":" + str(len(rows)),
                embedding_provider_resolver=lambda: "embed-v1",
                fingerprint_calculator=fingerprint,
                persist_index_state=lambda state: self.persisted.append(
                    {key: dict(value) for key, value in state.items()}
                ),
                kb_manager=self.manager,
                corpus_hint=lambda: tuple(self.hint),
                upload_group_size=2,
            )
        )
        self.kb_name = "kb_style"

    def run_job(self, generation=1):
        self.service.generations[self.kb_name] = generation
        self.service.syncing.add(self.kb_name)
        asyncio.run(self.service.sync_job(self.kb_name, "style", generation))

    def test_startup_race_is_silent_then_runtime_negative_cache(self):
        calls = []
        self.service.ports.embedding_provider_resolver = lambda: calls.append(1) or ""
        self.service.framework_loaded = False
        self.assertIsNone(asyncio.run(self.service.ensure(self.kb_name, "style")))
        self.assertNotIn(self.kb_name, self.service.ready)
        self.service.framework_loaded = True
        self.assertIsNone(asyncio.run(self.service.ensure(self.kb_name, "style")))
        self.assertEqual(self.service.ready[self.kb_name], False)
        count = len(calls)
        self.assertIsNone(asyncio.run(self.service.ensure(self.kb_name, "style")))
        self.assertEqual(len(calls), count, "negative cache must avoid provider probing")

    def test_force_bypasses_create_kb_disabled(self):
        """v4.1.9：/style_index 手动重建不受 create_kb 自动建库开关限制。"""
        self.config["create_kb"] = False
        self.assertIsNone(asyncio.run(self.service.ensure(self.kb_name, "style")))
        self.assertFalse(self.service.ready[self.kb_name])

        created = []

        def fake_create_task(coro):
            created.append(coro)
            coro.close()  # 不真正调度，避免 asyncio.run 结束时遗留未 await 协程
            return FakeTask()

        self.service.ports.create_task = fake_create_task
        self.assertIsNone(
            asyncio.run(self.service.ensure(self.kb_name, "style", force=True))
        )
        self.assertIn(self.kb_name, self.service.syncing)
        self.assertEqual(len(created), 1, "force=True 应受理并启动后台同步")

    def test_ready_fingerprint_short_circuit_and_stale_invalidation(self):
        self.service.ready[self.kb_name] = True
        self.service.index_state[self.kb_name] = {
            "fingerprint": self.service.current_index_fingerprint()
        }
        calls = []
        self.service.kick_sync = lambda name, style: calls.append((name, style))
        self.assertEqual(
            asyncio.run(self.service.ensure(self.kb_name, "style")), self.kb_name
        )
        self.assertEqual(calls, [])
        self.rows[0]["content"] = "changed"
        self.assertIsNone(asyncio.run(self.service.ensure(self.kb_name, "style")))
        self.assertEqual(self.service.ready[self.kb_name], False)
        self.assertEqual(calls, [(self.kb_name, "style")])

    def test_rerank_drift_reads_reality_once(self):
        self.manager.kb = FakeKb(self.kb_name, rerank_provider_id="rr-old")
        self.config["rerank_provider_id"] = "rr-old"
        self.assertFalse(asyncio.run(self.service.rerank_drift(self.kb_name)))
        self.config["rerank_provider_id"] = "rr-new"
        self.assertTrue(asyncio.run(self.service.rerank_drift(self.kb_name)))
        self.assertEqual(self.service.rerank_applied[self.kb_name], "rr-old")

    def test_create_and_upload_groups_then_reuse_and_update(self):
        self.config["rerank_provider_id"] = "rr-new"
        self.run_job()
        self.assertEqual(len(self.manager.create_calls), 1)
        self.assertEqual(len(self.manager.kb.uploads), 2)
        self.assertTrue(self.service.ready[self.kb_name])
        self.assertIn(self.kb_name, self.service.index_state)
        self.manager.update_returns_new = True
        self.manager.kb.kb.description = "stale"
        self.manager.kb.kb.rerank_provider_id = "rr-old"
        self.run_job(generation=2)
        self.assertEqual(len(self.manager.create_calls), 1)
        self.assertEqual(len(self.manager.update_calls), 1)
        self.assertEqual(self.manager.update_calls[0][1], self.kb_name)
        self.assertEqual(self.manager.kb.kb.rerank_provider_id, "rr-new")

    def test_marker_claim_without_upload(self):
        self.manager.kb = FakeKb(self.kb_name, description="desc:style:3")
        self.manager.kb.docs = [
            FakeDoc(self.kb_name + "__内置_0.txt"),
            FakeDoc(self.kb_name + "__用户_0.txt"),
        ]
        self.run_job()
        self.assertEqual(self.manager.kb.uploads, [])
        self.assertEqual(self.manager.kb.deletes, [])
        self.assertTrue(self.service.ready[self.kb_name])
        self.assertEqual(len(self.persisted), 1)

    def test_incomplete_group_is_deleted_and_reuploaded(self):
        self.rows.append({"source": "builtin", "content": "builtin three"})
        self.manager.kb = FakeKb(self.kb_name, description="desc:style:3")
        self.manager.kb.docs = [
            FakeDoc(self.kb_name + "__内置_0.txt", "old-builtin"),
            FakeDoc(self.kb_name + "__用户_0.txt", "keep-user"),
        ]
        self.service.index_state[self.kb_name] = {
            "fingerprint": self.service.current_index_fingerprint()
        }
        self.run_job()
        self.assertEqual(self.manager.kb.deletes, ["old-builtin"])
        # Current main behavior reuploads both source groups after deleting the
        # incomplete one; this preserves that idempotent recovery path.
        self.assertEqual(len(self.manager.kb.uploads), 3)
        self.assertEqual(
            sum(
                upload["file_name"].startswith(self.kb_name + "__内置_")
                for upload in self.manager.kb.uploads
            ),
            2,
        )
        self.assertIn("keep-user", [d.doc_id for d in self.manager.kb.docs])

    def test_upload_failure_leaves_false_ready(self):
        self.manager.kb = FakeKb(self.kb_name)
        self.manager.kb.fail_upload = True
        self.service.ready[self.kb_name] = True
        self.run_job()
        self.assertFalse(self.service.ready[self.kb_name])
        self.assertNotIn(self.kb_name, self.service.syncing)
        self.assertNotIn(self.kb_name, self.service.index_state)

    def test_no_user_source_reuses_existing_count(self):
        """无用户语料来源时，已有文档的知识库视为已同步（旧 `user_cnt == 0` 分支）。"""

        class _Bare:
            def __init__(self):
                self.docs = [FakeDoc("existing.txt")]
                self.uploads = []

            async def count_documents(self):
                return len(self.docs)

        # 无 list_documents 方法 → can_list False → 走 user_cnt==0 复用分支
        kb = _Bare()
        self.rows = [{"source": "builtin", "content": "b1"}]
        self.manager.kb = kb
        self.run_job()
        self.assertTrue(self.service.ready[self.kb_name])
        self.assertEqual(kb.uploads, [])

    def test_list_failure_logs_warning_and_retries(self):
        """完整性检测异常必须留痕并回退重传（旧静默 pass → warning）。

        注意：**逐页** list_documents 异常由 iter_all_documents 按设计吞掉
        （返回部分结果，与备份一致）；这里的 warning 针对完整性检测块本身的
        异常（如枚举入口抛错）。用注入的枚举端口抛错复现该路径。
        """
        logs = []

        async def boom(_kb):
            raise RuntimeError("enumeration entry failed")

        self.service.ports.logger = type(
            "L", (), {"warning": lambda _s, m: logs.append(m), "debug": lambda _s, m: None}
        )()
        self.service.ports.list_all_documents = boom
        self.manager.kb = FakeKb(self.kb_name, description="desc:style:3")
        self.run_job()
        self.assertTrue(
            any("已同步检测失败" in m for m in logs),
            f"完整性检测异常必须留痕，实得: {logs}",
        )
        # 仍回退整库重传
        self.assertTrue(self.manager.kb.uploads)

    def test_generation_stale_job_cannot_touch_state(self):
        self.service.generations[self.kb_name] = 2
        self.service.syncing.add(self.kb_name)
        self.service.ready[self.kb_name] = True
        asyncio.run(self.service.sync_job(self.kb_name, "style", generation=1))
        self.assertEqual(self.manager.create_calls, [])
        self.assertTrue(self.service.ready[self.kb_name])
        self.assertIn(self.kb_name, self.service.syncing)

    def test_kick_tracks_generation_and_task_and_cleanup(self):
        async def exercise():
            task = self.service.kick_sync(self.kb_name, "style")
            self.assertEqual(self.service.generations[self.kb_name], 1)
            self.assertIn(self.kb_name, self.service.syncing)
            self.assertIn(task, self.service.tasks)
            await task
            await asyncio.sleep(0)
            self.assertNotIn(self.kb_name, self.service.syncing)
            self.assertNotIn(task, self.service.tasks)

        asyncio.run(exercise())

    def test_syncing_cleanup_on_manager_failure(self):
        self.manager.create_error = RuntimeError("create failed")
        self.service.generations[self.kb_name] = 1
        self.service.syncing.add(self.kb_name)
        asyncio.run(self.service.sync_job(self.kb_name, "style", 1))
        self.assertNotIn(self.kb_name, self.service.syncing)
        self.assertFalse(self.service.ready[self.kb_name])


class TestDefaultFingerprintCache(unittest.TestCase):
    def setUp(self):
        self.rows = [{"source": "builtin", "content": "first"}]
        self.hint = [1]
        self.embedding = ["embed-v1"]
        self.reads = 0

        def get_rows():
            self.reads += 1
            return list(self.rows)

        self.service = KBService(
            KBPorts(
                effective_corpus_rows=get_rows,
                embedding_provider_resolver=lambda: self.embedding[0],
                corpus_hint=lambda: tuple(self.hint),
            )
        )

    def test_reuses_signature_until_corpus_hint_changes(self):
        signature = corpus_signature(self.rows)
        first = self.service.current_index_fingerprint()
        self.assertEqual(first, index_fingerprint(signature, "embed-v1"))
        self.assertEqual(self.service.corpus_fingerprint_cache, signature)
        self.assertEqual(self.service.current_index_fingerprint(), first)
        self.assertEqual(self.reads, 1)

        self.embedding[0] = "embed-v2"
        self.assertEqual(
            self.service.current_index_fingerprint(),
            index_fingerprint(signature, "embed-v2"),
        )
        self.assertEqual(self.reads, 1)

        self.rows[0]["content"] = "changed"
        self.hint[0] += 1
        self.assertEqual(
            self.service.current_index_fingerprint(),
            index_fingerprint(corpus_signature(self.rows), "embed-v2"),
        )
        self.assertEqual(self.service.corpus_fingerprint_cache, corpus_signature(self.rows))
        self.assertEqual(self.reads, 2)

    def test_invalidation_clears_signature_and_retrieval_cache(self):
        class RetrievalCache:
            def __init__(self):
                self.clears = 0

            def clear(self):
                self.clears += 1

        cache = RetrievalCache()
        self.service.retrieve_cache = cache
        self.service.current_index_fingerprint()
        self.service.ready["kb"] = True
        self.service.invalidate_index()
        self.assertIsNone(self.service.corpus_fingerprint_cache)
        self.assertIsNone(self.service.corpus_hint_cache)
        self.assertEqual(self.service.ready, {})
        self.assertEqual(cache.clears, 1)
        self.service.current_index_fingerprint()
        self.assertEqual(self.reads, 2)

    def test_main_uses_default_fingerprint_with_file_hint(self):
        import ast
        from pathlib import Path

        main = Path(__file__).resolve().parent.parent / "main.py"
        tree = ast.parse(main.read_text(encoding="utf-8"))
        kb_ports = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "KBPorts"
        ]
        self.assertEqual(len(kb_ports), 1)
        keys = {keyword.arg for keyword in kb_ports[0].keywords}
        self.assertIn("corpus_hint", keys)
        self.assertNotIn("fingerprint_calculator", keys)


if __name__ == "__main__":
    unittest.main()
