# -*- coding: utf-8 -*-
"""风格档案的加载/校验/查询测试。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_core import profiles


def _profile(**over):
    base = {
        "name": "测试风",
        "description": "测试用",
        "persona": "测试人设",
        "catchphrases": ["嗯嗯"],
        "sentence_patterns": ["多用短句"],
        "emotion_expressions": ["开心用哈哈哈哈"],
        "avoid": ["书面语"],
        "examples": ["示例一"],
    }
    base.update(over)
    return base


class TestValidate(unittest.TestCase):
    def test_valid_profile(self):
        self.assertIsNone(profiles.validate_profile(_profile()))

    def test_missing_optional_fields_ok(self):
        """只有 name 也可通过校验（渲染时跳过空字段）。"""
        self.assertIsNone(profiles.validate_profile({"name": "极简风"}))

    def test_non_dict(self):
        self.assertIsNotNone(profiles.validate_profile("not dict"))
        self.assertIsNotNone(profiles.validate_profile(None))

    def test_bad_name(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(name="")))
        self.assertIsNotNone(profiles.validate_profile(_profile(name="x" * 33)))

    def test_unknown_field(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(hack="x")))

    def test_list_fields_must_be_str_list(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(catchphrases="嗯嗯")))
        self.assertIsNotNone(profiles.validate_profile(_profile(catchphrases=[1, 2])))
        self.assertIsNone(profiles.validate_profile(_profile(catchphrases=["嗯嗯"])))

    def test_too_many_items(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(catchphrases=["x"] * 51)))


class TestNormalize(unittest.TestCase):
    def test_normalize_fills_empties(self):
        p = profiles.normalize_profile({"name": "极简风"})
        self.assertEqual(p["catchphrases"], [])
        self.assertEqual(p["sentence_patterns"], [])
        self.assertEqual(p["persona"], "")

    def test_normalize_strips(self):
        p = profiles.normalize_profile(_profile(catchphrases=[" 嗯嗯 ", ""]))
        self.assertEqual(p["catchphrases"], ["嗯嗯"])

    def test_normalize_new_fields_empty(self):
        """v2.3.0：旧档案（无新字段）规范化后补空列表。"""
        p = profiles.normalize_profile({"name": "旧风"})
        self.assertEqual(p["decision_rules"], [])
        self.assertEqual(p["interaction_scripts"], [])
        self.assertEqual(p["corrections"], [])

    def test_normalize_new_fields(self):
        p = profiles.normalize_profile(_profile(
            decision_rules=["先确认背景", " 数据>人情 "],
            interaction_scripts=["对上级先给结论"],
        ))
        self.assertEqual(p["decision_rules"], ["先确认背景", "数据>人情"])
        self.assertEqual(p["interaction_scripts"], ["对上级先给结论"])

    def test_normalize_corrections(self):
        p = profiles.normalize_profile(_profile(corrections=[
            {"scene": "被夸时", "wrong": "客气推辞", "correct": "坦然接受"},
            {"scene": " ", "wrong": "x", "correct": "y"},  # 空场景被丢弃
        ]))
        self.assertEqual(len(p["corrections"]), 1)
        self.assertEqual(p["corrections"][0]["correct"], "坦然接受")


class TestCorrectionsValidation(unittest.TestCase):
    def test_valid_corrections(self):
        self.assertIsNone(profiles.validate_profile(_profile(corrections=[
            {"scene": "开会", "wrong": "嗯嗯对", "correct": "先对齐背景"}
        ])))

    def test_corrections_not_list(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(corrections="x")))
        self.assertIsNotNone(profiles.validate_profile(_profile(corrections=123)))

    def test_corrections_item_not_dict(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(corrections=["x"])))

    def test_corrections_missing_key(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(
            corrections=[{"scene": "开会", "wrong": "嗯嗯"}]  # 缺 correct
        )))

    def test_corrections_empty_value(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(
            corrections=[{"scene": "", "wrong": "x", "correct": "y"}]
        )))

    def test_corrections_too_many(self):
        items = [{"scene": f"s{i}", "wrong": "w", "correct": "c"} for i in range(21)]
        self.assertIsNotNone(profiles.validate_profile(_profile(corrections=items)))

    def test_corrections_too_long(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(
            corrections=[{"scene": "x" * 201, "wrong": "w", "correct": "c"}]
        )))

    def test_new_list_fields_validation(self):
        self.assertIsNotNone(profiles.validate_profile(_profile(decision_rules="非列表")))
        self.assertIsNotNone(profiles.validate_profile(_profile(interaction_scripts=[1, 2])))
        self.assertIsNone(profiles.validate_profile(_profile(
            decision_rules=["先确认背景"], interaction_scripts=["对上级先给结论"]
        )))


class TestAddCorrection(unittest.TestCase):
    def test_add_ok(self):
        p, err = profiles.add_correction(_profile(), "开会", "嗯嗯对", "先对齐")
        self.assertIsNone(err)
        self.assertEqual(len(p["corrections"]), 1)
        self.assertEqual(p["corrections"][0]["scene"], "开会")
        # 入参不被修改（纯函数）
        self.assertEqual(_profile().get("corrections"), None)

    def test_add_empty_rejected(self):
        p, err = profiles.add_correction(_profile(), "", "w", "c")
        self.assertIsNotNone(err)
        self.assertEqual(p.get("corrections"), None)

    def test_add_over_limit(self):
        existing = [{"scene": f"s{i}", "wrong": "w", "correct": "c"} for i in range(20)]
        p, err = profiles.add_correction(_profile(corrections=existing), "s21", "w", "c")
        self.assertIsNotNone(err)
        self.assertIn("已满", err)

    def test_add_strips_whitespace(self):
        p, err = profiles.add_correction(_profile(), " 开会 ", " 嗯嗯 ", " 先对齐 ")
        self.assertEqual(p["corrections"][0]["scene"], "开会")
        self.assertEqual(p["corrections"][0]["wrong"], "嗯嗯")

    def test_add_invalid_profile(self):
        p, err = profiles.add_correction("not dict", "s", "w", "c")
        self.assertIsNotNone(err)


class TestLoadListFind(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, data):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_list_profiles_skips_bad(self):
        self._write("a.json", _profile(name="甲风"))
        self._write("bad.json", "not json")
        self._write("bad2.json", _profile(name="x" * 99))  # name 过长校验失败
        self._write("note.txt", "ignore me")
        ps = profiles.list_profiles(self.dir)
        names = [p["name"] for p in ps]
        self.assertIn("甲风", names)
        self.assertEqual(len(ps), 1)

    def test_find_profile_case_insensitive(self):
        self._write("a.json", _profile(name="日常口语风"))
        self.assertIsNotNone(profiles.find_profile(self.dir, "日常口语风"))
        self.assertIsNotNone(profiles.find_profile(self.dir, "日常口语风"))
        self.assertIsNone(profiles.find_profile(self.dir, "不存在的风"))

    def test_load_missing_file(self):
        self.assertIsNone(profiles.load_profile_file(os.path.join(self.dir, "nope.json")))

    def test_save_and_reload(self):
        path = profiles.save_profile_file(self.dir, _profile(name="保存风"))
        self.assertTrue(os.path.exists(path))
        loaded = profiles.load_profile_file(path)
        self.assertEqual(loaded["name"], "保存风")
        self.assertEqual(loaded["catchphrases"], ["嗯嗯"])

    def test_save_sanitizes_filename(self):
        path = profiles.save_profile_file(self.dir, _profile(name="风 格/测试"))
        self.assertIn(".json", os.path.basename(path))
        # 非法字符被替换，文件名不含空格斜杠
        self.assertNotIn(" ", os.path.basename(path))
        self.assertNotIn("/", os.path.basename(path))

    def test_list_profiles_path_is_file(self):
        """v2.8.1：styles_dir 是文件而非目录时返回空列表，不抛。"""
        f = os.path.join(self.dir, "afile")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("x")
        self.assertEqual(profiles.list_profiles(f), [])

    def test_list_profiles_listdir_error_returns_empty(self):
        """v2.8.1：os.listdir 抛错（目录被锁/删除）时返回空列表，不抛 OSError。

        用 monkeypatch 模拟 os.listdir 抛 PermissionError。
        """
        import style_core.profiles as profiles_mod

        orig = profiles_mod.os.listdir
        try:
            def boom(*_a, **_k):
                raise PermissionError(13, "Permission denied")
            profiles_mod.os.listdir = boom
            self.assertEqual(profiles_mod.list_profiles(self.dir), [])
        finally:
            profiles_mod.os.listdir = orig


if __name__ == "__main__":
    unittest.main()
