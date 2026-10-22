# -*- coding: utf-8 -*-
"""v3.5.1 情绪惯性引擎接线的源码契约测试（AST，不 import main.py）。

钉四条接线契约（main.py）：
1. sulky 喂点在 _bump_unanswered 内，且以 proactive_pout_on_unanswered
   （用户决策：生气可选，默认关）+ emotion_enable 双开关守卫；
2. 衰减+安抚在 _track_activity 内（decay 先、安抚后）；
3. on_llm_request 注入情绪指令行（emotion_enable 守卫在
   _emotion_directive_for 内、cron 跳过）；
4. 深度改写链 _rewrite_once 接收 state_line 并拼进 system_prompt /
   prompt 两分支（用户决策：情绪+节奏一起同步，防改写洗掉状态）；
5. persona_state.json 持久化：30s 刷盘循环与 terminate 路径都接
   _persona_store.save + prune。
"""

import ast
import os
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func

_MAIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"
)
_SERVICE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "services",
    "proactive_state.py",
)


def _parse_service():
    with open(_SERVICE, encoding="utf-8") as f:
        return ast.parse(f.read(), filename=_SERVICE)


def _find_service_func(name):
    for node in ast.walk(_parse_service()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"services/proactive_state.py 缺函数 {name}")


_EMOTION_MODULE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "humanizer_core",
    "emotion.py",
)


def _find_emotion_func(name):
    with open(_EMOTION_MODULE, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=_EMOTION_MODULE)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"humanizer_core/emotion.py 缺函数 {name}")


def _call_names(node):
    return [
        sub.func.attr if isinstance(sub.func, ast.Attribute) else getattr(sub.func, "id", "")
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call)
    ]


def _dumps(node):
    return ast.dump(node)


def _subscript_root_attr(node):
    """取下标表达式 `self._xxx[umo]` 的根属性名（_xxx）；不匹配返回空串。"""
    if not isinstance(node, ast.Subscript):
        return ""
    cur = node.value
    while isinstance(cur, ast.Attribute):
        if isinstance(cur.value, ast.Name):
            return cur.attr
        cur = cur.value
    return getattr(cur, "id", "")


# ⚠️ ast.walk 是广度优先遍历，返回顺序 ≠ 源码顺序；断言"谁先谁后"必须用
# node.lineno（行号）。此前用 walk 序号比较产生过两起假失败（源码实际正确）。


class TestSulkyFeed(unittest.TestCase):
    def test_feed_in_bump_unanswered(self):
        """v4.0 Phase 6：喂点下沉 ProactiveState.feed_sulky（双开关守卫仍钉死）。

        main._bump_unanswered 只负责编排——必须调用状态容器的 feed_sulky；
        总闸（proactive_pout_on_unanswered 生气可选 + emotion_enable）钉在
        服务源码上，强度不减。
        """
        func = _find_func(_parse(), "_bump_unanswered")
        src = _dumps(func)
        self.assertIn("feed_sulky", src, "_bump_unanswered 必须触发 sulky 喂点")
        feed = _find_service_func("feed_sulky")
        fsrc = _dumps(feed)
        self.assertIn("proactive_pout_on_unanswered", fsrc,
                      "sulky 总闸必须是 proactive_pout_on_unanswered（生气可选）")
        self.assertIn("emotion_enable", fsrc, "必须再受 emotion_enable 守卫")
        self.assertIn("_sulky_feed", fsrc, "喂点必须走可注入端口")

    def test_feed_after_unanswered_increment(self):
        """喂点必须在未回复计数递增之后（先有事件、后有情绪）。

        v4.0 Phase 6：递增在服务 bump_unanswered、喂点在服务 feed_sulky；
        main 内的调用顺序（bump_unanswered → feed_sulky）即源码序契约。
        """
        func = _find_func(_parse(), "_bump_unanswered")
        bump_lineno = next(
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "bump_unanswered"
        )
        feed_lineno = next(
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "feed_sulky"
        )
        self.assertLess(
            bump_lineno, feed_lineno, "feed_sulky 必须在计数递增之后（按行号）"
        )


class TestDecayAndSoothe(unittest.TestCase):
    def test_in_track_activity(self):
        """v4.0 Phase 6：衰减+安抚下沉纯函数 emotion.decay_and_soothe。

        _track_activity 仍必须触发该推进（传 text 与可配置安抚词），
        纯函数内保留逐条衰减/安抚检测/转 appy 三要素。
        """
        func = _find_func(_parse(), "_track_activity")
        src = _dumps(func)
        self.assertIn("decay_and_soothe", src, "_track_activity 必须触发情绪推进")
        self.assertIn("emotion_soothe_words", src, "安抚词必须可配置")
        pure = _find_emotion_func("decay_and_soothe")
        psrc = _dumps(pure)
        self.assertIn("decay", psrc, "必须逐条衰减")
        self.assertIn("hit_soothe", psrc, "必须检测安抚词")
        self.assertIn("bump_appy", psrc, "安抚命中必须转 appy")

    def test_decay_before_soothe(self):
        """v4.1.0 顺序契约（三段）：逐条衰减 → 热度漂移 → 安抚命中。

        衰减在先、安抚在后——冷却中的安抚依然能被感知；热度漂移居中——
        安抚保持在最后，明说的好话总能赢下基调（按行号比源码序）。
        v4.1.0 起逐条衰减改走无地板的 decay_raw()（组合链内不判地板，
        否则漂移增量被清零吞掉；decay() 单独调用的地板契约不变），锚点随之迁移。
        """
        func = _find_emotion_func("decay_and_soothe")
        decay_lineno = next(
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "decay_raw"
        )
        drift_lineno = next(
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "heat_drift"
        )
        appy_lineno = next(
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "bump_appy"
        )
        self.assertLess(decay_lineno, drift_lineno, "必须先衰减后漂移（按行号）")
        self.assertLess(drift_lineno, appy_lineno, "必须先漂移后安抚（按行号）")

    def test_first_contact_guard_in_pure_layer(self):
        """初见守卫钉在纯层：prev_seen_ts 缺失时 heat 按 warm 处理。"""
        func = _find_emotion_func("decay_and_soothe")
        src = _dumps(func)
        self.assertIn("prev_seen_ts", src, "decay_and_soothe 必须接收 prev_seen_ts")
        self.assertIn("warm", src, "守卫回落档必须是 warm（无漂移）")

    def test_heat_coupling_wired(self):
        """v4.1.0：_track_activity 必须把热度耦合进情绪推进。

        - decay_and_soothe 调用传 heat / prev_seen_ts / hot_drift / cold_drift；
        - 热度由 rhythm_heat 同源计算（第 2 参 snap.prev_seen，防恒 hot 契约
          由 test_rhythm_wiring::test_second_arg_is_prev_seen 全量覆盖）；
        - emotion_heat_drift_enable 开关守卫（默认开，可关）。
        """
        func = _find_func(_parse(), "_track_activity")
        calls = [
            n for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "decay_and_soothe"
        ]
        self.assertTrue(calls, "_track_activity 必须调用 decay_and_soothe")
        for call in calls:
            kw = {k.arg for k in call.keywords}
            for want in ("heat", "prev_seen_ts", "hot_drift", "cold_drift", "soothe_boost"):
                self.assertIn(want, kw, f"decay_and_soothe 调用缺 {want}= 参数")
        src = _dumps(func)
        self.assertIn("rhythm_heat", src, "热度必须经 rhythm_heat 同源计算")
        self.assertIn("emotion_heat_drift_enable", src, "热度耦合必须有独立开关")
        self.assertIn("_time_snapshot", src, "热度读取必须走 _time_snapshot 快照")
        # v4.1.0 审查强化：heat 变量的值必须就是 _track_activity 内的
        # rhythm_heat 调用结果（防"快照在别处、heat 传字面量"的字符串级假绿）
        heat_assigns = [
            n for n in ast.walk(func)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "heat" for t in n.targets)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "rhythm_heat"
        ]
        self.assertTrue(
            heat_assigns, "_track_activity 内 heat 必须由 rhythm_heat(...) 赋值"
        )

    def test_time_activity_handler_precedes_track_activity(self):
        """v4.1.0：_prev_seen 轮转 handler 必须先于情绪读点（同优先级按定义序）。

        _track_time_activity（轮转 _last_seen→_prev_seen）定义在 _track_activity
        （读 snap.prev_seen 计算热度）之前，是"热度=距上一条消息的间隔"语义
        的前提；若未来重构挪动定义顺序，本契约先红。
        """
        tree = _parse()
        time_lineno = _find_func(tree, "_track_time_activity").lineno
        track_lineno = _find_func(tree, "_track_activity").lineno
        self.assertLess(
            time_lineno, track_lineno,
            "_track_time_activity 必须定义在 _track_activity 之前"
            "（否则情绪热度读到的是 N-2 条消息的间隔）",
        )

    def test_schema_heat_keys(self):
        """schema：emotion 组四个耦合键与默认值（true / 0.2 / 0.10 / 0.2）。"""
        import json

        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "_conf_schema.json",
        )
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        items = schema["emotion"]["items"]
        self.assertTrue(items["emotion_heat_drift_enable"]["default"])
        self.assertAlmostEqual(items["emotion_hot_drift"]["default"], 0.2)
        self.assertAlmostEqual(items["emotion_cold_drift"]["default"], 0.10)
        self.assertAlmostEqual(items["emotion_soothe_boost"]["default"], 0.2)


class TestInjection(unittest.TestCase):
    def test_on_llm_request_injects_directive(self):
        func = _find_func(_parse(), "on_llm_request")
        src = _dumps(func)
        self.assertIn("_emotion_directive_for", src, "on_llm_request 必须注入情绪指令")

    def test_directive_helper_guards(self):
        func = _find_func(_parse(), "_emotion_directive_for")
        src = _dumps(func)
        self.assertIn("emotion_enable", src, "注入前必须检查 emotion_enable")
        self.assertIn("emotion_directive", src)
        # cron 跳过（主动消息自带 pout 通道）
        self.assertIn("cron", src, "cron 合成事件必须跳过情绪注入")

    def test_injection_independent_of_style_switch(self):
        """情绪注入必须在 style.enabled 早退之前（独立通道，与发送纪律同位）。

        按行号比较源码顺序（ast.walk 的 BFS 序号不可用于排序）。
        """
        func = _find_func(_parse(), "on_llm_request")
        emo_lineno = next(
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_emotion_directive_for"
        )
        gate_linenos = [
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.If)
            # ast.dump 渲染字符串常量为单引号（value='enabled'）
            and "_cfg" in _dumps(n.test) and "enabled" in _dumps(n.test)
            and any(isinstance(s, ast.Return) for s in ast.walk(n))
        ]
        self.assertTrue(gate_linenos, "on_llm_request 必须保留 style.enabled 早退")
        self.assertLess(
            emo_lineno, min(gate_linenos), "情绪注入必须在 enabled 早退之前（按行号）"
        )




class TestPersistence(unittest.TestCase):
    def test_store_init_and_load(self):
        # v4.0 Phase 1：persona 存储构建职责移入 StateStore facade——
        # 接线与文件名契约分别迁移至此与 tests/test_state_store.py
        # （DataPaths.persona_state == persona_state.json +
        #  store.persona 为 PersonaStateStore 的实例断言在那边钉死）。
        func = _find_func(_parse(), "_init_time_stores")
        src = _dumps(func)
        self.assertIn("StateStore", src, "存储器必须经 StateStore facade 构建")
        self.assertIn("_persona_store", src, "必须接线 persona 存储器")

    def test_flush_loop_saves_persona(self):
        func = _find_func(_parse(), "_time_flush_loop")
        src = _dumps(func)
        self.assertIn("_persona_dirty", src, "30s 循环必须检查情绪脏标记")
        self.assertIn("_persona_store", src)

    def test_terminate_flushes_persona(self):
        """terminate 走 _flush_time_state 无条件落盘——必须包含 persona。"""
        func = _find_func(_parse(), "_flush_time_state")
        src = _dumps(func)
        self.assertIn("_persona_store", src, "terminate 刷盘路径必须包含 persona_state")
        self.assertIn("prune", src, "落盘前必须 prune 陈旧会话")

    def test_cap_applied(self):
        """emotion_intensity_cap 必须被接线（_apply_cap 在两个喂点使用）。

        v4.0 Phase 6：sulky 喂点下沉后，cap 应用于新端口 `_feed_sulky_emotion`
        （由 main 注入 ProactiveState），appy 喂点仍在 _track_activity。
        """
        tree = _parse()
        cap_helper = _find_func(tree, "_apply_cap")
        self.assertIn("emotion_intensity_cap", _dumps(cap_helper))
        sulky = _find_func(tree, "_feed_sulky_emotion")
        track = _find_func(tree, "_track_activity")
        self.assertIn("_apply_cap", _dumps(sulky), "sulky 喂点必须过 cap")
        self.assertIn("_apply_cap", _dumps(track), "appy 喂点必须过 cap")
        # 端口接线：main 必须把 sulky 端口注入状态容器
        init_src = _dumps(_find_func(tree, "__init__"))
        self.assertIn("sulky_feed", init_src, "main 必须注入 sulky 喂点端口")


if __name__ == "__main__":
    unittest.main()
