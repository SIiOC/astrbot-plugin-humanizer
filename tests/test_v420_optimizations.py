# -*- coding: utf-8 -*-
"""v4.2.0 优化项回归：运行版本显示 + 发布前扫描器。"""

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

import pre_release_scan as prs  # noqa: E402

_SCHEMA = _ROOT / "metadata.yaml"


def _metadata_version() -> str:
    for line in _SCHEMA.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""


class TestRunVersionWiring(unittest.TestCase):
    """控制台「运行版本」：metadata 读取 + web_status 出口。"""

    def test_read_plugin_version_matches_metadata(self):
        import main as main_mod

        self.assertEqual(main_mod._read_plugin_version(), _metadata_version())

    def test_web_status_exposes_version_and_started_at(self):
        import main as main_mod

        plugin = main_mod.HumanizerPlugin.__new__(main_mod.HumanizerPlugin)
        plugin._h = lambda key, default=None: default
        plugin._p = lambda key, default=None: default
        plugin._cfg = lambda key, default=None: default
        plugin._life = lambda key, default=None: default
        plugin._time = lambda key, default=None: default
        plugin._emo = lambda key, default=None: default
        plugin._effective_active_style = lambda: ""
        plugin._plugin_version = "4.2.0-test"
        plugin._started_ts = 1700000000.0
        status = main_mod.HumanizerPlugin.web_status(plugin)
        self.assertEqual(status["version"], "4.2.0-test")
        self.assertEqual(status["started_at"], 1700000000)

    def test_web_status_fallback_keeps_version(self):
        import main as main_mod

        plugin = main_mod.HumanizerPlugin.__new__(main_mod.HumanizerPlugin)

        def boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        plugin._h = boom
        plugin._p = boom
        plugin._cfg = boom
        plugin._life = boom
        plugin._time = boom
        plugin._emo = boom
        plugin._plugin_version = "4.2.0-test"
        plugin._started_ts = 1700000000.0
        status = main_mod.HumanizerPlugin.web_status(plugin)
        self.assertTrue(status.get("degraded"))
        self.assertEqual(status.get("version"), "4.2.0-test")


class TestPreReleaseScanText(unittest.TestCase):
    def test_absolute_path_flagged(self):
        drive = "E"
        text = "log at " + drive + ":\\ai\\data\\x.log"
        findings = prs.scan_text("demo.py", text)
        self.assertTrue(any(f["kind"] == "absolute_path" for f in findings))

    def test_clean_text_passes(self):
        text = "相对路径 ../dist 与 http://example.com 都不算本机路径。"
        self.assertEqual(prs.scan_text("demo.md", text), [])

    def test_secret_masked(self):
        token = "ghp_" + "A" * 36
        findings = prs.scan_text("demo.py", "token=" + token)
        self.assertTrue(any(f["kind"] == "github_token" for f in findings))
        for finding in findings:
            self.assertNotIn(token, finding["excerpt"], "凭据不得原样回显")


class TestPreReleaseScanZip(unittest.TestCase):
    def _make_zip(self, names):
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        with zipfile.ZipFile(tmp.name, "w") as zf:
            for name, content in names.items():
                zf.writestr(name, content)
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        return Path(tmp.name)

    def test_clean_zip_passes(self):
        zip_path = self._make_zip(
            {"astrbot_plugin_wanna_be_human/main.py": "print('ok')\n"}
        )
        self.assertEqual(prs.scan_zip(zip_path), [])

    def test_forbidden_entries_flagged(self):
        zip_path = self._make_zip(
            {
                "astrbot_plugin_wanna_be_human/main.py": "print('ok')\n",
                "astrbot_plugin_wanna_be_human/tests/test_x.py": "x = 1\n",
                "astrbot_plugin_wanna_be_human/data/cmd_config.json": "{}",
            }
        )
        kinds = {f["kind"] for f in prs.scan_zip(zip_path)}
        self.assertIn("forbidden_dir", kinds)

    def test_top_dir_mismatch_flagged(self):
        zip_path = self._make_zip({"wrong_dir/main.py": "print('ok')\n"})
        kinds = {f["kind"] for f in prs.scan_zip(zip_path)}
        self.assertIn("top_dir_mismatch", kinds)


class TestReleaseFilesClean(unittest.TestCase):
    """发布门禁：当前打包清单必须 0 可疑内容（dogfood）。"""

    def test_packaging_list_is_clean(self):
        findings = prs.scan_release_files(_ROOT)
        summary = "\n".join(
            f"{f['kind']}: {f['path']}:{f.get('line')} {f['excerpt']}"
            for f in findings[:20]
        )
        self.assertEqual(findings, [], f"打包清单发现可疑内容：\n{summary}")


if __name__ == "__main__":
    unittest.main()
