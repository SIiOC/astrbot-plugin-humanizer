# -*- coding: utf-8 -*-
"""v3.11.0 波1 补测：severity 分级 + 注入子集轮换 + 星期/活跃时段。

覆盖三块新机制（纯函数层，零 astrbot 依赖）：
1. humaneness_rules：severity 字段规范化/迁移回填/排序/子集轮换/终检清单；
2. proactive：时段解析的星期前缀、活跃窗口、next_quiet_end/next_active_start。

临时文件走系统临时目录（不碰插件目录）。
"""

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import humaneness_rules as HR
from humanizer_core.proactive import (
    in_active_window,
    in_quiet,
    next_active_start,
    next_quiet_end,
)


def _rule(name="测试", rtype="inject", content="内容", **kw):
    base = {"id": kw.pop("id", "x-1"), "name": name, "type": rtype,
            "enabled": kw.pop("enabled", True), "builtin": kw.pop("builtin", False),
            "content": content}
    base.update(kw)
    return base


class TestSeverityNormalize(unittest.TestCase):
    def test_rules_version_bumped(self):
        self.assertEqual(HR.RULES_VERSION, 2)

    def test_valid_severity_kept(self):
        for sev in ("S1", "S2", "S3", "s1"):
            r = HR.normalize_rule(_rule(severity=sev))
            self.assertEqual(r["severity"], sev.upper())

    def test_missing_or_invalid_defaults(self):
        self.assertEqual(HR.normalize_rule(_rule())["severity"], HR.DEFAULT_SEVERITY)
        self.assertEqual(
            HR.normalize_rule(_rule(severity="X9"))["severity"], HR.DEFAULT_SEVERITY
        )

    def test_builtin_all_have_severity(self):
        for r in HR.BUILTIN_RULES:
            self.assertIn(r.get("severity"), HR.SEVERITIES, r["id"])

    def test_inject_count_within_cap(self):
        inject = [r for r in HR.BUILTIN_RULES if r["type"] == "inject" and r["enabled"]]
        self.assertLessEqual(len(inject), HR.INJECT_MAX_RULES)


class TestSeverityMigrate(unittest.TestCase):
    def test_legacy_file_upgrade_end_to_end(self):
        """审查修复：旧 v1 文件经真实加载链升级后，S1/S3 内置规则不得被压平成 S2。

        回归背景：normalize_rule 对缺 severity 的旧条目无条件填默认 S2，
        导致 migrate_builtins 的回填分支在真实链路上是死代码——初版测试
        直调 migrate 绕过了 normalize，未抓到。现钉死 load_rules →
        migrate_builtins 全链路（与 main._init_time_stores 相同）。
        """
        import json
        import tempfile
        tmp = tempfile.mkdtemp(prefix="hrules_")
        try:
            path = os.path.join(tmp, "humaneness_rules.json")
            legacy = {"version": 1, "rules": [
                {"id": "builtin-no-stage-direction", "name": "禁表演感描写",
                 "type": "inject", "enabled": True, "builtin": True,
                 "content": "不写表演感描写。"},
                {"id": "builtin-no-parallelism", "name": "克制排比",
                 "type": "inject", "enabled": True, "builtin": True,
                 "content": "克制工整排比。"},
                {"id": "builtin-time-aware", "name": "时间感知检查",
                 "type": "inject", "enabled": True, "builtin": True,
                 "content": "回复须与时间上下文一致。"},
            ]}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(legacy, f, ensure_ascii=False)
            rules, added = HR.migrate_builtins(HR.load_rules(path))
            self.assertEqual(added, len(HR.BUILTIN_RULES) - 3)
            by_id = {r["id"]: r for r in rules}
            canon = {r["id"]: r["severity"] for r in HR.BUILTIN_RULES}
            for rid in ("builtin-no-stage-direction", "builtin-no-parallelism",
                        "builtin-time-aware"):
                self.assertEqual(
                    by_id[rid]["severity"], canon[rid],
                    f"{rid} 升级后 severity 须与内置表一致",
                )
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reload_path_canonicalizes_too(self):
        """/rules_reload 只调 load_rules（不 migrate），规范化必须覆盖该路径。"""
        import json
        import tempfile
        tmp = tempfile.mkdtemp(prefix="hrules_")
        try:
            path = os.path.join(tmp, "humaneness_rules.json")
            legacy = {"version": 1, "rules": [
                {"id": "builtin-no-parallelism", "name": "克制排比",
                 "type": "inject", "enabled": True, "builtin": True,
                 "content": "克制工整排比。"},
            ]}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(legacy, f, ensure_ascii=False)
            canon = {r["id"]: r["severity"] for r in HR.BUILTIN_RULES}
            self.assertEqual(
                HR.load_rules(path)[0]["severity"],
                canon["builtin-no-parallelism"],
            )
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_user_rule_defaults_s2_and_migrate_leaves_it(self):
        user = [_rule(id="u-1")]
        user[0].pop("severity", None)
        out, _ = HR.migrate_builtins(user)
        got = next(r for r in out if r["id"] == "u-1")
        self.assertNotIn("severity", got, "migrate 不碰用户规则（S2 兜底由 normalize 负责）")
        # 但 normalize 路径（load/add）会给用户规则 S2 兜底
        self.assertEqual(HR.normalize_rule(dict(user[0]))["severity"], HR.DEFAULT_SEVERITY)

    def test_idempotent(self):
        out1, _ = HR.migrate_builtins([])
        _, again = HR.migrate_builtins(out1)
        self.assertEqual(again, 0)


class TestSeveritySort(unittest.TestCase):
    def test_order_s1_s2_s3(self):
        rules = [_rule(id="c", severity="S3"), _rule(id="a", severity="S1"),
                 _rule(id="b", severity="S2")]
        got = [r["id"] for r in HR.sort_by_severity(rules)]
        self.assertEqual(got, ["a", "b", "c"])

    def test_unknown_treated_as_s2(self):
        self.assertEqual(HR.severity_rank({"severity": "??"}), HR.SEVERITY_RANK["S2"])
        self.assertEqual(HR.severity_rank({}), HR.SEVERITY_RANK["S2"])


class TestSelectInjectSubset(unittest.TestCase):
    def _pool(self):
        return [
            _rule(id="s1a", severity="S1", content="核心1"),
            _rule(id="s2a", severity="S2", content="核心2"),
            _rule(id="s3a", severity="S3", content="风味A"),
            _rule(id="s3b", severity="S3", content="风味B"),
            _rule(id="s3c", severity="S3", content="风味C"),
        ]

    def test_core_always_present(self):
        for off in range(6):
            ids = {r["id"] for r in HR.select_inject_subset(self._pool(), off)}
            self.assertLessEqual({"s1a", "s2a"}, ids, f"核心必须在 offset={off}")

    def test_flavor_rotates(self):
        seen = set()
        for off in range(6):
            ids = [r["id"] for r in HR.select_inject_subset(self._pool(), off, 2)]
            flavor = [i for i in ids if i.startswith("s3")]
            seen.update(flavor)
            self.assertEqual(len(flavor), 2, f"offset={off} 应恰露 2 条风味")
        self.assertEqual(seen, {"s3a", "s3b", "s3c"}, "轮换应覆盖全部风味规则")

    def test_window_ge_pool_returns_all(self):
        ids = [r["id"] for r in HR.select_inject_subset(self._pool(), 0, 99)]
        self.assertEqual(len(ids), 5)

    def test_no_inject_returns_empty(self):
        self.assertEqual(HR.select_inject_subset([]), [])
        self.assertEqual(
            HR.select_inject_subset([_rule(rtype="qc", content="x")]), []
        )

    def test_disabled_excluded(self):
        pool = [_rule(id="off", severity="S1", enabled=False, content="x")]
        self.assertEqual(HR.select_inject_subset(pool), [])


class TestFinalCheck(unittest.TestCase):
    def test_has_five_and_nonempty(self):
        text = HR.render_final_check()
        self.assertTrue(text)
        for token in ("不是X而是Y", "单句断言", "破折号", "三连排比", "加粗"):
            self.assertIn(token, text)

    def test_count_is_five(self):
        self.assertEqual(len(HR.FINAL_CHECK_TELLS), 5)

    def test_qc_instruction_appends_final_check(self):
        """审查修复：终检清单必须真正接线进 QC 改写指令（曾被定义却未调用）。"""
        v = [_rule(name="禁宣誓句", rtype="qc", content="不用宣誓式表达")]
        text = HR.render_qc_instruction(v)
        self.assertIn("禁宣誓句", text)
        self.assertIn("最易复活", text, "QC 指令应附终检清单")
        # 无违规时不得带终检（避免空改写也注入）
        self.assertEqual(HR.render_qc_instruction([]), "")

    def test_qc_instruction_no_final_check_when_none(self):
        import unittest.mock as mock
        with mock.patch.object(HR, "FINAL_CHECK_TELLS", ()):
            v = [_rule(name="n", rtype="qc", content="c")]
            self.assertNotIn("最易复活", HR.render_qc_instruction(v))


class TestWeekdayQuiet(unittest.TestCase):
    """2026-08-17 是周一；08-22 周六；08-23 周日。"""

    def test_legacy_format_unchanged(self):
        self.assertTrue(in_quiet(datetime(2026, 8, 17, 3, 0), "22:00-07:00"))
        self.assertFalse(in_quiet(datetime(2026, 8, 17, 12, 0), "22:00-07:00"))

    def test_weekday_prefix(self):
        self.assertTrue(in_quiet(datetime(2026, 8, 17, 10, 0), "mon-fri 09:00-18:00"))
        self.assertFalse(in_quiet(datetime(2026, 8, 22, 10, 0), "mon-fri 09:00-18:00"))

    def test_weekend_plus(self):
        self.assertTrue(in_quiet(datetime(2026, 8, 22, 10, 0), "sat+sun 09:00-18:00"))
        self.assertFalse(in_quiet(datetime(2026, 8, 20, 10, 0), "sat+sun 09:00-18:00"))

    def test_numeric_weekday(self):
        # 0=周一：2=周三（08-19）
        self.assertTrue(in_quiet(datetime(2026, 8, 19, 10, 0), "2 09:00-18:00"))
        self.assertFalse(in_quiet(datetime(2026, 8, 18, 10, 0), "2 09:00-18:00"))

    def test_numeric_convention_zero_is_monday(self):
        """锁死数字约定：0=周一（工作日=0-4，非 1-5）。审查发现文档曾误写 1-5。"""
        # 08-17 周一
        self.assertTrue(in_quiet(datetime(2026, 8, 17, 10, 0), "0-4 09:00-18:00"))
        # 08-21 周五仍在 0-4 内
        self.assertTrue(in_quiet(datetime(2026, 8, 21, 10, 0), "0-4 09:00-18:00"))
        # 08-22 周六不在 0-4 内
        self.assertFalse(in_quiet(datetime(2026, 8, 22, 10, 0), "0-4 09:00-18:00"))

    def test_crosday_weekday_ownership(self):
        # 周五 22:00-02:00：周六凌晨属周五段，周日凌晨不属
        self.assertTrue(in_quiet(datetime(2026, 8, 22, 1, 0), "fri 22:00-02:00"))
        self.assertFalse(in_quiet(datetime(2026, 8, 23, 1, 0), "fri 22:00-02:00"))

    def test_bad_segment_skipped(self):
        self.assertTrue(in_quiet(datetime(2026, 8, 17, 12, 30), "zzz 01:00-02:00, 12:00-13:00"))


class TestActiveWindow(unittest.TestCase):
    def test_empty_means_no_limit(self):
        self.assertTrue(in_active_window(datetime(2026, 8, 17, 3, 0), ""))
        self.assertTrue(in_active_window(datetime(2026, 8, 17, 3, 0), None))

    def test_hit_and_miss(self):
        self.assertTrue(in_active_window(datetime(2026, 8, 17, 10, 0), "09:00-22:00"))
        self.assertFalse(in_active_window(datetime(2026, 8, 17, 23, 0), "09:00-22:00"))

    def test_with_weekday(self):
        self.assertTrue(in_active_window(datetime(2026, 8, 17, 10, 0), "mon-fri 09:00-18:00"))
        self.assertFalse(in_active_window(datetime(2026, 8, 22, 10, 0), "mon-fri 09:00-18:00"))

    def test_invalid_spec_degrades_to_unlimited(self):
        """审查修复：活跃时段配置非空但全非法 → 降级为不限制（安全向失败）。

        与 in_quiet 的"非法=不打扰"相反：白名单笔误不应让 bot 永不主动。
        """
        for bad in ("garbage", "25:99-26:99", "abc-def", "mon- 09:00", "::: "):
            self.assertTrue(
                in_active_window(datetime(2026, 8, 17, 3, 0), bad),
                f"非法活跃时段应降级为不限制: {bad!r}",
            )
        # 对照：非法勿扰时段仍偏向不打扰（旧语义不变）
        for bad in ("garbage", "25:99-26:99"):
            self.assertFalse(in_quiet(datetime(2026, 8, 17, 3, 0), bad))


class TestNextBoundaries(unittest.TestCase):
    def test_next_quiet_end_legacy(self):
        got = next_quiet_end(datetime(2026, 8, 17, 3, 0), "22:00-07:00")
        self.assertEqual((got.hour, got.minute), (7, 0))
        self.assertEqual(got.day, 17)

    def test_next_quiet_end_none_when_outside(self):
        self.assertIsNone(next_quiet_end(datetime(2026, 8, 17, 12, 0), "22:00-07:00"))

    def test_next_active_start(self):
        got = next_active_start(datetime(2026, 8, 17, 8, 0), "09:00-22:00")
        self.assertEqual((got.hour, got.minute), (9, 0))

    def test_next_active_start_weekday(self):
        # 周六 10:00 → 下一个工作日段在下周一 09:00
        got = next_active_start(datetime(2026, 8, 22, 10, 0), "mon-fri 09:00-18:00")
        self.assertEqual(got.weekday(), 0)
        self.assertEqual((got.hour, got.minute), (9, 0))

    def test_next_active_start_empty_none(self):
        self.assertIsNone(next_active_start(datetime(2026, 8, 17, 10, 0), ""))


class TestNewQcNoFalsePositive(unittest.TestCase):
    """审查修复回归：新增 QC 型规则必须对自然口语零误报。

    模块设计原则（见 humaneness_rules 头注）：QC 命中会触发整轮 LLM 改写，
    故 QC 型只收「口语中罕见的高置信痕迹」，宁可漏检也不误杀真人表达。
    本轮初版有 3 条正则误报率过高（10 条自然口语命中 7 条），已收紧。
    """

    HUMAN_UTTERANCES = (
        "我不能保证明天有空，先别定。",
        "这个能不能成我也不敢保证。",
        "早点休息很有必要。",
        "这顿饭吃得很有意义，好久没聚了。",
        "很多人觉得难，但其实上手还行。",
        "有人说这个好，可是我用着一般。",
        "首先我想说的是谢谢，然后呢咱们再聊。",
        "首先谢谢你，其次我确实不知道。",
        "这事很有价值，值得做。",
        "这个很值得思考，我再想想。",
        "我的知识有限，多包涵。",
        "见证了我们的友谊，挺好。",
        "首先我先看看，最后再决定。",
        "作为朋友，我建议你别去。",
        "人工智能这两年发展真快。",
        "我先保证不迟到。",
        "这是我标志性的穿搭。",
        "标志着性的事件发生了。",
    )
    NEW_QC_IDS = (
        "builtin-qc-disclaimer",
        "builtin-qc-grandiose",
        "builtin-qc-enumeration",
        "builtin-qc-double-dash",
    )

    def test_no_false_positive_on_natural_speech(self):
        by_id = {r["id"]: r for r in HR.BUILTIN_RULES}
        for rid in self.NEW_QC_IDS:
            r = by_id[rid]
            for t in self.HUMAN_UTTERANCES:
                self.assertFalse(
                    HR._qc_violation(t, r),
                    f"{rid} 误报自然口语: {t!r}",
                )

    def test_true_positive_on_ai_markers(self):
        by_id = {r["id"]: r for r in HR.BUILTIN_RULES}
        cases = {
            "builtin-qc-disclaimer": ("作为一个AI，我无法回答。", "作为语言模型，我的回答是……"),
            "builtin-qc-grandiose": ("这具有深远的意义。", "这标志着新时代的开始。"),
            "builtin-qc-enumeration": ("首先，我们需要明确目标；其次，制定方案；最后，执行。",),
            "builtin-qc-double-dash": ("—— 这是重点 —— 另一处 —— 又一处 ——",),
        }
        for rid, texts in cases.items():
            r = by_id[rid]
            for t in texts:
                self.assertTrue(HR._qc_violation(t, r), f"{rid} 漏检 AI 痕迹: {t!r}")

    def test_fake_alternative_not_shipped(self):
        """「假想对立面」刻意未收录（中文无法正则高置信区分），不得回归。"""
        self.assertNotIn(
            "builtin-qc-fake-alternative", {r["id"] for r in HR.BUILTIN_RULES}
        )


if __name__ == "__main__":
    unittest.main()
