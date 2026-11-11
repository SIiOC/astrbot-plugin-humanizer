# -*- coding: utf-8 -*-
"""Pure tests for the read-only growth diary projection (v4.9.1)."""

import unittest
from datetime import datetime, timedelta, timezone

from humanizer_core.growth_diary import MAX_DAYS, build_diary

SCOPE = "a" * 64
TZ = timezone(timedelta(hours=8))


def _event(event_id, moment, event_type="user_turn", length=10, source=None, scope=SCOPE):
    event = {
        "schema_version": 1,
        "type": event_type,
        "scope_id": scope,
        "event_id": event_id,
        "at": moment.timestamp(),
    }
    if event_type != "start":
        event["text_length"] = length
    if event_type == "bot_turn":
        event["source"] = source or "reply"
    return event


def _moment(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


class TestBuildDiary(unittest.TestCase):
    def test_empty_window_is_zero_filled_and_has_no_content_fields(self):
        diary = build_diary([], now=_moment(30, 12).timestamp(), days=7, tz_offset_minutes=480)
        self.assertEqual(diary["window_days"], 7)
        self.assertEqual(len(diary["days"]), 7)
        self.assertEqual(diary["event_count"], 0)
        self.assertEqual(diary["active_days"], 0)
        self.assertEqual(diary["streak_days"], 0)
        self.assertEqual(diary["totals"]["user_turns"], 0)
        self.assertEqual(len(diary["active_hours"]), 24)
        allowed = {
            "date", "user_turns", "bot_turns", "proactive_turns",
            "user_chars", "bot_chars", "first_at", "last_at",
        }
        for row in diary["days"]:
            self.assertLessEqual(set(row), allowed)
        rendered = repr(diary)
        for forbidden in ("content", "message", "text"):
            self.assertNotIn(forbidden, rendered.lower().replace("text_length", ""))

    def test_day_grouping_uses_requested_timezone(self):
        events = [
            _event("e1", _moment(29, 23, 30), length=8),
            _event("e2", _moment(30, 1, 10), length=12),
            _event("e3", _moment(30, 3, 0), event_type="bot_turn", length=20),
        ]
        diary = build_diary(
            events, now=_moment(30, 12).timestamp(), days=2, tz_offset_minutes=480
        )
        self.assertEqual([row["date"] for row in diary["days"]], ["2026-10-29", "2026-10-30"])
        self.assertEqual(diary["days"][0]["user_turns"], 1)
        self.assertEqual(diary["days"][0]["user_chars"], 8)
        self.assertEqual(diary["days"][1]["user_turns"], 1)
        self.assertEqual(diary["days"][1]["bot_turns"], 1)
        self.assertEqual(diary["days"][1]["bot_chars"], 20)
        self.assertEqual([h for h, n in enumerate(diary["active_hours"]) if n], [1, 3, 23])

    def test_duplicate_ids_and_foreign_scope_are_ignored(self):
        events = [
            _event("e1", _moment(30, 9)),
            _event("e1", _moment(30, 10)),
            _event("e2", _moment(30, 11), scope="b" * 64),
            _event("e3", _moment(30, 12), length=5),
        ]
        diary = build_diary(events, now=_moment(30, 13).timestamp(), days=1, tz_offset_minutes=480)
        self.assertEqual(diary["event_count"], 2)
        self.assertEqual(diary["totals"]["user_turns"], 2)
        self.assertEqual(diary["totals"]["user_chars"], 15)

    def test_proactive_bot_turn_is_counted_separately(self):
        events = [
            _event("b1", _moment(30, 9), event_type="bot_turn", source="reply"),
            _event("b2", _moment(30, 10), event_type="bot_turn", source="proactive"),
            _event("b3", _moment(30, 11), event_type="bot_turn", source="proactive"),
        ]
        diary = build_diary(events, now=_moment(30, 12).timestamp(), days=1, tz_offset_minutes=480)
        self.assertEqual(diary["totals"]["bot_turns"], 3)
        self.assertEqual(diary["totals"]["proactive_turns"], 2)

    def test_streak_ends_today_or_yesterday(self):
        events = []
        for day in (28, 29, 30):
            events.append(_event(f"u{day}", _moment(day, 9)))
        today = _moment(30, 12).timestamp()
        self.assertEqual(
            build_diary(events, now=today, days=7, tz_offset_minutes=480)["streak_days"], 3
        )
        # No activity today: the streak still counts through yesterday.
        self.assertEqual(
            build_diary(events[:2], now=today, days=7, tz_offset_minutes=480)["streak_days"], 2
        )
        # Gap two days ago ends the streak.
        self.assertEqual(
            build_diary(events[2:], now=today, days=7, tz_offset_minutes=480)["streak_days"], 1
        )

    def test_start_marker_is_not_counted_as_activity(self):
        started = datetime(2026, 10, 1, 8, tzinfo=TZ).timestamp()
        events = [
            {
                "schema_version": 1,
                "type": "start",
                "scope_id": SCOPE,
                "event_id": "start",
                "at": started,
            }
        ]
        diary = build_diary(events, now=_moment(30, 12).timestamp(), days=7, tz_offset_minutes=480)
        self.assertEqual(diary["event_count"], 0)
        self.assertEqual(diary["active_days"], 0)
        self.assertEqual(diary["active_hours"], [0] * 24)

    def test_window_and_timezone_are_clamped(self):
        now = _moment(30, 12).timestamp()
        self.assertEqual(build_diary([], now=now, days=999)["window_days"], MAX_DAYS)
        self.assertEqual(build_diary([], now=now, days=0)["window_days"], 1)
        self.assertEqual(build_diary([], now=now, tz_offset_minutes=-9999)["tz_offset_minutes"], -840)
        self.assertEqual(build_diary([], now=now, tz_offset_minutes=9999)["tz_offset_minutes"], 840)
        self.assertEqual(build_diary([], now=now, tz_offset_minutes="x")["tz_offset_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
