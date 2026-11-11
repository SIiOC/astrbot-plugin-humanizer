# -*- coding: utf-8 -*-
"""v4.4.0 回归：设置导入导出、最近清理明细、主动页进度、schema 死键守卫。"""

import json
import sys
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import main as main_mod  # noqa: E402


def _dashboard_plugin():
    from humanizer_core.metrics import MetricsSink

    plugin = main_mod.HumanizerPlugin.__new__(main_mod.HumanizerPlugin)
    plugin._metrics = MetricsSink(())
    plugin._prev_seen = {}
    plugin._emotions = {}
    plugin._next_trigger_ts = {}
    plugin._events_ring = plugin._metrics.events
    plugin._p_int = lambda key, default=None: default
    plugin._time = lambda key, default=None: default
    plugin._retrieve_cache = SimpleNamespace(hits=0, misses=0)
    plugin._inject_stats = {"turns": 0}
    plugin._cleanup_ring = plugin._metrics.cleanup
    return plugin


class TestCleanupRing(unittest.TestCase):
    def test_record_cleanup_caps_and_formats(self):
        from humanizer_core.metrics import MetricsSink

        plugin = main_mod.HumanizerPlugin.__new__(main_mod.HumanizerPlugin)
        plugin._metrics = MetricsSink((), cleanup_cap=3)
        plugin._cleanup_ring = plugin._metrics.cleanup
        for index in range(5):
            main_mod.HumanizerPlugin._record_cleanup(
                plugin, f"before{index}", f"after{index}", ["emoji", f"stage{index}"]
            )
        self.assertEqual(len(plugin._cleanup_ring), 3)
        newest = plugin._cleanup_ring[-1]
        self.assertEqual(newest["hits"], ["emoji", "stage4"])
        self.assertEqual(newest["before"], "before4")
        self.assertEqual(newest["after"], "after4")

    def test_record_cleanup_tolerates_string_hits(self):
        from humanizer_core.metrics import MetricsSink

        plugin = main_mod.HumanizerPlugin.__new__(main_mod.HumanizerPlugin)
        plugin._metrics = MetricsSink((), cleanup_cap=3)
        plugin._cleanup_ring = plugin._metrics.cleanup
        main_mod.HumanizerPlugin._record_cleanup(plugin, "a", "b", "emoji")
        self.assertEqual(plugin._cleanup_ring[0]["hits"], ["emoji"])


class TestDashboardCleanup(unittest.TestCase):
    def test_exposes_cleanup_newest_first(self):
        plugin = _dashboard_plugin()
        plugin._cleanup_ring.append({"ts": 1.0, "hits": ["emoji"]})
        plugin._cleanup_ring.append({"ts": 2.0, "hits": ["zh:ai"]})
        dash = main_mod.HumanizerPlugin.web_dashboard(plugin)
        self.assertEqual([row["ts"] for row in dash["cleanup"]], [2.0, 1.0])

    def test_missing_ring_degrades(self):
        plugin = _dashboard_plugin()
        del plugin._cleanup_ring
        dash = main_mod.HumanizerPlugin.web_dashboard(plugin)
        self.assertEqual(dash["cleanup"], [])


class TestSchemaDeadKeys(unittest.TestCase):
    """配置死键守卫：schema 里的每个键都必须在代码中被引用。"""

    def test_every_schema_key_appears_in_code(self):
        schema = json.loads(
            (_ROOT / "_conf_schema.json").read_text(encoding="utf-8")
        )
        files = [
            _ROOT / "main.py",
            _ROOT / "web_api.py",
            *sorted((_ROOT / "humanizer_core").glob("*.py")),
            *sorted((_ROOT / "services").glob("*.py")),
        ]
        blob = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore") for path in files
        )
        dead = []
        for group, meta in schema.items():
            for key in (meta.get("items") or {}):
                if ('"%s"' % key) not in blob and ("'%s'" % key) not in blob:
                    dead.append(f"{group}.{key}")
        self.assertEqual(dead, [], f"schema 存在代码从未引用的死键：{dead}")


class TestFrontendFeatures(unittest.TestCase):
    def _source(self, name):
        return (_ROOT / "webui" / "src" / "views" / name).read_text(
            encoding="utf-8"
        )

    def test_overview_cleanup_card(self):
        source = self._source("OverviewView.vue")
        self.assertIn("最近清理明细", source)
        self.assertIn("dash.value.cleanup", source)

    def test_config_import_export(self):
        source = self._source("ConfigView.vue")
        self.assertIn("exportConfig", source)
        self.assertIn("onImportFile", source)
        self.assertIn("humanizer-config.json", source)

    def test_proactive_progress(self):
        source = self._source("ProactiveView.vue")
        self.assertIn("maxUnanswered.value", source)


if __name__ == "__main__":
    unittest.main()
