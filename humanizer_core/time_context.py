"""Immutable, framework-independent time context data.

This module is deliberately limited to data assembly.  It does not render
prompt text and does not import the older ``time_flow`` or ``life`` modules.
The separate timestamp fields are intentional: callers can choose the
reference appropriate for a particular policy without this module inventing
fallbacks or combining activity streams.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


Timestamp = float | int | None
ClockValue = datetime | float | int


@runtime_checkable
class Clock(Protocol):
    """Clock protocol for an object whose ``now`` method returns a time.

    :func:`build_snapshot` also accepts a zero-argument callable.  Supporting
    both forms keeps the data layer easy to use with small test fakes without
    importing a concrete clock implementation.
    """

    def now(self) -> ClockValue:
        """Return the injected current datetime or timestamp."""


def _clock_value(clock: Clock | Callable[[], ClockValue]) -> ClockValue:
    """Read an injected clock without ever falling back to system time."""
    method = getattr(clock, "now", None)
    if callable(method):
        return method()
    if callable(clock):
        return clock()
    raise TypeError("clock must provide now() or be a zero-argument callable")


def _timestamp_for(dt: datetime) -> float | None:
    """Derive a timestamp only when the datetime carries timezone semantics.

    A naive datetime is retained as-is rather than being silently interpreted
    in the process timezone.  Callers that have a timestamp for a naive
    datetime can provide both explicitly.
    """
    if dt.tzinfo is None:
        return None
    return dt.timestamp()


def _resolve_now(
    *,
    now_datetime: datetime | None,
    now_ts: Timestamp,
    clock: Clock | Callable[[], ClockValue] | None,
) -> tuple[datetime | None, Timestamp]:
    """Resolve explicit time values and, only then, an injected clock."""
    if now_datetime is None and now_ts is None and clock is not None:
        value = _clock_value(clock)
        if isinstance(value, datetime):
            now_datetime = value
            now_ts = _timestamp_for(value)
        else:
            now_ts = value

    if now_datetime is not None and now_ts is None:
        now_ts = _timestamp_for(now_datetime)
    return now_datetime, now_ts


def _table_value(source: Any, key: object | None) -> Any:
    """Extract one scalar from a per-conversation mapping.

    ``None`` as a key intentionally means "no selected conversation".  A
    scalar is accepted as a convenience for callers that already selected a
    conversation.  No validation, coercion, or fallback between timestamp
    fields is performed here.
    """
    if source is None:
        return None
    if isinstance(source, Mapping):
        if key is None:
            return None
        return source.get(key)
    return source


def _optional_value(source: Any, key: object | None) -> Any:
    """Extract optional per-conversation data using the same clear key rule."""
    return _table_value(source, key)


def _mapping_copy(value: Any) -> Any:
    """Make optional mapping data read-only at the snapshot boundary."""
    if isinstance(value, Mapping):
        return MappingProxyType(dict(value))
    return value


@dataclass(frozen=True, slots=True)
class TimeContextSnapshot:
    """A point-in-time collection of conversation time facts.

    ``now_ts`` and ``now_datetime`` are intentionally separate.  An aware
    explicit datetime can supply ``now_ts`` when the latter is omitted; a
    naive datetime is preserved without an implicit process-timezone
    conversion.  Conversely, a timestamp never causes a datetime to be
    synthesized because its timezone is not known here.

    Activity fields are also intentionally separate:

    * ``previous_seen`` is the prior observation used by a caller's gap policy;
    * ``last_seen`` is the latest merged observation, if the caller has one;
    * ``first_seen`` is the first observation;
    * ``user_last_ts`` and ``ai_last_ts`` are the two directional timestamps.

    The ``gap_reference`` and ``silence_reference`` properties are transparent
    aliases for ``previous_seen`` and ``user_last_ts`` respectively.  They do
    not select a fallback, calculate an elapsed duration, or merge fields.
    ``life_state`` and ``calendar_data`` are optional caller-owned data
    snapshots; mappings are copied into read-only outer mappings.
    """

    now_ts: Timestamp = None
    now_datetime: datetime | None = None
    previous_seen: Any = None
    last_seen: Any = None
    first_seen: Any = None
    user_last_ts: Any = None
    ai_last_ts: Any = None
    life_state: Any = None
    calendar_data: Any = None

    def __post_init__(self) -> None:
        # A frozen dataclass prevents field reassignment.  Copying optional
        # mappings also prevents the common outer-container mutation from
        # changing an already-created snapshot.
        object.__setattr__(self, "life_state", _mapping_copy(self.life_state))
        object.__setattr__(self, "calendar_data", _mapping_copy(self.calendar_data))

    @property
    def now(self) -> datetime | None:
        """Compatibility alias for the explicit current datetime."""
        return self.now_datetime

    @property
    def now_dt(self) -> datetime | None:
        """Short alias for :attr:`now_datetime`."""
        return self.now_datetime

    @property
    def timestamp(self) -> Timestamp:
        """Compatibility alias for :attr:`now_ts`."""
        return self.now_ts

    @property
    def now_timestamp(self) -> Timestamp:
        """Explicit-name alias for :attr:`now_ts`."""
        return self.now_ts

    @property
    def prev_seen(self) -> Any:
        """Compatibility alias for :attr:`previous_seen`."""
        return self.previous_seen

    @property
    def last_user_ts(self) -> Any:
        """Compatibility alias for :attr:`user_last_ts`."""
        return self.user_last_ts

    @property
    def last_ai_ts(self) -> Any:
        """Compatibility alias for :attr:`ai_last_ts`."""
        return self.ai_last_ts

    @property
    def calendar(self) -> Any:
        """Compatibility alias for :attr:`calendar_data`."""
        return self.calendar_data

    @property
    def calendar_facts(self) -> Any:
        """Compatibility alias for :attr:`calendar_data`."""
        return self.calendar_data

    @property
    def gap_reference(self) -> Any:
        """Return exactly ``previous_seen``; never infer another reference."""
        return self.previous_seen

    @property
    def silence_reference(self) -> Any:
        """Return exactly ``user_last_ts``; never merge directional fields."""
        return self.user_last_ts

    @classmethod
    def from_mappings(
        cls,
        key: object | None = None,
        *,
        now: datetime | None = None,
        now_datetime: datetime | None = None,
        now_ts: Timestamp = None,
        previous_seen: Any = None,
        last_seen: Any = None,
        first_seen: Any = None,
        user_last_ts: Any = None,
        ai_last_ts: Any = None,
        life_state: Any = None,
        calendar_data: Any = None,
        calendar: Any = None,
        clock: Clock | Callable[[], ClockValue] | None = None,
    ) -> "TimeContextSnapshot":
        """Build a snapshot from per-key timestamp and optional-data mappings.

        ``key`` selects one conversation from each activity mapping.  Scalar
        activity values are accepted when a caller has already selected the
        conversation.  A missing key becomes ``None`` independently for each
        field: no value is copied from ``last_seen`` to ``previous_seen`` (or
        between user and AI sides).

        ``now``/``now_datetime`` is explicit and wins over ``clock``.  A clock
        is consulted only when both current-time fields are absent.  A
        callable clock may return an aware/naive datetime or a numeric
        timestamp.
        """
        if now_datetime is None:
            now_datetime = now
        now_datetime, now_ts = _resolve_now(
            now_datetime=now_datetime,
            now_ts=now_ts,
            clock=clock,
        )
        if calendar_data is None:
            calendar_data = calendar
        return cls(
            now_ts=now_ts,
            now_datetime=now_datetime,
            previous_seen=_table_value(previous_seen, key),
            last_seen=_table_value(last_seen, key),
            first_seen=_table_value(first_seen, key),
            user_last_ts=_table_value(user_last_ts, key),
            ai_last_ts=_table_value(ai_last_ts, key),
            life_state=_optional_value(life_state, key),
            calendar_data=_optional_value(calendar_data, key),
        )

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, Any] | None,
        *,
        key: object | None = None,
        now: datetime | None = None,
        now_datetime: datetime | None = None,
        now_ts: Timestamp = None,
        clock: Clock | Callable[[], ClockValue] | None = None,
    ) -> "TimeContextSnapshot":
        """Build from one record mapping, with a nested ``key`` if present.

        This is the record-shaped counterpart to :meth:`from_mappings`.  The
        accepted aliases mirror the explicit public field names (for example,
        ``prev_seen`` and ``last_user_ts``) without changing their semantics.
        Missing fields remain ``None``.
        """
        raw: Mapping[str, Any] = mapping or {}
        if key is not None and key in raw and isinstance(raw[key], Mapping):
            raw = raw[key]

        def value(*names: str) -> Any:
            for name in names:
                if name in raw:
                    return raw[name]
            return None

        if now_datetime is None:
            now_datetime = now
        if now_datetime is None:
            candidate = value("now_datetime", "now_dt", "now")
            if isinstance(candidate, datetime):
                now_datetime = candidate
        if now_ts is None:
            candidate = value("now_ts", "now_timestamp", "timestamp")
            if candidate is not None:
                now_ts = candidate

        now_datetime, now_ts = _resolve_now(
            now_datetime=now_datetime,
            now_ts=now_ts,
            clock=clock,
        )
        return cls(
            now_ts=now_ts,
            now_datetime=now_datetime,
            previous_seen=value("previous_seen", "prev_seen"),
            last_seen=value("last_seen"),
            first_seen=value("first_seen"),
            user_last_ts=value("user_last_ts", "last_user_ts"),
            ai_last_ts=value("ai_last_ts", "last_ai_ts"),
            life_state=value("life_state", "life"),
            calendar_data=value("calendar_data", "calendar", "calendar_facts"),
        )


def gap_reference(snapshot: TimeContextSnapshot) -> Any:
    """Return ``snapshot.previous_seen`` without applying a gap policy."""
    return snapshot.previous_seen


def silence_reference(snapshot: TimeContextSnapshot) -> Any:
    """Return ``snapshot.user_last_ts`` without merging directional fields."""
    return snapshot.user_last_ts


def build_snapshot(
    *,
    now: datetime | None = None,
    now_datetime: datetime | None = None,
    now_ts: Timestamp = None,
    clock: Clock | Callable[[], ClockValue] | None = None,
    key: object | None = None,
    previous_seen: Any = None,
    last_seen: Any = None,
    first_seen: Any = None,
    user_last_ts: Any = None,
    ai_last_ts: Any = None,
    life_state: Any = None,
    calendar_data: Any = None,
    calendar: Any = None,
) -> TimeContextSnapshot:
    """Construct a snapshot with explicit or injected current time.

    With no ``now``/``now_datetime`` and no ``clock``, this function does not
    read the system clock; the current-time fields remain missing.  This makes
    construction deterministic and keeps timezone decisions with the caller.
    """
    return TimeContextSnapshot.from_mappings(
        key=key,
        now=now,
        now_datetime=now_datetime,
        now_ts=now_ts,
        previous_seen=previous_seen,
        last_seen=last_seen,
        first_seen=first_seen,
        user_last_ts=user_last_ts,
        ai_last_ts=ai_last_ts,
        life_state=life_state,
        calendar_data=calendar_data,
        calendar=calendar,
        clock=clock,
    )


__all__ = [
    "Clock",
    "TimeContextSnapshot",
    "build_snapshot",
    "gap_reference",
    "silence_reference",
]
