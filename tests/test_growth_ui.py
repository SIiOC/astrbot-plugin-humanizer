# -*- coding: utf-8 -*-
"""Static contract checks for the v4.9 growth UI/config skeleton."""

import json
import re
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent


class TestGrowthSchemaAndConfigUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        cls.config = (_ROOT / "webui/src/views/ConfigView.vue").read_text(encoding="utf-8")

    def test_growth_schema_has_exact_six_settings_and_bounds(self):
        growth = self.schema["growth"]
        self.assertEqual(growth["description"], "成长档案")
        items = growth["items"]
        self.assertEqual(
            set(items),
            {"enabled", "identity_budget", "situation_budget", "tick_minutes", "max_events", "debug"},
        )
        self.assertEqual(items["enabled"]["default"], False)
        self.assertEqual(items["identity_budget"]["default"], 600)
        self.assertEqual((items["identity_budget"]["min"], items["identity_budget"]["max"]), (100, 900))
        self.assertEqual(items["situation_budget"]["default"], 260)
        self.assertEqual((items["situation_budget"]["min"], items["situation_budget"]["max"]), (80, 400))
        self.assertEqual(items["tick_minutes"]["default"], 5)
        self.assertEqual((items["tick_minutes"]["min"], items["tick_minutes"]["max"]), (1, 60))
        self.assertEqual(items["max_events"]["default"], 20000)
        self.assertEqual((items["max_events"]["min"], items["max_events"]["max"]), (100, 150000))
        self.assertEqual(items["debug"]["default"], False)
        self.assertIn("私聊", growth["hint"])
        self.assertIn("不保存消息正文", growth["hint"])
        self.assertIn("不会按天数自动晋级", growth["hint"])
        self.assertIn("宿主角色", growth["hint"])
        self.assertNotIn("表达基调", growth["hint"])
        self.assertIn("只读", growth["hint"])

    def test_config_ui_groups_and_simple_view(self):
        self.assertIn("growth: '成长档案 · 私聊元数据'", self.config)
        self.assertIn("persona: '表达基调 · 一键预设'", self.config)
        self.assertIn("growth: ['enabled']", self.config)
        self.assertIn(':min="meta.min"', self.config)
        self.assertIn(':max="meta.max"', self.config)
        self.assertIn("integer: kmeta.type === 'int'", self.config)
        self.assertIn("meta.integer && !Number.isInteger(value)", self.config)
        self.assertIn("min: typeof kmeta.min === 'number'", self.config)
        self.assertIn("max: typeof kmeta.max === 'number'", self.config)
        self.assertIn("不能小于 ${meta.min}", self.config)
        self.assertIn("不能大于 ${meta.max}", self.config)


class TestGrowthPageStaticContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = (_ROOT / "webui/src/views/GrowthView.vue").read_text(encoding="utf-8")
        cls.router = (_ROOT / "webui/src/router/index.ts").read_text(encoding="utf-8")

    def test_lazy_growth_route_is_page_eight(self):
        self.assertIn("const GrowthView = () => import('@/views/GrowthView.vue')", self.router)
        self.assertIn("path: '/growth'", self.router)
        self.assertIn("group: '像个人'", self.router)
        paths = re.findall(r"path:\s*'([^']+)'", self.router)
        self.assertEqual(len(paths), 8)
        self.assertEqual(paths[-1], "/growth")

    def test_read_only_scope_selection_and_stale_request_guard(self):
        self.assertIn("只读视图", self.view)
        self.assertIn("不自动选择会话", self.view)
        self.assertIn("apiGet('growth/state')", self.view)
        self.assertIn("apiGet('growth/state', { scope: scopeId })", self.view)
        self.assertIn("apiGet('growth/events', { scope: scopeId, limit: 50 })", self.view)
        self.assertIn("token === scopeRequest && scopeId === currentScope.value", self.view)
        self.assertIn("Promise.allSettled", self.view)
        self.assertNotRegex(self.view, r"setInterval|setTimeout\s*\(")
        self.assertNotRegex(self.view, r"apiPost|reset|promote|experience")

    def test_private_hash_and_metadata_only_rendering(self):
        self.assertIn("value.slice(0, 8)", self.view)
        self.assertIn("shortScope(item.id)", self.view)
        self.assertIn("text_length", self.view)
        self.assertIn("row.type || row.kind", self.view)
        self.assertIn("value * 1000", self.view)
        self.assertNotIn("return String(value)", self.view)
        self.assertNotRegex(self.view, r"(?:row|event)\.(?:text|content|message)\b")

    def test_events_accept_backend_type_field(self):
        self.assertIn("type?: string", self.view)
        self.assertIn("kind?: string", self.view)
        self.assertIn("eventKindLabel[row.type || row.kind || '']", self.view)

    def test_diary_is_readonly_metadata_projection(self):
        self.assertIn("apiGet('growth/diary'", self.view)
        self.assertIn("成长日记（事实版）", self.view)
        self.assertIn("active_hours", self.view)
        self.assertIn("diaryRows", self.view)
        self.assertIn("tz_offset_minutes: -new Date().getTimezoneOffset()", self.view)
        self.assertIn("不含聊天内容", self.view)
        # 日记也是只读投影：视图仍不得出现写接口或语义晋升入口。
        self.assertNotRegex(self.view, r"apiPost|reset|promote")

    def test_stage_is_fixed_observation_without_fake_progression(self):
        self.assertIn("<strong>观察积累</strong>", self.view)
        self.assertIn("阶段晋升语义尚未启用", self.view)
        self.assertNotIn("state.stage_name || '观察积累'", self.view)
        self.assertNotIn("item.stage_name || '观察积累'", self.view)

    def test_degraded_disabled_and_cap_states_are_distinguished(self):
        self.assertIn("!enabled && !loadError", self.view)
        self.assertIn("v-if=\"degraded\"", self.view)
        self.assertIn("v-if=\"loadError\"", self.view)
        self.assertIn("state.cap_reached", self.view)
        self.assertIn("暂无可选会话", self.view)
        self.assertIn("该会话暂无元数据事件", self.view)

    def test_p2_truncation_and_unavailable_states_have_copy(self):
        self.assertIn("summaryState.scopes_truncated", self.view)
        self.assertIn("会话数量超过单次读取上限", self.view)
        self.assertIn("summaryState.available === false", self.view)
        self.assertIn("成长档案后端不可用", self.view)
        self.assertIn("pendingTotal", self.view)
        self.assertIn("rejectedTotal", self.view)
        self.assertIn("待写", self.view)
        self.assertIn("已拒收", self.view)
        self.assertIn("stuckTotal", self.view)
        self.assertIn("无法写入", self.view)
        self.assertIn("Number(state.days_known ?? 0).toFixed(1)", self.view)
        # A busy store with no queued items must not claim "0 条等待落盘".
        self.assertNotIn("pending_writes || summaryState.pending_writes", self.view)


if __name__ == "__main__":
    unittest.main()
