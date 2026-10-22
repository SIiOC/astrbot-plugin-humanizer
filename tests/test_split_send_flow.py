# -*- coding: utf-8 -*-
"""v3.6.0 分段发送/连续性注入的行为级测试（真实插件方法 + 假事件 + 真消息链）。

与既有 AST 契约测试的区别：本文件在 venv（宿主环境）下 import 真实的
main.HumanizerPlugin 方法绑定到假 self 上跑完整链路，验证的是"实际可用"
而不是"源码形态"。无 astrbot 包的环境自动跳过（保持套件双环境可跑）。
"""

import asyncio
import os
import sys
import time
import types
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# 宿主根（AstrBot 安装目录）：venv 解释器位于 <宿主>/venv/Scripts，
# 源码版 astrbot 包在 <宿主>/astrbot。找不到则保持原样由 ImportError 触发跳过。
try:
    _HOST = Path(sys.executable).resolve().parents[2]
    if (_HOST / "astrbot").is_dir() and str(_HOST) not in sys.path:
        sys.path.append(str(_HOST))  # append：不得抢占插件目录的模块解析
except Exception:  # noqa: BLE001
    pass

# ⚠️ 不能 `import main`：AstrBot 安装根下恰有同名 main.py，sys.path 竞争会
# 解析到框架的入口文件（实测 4.27.4）。这里按文件路径显式加载插件主模块。
import importlib.util  # noqa: E402

try:
    _spec = importlib.util.spec_from_file_location(
        "humanizer_plugin_main", _ROOT / "main.py"
    )
    _main = importlib.util.module_from_spec(_spec)
    sys.modules["humanizer_plugin_main"] = _main
    _spec.loader.exec_module(_main)
    from astrbot.core.message.components import Plain  # noqa: E402,F401
    from astrbot.core.message.message_event_result import (  # noqa: E402,F401
        MessageChain,
        MessageEventResult,
    )

    HAS_HOST = True
except Exception:  # noqa: BLE001
    HAS_HOST = False

_LONG_TEXT = "今天在图书馆坐了一整天，腰都直不起来了，晚上回来还想再看看那本书，结果看着看着就睡着了，醒来已经十一点了。"


@unittest.skipUnless(HAS_HOST, "需要宿主 venv（astrbot 包）")
class _Harness(unittest.TestCase):
    """把真实方法绑到假 self；配置/状态用极简假实现。"""

    def setUp(self):
        self.cfg = {}
        self.stats = {}
        self.prev_seen = {}
        self.last_user_ts = {}
        self.h = types.SimpleNamespace()
        # 假访问器引用无下划线属性；主链方法（插件真方法）引用带下划线属性
        self.h.cfg = self.cfg
        self.h.stats = self.stats
        self.h.prev_seen = self.prev_seen
        self.h.last_user_ts = self.last_user_ts
        self.h._cfg = self.cfg
        self.h._stats = self.stats
        self.h._prev_seen = self.prev_seen
        self.h._last_user_ts = self.last_user_ts
        # v3.7.0：_time_context_block 新依赖（历法行/相识天数行）及其存储
        self.h._calendar_cache = {}
        self.h._first_seen = {}
        # v3.8.0：双向间隔表 + 承诺簿（_time_context_block 新增依赖）
        self.h._user_last_ts = {}
        self.h._ai_last_ts = {}
        # v4.0 Phase 2：_time_context_block 的节奏/连续性/gap 均改读统一快照
        # _time_snapshot 所需的五张映射表（生产 __init__ 全量装配；这里补齐
        # 假 self，避免真实方法链在快照读取处 AttributeError 静默降级）。
        self.h._last_seen = {}
        for name in (
            "_typing_delay_before_send",
            "_split_send_bubbles",
            "_new_inbound_since",
            "_collect_result_text",
            "_is_llm_reply",
            "_time_snapshot",
            "_gap_for_req",
            "_calendar_line_cached",
            "_days_line_for",
            "_time_context_block",
        ):
            setattr(
                self.h,
                name,
                types.MethodType(getattr(_main.HumanizerPlugin, name), self.h),
            )
        # 配置访问器与统计助手（假实现，见下方同名方法）
        # v4.1.1：时间感知档位读取（真实实例读配置；假 self 直接回落细分默认）
        self.h._time_flag = lambda key, default: default
        for name in (
            "_t",
            "_t_num",
            "_time",
            "_time_f",
            "_p_int",
            "_life",
            "_life_state_text",
            "_bump_stats",
            "_last_inbound_len",
        ):
            setattr(self.h, name, types.MethodType(getattr(type(self), name), self.h))

    # ---- 插件配置访问器的假实现（键名与 _group 语义对齐）----
    def _cm(self, key, default=None):
        return self.cfg.get(("commitments", key), default)

    def _t(self, key, default=None):
        return self.cfg.get(("typing", key), default)

    def _t_num(self, key, default, cast=float):
        v = self.cfg.get(("typing", key), default)
        try:
            return cast(v)
        except (TypeError, ValueError):
            return default

    def _time(self, key, default=None):
        return self.cfg.get(("time", key), default)

    def _time_f(self, key, default):
        return self._t_num(key, default, float) if ("time", key) in self.cfg else default

    def _p_int(self, key, default):
        return default

    def _life(self, key, default=None):
        return self.cfg.get(("life", key), default)

    def _life_state_text(self):
        return "", "当前状态"

    def _bump_stats(self, key):
        self.stats[key] = self.stats.get(key, 0) + 1

    def _last_inbound_len(self, umo):
        return 10

    # ---- 假事件 ----
    def _event(self, text, platform="aiocqhttp", llm=True, extra_result=None):
        ev = types.SimpleNamespace()
        ev.unified_msg_origin = "aiocqhttp:FriendMessage:1234"
        ev._platform = platform
        if extra_result is not None:
            ev._result = extra_result
        else:
            # 与框架 event.plain_result() 同型：生产链路 result 恒为
            # MessageEventResult（MessageChain 子类），derive() 行为一致。
            ev._result = MessageEventResult(chain=[Plain(text)])
        ev._extra = {"_humanizer_llm_replied": llm}
        ev.sent = []

        def get_result():
            return ev._result

        def get_extra(key, default=None):
            return ev._extra.get(key, default)

        def set_extra(key, value):
            ev._extra[key] = value

        async def send(chain):
            ev.sent.append(chain)
            # 模拟插话：测试用例在发送首条后把 _last_user_ts 拨到未来
            hook = getattr(ev, "_on_send", None)
            if hook:
                hook()

        def get_platform_name():
            return ev._platform

        ev.get_result = get_result
        ev.get_extra = get_extra
        ev.set_extra = set_extra
        ev.send = send
        ev.get_platform_name = get_platform_name
        ev.message_obj = types.SimpleNamespace(timestamp=time.time() - 3600)  # 1h 前→零补足
        return ev


@unittest.skipUnless(HAS_HOST, "需要宿主 venv（astrbot 包）")
class TestImportMain(unittest.TestCase):
    def test_import_and_helper(self):
        self.assertTrue(hasattr(_main, "_plain_chain"))
        self.assertTrue(hasattr(_main.HumanizerPlugin, "_split_send_bubbles"))


@unittest.skipUnless(HAS_HOST, "需要宿主 venv（astrbot 包）")
class TestSplitSendFlow(_Harness):
    def test_long_reply_splits_in_order(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._event(_LONG_TEXT)
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertGreaterEqual(len(ev.sent), 2)
        texts = [c.chain[0].text for c in ev.sent]
        self.assertEqual("".join(texts), _LONG_TEXT)
        self.assertEqual(len(ev._result.chain), 0, "待发链应已清空")
        registered = ev.get_extra("_send_message_to_user_current_session_plain_texts")
        self.assertEqual(registered, texts, "已发文本应登记进事件 extra")
        self.assertEqual(self.stats.get("split_sent"), 1)

    def test_each_sent_is_single_plain_chain(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._event(_LONG_TEXT)
        asyncio.run(self.h._typing_delay_before_send(ev))
        for chain in ev.sent:
            self.assertIsInstance(chain, MessageChain)
            self.assertEqual(len(chain.chain), 1)
            self.assertIsInstance(chain.chain[0], Plain)

    def test_short_text_untouched(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._event("好的，明天见")
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertEqual(len(ev.sent), 0, "短文本不应手动发送")
        self.assertEqual(len(ev._result.chain), 1, "待发链应保持原样交框架发送")
        self.assertNotIn("split_sent", self.stats)

    def test_split_disabled_noop(self):
        ev = self._event(_LONG_TEXT)
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertEqual(len(ev.sent), 0)
        self.assertEqual(len(ev._result.chain), 1)

    def test_non_plain_chain_skipped(self):
        self.cfg[("typing", "split_enable")] = True
        result = MessageChain(chain=[Plain(_LONG_TEXT), _dummy_image()])
        ev = self._event(_LONG_TEXT, extra_result=result)
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertEqual(len(ev.sent), 0, "含非文本组件的链不拆不丢")
        self.assertEqual(len(ev._result.chain), 2, "原链保持原样")

    def test_abort_on_new_inbound_between_bubbles(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._event(_LONG_TEXT)
        umo = ev.unified_msg_origin

        def simulate_interjection():
            self.last_user_ts[umo] = time.time() + 100  # 首条发出后来了新消息

        ev._on_send = simulate_interjection
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertEqual(len(ev.sent), 1, "插话后应中止剩余段")
        self.assertEqual(self.stats.get("split_sent"), 1)

    def test_cron_proactive_splits_without_delay(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._event(_LONG_TEXT, platform="cron", llm=False)
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertGreaterEqual(len(ev.sent), 2, "主动消息完整管线应零延迟直拆")

    def test_command_reply_never_splits(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._event(_LONG_TEXT, platform="aiocqhttp", llm=False)
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertEqual(len(ev.sent), 0, "非 LLM 产出（命令回复）不拆分")
        self.assertEqual(len(ev._result.chain), 1)


@unittest.skipUnless(HAS_HOST, "需要宿主 venv（astrbot 包）")
class TestContinuityBlock(_Harness):
    def test_days_absence_directive_injected(self):
        self.cfg[("time", "enable_gap")] = True
        self.cfg[("time", "continuity_inject")] = True
        self.cfg[("time", "gap_threshold_minutes")] = 30
        self.cfg[("time", "rhythm_enable")] = False
        ev = self._event("在吗")
        self.prev_seen[ev.unified_msg_origin] = time.time() - 72 * 3600  # 3 天前
        block = self.h._time_context_block(ev)
        self.assertIn("<time_context>", block)
        self.assertIn("距上次交流", block)
        self.assertIn("隔了好几天", block, "3 天缺席应注入 days 档指令")

    def test_continuous_chat_no_continuity_line(self):
        self.cfg[("time", "enable_gap")] = True
        self.cfg[("time", "continuity_inject")] = True
        self.cfg[("time", "gap_threshold_minutes")] = 30
        self.cfg[("time", "rhythm_enable")] = False
        ev = self._event("嗯嗯")
        self.prev_seen[ev.unified_msg_origin] = time.time() - 120  # 2 分钟前
        block = self.h._time_context_block(ev)
        self.assertNotIn("重新开口", block)
        self.assertNotIn("久别重逢", block)


def _dummy_image():
    """构造一个真实 Image 组件（占位 file 仅用于类型判断）。"""
    from astrbot.core.message.components import Image

    return Image(file="https://example.invalid/x.png")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAS_HOST, "需要宿主 venv（astrbot 包）")
class TestSplitSendFailureGuard(_Harness):
    """v3.7.0 审查修复（P3）：逐段 send 失败防护——剩余段回填待发链。

    旧实现清链后任一段 send 抛异常 → 外层 except 吞掉 → 已构造未发的
    段全部丢失（首段失败=整条回复凭空消失）。新行为：失败即停，失败段
    起的未发段回填 result.chain 交框架原路发送；已发部分照常登记。
    """

    def _fail_at(self, idx):
        """构造第 idx 段（0 基）send 抛异常的事件。"""
        ev = self._event(_LONG_TEXT)
        state = {"n": 0}

        async def send(chain):  # noqa: ANN001
            if state["n"] == idx:
                state["n"] += 1
                raise RuntimeError("simulated send failure")
            state["n"] += 1
            ev.sent.append(chain)

        ev.send = send
        return ev

    def test_mid_bubble_failure_backfills_tail(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._event(_LONG_TEXT)
        state = {"n": 0}

        async def send(chain):  # noqa: ANN001
            state["n"] += 1
            if state["n"] == 2:  # 第 2 段失败
                raise RuntimeError("simulated send failure")
            ev.sent.append(chain)

        ev.send = send
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertEqual(len(ev.sent), 1, "失败前应有 1 段已发出")
        # 失败段 + 未发段回填待发链（段数随默认参数拆分结果自适应）
        from humanizer_core.typing import split_reply_bubbles as _srb
        expect_bubbles = _srb(
            _LONG_TEXT, threshold=40.0, max_segments=3, min_part=8
        )
        self.assertGreaterEqual(len(expect_bubbles), 2)
        self.assertEqual(
            len(ev._result.chain),
            len(expect_bubbles) - 1,
            "失败段起的剩余段应回填待发链",
        )
        backfilled = "".join(c.text for c in ev._result.chain)
        sent_texts = [c.chain[0].text for c in ev.sent]
        self.assertEqual(
            "".join(sent_texts) + backfilled, _LONG_TEXT, "已发+回填内容守恒"
        )
        # 已发部分照常登记
        registered = ev.get_extra("_send_message_to_user_current_session_plain_texts")
        self.assertEqual(registered, sent_texts)
        self.assertEqual(self.stats.get("split_sent"), 1)

    def test_first_bubble_failure_backfills_all(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._fail_at(0)
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertEqual(len(ev.sent), 0, "首段失败时没有任何段发出")
        self.assertGreaterEqual(len(ev._result.chain), 1, "全部段应回填待发链交框架")
        backfilled = "".join(c.text for c in ev._result.chain)
        self.assertEqual(backfilled, _LONG_TEXT, "回填内容=全文")
        self.assertNotIn("split_sent", self.stats, "发送未完成不计 split_sent")

    def test_all_sent_no_backfill(self):
        self.cfg[("typing", "split_enable")] = True
        ev = self._event(_LONG_TEXT)
        asyncio.run(self.h._typing_delay_before_send(ev))
        self.assertEqual(len(ev._result.chain), 0, "全部成功时不回填")
