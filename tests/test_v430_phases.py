# -*- coding: utf-8 -*-
"""v4.3.0 三阶段回归：发布隐私扫描 / 可观测性二期 / 配置与体验。"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import deque
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

import main as main_mod  # noqa: E402
import pre_release_scan as prs  # noqa: E402

# 显式按文件路径加载根目录实现：不能 `import package_plugin`——sys.path 里
# 若 tools/ 在前会命中兼容入口（runpy 执行打包脚本并解析 pytest argv）。
_spec = spec_from_file_location("humanizer_package_plugin", _ROOT / "package_plugin.py")
package_plugin = module_from_spec(_spec)
sys.modules["humanizer_package_plugin"] = package_plugin
_spec.loader.exec_module(package_plugin)


class TestGitHistoryScan(unittest.TestCase):
    """隐私：git 历史扫描（含已删除文件），旧提交命中应可报告。"""

    def _init_repo(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name)

        def git(*args):
            subprocess.run(
                ["git", "-C", td.name, *args],
                check=True,
                capture_output=True,
            )

        git("init", "-q")
        git("config", "user.email", "test@example.com")
        git("config", "user.name", "test")
        return root, git

    @unittest.skipUnless(shutil.which("git"), "系统无 git")
    def test_detects_path_in_deleted_file(self):
        root, git = self._init_repo()
        literal = "E" + ":" + chr(92) + "ai" + chr(92) + "data"
        (root / "old.py").write_text("p = '" + literal + "'\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "add")
        (root / "old.py").unlink()
        git("add", "-A")
        git("commit", "-qm", "delete")
        findings = prs.scan_git_history(root, limit=10)
        self.assertTrue(
            any(
                f["kind"] == "absolute_path" and "old.py" in f["path"]
                for f in findings
            ),
            findings,
        )

    @unittest.skipUnless(shutil.which("git"), "系统无 git")
    def test_clean_history_passes(self):
        root, git = self._init_repo()
        (root / "a.py").write_text("print('ok')\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "ok")
        self.assertEqual(prs.scan_git_history(root, limit=10), [])


class TestPackagingGate(unittest.TestCase):
    """隐私：打包脚本内置扫描门禁（当前仓库应 0 命中）。"""

    def test_scan_findings_clean(self):
        self.assertEqual(package_plugin._scan_findings(), [])


class TestInjectStats(unittest.TestCase):
    """可观测性：注入字符统计累加。"""

    def test_record_inject_accumulates_and_ignores_unknown(self):
        from humanizer_core.metrics import MetricsSink

        plugin = main_mod.HumanizerPlugin.__new__(main_mod.HumanizerPlugin)
        sink = MetricsSink(("turns",), inject_keys=("turns", "time", "rules"))
        plugin._metrics = sink
        main_mod.HumanizerPlugin._record_inject(plugin, "time", "abc")
        main_mod.HumanizerPlugin._record_inject(plugin, "time", "de")
        main_mod.HumanizerPlugin._record_inject(plugin, "nope", "zzz")
        self.assertEqual(sink.inject_stats["time"], 5)
        self.assertNotIn("nope", sink.inject_stats)


class TestDashboardObservability(unittest.TestCase):
    """可观测性：控制台仪表盘暴露缓存命中率与每轮注入字符。"""

    def _plugin(self):
        plugin = main_mod.HumanizerPlugin.__new__(main_mod.HumanizerPlugin)
        plugin._prev_seen = {}
        plugin._emotions = {}
        plugin._next_trigger_ts = {}
        plugin._events_ring = deque(maxlen=80)
        plugin._p_int = lambda key, default=None: default
        plugin._time = lambda key, default=None: default
        plugin._retrieve_cache = SimpleNamespace(hits=3, misses=1)
        plugin._inject_stats = {"turns": 2, "time": 100, "rules": 50, "style": 0}
        return plugin

    def test_cache_and_inject(self):
        dash = main_mod.HumanizerPlugin.web_dashboard(self._plugin())
        self.assertEqual(
            dash["cache"],
            {"hits": 3, "misses": 1, "hit_rate": 75.0, "recent": []},
        )
        self.assertEqual(dash["inject"]["total_chars"], 150)
        self.assertEqual(dash["inject"]["avg_chars"], 75.0)

    def test_missing_cache_object_degrades(self):
        plugin = self._plugin()
        del plugin._retrieve_cache
        dash = main_mod.HumanizerPlugin.web_dashboard(plugin)
        self.assertEqual(dash["cache"]["hit_rate"], 0.0)


class TestActiveStyleAutofallback(unittest.TestCase):
    """体验：active_style 空值回退可关闭（清空 = 不注入风格）。"""

    def _plugin(self, enabled):
        plugin = main_mod.HumanizerPlugin.__new__(main_mod.HumanizerPlugin)
        plugin._cfg = lambda key, default=None: {
            "active_style": "",
            "active_style_autofallback": enabled,
        }.get(key, default)
        plugin._find_profile_cached = lambda name: None
        plugin._list_profiles_cached = lambda: [{"name": "x"}]
        plugin._set_cfg = lambda key, value: None
        plugin.config = SimpleNamespace(save_config_async=lambda: None)
        return plugin

    def test_disabled_returns_empty(self):
        plugin = self._plugin(False)
        self.assertEqual(
            main_mod.HumanizerPlugin._effective_active_style(plugin), ""
        )

    def test_enabled_falls_back(self):
        plugin = self._plugin(True)
        self.assertEqual(
            main_mod.HumanizerPlugin._effective_active_style(plugin), "x"
        )


class TestObservabilityContract(unittest.TestCase):
    """可观测性：新增统计键与规则级计数接线在位。"""

    def test_stats_keys_and_qc_rule_counter(self):
        from humanizer_core.observability import STATS_KEYS

        for key in ("qc_rule_hits", "proactive_failed", "proactive_timeout"):
            self.assertIn(key, STATS_KEYS)
        src = (_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("from humanizer_core.observability import EVENT_LABELS, STATS_KEYS", src)
        self.assertIn('self._bump_stats("qc_rule_hits", len(violated))', src)
        self.assertIn('self._bump_stats("proactive_timeout")', src)


class TestSchemaAutofallback(unittest.TestCase):
    """配置：新增 active_style_autofallback 键（v4.8.0 起 132 键）。"""

    def test_schema_key_and_count(self):
        schema = json.loads(
            (_ROOT / "_conf_schema.json").read_text(encoding="utf-8")
        )
        items = schema["style"]["items"]
        self.assertIn("active_style_autofallback", items)
        self.assertTrue(items["active_style_autofallback"]["default"])
        total = sum(len(group.get("items", {})) for group in schema.values())
        self.assertEqual(total, 138, f"配置键总数应为 138，实际 {total}")


if __name__ == "__main__":
    unittest.main()
