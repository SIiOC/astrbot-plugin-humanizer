# -*- coding: utf-8 -*-
"""运行态指标汇聚（v4.8.0：统计 / 事件流 / 注入字符 / 清理明细共用一个 sink）。

之前这四类数据各自在 main.py 里维护一个 dict/deque 和一对读写方法，
控制台端点再从各属性拼装；v4.8.0 收进一个纯数据类，main 只保留兼容访问
属性（``_stats`` / ``_events_ring`` / ``_inject_stats`` ...），这样：
- 计数、事件、注入字符、清理明细共享同一份内存事实源；
- reset / snapshot 只需要一个入口；
- 后续新增指标不必再改 main 的初始化块。
"""

from __future__ import annotations

import time
from collections import deque

from humanizer_core.privacy import mask_pii

# 注入器记录键（控制台 breakdown 与注入管线共用）
INJECT_KEYS: tuple[str, ...] = (
    "turns",
    "growth",
    "growth_state",
    "time",
    "discipline",
    "emotion",
    "rules",
    "lang",
    "style",
    "examples",
)


class MetricsSink:
    """内存态指标汇聚器；不依赖 astrbot，落盘仍由 main 负责。"""

    def __init__(
        self,
        counter_keys,
        event_labels=None,
        inject_keys=INJECT_KEYS,
        event_cap: int = 80,
        cleanup_cap: int = 20,
        recent_cap: int = 20,
    ):
        self.counters: dict[str, int] = {str(key): 0 for key in counter_keys}
        self.events: deque = deque(maxlen=event_cap)
        self.cleanup: deque = deque(maxlen=cleanup_cap)
        self.inject_stats: dict[str, int] = {str(key): 0 for key in inject_keys}
        self.inject_turn_chars = 0
        self.inject_recent: deque = deque(maxlen=recent_cap)
        self.inject_last: dict[str, int] = {}
        self._event_labels = dict(event_labels or {})

    # ---------------------------------------------------------------- 计数/事件
    def bump(self, key: str, delta: int = 1) -> bool:
        """累加计数；非法键/非法增量返回 False（调用方可据此置脏标记）。"""
        if key not in self.counters:
            return False
        try:
            amount = int(delta)
        except (TypeError, ValueError):
            return False
        if amount == 0:
            return False
        self.counters[key] += amount
        label = self._event_labels.get(key)
        if label:
            self.event(label[0], label[1])
        return True

    def event(self, tag: str, msg: str) -> None:
        """控制台「实时事件流」事件入环（内存态，重启清空）。"""
        try:
            self.events.append(
                {"ts": round(time.time(), 3), "tag": str(tag), "msg": str(msg)[:120]}
            )
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- 注入字符
    def start_turn(self) -> None:
        """一轮 LLM 请求开始：结算上一轮字符数并计入 turns。"""
        try:
            self.inject_stats["turns"] = self.inject_stats.get("turns", 0) + 1
            if self.inject_turn_chars:
                self.inject_recent.append(self.inject_turn_chars)
            self.inject_turn_chars = 0
            self.inject_last = {}
        except Exception:  # noqa: BLE001
            pass

    def record_inject(self, key: str, text: str) -> None:
        """累加一次提示词注入的字符数（未知键静默忽略）。"""
        try:
            amount = len(text or "")
            if amount and key in self.inject_stats:
                self.inject_stats[key] += amount
                self.inject_turn_chars += amount
        except Exception:  # noqa: BLE001
            pass

    def record_cleanup(self, text: str, cleaned: str, hits) -> None:
        """记录一次规则清理明细（before/after 先做 PII 掩码）。"""
        try:
            items = list(hits) if isinstance(hits, (list, tuple)) else [hits]
            self.cleanup.append(
                {
                    "ts": round(time.time(), 1),
                    "hits": [str(item)[:40] for item in items][:8],
                    "before": mask_pii(str(text))[:60],
                    "after": mask_pii(str(cleaned))[:60],
                }
            )
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- 统一重置
    def reset_counters(self) -> None:
        """清零持久化计数（事件流/注入最近值保留，便于排障）。"""
        for key in self.counters:
            self.counters[key] = 0

    def snapshot(self) -> dict:
        """只读快照（调试/测试用；控制台端点仍按需拼装）。"""
        return {
            "counters": dict(self.counters),
            "events": list(self.events),
            "cleanup": list(self.cleanup),
            "inject": {
                "stats": dict(self.inject_stats),
                "turn_chars": self.inject_turn_chars,
                "recent": list(self.inject_recent),
                "last": dict(self.inject_last),
            },
        }


__all__ = ["INJECT_KEYS", "MetricsSink"]
