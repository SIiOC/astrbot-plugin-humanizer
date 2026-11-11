# -*- coding: utf-8 -*-
"""Append-only JSONL storage for metadata-only growth events."""

from __future__ import annotations

import errno
import json
import math
import os
import threading
from pathlib import Path
from typing import Any, Mapping

from .growth_engine import derive_state, is_scope_id, validate_event

# Independent hard read limits, not configurable quotas. Validate before parsing
# or materializing an untrusted log; a bounded readline cannot allocate a huge line.
# The byte guard is deliberately above the realistic worst case for the configured
# quota: real events are ~230 bytes, so 200k events ≈ 46 MiB < 64 MiB. A 4 KiB
# line is only the per-line ceiling, not the expected size.
MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 4 * 1024
MAX_LOG_EVENTS = 1000000


def _log_signature(stat) -> tuple[int, ...]:
    return (stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns, stat.st_dev, stat.st_ino)

try:  # Windows
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None
try:  # POSIX
    import fcntl
except ImportError:  # Windows
    fcntl = None


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


class GrowthStore:
    """One hashed scope store. Construction and reads never create directories."""

    def __init__(self, root: str | os.PathLike[str] | None, scope_id: str, max_events: int = 20000):
        if not is_scope_id(scope_id):
            raise ValueError("invalid_scope_id")
        self.root = Path(root) if root is not None else None
        self.scope_id = scope_id
        self.max_events = max(1, int(max_events))
        self.directory = self.root / "growth" / scope_id if self.root is not None else None
        self.events_path = self.directory / "events.jsonl" if self.directory is not None else None
        self.state_path = self.directory / "state.json" if self.directory is not None else None
        self.lock_path = self.directory / "writer.lock" if self.directory is not None else None
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] | None = None
        self._ids: set[str] = set()
        self._signature: tuple[int, ...] | None = None
        self._state: dict[str, Any] | None = None
        self.degraded = False
        self.error = ""
        #: Temporary cross-process contention. Distinct from ``error`` (fatal and
        #: sticky); a busy writer may succeed on the next maintenance retry.
        self.busy = False
        self.cap_reached = False
        self._write_failed = False
        self._loaded = False
        self._state_dirty = False

    def _fail(self, code: str) -> None:
        self.degraded = True
        self.error = code
        self.busy = False

    def _is_safe_directory(self, create: bool) -> bool:
        if self.root is None or self.directory is None:
            return False
        root = self.root
        growth = root / "growth"
        target = self.directory
        try:
            if root.is_symlink() or growth.is_symlink() or target.is_symlink():
                self._fail("unsafe_storage_path")
                return False
            # Verify fixed names are ordinary files, never links/special files;
            # is_symlink() also detects a dangling symbolic link.
            for path in (self.events_path, self.state_path, self.lock_path, self.directory / "state.json.tmp"):
                if path is not None and path.is_symlink():
                    self._fail("unsafe_storage_path")
                    return False
                if path is not None and path.exists() and not path.is_file():
                    self._fail("unsafe_storage_path")
                    return False
            if create:
                root.mkdir(parents=True, exist_ok=True)
                growth.mkdir(exist_ok=True)
                target.mkdir(exist_ok=True)
            return target.is_dir()
        except OSError:
            self._fail("storage_unavailable")
            return False

    def _locked(self, create: bool):
        return _ExclusiveLock(self, create)

    def _read_all_locked(self) -> list[dict[str, Any]] | None:
        """Return internal events only while the caller owns both locks."""
        path = self.events_path
        try:
            if path is None or not path.exists():
                if self._signature != () or not self._loaded:
                    self._events = []
                    self._ids = set()
                    self._state = derive_state(())
                    self._signature = ()
                    self._loaded = True
                self.cap_reached = False
                return self._events
            stat = path.stat()
            if stat.st_size > MAX_LOG_BYTES:
                self._fail("event_log_too_large")
                return None
            signature = _log_signature(stat)
            # A stable locked stat reuses the internal list/state without O(n)
            # copies. External appends/replacements invalidate both together.
            if self._loaded and signature == self._signature and self._events is not None:
                self.cap_reached = len(self._events) >= min(self.max_events, MAX_LOG_EVENTS)
                return self._events
            events: list[dict[str, Any]] = []
            ids: set[str] = set()
            total_bytes = 0
            with path.open("rb") as handle:
                while True:
                    raw_line = handle.readline(MAX_LINE_BYTES + 1)
                    if not raw_line:
                        break
                    total_bytes += len(raw_line)
                    if total_bytes > MAX_LOG_BYTES:
                        self._fail("event_log_too_large")
                        return None
                    if len(raw_line) > MAX_LINE_BYTES:
                        self._fail("event_line_too_large")
                        return None
                    if len(events) >= MAX_LOG_EVENTS:
                        self._fail("event_log_too_many_events")
                        return None
                    if not raw_line.endswith(b"\n"):
                        self._fail("corrupt_event_log")
                        return None
                    try:
                        event = json.loads(raw_line.decode("utf-8"), object_pairs_hook=_unique_json_object)
                    except (UnicodeError, ValueError, RecursionError):
                        self._fail("corrupt_event_log")
                        return None
                    if not validate_event(event, self.scope_id):
                        self._fail("corrupt_event_log")
                        return None
                    event_id = event["event_id"]
                    if event_id in ids:
                        self._fail("corrupt_event_log")
                        return None
                    ids.add(event_id)
                    events.append(dict(event))
            # Signature after reading catches concurrent out-of-band mutation.
            if _log_signature(path.stat()) != signature:
                self._fail("storage_changed_during_read")
                return None
            self._events = events
            self._ids = ids
            self._state = derive_state(events)
            self._signature = signature
            self._loaded = True
            self.cap_reached = len(events) >= min(self.max_events, MAX_LOG_EVENTS)
            return events
        except OSError:
            self._fail("storage_read_failed")
            return None

    def _refresh_locked(self) -> bool:
        if not self._is_safe_directory(create=False):
            return False
        with self._locked(create=False) as acquired:
            refreshed = bool(acquired and self._read_all_locked() is not None)
        return refreshed and not self.degraded

    def has_event(self, event_id: str) -> bool:
        """Check a cached ID set after a cheap stat refresh, without copying events."""
        if self.root is None or self.degraded:
            return False
        with self._lock:
            return not self.degraded and self._refresh_locked() and event_id in self._ids

    def state(self, now: float | None = None) -> dict[str, Any]:
        """Return O(1) derived metadata after a stat-based cache refresh.

        A busy writer yields an empty state for this call; stale cached facts are
        never injected while the source cannot be verified. The next call retries.
        """
        with self._lock:
            if self.root is None or self.degraded or not self._refresh_locked():
                return derive_state(())
            assert self._state is not None
            state = self._state
            state["days_known"] = 0.0
            started_at = state["started_at"]
            if started_at is not None and not isinstance(now, bool) and isinstance(now, (int, float)):
                try:
                    if math.isfinite(now):
                        state["days_known"] = max(0.0, (float(now) - started_at) / 86400.0)
                except (OverflowError, ValueError):
                    pass
            return dict(state)

    def events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Read validated events; a corrupt log returns no partial data."""
        if self.root is None or self.degraded:
            return []
        with self._lock:
            if self.degraded:
                return []
            try:
                if not self._is_safe_directory(create=False):
                    return []
                with self._locked(create=False) as acquired:
                    if not acquired:
                        return []
                    all_events = self._read_all_locked()
                    if all_events is None:
                        return []
                    result = all_events
                    if limit is not None:
                        count = max(0, int(limit))
                        result = all_events[-count:] if count else []
                    copied = [dict(event) for event in result]
                return [] if self.degraded else copied
            except (OSError, ValueError):
                self._fail("storage_read_failed")
                return []

    def append(self, event: Mapping[str, Any]) -> bool:
        """Append a validated event once; corruption and IO errors fail closed."""
        if self.root is None or self.degraded or self._write_failed:
            return False
        if not isinstance(event, Mapping):
            return False
        candidate = dict(event)
        if not validate_event(candidate, self.scope_id):
            return False
        return self._append_many([candidate])

    def append_with_start(self, event: Mapping[str, Any]) -> bool:
        """Append a turn event and, on first use, its start marker atomically.

        One lock acquisition and one ``fsync`` cover both lines, so the hot path
        no longer pays a separate ``has_event`` probe, start append and snapshot
        write per message. Repeated calls with the same event id are idempotent.
        """
        if self.root is None or self.degraded or self._write_failed:
            return False
        if not isinstance(event, Mapping):
            return False
        candidate = dict(event)
        if not validate_event(candidate, self.scope_id) or candidate["type"] == "start":
            return False
        pending = [candidate]
        with self._lock:
            # Re-read under the writer lock: whether the start marker already
            # exists must be decided from the durable log, not a stale cache.
            if self.degraded or self._write_failed:
                return False
            inserted = self._append_many_locked(pending, with_start=True)
            return inserted

    def _append_many(self, pending: list[dict[str, Any]]) -> bool:
        with self._lock:
            if self.degraded or self._write_failed:
                return False
            return self._append_many_locked(pending, with_start=False)

    def _append_many_locked(self, pending: list[dict[str, Any]], with_start: bool) -> bool:
        try:
            if not self._is_safe_directory(create=True):
                return False
            with self._locked(create=True) as acquired:
                if not acquired:
                    return False
                # The locked stat signature invalidates cached data after any
                # other writer; unchanged files need not be rescanned per turn.
                current = self._read_all_locked()
                if current is None:
                    return False
                fresh = [item for item in pending if item["event_id"] not in self._ids]
                if not fresh:
                    return True
                batch: list[dict[str, Any]] = []
                if with_start and "start" not in self._ids:
                    batch.append({
                        "schema_version": 1,
                        "type": "start",
                        "scope_id": self.scope_id,
                        "event_id": "start",
                        "at": fresh[0]["at"],
                    })
                batch.extend(fresh)
                if len(current) + len(batch) > min(self.max_events, MAX_LOG_EVENTS):
                    self.cap_reached = True
                    return False
                try:
                    serialized = b"".join(self._serialize(item) for item in batch)
                except ValueError:
                    self.error = "event_line_too_large"
                    return False
                if (self._signature[1] if self._signature else 0) + len(serialized) > MAX_LOG_BYTES:
                    self.error = "event_log_size_limit"
                    self.cap_reached = True
                    return False
                path = self.events_path
                assert path is not None
                try:
                    with path.open("ab") as handle:
                        written = handle.write(serialized)
                        if written != len(serialized):
                            raise OSError("short_write")
                        handle.flush()
                        os.fsync(handle.fileno())
                except OSError:
                    self._write_failed = True
                    self._fail("storage_write_failed")
                    return False
                # Memory/derived state updates only after the durable flush.
                for item in batch:
                    current.append(item)
                    self._ids.add(item["event_id"])
                    self._advance_state_locked(item)
                self._events = current
                try:
                    stat = path.stat()
                except OSError:
                    # The data is durable; only the stat cache is unknown. Force a
                    # re-read next time instead of declaring a healthy store dead.
                    self._signature = None
                    self._loaded = False
                else:
                    self._signature = _log_signature(stat)
                    self._loaded = True
                self.cap_reached = len(current) >= min(self.max_events, MAX_LOG_EVENTS)
                self._state_dirty = True
                self.error = ""
                self.busy = False
            return not self.degraded
        except (OSError, ValueError):
            self._write_failed = True
            self._fail("storage_write_failed")
            return False

    @staticmethod
    def _serialize(event: Mapping[str, Any]) -> bytes:
        data = json.dumps(
            event, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8") + b"\n"
        if len(data) > MAX_LINE_BYTES:
            raise ValueError("event_line_too_large")
        return data

    def _advance_state_locked(self, event: Mapping[str, Any]) -> None:
        """Update the verified state's fixed-size counters after a durable append."""
        assert self._state is not None
        state = self._state
        timestamp = float(event["at"])
        prior_count = state["event_count"]
        state["scope_id"] = self.scope_id
        state["event_count"] = prior_count + 1
        if event["type"] == "user_turn":
            state["user_turns"] += 1
        elif event["type"] == "bot_turn":
            state["bot_turns"] += 1
        # Schema validation reserves the one start ID; before it exists, the
        # earliest turn is a fallback. A real start supersedes that fallback.
        if event["type"] == "start":
            state["started_at"] = timestamp
        elif "start" not in self._ids:
            state["started_at"] = min(state["started_at"], timestamp) if prior_count else timestamp
        previous_last = state["last_event_ts"]
        state["last_event_ts"] = max(previous_last, timestamp) if previous_last is not None else timestamp

    def _write_state_locked(self) -> bool:
        """Best-effort atomic derived snapshot; never a source of truth."""
        if self.state_path is None or self.directory is None or self._state is None:
            return False
        payload = {"schema_version": 1, "scope_id": self.scope_id, "events": self._state["event_count"], "last_event_ts": self._state["last_event_ts"]}
        temp = self.directory / "state.json.tmp"
        try:
            if temp.exists() and temp.is_symlink():
                return False
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.state_path)
            return True
        except OSError:
            # Preserve the failed temporary file for diagnosis; never delete user data.
            # The append-only log remains authoritative, with no empty overwrite.
            return False

    def flush_state(self) -> bool:
        """Persist the derived snapshot at most once per maintenance cycle.

        Batched here rather than per append, so a burst of messages costs one
        snapshot write instead of one ``fsync`` per event. The value is only a
        cache; a missing or stale file never changes derived facts. Like every
        other path, a symlinked/untrusted directory is never written through.
        """
        if self.root is None or self.degraded or not self._state_dirty:
            return False
        with self._lock:
            if self.degraded or not self._state_dirty:
                return False
            if not self._is_safe_directory(create=False):
                return False
            with self._locked(create=False) as acquired:
                if not acquired:
                    return False
                written = self._write_state_locked()
            if written:
                self._state_dirty = False
            return written

    def refresh(self) -> list[dict[str, Any]]:
        """Refresh a cached view if necessary, without creating any path."""
        return self.events()

    def close(self) -> None:
        """No persistent handles are retained between operations."""
        return None


class _ExclusiveLock:
    """Cross-process byte lock on a persistent lock file."""

    def __init__(self, store: GrowthStore, create: bool):
        self.store = store
        self.create = create
        self.handle = None
        self.acquired = False

    def _discard_handle(self) -> None:
        if self.handle is not None:
            handle, self.handle = self.handle, None
            try:
                handle.close()
            except OSError:
                self.store._fail("writer_lock_failed")

    def __enter__(self):
        store = self.store
        path = store.lock_path
        if path is None:
            return False
        try:
            if not path.exists() and not self.create:
                # A read may validate a manually supplied log without creating a
                # lock. A later writer will create it; post-read stat is checked.
                return True
            self.handle = path.open("a+b" if self.create else "rb")
            self.handle.seek(0, os.SEEK_END)
            if self.create and self.handle.tell() == 0:
                self.handle.write(b"\0")
                self.handle.flush()
            self.handle.seek(0)
        except OSError:
            store._fail("writer_lock_failed")
            self._discard_handle()
            return False
        try:
            if msvcrt is not None:
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            elif fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                store._fail("writer_lock_unavailable")
                self._discard_handle()
                return False
        except OSError as exc:
            busy_codes = (errno.EACCES, errno.EAGAIN, errno.EDEADLK)
            if exc.errno in busy_codes or getattr(exc, "winerror", None) in (33, 36):
                # Contention is retryable and must never degrade the store.
                store.busy = True
            else:
                store._fail("writer_lock_failed")
            self._discard_handle()
            return False
        self.acquired = True
        store.busy = False
        return True

    def __exit__(self, exc_type, exc, tb):
        if self.handle is not None and self.acquired:
            try:
                self.handle.seek(0)
                if msvcrt is not None:
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                self.store._fail("writer_unlock_failed")
        self._discard_handle()
        return False
