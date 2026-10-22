# -*- coding: utf-8 -*-
"""v4.0 Phase 6：LangMirrorState 采集/剪枝/载入行为契约。

钉死 v3.9.1 采集语义与 v3.9.5「剪枝回写内存」修复：
- observe 受 lang_mirror_enable 守卫，粗口过滤透传；
- prune 原地回写 profiles（别名对象标识稳定，不重新赋值）；
- load 缺失/损坏按空表、只收 dict 型项、对象标识稳定。
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from services.lang_service import LangMirrorState  # noqa: E402


def _state(config=None, **kw):
    return LangMirrorState(
        config_getter=lambda k, d=None: (config or {}).get(k, d),
        clock=lambda: 1_000_000.0,
        **kw,
    )


class TestObserve(unittest.TestCase):
    def test_observe_accumulates(self):
        st = _state({"lang_mirror_enable": True})
        self.assertTrue(st.observe("u1", "哈哈 绝了"))
        self.assertTrue(st.observe("u1", "今天好累啊"))
        self.assertEqual(st.profiles["u1"]["msg_count"], 2)

    def test_observe_disabled_noop(self):
        st = _state({"lang_mirror_enable": False})
        self.assertFalse(st.observe("u1", "哈哈"))
        self.assertNotIn("u1", st.profiles)

    def test_observe_profanity_filter_passthrough(self):
        seen = {}

        def fake_observe(profile, text, ts=0.0, profanity_filter=True):
            seen["profanity_filter"] = profanity_filter
            return dict(profile or {})

        st = _state(
            {"lang_mirror_enable": True, "lang_mirror_profanity_filter": False},
            observe_fn=fake_observe,
        )
        st.observe("u1", "x")
        self.assertFalse(seen["profanity_filter"])

    def test_observe_swallows_exception(self):
        def boom(*_a, **_k):
            raise RuntimeError("x")

        st = _state({"lang_mirror_enable": True}, observe_fn=boom)
        self.assertFalse(st.observe("u1", "x"))  # 不得抛出


class TestPrune(unittest.TestCase):
    def test_prune_in_place_keeps_identity(self):
        st = _state()
        st.profiles["a"] = {"msg_count": 5, "ts": 1_000_000.0}
        st.profiles["b"] = {"msg_count": 5, "ts": 1_000_000.0 - 40 * 86400}
        alias = st.profiles
        payload = st.prune()
        self.assertIs(st.profiles, alias, "必须原地回写，别名对象标识稳定")
        self.assertEqual(set(st.profiles), {"a"}, "陈旧画像必须回写内存剔除")
        self.assertEqual(set(payload), {"a"})

    def test_prune_no_stale_keeps_items(self):
        st = _state()
        st.profiles["a"] = {"msg_count": 5, "ts": 1_000_000.0}
        st.prune()
        self.assertIn("a", st.profiles)

    def test_prune_payload_is_copy(self):
        st = _state()
        st.profiles["a"] = {"msg_count": 5, "ts": 1_000_000.0}
        payload = st.prune()
        payload["injected"] = {}
        self.assertNotIn("injected", st.profiles, "落盘快照必须是副本")


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lang_profile.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_valid_and_identity(self):
        self.path.write_text(
            json.dumps({"version": 1, "profiles": {"u1": {"msg_count": 3}}}),
            encoding="utf-8",
        )
        st = _state(store_path=self.path)
        alias = st.profiles
        st.load()
        self.assertIs(st.profiles, alias, "load 必须原地更新，别名不悬空")
        self.assertEqual(st.profiles, {"u1": {"msg_count": 3}})

    def test_load_filters_non_dict(self):
        self.path.write_text(
            json.dumps({"profiles": {"u1": {"msg_count": 1}, "bad": 5}}),
            encoding="utf-8",
        )
        st = _state(store_path=self.path)
        st.load()
        self.assertEqual(set(st.profiles), {"u1"})

    def test_load_missing_is_empty(self):
        st = _state(store_path=self.path)
        st.load()
        self.assertEqual(st.profiles, {})

    def test_load_corrupt_is_empty(self):
        self.path.write_text("{not json", encoding="utf-8")
        st = _state(store_path=self.path)
        st.load()
        self.assertEqual(st.profiles, {})


if __name__ == "__main__":
    unittest.main()
