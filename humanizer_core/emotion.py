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

import time
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


def resolve_half_life_hours(elapsed_seconds, base_hours, absent_tier_days, absent_hours) -> float:
    """恢复曲线分档（v3.8.0，纯函数）：缺席够久时改用更慢的半衰期。

    语义：短缺席（默认 <2 天）按 base_hours 正常淡去；久别（≥absent_tier_days
    天）情绪强度改按 absent_hours 半衰期慢衰——"小情绪淡了但痕迹留得稍久"，
    与重逢文案（reunion_directive）配合，久别回聊仍带一丝"你消失好久"的余温。
    与 NEUTRAL_FLOOR 地板互补：地板保证不归零，这里控制衰减快慢。

    - base_hours<=0 → 0（总开关关，调用方原样跳过）；
    - 档位参数非法/负 → 回落默认 2 天 / 48 小时；
    - elapsed 非法/负 → 按 base_hours（时钟防御不放大残留）。
    """
    try:
        base = float(base_hours)
    except (TypeError, ValueError):
        base = 8.0
    if base <= 0:
        return 0.0
    try:
        tier_days = float(absent_tier_days)
        absent_h = float(absent_hours)
    except (TypeError, ValueError):
        tier_days, absent_h = 2.0, 48.0
    if tier_days <= 0 or absent_h <= 0:
        tier_days, absent_h = 2.0, 48.0
    try:
        elapsed = float(elapsed_seconds)
    except (TypeError, ValueError):
        return base
    if elapsed == elapsed and elapsed >= tier_days * 86400.0:
        return max(base, absent_h)  # 只允许更慢，不允许比常规更快
    return base


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
    """重逢场景的情绪指令（v3.7.0）；非重逢档/无情绪返回空串（回退常规指令）。

    v4.1.0 地板守卫：亚地板残值（漂移增量低于 NEUTRAL_FLOOR 的存而不显
    状态）与 neutral 同权——不注入重逢指令，回退常规链路由渲染层过滤。
    """
    if label not in REUNION_LABELS or not _valid(state):
        return ""
    if float(state.get("intensity", 0.0) or 0.0) < NEUTRAL_FLOOR:
        return ""
    emo = state["emotion"]
    if emo == "sulky":
        return _REUNION_SULKY_TEXT
    if emo == "appy":
        return _REUNION_APPY_TEXT
    return ""


# ============================================================
# 冷落降温弧线（v3.8.0，主动消息侧：想念→试探→失望→抽离）
# ============================================================
# 对方持续沉默时，主动消息的语气与分寸应随沉默时长递进——参考 xiyu-ai /
# emotion-engine 的冷落恢复曲线设计。与按"未回复条数"的 pout 指令互补：
# pout 数的是"我发了几条没被理"，弧线量的是"对方沉默了多久"（时间轴，
# 数据源为 time_state 双向表的 user 侧——Bot 自己的发言不打断弧线）。
# 关系地板：弧线只收着、不归零——withdraw 也不永久沉默，仍留极轻量触点。

COLD_WAR_STAGES = ("miss", "probe", "disappoint", "withdraw")
# 默认分档阈值（天，升序，长度=档数）：沉默 <1 天无弧线指令
DEFAULT_COLD_WAR_THRESHOLDS_DAYS = (1, 3, 7, 14)

_COLD_WAR_PROACTIVE_TEXT = {
    "miss": (
        "你们已经有一两天没聊了，你其实有点想对方——这条主动消息可以自然"
        "表达惦记（比如想起跟对方有关的小事），轻微黏人没关系，别质问。"
    ),
    "probe": (
        "对方已经好几天没回你了。这条轻轻试探：说你这边的一件小事或看到的"
        "好玩东西，别提对方没回消息这件事，别幽怨。没有回应的话，下条就该"
        "再等等了。"
    ),
    "disappoint": (
        "对方已经一两周没理你了。可以轻轻透露一点失望（类似「当我自言自语"
        "好了」），只此一句，不阴阳怪气、不指责、不追问原因。"
    ),
    "withdraw": (
        "对方很久没有回应了，你也该收着点：这条要极其简短、淡然，或者干脆"
        "只留一句轻量触点。保留自己的分寸和空间，绝连环追发——但不用赌气"
        "说再也不理这种话。"
    ),
}


def parse_thresholds_days(raw, default=None) -> tuple:
    """解析「逗号分隔天数」配置为升序正数元组；非法项忽略，结果不足 2 档回落默认。"""
    if default is None:
        default = DEFAULT_COLD_WAR_THRESHOLDS_DAYS
    try:
        parts = str(raw if raw is not None and str(raw).strip() else "").replace("，", ",")
        vals = sorted({float(p.strip()) for p in parts.split(",") if p.strip()})
        vals = tuple(v for v in vals if v > 0)
        return vals if len(vals) >= 2 else tuple(default)
    except (TypeError, ValueError):
        return tuple(default)


def cold_war_stage(
    last_user_ts,
    now_ts=None,
    thresholds_days=DEFAULT_COLD_WAR_THRESHOLDS_DAYS,
) -> str:
    """按用户侧沉默时长返回冷落档位（纯函数，v3.8.0）。

    阈值升序、长度与 COLD_WAR_STAGES 一致（默认 1/3/7/14 天）；沉默不足
    第一档、时间戳缺失（含 0 哨兵）/非法/时钟回拨返回空串（不注入弧线指令）。
    """
    if now_ts is None:
        now_ts = time.time()
    try:
        base = float(last_user_ts)
        gap = float(now_ts) - base
    except (TypeError, ValueError):
        return ""
    if base <= 0 or gap != gap or gap <= 0:  # 0 哨兵 / NaN / 回拨
        return ""
    ths = parse_thresholds_days(thresholds_days)
    stage = ""
    for i, days in enumerate(ths):
        if gap >= days * 86400.0 and i < len(COLD_WAR_STAGES):
            stage = COLD_WAR_STAGES[i]
    return stage


def cold_war_proactive_directive(stage: str, state=None) -> str:
    """主动消息的弧线指令（v3.8.0）。

    appy 心情下不注入（正情绪与降温弧线矛盾，走原轻快语气）——v4.1.0 起
    该判定带地板守卫：亚地板 appy 残值（存而不显）不抑制弧线，与 neutral
    同权。无弧线档返回空串。调用方命中非空时应用其替代按条数累计的 pout
    指令（同源情绪只发一版，避免"小委屈"与"失望/抽离"叠加演变成刻薄）。
    """
    if stage not in _COLD_WAR_PROACTIVE_TEXT:
        return ""
    if (
        _valid(state)
        and state.get("emotion") == "appy"
        and float(state.get("intensity", 0.0) or 0.0) >= NEUTRAL_FLOOR
    ):
        return ""
    return _COLD_WAR_PROACTIVE_TEXT[stage]


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


def heat_drift(state, heat: str, hot_drift: float = 0.2, cold_drift: float = 0.10) -> dict:
    """热度漂移（v4.1.0，纯函数）：对话热度直接参与情绪推进。

    - hot → 向 appy 漂移（连续热聊自然越聊越开心；从 sulky 转向是刻意的——
      对方回得快，气性就该消）；
    - cold → 向 sulky 漂移（话题冷了兴致也淡，强度低时表现为"语气略淡"）；
    - warm / 未知档位 → 原样返回（不参与）；
    - 漂移量非正/非法 = 该方向关闭（返回原状态的拷贝）——刻意不走
      bump_* 的"非法回落默认量"契约，否则配置 0（想关）会变成最大漂移。
    权重设计（v4.1.0 二次调参：用户要求降关键词、升热聊）：hot 单条即注入
    （0.2 ≥ 渲染地板 0.15）、cold 两条起注入（0.10→0.16）；稳态
    hot ≈0.50 / cold ≈0.25——热聊是情绪的**主导来源**（持续热聊的积累
    远超零星关键词），cold 刻意低于 hot（负面情绪建得比正面慢），
    均低于 0.45 的 sulky"明显情绪"档（appy 无分档）。
    """
    if not isinstance(heat, str) or heat not in ("hot", "cold"):
        return dict(state) if _valid(state) else neutral_state()
    try:
        amount = float(hot_drift if heat == "hot" else cold_drift)
    except (TypeError, ValueError):
        return dict(state) if _valid(state) else neutral_state()
    if amount <= 0:
        return dict(state) if _valid(state) else neutral_state()
    if heat == "hot":
        return bump_appy(state, amount)
    return bump_sulky(state, amount)


def parse_soothe_words(raw) -> list:
    """解析安抚词配置（逗号/中文逗号分隔，去空白）；空配置回落默认池。"""
    return [
        w.strip()
        for w in str(raw or "").replace("，", ",").split(",")
        if w.strip()
    ]


def decay_raw(state, factor) -> dict:
    """逐条衰减（无地板版，v4.1.0 组合链专用）：只乘系数、不判 NEUTRAL_FLOOR。

    地板是推进链外的事——渲染层（emotion_directive / emotion_short）自带
    过滤；若在衰减中间步判地板，会把亚地板残值清零、漂移增量整体被吞
    （情绪身份被打回 neutral、跨消息累加断链，v4.1.0 实测教训）。
    单独使用请用 decay()（带地板语义，既有契约不变）。
    """
    if not _valid(state):
        return neutral_state()
    return _make(state["emotion"], float(state["intensity"]) * _decay_factor_value(factor))


def decay_time_raw(state, elapsed_seconds, half_life_hours: float = 8.0) -> dict:
    """时间衰减（无地板版，v4.1.0 组合链专用）：只乘半衰期因子、不判 NEUTRAL_FLOOR。

    与 decay_raw 同理：组合链中间步判地板会把亚地板残值清零（漂移增量
    被吞、累加断链——写回会打 ts，下一条消息必经时间衰减步，地板必须
    只留在渲染层与单独调用的 decay_time()）。时钟防御与 decay_time 一致：
    elapsed 非法/NaN/负数不衰减（时钟回拨防御）、half_life<=0 视为关闭。
    """
    if not _valid(state):
        return neutral_state()
    try:
        elapsed = float(elapsed_seconds)
    except (TypeError, ValueError):
        return dict(state)
    if elapsed != elapsed or elapsed <= 0:  # NaN / 时钟回拨：不衰减
        return dict(state)
    try:
        half = float(half_life_hours)
    except (TypeError, ValueError):
        half = 8.0
    if half <= 0:  # 关闭开关
        return dict(state)
    factor = 0.5 ** (elapsed / (half * 3600.0))
    return _make(state["emotion"], float(state["intensity"]) * factor)


def decay_and_soothe(
    baseline,
    text,
    *,
    now_ts: float,
    half_life_base_hours: float = 8.0,
    absent_tier_days: float = 2.0,
    absent_half_life_hours: float = 48.0,
    decay_factor: float = 0.6,
    soothe_words=None,
    heat: str = "warm",
    prev_seen_ts=None,
    hot_drift: float = 0.2,
    cold_drift: float = 0.10,
    soothe_boost: float = 0.2,
) -> dict:
    """用户每发言一次的情绪推进（纯函数，v4.0 Phase 6 从 main._track_activity 下沉）。

    顺序契约（不可换）：时间衰减（v3.7.0，按 ts 真实流逝 + v3.8.0 分档半衰期）
    → 逐条衰减 → 热度漂移（v4.1.0，hot→appy / cold→sulky）→ 安抚命中转 appy
    （量级 = soothe_boost：默认 0.2 ≈ 一条热聊；非正/NaN = 安抚词不参与，
    与 heat_drift 的"0=关方向"同契约；无法解析才回落默认——v4.1.0 权重调整）。
    时间衰减在先保证"隔了半天回来情绪随时间淡去"；热度漂移在安抚之前、
    安抚保持在最后，保证"冷却中的安抚依然能被感知"且明说的好话总能赢下基调。

    v4.1.0 初见守卫：prev_seen_ts 缺失/非正（新会话第一条、或时间表无记录）
    时 heat 一律按 warm 处理——rhythm_heat 对无记录会话返回 cold，但那是
    "初见"不是"冷场"，首条消息不能摆脸色。

    - baseline 为会话内存态（无记录时应传 neutral_state()）；
    - heat 由调用方按节奏引擎同源（_prev_seen 快照）计算后传入；
    - 强度封顶（emotion_intensity_cap）刻意留给调用方，便于 cap 契约单点钉死；
    - 返回值供调用方与 baseline 比较决定是否写回（时间衰减单独生效时
      返回值可能恰等于时间衰减后的中间态，但相对内存仍是变化）。
    """
    st0 = baseline if _valid(baseline) else neutral_state()
    old = st0
    emo_elapsed = 0.0
    emo_ts = old.get("ts")
    if isinstance(emo_ts, (int, float)) and emo_ts > 0:
        emo_elapsed = now_ts - emo_ts
    half_life = resolve_half_life_hours(
        emo_elapsed, half_life_base_hours, absent_tier_days, absent_half_life_hours
    )
    if half_life > 0 and emo_elapsed > 0:
        old = decay_time_raw(old, emo_elapsed, half_life)
    # 逐条衰减：走无地板的 decay_raw（地板语义见其 docstring——中间判地板
    # 会吞掉漂移增量；decay() 单独调用的地板契约保持不变）。
    st = decay_raw(old, decay_factor)
    try:
        prev_ts = float(prev_seen_ts)
    except (TypeError, ValueError):
        prev_ts = 0.0
    effective_heat = heat if prev_ts > 0 else "warm"
    st = heat_drift(st, effective_heat, hot_drift, cold_drift)
    if hit_soothe(text, soothe_words or None):
        # v4.1.0 权重调整：安抚命中仍最后执行（方向获胜、sulky→appy），
        # 但量级从固定 0.4 降为可配的 soothe_boost（默认 0.2 ≈ 一条热聊
        # 消息的漂移）——关键词从"一锤定音的主导事件"降格为"与一条热聊
        # 同量级的加分项"，情绪基调由对话热度主导。
        # 契约与 heat_drift 对齐（审查轮修复）：boost 非正/NaN = 安抚词
        # 完全不参与（不增量也不转方向，sulky 会话里说"哈哈"也维持原状）；
        # 无法解析（非数字）才回落默认 0.2——面板填 0 就是关，不是默认量。
        try:
            boost = float(soothe_boost)
        except (TypeError, ValueError):
            boost = 0.2
        if boost > 0:
            st = bump_appy(st, boost)
    # 组合链刻意不做地板重置（时间衰减 decay_time_raw / 逐条衰减 decay_raw
    # 均为无地板变体）：亚地板残值跨消息累积才是"惯性"——渲染层
    # （emotion_directive / emotion_short）自带 NEUTRAL_FLOOR 过滤，低于
    # 地板的状态存而不显；decay()/decay_time() 单独调用仍带地板语义
    # （既有契约不变）。⚠️ 无地板残值消费者见 reunion_directive /
    # cold_war_proactive_directive 的地板守卫（亚地板与 neutral 同权）。
    return st


def _decay_factor_value(factor) -> float:
    """衰减系数安全取值（0< f ≤1，非法回落 0.6）；与 decay() 同规则。"""
    try:
        f = float(factor)
    except (TypeError, ValueError):
        return 0.6
    if not (0.0 < f <= 1.0):
        return 0.6
    return f


__all__ = [
    "COLD_WAR_STAGES",
    "DEFAULT_COLD_WAR_THRESHOLDS_DAYS",
    "DEFAULT_SOOTHE_WORDS",
    "EMOTIONS",
    "NEUTRAL_FLOOR",
    "REUNION_LABELS",
    "bump_appy",
    "bump_sulky",
    "cold_war_proactive_directive",
    "decay_and_soothe",
    "heat_drift",
    "parse_soothe_words",
    "cold_war_stage",
    "decay",
    "decay_raw",
    "decay_time",
    "decay_time_raw",
    "emotion_directive",
    "emotion_short",
    "hit_soothe",
    "neutral_state",
    "parse_thresholds_days",
    "resolve_half_life_hours",
    "reunion_directive",
]
