# -*- coding: utf-8 -*-
"""Growth skeleton contract tests: metadata only, conservative defaults, safe storage."""

from __future__ import annotations

import errno
import json
import multiprocessing
import os
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from humanizer_core.growth_engine import (
    DEFAULTS,
    derive_state,
    normalize_config,
    scope_id_for,
    validate_event,
)
from humanizer_core.growth_service import GrowthService
from humanizer_core.growth_store import GrowthStore
from humanizer_core import growth_store as growth_store_module
from humanizer_core import growth_service as growth_service_module


def _concurrent_append(root: str, scope_id: str, worker: int, barrier, results) -> None:
    store = GrowthStore(Path(root), scope_id, max_events=100)
    barrier.wait()
    event = {
        "schema_version": 1,
        "type": "user_turn",
        "scope_id": scope_id,
        "event_id": f"worker-{worker}",
        "at": 1000 + worker,
        "text_length": 10 + worker,
    }
    # Nonblocking stores leave retry scheduling to their caller. This harness
    # retries only contention, never a permanent IO/schema failure.
    deadline = time.monotonic() + 5
    while True:
        written = store.append(event)
        if written or not store.busy or time.monotonic() >= deadline:
            results.put(written)
            return
        time.sleep(0.005)


class TestGrowthEngine(unittest.TestCase):
    def test_defaults_and_strict_config_clamping(self):
        self.assertEqual(DEFAULTS["enabled"], False)
        cfg = normalize_config({
            "enabled": 1,
            "debug": "yes",
            "identity_budget": 10,
            "situation_budget": 900,
            "tick_minutes": 0,
            "max_events": float("inf"),
        })
        self.assertIs(cfg["enabled"], False)
        self.assertIs(cfg["debug"], False)
        self.assertEqual(cfg["identity_budget"], 100)
        self.assertEqual(cfg["situation_budget"], 400)
        self.assertEqual(cfg["tick_minutes"], 1)
        self.assertEqual(cfg["max_events"], DEFAULTS["max_events"])
        self.assertEqual(normalize_config({"identity_budget": 9999})["identity_budget"], 900)

    def test_validation_rejects_private_payload_and_invalid_metadata(self):
        sid = scope_id_for("private conversation token")
        event = {"schema_version": 1, "type": "user_turn", "scope_id": sid,
                 "event_id": "evt-1", "at": 3.5, "text_length": 42}
        self.assertTrue(validate_event(event))
        for key, value in (("text", "private text"), ("umo", "private id"), ("persona", "raw persona")):
            bad = {**event, key: value}
            self.assertFalse(validate_event(bad))
        for value in (-1, float("nan"), float("inf"), True, "1", 10 ** 400):
            self.assertFalse(validate_event({**event, "at": value}))
        for value in (-1, 1000001, True):
            self.assertFalse(validate_event({**event, "text_length": value}))
        self.assertFalse(validate_event({**event, "schema_version": True}))
        self.assertFalse(validate_event({**event, "scope_id": "../bad"}))
        self.assertFalse(validate_event({**event, "event_id": "x" * 129}))
        self.assertFalse(validate_event({**event, "event_id": "start"}))
        self.assertFalse(validate_event({**event, "type": []}))
        self.assertFalse(validate_event({**event, "type": "bot_turn"}))
        self.assertFalse(validate_event({**event, "type": "bot_turn", "source": "raw private text"}))
        self.assertFalse(validate_event({**event, "type": "bot_turn", "source": "private_payload"}))
        self.assertTrue(validate_event({**event, "type": "bot_turn", "source": "proactive"}))
        start = {"schema_version": 1, "type": "start", "scope_id": sid,
                 "event_id": "start", "at": 3.5}
        self.assertTrue(validate_event(start))
        self.assertFalse(validate_event({**start, "text_length": 1}))
        self.assertFalse(validate_event({**start, "event_id": "another-start"}))
        self.assertEqual(derive_state([event], now=10 ** 400)["days_known"], 0.0)

    def test_derive_state_never_advances_with_messages_or_days(self):
        sid = scope_id_for("room")
        events = [{"schema_version": 1, "type": "start", "scope_id": sid,
                   "event_id": "start", "at": 1}]
        for i in range(300):
            events.append({"schema_version": 1, "type": "user_turn", "scope_id": sid,
                           "event_id": f"u{i}", "at": 2 + i, "text_length": 1})
        state = derive_state(events, now=20 * 365 * 86400)
        self.assertEqual(state["stage"], 0)
        self.assertEqual(state["stage_name"], "观察积累")
        self.assertIn("不会自动晋级", state["stage_reason"])
        self.assertEqual(state["user_turns"], 300)
        self.assertEqual(state["bot_turns"], 0)
        self.assertEqual(state["event_count"], 301)


class TestGrowthStore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scope_id = scope_id_for("test-scope")
        self.store = GrowthStore(self.root, self.scope_id, max_events=100)

    def tearDown(self):
        self.temp.cleanup()

    def _event(self, event_id="e1"):
        return {"schema_version": 1, "type": "user_turn", "scope_id": self.scope_id,
                "event_id": event_id, "at": 100.0, "text_length": 12}

    def test_rebuild_from_log_and_cross_instance_deduplication(self):
        self.assertTrue(self.store.append(self._event()))
        second = GrowthStore(self.root, self.scope_id, max_events=100)
        self.assertTrue(second.append(self._event()))
        self.assertEqual(len(second.events()), 1)
        rebuilt = GrowthStore(self.root, self.scope_id, max_events=100)
        self.assertEqual(rebuilt.events(), [self._event()])

    def test_read_returns_copies_and_snapshot_is_only_a_cache(self):
        self.assertTrue(self.store.append(self._event()))
        returned = self.store.events()
        returned[0]["text_length"] = 999
        returned[0]["text"] = "must not enter the cache"
        self.assertEqual(self.store.events(), [self._event()])
        self.store.state_path.write_text('{"untrusted":"snapshot"}', encoding="utf-8")
        rebuilt = GrowthStore(self.root, self.scope_id)
        self.assertEqual(rebuilt.events(), [self._event()])

    def test_read_without_a_writer_lock_never_creates_one(self):
        directory = self.root / "growth" / self.scope_id
        directory.mkdir(parents=True)
        self.store.events_path.write_text(json.dumps(self._event()) + "\n", encoding="utf-8")
        self.assertEqual(self.store.events(), [self._event()])
        self.assertFalse(self.store.lock_path.exists())

    def test_corrupt_tail_and_middle_fail_closed_without_repair(self):
        self.assertTrue(self.store.append(self._event("first")))
        path = self.store.events_path
        original = path.read_bytes()
        path.write_bytes(original + b'{"broken":')
        damaged = path.read_bytes()
        self.assertEqual(self.store.events(), [])
        self.assertTrue(self.store.degraded)
        self.assertEqual(path.read_bytes(), damaged, "坏尾不得截断或改名")

        # A new store must reject corruption even if a valid line follows it.
        path.write_bytes(original + b'{"broken":}\n' + original)
        damaged = path.read_bytes()
        middle = GrowthStore(self.root, self.scope_id)
        self.assertEqual(middle.events(), [])
        self.assertTrue(middle.degraded)
        self.assertEqual(path.read_bytes(), damaged)

    def test_invalid_json_shapes_and_duplicate_keys_fail_closed(self):
        directory = self.root / "growth" / self.scope_id
        directory.mkdir(parents=True)
        event = self._event()
        duplicate = json.dumps(event).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
        cases = [
            json.dumps({**event, "type": []}),
            json.dumps({**event, "at": 10 ** 400}),
            duplicate,
            "[" * 2000 + "]" * 2000,
        ]
        for damaged_text in cases:
            with self.subTest(prefix=damaged_text[:60]):
                damaged = damaged_text.encode("utf-8") + b"\n"
                self.store.events_path.write_bytes(damaged)
                store = GrowthStore(self.root, self.scope_id)
                self.assertEqual(store.events(), [])
                self.assertTrue(store.degraded)
                self.assertFalse(store.append(self._event("new")))
                self.assertEqual(self.store.events_path.read_bytes(), damaged)

    def test_quota_rejects_new_event_but_allows_reads(self):
        limited = GrowthStore(self.root, self.scope_id, max_events=1)
        self.assertTrue(limited.append(self._event("one")))
        self.assertFalse(limited.append(self._event("two")))
        self.assertEqual([e["event_id"] for e in limited.events()], ["one"])
        self.assertTrue(limited.cap_reached)
        limited.max_events = 100
        self.assertEqual(len(limited.events()), 1)
        self.assertFalse(limited.cap_reached)

    def test_symlink_scope_path_is_rejected(self):
        growth = self.root / "growth"
        growth.mkdir()
        target = self.root / "elsewhere"
        target.mkdir()
        scope_dir = growth / self.scope_id
        try:
            scope_dir.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are unavailable")
        self.assertFalse(self.store.append(self._event()))
        self.assertTrue(self.store.degraded)
        self.assertEqual(list(target.iterdir()), [])

    def test_failed_fsync_never_truncates_log_and_disables_future_writes(self):
        self.assertTrue(self.store.append(self._event("before")))
        before = self.store.events_path.read_bytes()
        with mock.patch("humanizer_core.growth_store.os.fsync", side_effect=OSError("disk")):
            self.assertFalse(self.store.append(self._event("failure")))
        # flush precedes fsync: failure does not prove the append is absent. It
        # must preserve the prefix and stop, never truncate an uncertain append.
        failed_bytes = self.store.events_path.read_bytes()
        self.assertTrue(failed_bytes.startswith(before))
        self.assertEqual(self.store.events(), [])
        self.assertFalse(self.store.append(self._event("after")))
        self.assertEqual(self.store.events_path.read_bytes(), failed_bytes)
        self.assertTrue(self.store.degraded)
        rebuilt = GrowthStore(self.root, self.scope_id)
        self.assertEqual([e["event_id"] for e in rebuilt.events()], ["before", "failure"])

    def test_busy_writer_is_nonblocking_and_retryable_without_stale_state(self):
        self.assertTrue(self.store.append(self._event("one")))
        reader = GrowthStore(self.root, self.scope_id)
        self.assertEqual(reader.state(200)["event_count"], 1)
        with self.store._locked(create=True) as acquired:
            self.assertTrue(acquired)
            began = time.monotonic()
            self.assertFalse(reader.append(self._event("two")))
            self.assertLess(time.monotonic() - began, 1.0)
            self.assertEqual(reader.busy, True)
            self.assertFalse(reader.degraded)
            self.assertEqual(reader.events(), [])
            self.assertEqual(reader.state(200)["event_count"], 0)
        self.assertTrue(reader.append(self._event("two")))
        self.assertEqual(reader.error, "")
        self.assertFalse(reader.degraded)
        self.assertEqual(reader.state(200)["event_count"], 2)

    def test_lock_backend_is_nonblocking_and_io_errors_are_permanent(self):
        self.assertTrue(self.store.append(self._event()))
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(backend, name) as lock:
            self.assertEqual(self.store.state(200)["event_count"], 1)
            operation = lock.call_args_list[0].args[1]
            expected = backend.LK_NBLCK if name == "locking" else backend.LOCK_EX | backend.LOCK_NB
            self.assertEqual(operation, expected)
        with mock.patch.object(backend, name, side_effect=OSError(errno.EIO, "disk")):
            self.assertFalse(self.store.append(self._event("failed")))
        self.assertEqual(self.store.error, "writer_lock_failed")
        self.assertTrue(self.store.degraded)
        self.assertFalse(self.store.append(self._event("never")))

    def test_lock_open_permission_error_fails_closed_not_busy(self):
        self.assertTrue(self.store.append(self._event()))
        original = self.store.events_path.read_bytes()
        with mock.patch.object(Path, "open", side_effect=PermissionError(errno.EACCES, "denied")):
            self.assertEqual(self.store.state(200)["event_count"], 0)
        self.assertTrue(self.store.degraded)
        self.assertEqual(self.store.error, "writer_lock_failed")
        self.assertEqual(self.store.events_path.read_bytes(), original)

    def test_unlock_failure_returns_no_cached_facts_and_blocks_future_writes(self):
        self.assertTrue(self.store.append(self._event()))
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        real_lock = getattr(backend, name)
        def release_then_fail(*args):
            result = real_lock(*args)
            unlock = backend.LK_UNLCK if name == "locking" else backend.LOCK_UN
            if args[1] == unlock:
                raise OSError(errno.EIO, "unlock failed")
            return result
        with mock.patch.object(backend, name, side_effect=release_then_fail):
            self.assertEqual(self.store.state(200)["event_count"], 0)
        self.assertTrue(self.store.degraded)
        self.assertEqual(self.store.error, "writer_unlock_failed")
        self.assertFalse(self.store.append(self._event("never")))

    def test_hard_read_limits_reject_source_unchanged_with_explicit_errors(self):
        self.assertEqual(growth_store_module.MAX_LOG_BYTES, 64 * 1024 * 1024)
        self.assertEqual(growth_store_module.MAX_LINE_BYTES, 4096)
        self.assertEqual(growth_store_module.MAX_LOG_EVENTS, 1000000)
        self.store.directory.mkdir(parents=True)
        rows = [(json.dumps(self._event(f"e{i}")) + "\n").encode() for i in range(3)]
        source = b"".join(rows)
        self.store.events_path.write_bytes(source)
        with mock.patch.object(growth_store_module, "MAX_LOG_BYTES", len(source) - 1), \
             mock.patch.object(Path, "open", side_effect=AssertionError("oversize source opened")):
            self.assertEqual(self.store.events(), [])
        self.assertEqual(self.store.error, "event_log_too_large")
        self.assertEqual(self.store.events_path.read_bytes(), source)
        counted = GrowthStore(self.root, self.scope_id)
        with mock.patch.object(growth_store_module, "MAX_LOG_EVENTS", 2):
            self.assertEqual(counted.events(), [])
        self.assertEqual(counted.error, "event_log_too_many_events")
        self.assertEqual(self.store.events_path.read_bytes(), source)
        long_line = b" " * 4097 + b"\n"
        self.store.events_path.write_bytes(long_line)
        oversized = GrowthStore(self.root, self.scope_id)
        self.assertEqual(oversized.events(), [])
        self.assertEqual(oversized.error, "event_line_too_large")
        self.assertFalse(oversized.append(self._event("never")))
        self.assertEqual(self.store.events_path.read_bytes(), long_line)

    def test_line_limit_includes_newline_and_append_cannot_exceed_file_limit(self):
        self.store.directory.mkdir(parents=True)
        serialized = json.dumps(self._event()).encode()
        exact_line = serialized + b" " * (4095 - len(serialized)) + b"\n"
        self.store.events_path.write_bytes(exact_line)
        self.assertEqual(self.store.events(), [self._event()])
        self.assertFalse(self.store.degraded)
        # A source already at the byte limit remains readable but cannot grow.
        with mock.patch.object(growth_store_module, "MAX_LOG_BYTES", len(exact_line)):
            self.assertFalse(self.store.append(self._event("cannot-fit")))
        self.assertEqual(self.store.error, "event_log_size_limit")
        self.assertFalse(self.store.degraded)
        self.assertEqual(self.store.events_path.read_bytes(), exact_line)
        self.assertTrue(self.store.append(self._event("fits-after-limit-restored")))
        self.assertEqual(self.store.error, "")

    def test_derived_state_is_incremental_copied_and_invalidated_by_external_append(self):
        self.assertTrue(self.store.append(self._event("one")))
        with mock.patch.object(growth_store_module, "derive_state", wraps=derive_state) as derive:
            state = self.store.state(86500)
            state["user_turns"] = 999
            self.assertEqual(self.store.state(86500)["user_turns"], 1)
            self.assertTrue(self.store.append({**self._event("two"), "at": 90}))
            self.assertEqual(self.store.state(86500)["started_at"], 90)
            self.assertTrue(self.store.append({"schema_version": 1, "type": "start",
                                               "scope_id": self.scope_id, "event_id": "start", "at": 110}))
            self.assertEqual(self.store.state(86510)["started_at"], 110)
            self.assertEqual(self.store.state(86510)["days_known"], 1)
            self.assertTrue(self.store.append({**self._event("bot"), "type": "bot_turn", "source": "reply"}))
            self.assertEqual(self.store.state(86510)["bot_turns"], 1)
            self.assertEqual(derive.call_count, 0, "unchanged/local append must not scan the log")
            peer = GrowthStore(self.root, self.scope_id)
            self.assertTrue(peer.append(self._event("external")))
            derive.reset_mock()
            current = self.store.state(86510)
            self.assertEqual(current["event_count"], 5)
            self.assertEqual(current["user_turns"], 3)
            self.assertEqual(derive.call_count, 1)
            self.assertEqual(current, derive_state(self.store.events(), 86510))

    def test_concurrent_processes_append_without_lost_updates(self):
        count = 6
        ctx = multiprocessing.get_context("spawn")
        barrier = ctx.Barrier(count)
        results = ctx.Queue()
        workers = [ctx.Process(target=_concurrent_append,
                               args=(str(self.root), self.scope_id, i, barrier, results))
                   for i in range(count)]
        for process in workers:
            process.start()
        for process in workers:
            process.join(15)
            self.assertEqual(process.exitcode, 0)
        outcomes = [results.get(timeout=3) for _ in workers]
        self.assertTrue(all(outcomes))
        rebuilt = GrowthStore(self.root, self.scope_id)
        self.assertEqual(len(rebuilt.events()), count)


class TestGrowthService(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_disabled_service_never_creates_directories_or_injects(self):
        service = GrowthService(self.root, {"enabled": False})
        self.assertFalse(service.note_user("private", "event", 100, 12))
        self.assertEqual(service.render("private", 100), ("", ""))
        service.tick(1000)
        self.assertEqual(service.events(scope_id_for("private")), [])
        self.assertFalse((self.root / "growth").exists())

    def test_metadata_only_service_snapshot_render_and_no_default_selection(self):
        service = GrowthService(self.root, {"enabled": True, "identity_budget": 100,
                                            "situation_budget": 80})
        raw_scope = "secret-scope"
        sid = scope_id_for(raw_scope)
        self.assertTrue(service.note_user(raw_scope, "user-1", 100, 20))
        self.assertTrue(service.note_bot(raw_scope, "bot-1", 110, 40, "reply"))
        events = service.events(sid)
        self.assertEqual(len(events), 3)  # start + user + bot
        serialized = json.dumps(events, ensure_ascii=False)
        self.assertNotIn(raw_scope, serialized)
        for event in events:
            for forbidden in ("text", "umo", "persona"):
                self.assertNotIn(forbidden, event)
        summary = service.snapshot(sid, now=200)
        self.assertEqual(summary["user_turns"], 1)
        self.assertEqual(summary["bot_turns"], 1)
        self.assertEqual(summary["stage"], 0)
        default_summary = service.snapshot(now=200)
        self.assertEqual(default_summary["scope_id"], "")
        self.assertEqual(default_summary["event_count"], 0)
        self.assertEqual(default_summary["scopes"][0]["id"], sid)
        identity, situation = service.render(raw_scope, 200)
        self.assertLessEqual(len(identity), 100)
        self.assertLessEqual(len(situation), 80)
        self.assertIn("[", identity)
        service.close()
        self.assertEqual(service.render(raw_scope, 200), ("", ""))

    def test_scope_id_input_validation_and_read_does_not_create(self):
        service = GrowthService(self.root, {"enabled": True})
        with self.assertRaises(ValueError):
            service.snapshot("../bad")
        with self.assertRaises(ValueError):
            service.events("not-a-hash")
        valid = scope_id_for("never-created")
        self.assertEqual(service.events(valid), [])
        self.assertFalse((self.root / "growth").exists())

    def test_invalid_inputs_do_not_write_start_and_tick_does_not_synthesize_events(self):
        service = GrowthService(self.root, {"enabled": True})
        for timestamp in (10 ** 400, -1, float("nan"), True):
            self.assertFalse(service.note_user("scope", "user-1", timestamp, 1))
        for event_id in ("start", "has spaces", "quote\"", ""):
            self.assertFalse(service.note_user("scope", event_id, 100, 1))
        self.assertFalse(service.note_bot("scope", "bot-1", 100, 1, "private text"))
        self.assertFalse((self.root / "growth").exists())
        self.assertTrue(service.note_user("scope", "user-1", 100, 1))
        self.assertTrue(service.note_user("scope", "user-1", 101, 1))
        sid = scope_id_for("scope")
        store = service._stores[sid]
        before = store.events_path.read_bytes()
        service.tick(50 * 365 * 86400)
        self.assertEqual(store.events_path.read_bytes(), before)
        self.assertEqual(service.snapshot(sid, now=10 ** 400)["event_count"], 2)
        self.assertEqual(service.snapshot(sid, now=100)["stage"], 0)
        service.configure({"enabled": False})
        self.assertFalse(service.note_bot("scope", "bot-2", 101, 1))
        service.tick(10 ** 400)
        self.assertEqual(service.render("scope", 101), ("", ""))
        self.assertEqual(store.events_path.read_bytes(), before)

    def test_disabled_reads_do_not_inspect_or_expose_existing_scopes(self):
        service = GrowthService(self.root, {"enabled": True})
        self.assertTrue(service.note_user("old-private-scope", "user-1", 100, 1))
        sid = scope_id_for("old-private-scope")
        service.configure({"enabled": False})
        with mock.patch.object(Path, "iterdir", side_effect=AssertionError("disabled read")), \
             mock.patch.object(Path, "exists", side_effect=AssertionError("disabled stat")), \
             mock.patch.object(Path, "open", side_effect=AssertionError("disabled open")):
            self.assertEqual(service.events(sid), [])
            self.assertEqual(service.snapshot()["scopes"], [])
            self.assertEqual(service.snapshot(sid)["scope_id"], "")
            self.assertEqual(service.snapshot(sid)["event_count"], 0)
            self.assertEqual(service.render("old-private-scope", 200), ("", ""))
            service.tick(200)
            service.close()

    def test_render_snapshot_tick_reuse_cache_and_skip_duplicate_start_append(self):
        service = GrowthService(self.root, {"enabled": True})
        sid = scope_id_for("cached-scope")
        self.assertTrue(service.note_user("cached-scope", "first", 100, 1))
        store = service._stores[sid]
        with mock.patch.object(store, "events", side_effect=AssertionError("full event copy")), \
             mock.patch.object(growth_store_module, "derive_state", side_effect=AssertionError("full derive")), \
             mock.patch.object(store, "append_with_start", wraps=store.append_with_start) as append:
            self.assertTrue(service.note_user("cached-scope", "second", 110, 2))
            self.assertEqual(append.call_count, 1, "one batched write per turn")
            lines = [json.loads(line) for line in store.events_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(sum(row["type"] == "start" for row in lines), 1,
                             "cached start must not be appended twice")
            for now in (200, 300, 400):
                self.assertIn("用户消息 2 条", service.render("cached-scope", now)[1])
                self.assertEqual(service.snapshot(sid, now)["event_count"], 3)
                service.tick(now)
        external = GrowthStore(self.root, sid)
        self.assertTrue(external.append({"schema_version": 1, "type": "user_turn", "scope_id": sid,
                                         "event_id": "external", "at": 120, "text_length": 1}))
        with mock.patch.object(growth_store_module, "derive_state", wraps=derive_state) as derive:
            service.tick(86500)
            self.assertEqual(store._state["event_count"], 4)
            self.assertEqual(store._state["days_known"], 1)
            self.assertEqual(derive.call_count, 1)
            self.assertEqual(service.snapshot(sid, 86500)["user_turns"], 3)
            self.assertIn("用户消息 3 条", service.render("cached-scope", 86500)[1])
            self.assertEqual(derive.call_count, 1)

    def test_busy_pending_fifo_deduplicates_metadata_and_tick_persists_in_order(self):
        service = GrowthService(self.root, {"enabled": True})
        sid = scope_id_for("private-queue-scope")
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            self.assertFalse(service.note_user("private-queue-scope", "u1", 100, 1))
            self.assertFalse(service.note_user("private-queue-scope", "u1", 999, 999))
            self.assertFalse(service.note_bot("private-queue-scope", "b1", 110, 2, "reply"))
            state = service.snapshot(sid, 200)
            self.assertEqual(state["pending_writes"], 2)
            self.assertEqual(state["event_count"], 0)
            self.assertEqual(state["error"], "pending_writes")
            self.assertFalse(state["degraded"])
            self.assertEqual(state["scopes"], [{"id": sid, "stage_name": "观察积累", "event_count": 0,
                                                 "last_event_ts": None, "pending_writes": 2,
                                                 "stuck_writes": 0}])
            service.tick(200)
            self.assertEqual(len(service._pending), 2)
            payload = json.dumps(list(service._pending.values()))
            self.assertNotIn("private-queue-scope", payload)
            self.assertEqual(next(iter(service._pending.values()))["at"], 100)
        # A successful read does not imply the volatile queue was persisted.
        self.assertEqual(service.snapshot(sid, 200)["error"], "pending_writes")
        self.assertEqual(service.events(sid), [])
        service.tick(200)
        self.assertEqual([row["event_id"] for row in service.events(sid)], ["start", "u1", "b1"])
        self.assertEqual(service.events(sid)[0]["at"], 100)
        state = service.snapshot(sid, 200)
        self.assertEqual(state["pending_writes"], 0)
        self.assertEqual(state["event_count"], 3)
        self.assertEqual(state["error"], "")
        service.tick(300)
        self.assertEqual(len(service.events(sid)), 3)

    def test_busy_after_start_and_partial_fifo_retry_keep_only_unpersisted_items(self):
        service = GrowthService(self.root, {"enabled": True})
        sid = scope_id_for("partial-queue")
        store = service._store(sid)
        real_append = store.append_with_start

        def busy_turn(event):
            store.busy = True
            return False

        with mock.patch.object(store, "append_with_start", side_effect=busy_turn):
            self.assertFalse(service.note_user("partial-queue", "one", 100, 1))
            self.assertFalse(service.note_user("partial-queue", "two", 110, 1))
        self.assertEqual(service.events(sid), [])
        # Persist the reserved start marker, then let only "one" succeed.
        self.assertTrue(store.append({"schema_version": 1, "type": "start",
                                      "scope_id": sid, "event_id": "start", "at": 100}))

        def persist_one(event):
            if event["event_id"] == "two":
                store.busy = True
                return False
            return real_append(event)

        with mock.patch.object(store, "append_with_start", side_effect=persist_one):
            service.tick(200)
        self.assertEqual(list(service._pending), [(sid, "two")])
        self.assertEqual([row["event_id"] for row in service.events(sid)], ["start", "one"])
        service.tick(300)
        self.assertEqual([row["event_id"] for row in service.events(sid)], ["start", "one", "two"])
        self.assertEqual(service.snapshot(sid)["pending_writes"], 0)

    def test_pending_queue_is_bounded_and_full_warning_does_not_claim_success(self):
        service = GrowthService(self.root, {"enabled": True})
        self.assertEqual(growth_service_module.MAX_PENDING_WRITES, 256)
        sid = scope_id_for("full-queue")
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(growth_service_module, "MAX_PENDING_WRITES", 2), \
             mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            for event_id in ("one", "two", "rejected"):
                self.assertFalse(service.note_user("full-queue", event_id, 100, 1))
            self.assertEqual(len(service._pending), 2)
            # Scoped view must not leak the global queue-full condition.
            self.assertEqual(service.snapshot(sid)["error"], "pending_writes")
            self.assertEqual(service.snapshot()["error"], "pending_queue_full")
            self.assertEqual(service.snapshot()["pending_writes"], 2)
        service.tick(200)
        self.assertEqual([row["event_id"] for row in service.events(sid)], ["start", "one", "two"])
        # The full-queue condition no longer holds once the queue drained; the
        # refusal itself stays observable via the global rejected counter.
        state = service.snapshot(sid)
        self.assertEqual(state["error"], "")
        self.assertEqual(state["pending_writes"], 0)
        self.assertEqual(state["rejected_writes"], 0, "scoped view must not expose global counters")
        overall = service.snapshot()
        self.assertFalse(overall["queue_full"])
        self.assertEqual(overall["rejected_writes"], 1)

    def test_degraded_scope_does_not_block_other_scopes_pending_retry(self):
        service = GrowthService(self.root, {"enabled": True})
        blocked = scope_id_for("blocked-queue")
        healthy = scope_id_for("healthy-queue")
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            self.assertFalse(service.note_user("blocked-queue", "u1", 100, 1))
            self.assertFalse(service.note_user("healthy-queue", "u2", 101, 1))
        self.assertEqual(len(service._pending), 2)
        service._store(blocked)._fail("storage_write_failed")
        service.tick(200)
        self.assertEqual([row["event_id"] for row in service.events(healthy)], ["start", "u2"])
        self.assertEqual(list(service._stuck), [(blocked, "u1")])
        self.assertEqual(list(service._pending), [])

    def test_degraded_queue_is_retained_and_close_does_not_retry_or_expose_it(self):
        service = GrowthService(self.root, {"enabled": True})
        sid = scope_id_for("degraded-queue")
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            self.assertFalse(service.note_user("degraded-queue", "pending", 100, 1))
        store = service._stores[sid]
        store._fail("storage_write_failed")
        with mock.patch.object(store, "append_with_start", side_effect=AssertionError("degraded retry")):
            service.tick(200)
            # A degraded scope's queued item is parked, not retried or kept as pending.
            self.assertEqual(len(service._pending), 0)
            self.assertEqual(len(service._stuck), 1)
            self.assertFalse(service.note_user("degraded-queue", "not-queued", 110, 1))
        self.assertEqual(len(service._pending), 0)
        state = service.snapshot(sid)
        self.assertTrue(state["degraded"])
        self.assertEqual(state["error"], "storage_write_failed")
        self.assertEqual(state["pending_writes"], 0)
        self.assertEqual(state["stuck_writes"], 1)
        service.configure({"enabled": False})
        with mock.patch.object(Path, "open", side_effect=AssertionError("disabled IO")), \
             mock.patch.object(Path, "exists", side_effect=AssertionError("disabled stat")), \
             mock.patch.object(Path, "iterdir", side_effect=AssertionError("disabled scan")):
            service.tick(200)
            self.assertEqual(service.snapshot(sid)["pending_writes"], 0)
            service.close()
            service.tick(300)
            self.assertEqual(service.snapshot(sid)["pending_writes"], 0)
        # close drops volatile queues so a post-close snapshot cannot claim items
        # that no longer exist anywhere.
        self.assertEqual(len(service._pending), 0)
        self.assertEqual(len(service._stuck), 0)

    def test_public_service_methods_share_reentrant_thread_lock(self):
        service = GrowthService(self.root, {"enabled": True})
        sid = scope_id_for("threaded")
        calls = [
            lambda: service.configure({"enabled": True}),
            lambda: service.note_user("threaded", "user", 100, 1),
            lambda: service.note_bot("threaded", "bot", 101, 1),
            lambda: service.render("threaded", 200),
            lambda: service.snapshot(sid, 200),
            lambda: service.events(sid),
            lambda: service.tick(200),
            service.close,
        ]
        with service._lock:
            service.configure({"enabled": True})  # reentrant, not a plain Lock
        with ThreadPoolExecutor(max_workers=1) as executor:
            for call in calls:
                began, finished = threading.Event(), threading.Event()
                def invoke(action=call):
                    began.set()
                    try:
                        return action()
                    finally:
                        finished.set()
                with service._lock:
                    future = executor.submit(invoke)
                    self.assertTrue(began.wait(2))
                    self.assertFalse(finished.wait(0.02), "public method bypassed service lock")
                future.result(timeout=3)
        self.assertTrue(service._closed)
        self.assertEqual(service._stores, {})
        self.assertFalse(service.note_user("threaded", "after-close", 200, 1))
        self.assertEqual(service.render("threaded", 200), ("", ""))
        self.assertEqual(service.snapshot(sid)["event_count"], 0)

    def test_max_events_configuration_minimum_is_clamped(self):
        service = GrowthService(self.root, {"enabled": True, "max_events": 1})
        self.assertEqual(service.config["max_events"], 100)
        self.assertEqual(service.configure({"enabled": True, "max_events": 1})["max_events"], 100)


class TestGrowthP2Optimizations(unittest.TestCase):
    """P2 batch: single-write hot path, bounded snapshot, explicit untrusted root."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scope_id = scope_id_for("p2-scope")

    def tearDown(self):
        self.temp.cleanup()

    def _turn(self, event_id="t1", at=100.0):
        return {"schema_version": 1, "type": "user_turn", "scope_id": self.scope_id,
                "event_id": event_id, "at": at, "text_length": 5}

    def test_append_with_start_writes_both_lines_once_and_flushes_state_lazily(self):
        store = GrowthStore(self.root, self.scope_id)
        self.assertTrue(store.append_with_start(self._turn()))
        self.assertEqual([row["event_id"] for row in store.events()], ["start", "t1"])
        # The derived snapshot is no longer written on the message hot path.
        self.assertFalse(store.state_path.exists())
        self.assertTrue(store.flush_state())
        payload = json.loads(store.state_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["events"], 2)
        # Repeated delivery of the same turn is idempotent (no duplicate lines).
        self.assertTrue(store.append_with_start(self._turn()))
        self.assertEqual(len(store.events()), 2)
        self.assertFalse(store.flush_state(), "a clean snapshot is not rewritten")

    def test_busy_is_temporary_and_never_becomes_a_fatal_error(self):
        store = GrowthStore(self.root, self.scope_id)
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            self.assertFalse(store.append_with_start(self._turn()))
        self.assertTrue(store.busy)
        self.assertEqual(store.error, "", "contention must not be reported as fatal")
        self.assertFalse(store.degraded)
        self.assertTrue(store.append_with_start(self._turn()))
        self.assertFalse(store.busy)
        self.assertEqual(store.error, "")

    def test_unscoped_snapshot_is_bounded_and_reports_truncation(self):
        service = GrowthService(self.root, {"enabled": True})
        scopes = [scope_id_for(f"scope-{index}") for index in range(3)]
        for sid in scopes:
            self.assertTrue(GrowthStore(self.root, sid).append_with_start({
                "schema_version": 1, "type": "user_turn", "scope_id": sid,
                "event_id": "turn", "at": 1, "text_length": 1,
            }))
        with mock.patch.object(growth_service_module, "MAX_SCOPE_SUMMARIES", 2):
            state = service.snapshot()
        self.assertEqual(len(state["scopes"]), 2)
        self.assertTrue(state["scopes_truncated"])
        self.assertEqual(state["pending_writes"], 0)
        full = service.snapshot()
        self.assertFalse(full["scopes_truncated"])

    def test_unscoped_snapshot_materializes_only_bounded_stores(self):
        for index in range(5):
            sid = scope_id_for(f"bounded-{index}")
            self.assertTrue(GrowthStore(self.root, sid).append_with_start({
                "schema_version": 1, "type": "user_turn", "scope_id": sid,
                "event_id": "turn", "at": 1, "text_length": 1,
            }))
        service = GrowthService(self.root, {"enabled": True})
        with mock.patch.object(growth_service_module, "MAX_SCOPE_SUMMARIES", 2):
            state = service.snapshot()
        # Aggregates must not create one store object per scope on disk.
        self.assertLessEqual(len(service._stores), 3)
        self.assertTrue(state["scopes_truncated"])

    def test_permanently_blocked_scope_is_not_retried_every_tick(self):
        service = GrowthService(self.root, {"enabled": True})
        sid = scope_id_for("cap-blocked")
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            self.assertFalse(service.note_user("cap-blocked", "u1", 100, 1))
        store = service._stores[sid]
        store.cap_reached = True
        with mock.patch.object(store, "append_with_start", side_effect=AssertionError("blocked retry")):
            service.tick(200)
        # Cap-blocked items are parked (not retried, not occupying the pending queue).
        self.assertEqual(len(service._pending), 0)
        self.assertEqual(len(service._stuck), 1)
        store.cap_reached = False
        service.configure({"enabled": True, "max_events": 30000})
        service.tick(300)
        self.assertEqual([row["event_id"] for row in service.events(sid)], ["start", "u1"])

    def test_unscoped_error_prefers_degraded_scope(self):
        service = GrowthService(self.root, {"enabled": True})
        clean = service._store(scope_id_for("clean-error"))
        clean.error = "event_log_size_limit"  # non-fatal, would otherwise win by hash order
        bad = service._store(scope_id_for("corrupt-error"))
        bad._fail("corrupt_event_log")
        state = service.snapshot()
        self.assertTrue(state["degraded"])
        self.assertEqual(state["error"], "corrupt_event_log")

    def test_cached_scope_beyond_listing_cap_is_still_aggregated(self):
        service = GrowthService(self.root, {"enabled": True})
        store = service._store(scope_id_for("cached-degraded"))
        store._fail("storage_write_failed")
        with mock.patch.object(service, "_scope_ids_on_disk", return_value=([], "")), \
             mock.patch.object(growth_service_module, "MAX_SCOPE_SUMMARIES", 0):
            state = service.snapshot()
        self.assertTrue(state["degraded"])
        self.assertEqual(state["error"], "storage_write_failed")

    def test_permanent_failure_is_parked_and_surfaces_as_stuck(self):
        service = GrowthService(self.root, {"enabled": True})
        sid = scope_id_for("parked")
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            self.assertFalse(service.note_user("parked", "u1", 100, 1))
        store = service._stores[sid]
        store.cap_reached = True
        service.tick(200)
        state = service.snapshot()
        self.assertEqual(len(service._pending), 0)
        self.assertEqual(len(service._stuck), 1)
        self.assertEqual(state["pending_writes"], 0)
        self.assertEqual(state["stuck_writes"], 1)
        self.assertEqual(state["error"], "stuck_writes")
        self.assertFalse(state["queue_full"])
        store.cap_reached = False
        service.configure({"enabled": True, "max_events": 30000})
        service.tick(300)
        self.assertEqual([row["event_id"] for row in service.events(sid)], ["start", "u1"])
        self.assertEqual(service.snapshot()["stuck_writes"], 0)

    def test_retry_attempts_even_when_store_has_stale_error(self):
        service = GrowthService(self.root, {"enabled": True})
        sid = scope_id_for("stale-error")
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            self.assertFalse(service.note_user("stale-error", "u1", 100, 1))
        store = service._stores[sid]
        store.error = "event_log_size_limit"  # stale, non-degraded, no write attempt yet
        service.tick(200)
        self.assertEqual([row["event_id"] for row in service.events(sid)], ["start", "u1"])
        self.assertEqual(store.error, "", "a successful retry must clear the stale error")

    def test_scoped_snapshot_does_not_leak_global_queue_state(self):
        service = GrowthService(self.root, {"enabled": True})
        quiet = scope_id_for("quiet-leak")
        backend = growth_store_module.msvcrt or growth_store_module.fcntl
        name = "locking" if growth_store_module.msvcrt is not None else "flock"
        with mock.patch.object(growth_service_module, "MAX_PENDING_WRITES", 1), \
             mock.patch.object(backend, name, side_effect=OSError(errno.EAGAIN, "busy")):
            self.assertFalse(service.note_user("busy-leak", "a", 100, 1))
            self.assertFalse(service.note_user("busy-leak", "b", 101, 1))
            scoped = service.snapshot(quiet)
            overall = service.snapshot()
        self.assertEqual(scoped["pending_writes"], 0)
        self.assertEqual(scoped["rejected_writes"], 0)
        self.assertFalse(scoped["queue_full"])
        self.assertEqual(scoped["error"], "")
        self.assertEqual(overall["rejected_writes"], 1)
        self.assertTrue(overall["queue_full"])
        self.assertEqual(overall["error"], "pending_queue_full")

    def test_symlinked_growth_root_is_reported_not_silently_empty(self):
        service = GrowthService(self.root, {"enabled": True})
        real_is_symlink = Path.is_symlink

        def fake_is_symlink(self):
            return self.name == "growth" or real_is_symlink(self)

        with mock.patch.object(Path, "is_symlink", fake_is_symlink):
            ids, error = service._scope_ids_on_disk()
            state = service.snapshot()
        self.assertEqual(ids, [])
        self.assertEqual(error, "unsafe_storage_path")
        self.assertTrue(state["degraded"])
        self.assertEqual(state["error"], "unsafe_storage_path")

    def test_hashed_scope_is_used_directly_without_a_second_hash(self):
        service = GrowthService(self.root, {"enabled": True})
        self.assertTrue(service.note_user(self.scope_id, "user", 100, 3))
        self.assertTrue((self.root / "growth" / self.scope_id / "events.jsonl").is_file())
        self.assertEqual(service.render(self.scope_id, 200)[0].count("观察积累"), 1)


if __name__ == "__main__":
    unittest.main()
