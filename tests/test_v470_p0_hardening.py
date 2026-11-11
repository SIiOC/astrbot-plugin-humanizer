# -*- coding: utf-8 -*-
"""v4.7.0 P0 加固回归：服务端配置校验、导入闭环、降级禁存。"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from humanizer_core.privacy import mask_pii
from web_api import (
    ROUTE_SPECS,
    _load_config_schema,
    _validate_config_updates,
    _validate_config_value,
)

_ROOT = Path(__file__).resolve().parent.parent


def _fake_plugin() -> SimpleNamespace:
    return SimpleNamespace(
        config={
            "style": {
                "enabled": True,
                "active_style": "",
                "retrieve_top_k": 3,
                "retrieval_timeout": 5.0,
            },
            "time": {"gap_granularity": "mixed"},
            "typing": {"command_prefixes": ["/humanize"]},
        }
    )


class TestSchemaValueValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = _load_config_schema()

    def _item(self, group: str, key: str) -> dict:
        return self.schema[group]["items"][key]

    def test_bool_rejects_non_bool(self):
        item = self._item("style", "enabled")
        self.assertIsNone(_validate_config_value(item, True))
        self.assertIsNotNone(_validate_config_value(item, "true"))
        self.assertIsNotNone(_validate_config_value(item, 1))

    def test_int_rejects_bool_and_float(self):
        item = self._item("style", "retrieve_top_k")
        self.assertIsNone(_validate_config_value(item, 3))
        self.assertIsNotNone(_validate_config_value(item, True))
        self.assertIsNotNone(_validate_config_value(item, 3.5))
        self.assertIsNotNone(_validate_config_value(item, "3"))

    def test_float_accepts_int(self):
        item = self._item("style", "retrieval_timeout")
        self.assertIsNone(_validate_config_value(item, 5))
        self.assertIsNone(_validate_config_value(item, 5.5))
        self.assertIsNotNone(_validate_config_value(item, "5"))

    def test_enum_rejects_unknown_option(self):
        item = self._item("time", "gap_granularity")
        self.assertIsNone(_validate_config_value(item, "mixed"))
        reason = _validate_config_value(item, "bogus")
        self.assertIn("可选范围", reason or "")

    def test_list_requires_string_items(self):
        item = self._item("typing", "command_prefixes")
        self.assertIsNone(_validate_config_value(item, ["/a", "/b"]))
        self.assertIsNotNone(_validate_config_value(item, ["/a", 1]))
        self.assertIsNotNone(_validate_config_value(item, "/a"))

    def test_none_rejected(self):
        self.assertIsNotNone(_validate_config_value({}, None))

    def test_every_schema_type_is_supported(self):
        supported = {"bool", "int", "float", "string", "file", "list", "text"}
        for group, meta in self.schema.items():
            for key, item in (meta.get("items") or {}).items():
                with self.subTest(group=group, key=key):
                    self.assertIn(str(item.get("type", "")).lower(), supported)


class TestUpdateValidation(unittest.TestCase):
    def test_valid_changes_accepted(self):
        plugin = _fake_plugin()
        accepted, errors, ignored = _validate_config_updates(
            plugin, {"style": {"enabled": False, "retrieve_top_k": 5}}
        )
        self.assertEqual(
            accepted, {"style": {"enabled": False, "retrieve_top_k": 5}}
        )
        self.assertEqual(errors, {})
        self.assertEqual(ignored, [])

    def test_wrong_type_reported_per_key(self):
        plugin = _fake_plugin()
        accepted, errors, _ = _validate_config_updates(
            plugin, {"style": {"enabled": "yes", "retrieve_top_k": 5}}
        )
        self.assertIn("style.enabled", errors)
        self.assertEqual(accepted, {"style": {"retrieve_top_k": 5}})

    def test_unchanged_invalid_legacy_value_skipped(self):
        plugin = _fake_plugin()
        plugin.config["style"]["enabled"] = "legacy"  # 历史脏值，但本次未改动
        accepted, errors, _ = _validate_config_updates(
            plugin, {"style": {"enabled": "legacy"}}
        )
        self.assertEqual(errors, {})
        self.assertEqual(accepted, {})

    def test_unknown_key_ignored(self):
        plugin = _fake_plugin()
        accepted, errors, ignored = _validate_config_updates(
            plugin, {"style": {"not_a_key": 1}}
        )
        self.assertEqual(accepted, {})
        self.assertEqual(errors, {})
        self.assertIn("style.not_a_key", ignored)

    def test_enum_invalid_in_updates(self):
        plugin = _fake_plugin()
        _, errors, _ = _validate_config_updates(
            plugin, {"time": {"gap_granularity": "bogus"}}
        )
        self.assertIn("time.gap_granularity", errors)


class TestPrivacyMask(unittest.TestCase):
    def test_masks_phone(self):
        masked = mask_pii("我的手机是13812345678，打我电话")
        self.assertNotIn("13812345678", masked)
        self.assertIn("138****5678", masked)

    def test_masks_email(self):
        masked = mask_pii("联系 test.user@example.com 谢谢")
        self.assertNotIn("test.user@example.com", masked)
        self.assertIn("[邮箱]", masked)

    def test_masks_long_digits_but_keeps_short(self):
        masked = mask_pii("QQ 123456789，验证码 888888，年份 2026")
        self.assertNotIn("123456789", masked)
        self.assertNotIn("888888", masked)
        self.assertIn("2026", masked)


class TestP1Features(unittest.TestCase):
    def _read(self, rel: str) -> str:
        return (_ROOT / rel).read_text(encoding="utf-8")

    def test_stats_reset_route_registered(self):
        routes = {spec[0]: spec[1] for spec in ROUTE_SPECS}
        self.assertEqual(routes.get("stats/reset"), "reset_stats")

    def test_stats_view_four_columns_and_reset(self):
        source = self._read("webui/src/views/StatsView.vue")
        self.assertIn(':cols="4"', source)
        self.assertIn('stats/reset', source)
        self.assertIn("重置计数", source)

    def test_config_search_tab_counts(self):
        source = self._read("webui/src/views/ConfigView.vue")
        self.assertIn("tabLabel(gname", source)

    def test_overview_invalid_style_chip(self):
        source = self._read("webui/src/views/OverviewView.vue")
        self.assertIn("active_style_invalid", source)
        self.assertIn("chip-warn", source)

    def test_status_exposes_style_state(self):
        source = self._read("main.py")
        self.assertIn('"active_style_configured"', source)
        self.assertIn('"active_style_invalid"', source)

    def test_record_cleanup_masks_pii(self):
        """v4.8.0：清理明细写入统一 MetricsSink，掩码逻辑随 sink 迁移。"""
        metrics = self._read("humanizer_core/metrics.py")
        self.assertIn("mask_pii(str(text))", metrics)
        self.assertIn("mask_pii(str(cleaned))", metrics)
        source = self._read("main.py")
        self.assertIn("self._metrics.record_cleanup(text, cleaned, hits)", source)

    def test_trend_series_exposed(self):
        source = self._read("main.py")
        self.assertIn('"recent": list(getattr(self, "_inject_recent", []))', source)
        self.assertIn('"recent": cache_recent', source)
        self.assertIn('getattr(self._retrieve_cache, "history", [])', source)

    def test_frontend_trend_component(self):
        source = self._read("webui/src/views/OverviewView.vue")
        self.assertIn("SparkBars", source)
        self.assertIn("injectRecent", source)
        self.assertTrue((_ROOT / "webui" / "src" / "components" / "SparkBars.vue").exists())


class TestMarketVersionTool(unittest.TestCase):
    def _module(self):
        import importlib.util

        path = _ROOT / "tools" / "check_market_version.py"
        spec = importlib.util.spec_from_file_location("check_market_version", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_version_tuple_order(self):
        module = self._module()
        self.assertGreater(
            module.version_tuple("4.7.0"), module.version_tuple("4.6.9")
        )
        self.assertEqual(module.version_tuple("4.7.0"), (4, 7, 0))

    def test_extract_entry_matches_repo_and_name(self):
        module = self._module()
        data = {
            "x/other": {"name": "other", "repo": "https://github.com/x/other"},
            "SIiOC/astrbot-plugin-humanizer": {
                "name": "astrbot_plugin_wanna_be_human",
                "repo": "https://github.com/SIiOC/astrbot-plugin-humanizer",
                "version": "4.6.0",
            },
        }
        entry = module.extract_entry(
            data, "SIiOC/astrbot-plugin-humanizer", "astrbot_plugin_wanna_be_human"
        )
        self.assertEqual(entry["version"], "4.6.0")


class TestObservabilityModule(unittest.TestCase):
    def test_stats_keys_extracted_from_main(self):
        from humanizer_core.observability import EVENT_LABELS, STATS_KEYS

        self.assertEqual(len(STATS_KEYS), 12)
        self.assertEqual(set(EVENT_LABELS), set(STATS_KEYS))
        source = (_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("from humanizer_core.observability import EVENT_LABELS, STATS_KEYS", source)
        self.assertIn("MetricsSink(STATS_KEYS, EVENT_LABELS, INJECT_KEYS)", source)

    def test_ci_workflow_exists(self):
        workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("vite build", workflow)
        self.assertIn("test_v470_p0_hardening.py", workflow)


class TestFrontendHardening(unittest.TestCase):
    def _read(self, rel: str) -> str:
        return (_ROOT / rel).read_text(encoding="utf-8")

    def test_backend_validation_wired_into_save(self):
        source = self._read("web_api.py")
        self.assertIn("_validate_config_updates(self.plugin, updates)", source)
        self.assertIn("status_code=400", source)

    def test_import_handles_complex_keys(self):
        source = self._read("webui/src/views/ConfigView.vue")
        for token in ("validateComplexValue", "复杂项", "未知键", "未知分组"):
            self.assertIn(token, source)

    def test_save_disabled_when_degraded(self):
        source = self._read("webui/src/views/ConfigView.vue")
        self.assertIn("!dirty || !!loadError", source)
        self.assertIn("res?.errors", source)


if __name__ == "__main__":
    unittest.main()
