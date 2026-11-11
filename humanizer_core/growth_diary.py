# -*- coding: utf-8 -*-
"""Metadata-only diary aggregation for the opt-in growth skeleton (v4.9.1).

The diary is a *read-only projection* of the already-stored metadata events. It
never stores new data, never stores message text, and never invents semantic
progress: it only groups existing ``user_turn`` / ``bot_turn`` facts by local
calendar day and hour. Growth stays disabled by default.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from .growth_engine import validate_event

#: One diary request reads at most this many recent events. This bounds IO while
#: still covering a long window for typical private chats.
MAX_EVENTS_SCAN = 5000
MAX_DAYS = 30
_DAY_KEYS = ("user_turns", "bot_turns", "proactive_turns", "user_chars", "bot_chars")


def _clamp_days(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 7
    return max(1, min(MAX_DAYS, value))


def _clamp_tz(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(-840, min(840, value))


def _safe_now(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return time.time()
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return time.time()
    if not math.isfinite(number) or number < 0:
        return time.time()
    return number


def _empty_day(day: date) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        **{key: 0 for key in _DAY_KEYS},
        "first_at": None,
        "last_at": None,
    }


def build_diary(
    events: Iterable[Mapping[str, Any]] | None,
    *,
    now: float | None = None,
    days: int = 7,
    tz_offset_minutes: int = 0,
) -> dict[str, Any]:
    """Aggregate validated metadata events into a day/hour diary window.

    Only schema-v1 growth events are counted. Events from a different scope than
    the first valid one are ignored (mirrors :func:`growth_engine.derive_state`).
    ``start`` markers are used for neither counts nor activity.
    """
    window_days = _clamp_days(days)
    offset = _clamp_tz(tz_offset_minutes)
    now_ts = _safe_now(now)
    tzinfo = timezone(timedelta(minutes=offset))
    today = datetime.fromtimestamp(now_ts, tzinfo).date()
    window = [today - timedelta(days=window_days - 1 - index) for index in range(window_days)]
    buckets = {day.isoformat(): _empty_day(day) for day in window}
    active_hours = [0] * 24

    seen: set[str] = set()
    scope: str | None = None
    counted = 0
    for event in events or ():
        if not validate_event(event):
            continue
        event_id = event["event_id"]
        if event_id in seen:
            continue
        event_scope = event["scope_id"]
        if scope is None:
            scope = event_scope
        elif event_scope != scope:
            continue
        seen.add(event_id)
        event_type = event["type"]
        if event_type not in ("user_turn", "bot_turn"):
            continue
        try:
            timestamp = float(event["at"])
        except (KeyError, TypeError, ValueError):
            continue
        moment = datetime.fromtimestamp(timestamp, tzinfo)
        bucket = buckets.get(moment.date().isoformat())
        if bucket is None:
            continue
        counted += 1
        length = int(event.get("text_length") or 0)
        if event_type == "user_turn":
            bucket["user_turns"] += 1
            bucket["user_chars"] += length
        else:
            bucket["bot_turns"] += 1
            bucket["bot_chars"] += length
            if event.get("source") == "proactive":
                bucket["proactive_turns"] += 1
        if bucket["first_at"] is None or timestamp < bucket["first_at"]:
            bucket["first_at"] = timestamp
        if bucket["last_at"] is None or timestamp > bucket["last_at"]:
            bucket["last_at"] = timestamp
        active_hours[moment.hour] += 1

    day_rows = [buckets[day.isoformat()] for day in window]
    totals = {key: sum(row[key] for row in day_rows) for key in _DAY_KEYS}
    active_days = sum(1 for row in day_rows if row["user_turns"] + row["bot_turns"] > 0)

    # Friendly current streak: consecutive active days ending today; if today has
    # no activity yet, a streak ending yesterday is still shown as current.
    streak = 0
    for index in range(len(day_rows) - 1, -1, -1):
        row = day_rows[index]
        active = row["user_turns"] + row["bot_turns"] > 0
        if active:
            streak += 1
        elif index == len(day_rows) - 1:
            continue
        else:
            break

    return {
        "window_days": window_days,
        "tz_offset_minutes": offset,
        "event_count": counted,
        "active_days": active_days,
        "streak_days": streak,
        "days": day_rows,
        "totals": totals,
        "active_hours": active_hours,
    }


__all__ = ["MAX_DAYS", "MAX_EVENTS_SCAN", "build_diary"]
