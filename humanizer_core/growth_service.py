# -*- coding: utf-8 -*-
"""Conservative orchestration for the opt-in metadata-only growth skeleton."""

from __future__ import annotations

import math
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from functools import wraps
from pathlib import Path
from typing import Any

from .growth_diary import MAX_EVENTS_SCAN, build_diary
from .growth_engine import (
    STAGE_NAME,
    STAGE_REASON,
    is_scope_id,
    normalize_config,
    scope_id_for,
)
from .growth_store import GrowthStore

_SOURCE_RE = re.compile(r"^(?:reply|proactive)$")
MAX_PENDING_WRITES = 256
#: Parked (non-busy failure) metadata is kept only for diagnosis and a possible
#: post-config-change retry; it is capped so a broken scope cannot grow forever.
MAX_STUCK_WRITES = 1024
#: Internal hard page bound; the web layer already caps at 100.
MAX_EVENTS_PAGE = 1000
#: Upper bound for one unscoped console snapshot; each listed scope costs a log
#: stat/read, so an unbounded directory walk must not be reachable over HTTP.
MAX_SCOPE_SUMMARIES = 100


def _empty_state(scope_id: str = "") -> dict[str, Any]:
    return {
        "scope_id": scope_id,
        "stage": 0,
        "stage_name": STAGE_NAME,
        "stage_reason": STAGE_REASON,
        "user_turns": 0,
        "bot_turns": 0,
        "event_count": 0,
        "started_at": None,
        "last_event_ts": None,
        "days_known": 0.0,
    }


def _synchronized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return locked


class GrowthService:
    """Routes events into hashed scope stores and renders only explicit facts."""

    def __init__(self, data_dir: Path | None, config: Mapping[str, Any]):
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.config = normalize_config(config)
        self._stores: dict[str, GrowthStore] = {}
        self._lock = threading.RLock()
        # Volatile metadata only: no plaintext scope/message and no crash-durability
        # claim. Busy events stay FIFO until tick persists them or close stops work.
        self._pending: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        # Non-busy failures cannot succeed without a config/state change; park them
        # outside the retry queue so they neither occupy capacity nor claim "pending".
        self._stuck: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        self._retry_parked = False
        self._pending_rejected = 0
        self._closed = False

    def _queue_full(self) -> bool:
        return len(self._pending) >= MAX_PENDING_WRITES

    @_synchronized
    def configure(self, config: Mapping[str, Any]) -> dict[str, Any]:
        """Replace live configuration with a normalized copy."""
        upcoming = normalize_config(config)
        if upcoming["max_events"] != self.config["max_events"]:
            # A quota change is the only common way a parked item becomes writable.
            self._retry_parked = True
        self.config = upcoming
        for store in self._stores.values():
            store.max_events = self.config["max_events"]
        return dict(self.config)

    def _store(self, scope_id: str) -> GrowthStore:
        if not is_scope_id(scope_id):
            raise ValueError("invalid_scope_id")
        store = self._stores.get(scope_id)
        if store is None:
            store = GrowthStore(self.data_dir, scope_id, self.config["max_events"])
            self._stores[scope_id] = store
        else:
            store.max_events = self.config["max_events"]
        return store

    @staticmethod
    def _valid_event_inputs(event_id: str, now: float, text_length: int) -> bool:
        if not isinstance(event_id, str) or not (1 <= len(event_id) <= 128) or event_id == "start":
            return False
        if re.fullmatch(r"[A-Za-z0-9_.:-]+", event_id) is None:
            return False
        if isinstance(now, bool) or not isinstance(now, (int, float)) or now < 0:
            return False
        try:
            if not math.isfinite(now):
                return False
        except (OverflowError, TypeError, ValueError):
            return False
        if type(text_length) is not int or not 0 <= text_length <= 1000000:
            return False
        return True

    def _note(self, kind: str, scope: str, event_id: str, now: float, text_length: int, source: str | None = None) -> bool:
        if self._closed or not self.config["enabled"] or self.data_dir is None:
            return False
        if not self._valid_event_inputs(event_id, now, text_length):
            return False
        # Adapters may already hand over a hash; hashing twice would only add a
        # needless round trip and make the on-disk id harder to trace.
        if is_scope_id(scope):
            hashed = scope
        else:
            try:
                hashed = scope_id_for(scope)
            except (TypeError, ValueError):
                return False
        event: dict[str, Any] = {
            "schema_version": 1,
            "type": kind,
            "scope_id": hashed,
            "event_id": event_id,
            "at": now,
            "text_length": text_length,
        }
        if kind == "bot_turn":
            event["source"] = source or "reply"
        key = (hashed, event_id)
        if key in self._pending:
            return False  # Already accepted for retry, not yet persisted.
        store = self._store(hashed)
        if self._persist_event(store, event):
            return True
        if store.busy and not store.degraded:
            if self._queue_full():
                self._pending_rejected += 1
            else:
                self._pending[key] = event
        return False

    @staticmethod
    def _persist_event(store: GrowthStore, event: Mapping[str, Any]) -> bool:
        # Fatal storage state must short-circuit before touching the writer path;
        # only a healthy store may attempt the single-lock start+turn batch.
        if store.degraded or store._write_failed:
            return False
        return store.append_with_start(event)

    def _park_stuck(self, key: tuple[str, str], event: dict[str, Any]) -> None:
        """Move an undeliverable item out of the retry queue, keeping it traceable."""
        if len(self._stuck) >= MAX_STUCK_WRITES:
            self._stuck.popitem(last=False)
            self._pending_rejected += 1
        self._stuck[key] = event

    def _retry_pending(self) -> None:
        # Phase 1: busy-contended metadata retries in arrival order. A non-busy
        # failure (quota, bad line, storage error) is parked instead of retried,
        # otherwise it would occupy a queue slot forever and make `pending_writes`
        # permanently non-zero.
        blocked: set[str] = set()
        for key, event in list(self._pending.items()):
            if key[0] in blocked:
                continue
            store = self._store(key[0])
            if store.degraded or store.cap_reached:
                # Permanent for this run: park instead of keeping a slot that will
                # never become writable and would pin pending_writes above zero.
                self._pending.pop(key, None)
                self._park_stuck(key, event)
                blocked.add(key[0])
                continue
            if self._persist_event(store, event):
                self._pending.pop(key, None)
                continue
            if store.busy:
                blocked.add(key[0])
                continue
            self._pending.pop(key, None)
            self._park_stuck(key, event)
        # Phase 2: parked items are only retried after a config change that may
        # have raised the quota; a permanent error otherwise never clears itself.
        if self._retry_parked:
            for key, event in list(self._stuck.items()):
                store = self._store(key[0])
                if store.degraded or store.cap_reached:
                    continue
                if self._persist_event(store, event):
                    self._stuck.pop(key, None)
            self._retry_parked = False

    @_synchronized
    def note_user(self, scope: str, event_id: str, now: float, text_length: int) -> bool:
        return self._note("user_turn", scope, event_id, now, text_length)

    @_synchronized
    def note_bot(self, scope: str, event_id: str, now: float, text_length: int, source: str = "reply") -> bool:
        if not isinstance(source, str) or _SOURCE_RE.fullmatch(source) is None:
            return False
        return self._note("bot_turn", scope, event_id, now, text_length, source=source)

    @staticmethod
    def _safe_now(now: float | None) -> float:
        if now is None:
            return time.time()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or now < 0:
            return time.time()
        try:
            if math.isfinite(now):
                return float(now)
        except (OverflowError, TypeError, ValueError):
            pass
        return time.time()

    def _read_state(self, scope_id: str, now: float) -> tuple[dict[str, Any], GrowthStore]:
        store = self._store(scope_id)
        return store.state(now=now), store

    @_synchronized
    def render(self, scope: str, now: float) -> tuple[str, str]:
        """Return bounded identity/situation prompts; disabled mode injects nothing."""
        if self._closed or not self.config["enabled"]:
            return "", ""
        if is_scope_id(scope):
            hashed = scope
        else:
            try:
                hashed = scope_id_for(scope)
            except (TypeError, ValueError):
                return "", ""
        state, _store = self._read_state(hashed, self._safe_now(now))
        if not state["event_count"]:
            return "", ""

        identity = (
            "[成长观察：已核实的元数据]\n"
            f"当前记录阶段：{state['stage_name']}（阶段 {state['stage']}）。\n"
            "目前仅记录消息数量与时间；没有可据此确认的偏好、经历或人格变化。"
        )
        situation = (
            "[本会话记录摘要]\n"
            f"已记录用户消息 {state['user_turns']} 条、回复 {state['bot_turns']} 条。"
        )
        return identity[: self.config["identity_budget"]], situation[: self.config["situation_budget"]]

    def _scope_ids_on_disk(self) -> tuple[list[str], str]:
        """Enumerate hash scopes; an untrusted root is reported, never hidden."""
        if self.data_dir is None:
            return [], ""
        root = self.data_dir / "growth"
        try:
            if root.is_symlink():
                return [], "unsafe_storage_path"
            if not root.exists():
                return [], ""
            if not root.is_dir():
                return [], "unsafe_storage_path"
            result = []
            for item in root.iterdir():
                if item.is_dir() and not item.is_symlink() and is_scope_id(item.name):
                    result.append(item.name)
            return sorted(result), ""
        except OSError:
            return [], "storage_unavailable"

    @_synchronized
    def snapshot(self, scope_id: str = "", now: float | None = None) -> dict[str, Any]:
        """Summarize selected scope or list scope summaries without selecting one."""
        if scope_id and not is_scope_id(scope_id):
            raise ValueError("invalid_scope_id")
        if self._closed or not self.config["enabled"]:
            return {
                "enabled": bool(self.config["enabled"] and not self._closed),
                **_empty_state(),
                "degraded": False,
                "error": "",
                "scopes": [],
                "cap_reached": False,
                "pending_writes": 0,
                "stuck_writes": 0,
                "rejected_writes": 0,
                "queue_full": False,
                "scopes_truncated": False,
                "busy": False,
            }
        current_time = self._safe_now(now)
        disk_ids, disk_error = self._scope_ids_on_disk()
        all_ids = set(disk_ids) | set(self._stores)
        ordered = sorted(all_ids)
        # Each listed scope costs a log read; bound one console request even if
        # the directory legitimately holds far more scopes than the page shows.
        scopes_truncated = len(ordered) > MAX_SCOPE_SUMMARIES
        listed = ordered[:MAX_SCOPE_SUMMARIES]
        if scope_id and scope_id not in listed:
            listed.append(scope_id)
        # Aggregates also cover already-cached stores beyond the listing cap: they
        # cost no extra IO and must not be reported healthy while actually broken.
        aggregated = sorted(set(listed) | set(self._stores))
        summaries: list[dict[str, Any]] = []
        pending_by_scope: dict[str, int] = {}
        stuck_by_scope: dict[str, int] = {}
        for pending_scope, _event_id in self._pending:
            pending_by_scope[pending_scope] = pending_by_scope.get(pending_scope, 0) + 1
        for stuck_scope, _event_id in self._stuck:
            stuck_by_scope[stuck_scope] = stuck_by_scope.get(stuck_scope, 0) + 1
        current_state = _empty_state(scope_id)
        current_store: GrowthStore | None = None
        for item_id in listed:
            state, store = self._read_state(item_id, current_time)
            if (
                state["event_count"]
                or store.degraded
                or pending_by_scope.get(item_id)
                or stuck_by_scope.get(item_id)
            ):
                summaries.append({
                    "id": item_id,
                    "stage_name": state["stage_name"],
                    "event_count": state["event_count"],
                    "last_event_ts": state["last_event_ts"],
                    "pending_writes": pending_by_scope.get(item_id, 0),
                    "stuck_writes": stuck_by_scope.get(item_id, 0),
                })
            if scope_id and item_id == scope_id:
                current_state, current_store = state, store
        if not scope_id:
            inspected = [self._store(item_id) for item_id in aggregated]
            degraded_errors = [s.error for s in inspected if s.degraded and s.error]
            other_errors = [s.error for s in inspected if not s.degraded and s.error]
            degraded = bool(disk_error) or bool(degraded_errors)
            error = disk_error or (
                degraded_errors[0] if degraded_errors
                else (other_errors[0] if other_errors else "")
            )
            cap_reached = any(s.cap_reached for s in inspected)
            busy = any(s.busy for s in inspected)
            pending_writes = len(self._pending)
            stuck_writes = len(self._stuck)
            rejected_writes = self._pending_rejected
            queue_full = self._queue_full()
        else:
            current_store = current_store or self._store(scope_id)
            degraded = current_store.degraded
            error = current_store.error
            cap_reached = current_store.cap_reached
            busy = current_store.busy
            pending_writes = pending_by_scope.get(scope_id, 0)
            stuck_writes = stuck_by_scope.get(scope_id, 0)
            # Global counters cannot be attributed to one scope; reporting them on
            # a scoped request would leak unrelated conversations' state.
            rejected_writes = 0
            queue_full = False
        # A concrete per-scope storage error must not be masked by a generic
        # queue hint; pending markers only fill an otherwise empty error slot.
        if not degraded and not error:
            if queue_full:
                error = "pending_queue_full"
            elif pending_writes:
                error = "pending_writes"
            elif stuck_writes:
                error = "stuck_writes"
            elif busy:
                error = "writer_busy"
        return {
            "enabled": bool(self.config["enabled"]),
            **current_state,
            "degraded": bool(degraded),
            "error": error,
            "busy": bool(busy),
            "scopes": summaries,
            "cap_reached": bool(cap_reached),
            "pending_writes": pending_writes,
            "stuck_writes": stuck_writes,
            "rejected_writes": rejected_writes,
            "queue_full": bool(queue_full),
            "scopes_truncated": bool(scopes_truncated),
        }

    @_synchronized
    def events(self, scope_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """Return only validated metadata for an explicitly selected hash scope."""
        if self._closed or not self.config["enabled"] or not scope_id:
            return []
        if not is_scope_id(scope_id):
            raise ValueError("invalid_scope_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("invalid_limit")
        if limit > MAX_EVENTS_PAGE:
            raise ValueError("invalid_limit")
        store = self._store(scope_id)
        result = store.events(limit=limit)
        # Return copies containing only the schema-approved metadata keys.
        return [dict(event) for event in result]

    @_synchronized
    def diary(
        self,
        scope_id: str = "",
        days: int = 7,
        tz_offset_minutes: int = 0,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Read-only diary projection of already-stored metadata (v4.9.1).

        Disabled/closed service returns a zero-filled diary so the page never
        reports an error for an intentional opt-out. No new data is written.
        """
        if self._closed or not self.config["enabled"] or not scope_id:
            return build_diary((), now=now, days=days, tz_offset_minutes=tz_offset_minutes)
        if not is_scope_id(scope_id):
            raise ValueError("invalid_scope_id")
        rows = self._store(scope_id).events(limit=MAX_EVENTS_SCAN)
        return build_diary(rows, now=now, days=days, tz_offset_minutes=tz_offset_minutes)

    @_synchronized
    def tick(self, now: float) -> None:
        """Retry queued metadata, refresh caches, and batch the derived snapshot."""
        if self._closed or not self.config["enabled"]:
            return
        current_time = self._safe_now(now)
        self._retry_pending()
        for store in list(self._stores.values()):
            # Updates the same cache used by render/snapshot (including elapsed
            # time) without copying logs; state.json is written once per cycle.
            store.state(now=current_time)
            store.flush_state()

    @_synchronized
    def close(self) -> None:
        """Stop without IO; unpersisted volatile queues are dropped here.

        Pending/stuck metadata is never written by close; clearing it makes the
        post-close snapshot truthful instead of reporting retained-but-unusable
        items.
        """
        if self._closed:
            return
        for store in self._stores.values():
            store.close()
        self._stores.clear()
        self._pending.clear()
        self._stuck.clear()
        self._closed = True


__all__ = ["GrowthService"]
