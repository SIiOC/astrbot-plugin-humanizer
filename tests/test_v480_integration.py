# -*- coding: utf-8 -*-
"""v4.8.0 整合回归：跨域人格预设 + 读取链优先级 + 前端入口。"""

import json
import unittest
from pathlib import Path

from humanizer_core.presets import (
    EMOTION_MODES,
    PROFILE_EXTRA,
    PROFILE_LABELS,
    PROFILES,
    PROACTIVE_PRESETS,
    TIME_MODES,
    preset_value,
    profile_label,
    profile_mode,
    profile_value,
)

_ROOT = Path(__file__).resolve().parent.parent


class TestProfileComposition(unittest.TestCase):
    """人格 = 三张域档位表的组合，custom 不覆盖。"""

    def test_custom_never_overrides(self):
        for domain in ("time", "emotion", "proactive"):
            for key in ("rhythm_enable", "emotion_cold_war", "proactive_followup_enable"):
                self.assertIsNone(profile_value("custom", domain, key))
        self.assertIsNone(profile_mode("custom", "time"))

    def test_reserved_composes_simple_and_reserved(self):
        self.assertEqual(profile_mode("reserved", "time"), "simple")
        self.assertEqual(profile_mode("reserved", "emotion"), "simple")
        self.assertEqual(profile_mode("reserved", "proactive"), "reserved")
        self.assertFalse(profile_value("reserved", "time", "rhythm_enable"))
        self.assertFalse(profile_value("reserved", "emotion", "emotion_cold_war"))
        self.assertFalse(
            profile_value("reserved", "proactive", "proactive_followup_enable")
        )

    def test_natural_uses_standard_modes(self):
        self.assertEqual(profile_mode("natural", "time"), "standard")
        self.assertFalse(profile_value("natural", "time", "include_first_seen"))
        # standard 主动表为空 → 无覆盖，回落细分开关
        self.assertIsNone(profile_value("natural", "proactive", "proactive_followup_enable"))

    def test_clingy_enables_followup(self):
        self.assertTrue(
            profile_value("clingy", "proactive", "proactive_followup_enable")
        )
        self.assertTrue(
            profile_value("clingy", "proactive", "proactive_pout_on_unanswered")
        )

    def test_work_disables_proactive(self):
        self.assertFalse(profile_value("work", "proactive", "enable_proactive"))
        # 额外覆盖优先于域档位表
        self.assertTrue(
            profile_value("work", "time", "rhythm_enable") is False
        )

    def test_labels_cover_all_profiles(self):
        self.assertEqual(set(PROFILE_LABELS), set(PROFILES))
        self.assertEqual(profile_label("clingy"), "黏人")
        self.assertEqual(profile_label("unknown"), "unknown")


class TestProfileSchemaAndWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(
            (_ROOT / "_conf_schema.json").read_text(encoding="utf-8")
        )
        cls.main_src = (_ROOT / "main.py").read_text(encoding="utf-8")

    def test_persona_group_schema(self):
        persona = self.schema["persona"]["items"]["preset"]
        self.assertEqual(persona["default"], "custom")
        self.assertEqual(
            persona["options"],
            ["custom", "reserved", "natural", "clingy", "work"],
        )

    def test_profile_override_keys_exist_in_schema(self):
        """人格引用的每个键都必须真实存在于对应分组（防拼写漂移）。"""
        tables = {
            "time": TIME_MODES,
            "emotion": EMOTION_MODES,
            "proactive": PROACTIVE_PRESETS,
        }
        for domain, table in tables.items():
            schema_keys = set(self.schema[domain]["items"])
            for mode, overrides in table.items():
                for key in overrides:
                    self.assertIn(
                        key, schema_keys, f"{domain}.{key} 不在 schema（模式 {mode}）"
                    )
        for domain, extra in PROFILE_EXTRA.items():
            for profile, overrides in extra.items():
                for key in overrides:
                    self.assertIn(
                        key,
                        set(self.schema[profile]["items"]),
                        f"{profile}.{key} 不在 schema（人格 {domain}）",
                    )

    def test_main_reads_profile_first(self):
        for token in (
            "def _profile(self)",
            'self._group("persona", "preset", "custom")',
            'profile_value(self._profile(), "proactive", key)',
            'profile_value(self._profile(), "time", key)',
            'profile_value(self._profile(), "emotion", key)',
            '"profile": self._profile(),',
            '"profile_label": PROFILE_LABELS.get',
        ):
            self.assertIn(token, self.main_src)


class TestProfileFrontend(unittest.TestCase):
    def _read(self, rel):
        return (_ROOT / rel).read_text(encoding="utf-8")

    def test_config_page_has_persona_group(self):
        source = self._read("webui/src/views/ConfigView.vue")
        self.assertIn("persona: '表达基调 · 一键预设'", source)
        self.assertIn("natural: '自然'", source)
        self.assertIn("work: '工作'", source)

    def test_overview_shows_profile_chip(self):
        source = self._read("webui/src/views/OverviewView.vue")
        self.assertIn('to="/config?group=persona"', source)
        self.assertIn("status.profile_label", source)


class TestInjectPipeline(unittest.TestCase):
    """v4.8.0：注入顺序从手写代码收敛为声明式注册表。"""

    @classmethod
    def setUpClass(cls):
        from humanizer_core.inject_pipeline import (
            INJECTOR_BY_NAME,
            INJECTOR_NAMES,
            INJECTORS,
            injector_specs,
        )

        cls.INJECTORS = INJECTORS
        cls.by_name = INJECTOR_BY_NAME
        cls.names = INJECTOR_NAMES
        cls.specs = injector_specs()
        cls.main_src = (_ROOT / "main.py").read_text(encoding="utf-8")

    def test_names_unique_and_priority_ordered(self):
        self.assertEqual(len(self.names), len(set(self.names)))
        priorities = [spec.priority for spec in self.INJECTORS]
        self.assertEqual(priorities, sorted(priorities), "优先级必须递增")
        self.assertEqual(
            self.names,
            ("growth", "time", "growth_state", "discipline", "emotion", "rules", "lang", "style", "examples"),
            "注入顺序必须保持既有语义",
        )

    def test_each_spec_has_handler_and_record_key(self):
        for spec in self.INJECTORS:
            self.assertIn(spec.handler, self.main_src, f"{spec.name} handler 不存在")
            self.assertIn(spec.record_key, self.main_src)
            self.assertIn(spec.placement, {"system", "extra_tail", "extra_tail_or_system"})

    def test_examples_depends_on_style(self):
        self.assertEqual(self.by_name["examples"].depends_on, ("style",))

    def test_on_llm_request_uses_registry(self):
        self.assertIn("for spec in INJECTORS:", self.main_src)
        self.assertIn('getattr(self, spec.handler)', self.main_src)
        self.assertIn("self._apply_injection(req, text, spec.placement)", self.main_src)
        # 每个注入器只集中记录一次字符数（不再散落在各 handler 内）
        self.assertIn("self._record_inject(spec.record_key, text)", self.main_src)

    def test_dashboard_exposes_pipeline(self):
        self.assertIn('"pipeline": [', self.main_src)
        self.assertIn('"last_chars": int(', self.main_src)

    def test_specs_are_plain_dicts_for_dashboard(self):
        for item in self.specs:
            self.assertIsInstance(item, dict)
            for key in ("name", "label", "priority", "placement", "depends_on"):
                self.assertIn(key, item)


class TestMetricsSink(unittest.TestCase):
    """v4.8.0：统计/事件/注入/清理统一到 MetricsSink。"""

    @classmethod
    def setUpClass(cls):
        from humanizer_core.metrics import INJECT_KEYS, MetricsSink
        from humanizer_core.observability import EVENT_LABELS, STATS_KEYS

        cls.INJECT_KEYS = INJECT_KEYS
        cls.MetricsSink = MetricsSink
        cls.STATS_KEYS = STATS_KEYS
        cls.EVENT_LABELS = EVENT_LABELS

    def _sink(self):
        return self.MetricsSink(self.STATS_KEYS, self.EVENT_LABELS, self.INJECT_KEYS)

    def test_bump_emits_event_and_rejects_unknown(self):
        sink = self._sink()
        key = self.STATS_KEYS[0]
        self.assertTrue(sink.bump(key, 2))
        self.assertEqual(sink.counters[key], 2)
        self.assertEqual(len(sink.events), 1, "有事件标签的计数应同步入事件环")
        self.assertFalse(sink.bump("nope", 1))
        self.assertFalse(sink.bump(key, 0))

    def test_start_turn_moves_chars_to_recent(self):
        sink = self._sink()
        sink.record_inject("time", "abc")
        sink.start_turn()
        self.assertEqual(sink.inject_stats["turns"], 1)
        self.assertEqual(list(sink.inject_recent), [3])
        self.assertEqual(sink.inject_turn_chars, 0)
        self.assertEqual(sink.inject_stats["time"], 3)

    def test_inject_last_is_per_round(self):
        sink = self._sink()
        sink.inject_last = {"time": 5}
        sink.start_turn()
        self.assertEqual(sink.inject_last, {}, "新一轮应清空上轮注入明细")

    def test_cleanup_masks_pii(self):
        sink = self._sink()
        sink.record_cleanup("联系 13812345678", "联系 138****5678", ["hit"])
        item = sink.cleanup[-1]
        self.assertNotIn("13812345678", item["before"])
        self.assertEqual(len(item["hits"]), 1)

    def test_reset_counters_keeps_rings(self):
        sink = self._sink()
        sink.bump(self.STATS_KEYS[0], 3)
        sink.event("t", "m")
        sink.reset_counters()
        self.assertEqual(set(sink.counters.values()), {0})
        self.assertEqual(len(sink.events), 2, "重置计数不应清空事件流")

    def test_main_uses_sink_and_legacy_aliases(self):
        src = (_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("MetricsSink(STATS_KEYS, EVENT_LABELS, INJECT_KEYS)", src)
        self.assertIn("self._metrics.start_turn()", src)
        self.assertIn("self._metrics.reset_counters()", src)
        self.assertIn("self._stats: dict[str, int] = self._metrics.counters", src)


class TestConfigSimpleView(unittest.TestCase):
    """v4.8.0：配置页简单/专家视图。"""

    @classmethod
    def setUpClass(cls):
        cls.config = (_ROOT / "webui/src/views/ConfigView.vue").read_text(encoding="utf-8")
        cls.verify = (_ROOT / "tools/verify_console.py").read_text(encoding="utf-8")

    def test_simple_keys_cover_every_group(self):
        self.assertIn("const SIMPLE_KEYS: Record<string, string[]>", self.config)
        for token in (
            "persona: ['preset']",
            "time: ['awareness_mode'",
            "emotion: ['emotion_mode'",
            "proactive: ['proactive_preset'",
            "typing: ['enable', 'delay_min'",
        ):
            self.assertIn(token, self.config)

    def test_toggle_and_persistence(self):
        self.assertIn("humanizer-config-simple", self.config)
        self.assertIn("const simpleView = ref(true)", self.config)
        self.assertIn("<template #checked>简单</template>", self.config)
        self.assertIn("<template #unchecked>专家</template>", self.config)

    def test_search_overrides_simple_filter(self):
        body = self.config.split("function visibleItems")[1][:900]
        self.assertLess(body.index("if (q)"), body.index("if (!simpleView.value)"))

    def test_verify_tool_has_config_view_flag(self):
        self.assertIn('"--config-view"', self.verify)
        self.assertIn('humanizer-config-simple', self.verify)
        self.assertIn("config_min_items", self.verify)


class TestTaskNav(unittest.TestCase):
    """v4.8.0：导航按用户任务分组，路由与 API 不变。"""

    @classmethod
    def setUpClass(cls):
        cls.router = (_ROOT / "webui/src/router/index.ts").read_text(encoding="utf-8")
        cls.app = (_ROOT / "webui/src/App.vue").read_text(encoding="utf-8")
        cls.verify = (_ROOT / "tools/verify_console.py").read_text(encoding="utf-8")

    def test_route_groups(self):
        for token in (
            "title: '总览', icon: 'lucide:layout-dashboard', tone: 'pink', group: '像个人'",
            "group: '像个人'",
            "group: '别被识破'",
            "group: '主动找人'",
            "group: '调校排障'",
        ):
            self.assertIn(token, self.router)
        self.assertEqual(self.router.count("group:"), 8, "8 个页面都应归属任务组")
        self.assertIn("path: '/config'", self.router)
        self.assertIn("path: '/stats'", self.router)

    def test_app_renders_grouped_nav(self):
        self.assertIn("const NAV_GROUPS = ['像个人', '别被识破', '主动找人', '调校排障']", self.app)
        self.assertIn("const navGroups = NAV_GROUPS.map", self.app)
        self.assertIn('class="nav-group-label"', self.app)
        self.assertIn("v-for=\"group in navGroups\"", self.app)

    def test_verify_expects_grouped_order(self):
        self.assertIn(
            'expect = ["总览", "语料与风格", "成长档案", "记录回看", "真人感规则", "主动聊天", "配置", "统计"]',
            self.verify,
        )


class TestRealUserUX(unittest.TestCase):
    """v4.8.1 真实体验自检回归：窄屏不撑宽页面 + 人格覆盖提示。"""

    def _read(self, rel):
        return (_ROOT / rel).read_text(encoding="utf-8")

    def test_nav_shrinks_instead_of_page_overflow(self):
        app = self._read("webui/src/App.vue")
        self.assertIn("min-width: 0;", app)
        self.assertIn("flex: 1 1 auto;", app, "导航容器必须允许收缩（否则整页横向溢出）")
        self.assertIn("overflow-x: clip;", app, "装饰元素不得撑出页面滚动条")

    def test_proactive_table_scrolls_on_mobile(self):
        source = self._read("webui/src/views/ProactiveView.vue")
        self.assertIn(':scroll-x="680"', source)

    def test_stats_grid_children_can_shrink(self):
        source = self._read("webui/src/views/StatsView.vue")
        self.assertIn(":deep(.n-grid-item)", source)
        self.assertIn("min-width: 0;", source)

    def test_persona_override_notice_and_chinese_labels(self):
        source = self._read("webui/src/views/ConfigView.vue")
        self.assertIn("persona-note", source)
        self.assertIn("personaPreset !== 'custom'", source)
        self.assertIn("自定义（按细分开关）", source)
        self.assertIn("（简单视图）", source)


class TestV482Optimizations(unittest.TestCase):
    """v4.8.2：人格快捷切换、注入管线可视化、路由懒加载、未解析组件修复。"""

    def _read(self, rel):
        return (_ROOT / rel).read_text(encoding="utf-8")

    def test_overview_imports_button_component(self):
        source = self._read("webui/src/views/OverviewView.vue")
        self.assertIn("NButton,", source, "模板用了 n-button 必须导入 NButton")
        self.assertIn("<n-button", source)

    def test_persona_quick_switch(self):
        source = self._read("webui/src/views/OverviewView.vue")
        self.assertIn("const PERSONAS = [", source)
        self.assertIn("function switchPersona(value: string)", source)
        self.assertIn("apiPost('config/save', { persona: { preset: value } })", source)
        self.assertIn("切换表达基调", source)

    def test_pipeline_visualization(self):
        source = self._read("webui/src/views/OverviewView.vue")
        self.assertIn("本轮注入构成", source)
        self.assertIn("dash.value.inject?.pipeline", source)
        self.assertIn("pipeWidth", source)

    def test_routes_are_lazy_loaded(self):
        source = self._read("webui/src/router/index.ts")
        self.assertIn("() => import('@/views/OverviewView.vue')", source)
        self.assertIn("() => import('@/views/StatsView.vue')", source)
        self.assertNotIn("import OverviewView from", source)

    def test_verify_console_covers_persona_switch(self):
        source = self._read("tools/verify_console.py")
        self.assertIn("apiPost: (path, body)", source)
        self.assertIn("人格快捷切换", source)
        self.assertIn("1b-总览-人格切换.png", source)

    def test_onboarding_is_status_aware(self):
        source = self._read("webui/src/views/OverviewView.vue")
        self.assertIn("const onboardingSteps = computed(", source)
        self.assertIn("apiGet('corpus')", source)
        self.assertIn("已完成 {{ onboardingDone }}", source)
        self.assertIn("onb-progress", source)
        verify = self._read("tools/verify_console.py")
        self.assertIn("首装向导完成度", verify)

    def test_audit_hardening(self):
        """复审修正：接口独立降级、风格启用判定、懒加载提示、人格场景断言。"""
        overview = self._read("webui/src/views/OverviewView.vue")
        self.assertIn("Promise.allSettled([", overview)
        self.assertIn("corpusLoaded", overview)
        self.assertIn("风格已配置但未启用", overview)
        app = self._read("webui/src/App.vue")
        self.assertIn("router.beforeEach(", app)
        self.assertIn("routeLoading", app)
        self.assertNotIn("<suspense>", app, "Suspense 与 transition 组合会触发 DOM 错误")
        verify = self._read("tools/verify_console.py")
        self.assertIn('expected_done = "2 / 3"', verify)


if __name__ == "__main__":
    unittest.main()
