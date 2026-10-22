# -*- coding: utf-8 -*-
"""v3.7.0 时间流逝增强接线的源码契约测试（AST，不 import main.py）。

钉七条契约（main.py + time_flow.py + state.py）：
1. _inject_life_context 用 mark_as_temp 注入时间块（带 AttributeError 降级）；
2. _track_activity 内时间衰减（emotion_decay_time）先于逐条衰减（emotion_decay），
   且写回比较基线是内存原状态（baseline）——防时间衰减结果被"无变化"跳过；
3. _emotion_directive_for 接重逢组合指令（reunion_inject 开关守卫）；
4. _time_context_block 把 calendar_line / days_line 传进 build_state_block；
5. 首见持久化：_init_time_stores 读 first_seen、两个落盘点同步收缩；
6. time_flow.build_state_block 签名含 calendar_line/days_line（默认空串）；
7. state.TimeStateStore 具备 load_first_seen（v2 兼容层）。
"""

import ast
import os
import unittest
import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ast_helpers import parse_main as _parse, find_func as _find_func  # noqa: E402

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse_file(relpath):
    with open(os.path.join(_PLUGIN_ROOT, relpath), encoding="utf-8") as f:
        return ast.parse(f.read())


def _call_lineno(func, name):
    """func 体内名为 name 的调用行号；找不到返回 None（ast.walk 是 BFS，
    断言先后只能用 lineno，见 test_emotion_wiring.py 顶部注释）。"""
    for n in ast.walk(func):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == name
        ):
            return n.lineno
    return None


class TestMarkAsTemp(unittest.TestCase):
    def test_inject_life_context_uses_mark_as_temp(self):
        func = _find_func(_parse(), "_inject_life_context")
        src = ast.dump(func)
        self.assertIn("mark_as_temp", src, "时间块必须 mark_as_temp（不进持久化历史）")
        self.assertIn(
            "AttributeError", src, "必须有旧框架降级（无 mark_as_temp 时回退常驻注入）"
        )


class TestEmotionTimeDecayWiring(unittest.TestCase):
    def test_time_decay_before_message_decay(self):
        """v4.0 Phase 6：顺序下沉纯函数 emotion.decay_and_soothe。

        契约不回归：时间衰减（decay_time）必须先于逐条衰减（decay）。
        """
        tree = _parse_file(os.path.join("humanizer_core", "emotion.py"))
        func = None
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == "decay_and_soothe":
                func = n
                break
        self.assertIsNotNone(func, "emotion.py 缺 decay_and_soothe")
        t_lineno = _call_lineno(func, "decay_time_raw")
        m_lineno = _call_lineno(func, "decay_raw")
        self.assertIsNotNone(t_lineno, "decay_and_soothe 缺时间衰减调用")
        self.assertIsNotNone(m_lineno, "decay_and_soothe 缺逐条衰减调用")
        self.assertLess(
            t_lineno, m_lineno, "时间衰减必须先于逐条衰减（先随时间淡去、再随聊天消散）"
        )

    def test_baseline_comparison_not_decayed_old(self):
        func = _find_func(_parse(), "_track_activity")
        src = ast.dump(func)
        self.assertIn(
            "baseline", src, "写回比较基线必须是内存原状态 baseline"
        )
        self.assertIn(
            'emotion_time_half_life_hours',
            src,
            "时间半衰期必须可配置",
        )


class TestReunionWiring(unittest.TestCase):
    def test_emotion_directive_uses_reunion(self):
        func = _find_func(_parse(), "_emotion_directive_for")
        src = ast.dump(func)
        self.assertIn("reunion_directive", src, "必须优先尝试重逢组合指令")
        self.assertIn(
            "emotion_reunion_inject", src, "重逢指令必须有配置开关"
        )
        self.assertIn(
            "continuity_label", src, "重逢档位必须与连续性分档同源"
        )


class TestTimeContextBlockWiring(unittest.TestCase):
    def test_block_passes_new_lines(self):
        func = _find_func(_parse(), "_time_context_block")
        src = ast.dump(func)
        self.assertIn("calendar_line", src, "必须组装历法行")
        self.assertIn("days_line", src, "必须组装相识天数行")

    def test_helper_calendar_line_cached(self):
        func = _find_func(_parse(), "_calendar_line_cached")
        src = ast.dump(func)
        self.assertIn("build_calendar_line", src)
        self.assertIn("DEFAULT_SENSITIVE_KEYWORDS", src, "敏感词表必须内置+可追加")
        self.assertIn("include_calendar", src, "必须有 include_calendar 开关")

    def test_helper_days_line_for(self):
        func = _find_func(_parse(), "_days_line_for")
        src = ast.dump(func)
        self.assertIn("include_first_seen", src, "相识天数默认必须可关")


class TestFirstSeenPersistence(unittest.TestCase):
    def test_init_loads_first_seen(self):
        func = _find_func(_parse(), "_init_time_stores")
        src = ast.dump(func)
        self.assertIn("load_first_seen", src, "启动必须加载 first_seen")

    def test_both_flush_paths_prune_first_seen(self):
        for name in ("_time_flush_loop", "_flush_time_state"):
            func = _find_func(_parse(), name)
            src = ast.dump(func)
            self.assertIn(
                "_first_seen", src, f"{name} 落盘必须带 first_seen（同步收缩）"
            )


class TestPureModuleContracts(unittest.TestCase):
    def test_build_state_block_signature(self):
        tree = _parse_file(os.path.join("humanizer_core", "time_flow.py"))
        func = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "build_state_block"
        )
        args = [a.arg for a in func.args.args]
        self.assertIn("calendar_line", args)
        self.assertIn("days_line", args)

    def test_time_state_store_has_load_first_seen(self):
        tree = _parse_file(os.path.join("humanizer_core", "state.py"))
        names = {
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
        }
        self.assertIn("load_first_seen", names)


if __name__ == "__main__":
    unittest.main()


class TestAuditTimeoutWiring(unittest.TestCase):
    """2026-09-07 审查修复（P1/P2）：剩余两处 LLM/检索调用必须 wait_for 包裹。

    v3.4.5 事故同型：无超时的供应商调用挂起 → 钩子/命令永久卡死。
    """

    def test_retrieve_wrapped_in_wait_for(self):
        # v4.0 Phase 4：wait_for 编排下沉 style_core.retrieve.retrieve_section
        # （超时/扁平化语义行为契约在 tests/test_kb_retrieve_section.py）；
        # 此处钉 main 入口仍委托下沉实现 + 超时可配 + 调用链经助手。
        func = _find_func(_parse(), "_kb_retrieve_section")
        src = ast.dump(func)
        self.assertIn("retrieve_section", src, "检索必须委托下游编排")
        caller = _find_func(_parse(), "_retrieve_examples")
        csrc = ast.dump(caller)
        self.assertIn("retrieval_timeout", csrc, "超时必须可配置")
        self.assertIn("_kb_retrieve_section", csrc, "_retrieve_examples 必须经助手检索")

    def test_profile_llm_wrapped_in_wait_for(self):
        # v4.0 Phase 3：提炼调用超时下沉 invoke_llm（恒正超时内包 wait_for，
        # 行为在 tests/test_llm_calls.py 钉死）；站点必须传 extract_timeout
        # 且非正值回 120 的兜底仍在（保证传给 invoke_llm 的超时恒为正）。
        func = _find_func(_parse(), "_call_llm_for_profile")
        src = ast.dump(func)
        self.assertIn("invoke_llm", src, "提炼 llm_generate 必须经带超时的 invoke_llm")
        self.assertIn("extract_timeout", src, "超时必须可配置")
        self.assertIn("120", src, "非法/非正超时必须回 120（v3.7.0 事故同型防护）")


class TestSplitFailureGuardWiring(unittest.TestCase):
    """2026-09-07 审查修复（P3）：分段 send 逐段防护 + 失败回填。"""

    def test_split_send_has_per_bubble_guard(self):
        func = _find_func(_parse(), "_split_send_bubbles")
        src = ast.dump(func)
        self.assertIn("failed_at", src, "必须记录首个失败段下标")
        # 回填必须发生在清链之后（回填=对 result.chain 再赋值）
        assigns = [
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Assign)
            and isinstance(n.targets[0], ast.Attribute)
            and n.targets[0].attr == "chain"
        ]
        self.assertGreaterEqual(len(assigns), 2, "清链后必须有回填赋值路径")
