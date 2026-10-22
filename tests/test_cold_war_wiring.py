# -*- coding: utf-8 -*-
"""v3.8.0 情绪深化接线的源码契约测试（AST，不 import main.py）。

钉三条契约：
1. _track_activity：分档半衰期（resolve_half_life_hours）在逐条衰减之前，
   分档参数可配置——时间衰减仍是第一道（v3.7.0 顺序契约不回归）；
2. _proactive_chat：弧线有 emotion_cold_war 开关守卫，且顶替（不叠加）
   按条数的 pout 块；
3. 弧线数据源是用户沉默时刻（_last_user_ts），非 Bot 自己的打点。
"""

import ast
import os
import sys as _sys
import unittest

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func  # noqa: E402


def _lineno(func, name):
    import ast

    for n in ast.walk(func):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name:
            return n.lineno
    return None


_EMOTION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "humanizer_core",
    "emotion.py",
)


def _find_emotion_func(name):
    import ast as _ast

    with open(_EMOTION, encoding="utf-8") as f:
        tree = _ast.parse(f.read(), filename=_EMOTION)
    for n in _ast.walk(tree):
        if isinstance(n, _ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError(f"emotion.py 缺函数 {name}")


class TestTieredDecayWiring(unittest.TestCase):
    def test_resolver_before_message_decay(self):
        """v4.0 Phase 6：时间衰减+逐条衰减顺序下沉纯函数 decay_and_soothe。

        顺序契约（v3.7.0 不回归）：分档半衰期解析 → 时间衰减 → 逐条衰减。
        """
        func = _find_emotion_func("decay_and_soothe")
        r = _lineno(func, "resolve_half_life_hours")
        t = _lineno(func, "decay_time_raw")
        m = _lineno(func, "decay_raw")
        self.assertIsNotNone(r, "缺分档半衰期解析")
        self.assertIsNotNone(t, "时间衰减调用丢失（v3.7.0 契约回归）")
        self.assertIsNotNone(m)
        self.assertLess(r, t, "半衰期必须先算后传给 decay_time")
        self.assertLess(t, m, "时间衰减必须先于逐条衰减")

    def test_tier_keys_configurable(self):
        """分档参数仍从配置读出（接线在 _track_activity 的 kwargs）。"""
        src = ast.dump(_find_func(_parse(), "_track_activity"))
        self.assertIn("emotion_absent_tier_days", src)
        self.assertIn("emotion_absent_half_life_hours", src)


_PROMPT_MODULE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "humanizer_core",
    "proactive_prompt.py",
)


def _find_prompt_func(name):
    import ast as _ast

    with open(_PROMPT_MODULE, encoding="utf-8") as f:
        tree = _ast.parse(f.read(), filename=_PROMPT_MODULE)
    for n in _ast.walk(tree):
        if isinstance(n, _ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError(f"proactive_prompt.py 缺函数 {name}")


class TestColdWarWiring(unittest.TestCase):
    def test_arc_guarded_and_replaces_pout(self):
        """v4.0 Phase 6：情绪块决策下沉 proactive_prompt.emotion_block。

        契约不回归：弧线有开关、用 cold_war_stage/cold_war_proactive_directive/
        可配阈值；优先级 弧线 > 追问 > pout（弧线命中即顶替 pout，同源情绪
        只发一版）。main._proactive_chat 只传参并拼接。
        """
        func = _find_prompt_func("emotion_block")
        src = ast.dump(func)
        self.assertIn("cold_war_enabled", src, "弧线必须有开关参数")
        self.assertIn("cold_war_stage", src)
        self.assertIn("cold_war_proactive_directive", src)
        self.assertIn("thresholds", src, "分档阈值必须可配")
        self.assertIn("arc_block", src)
        # 优先级：弧线命中即返回，pout 只在弧线为空后才可能
        self.assertIn("build_pout_directive", src)
        chat = ast.dump(_find_func(_parse(), "_proactive_chat"))
        self.assertIn("emotion_block", chat, "_proactive_chat 必须调用情绪块决策")
        self.assertIn("emotion_cold_war", chat, "弧线开关必须在接线点透传")

    def test_arc_reads_user_ts(self):
        """弧线数据源是用户沉默时刻（last_user_ts），不是 Bot 自己的打点。"""
        import ast as _ast

        func = _find_prompt_func("emotion_block")
        hit = False
        for n in _ast.walk(func):
            if (
                isinstance(n, _ast.Call)
                and isinstance(n.func, _ast.Name)
                and n.func.id == "cold_war_stage"
            ):
                # 首参必须是 last_user_ts（函数形参，来源由调用方保证）
                self.assertIsInstance(n.args[0], _ast.Name)
                self.assertEqual(n.args[0].id, "last_user_ts")
                hit = True
        self.assertTrue(hit, "未找到 cold_war_stage 调用")
        # 接线点：main._proactive_chat 必须把 _last_user_ts 的值作为 last_user_ts 传入
        chat = _find_func(_parse(), "_proactive_chat")
        # 数据源钉死：last_ts 的赋值来自 _last_user_ts（用户沉默时刻）
        found_source = False
        for n in _ast.walk(chat):
            if (
                isinstance(n, _ast.Assign)
                and any(isinstance(t, _ast.Name) and t.id == "last_ts" for t in n.targets)
            ):
                self.assertIn("_last_user_ts", _ast.dump(n.value))
                found_source = True
        self.assertTrue(found_source, "last_ts 必须来自用户最后发言打点")
        found_kw = False
        for n in _ast.walk(chat):
            if (
                isinstance(n, _ast.Call)
                and isinstance(n.func, _ast.Name)
                and n.func.id == "emotion_block"
            ):
                for kw in n.keywords:
                    if kw.arg == "last_user_ts":
                        self.assertIsInstance(kw.value, _ast.Name)
                        self.assertEqual(kw.value.id, "last_ts")
                        found_kw = True
        self.assertTrue(found_kw, "emotion_block 的 last_user_ts 必须接 last_ts 打点")


if __name__ == "__main__":
    unittest.main()
