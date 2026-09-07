# -*- coding: utf-8 -*-
"""情绪惯性引擎（v3.5.1，纯函数、零 astrbot 依赖）。

跨消息的情绪状态机：机器人对每个会话维持一档轻微情绪
（neutral 平静 / sulky 有点小情绪 / appy 心情不错），随对话事件
演进并逐条衰减——"被冷落会蔫一阵，被哄了会开心一阵，聊几句就过去"。

状态形态（per-umo dict）：{"emotion": str, "intensity": float}
- emotion ∈ EMOTIONS；intensity ∈ [0, 1]，0 视同 neutral。
所有函数返回新状态 dict（输入不做原地修改，便于测试与无副作用接线）。
"""

from __future__ import annotations

from typing import Iterable, Optional

EMOTIONS = ("neutral", "sulky", "appy")

# 强度低于该值回落 neutral（衰减后残值不再值得注入指令）
NEUTRAL_FLOOR = 0.15

DEFAULT_SOOTHE_WORDS = (
    "哈哈",
    "笑死",
    "谢谢",
    "感谢",
    "抱抱",
    "摸摸",
    "喜欢你",
    "爱你",
    "辛苦了",
    "辛苦啦",
    "对不起",
    "抱歉",
    "别生气",
    "乖",
    "最棒",
    "厉害",
)


def neutral_state() -> dict:
    return {"emotion": "neutral", "intensity": 0.0}


def _valid(state) -> bool:
    return (
        isinstance(state, dict)
        and state.get("emotion") in EMOTIONS
        and isinstance(state.get("intensity"), (int, float))
    )


def _make(emotion: str, intensity: float) -> dict:
    return {"emotion": emotion, "intensity": round(max(0.0, min(float(intensity), 1.0)), 4)}


def bump_sulky(state, amount: float = 0.35) -> dict:
    """被冷落事件喂入：情绪转向 sulky 并抬升强度（appy 被覆盖——
    刚被哄开心又连吃闭门羹，以更新的冷落为准）。amount 非法按默认值。"""
    if not _valid(state):
        state = neutral_state()
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        amt = 0.35
    if amt <= 0:
        amt = 0.35
    base = state["intensity"] if state.get("emotion") == "sulky" else 0.0
    return _make("sulky", base + amt)


def bump_appy(state, amount: float = 0.4) -> dict:
    """安抚/积极信号喂入：情绪转向 appy 并抬升强度（sulky 被覆盖——
    被哄了就是被哄了）。amount 非法按默认值。"""
    if not _valid(state):
        state = neutral_state()
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        amt = 0.4
    if amt <= 0:
        amt = 0.4
    base = state["intensity"] if state.get("emotion") == "appy" else 0.0
    return _make("appy", base + amt)


def decay(state, factor: float = 0.6) -> dict:
    """用户每发言一次衰减一次；强度低于 NEUTRAL_FLOOR 回落 neutral。"""
    if not _valid(state):
        return neutral_state()
    try:
        f = float(factor)
    except (TypeError, ValueError):
        f = 0.6
    if not (0.0 < f <= 1.0):
        f = 0.6
    val = float(state["intensity"]) * f
    if val < NEUTRAL_FLOOR:
        return neutral_state()
    return _make(state["emotion"], val)


def decay_time(state, elapsed_seconds, half_life_hours: float = 8.0) -> dict:
    """按真实流逝时长做半衰期衰减（v3.7.0）；低于 NEUTRAL_FLOOR 回落 neutral。

    与 decay()（逐条衰减）互补：情绪状态带 ts 持久化，用户隔了半天/几天
    回来时情绪应随时间淡去，而不是原封不动地带到下一轮。
    - half_life_hours<=0 视为关闭（原样返回，调用方据此刻意停用）；
    - elapsed 非法/NaN/负数一律不衰减（时钟回拨防御）。
    """
    if not _valid(state):
        return neutral_state()
    try:
        elapsed = float(elapsed_seconds)
    except (TypeError, ValueError):
        return state
    if elapsed != elapsed or elapsed <= 0:  # NaN / 时钟回拨：不衰减
        return state
    try:
        half = float(half_life_hours)
    except (TypeError, ValueError):
        half = 8.0
    if half <= 0:  # 关闭开关
        return state
    factor = 0.5 ** (elapsed / (half * 3600.0))
    val = float(state["intensity"]) * factor
    if val < NEUTRAL_FLOOR:
        return neutral_state()
    return _make(state["emotion"], val)


# ============================================================
# 重逢组合指令（v3.7.0）
# ============================================================
# 隔了好几天/久别（continuity_label ∈ REUNION_LABELS，由 main 侧
# time_flow.continuity_label 计算）时，情绪指令换成「淡了但温度还在」的
# 重逢版——情绪不该延续分离前的语气，也不该凭空归零。

REUNION_LABELS = ("days", "long_absence")

_REUNION_SULKY_TEXT = (
    "【情绪状态】你们已经好几天没聊了。之前那点小情绪其实早就淡了——"
    "现在更多的是「终于又聊上了」的感觉，可以自然问问这几天过得怎么样，"
    "别翻旧账、别再提闹别扭的事。"
)
_REUNION_APPY_TEXT = (
    "【情绪状态】好几天没聊，突然又聊上了，你其实有点开心——"
    "语气自然带点热乎劲，像老朋友重新联系那样，但别用力过猛。"
)


def reunion_directive(state, label: str) -> str:
    """重逢场景的情绪指令（v3.7.0）；非重逢档/无情绪返回空串（回退常规指令）。"""
    if label not in REUNION_LABELS or not _valid(state):
        return ""
    emo = state["emotion"]
    if emo == "sulky":
        return _REUNION_SULKY_TEXT
    if emo == "appy":
        return _REUNION_APPY_TEXT
    return ""


def hit_soothe(text, words: Optional[Iterable[str]] = None) -> bool:
    """用户消息是否命中安抚/积极词池（任一子串命中即 True）。

    words 为空/非字符串元素时回落内置默认池；text 非字符串返回 False。
    """
    if not isinstance(text, str) or not text.strip():
        return False
    pool = [w for w in (words if words else DEFAULT_SOOTHE_WORDS) if isinstance(w, str) and w.strip()]
    if not pool:
        pool = list(DEFAULT_SOOTHE_WORDS)
    return any(w in text for w in pool)


def emotion_directive(state) -> str:
    """按状态渲染注入指令行；neutral / 低强度返回空串（不占 token）。

    措辞刻意克制：轻微、有分寸、绝不过激——与"微微生气"的产品定位一致。
    """
    if not _valid(state):
        return ""
    emo = state["emotion"]
    val = float(state["intensity"])
    if val < NEUTRAL_FLOOR:
        return ""
    if emo == "sulky":
        if val >= 0.45:
            return (
                "【情绪状态】你此刻有点小情绪（对方连续没理你）：语气带一点小委屈和不情愿，"
                "可以轻轻嘟囔一句，但依然在意对方，绝不指责、绝不过激。"
            )
        return "【情绪状态】你还有一点点没消散的小情绪：语气略微淡淡，偶尔轻描淡写带一下就好。"
    if emo == "appy":
        return "【情绪状态】你此刻心情不错：回复自然带点轻快和暖意，但别用力过猛。"
    return ""


def emotion_short(state) -> str:
    """给深度改写链用的极短状态描述（省 token）；无情绪返回空串。"""
    if not _valid(state):
        return ""
    val = float(state["intensity"])
    if val < NEUTRAL_FLOOR:
        return ""
    if state["emotion"] == "sulky":
        return "你现在有点小情绪，语气带一点点不情愿"
    if state["emotion"] == "appy":
        return "你现在心情不错，语气轻快带点暖意"
    return ""


__all__ = [
    "DEFAULT_SOOTHE_WORDS",
    "EMOTIONS",
    "NEUTRAL_FLOOR",
    "REUNION_LABELS",
    "bump_appy",
    "bump_sulky",
    "decay",
    "decay_time",
    "emotion_directive",
    "emotion_short",
    "hit_soothe",
    "neutral_state",
    "reunion_directive",
]
