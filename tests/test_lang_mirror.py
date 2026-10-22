# -*- coding: utf-8 -*-
"""v3.9.1 语言风格趋同测试：humanizer_core/lang_mirror.py 纯函数。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from humanizer_core import lang_mirror as LM


class TestObserve(unittest.TestCase):
    def test_accumulates_counts(self):
        p = LM.empty_profile()
        for t in ("哈哈 绝了", "今天好累啊", "绝了真的"):
            p = LM.observe(p, t, ts=1.0)
        self.assertEqual(p["msg_count"], 3)
        self.assertEqual(p["len_sum"], 5 + 5 + 4)
        self.assertGreaterEqual(p["laugh_msgs"], 1)
        self.assertEqual(p["ts"], 1.0)

    def test_empty_text_noop(self):
        p = LM.observe(LM.empty_profile(), "   ")
        self.assertEqual(p["msg_count"], 0)

    def test_emoji_and_tilde(self):
        p = LM.observe(LM.empty_profile(), "好耶~ [表情]")
        # 用包含 emoji 字符的样本验证
        p2 = LM.observe(LM.empty_profile(), "好耶\U0001F606~")
        self.assertEqual(p2["emoji_msgs"], 1)
        self.assertEqual(p2["tilde_msgs"], 1)

    def test_phrase_freq_threshold(self):
        p = LM.empty_profile()
        for _ in range(3):
            p = LM.observe(p, "绝了这个真的绝了")
        # 「绝了」出现 ≥3 次应入选；随机 2 字组合频次不足被清掉
        self.assertIn("绝了", p["phrase_freq"])
        self.assertLessEqual(len(p["phrase_freq"]), LM.PHRASE_STORE_LIMIT)

    def test_blocked_phrase_not_collected(self):
        p = LM.empty_profile()
        for _ in range(4):
            p = LM.observe(p, "傻逼玩意真是傻逼")
        self.assertNotIn("傻逼", p["phrase_freq"])
        self.assertTrue(all("傻逼" not in k for k in p["phrase_freq"]))

    def test_profanity_filter_off_collects(self):
        """过滤关闭后粗口口头禅照常采集（v3.9.1 用户偏好开关）。"""
        p = LM.empty_profile()
        for _ in range(4):
            p = LM.observe(p, "卧槽这绝了真卧槽", profanity_filter=False)
        # 「卧槽」非黑名单词此处本就应采集；用真黑名单成员验证开关语义：
        p2 = LM.empty_profile()
        for _ in range(4):
            p2 = LM.observe(p2, "这人真傻逼啊傻逼", profanity_filter=False)
        self.assertIn("傻逼", p2["phrase_freq"], "关过滤后黑名单词应可采集")
        # 对照：开过滤（默认）时不采集
        p3 = LM.empty_profile()
        for _ in range(4):
            p3 = LM.observe(p3, "这人真傻逼啊傻逼")
        self.assertNotIn("傻逼", p3["phrase_freq"])

    def test_profanity_off_still_filters_noise(self):
        """关过滤后数字/虚词噪音抑制仍生效（那是噪音不是内容审查）。"""
        p = LM.empty_profile()
        for _ in range(4):
            p = LM.observe(p, "23333 的了的了", profanity_filter=False)
        self.assertTrue(all(not (k.isdigit() or k.isascii()) for k in p["phrase_freq"]))

    def test_stopword_phrase_filtered(self):
        p = LM.empty_profile()
        for _ in range(4):
            p = LM.observe(p, "的是不是的是不是的")
        self.assertNotIn("的是", p["phrase_freq"])

    def test_no_mutation_of_input(self):
        src = LM.empty_profile()
        src["phrase_freq"] = {"绝了": 2}
        snap = dict(src["phrase_freq"])
        LM.observe(src, "绝了一次")
        self.assertEqual(src["phrase_freq"], snap, "输入画像不得被原地修改")

    def test_long_message_truncated(self):
        p = LM.observe(LM.empty_profile(), "啊" * 5000)
        self.assertEqual(p["len_sum"], LM.MAX_PROCESS_CHARS)


class TestConvergenceAndRender(unittest.TestCase):
    def _profile(self, n, **kw):
        p = LM.empty_profile()
        p["msg_count"] = n
        p["len_sum"] = n * 15
        p["phrase_freq"] = {"绝了": 5, "服了": 4}
        p.update(kw)
        return p

    def test_insufficient_msgs_empty(self):
        self.assertEqual(LM.build_lang_mirror_text(self._profile(10), min_msgs=30), "")

    def test_sufficient_renders(self):
        text = LM.build_lang_mirror_text(self._profile(50), min_msgs=30, topk=2)
        self.assertIn("【对方语言习惯】", text)
        self.assertIn("绝了", text)
        self.assertIn("15", text, text)

    def test_minimal_feature_set_suppressed(self):
        """只有长度一条事实（无短语/笑声/句尾特征，emoji 处于中性带）时不注入。"""
        p = self._profile(50)
        p["phrase_freq"] = {}
        p["laugh_msgs"] = 0
        p["emoji_msgs"] = 10  # 20%：处于 5%~30% 中性带，不产生 emoji 事实
        p["tilde_msgs"] = 0
        self.assertEqual(LM.build_lang_mirror_text(p, min_msgs=30), "")

    def test_topk_limits_phrases(self):
        p = self._profile(50)
        p["phrase_freq"] = {f"短语{i}": 9 - i for i in range(6)}
        text = LM.build_lang_mirror_text(p, min_msgs=30, topk=2)
        self.assertLessEqual(text.count("「"), 2)

    def test_emoji_low_is_reported(self):
        p = self._profile(50, emoji_msgs=1)
        text = LM.build_lang_mirror_text(p, min_msgs=30)
        self.assertIn("几乎不用 emoji", text)


class TestPrune(unittest.TestCase):
    def test_prune_by_ts(self):
        now = 1_000_000.0
        profiles = {
            "a": {"msg_count": 5, "ts": now},
            "b": {"msg_count": 5, "ts": now - 40 * 86400},
            "c": {"msg_count": 5},
        }
        out = LM.prune_profiles(profiles, now)
        self.assertEqual(set(out), {"a"})


if __name__ == "__main__":
    unittest.main()

import ast

_MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")


class TestWiring(unittest.TestCase):
    """v3.9.1 接线契约：采集点/注入点/存储刷盘（AST，不 import main.py）。"""

    @classmethod
    def setUpClass(cls):
        import ast as _ast
        with open(_MAIN, encoding="utf-8") as f:
            cls.tree = _ast.parse(f.read(), filename=_MAIN)

    def _func(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
        raise AssertionError(f"main.py 缺函数 {name}")

    def test_observe_in_track_activity(self):
        """采集必须在 _track_activity 内触发；enable 守卫在 LangMirrorState。"""
        func = self._func("_track_activity")
        src = ast.dump(func)
        self.assertIn("_lang_mirror", src, "_track_activity 必须经状态服务采集")
        self.assertIn("observe", src, "必须调用采集入口")
        # v4.0 Phase 6：lang_mirror_enable 守卫下沉服务 observe
        svc_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "services",
            "lang_service.py",
        )
        with open(svc_path, encoding="utf-8") as f:
            svc_src = f.read()
        self.assertIn("lang_mirror_enable", svc_src, "采集守卫必须仍在（服务侧）")

    def test_inject_in_on_llm_request_before_gate(self):
        """注入必须在 on_llm_request 内、style.enabled 早退之前。"""
        func = self._func("on_llm_request")
        src = ast.dump(func)
        self.assertIn("_lang_mirror_text", src)
        gate_lineno = min(
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.If)
            and "_cfg" in ast.dump(n.test)
            and "enabled" in ast.dump(n.test)
            and any(isinstance(s, ast.Return) for s in ast.walk(n))
        )
        call_lineno = min(
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_lang_mirror_text"
        )
        self.assertLess(call_lineno, gate_lineno, "语言趋同注入必须在 enabled 早退之前")

    def test_store_init_and_flush(self):
        init = ast.dump(self._func("_init_time_stores"))
        self.assertIn("lang_profile.json", init)
        flush = ast.dump(self._func("_time_flush_loop"))
        self.assertIn("_lang_dirty", flush)
        # v4.0 Phase 6：剪枝经状态服务（原地回写内存，见 test_v395_fixes）
        self.assertIn("_lang_mirror", flush)
        self.assertIn("prune", flush)


