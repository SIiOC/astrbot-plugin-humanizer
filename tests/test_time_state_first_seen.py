# -*- coding: utf-8 -*-
"""v3.7.0 TimeStateStore first_seen（v2）单测（tempfile 隔离）。

兼容契约：load()/save() 旧签名行为不变（test_state.py 原有用例继续成立）；
first_seen 走 save 第二参与 load_first_seen()。
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from humanizer_core.state import TimeStateStore
from humanizer_core.time_flow import acquaintance_days

_CN = ZoneInfo("Asia/Shanghai")


def _ts(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=_CN).timestamp()


class TestAcquaintanceDays(unittest.TestCase):
    """v3.7.0 审查修复：相识天数必须按北京时间自然日进位（非 // 86400）。"""

    def test_midnight_boundary(self):
        first = _ts(2026, 9, 5, 12, 0)
        self.assertEqual(acquaintance_days(first, _ts(2026, 9, 5, 23, 59)), 1)
        self.assertEqual(acquaintance_days(first, _ts(2026, 9, 6, 0, 1)), 2)

    def test_late_night_first_chat_same_natural_day(self):
        # 23:50 首聊，次日 00:10 = 第 2 天；当晚 23:59 仍是第 1 天
        first = _ts(2026, 9, 6, 23, 50)
        self.assertEqual(acquaintance_days(first, _ts(2026, 9, 7, 0, 10)), 2)
        self.assertEqual(acquaintance_days(first, _ts(2026, 9, 6, 23, 59)), 1)

    def test_utc_day_trap(self):
        # //86400 算法在东八区早 8 点前会少一天；自然日算法不受影响
        self.assertEqual(acquaintance_days(_ts(2026, 9, 6, 3, 0), _ts(2026, 9, 7, 3, 0)), 2)
        self.assertEqual(acquaintance_days(_ts(2026, 9, 6, 9, 0), _ts(2026, 9, 6, 23, 0)), 1)

    def test_multi_day(self):
        self.assertEqual(acquaintance_days(_ts(2026, 8, 24, 12, 0), _ts(2026, 9, 7, 8, 0)), 15)

    def test_invalid_inputs_return_zero(self):
        for args in ((None, 1.0), (1.0, None), (0, 1.0), (-5, 1.0),
                     (2.0, 1.0), ("x", 1.0), (float("nan"), 1.0)):
            self.assertEqual(acquaintance_days(*args), 0, msg=str(args))


class TestTimeStateFirstSeen(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "time_state.json"
        self.store = TimeStateStore(self.path)

    def test_v2_roundtrip_both_dicts(self):
        last = {"a": 100.0, "b": 200.0}
        first = {"a": 50.0}
        self.store.save(last, first)
        self.assertEqual(self.store.load(), last)
        self.assertEqual(self.store.load_first_seen(), first)

    def test_save_without_first_seen_loads_empty(self):
        self.store.save({"a": 100.0})
        self.assertEqual(self.store.load_first_seen(), {})

    def test_v1_file_backcompat(self):
        self.path.write_text(
            '{"version": 1, "last_seen": {"ok": 100.0}}', encoding="utf-8"
        )
        self.assertEqual(self.store.load(), {"ok": 100.0})
        self.assertEqual(self.store.load_first_seen(), {})

    def test_garbage_file_both_empty(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(self.store.load(), {})
        self.assertEqual(self.store.load_first_seen(), {})

    def test_first_seen_filters_invalid_entries(self):
        self.path.write_text(
            '{"version": 2, "last_seen": {"a": 1.0}, '
            '"first_seen": {"a": 5.0, "bad": "x", "": 2, "neg": -9}}',
            encoding="utf-8",
        )
        self.assertEqual(self.store.load_first_seen(), {"a": 5.0})

    def test_saved_file_has_version_3(self):
        """v3.8.0：落盘版本升到 3（新增 user_seen/ai_seen 双向表）。"""
        import json

        self.store.save({"a": 1.0}, {"a": 0.5})
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("version"), 3)
        self.assertIn("first_seen", data)
        self.assertIn("user_seen", data)
        self.assertIn("ai_seen", data)

    def test_prune_filter_pattern_with_first_seen(self):
        """调用方收缩模式：first_seen 仅保留 prune 后 last_seen 仍存在的键。"""
        now = 10_000_000.0
        last = {"fresh": now, "stale": now - 40 * 86400.0}
        first = {"fresh": now - 100.0, "stale": now - 50 * 86400.0}
        kept = self.store.prune(last, now)
        self.store.save(kept, {k: v for k, v in first.items() if k in kept})
        self.assertEqual(self.store.load(), {"fresh": now})
        self.assertEqual(self.store.load_first_seen(), {"fresh": now - 100.0})


if __name__ == "__main__":
    unittest.main()
