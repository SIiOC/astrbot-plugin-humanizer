# -*- coding: utf-8 -*-
"""v3.5.2 真人感规则集纯函数测试（humanizer_core.humaneness_rules）。

零 astrbot 依赖；临时文件走系统临时目录（不碰插件目录）。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import humaneness_rules as HR


def _rule(name="测试", rtype="inject", content="内容", **kw):
    base = {"id": kw.pop("id", "x-1"), "name": name, "type": rtype,
            "enabled": kw.pop("enabled", True), "builtin": kw.pop("builtin", False),
            "content": content}
    base.update(kw)
    return base


class TestNormalizeRule(unittest.TestCase):
    def test_valid_kept(self):
        r = HR.normalize_rule(_rule())
        self.assertIsNotNone(r)
        self.assertEqual(r["id"], "x-1")

    def test_invalid_dropped(self):
        for bad in (
            None, "str", {},
            _rule(name=""), _rule(id=""), _rule(content=""),
            _rule(rtype="unknown"),
            ["list"],
        ):
            self.assertIsNone(HR.normalize_rule(bad), f"应丢弃: {bad!r}")

    def test_qc_pattern_defaults_to_content(self):
        r = HR.normalize_rule(_rule(rtype="qc", content="不得自称AI"))
        self.assertEqual(r["qc_pattern"], "不得自称AI")

    def test_inject_has_no_qc_pattern(self):
        r = HR.normalize_rule(_rule())
        self.assertNotIn("qc_pattern", r)


class TestStoreRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="hrules_")
        try:
            path = os.path.join(tmp, "humaneness_rules.json")
            rules = [_rule(id="a"), _rule(id="b", rtype="qc", content="k1，k2")]
            HR.save_rules(path, rules)
            loaded = HR.load_rules(path)
            self.assertEqual([r["id"] for r in loaded], ["a", "b"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_corrupt_and_missing(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="hrules_")
        try:
            path = os.path.join(tmp, "humaneness_rules.json")
            self.assertEqual(HR.load_rules(path), [])  # 缺失
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken")
            self.assertEqual(HR.load_rules(path), [])  # 损坏
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"version":1,"rules":[{"id":"ok","name":"n","type":"inject","content":"c"},{"garbage":1}]}')
            loaded = HR.load_rules(path)
            self.assertEqual(len(loaded), 1)  # 非法条目丢弃
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestMigrateBuiltins(unittest.TestCase):
    def test_empty_adds_all(self):
        out, added = HR.migrate_builtins([])
        self.assertEqual(added, len(HR.BUILTIN_RULES))
        self.assertEqual(len(out), len(HR.BUILTIN_RULES))
        self.assertTrue(all(r["builtin"] for r in out))

    def test_idempotent(self):
        out1, _ = HR.migrate_builtins([])
        out2, added2 = HR.migrate_builtins(out1)
        self.assertEqual(added2, 0)
        self.assertEqual(len(out2), len(out1))

    def test_preserves_disabled_state(self):
        seeded = [dict(HR.BUILTIN_RULES[0], enabled=False)]
        out, added = HR.migrate_builtins(list(seeded))
        self.assertEqual(added, len(HR.BUILTIN_RULES) - 1)
        match = [r for r in out if r["id"] == seeded[0]["id"]]
        self.assertEqual(len(match), 1)
        self.assertFalse(match[0]["enabled"], "用户停用的预置规则不得被迁移复活")


class TestCrud(unittest.TestCase):
    def setUp(self):
        self.rules, _ = HR.migrate_builtins([])

    def test_add_and_dup(self):
        out, err = HR.add_rule(self.rules, "新规则", "inject", "别啰嗦")
        self.assertEqual(err, "")
        self.assertEqual(len(out), len(self.rules) + 1)
        out2, err2 = HR.add_rule(out, "新规则", "inject", "别的")
        self.assertNotEqual(err2, "")
        self.assertEqual(len(out2), len(out))

    def test_add_bad_type_and_empty(self):
        for args in (("", "inject", "x"), ("n", "bad", "x"), ("n", "inject", "")):
            out, err = HR.add_rule(self.rules, *args)
            self.assertNotEqual(err, "")
            self.assertEqual(out, self.rules)

    def test_delete_builtin_refused_user_ok(self):
        builtin = next(r for r in self.rules if r["builtin"])
        out, err = HR.delete_rule(self.rules, builtin["id"])
        self.assertNotEqual(err, "")
        self.assertEqual(out, self.rules)
        out2, err2 = HR.add_rule(self.rules, "临时的", "inject", "x")
        out3, err3 = HR.delete_rule(out2, "临时的")
        self.assertEqual(err3, "")
        self.assertEqual(len(out3), len(self.rules))

    def test_toggle_by_seq_and_name(self):
        out, err = HR.toggle_rule(self.rules, "1", False)
        self.assertEqual(err, "")
        self.assertFalse(out[0]["enabled"])
        out2, err2 = HR.toggle_rule(out, "时间感知检查", True)
        self.assertEqual(err2, "")
        self.assertTrue(out2[0]["enabled"])
        self.assertIsNot(out2[0], self.rules[0], "不得原地修改输入")

    def test_find_rule(self):
        r, err = HR.find_rule(self.rules, "2")
        self.assertEqual(err, "")
        self.assertEqual(r["id"], self.rules[1]["id"])
        r2, err2 = HR.find_rule(self.rules, "999")
        self.assertIsNone(r2)
        r3, err3 = HR.find_rule(self.rules, "不存在")
        self.assertIsNone(r3)


class TestQcMatch(unittest.TestCase):
    def test_keyword_default(self):
        rule = _rule(rtype="qc", content="x", qc_pattern="作为AI，语言模型")
        self.assertTrue(HR.qc_violations("我作为AI认为", [rule]))
        self.assertTrue(HR.qc_violations("我是语言模型", [rule]))
        self.assertEqual(HR.qc_violations("我今天吃饭", [rule]), [])

    def test_pipe_and_mixed_comma_split(self):
        rule = _rule(rtype="qc", content="x", qc_pattern="a|b，c,d")
        for hit in ("xa", "xb", "xc", "xd"):
            self.assertTrue(HR.qc_violations(hit, [rule]))

    def test_regex_prefix(self):
        rule = _rule(rtype="qc", content="x", qc_pattern="re:作为AI|大\\d+模型")
        self.assertTrue(HR.qc_violations("我是大3模型", [rule]))
        self.assertFalse(HR.qc_violations("没事", [rule]))

    def test_invalid_regex_safe_false(self):
        rule = _rule(rtype="qc", content="x", qc_pattern="re:[未闭合")
        self.assertEqual(HR.qc_violations("任意文本", [rule]), [])

    def test_disabled_and_non_qc_excluded(self):
        off = _rule(rtype="qc", content="x", qc_pattern="关键词", enabled=False)
        inj = _rule(rtype="inject", content="关键词")
        self.assertEqual(HR.qc_violations("有关键词", [off, inj]), [])

    def test_empty_text(self):
        rule = _rule(rtype="qc", content="x", qc_pattern="a")
        self.assertEqual(HR.qc_violations("", [rule]), [])
        self.assertEqual(HR.qc_violations(None, [rule]), [])


class TestRender(unittest.TestCase):
    def test_inject_section(self):
        rules = [
            _rule(id="1", rtype="inject", content="规则一"),
            _rule(id="2", rtype="inject", content="规则二", enabled=False),
            _rule(id="3", rtype="qc", content="质检不进注入"),
        ]
        text = HR.render_inject_section(rules)
        self.assertIn("【真人感规则】", text)
        self.assertIn("规则一", text)
        self.assertNotIn("规则二", text)
        self.assertNotIn("质检不进注入", text)

    def test_inject_empty_when_no_enabled(self):
        self.assertEqual(HR.render_inject_section([]), "")
        self.assertEqual(
            HR.render_inject_section([_rule(rtype="inject", enabled=False)]), ""
        )

    def test_inject_cap_and_clip(self):
        many = [
            _rule(id=str(i), rtype="inject", content="长" * 200)
            for i in range(30)
        ]
        text = HR.render_inject_section(many)
        self.assertLessEqual(text.count("- "), HR.INJECT_MAX_RULES)
        self.assertIn("条规则未载入", text)
        for line in text.splitlines():
            if line.startswith("- "):
                self.assertLessEqual(len(line), HR.INJECT_MAX_CONTENT + 4)

    def test_qc_instruction(self):
        v = [_rule(name="禁宣誓句", rtype="qc", content="不用宣誓式表达")]
        text = HR.render_qc_instruction(v)
        self.assertIn("禁宣誓句", text)
        self.assertIn("宣誓", text)
        self.assertEqual(HR.render_qc_instruction([]), "")


class TestBuiltinV360(unittest.TestCase):
    """v3.6.0 补库：blader 35 tells 的聊天向子集（客服腔/过度附和/强行提问）。"""

    def test_new_builtin_ids_present(self):
        ids = {r["id"] for r in HR.BUILTIN_RULES}
        for rid in (
            "builtin-no-forced-question",
            "builtin-no-support-tone",
            "builtin-no-flattery",
            "builtin-qc-support-tone",
            "builtin-qc-flattery",
        ):
            self.assertIn(rid, ids)

    def test_inject_contents_within_cap(self):
        for r in HR.BUILTIN_RULES:
            if r["type"] == "inject":
                self.assertLessEqual(
                    len(r["content"]), HR.INJECT_MAX_CONTENT, r["id"]
                )

    def test_qc_support_tone_hits(self):
        rules, _ = HR.migrate_builtins([])
        for t in (
            "希望这对你有帮助，加油！",
            "希望这有帮助",
            "希望以上对你有所帮助",
            "有问题随时找我",
            "如果还有任何问题请告诉我",
            "有问题可以随时联系我哦",
        ):
            self.assertTrue(HR.qc_violations(t, rules), t)

    def test_qc_support_tone_no_false_positive(self):
        rules, _ = HR.migrate_builtins([])
        for t in (
            "祝你生日快乐！",
            "希望你今天过得开心",
            "希望你玩得开心呀",
            "有空我们再聊",
        ):
            self.assertFalse(HR.qc_violations(t, rules), t)

    def test_qc_flattery_hits_at_start(self):
        rules, _ = HR.migrate_builtins([])
        for t in ("你说得太对了！", "好问题！让我想想", "问得好！", "问得不错。"):
            self.assertTrue(HR.qc_violations(t, rules), t)

    def test_qc_flattery_spares_mid_sentence(self):
        # 只拦开头形态：中缀出现不算命中（防误杀真人表达），生成端由 inject 约束
        rules, _ = HR.migrate_builtins([])
        for t in ("这是个好问题，不过我觉得", "哈哈你说得太对了", "你问得好有意思"):
            self.assertFalse(HR.qc_violations(t, rules), t)


class TestBuiltinV380Time(unittest.TestCase):
    """v3.8.0 补库：时笺 TIME_GUIDE 时间行为规则（改写为 Humanizer 语境，非照搬）。"""

    NEW_IDS = (
        "builtin-time-no-fabricate",
        "builtin-time-colloquial",
        "builtin-gap-tone",
        "builtin-calendar-natural",
    )

    def test_new_builtin_ids_present(self):
        ids = {r["id"] for r in HR.BUILTIN_RULES}
        for rid in self.NEW_IDS:
            self.assertIn(rid, ids)

    def test_all_are_enabled_inject_type(self):
        by_id = {r["id"]: r for r in HR.BUILTIN_RULES}
        for rid in self.NEW_IDS:
            self.assertEqual(by_id[rid]["type"], "inject", rid)
            self.assertTrue(by_id[rid]["enabled"], rid)

    def test_migrate_idempotent_adds_all_four(self):
        rules, added = HR.migrate_builtins([])
        ids = {r["id"] for r in rules}
        self.assertTrue(set(self.NEW_IDS).issubset(ids))
        self.assertEqual(added, len(HR.BUILTIN_RULES))
        # 二次迁移不再新增
        _, again = HR.migrate_builtins(rules)
        self.assertEqual(again, 0)

    def test_new_inject_contents_within_cap(self):
        by_id = {r["id"]: r for r in HR.BUILTIN_RULES}
        for rid in self.NEW_IDS:
            self.assertLessEqual(
                len(by_id[rid]["content"]), HR.INJECT_MAX_CONTENT, rid
            )



class TestBuiltinV390Tells(unittest.TestCase):
    """v3.9.0 tells 补库（来源 no-ai-slop 对话向子集）：命中/放行与封顶余量。"""

    NEW_IDS = (
        "builtin-qc-sublimation",
        "builtin-qc-vague-source",
        "builtin-qc-lecture-opener",
        "builtin-qc-summary-opener",
        "builtin-no-essay-ending",
        "builtin-no-lecture-tone",
        "builtin-no-parallelism",
        "builtin-no-dramatic-ending",
    )

    def test_ids_present_and_migrate(self):
        rules, added = HR.migrate_builtins([])
        ids = {r["id"] for r in rules}
        for rid in self.NEW_IDS:
            self.assertIn(rid, ids)
        self.assertEqual(added, len(HR.BUILTIN_RULES))

    def test_qc_sublimation(self):
        r = {"qc_pattern": "re:这(不仅|不只是)[^。！？]{0,20}(更是|也是)"}
        self.assertTrue(HR._qc_violation("这不只是一次聊天，更是一种陪伴", r))
        self.assertFalse(HR._qc_violation("这不只是聊天", r))  # 缺后半
        self.assertFalse(HR._qc_violation("不只是普通的一天，也是节日", r))  # 缺「这」引导

    def test_qc_vague_source(self):
        r = {"qc_pattern": "re:(研究|科学)(表明|显示)|专家(表示|指出)"}
        self.assertTrue(HR._qc_violation("研究表明早睡比较好", r))
        self.assertTrue(HR._qc_violation("专家表示这样不行", r))
        self.assertFalse(HR._qc_violation("我研究了一下这个游戏", r))  # 研究后不接表明/显示
        self.assertFalse(HR._qc_violation("专家说得对吧", r))  # 说得对非表明句式

    def test_qc_lecture_opener(self):
        r = {"qc_pattern": "re:^(记住|请注意|听好了|你要知道)[，,：:]"}
        self.assertTrue(HR._qc_violation("记住：早点睡", r))
        self.assertTrue(HR._qc_violation("你要知道，这样不行", r))
        self.assertFalse(HR._qc_violation("你记住：我说过", r))  # 非行首
        self.assertFalse(HR._qc_violation("记住这个教训吧", r))  # 无标点分隔

    def test_qc_summary_opener(self):
        r = {"qc_pattern": "re:^(总之|总的来说|总而言之|综上)[，,。！？]"}
        self.assertTrue(HR._qc_violation("总之，就这么定了", r))
        self.assertTrue(HR._qc_violation("总而言之。", r))
        self.assertFalse(HR._qc_violation("我总之下次再约", r))  # 非行首
        self.assertFalse(HR._qc_violation("总之就这样", r))  # 无分隔标点（口语可接受，放行）

    def test_inject_count_within_render_cap(self):
        enabled_inject = [
            r for r in HR.BUILTIN_RULES if r["type"] == "inject" and r["enabled"]
        ]
        self.assertLessEqual(len(enabled_inject), HR.INJECT_MAX_RULES)

    def test_inject_contents_within_char_cap(self):
        by_id = {r["id"]: r for r in HR.BUILTIN_RULES}
        for rid in self.NEW_IDS:
            self.assertLessEqual(
                len(by_id[rid]["content"]), HR.INJECT_MAX_CONTENT, rid
            )

    def test_render_contains_new_tells(self):
        section = HR.render_inject_section(HR.BUILTIN_RULES)
        self.assertIn("不写作文收尾", section)
        self.assertIn("克制工整排比", section)

if __name__ == "__main__":
    unittest.main()
