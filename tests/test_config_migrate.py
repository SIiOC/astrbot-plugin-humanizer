# -*- coding: utf-8 -*-
"""
配置结构迁移测试：扁平结构 → humanize/proactive 两个分组。
"""

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.config_migrate import (
    migrate_flat_to_groups,
    migrate_proactive_key_names,
)


class TestMigrateFlatToGroups(unittest.TestCase):
    def test_flat_config_migrated_preserving_values(self):
        """旧扁平配置迁移为分组，用户设置全部保留。"""
        flat = {
            "enabled": True,
            "enable_llm_rewrite": True,
            "rewrite_model": "xiaomi-token-plan/mimo-v2.5-pro",
            "remove_emoji": False,
            "remove_reasoning": True,
            "min_length": 5,
            "max_chars": 200,
            "debug": False,
            "enable_proactive": True,
            "idle_after_minutes": 30,
            "proactive_quiet_hours": "22:00-07:00",
            "proactive_prompt": "自定义模板",
        }
        changed = migrate_flat_to_groups(flat)
        self.assertTrue(changed)
        # 旧扁平键已移除
        for k in (
            "enabled",
            "rewrite_model",
            "enable_proactive",
            "idle_after_minutes",
        ):
            self.assertNotIn(k, flat)
        # 分组存在且值保留
        self.assertEqual(flat["humanize"]["rewrite_model"], "xiaomi-token-plan/mimo-v2.5-pro")
        self.assertEqual(flat["humanize"]["min_length"], 5)
        self.assertEqual(flat["humanize"]["remove_reasoning"], True)
        self.assertEqual(flat["proactive"]["enable_proactive"], True)
        self.assertEqual(flat["proactive"]["idle_after_minutes"], 30)
        self.assertEqual(flat["proactive"]["proactive_quiet_hours"], "22:00-07:00")
        self.assertEqual(flat["proactive"]["proactive_prompt"], "自定义模板")

    def test_already_grouped_no_change(self):
        """已是分组结构：不迁移，返回 False。"""
        grouped = {
            "humanize": {"enabled": True, "rewrite_model": ""},
            "proactive": {"enable_proactive": False},
        }
        changed = migrate_flat_to_groups(grouped)
        self.assertFalse(changed)
        self.assertEqual(grouped["humanize"]["enabled"], True)

    def test_empty_config_no_change(self):
        self.assertFalse(migrate_flat_to_groups({}))

    def test_partial_flat_migrates(self):
        """部分旧键存在也迁移，缺失的键不报错。"""
        partial = {"enabled": False, "humanize": {"debug": True}}
        changed = migrate_flat_to_groups(partial)
        self.assertTrue(changed)
        self.assertNotIn("enabled", partial)
        self.assertEqual(partial["humanize"]["enabled"], False)
        self.assertEqual(partial["humanize"]["debug"], True)
        self.assertIn("proactive", partial)

    def test_idempotent(self):
        """迁移后再次迁移无变化。"""
        cfg = {"rewrite_model": "gpt-4o", "enable_proactive": True}
        self.assertTrue(migrate_flat_to_groups(cfg))
        self.assertFalse(migrate_flat_to_groups(cfg))


class TestMigrateProactiveKeyNames(unittest.TestCase):
    """v2.0.0 主动聊天键名迁移（idle_* → silence_*）。"""

    def test_group_old_keys_renamed_preserving_values(self):
        """分组内旧键搬迁到新键，值保留，旧键删除。"""
        cfg = {
            "proactive": {
                "enable_proactive": True,
                "idle_after_minutes": 30,
                "idle_fluctuation_minutes": 10,
            }
        }
        self.assertTrue(migrate_proactive_key_names(cfg))
        proactive = cfg["proactive"]
        self.assertEqual(proactive["silence_after_minutes"], 30)
        self.assertEqual(proactive["silence_fluctuation_minutes"], 10)
        self.assertNotIn("idle_after_minutes", proactive)
        self.assertNotIn("idle_fluctuation_minutes", proactive)
        self.assertEqual(proactive["enable_proactive"], True)

    def test_top_level_old_keys_renamed(self):
        """顶层旧键也迁移（扁平形态兜底）。"""
        cfg = {"idle_after_minutes": 45}
        self.assertTrue(migrate_proactive_key_names(cfg))
        self.assertEqual(cfg["silence_after_minutes"], 45)
        self.assertNotIn("idle_after_minutes", cfg)

    def test_new_keys_present_no_change(self):
        """已是新键名：不迁移，返回 False。"""
        cfg = {"proactive": {"silence_after_minutes": 45}}
        self.assertFalse(migrate_proactive_key_names(cfg))

    def test_empty_no_change(self):
        self.assertFalse(migrate_proactive_key_names({}))
        self.assertFalse(migrate_proactive_key_names({"humanize": {"debug": True}}))

    def test_new_key_wins_over_old(self):
        """新键已有值时不动旧键（不覆盖用户新设置）。"""
        cfg = {
            "proactive": {
                "silence_after_minutes": 60,
                "idle_after_minutes": 30,
            }
        }
        self.assertFalse(migrate_proactive_key_names(cfg))
        self.assertEqual(cfg["proactive"]["silence_after_minutes"], 60)
        self.assertIn("idle_after_minutes", cfg["proactive"])

    def test_flat_then_rename_full_path(self):
        """完整链路：扁平旧配置 → 分组 → 键名迁移，值不丢。"""
        flat = {
            "enable_proactive": True,
            "idle_after_minutes": 30,
            "idle_fluctuation_minutes": 10,
            "proactive_quiet_hours": "22:00-07:00",
        }
        self.assertTrue(migrate_flat_to_groups(flat))
        self.assertTrue(migrate_proactive_key_names(flat))
        proactive = flat["proactive"]
        self.assertEqual(proactive["enable_proactive"], True)
        self.assertEqual(proactive["silence_after_minutes"], 30)
        self.assertEqual(proactive["silence_fluctuation_minutes"], 10)
        self.assertEqual(proactive["proactive_quiet_hours"], "22:00-07:00")
        self.assertNotIn("idle_after_minutes", flat)
        self.assertNotIn("idle_after_minutes", proactive)


class TestDebounceConfigWiring(unittest.TestCase):
    """v3.9.5 回归：防抖数值键已并入 typing，读取不能回到旧 debounce 组。"""

    def test_d_num_reads_typing_group_and_key_map(self):
        import ast

        main_path = _ROOT / "main.py"
        tree = ast.parse(main_path.read_text(encoding="utf-8"))
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_d_num"
        )
        src = ast.dump(fn)
        self.assertIn("typing", src)
        self.assertIn("_DEBOUNCE_KEY_MAP", src)
        self.assertNotIn('Constant(value="debounce")', src)

    def test_debounce_numeric_keys_are_not_old_group(self):
        import json

        schema = json.loads((_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        typing = schema["typing"]["items"]
        for key in (
            "debounce_time",
            "adaptive_min_wait",
            "adaptive_max_wait",
            "adaptive_max_total_wait",
            "adaptive_short_message_threshold",
            "max_session_wait",
            "max_typing_wait",
        ):
            self.assertIn(key, typing)


if __name__ == "__main__":
    unittest.main()
