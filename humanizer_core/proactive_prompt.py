# -*- coding: utf-8 -*-
"""主动消息 prompt 组装（v4.0 Phase 6 第三片 c，纯函数）。

从 `main._proactive_chat` 下沉"取数据之后、生成之前"的纯组装逻辑——
没有任何 IO / 框架依赖，可完全离线单测：

- 沉默时长估算（含无打点时的按周期近似）；
- 情绪块决策：**优先级 弧线 > 追问 > pout**（三者同源情绪只发一版；
  追问自带"轻碰/收尾"分寸，叠加 pout 会变成质问）；
- 迟到补发块（宕机跨点/免打扰压单/生成慢导致的迟到由它度量）；
- 顺序拼接：基础 prompt → 话题块 → 情绪块 → 迟到块。

判定所依赖的渲染函数（build_pout_directive / build_followup_directive /
late_delivery_block / cold_war_*）仍属 humanizer_core.proactive / .emotion，
本模块只做"何时用哪个 + 怎么拼"的编排，便于单点钉死顺序与优先级契约。
"""

from __future__ import annotations

from typing import Any, Optional

from humanizer_core.emotion import (
    cold_war_proactive_directive,
    cold_war_stage,
)
from humanizer_core.proactive import (
    build_followup_directive,
    build_pout_directive,
    late_delivery_block,
)

# 情绪块种类标记（供调用方日志分档，不参与注入文本）
ARC = "arc"
FOLLOWUP = "followup"
POUT = "pout"
NONE = ""


def silence_hours_estimate(
    last_ts: Optional[float],
    now_ts: float,
    unanswered: int,
    idle_minutes: int,
) -> int:
    """估算静默小时数（{silence_hours} 占位符用）。

    有最后发言打点：按真实流逝时长取整（round，非 int——45 分钟周期第 1 次
    即约 1 小时，不再出现"约 0 小时"）。无打点（旧状态迁移/极端场景）：按
    未回复计数 × 周期近似。clamp 下限 0。
    """
    if last_ts:
        try:
            return max(round((now_ts - float(last_ts)) / 3600), 0)
        except (TypeError, ValueError):
            return 0
    try:
        base = int(unanswered) * int(idle_minutes) / 60
    except (TypeError, ValueError):
        return 0
    return max(round(base), 0)


def emotion_block(
    *,
    followup_stage: int,
    unanswered: int,
    silence_hours: int,
    pout_on: bool,
    cold_war_enabled: bool,
    last_user_ts: Optional[float],
    now_ts: float,
    thresholds: Any = "1,3,7,14",
    emotion_state: Any = None,
) -> tuple[str, str]:
    """按优先级选择情绪注入块，返回 (文本, 种类)。

    优先级：弧线（冷落降温，独立开关）> 追问话术 > pout（未回复小情绪）。
    弧线块前置 ``\\n\\n【冷落降温】``；弧线判定异常时静默回落（不注入弧线，
    继续考虑追问/pout）。
    """
    arc_block = ""
    if cold_war_enabled and last_user_ts:
        try:
            stage = cold_war_stage(last_user_ts, now_ts, thresholds)
            arc_text = cold_war_proactive_directive(stage, emotion_state)
            if arc_text:
                arc_block = "\n\n【冷落降温】" + arc_text
        except Exception:  # noqa: BLE001
            arc_block = ""
    if arc_block:
        return arc_block, ARC
    if int(followup_stage or 0) > 0:
        return build_followup_directive(followup_stage), FOLLOWUP
    if pout_on:
        return build_pout_directive(unanswered, silence_hours), POUT
    return "", NONE


def late_block(
    due_ts: Optional[float],
    now_ts: float,
    threshold_minutes: int,
) -> str:
    """迟到补发块：预定触发时刻被拖过阈值时渲染"来晚了"指令。

    due_ts 缺失/非法/渲染异常一律返回空串（不干预）。late_minutes 允许为负
    （提前触发），late_delivery_block 自身对 <threshold 返回空串。
    """
    if not due_ts:
        return ""
    try:
        late_minutes = int((now_ts - float(due_ts)) / 60)
        return late_delivery_block(late_minutes, threshold_minutes)
    except Exception:  # noqa: BLE001
        return ""


def assemble_prompt(
    base: str,
    *,
    topic_block: str = "",
    emotion_block_text: str = "",
    late_block_text: str = "",
) -> str:
    """顺序拼接主动 prompt：基础 → 话题 → 情绪 → 迟到（空块跳过）。"""
    prompt = base
    if topic_block:
        prompt = prompt + topic_block
    if emotion_block_text:
        prompt = prompt + emotion_block_text
    if late_block_text:
        prompt = prompt + late_block_text
    return prompt


def life_for_template(template: str, life_block: str) -> str:
    """仅当模板显式含 {life} 占位符时注入生活块（否则不无条件追加）。"""
    return life_block if "{life}" in template else ""


__all__ = [
    "ARC",
    "FOLLOWUP",
    "NONE",
    "POUT",
    "assemble_prompt",
    "emotion_block",
    "late_block",
    "life_for_template",
    "silence_hours_estimate",
]
