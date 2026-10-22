# -*- coding: utf-8 -*-
"""v3.9.5 新纯函数模块测试：kb_state / retrieve_cache / llm_budget / task_registry。"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core.kb_state import (
    INDEX_SCHEMA_VERSION,
    corpus_signature,
    file_hint,
    index_fingerprint,
    load_state,
    save_state,
)
from humanizer_core.retrieve_cache import RetrieveCache
from humanizer_core.task_registry import TaskRegistry


class TestKbState(unittest.TestCase):
    def test_signature_stable_and_order_sensitive(self):
        rows = [{"source": "builtin", "content": "a"}, {"source": "user", "content": "b"}]
        self.assertEqual(corpus_signature(rows), corpus_signature(list(rows)))
        self.assertNotEqual(
            corpus_signature(rows), corpus_signature(list(reversed(rows)))
        )

    def test_content_change_changes_signature(self):
        a = [{"source": "b", "content": "x"}]
        b = [{"source": "b", "content": "y"}]
        self.assertNotEqual(corpus_signature(a), corpus_signature(b))

    def test_garbage_rows_ignored(self):
        self.assertEqual(
            corpus_signature(["junk", None, {"source": "u", "content": "c"}]),
            corpus_signature([{"content": "c", "source": "u"}]),
        )

    def test_fingerprint_embedding_matters(self):
        sig = corpus_signature([{"source": "b", "content": "x"}])
        self.assertNotEqual(
            index_fingerprint(sig, "emb-a"), index_fingerprint(sig, "emb-b")
        )
        self.assertEqual(
            index_fingerprint(sig, "emb-a"), index_fingerprint(sig, "emb-a")
        )

    def test_file_hint(self):
        with tempfile.TemporaryDirectory(prefix="kbh_") as d:
            p = Path(d) / "x.jsonl"
            p.write_text("hello", encoding="utf-8")
            h1 = file_hint(p)
            self.assertNotEqual(h1, (0, 0))
            p.write_text("hello world!", encoding="utf-8")
            self.assertNotEqual(h1, file_hint(p))
        self.assertEqual(file_hint(Path(d) / "missing"), (0, 0))

    def test_state_roundtrip_and_corrupt(self):
        with tempfile.TemporaryDirectory(prefix="kbs_") as d:
            p = Path(d) / "kb_index_state.json"
            save_state(p, {"kb1": {"fingerprint": "ff"}})
            self.assertEqual(load_state(p)["kb1"]["fingerprint"], "ff")
            p.write_text("{broken", encoding="utf-8")
            self.assertEqual(load_state(p), {})
            save_state(p, {"kb1": "garbage"})  # 非法条目被剔除
            self.assertEqual(load_state(p), {})


class TestRetrieveCache(unittest.TestCase):
    def test_hit_miss_ttl_and_lru(self):
        c = RetrieveCache(maxsize=2, ttl=10.0)
        c.put("a", "va", now=0.0)
        c.put("b", "vb", now=0.0)
        self.assertEqual(c.get("a", now=5.0), "va")
        self.assertIsNone(c.get("a", now=11.0), "TTL 过期")
        c.put("a", "va2", now=12.0)
        c.put("c", "vc", now=12.0)  # 超容量 → 淘汰最旧 b
        self.assertIsNone(c.get("b", now=12.5))
        self.assertEqual(c.get("a", now=12.5), "va2")

    def test_empty_not_cached(self):
        c = RetrieveCache()
        c.put("k", "")
        self.assertIsNone(c.get("k"))

    def test_inflight_merge_single_factory(self):
        c = RetrieveCache()
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            await asyncio.sleep(0.05)
            return "result"

        async def run():
            rs = await asyncio.gather(
                c.get_or_create("k", factory),
                c.get_or_create("k", factory),
                c.get_or_create("k", factory),
            )
            return rs

        rs = asyncio.run(run())
        self.assertEqual(rs, ["result"] * 3)
        self.assertEqual(calls["n"], 1, "并发应合并为一次底层调用")
        self.assertEqual(c.get("k"), "result", "成功结果应落缓存")

    def test_exception_not_cached_and_propagates(self):
        c = RetrieveCache()

        async def bad():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            asyncio.run(c.get_or_create("k", bad))
        self.assertIsNone(c.get("k"))

    def test_empty_factory_result_not_cached(self):
        c = RetrieveCache()

        async def empty():
            return ""

        self.assertEqual(asyncio.run(c.get_or_create("k", empty)), "")
        self.assertEqual(c.misses, 1)
        self.assertIsNone(c.get("k"))

    def test_cancel_waiter_keeps_task(self):
        c = RetrieveCache()
        done = {"v": None}

        async def slow():
            await asyncio.sleep(0.1)
            done["v"] = "ok"
            return "ok"

        async def run():
            leader = asyncio.ensure_future(c.get_or_create("k", slow))
            await asyncio.sleep(0.01)
            follower = asyncio.ensure_future(c.get_or_create("k", slow))
            await asyncio.sleep(0.01)
            follower.cancel()
            try:
                await follower
            except asyncio.CancelledError:
                pass
            v = await leader  # 取消等待者不得取消共享任务
            await asyncio.sleep(0.12)
            return v, done["v"]

        v, dv = asyncio.run(run())
        self.assertEqual((v, dv), ("ok", "ok"))




class TestTaskRegistry(unittest.TestCase):
    def test_track_done_and_exception_consumed(self):
        r = TaskRegistry()

        async def ok():
            return 1

        async def bad():
            raise ValueError("x")

        async def run():
            t1 = r.track(asyncio.ensure_future(ok()))
            t2 = r.track(asyncio.ensure_future(bad()))
            await asyncio.gather(t1, t2, return_exceptions=True)

        asyncio.run(run())
        self.assertEqual(len(r), 0, "完成即移除")

    def test_close_rejects_and_cancel_all(self):
        r = TaskRegistry()
        started = asyncio.Event()

        async def hang():
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise

        async def run():
            t = r.track(asyncio.ensure_future(hang()))
            await started.wait()
            r.close()
            self.assertTrue(r.closed)
            r.track(asyncio.ensure_future(asyncio.sleep(0)))  # closed 后忽略
            await r.cancel_all(timeout=2.0)
            self.assertTrue(t.cancelled() or t.done())

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
