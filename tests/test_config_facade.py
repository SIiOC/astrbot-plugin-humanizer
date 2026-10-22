# -*- coding: utf-8 -*-
"""配置门面行为测试。"""

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.config_facade import TypedConfig


class TestTypedConfig(unittest.TestCase):
    """覆盖分组访问、兼容别名、数值转换和底层可变性。"""

    def test_grouped_read_write(self):
        """正式分组支持读取、写入和直接返回底层分组。"""
        config = {"style": {"enabled": True}, "humanize": {"max_chars": 240}}
        facade = TypedConfig(config)

        self.assertTrue(facade.get("style", "enabled"))
        self.assertEqual(facade.humanize("max_chars"), 240)
        self.assertIs(facade.group("style"), config["style"])

        facade.set("style", "active_style", "聊天风格")
        self.assertEqual(config["style"]["active_style"], "聊天风格")

    def test_compatibility_aliases_read_and_write(self):
        """旧分组和键名别名读取、写入到当前正式位置。"""
        config = {
            "style": {"enabled": True},
            "time": {"life_extract_model": "life-model"},
            "typing": {
                "debounce_enable": False,
                "send_discipline_enabled": True,
                "send_discipline_debug": False,
            },
        }
        facade = TypedConfig(config)

        self.assertTrue(facade.get("config", "enabled"))
        self.assertEqual(facade.get("life", "extract_model"), "life-model")
        self.assertFalse(facade.debounce("enable"))
        self.assertTrue(facade.send_discipline("enabled"))
        self.assertFalse(facade.send_discipline("debug"))

        facade.set("life", "extract_model", "new-life-model")
        facade.set("debounce", "enable", True)
        facade.set("send_discipline", "debug", True)
        self.assertEqual(config["time"]["life_extract_model"], "new-life-model")
        self.assertTrue(config["typing"]["debounce_enable"])
        self.assertTrue(config["typing"]["send_discipline_debug"])

    def test_numeric_fallback_and_legal_zero(self):
        """数值缺失、空值和非法值回落，但合法零值保持不变。"""
        config = {
            "typing": {
                "delay_min": 0,
                "delay_max": "0",
                "total_delay_cap": None,
                "split_threshold": "not-a-number",
            }
        }
        facade = TypedConfig(config)

        self.assertEqual(facade.get_int("typing", "delay_min", 7), 0)
        self.assertEqual(facade.get_float("typing", "delay_max", 7.5), 0.0)
        self.assertEqual(facade.get_float("typing", "total_delay_cap", 7.5), 7.5)
        self.assertEqual(facade.get_int("typing", "split_threshold", 7), 7)
        self.assertEqual(facade.get_int("missing", "value", 7), 7)

    def test_mapping_mutation_and_no_implicit_group_creation(self):
        """读取不创建分组，显式写入和原地修改都作用于底层 mapping。"""
        config = {}
        facade = TypedConfig(config)

        self.assertIsNone(facade.group("life"))
        self.assertEqual(facade.get("life", "extract_model", "fallback"), "fallback")
        self.assertNotIn("time", config)

        facade.set("life", "extract_model", "timeline-model")
        self.assertEqual(config, {"time": {"life_extract_model": "timeline-model"}})
        facade.group("life")["life_extract_model"] = "changed-in-place"
        self.assertEqual(facade.get("time", "life_extract_model"), "changed-in-place")


if __name__ == "__main__":
    unittest.main()
