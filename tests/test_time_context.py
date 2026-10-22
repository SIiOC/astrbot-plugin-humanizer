"""Tests for the framework-independent time-context snapshot."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from humanizer_core.time_context import (
    TimeContextSnapshot,
    build_snapshot,
    gap_reference,
    silence_reference,
)


class FakeClock:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def now(self):
        self.calls += 1
        return self.value


def test_snapshot_is_frozen_and_keeps_optional_mapping_data_read_only():
    snapshot = TimeContextSnapshot(
        now_ts=10.0,
        previous_seen=3.0,
        life_state={"doing": "reading"},
        calendar_data={"date": "2026-09-11"},
    )

    with pytest.raises(FrozenInstanceError):
        snapshot.now_ts = 11.0

    assert isinstance(snapshot.life_state, MappingProxyType)
    assert isinstance(snapshot.calendar_data, MappingProxyType)
    with pytest.raises(TypeError):
        snapshot.life_state["doing"] = "sleeping"


def test_from_mappings_extracts_each_timestamp_independently():
    now = datetime(2026, 9, 11, 17, 30, tzinfo=timezone(timedelta(hours=8)))
    life = {"chat-1": {"doing": "reading"}}
    calendar = {"chat-1": {"date": "2026-09-11", "term": "白露"}}

    snapshot = TimeContextSnapshot.from_mappings(
        "chat-1",
        now=now,
        previous_seen={"chat-1": 100.0},
        last_seen={"chat-1": 200.0},
        first_seen={"chat-1": 50.0},
        user_last_ts={"chat-1": 180.0},
        ai_last_ts={"chat-1": 200.0},
        life_state=life,
        calendar_data=calendar,
    )

    assert snapshot.now_datetime is now
    assert snapshot.now_ts == pytest.approx(now.timestamp())
    assert snapshot.previous_seen == 100.0
    assert snapshot.last_seen == 200.0
    assert snapshot.first_seen == 50.0
    assert snapshot.user_last_ts == 180.0
    assert snapshot.ai_last_ts == 200.0
    assert dict(snapshot.life_state) == {"doing": "reading"}
    assert dict(snapshot.calendar_data) == {"date": "2026-09-11", "term": "白露"}
    assert snapshot.gap_reference == 100.0
    assert snapshot.silence_reference == 180.0
    assert gap_reference(snapshot) == 100.0
    assert silence_reference(snapshot) == 180.0


def test_from_mapping_extracts_record_aliases_and_does_not_merge_missing_values():
    snapshot = TimeContextSnapshot.from_mapping(
        {
            "now_ts": 123.5,
            "prev_seen": 100.0,
            "last_seen": 120.0,
            "first_seen": 80.0,
            "last_user_ts": 110.0,
            "last_ai_ts": 115.0,
            "life": {"slot": "afternoon"},
            "calendar_facts": {"date": "2026-09-11"},
        }
    )

    assert snapshot.now_ts == 123.5
    assert snapshot.previous_seen == 100.0
    assert snapshot.last_seen == 120.0
    assert snapshot.first_seen == 80.0
    assert snapshot.user_last_ts == 110.0
    assert snapshot.ai_last_ts == 115.0
    assert dict(snapshot.life_state) == {"slot": "afternoon"}
    assert dict(snapshot.calendar_data) == {"date": "2026-09-11"}

    missing = TimeContextSnapshot.from_mappings(
        "missing",
        previous_seen={"known": 1.0},
        last_seen={"known": 2.0},
        first_seen={"known": 3.0},
        user_last_ts={"known": 4.0},
        ai_last_ts={"known": 5.0},
    )
    assert missing.previous_seen is None
    assert missing.last_seen is None
    assert missing.first_seen is None
    assert missing.user_last_ts is None
    assert missing.ai_last_ts is None
    assert missing.gap_reference is None
    assert missing.silence_reference is None


def test_explicit_datetime_preserves_naive_timezone_semantics_and_does_not_call_clock():
    naive = datetime(2026, 9, 11, 17, 30)
    clock = FakeClock(datetime(2000, 1, 1, tzinfo=timezone.utc))

    snapshot = build_snapshot(now=naive, clock=clock)

    assert snapshot.now_datetime is naive
    assert snapshot.now_ts is None
    assert clock.calls == 0


def test_injected_clock_is_deterministic_for_aware_datetime():
    now = datetime(2026, 9, 11, 17, 30, tzinfo=timezone.utc)
    clock = FakeClock(now)

    first = build_snapshot(clock=clock, previous_seen=10.0)
    second = build_snapshot(clock=clock, previous_seen=10.0)

    assert first == second
    assert first.now_datetime == now
    assert first.now_ts == pytest.approx(now.timestamp())
    assert clock.calls == 2


def test_injected_callable_clock_can_supply_timestamp():
    calls = []

    def clock():
        calls.append("called")
        return 9876.5

    snapshot = build_snapshot(clock=clock)

    assert snapshot.now_datetime is None
    assert snapshot.now_ts == 9876.5
    assert calls == ["called"]


def test_explicit_current_timestamp_wins_over_injected_clock():
    clock = FakeClock(999.0)
    snapshot = build_snapshot(now_ts=123.0, clock=clock)

    assert snapshot.now_ts == 123.0
    assert snapshot.now_datetime is None
    assert clock.calls == 0


def test_no_time_input_is_missing_not_system_time():
    snapshot = build_snapshot()

    assert snapshot.now_datetime is None
    assert snapshot.now_ts is None


if __name__ == "__main__":
    pytest.main([__file__])
