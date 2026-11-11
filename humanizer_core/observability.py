# -*- coding: utf-8 -*-
"""可观测性元数据（v4.7.0 从 main.py 拆出）。

只放纯常量与纯函数：统计键清单、事件流标签。main.py 只负责计数与落盘，
避免 5k 行的装配层继续膨胀；后续统计存储迁移到独立 store 时也在这里扩展。
"""

from __future__ import annotations

# 持久化到 stats.json 的计数器（顺序即控制台/文件中的顺序）
STATS_KEYS: tuple[str, ...] = (
    "rules_hit",
    "proactive_sent",
    "style_built",
    "proactive_interject_dropped",
    "qc_hits",
    "split_sent",
    "qc_checked",
    "typing_delay_applied",
    "debounce_merged",
    "qc_rule_hits",
    "proactive_failed",
    "proactive_timeout",
)

# 事件流标签：key -> (tag, 人类可读说明)
EVENT_LABELS: dict[str, tuple[str, str]] = {
    "rules_hit": ("去痕", "规则清理命中"),
    "proactive_sent": ("主动", "主动消息已发送"),
    "style_built": ("风格", "风格档案提炼完成"),
    "proactive_interject_dropped": ("主动", "生成期间用户发言，本次让位"),
    "qc_hits": ("质检", "规则质检命中（仅记录，不改写）"),
    "split_sent": ("分段", "回复拆分为多条消息发送"),
    "qc_checked": ("质检", "QC 规则检查轮次（只读观测）"),
    "typing_delay_applied": ("发送", "拟人打字延迟实际生效"),
    "debounce_merged": ("发送", "防抖合并了多条消息"),
    "qc_rule_hits": ("质检", "规则质检命中条数"),
    "proactive_failed": ("主动", "主动消息生成/发送失败"),
    "proactive_timeout": ("主动", "主动消息生成超时"),
}

__all__ = ["STATS_KEYS", "EVENT_LABELS"]
