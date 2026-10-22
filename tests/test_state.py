# -*- coding: utf-8 -*-
"""humanizer_core/state.py 持久化单测（tempfile 隔离，不触真实数据目录）。"""

import tempfile
import time
import unittest
from pathlib import Path

from humanizer_core.state import LifeStateStore, TimeStateStore
from humanizer_core.time_flow import LifeState, TimelineEntry


class TestTimeStateStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "time_state.json"
        self.store = TimeStateStore(self.path)

    def test_load_missing_file(self):
        self.assertEqual(self.store.load(), {})

    def test_roundtrip(self):
        data = {"aiocqq:FriendMessage:123": 1755000000.0, "webchat:session:abc": 1755000001}
        self.store.save(data)
        self.assertEqual(self.store.load(), data)

    def test_load_garbage(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(self.store.load(), {})
        self.path.write_text('{"last_seen": "bad"}', encoding="utf-8")
        self.assertEqual(self.store.load(), {})

    def test_load_filters_invalid_entries(self):
        self.path.write_text(
            '{"version": 1, "last_seen": {"ok": 100.0, "bad": "x", "": 1, "neg": -5}}',
            encoding="utf-8",
        )
        self.assertEqual(self.store.load(), {"ok": 100.0})

    def test_prune_drops_stale(self):
        now = time.time()
        data = {"new": now, "old": now - 31 * 86400.0}
        self.assertEqual(self.store.prune(data, now), {"new": now})

    def test_no_tmp_left_after_save(self):
        self.store.save({"a": 1.0})
        leftovers = list(self.path.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])


def _make_state(date: str, schedule: str = "日常") -> LifeState:
    return LifeState(
        date=date,
        schedule_summary=f"{date} {schedule}",
        timeline=[
            TimelineEntry("08:00-12:00", "居家休息", {"mood": "平静"}),
            TimelineEntry("下午", "咖啡店打工", {"location": "咖啡店"}),
        ],
        status="ok",
        generated_at="2026-08-20 08:00",
    )


class TestLifeStateStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "life_state.json"
        self.store = LifeStateStore(self.path)

    def test_set_and_current_for_date(self):
        st = _make_state("2026-08-20")
        self.store.set(st)
        cur = self.store.current_for_date("2026-08-20")
        self.assertIsNotNone(cur)
        self.assertEqual(cur.date, "2026-08-20")
        self.assertIsNone(self.store.current_for_date("2026-08-21"))

    def test_set_clears_same_date_history(self):
        self.store.set(_make_state("2026-08-20"))
        self.store.archive_before_generation("2026-08-21")
        # 归档后当日文件清空，历史里应有 08-20
        self.assertIsNone(self.store.current())
        self.assertEqual(self.store.get_by_date("2026-08-20").date, "2026-08-20")
        # 同日重新 set 时应清掉历史里的同日文件（单一事实源）
        self.store.set(_make_state("2026-08-20"))
        self.store.archive_before_generation("2026-08-21")
        names = [p.name for p in (self.path.parent / "history").glob("*.json")]
        self.assertEqual(names.count("life_state_2026.08.20.json"), 1)

    def test_archive_then_regenerate(self):
        self.store.set(_make_state("2026-08-19"))
        self.store.archive_before_generation("2026-08-20")
        self.assertIsNone(self.store.current())
        self.assertFalse(self.path.exists())
        self.store.set(_make_state("2026-08-20"))
        self.assertIsNotNone(self.store.current_for_date("2026-08-20"))

    def test_archive_same_date_noop(self):
        self.store.set(_make_state("2026-08-20"))
        self.store.archive_before_generation("2026-08-20")
        self.assertIsNotNone(self.store.current_for_date("2026-08-20"))

    def test_get_recent_history(self):
        for i in (17, 18, 19):
            d = f"2026-08-{i}"
            self.store.set(_make_state(d))
            self.store.archive_before_generation(f"2026-08-{i + 1}")
        hist = self.store.get_recent_history("2026-08-20", limit=2)
        self.assertEqual([s.date for s in hist], ["2026-08-19", "2026-08-18"])

    def test_history_prune_keeps_7(self):
        for i in range(10):
            d = f"2026-08-{10 + i:02d}"
            self.store.set(_make_state(d))
            self.store.archive_before_generation(f"2026-08-{11 + i:02d}")
        names = sorted(
            p.name for p in (self.path.parent / "history").glob("life_state_*.json")
        )
        self.assertEqual(len(names), 7)

    def test_load_missing(self):
        self.assertIsNone(self.store.current())


if __name__ == "__main__":
    unittest.main()
