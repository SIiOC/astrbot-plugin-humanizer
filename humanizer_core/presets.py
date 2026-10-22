# -*- coding: utf-8 -*-
"""配置档位（v4.1.1 P1：把同质的多组细分开关收敛成「档位」，纯函数、零 astrbot 依赖）。

设计约定：
- ``custom`` 是默认档：不做任何覆盖，完全按各细分开关的现有语义工作（向后兼容）；
- 其余档位只在**读取配置时**覆盖少量键，不修改用户已保存的配置值；
- 档位表是唯一事实源，main 通过 ``preset_value`` 查询，避免在编排层散落 if 分支。
"""

from __future__ import annotations

from typing import Any, Mapping

# 时间感知：simple=只保留 gap + 生活状态；standard=加节奏/连续性/历法；
# full=再加双向最后发言与相识天数。
TIME_MODES: dict[str, dict[str, Any]] = {
    "custom": {},
    "simple": {
        "rhythm_enable": False,
        "continuity_inject": False,
        "include_calendar": False,
        "include_first_seen": False,
        "include_last_chat": False,
    },
    "standard": {
        "include_first_seen": False,
        "include_last_chat": False,
    },
    "full": {},
}

# 情绪：simple=只留基础惯性 + 时间衰减；standard=加热度耦合/安抚；
# full=再加重逢与冷落弧线。
EMOTION_MODES: dict[str, dict[str, Any]] = {
    "custom": {},
    "simple": {
        "emotion_heat_drift_enable": False,
        "emotion_reunion_inject": False,
        "emotion_cold_war": False,
        "emotion_soothe_boost": 0.0,
    },
    "standard": {
        "emotion_cold_war": False,
    },
    "full": {},
}

# 主动聊天：reserved=克制（无追问/无未回小情绪）；standard=默认；
# clingy=黏人（追问+未回小情绪）。
PROACTIVE_PRESETS: dict[str, dict[str, Any]] = {
    "custom": {},
    "reserved": {
        "proactive_followup_enable": False,
        "proactive_pout_on_unanswered": False,
    },
    "standard": {},
    "clingy": {
        "proactive_followup_enable": True,
        "proactive_pout_on_unanswered": True,
    },
}


def preset_value(groups: Mapping[str, Mapping[str, Any]] | None, mode: Any, key: str) -> Any:
    """查询某档位对某个键的覆盖值；无覆盖返回 None（调用方回落细分开关）。"""
    if not isinstance(groups, Mapping):
        return None
    table = groups.get(str(mode or "custom")) or {}
    if not isinstance(table, Mapping):
        return None
    return table.get(key)


__all__ = [
    "EMOTION_MODES",
    "PROACTIVE_PRESETS",
    "TIME_MODES",
    "preset_value",
]
