# -*- coding: utf-8 -*-
"""v4.0.0 波 1 功能验证（区别于单测：验证"实际运行行为"）。

三块：
1. 时段体系时间轴全扫描 + 重排收敛模拟——把 main._proactive_loop 的
   "gate 判定 → 分支重排"算法镜像下来，在多配置×多天×素数步长的时间轴上
   断言三性质：放行时刻必同时满足"非勿扰且在活跃窗口"、被拦时刻的重排
   严格前进且 ≤3 跳收敛到放行区、永不悬挂。
2. 规则库升级持久化往返——legacy v1 文件经真实 load→migrate→save→load
   全链后 severity 稳定、version 升 2（防"内存对、盘上错"）。
3. （宿主门控）真 main.HumanizerPlugin._rules_inject_text / _inject_rules_tail
   绑定假 self 实跑：轮换确定性、渲染封顶、TextPart 贴尾 + _no_save、
   旧框架回退 system_prompt。加载用 importlib 按路径显式加载（AstrBot 安装
   根有同名 main.py，禁直接 import——见 test_split_send_flow 头注）。
"""

import importlib.util
import json
import os
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from humanizer_core import humaneness_rules as HR
from humanizer_core.proactive import (
    in_active_window,
    in_quiet,
    next_active_start,
    next_quiet_end,
)

# ---------------------------------------------------------------- 纯函数部分


def _mirror_reschedule(now: datetime, quiet: str, active: str, grace: int = 300):
    """镜像 main._proactive_loop 的重排分支（勿扰→next_quiet_end；否则活跃起点），
    并加与生产一致的宽限（q_end.timestamp() + max(grace*60, 60)，最短 60 秒——
    该缓冲正是用来越过闭区间结束边界的，漏加会在 07:00:00 整点死循环）。

    生产代码该分支在 1900-1923 行；此处按同序复制——若生产改动此处须同步。
    """
    if in_quiet(now, quiet):
        qe = next_quiet_end(now, quiet)
    else:
        qe = next_active_start(now, active)
    if qe is None:
        return None
    return qe + timedelta(seconds=max(grace * 60, 60))


def _gate_blocked(now: datetime, quiet: str, active: str) -> bool:
    """镜像生产闸门：勿扰内 或 不在活跃窗口 → 拦下。"""
    return in_quiet(now, quiet) or not in_active_window(now, active)


class TestTimelineSweep(unittest.TestCase):
    """时间轴全扫描：gate 与重排的联合性质。"""

    CONFIGS = (
        # (quiet, active, 起始日(周一), 天数, 步长分钟, 说明)
        ("23:00-07:00", "mon-fri 09:00-22:00", datetime(2026, 9, 7), 14, 37,
         "跨天勿扰 × 工作日活跃"),
        ("0-4 01:00-07:00, sat+sun 02:00-12:00", "09:00-23:00",
         datetime(2026, 9, 9), 10, 23, "数字星期多段勿扰 × 每日活跃"),
        ("01:00-07:00", "", datetime(2026, 9, 7), 7, 41,
         "仅勿扰（活跃空=不限制，旧行为）"),
    )

    def test_sweep_gate_and_convergence(self):
        for quiet, active, start, days, step, label in self.CONFIGS:
            with self.subTest(config=label):
                blocked_cnt = allowed_cnt = 0
                t = start
                end = start + timedelta(days=days)
                while t < end:
                    if _gate_blocked(t, quiet, active):
                        blocked_cnt += 1
                        # 放行时刻必不与"两闸任一拦截"矛盾（恒等式自检）
                        if in_quiet(t, quiet) and not in_active_window(t, active):
                            pass  # 双拦：任一分支都合法
                        # 收敛模拟：镜像生产重排，≤3 跳必须进入放行区
                        cur = t
                        hops = 0
                        while _gate_blocked(cur, quiet, active) and hops < 8:
                            nxt = _mirror_reschedule(cur, quiet, active)
                            self.assertIsNotNone(
                                nxt,
                                f"被拦时刻 {t} 的重排目标不得为 None（会悬挂）: {label}",
                            )
                            self.assertGreater(
                                nxt, cur, f"重排必须严格前进: {t} → {nxt}"
                            )
                            cur = nxt
                            hops += 1
                        self.assertLessEqual(
                            hops, 3,
                            f"{t} 需 {hops} 跳才收敛（>3 说明重排策略有问题）: {label}",
                        )
                        self.assertFalse(
                            _gate_blocked(cur, quiet, active),
                            f"{t} 重排 {hops} 跳到 {cur} 仍被拦: {label}",
                        )
                    else:
                        allowed_cnt += 1
                        self.assertFalse(in_quiet(t, quiet))
                        self.assertTrue(in_active_window(t, active))
                    t += timedelta(minutes=step)
                # 扫描必须两种时刻都覆盖到（防步长/配置退化成全拦或全放）
                self.assertGreater(blocked_cnt, 0, f"{label} 扫描未覆盖被拦时刻")
                self.assertGreater(allowed_cnt, 0, f"{label} 扫描未覆盖放行时刻")

    def test_legacy_no_active_behavior_unchanged(self):
        """active_hours 为空时，闸门行为必须与 v3.9.5 完全一致（只有勿扰）。"""
        quiet = "01:00-07:00"
        for h in range(24):
            t = datetime(2026, 9, 7, h, 30)
            self.assertEqual(
                _gate_blocked(t, quiet, ""),
                in_quiet(t, quiet),
                f"{h}:30 空活跃配置下闸门应只由勿扰决定",
            )


class TestUpgradePersistenceRoundTrip(unittest.TestCase):
    """升级持久化往返：内存对的，盘上也要对。"""

    def test_legacy_save_reload_stable(self):
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
            ]}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(legacy, f, ensure_ascii=False)

            # 第一次启动：load → migrate → save（与 main._init_time_stores 同序）
            rules, added = HR.migrate_builtins(HR.load_rules(path))
            self.assertEqual(added, len(HR.BUILTIN_RULES) - 2)
            HR.save_rules(path, rules)

            # 盘上直接断言：version 升 2
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            self.assertEqual(raw.get("version"), HR.RULES_VERSION)

            # 重启模拟：再 load → migrate，severity 不漂移、幂等
            again, added2 = HR.migrate_builtins(HR.load_rules(path))
            self.assertEqual(added2, 0)
            canon = {r["id"]: r["severity"] for r in HR.BUILTIN_RULES}
            for r in again:
                if r.get("builtin"):
                    self.assertEqual(r["severity"], canon[r["id"]], r["id"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestQcInstructionFunctional(unittest.TestCase):
    """QC 指令端到端内容（命中名 + 终检段 + 空违规不带终检）。"""

    def test_full_instruction_shape(self):
        text = "作为一个AI，我无法回答。"
        violated = HR.qc_violations(text, HR.BUILTIN_RULES)
        self.assertTrue(any(r["id"] == "builtin-qc-disclaimer" for r in violated))
        ins = HR.render_qc_instruction(violated)
        self.assertIn("必须去除的内容", ins)
        self.assertIn("自称AI命中检查", ins)
        self.assertIn("最易复活", ins)
        # 终检五条齐全
        for token in ("不是X而是Y", "单句断言", "破折号", "三连排比", "加粗"):
            self.assertIn(token, ins)


# ---------------------------------------------------------------- 宿主部分

try:
    _HOST = Path(sys.executable).resolve().parents[2]
    if (_HOST / "astrbot").is_dir() and str(_HOST) not in sys.path:
        sys.path.append(str(_HOST))
except Exception:  # noqa: BLE001
    pass

_spec = None
try:
    _spec = importlib.util.spec_from_file_location(
        "humanizer_plugin_main_audit", _ROOT / "main.py"
    )
    _main = importlib.util.module_from_spec(_spec)
    sys.modules["humanizer_plugin_main_audit"] = _main
    _spec.loader.exec_module(_main)
    HAS_HOST = True
except Exception:  # noqa: BLE001
    HAS_HOST = False


@unittest.skipUnless(HAS_HOST, "需要宿主 venv（astrbot 包）")
class TestRulesInjectFunctional(unittest.TestCase):
    """真 main.HumanizerPlugin._rules_inject_text 实跑（假 self + 真规则库）。"""

    def setUp(self):
        self.h = types.SimpleNamespace()
        self.h._humaneness_rules = list(HR.BUILTIN_RULES)
        self.h._rules_rotate_offset = 0
        self.h._rh = lambda key, default=None: True
        self.m = types.MethodType(_main.HumanizerPlugin._rules_inject_text, self.h)

    def test_rotation_matches_pure_model_exactly(self):
        """真方法逐请求输出必须与纯函数模型（offset 递增）逐字一致。"""
        canon = {r["id"]: r["severity"] for r in HR.BUILTIN_RULES}
        for off in range(5):
            got = self.m()
            expect = HR.render_inject_section(
                HR.select_inject_subset(self.h._humaneness_rules, off)
            )
            self.assertEqual(got, expect, f"offset={off} 真方法与模型不一致")
            self.assertNotIn("未载入", got)
            self.assertLessEqual(got.count("- "), HR.INJECT_MAX_RULES)
        self.assertEqual(self.h._rules_rotate_offset, 5, "游标必须逐请求自增")

    def test_s3_flavor_rotates_across_calls(self):
        s3_ids = [r["id"] for r in HR.BUILTIN_RULES
                  if r["type"] == "inject" and canon_sev(r) == "S3"]
        self.assertGreaterEqual(len(s3_ids), 3, "前置：S3 池须 ≥3 条才有轮换意义")
        seen = set()
        for _ in range(len(s3_ids) + 1):
            got = self.m()
            for rid in s3_ids:
                marker = _content_head(rid)
                if marker and marker in got:
                    seen.add(rid)
        self.assertEqual(seen, set(s3_ids), "轮换须在多次调用中覆盖全部 S3 风味")

    def test_disabled_returns_empty_and_no_offset_advance(self):
        self.h._rh = lambda key, default=None: False
        before = self.h._rules_rotate_offset
        self.assertEqual(self.m(), "")
        self.assertEqual(self.h._rules_rotate_offset, before, "关闭态不得推进游标")

    def test_empty_pool_returns_empty(self):
        self.h._humaneness_rules = []
        self.assertEqual(self.m(), "")


@unittest.skipUnless(HAS_HOST, "需要宿主 venv（astrbot 包）")
class TestEventStreamDashboardFunctional(unittest.TestCase):
    """v3.9.6（并入 v4.0.0）事件流与仪表盘的真方法实跑。"""

    def _make(self):
        h = types.SimpleNamespace()
        h._events_ring = __import__("collections").deque(maxlen=80)
        h._stats = {"rules_hit": 0}
        h._state_dirty = False
        h._p_int = lambda key, default: default
        h._time = lambda key, default: default
        h._prev_seen = {"umo-1": __import__("time").time() - 600}
        h._emotions = {"umo-1": {"emotion": "appy", "intensity": 0.5, "ts": 1}}
        h._next_trigger_ts = {"umo-1": __import__("time").time() + 3600}
        h._push_event = types.MethodType(_main.HumanizerPlugin._push_event, h)
        h._bump = types.MethodType(_main.HumanizerPlugin._bump_stats, h)
        h._dash = types.MethodType(_main.HumanizerPlugin.web_dashboard, h)
        h._EVENT_LABELS = _main.HumanizerPlugin._EVENT_LABELS  # 真实例经类属性取得
        return h

    def test_push_event_ring(self):
        h = self._make()
        for i in range(90):
            h._push_event("测试", f"事件{i}")
        ring = list(h._events_ring)
        self.assertEqual(len(ring), 80, "环形缓冲封顶 80")
        self.assertEqual(ring[-1]["msg"], "事件89", "最新事件在尾部")
        self.assertEqual(ring[0]["msg"], "事件10", "最旧事件被挤出")

    def test_bump_stats_pushes_labeled_event(self):
        h = self._make()
        h._bump("rules_hit")
        self.assertEqual(h._stats["rules_hit"], 1)
        self.assertEqual(len(h._events_ring), 1)
        self.assertEqual(h._events_ring[0]["tag"], "去痕")
        # 未登记标签的 key 不产生事件
        h._bump("unknown_key")
        self.assertEqual(len(h._events_ring), 1)

    def test_bump_on_foreign_self_without_ring_is_safe(self):
        """_push_event 的 try/except 必须吞掉缺 _events_ring 的假 self——
        既有 stats 测试的 fake self 没有 ring，不得因此炸测试。"""
        h = types.SimpleNamespace()
        h._stats = {"rules_hit": 0}
        h._state_dirty = False
        h._bump = types.MethodType(_main.HumanizerPlugin._bump_stats, h)
        h._bump("rules_hit")  # 不抛异常即通过
        self.assertEqual(h._stats["rules_hit"], 1)

    def test_dashboard_shape(self):
        h = self._make()
        h._push_event("测试", "你好")
        d = h._dash()
        self.assertIn("rhythm", d)
        self.assertIn("mode", d["rhythm"])
        self.assertEqual(d["emotions"][0]["emotion"], "appy")
        self.assertIsNotNone(d["next_proactive"])
        self.assertEqual(len(d["events"]), 1)
        self.assertEqual(d["events"][0]["msg"], "你好")


@unittest.skipUnless(HAS_HOST, "需要宿主 venv（astrbot 包）")
class TestRulesTailFunctional(unittest.TestCase):
    """真 _inject_rules_tail 实跑：贴尾 + _no_save + 旧框架回退。"""

    def _bound(self):
        h = types.SimpleNamespace()
        return types.MethodType(_main.HumanizerPlugin._inject_rules_tail, h)

    def test_parts_present_textpart_with_no_save(self):
        m = self._bound()
        req = types.SimpleNamespace(system_prompt="keep", extra_user_content_parts=[])
        text = "【真人感规则】测试规则段"
        m(req, text)
        self.assertEqual(len(req.extra_user_content_parts), 1)
        part = req.extra_user_content_parts[0]
        self.assertEqual(type(part).__name__, "TextPart")
        self.assertEqual(part.text, text)
        self.assertTrue(
            getattr(part, "_no_save", False), "mark_as_temp 必须生效（不进历史）"
        )
        self.assertEqual(req.system_prompt, "keep", "贴尾路径不得污染 system_prompt")

    def test_parts_none_falls_back_to_system_prompt(self):
        m = self._bound()
        req = types.SimpleNamespace(system_prompt="keep")  # 无 parts 属性（旧框架）
        text = "【真人感规则】旧框架规则段"
        m(req, text)
        self.assertIn("keep", req.system_prompt)
        self.assertIn(text, req.system_prompt)


# ---------------------------------------------------------------- 工具

def canon_sev(rule: dict) -> str:
    return str(rule.get("severity") or HR.DEFAULT_SEVERITY).upper()


def _content_head(rid: str) -> str:
    """取内置规则 content 的前 12 字作渲染文本中的锚（_clip 不超过它）。"""
    for r in HR.BUILTIN_RULES:
        if r["id"] == rid:
            return r["content"][:12]
    return ""


if __name__ == "__main__":
    unittest.main()
