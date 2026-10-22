# -*- coding: utf-8 -*-
"""防泄漏守卫：插件目录内不得出现框架按 cwd 生成的 data/cmd_config.json。

AstrBot 的 ``get_astrbot_root()`` 在未设置 ``ASTRBOT_ROOT`` 时取当前工作目录，
从插件根目录跑测试/导入框架会把 ``data/cmd_config.json``（含 dashboard 口令
哈希）落到插件目录。``tests/conftest.py`` 已自动设置 ASTRBOT_ROOT 阻止该行为；
本测试保证插件目录保持干净，并给出清理指引。
"""

import os
import unittest


class TestNoPluginLocalData(unittest.TestCase):
    def test_no_cmd_config_copy_in_plugin_dir(self):
        plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        leaked = os.path.join(plugin_dir, "data", "cmd_config.json")
        self.assertFalse(
            os.path.exists(leaked),
            "插件目录内出现 data/cmd_config.json（框架按 cwd 生成的配置副本，"
            "含 dashboard 口令哈希）。请把 data/ 目录移出插件目录，或在运行测试/"
            "导入框架前设置 ASTRBOT_ROOT=<AstrBot 根目录>。",
        )

    def test_gitignore_and_package_exclude_data(self):
        plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        gitignore = open(os.path.join(plugin_dir, ".gitignore"), encoding="utf-8").read()
        self.assertIn("data/", gitignore)
        packaging = open(os.path.join(plugin_dir, "package_plugin.py"), encoding="utf-8").read()
        self.assertIn('"data"', packaging)


if __name__ == "__main__":
    unittest.main()
