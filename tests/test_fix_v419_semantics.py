# -*- coding: utf-8 -*-
"""v4.1.9 语义一致性修复的回归钉子。

覆盖审计报告中的可自动化项：
- H1 custom 档布尔细分开关回读配置（而不是用调用点默认值）
- H2 create_kb 关闭后 /style_index 仍可手动重建
- M1/M2/M3/M4/M5 配置提示与实现对齐
- M6/M7 控制台状态出口显式降级、主动页补齐闸门字段
- M8 配置保存失败可回滚内存
- L2 主动消息历史只认完整合成句
- L4 主动消息去痕两路径统一且受润色开关/最小长度约束
"""

import asyncio
import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_MAIN = os.path.join(_ROOT, "main.py")
_KB = os.path.join(_ROOT, "services", "kb_service.py")
_WEB = os.path.join(_ROOT, "web_api.py")
_SCHEMA = os.path.join(_ROOT, "_conf_schema.json")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestPresetFlagsReadSavedConfig(unittest.TestCase):
    """H1：custom 档下布尔细分开关必须回读已保存配置。"""

    def setUp(self):
        import main as _main_mod

        self.main = _main_mod
        self.plugin = _main_mod.HumanizerPlugin.__new__(_main_mod.HumanizerPlugin)

    def test_time_flag_reads_saved_false(self):
        saved = {"rhythm_enable": False}
        self.plugin._group = lambda name, key, default=None: saved.get(key, default)
        self.assertFalse(
            self.main.HumanizerPlugin._time_flag(self.plugin, "rhythm_enable", True)
        )

    def test_time_flag_reads_saved_true(self):
        saved = {"include_last_chat": True}
        self.plugin._group = lambda name, key, default=None: saved.get(key, default)
        self.assertTrue(
            self.main.HumanizerPlugin._time_flag(self.plugin, "include_last_chat", False)
        )

    def test_time_preset_override_still_wins(self):
        def group(name, key, default=None):
            return "simple" if key == "awareness_mode" else True

        self.plugin._group = group
        self.assertFalse(
            self.main.HumanizerPlugin._time_flag(self.plugin, "continuity_inject", True)
        )

    def test_emo_flag_reads_saved_true(self):
        saved = {"emotion_cold_war": True}
        self.plugin._group = lambda name, key, default=None: saved.get(key, default)
        self.assertTrue(
            self.main.HumanizerPlugin._emo_flag(self.plugin, "emotion_cold_war", False)
        )

    def test_emo_preset_override_still_wins(self):
        def group(name, key, default=None):
            return "simple" if key == "emotion_mode" else False

        self.plugin._group = group
        self.assertFalse(
            self.main.HumanizerPlugin._emo_flag(
                self.plugin, "emotion_heat_drift_enable", True
            )
        )


class TestKBManualRebuild(unittest.TestCase):
    """H2：create_kb 只约束自动同步，手动 /style_index 必须可用。"""

    def test_service_ensure_accepts_force(self):
        src = _read(_KB)
        self.assertIn("def ensure(", src)
        self.assertIn("force: bool = False", src)
        self.assertIn("if not force and not self._cfg(\"create_kb\", True):", src)

    def test_style_index_passes_force(self):
        src = _read(_MAIN)
        self.assertIn("_ensure_kb(kb_name, name, force=True)", src)
        self.assertIn("force=force", src)


class TestCopyAlignment(unittest.TestCase):
    """M1–M5：配置提示与实现一致（不承诺实现没有的行为）。"""

    def setUp(self):
        with open(_SCHEMA, encoding="utf-8") as f:
            self.schema = json.load(f)

    def _hint(self, group, key):
        return self.schema[group]["items"][key]["hint"]

    def test_create_kb_hint_keeps_manual_path(self):
        hint = self._hint("style", "create_kb")
        self.assertIn("/style_index", hint)
        self.assertIn("手动重建", hint)

    def test_qc_hint_is_record_only(self):
        hint = self._hint("style", "qc_enable")
        self.assertIn("仅记录", hint)
        self.assertNotIn("额外消耗", hint)
        self.assertNotIn("触发一次针对性改写", hint)

    def test_humanize_hint_qc_independent(self):
        hint = self._hint("humanize", "enabled")
        self.assertIn("质检型规则检测", hint)
        self.assertNotIn("不再做规则清理与 QC 检测", hint)

    def test_style_enabled_hint_not_absolute(self):
        self.assertNotIn("完全不注入", self._hint("style", "enabled"))

    def test_active_style_hint_matches_fallback(self):
        hint = self._hint("style", "active_style")
        self.assertIn("第一个可用风格", hint)
        self.assertNotIn("空 = 不注入", hint)

    def test_enable_gap_hint_life_independent(self):
        hint = self._hint("time", "enable_gap")
        self.assertIn("enable_life", hint)
        self.assertNotIn("完全不注入时间上下文", hint)

    def test_event_label_not_claiming_rewrite(self):
        import main as _main_mod

        msg = _main_mod.HumanizerPlugin._EVENT_LABELS["qc_hits"][1]
        self.assertIn("仅记录", msg)
        self.assertNotIn("触发针对性改写", msg)


class TestProactiveViewGates(unittest.TestCase):
    """M7：主动状态页出口补齐白名单/上限/自适应闸门。"""

    def _view(self):
        import main as _main_mod

        plugin = _main_mod.HumanizerPlugin.__new__(_main_mod.HumanizerPlugin)
        config = {
            "enable_proactive": True,
            "proactive_quiet_hours": "",
            "proactive_active_hours": "",
            "proactive_session_allowlist": "aiocqhttp:GroupMessage:1",
            "proactive_silence_scale_enable": False,
        }
        ints = {
            "silence_after_minutes": 45,
            "silence_fluctuation_minutes": 15,
            "proactive_quiet_grace_minutes": 5,
            "proactive_max_unanswered": 6,
            "proactive_silence_scale_cap_minutes": 240,
        }
        plugin._p = lambda key, default=None: config.get(key, default)
        plugin._p_int = lambda key, default: ints.get(key, default)
        plugin._p_f = lambda key, default: 0.3
        plugin._next_trigger_ts = {}
        plugin._proactive_unanswered = {}
        plugin._last_user_ts = {}
        return _main_mod.HumanizerPlugin.web_proactive_view(plugin)

    def test_gate_fields_present(self):
        view = self._view()
        for key in (
            "session_allowlist",
            "max_unanswered",
            "silence_scale_enable",
            "silence_scale_step",
            "silence_scale_cap_minutes",
        ):
            self.assertIn(key, view)

    def test_allowlist_normalized(self):
        self.assertEqual(
            self._view()["session_allowlist"], ["aiocqhttp:GroupMessage:1"]
        )


class TestConfigSaveRollback(unittest.TestCase):
    """M8：保存失败回滚内存配置（通过可单测的纯 helper）。"""

    def setUp(self):
        from web_api import _apply_config_updates, _rollback_config

        self.apply = _apply_config_updates
        self.rollback = _rollback_config

        class _Plugin:
            pass

        self.plugin = _Plugin()
        self.plugin.config = {
            "style": {"enabled": True, "active_style": ""},
            "time": {"enable_gap": True},
        }

    def test_apply_ignores_unknown_keys(self):
        backup = self.apply(self.plugin, {"style": {"bogus": 1}})
        self.assertNotIn("bogus", self.plugin.config["style"])
        self.assertIn("style", backup)

    def test_rollback_restores_values_in_place(self):
        original = self.plugin.config["style"]
        backup = self.apply(
            self.plugin, {"style": {"enabled": False, "active_style": "新风格"}}
        )
        self.assertFalse(self.plugin.config["style"]["enabled"])
        self.rollback(self.plugin, backup)
        self.assertTrue(self.plugin.config["style"]["enabled"])
        self.assertEqual(self.plugin.config["style"]["active_style"], "")
        self.assertIs(self.plugin.config["style"], original, "回滚应保持 dict 引用不变")


class TestProactiveHistoryMarker(unittest.TestCase):
    """L2：只认插件写入的完整合成句。"""

    def test_exact_marker_marked(self):
        from web_api import _parse_conversation_history

        msgs = _parse_conversation_history(
            json.dumps(
                [{"role": "user", "content": "[主动消息] 请自然地延续对话。"}]
            )
        )
        self.assertTrue(msgs[0].get("proactive"))

    def test_plain_prefix_text_not_marked(self):
        from web_api import _parse_conversation_history

        msgs = _parse_conversation_history(
            json.dumps([{"role": "user", "content": "[主动消息] 这是我自己打的字"}])
        )
        self.assertNotIn("proactive", msgs[0])

    def test_assistant_reply_not_marked(self):
        from web_api import _parse_conversation_history

        msgs = _parse_conversation_history(
            json.dumps([{"role": "assistant", "content": "[主动消息] 请自然地延续对话。"}])
        )
        self.assertNotIn("proactive", msgs[0])


class TestStatusDegraded(unittest.TestCase):
    """M6：状态快照内部异常必须显式降级，不能被前端当成「全部关闭」。"""

    def test_web_status_marks_degraded_on_error(self):
        import main as _main_mod

        plugin = _main_mod.HumanizerPlugin.__new__(_main_mod.HumanizerPlugin)

        def boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        plugin._h = boom
        plugin._p = boom
        plugin._cfg = boom
        plugin._life = boom
        plugin._time = boom
        plugin._emo = boom
        result = _main_mod.HumanizerPlugin.web_status(plugin)
        self.assertTrue(result.get("degraded"))
        self.assertIn("error", result)
        self.assertEqual(result.get("styles"), [])


class TestProactiveHumanizeGating(unittest.TestCase):
    """L4：主动消息去痕受 humanize.enabled / min_length 约束。"""

    def setUp(self):
        import main as _main_mod

        self.main = _main_mod
        self.plugin = _main_mod.HumanizerPlugin.__new__(_main_mod.HumanizerPlugin)

    def _stub(self, enabled, min_length=8, remove_emoji=True):
        values = {
            "enabled": enabled,
            "min_length": min_length,
            "remove_emoji": remove_emoji,
        }
        self.plugin._h = lambda key, default=None: values.get(key, default)

    def test_disabled_returns_text_unchanged(self):
        self._stub(enabled=False)
        text = "嗯嗯，好的呀～😊"
        self.assertEqual(
            self.main.HumanizerPlugin._humanize_proactive_text(self.plugin, text), text
        )

    def test_short_text_skipped(self):
        self._stub(enabled=True, min_length=20)
        text = "好呀😊"
        self.assertEqual(
            self.main.HumanizerPlugin._humanize_proactive_text(self.plugin, text), text
        )

    def test_enabled_and_long_text_cleaned(self):
        self._stub(enabled=True, min_length=4, remove_emoji=True)
        text = "嗯嗯，好的呀😊"
        cleaned = self.main.HumanizerPlugin._humanize_proactive_text(self.plugin, text)
        self.assertNotIn("😊", cleaned)


if __name__ == "__main__":
    unittest.main()
