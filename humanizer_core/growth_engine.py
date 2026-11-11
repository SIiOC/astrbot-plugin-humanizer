# -*- coding: utf-8 -*-
"""Pure, metadata-only growth event validation and derivation.

This first-version skeleton intentionally has no semantic progression: message
counts and elapsed time are observable facts, not evidence of personality change.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "identity_budget": 600,
    "situation_budget": 260,
    "tick_minutes": 5,
    "max_events": 20000,
    "debug": False,
}

# Schema max events is aligned with the storage byte cap. Event lines observed in
# practice are ~230-325 bytes, so 150k events ≈ 35-49 MiB with a 27-48% margin
# below 64 MiB; the byte guard therefore cannot silently preempt the quota.
MAX_EVENTS_LIMIT = 150000

_CONFIG_LIMITS = {
    "identity_budget": (100, 900),
    "situation_budget": (80, 400),
    "tick_minutes": (1, 60),
    "max_events": (100, MAX_EVENTS_LIMIT),
}
_SCOPE_RE = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SOURCE_RE = re.compile(r"^(?:reply|proactive)$")
_EVENT_TYPES = frozenset(("start", "user_turn", "bot_turn"))
#: Single source of truth for the fixed observation-only stage copy.
STAGE_NAME = "观察积累"
STAGE_REASON = "尚未启用语义事件，消息数量和天数不会自动晋级"


def normalize_config(raw: Any) -> dict[str, Any]:
    """Return a strict, bounded config copy; invalid values fall back safely."""
    source = raw if isinstance(raw, Mapping) else {}
    result = dict(DEFAULTS)
    for key in ("enabled", "debug"):
        value = source.get(key, DEFAULTS[key])
        result[key] = value if type(value) is bool else DEFAULTS[key]

    for key, (minimum, maximum) in _CONFIG_LIMITS.items():
        if key not in source:
            result[key] = DEFAULTS[key]
            continue
        value = source[key]
        # Do not accept bool as an integer, numeric strings, NaN, or infinity.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            result[key] = DEFAULTS[key]
            continue
        if isinstance(value, float) and not math.isfinite(value):
            result[key] = DEFAULTS[key]
            continue
        if value < minimum:
            result[key] = minimum
        elif value > maximum:
            result[key] = maximum
        else:
            result[key] = int(value)
    return result


def scope_id_for(scope: str) -> str:
    """Hash an ephemeral conversation scope; the original value is never stored."""
    if not isinstance(scope, str) or not scope:
        raise ValueError("invalid_scope")
    try:
        encoded = scope.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("invalid_scope") from exc
    return hashlib.sha256(encoded).hexdigest()


def is_scope_id(value: Any) -> bool:
    return isinstance(value, str) and _SCOPE_RE.fullmatch(value) is not None


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def validate_event(event: Any, expected_scope_id: str | None = None) -> bool:
    """Validate one complete metadata-only schema-v1 JSONL event."""
    if not isinstance(event, Mapping):
        return False
    event_type = event.get("type")
    if not isinstance(event_type, str) or event_type not in _EVENT_TYPES:
        return False
    required = {"schema_version", "type", "scope_id", "event_id", "at"}
    if event_type in ("user_turn", "bot_turn"):
        required = required | {"text_length"}
    if event_type == "bot_turn":
        required = required | {"source"}
    if not required.issubset(event.keys()) or not set(event.keys()).issubset(required):
        return False

    version = event.get("schema_version")
    if type(version) is not int or version != 1:
        return False
    event_scope = event.get("scope_id")
    if not is_scope_id(event_scope):
        return False
    if expected_scope_id is not None and event_scope != expected_scope_id:
        return False

    event_id = event.get("event_id")
    if not isinstance(event_id, str) or _EVENT_ID_RE.fullmatch(event_id) is None:
        return False
    if (event_type == "start") != (event_id == "start"):
        return False
    timestamp = event.get("at")
    if not _finite_number(timestamp) or timestamp < 0:
        return False

    if "text_length" in event:
        length = event["text_length"]
        # 0 is valid on purpose: an image/sticker-only private message still
        # counts as one user turn, while the adapter only records bot turns it
        # actually delivered (hence a positive length).
        if type(length) is not int or not 0 <= length <= 1000000:
            return False
    if event_type in ("user_turn", "bot_turn") and "text_length" not in event:
        return False
    if event_type == "bot_turn":
        source = event.get("source")
        if not isinstance(source, str) or _SOURCE_RE.fullmatch(source) is None:
            return False
    return True


def derive_state(events: Iterable[Mapping[str, Any]], now: float | None = None) -> dict[str, Any]:
    """Derive verifiable counts/timestamps; never infer an advancement stage."""
    valid: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    scope: str | None = None
    for event in events:
        if not validate_event(event):
            continue
        event_id = event["event_id"]
        if event_id in seen:
            continue
        if scope is not None and event["scope_id"] != scope:
            continue
        scope = event["scope_id"]
        seen.add(event_id)
        valid.append(event)

    starts = [float(event["at"]) for event in valid if event["type"] == "start"]
    timestamps = [float(event["at"]) for event in valid]
    started_at = min(starts) if starts else (min(timestamps) if timestamps else None)
    last_event_ts = max(timestamps) if timestamps else None
    normalized_now: float | None = None
    if _finite_number(now):
        normalized_now = float(now)
    days_known = 0.0
    if started_at is not None and normalized_now is not None:
        days_known = max(0.0, (normalized_now - started_at) / 86400.0)

    return {
        "scope_id": scope or "",
        "stage": 0,
        "stage_name": STAGE_NAME,
        "stage_reason": STAGE_REASON,
        "user_turns": sum(event["type"] == "user_turn" for event in valid),
        "bot_turns": sum(event["type"] == "bot_turn" for event in valid),
        "event_count": len(valid),
        "started_at": started_at,
        "last_event_ts": last_event_ts,
        "days_known": days_known,
    }


__all__ = [
    "DEFAULTS",
    "MAX_EVENTS_LIMIT",
    "STAGE_NAME",
    "STAGE_REASON",
    "derive_state",
    "is_scope_id",
    "normalize_config",
    "scope_id_for",
    "validate_event",
]
