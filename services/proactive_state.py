# -*- coding: utf-8 -*-
"""主动消息状态容器与持久化（v4.0 Phase 6 第一片）。

从 `main.HumanizerPlugin` 下沉 load/save 与五个状态字典的持有，保持
`proactive_state.json` 的 v3 结构与全部既有语义：

- 五个字典：triggers / unanswered / last_user_ts / followups / topic_used
- 过期触发点顺延一个周期（**非**自适应延迟，与旧实现逐字一致）
- 过期追问顺延一个追问周期（随机区间）
- topic_used 剪枝 30 天外条目
- 写入恒为 v3（`v` 键，非 version），tmp + os.replace 原子替换

`main` 侧仍持有同名属性，但**绑定到本容器持有的同一 dict 对象**（非副本），
因此现有 hook/命令对 `self._next_trigger_ts[...]` 等的读写与持久化天然一致。

不依赖 AstrBot：clock / randint / 配置读取 / 日志均为注入依赖，可离线单测。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from humanizer_core.emotion import cold_war_stage
from humanizer_core.proactive import (
    arm_followup_decision,
    compute_next_delay,
    compute_next_delay_adaptive,
    parse_proactive_extras,
    parse_proactive_state,
)

# 预置话题使用记录的保留窗口（天）：超期不恢复，防状态文件无限增长
_TOPIC_KEEP_DAYS = 30


class ProactiveState:
    """持有主动消息运行时状态并负责其磁盘往返。"""

    def __init__(
        self,
        *,
        state_file: str | os.PathLike[str] | None = None,
        config_getter: Optional[Callable[..., Any]] = None,
        logger: Any = None,
        clock: Callable[[], float] = time.time,
        randint: Callable[[int, int], int] | None = None,
        followup_decision: Optional[Callable[..., Any]] = None,
        sulky_feed: Optional[Callable[[Any], Any]] = None,
        cold_withdraw_detector: Optional[Callable[..., str]] = None,
    ) -> None:
        self.state_file = Path(state_file) if state_file else None
        self._config = config_getter
        self._logger = logger
        self._clock = clock
        self._randint = randint
        # 纯判定/情绪喂点为可注入端口（不满足时安全降级），服务保持离线可测。
        self._followup_decision = (
            followup_decision if followup_decision is not None else arm_followup_decision
        )
        self._sulky_feed = sulky_feed
        self._cold_withdraw_detector = (
            cold_withdraw_detector if cold_withdraw_detector is not None else cold_war_stage
        )

        # 公开的五个状态字典；调用方直接持有这些对象。
        self.triggers: dict[str, float] = {}
        self.unanswered: dict[str, int] = {}
        self.last_user_ts: dict[str, float] = {}
        self.followups: dict[str, dict] = {}
        self.topic_used: dict[str, float] = {}

    # -- 依赖适配 ---------------------------------------------------------
    def _cfg_value(self, key: str, default: Any) -> Any:
        getter = self._config
        if getter is None:
            return default
        try:
            return getter(key, default)
        except TypeError:
            try:
                return getter(key)
            except Exception:  # noqa: BLE001
                return default
        except Exception:  # noqa: BLE001
            return default

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self._cfg_value(key, default))
        except (TypeError, ValueError):
            return default

    def _cfg_float(self, key: str, default: float) -> float:
        try:
            return float(self._cfg_value(key, default))
        except (TypeError, ValueError):
            return default

    def _cfg_bool(self, key: str, default: bool) -> bool:
        return bool(self._cfg_value(key, default))

    def _rand(self, lo: int, hi: int) -> int:
        if self._randint is not None:
            return int(self._randint(lo, hi))
        import random

        return random.randint(lo, hi)

    def _log(self, level: str, message: str) -> None:
        if self._logger is None:
            return
        fn = getattr(self._logger, level, None)
        if fn is not None:
            try:
                fn(message)
            except Exception:  # noqa: BLE001
                pass

    # -- 持久化 -----------------------------------------------------------
    def load(self) -> None:
        """从文件恢复状态；缺失/损坏时静默保留空状态。

        语义与旧 `_load_proactive_state` 逐字一致：过期触发点顺延一个周期
        （`compute_next_delay`，非自适应）、过期追问顺延随机周期、话题记录
        剪枝；旧扁平/v2 文件由 parse_proactive_state 自动迁移。
        """
        path = self.state_file
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            triggers, unanswered, last_user_ts = parse_proactive_state(data)
            followups, topic_used = parse_proactive_extras(data)
            now = self._clock()
            idle = self._cfg_int("silence_after_minutes", 45)
            fluc = self._cfg_int("silence_fluctuation_minutes", 15)
            for umo, ts in triggers.items():
                if ts <= now:
                    # 已过期触发点：顺延一个周期，避免重启后立即补发
                    ts = now + compute_next_delay(idle, fluc) * 60
                self.triggers[umo] = float(ts)
            self.unanswered.update(unanswered)
            self.last_user_ts.update(last_user_ts)
            fu_lo = self._cfg_int("proactive_followup_delay_min_minutes", 12)
            fu_hi = max(self._cfg_int("proactive_followup_delay_max_minutes", 20), fu_lo)
            for umo, fu in followups.items():
                if fu.get("due_ts", 0.0) <= now:
                    # 已到期的追问不立即补发：顺延一个追问周期（比常规轮轻）
                    fu["due_ts"] = now + self._rand(fu_lo, fu_hi) * 60
                self.followups[umo] = fu
            cutoff = now - _TOPIC_KEEP_DAYS * 86400
            self.topic_used.update(
                {t: ts for t, ts in topic_used.items() if ts >= cutoff}
            )
            self._log(
                "info",
                f"[Humanizer] 已恢复 {len(self.triggers)} 个会话的主动聊天状态",
            )
        except Exception as e:  # noqa: BLE001
            self._log("warning", f"[Humanizer] 加载主动聊天状态失败（忽略）: {e}")

    def save(self) -> bool:
        """原子写入 v3 状态（tmp + os.replace）；成功返回 True。

        结构与旧 `_save_proactive_state` 逐字一致（键名 v/triggers/unanswered/
        last_user_ts/followups/topic_used）。失败静默记 debug。
        """
        path = self.state_file
        if path is None:
            return False
        try:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "v": 3,
                        "triggers": self.triggers,
                        "unanswered": self.unanswered,
                        "last_user_ts": self.last_user_ts,
                        "followups": self.followups,
                        "topic_used": self.topic_used,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(tmp, path)
            return True
        except Exception as e:  # noqa: BLE001
            self._log("debug", f"[Humanizer] 保存主动聊天状态失败: {e}")
            return False


    # -- 调度状态操作（v4.0 Phase 6 第二片）-------------------------------
    def note_user_message(self, umo: str, now: float) -> float:
        """用户发言：清零未回复计数、记录最后发言、作废追问链、排下次触发。

        返回下次触发的延迟分钟数（调用方可用于日志/测试）。顺序与旧
        `_track_activity` 逐字一致——**先**清零计数再算延迟（v3.9.0：否则
        刚回复就吃未回复缩放）。
        """
        self.unanswered[umo] = 0
        self.last_user_ts[umo] = now
        # 用户回复 → 该会话待发追问链整体作废（追问只追"没回"）
        if umo in self.followups:
            self.followups.pop(umo, None)
        delay_minutes = compute_next_delay_adaptive(
            self._cfg_int("silence_after_minutes", 45),
            self._cfg_int("silence_fluctuation_minutes", 15),
            0,
            scale_step=self._cfg_float("proactive_silence_scale_step", 0.3)
            if self._cfg_bool("proactive_silence_scale_enable", True)
            else 0.0,
            cap_minutes=self._cfg_int("proactive_silence_scale_cap_minutes", 240),
        )
        self.triggers[umo] = now + delay_minutes * 60
        return delay_minutes

    def reschedule_next(self, umo: str, now: float) -> float:
        """触发后重排下次触发（按沉默自适应缩放；未回复计数参与放大）。

        返回延迟分钟数。与旧 `_proactive_loop` 内联计算逐字一致。
        """
        delay_minutes = compute_next_delay_adaptive(
            self._cfg_int("silence_after_minutes", 45),
            self._cfg_int("silence_fluctuation_minutes", 15),
            int(self.unanswered.get(umo, 0) or 0),
            scale_step=self._cfg_float("proactive_silence_scale_step", 0.3)
            if self._cfg_bool("proactive_silence_scale_enable", True)
            else 0.0,
            cap_minutes=self._cfg_int("proactive_silence_scale_cap_minutes", 240),
        )
        self.triggers[umo] = now + delay_minutes * 60
        return delay_minutes

    def prune_stale(self, now: float, max_age_seconds: float = 24 * 3600) -> list[str]:
        """清理超过 max_age 未活动的会话跟踪条目；返回被清理的会话列表。

        v4.0.1：以 **last_user_ts**（用户最后发言）判过期。原先用 triggers
        （下次触发时间）判断——但 triggers 恒被重排到未来（触发即
        reschedule_next），主动开启时 `now - ts` 永远为负，死会话四表
        永不回收；只有功能关闭、触发时间停在过去时清理才碰巧生效。
        机器人自己持续发送的主动消息不算"活动"（那正是要回收的对象）。
        """
        stale = [
            umo for umo in set(self.triggers) | set(self.last_user_ts)
            if now - float(self.last_user_ts.get(umo, 0.0)) > max_age_seconds
        ]
        for umo in stale:
            self.triggers.pop(umo, None)
            self.unanswered.pop(umo, None)
            self.last_user_ts.pop(umo, None)
            self.followups.pop(umo, None)
        return stale

    def drop_session(self, umo: str) -> None:
        """整体移除一个会话的全部跟踪状态（白名单外/过期回收共用）。"""
        self.triggers.pop(umo, None)
        self.unanswered.pop(umo, None)
        self.last_user_ts.pop(umo, None)
        self.followups.pop(umo, None)

    def drop_followup(self, umo: str) -> None:
        """只作废某会话的追问链（用户已回复/开关关闭等）。"""
        self.followups.pop(umo, None)

    def clear_topic_used(self) -> None:
        """清空预置话题使用记录（测试/维护用）。"""
        self.topic_used.clear()

    def prune_topic_used(self, max_items: int = 200) -> bool:
        """话题使用记录的容量护栏：超过 max_items 条丢最旧一半。

        **原地 clear+update**（不重新赋值）——`main._topic_used` 与本容器的
        `topic_used` 是同一 dict 对象，重新赋值会让别名指向旧 dict，导致
        save() 落盘过期数据（v4.0 Phase 6 期引入的回归，此处修复）。保留语义
        逐字对齐旧内联实现：按时间戳中位数丢弃更旧的一半。返回是否发生裁剪。
        """
        if len(self.topic_used) <= max_items:
            return False
        keep_after = sorted(self.topic_used.values())[len(self.topic_used) // 2]
        kept = {
            t: ts for t, ts in self.topic_used.items() if ts >= keep_after
        }
        self.topic_used.clear()
        self.topic_used.update(kept)
        return True

    # -- 未回复计数 / 追问布防（v4.0 Phase 6 第三片）---------------------
    def bump_unanswered(self, umo: str, started_ts: float = 0.0) -> dict[str, object]:
        """主动消息确认发送后递增未回复计数，失败/被拦截的发送不递增。

        竞态守卫：发送耗时数十秒，若期间用户恰好回复（计数已被清零），
        本次递增作废——以 started_ts 与 last_user_ts 比较判断，避免
        "用户刚回复却收到你没理我"的档位错乱。

        返回 ``{"race": bool}``；调用方据此设置落盘脏标记（`_state_dirty`
        刻意留在 main——它是 proactive 与 stats 共享的 bool 触发器）。
        """
        if started_ts and self.last_user_ts.get(umo, 0.0) >= started_ts:
            self._log("debug", f"[Humanizer] 发送期间用户已回复，跳过未回复计数递增: {umo}")
            return {"race": True}
        try:
            self.unanswered[umo] = int(self.unanswered.get(umo, 0)) + 1
        except (TypeError, ValueError):  # noqa: BLE001
            self.unanswered[umo] = 1
        return {"race": False}

    def feed_sulky(self, umo: str) -> None:
        """未回复事件喂入情绪引擎（sulky）；总闸沿用 proactive_pout_on_unanswered。

        该开关同时管主动消息文案（pout）与对话侧情绪（sulky）——保持
        "微微生气是可选"的初衷。喂点函数由构造注入（`sulky_feed`），缺省
        时静默跳过（纯离线场景）。
        """
        if not self._cfg_bool("proactive_pout_on_unanswered", False):
            return
        if not self._cfg_bool("emotion_enable", True):
            return
        if self._sulky_feed is None:
            return
        try:
            self._sulky_feed(umo)
        except Exception as e:  # noqa: BLE001
            self._log("debug", f"[Humanizer] 情绪喂入(sulky)失败: {e}")

    def cold_withdraw(self, umo: str) -> bool:
        """冷落弧线"抽离档"信号：关系收着不归零但不再追问。

        与弧线"留极轻触点"的分寸一致，追问会打破它。仅在 emotion_cold_war
        开启且数据源（last_user_ts）可用时判定；任何异常回落 False（不干预）。
        """
        if not self._cfg_bool("emotion_cold_war", False):
            return False
        last_ts = self.last_user_ts.get(umo)
        if not last_ts:
            return False
        try:
            return (
                self._cold_withdraw_detector(
                    last_ts,
                    self._clock(),
                    self._cfg_value("cold_war_thresholds_days", "1,3,7,14"),
                )
                == "withdraw"
            )
        except Exception:  # noqa: BLE001
            return False

    def arm_followup(self, umo: str, just_sent_stage: int, cold_withdraw: bool) -> bool:
        """发送成功后决定是否布防下一条轻追问（v3.9.0，纯调度无 IO）。

        判定委托可注入的 `followup_decision`（默认 proactive.arm_followup_decision，
        可离线测试）；任何拒绝（功能关/抽离档/超上限/抽签不中）都清掉该会话
        残留的旧链。返回是否发生状态变更（供调用方置脏标记）。
        """
        if not self._cfg_bool("proactive_followup_enable", False):
            changed = umo in self.followups
            self.followups.pop(umo, None)
            return changed
        decision = self._followup_decision(
            just_sent_stage,
            enabled=True,
            unanswered_after=int(self.unanswered.get(umo, 0) or 0),
            max_unanswered=self._cfg_int("proactive_followup_max_unanswered", 2),
            prob=self._cfg_float("proactive_followup_prob", 0.6),
            delay_min_minutes=self._cfg_int("proactive_followup_delay_min_minutes", 12),
            delay_max_minutes=self._cfg_int("proactive_followup_delay_max_minutes", 20),
            cold_withdraw=cold_withdraw,
        )
        if decision is None:
            changed = umo in self.followups
            self.followups.pop(umo, None)
            return changed
        next_stage, delay_minutes = decision
        now = self._clock()
        self.followups[umo] = {
            "stage": next_stage,
            "due_ts": now + delay_minutes * 60,
            "armed_ts": now,
        }
        return True


__all__ = ["ProactiveState"]
