# -*- coding: utf-8 -*-
"""
主动聊天（用户沉默后自然续聊）的触发判定模块。

负责：免打扰时段判定、随机延迟计算、提示词拼接、上下文提取、思维链剥离与问候校验。
不依赖 astrbot，全部为纯函数，便于单元测试。

只实现"何时该主动发"的判断，发送/生成由 main.py 负责。
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime, time, timedelta

# 最小延迟（分钟）：避免频繁打扰
MIN_DELAY_MINUTES = 30

_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(s: str) -> tuple[int, int] | None:
    """解析 "HH:MM" 格式，返回 (小时, 分钟)；非法输入返回 None。"""
    if not s:
        return None
    m = _HHMM_RE.match(s.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def in_quiet(now: datetime, quiet: str) -> bool:
    """当前时间是否在免打扰时段内（支持跨天与多段）。

    quiet 支持一个或多个时间段，逗号分隔，如 "01:00-07:00" 或
    "01:00-07:00, 12:00-13:00"；任一时间段命中即视为在免打扰内。
    空串或格式非法返回 False（不打扰）。
    """
    if not quiet or "-" not in quiet:
        return False
    nt = now.time()
    for segment in quiet.split(","):
        segment = segment.strip()
        if "-" not in segment:
            continue
        a, b = segment.split("-", 1)
        p1 = parse_hhmm(a)
        p2 = parse_hhmm(b)
        if not p1 or not p2:
            continue
        t1 = time(p1[0], p1[1])
        t2 = time(p2[0], p2[1])
        if t1 <= t2:
            if t1 <= nt <= t2:
                return True
        else:
            # 跨天：如 22:00-07:00，22:00 之后或 07:00 之前都在免打扰内
            if nt >= t1 or nt <= t2:
                return True
    return False


def next_quiet_end(now: datetime, quiet: str) -> datetime | None:
    """返回当前时刻所在免打扰时段的结束时刻；当前不在任何时段返回 None。

    与 in_quiet 同一套时段解析（复用 parse_hhmm），用于"免打扰内到期
    的主动消息显式重排到免打扰结束后触发"：

    - 同天时段（t1<=t2）返回当天结束时刻；
    - 跨天时段（t1>t2）中，晚间段（now>=t1）结束在次日，凌晨段（now<=t2）
      结束在当天；
    - 同时命中多段（边界重叠）时取结束最晚的；
    - quiet 为空/非法/当前不在任何时段返回 None（调用方跳过重排）。
    """
    if not quiet or "-" not in quiet:
        return None
    nt = now.time()
    ends: list[datetime] = []
    for segment in quiet.split(","):
        segment = segment.strip()
        if "-" not in segment:
            continue
        a, b = segment.split("-", 1)
        p1 = parse_hhmm(a)
        p2 = parse_hhmm(b)
        if not p1 or not p2:
            continue
        t1 = time(p1[0], p1[1])
        t2 = time(p2[0], p2[1])
        if t1 <= t2:
            if not (t1 <= nt <= t2):
                continue
            ends.append(
                datetime(now.year, now.month, now.day, p2[0], p2[1])
            )
        else:
            if not (nt >= t1 or nt <= t2):
                continue
            if nt <= t2:
                # 凌晨段（00:00 ~ t2）：结束在当天
                end_day = now.date()
            else:
                # 晚间段（t1 ~ 23:59）：结束在次日
                end_day = now.date() + timedelta(days=1)
            ends.append(
                datetime(end_day.year, end_day.month, end_day.day, p2[0], p2[1])
            )
    if not ends:
        return None
    return max(ends)


def compute_next_delay(
    base_minutes: int, fluctuation_minutes: int = 0, *, rng: random.Random | None = None
) -> int:
    """计算下一次触发延迟（分钟）：base ± fluctuation 随机波动，下限 30 分钟。

    fluctuation_minutes 为 0 或负数时不做波动（固定 base，仍受下限约束）。
    """
    rng = rng or random
    base = max(int(base_minutes), MIN_DELAY_MINUTES)
    if fluctuation_minutes > 0:
        base += rng.randint(-fluctuation_minutes, fluctuation_minutes)
    return max(base, MIN_DELAY_MINUTES)


def user_interjected_during(started_ts: float, last_user_ts: float | None) -> bool:
    """插话丢弃判定（v3.2）：started_ts 之后用户是否发过言。

    主动消息生成耗时数十秒，期间用户发言则放弃发送。last_user_ts 来自
    _track_activity 打点；防抖合并会使信号晚到几秒，但"是否存在更晚
    发言"的比较不受影响。started_ts 非法（0/负）时保守返回 False。
    """
    if not started_ts or started_ts <= 0:
        return False
    return bool(last_user_ts and last_user_ts > started_ts)


def _sanitize_quote(text: str) -> str:
    """把注入引用区的聊天内容转义：换行→空格、『「」』→『「」』全角变体。

    v2.2.2 安全：last_user/last_ai 是用户可控文本，若含未转义的 」/换行会
    跳出模板的「」引用围栏，把用户消息变成指令行。这里统一转义，任何模板
    下都安全（自定义模板同样受益）。
    """
    if not text:
        return text
    # 换行/制表折叠为空格（防跳行）
    t = " ".join(str(text).split())
    # 引号字符替换为全角变体（防闭合引用围栏）
    t = t.replace("」", "』").replace("「", "『")
    t = t.replace("”", "’").replace("“", "‘")
    return t


# 主动消息时间感知：投递时刻（生成即投递）写入当前时间与自然时段，让模型按
# "实际送达时刻"调整问候语境——修复免打扰压单后凌晨生成的内容在早晨送达的
# 时间错位。时段划分与 time_flow 的 _NATURAL_SLOTS 一致。
_NATURAL_SLOTS = (
    (0, 6, "凌晨"),
    (6, 9, "早上"),
    (9, 12, "上午"),
    (12, 14, "中午"),
    (14, 18, "下午"),
    (18, 20, "傍晚"),
    (20, 23, "晚上"),
    (23, 24, "深夜"),
)
_WEEKDAY_CN = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def time_slot_of(now: datetime) -> str:
    """返回当前时刻的自然时段名（凌晨/早上/上午/中午/下午/傍晚/晚上/深夜）。"""
    minute = now.hour * 60 + now.minute
    for start, end, name in _NATURAL_SLOTS:
        if start * 60 <= minute < end * 60:
            return name
    return "深夜"  # 兜底（正常不会走到）


def current_time_block(now: datetime) -> str:
    """生成投递时刻的时间指令块（主动消息 prompt 末尾追加，v2.4.0）。

    给模型当前精确时间与自然时段，并显式要求按当下时段调整问候——
    否则免打扰压单后（凌晨触发、早晨送达）模型会依据历史「晚安」语境
    继续产出睡前内容。
    """
    slot = time_slot_of(now)
    wd = _WEEKDAY_CN[now.weekday()]
    return (
        f"\n\n【当前时间】现在是 {now.year}年{now.month:02d}月{now.day:02d}日 "
        f"{wd} {now.hour:02d}:{now.minute:02d}（{slot}）。"
        "请先看一眼上面的时间再开口：若已是早晨/白天，就按早晨/白天的问候与"
        "话题来，不要沿用深夜的『晚安』『睡啦』这类睡前语境；若确在深夜，"
        "才可用晚安类内容。"
    )


def build_proactive_prompt(
    template: str,
    persona: str,
    last_user: str = "",
    last_ai: str = "",
    unanswered_count: int = 0,
    silence_hours: int = 0,
    fallback_persona: str = "你是一个贴心、自然的聊天伙伴。",
    current_time: str = "",
    life: str = "",
) -> str:
    """拼接主动聊天的最终提示词。

    - persona 非空时替换模板里的 {persona} 占位符（用户配置的人设）；
      persona 为空时使用 fallback_persona 兜底。
    - {last_user}/{last_ai} 替换为最近聊天上下文（v2.2.2：注入前转义
      换行与引号，防止用户消息跳出引用围栏）。
    - {unanswered_count}/{silence_hours}（v2.2.0 可选）替换为连续未回复
      主动消息的次数与用户静默时长（小时）；模板不含这些占位符时
      多余 kwargs 被 format 忽略，旧模板行为不变。
    - current_time（v2.4.0 可选）：投递时刻的时间指令块（current_time_block
      的输出）。非空时无条件追加在模板末尾——不依赖模板占位符，自定义模板
      同样生效；为空时行为与旧版完全一致（回归安全）。
    - life（v2.5 可选）：动态一天状态块（build_life_context 的输出）。
      仅当模板含 {life} 占位符时替换——主动消息走 Agent Pipeline 时
      on_llm_request 钩子已把生活状态注入 LLM 请求，这里不重复无条件追加，
      只在用户模板显式引用时生效。
    - 模板缺占位符或 format 失败时原样返回模板（不抛异常）。
    """
    filled_persona = persona.strip() or fallback_persona
    try:
        filled = template.format(
            persona=filled_persona,
            last_user=_sanitize_quote(last_user),
            last_ai=_sanitize_quote(last_ai),
            unanswered_count=max(int(unanswered_count or 0), 0),
            silence_hours=max(int(silence_hours or 0), 0),
            life=life,
        )
    except (KeyError, IndexError, ValueError):
        return template
    if current_time:
        return filled + current_time
    return filled


def build_pout_directive(unanswered: int, silence_hours: int = 0) -> str:
    """生成"未回复小情绪"指令块（追加在主动消息提示词末尾）。

    unanswered < 1 时返回空串（首条主动消息不带情绪，开关只影响追发）。
    指令约束：微微生气/小委屈、可爱不刻薄、一两句、不用引号、不重复上次
    句式——措辞同时避开 is_plausible_greeting 的引号与信号词拦截特征。
    """
    try:
        n = max(int(unanswered or 0), 0)
        hours = max(int(silence_hours or 0), 0)
    except (TypeError, ValueError):
        return ""
    if n < 1:
        return ""
    silence_note = f"（距你上次主动联系约 {hours} 小时）" if hours > 0 else ""
    return (
        f"\n\n【补充要求】这已经是你第 {n + 1} 次主动联系对方{silence_note}，"
        "对方一直没有回复你。这次请带一点点小情绪——像被晾在一边的"
        "微微生气或小委屈（类似怎么又不理我了这种感觉），"
        "但仍然可爱、不刻薄、不指责。要求：只用一两句话；不要使用任何引号；"
        "不要重复你上一次主动消息的句式和说法。"
    )


def parse_proactive_state(data) -> tuple[dict, dict, dict]:
    """解析主动聊天持久化状态文件内容（纯函数，供离线测试）。

    兼容两种格式：
    - v2（v2.2.0+）：{"v":2,"triggers":{umo:ts},...,"unanswered":{umo:int},
      "last_user_ts":{umo:ts}}——按字段读取，缺字段回空/默认。
    - 旧扁平（≤v2.1.2）：{umo: ts}——视为 triggers，计数全 0、
      last_user_ts 缺省（umo 永远是 platform:MessageType:session_id 形态，
      不会与保留键 "v"/"triggers"/"unanswered"/"last_user_ts" 冲突）。

    判定规则（v2.2.1）：只要出现任一保留键（"v"/"triggers"/"unanswered"/
    "last_user_ts"）即按 v2 语义解析——triggers 缺失/损坏时回空，绝不落入
    旧扁平分支把保留键当会话名（否则会产生每周期尝试发送的幽灵会话 "v"）。

    返回 (triggers, unanswered, last_user_ts)；输入非法（None/非 dict/
    结构损坏）一律返回三个空 dict，不抛异常。
    """
    empty: tuple[dict, dict, dict] = ({}, {}, {})
    if not isinstance(data, dict):
        return empty
    try:
        _RESERVED = ("v", "triggers", "unanswered", "last_user_ts")
        if any(k in data for k in _RESERVED):
            # v2 语义：按字段读取，非 dict 字段一律回空
            raw_triggers = data.get("triggers")
            raw_unanswered = data.get("unanswered")
            raw_last_user = data.get("last_user_ts")
            if not isinstance(raw_triggers, dict):
                raw_triggers = {}
            if not isinstance(raw_unanswered, dict):
                raw_unanswered = {}
            if not isinstance(raw_last_user, dict):
                raw_last_user = {}
            triggers = {
                str(k): float(v)
                for k, v in raw_triggers.items()
                if isinstance(k, str) and isinstance(v, (int, float))
                and not isinstance(v, bool)
            }
            unanswered = {
                str(k): max(int(v), 0)
                for k, v in raw_unanswered.items()
                if isinstance(k, str) and isinstance(v, (int, float))
                and not isinstance(v, bool)
            }
            last_user_ts = {
                str(k): float(v)
                for k, v in raw_last_user.items()
                if isinstance(k, str) and isinstance(v, (int, float))
                and not isinstance(v, bool)
            }
            return triggers, unanswered, last_user_ts
        # 旧扁平格式（无任何保留键）
        triggers = {
            str(k): float(v)
            for k, v in data.items()
            if isinstance(k, str) and isinstance(v, (int, float))
            and not isinstance(v, bool)
        }
        return triggers, {}, {}
    except (TypeError, ValueError):
        return empty


# 历史写回的主动消息标记前缀（main._save_proactive_history 写入）。
# 提取上下文时跳过带此标记的 user 消息——那是插件代发的"假用户消息"，
# 不是用户真实发言（v2.2.1：此前会把标记文本当成"用户最后说"污染上下文）。
_PROACTIVE_HISTORY_MARKER = "[主动消息]"


def extract_last_messages(history_raw, max_chars: int = 200) -> tuple[str, str]:
    """从会话历史原始数据提取最近一条用户消息与 AI 消息文本。

    Args:
        history_raw: Conversation.history 的值（JSON 字符串，或已是 list）。
        max_chars: 单条消息截断长度。

    Returns:
        (last_user, last_ai)；无有效内容时为空串。任何解析失败都返回空串，
        不抛异常（调用方拿空串继续走兜底）。

    user 消息中带 [主动消息] 标记的是插件写回的代发记录，跳过之——
    连续主动追问时"用户最后说"仍取用户真实话语（可能为更早的消息）。
    """
    last_user, last_ai = "", ""
    try:
        history = (
            json.loads(history_raw) if isinstance(history_raw, str) else history_raw
        )
        if not isinstance(history, list):
            return last_user, last_ai
        for msg in reversed(history):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                # 多模态内容块：提取 text 段拼接
                content = " ".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            text = str(content)[:max_chars] if content else ""
            if role == "user":
                if text.startswith(_PROACTIVE_HISTORY_MARKER):
                    # 插件代发的主动消息标记，不是用户真实发言
                    continue
                if not last_user:
                    last_user = text
            elif role == "assistant" and not last_ai:
                last_ai = text
            if last_user and last_ai:
                break
    except (ValueError, TypeError, json.JSONDecodeError):
        pass
    return last_user, last_ai


# 思维链标记：用于剥离模型思考内容（发送前防御）
# - 🤔 思考: ...（框架 result_decorate 注入格式）
# - <thinking>...</thinking> / <reasoning>...</reasoning>（Anthropic/DeepSeek 常见）
# - 文本开头 "思考：/思考:" 的整段
_REASONING_PREFIX = re.compile(r"^\s*(?:🤔\s*)?思考[:：]\s*", re.I)
_REASONING_BLOCKS = [
    re.compile(r"<thinking>.*?</thinking>", re.S),
    re.compile(r"<reasoning>.*?</reasoning>", re.S),
    re.compile(r"\[/?Reasoning\]", re.I),
]


def strip_reasoning_markers(text: str) -> str:
    """剥离文本中残留的思维链内容（发送前防御）。

    推理模型的 completion_text 可能残留思考内容（如 "🤔 思考: ..." 注入、
    "<thinking>...</thinking>" 包裹、或 "思考：..." 开头段）。
    只剥离明确标记的内容，不误删正常正文；无标记时原样返回。
    """
    if not text:
        return ""
    for pat in _REASONING_BLOCKS:
        text = pat.sub("", text)
    # 处理 "思考：..." 开头的整段（到第一个空行或结尾）
    m = _REASONING_PREFIX.match(text)
    if m:
        rest = text[m.end():]
        # 找第一个空行作为段落边界；没有则整段视为思考
        split = rest.split("\n\n", 1)
        if len(split) > 1:
            text = split[1].strip()
        else:
            text = ""
    return text.strip()


# 主动消息"问候合理性"校验：以下特征说明生成结果不是问候，而是模型的
# 内部推理/记录回顾（deepseek 等推理模型常把思考直接当正文输出，无标记可剥离）
# - 引用用户原话做分析（「...」）
# - 记录回顾词（"根据以往记录""我已回复"等）
_MAX_GREETING_CHARS = 80
_REASONING_SIGNAL_WORDS = (
    "根据以往记录",
    "以往记录",
    "我已回复",
    "记录显示",
    "确认库存",
    "之前的对话",
    "刚才说了",
    "综上所述",
    "总结一下",
    "分析如下",
    # 内部决策用语：agent 推理自己该不该发消息时常用
    "按规则",
    "不发了",
    "不发了，",
    "等他先开口",
    "等他回来",
    "等他",
    "保持沉默",
    "沉默规则",
    "不主动发",
    "不该说",
    "这时候硬找",
    "反而",
    "就不发",
    "就不打扰",
    "先不开口",
    "轮不到",
)
_QUOTE_CHARS = ("「", "」", '"', "“", "”")
# 引用用户原话的特征：成对引号且内文较长（≥5 字）。单词级口癖（如「好耶」）
# 是风格注入教模型的正常表达，不构成引用，不应触发误杀。
_QUOTED_REFERENCE_RES = (
    re.compile(r"「([^「」]{5,})」"),
    re.compile(r"“([^“”]{5,})”"),
    re.compile(r'"([^"]{5,})"'),
)


def _has_quoted_reference(text: str) -> bool:
    """判断文本是否含"引用原话式"引号（成对且内文 ≥5 字）。

    用于问候校验：引用用户原话做分析（如 你之前说「我今天中午想吃火锅」）
    说明是内部推理回顾；而口癖级短引用（如 又说「好耶」）是正常语气词。
    """
    return any(rx.search(text) for rx in _QUOTED_REFERENCE_RES)


def is_plausible_greeting(text: str) -> bool:
    """判断主动消息生成结果是否像一句正常问候（而非内部推理/记录回顾）。

    任一异常信号命中即返回 False（调用方应放弃本次发送）：
      1. 文本过长（> 80 字，问候通常一两句）；
      2. 含"引用原话式"引号（成对引号且内文 ≥5 字，如引用用户原话做分析；
         单词级口癖短引用不触发——v2.2.1 放宽，此前任意引号字符即拒，
         会把风格档案注入的口癖表达成批误杀）；
      3. 含记录回顾词（"根据以往记录""我已回复"等推理特征）。

    宁可漏发也不误发——主动消息是可选项，发不出比发错内容打扰用户好。
    """
    if not text:
        return False
    if len(text) > _MAX_GREETING_CHARS:
        return False
    if _has_quoted_reference(text):
        return False
    if any(w in text for w in _REASONING_SIGNAL_WORDS):
        return False
    return True


def was_already_sent_by_agent(event: object) -> bool:
    """判断 agent 是否已在本次运行中通过发消息工具直发过回复。

    工具成功直发后，AstrBot 会在事件上置位 _has_send_oper
    （astrbot/core/tools/message_tools.py）。此时插件若再用最终文本走一遍
    发送管线，会因最终文本与工具文本不一致而绕过框架去重（respond/stage.py
    只在文本完全一致时跳过），导致同一轮消息双发——调用方应跳过管线发送、
    只写回历史。用 getattr 防御旧框架无此属性的情况。
    """
    return bool(getattr(event, "_has_send_oper", False))


class ProactiveInFlightGuard:
    """主动聊天并发保护：同一实例内，同一会话 in-flight 时拒绝重复触发。

    注意（v2.2.1 修正表述）：本守卫是实例级对象，**不提供跨实例（热重载
    新老实例并存）防护**——热重载双发的真正防线是 _proactive_loop 在发送
    前先重排触发时间（旧实例落盘的不会是"已到期"时间）。守卫在此兜底
    单实例内的重入（如未来改为并发调度时），正常单实例顺序调度下不会命中。
    """

    def __init__(self) -> None:
        self._inflight: set[str] = set()

    def try_acquire(self, umo: str) -> bool:
        """尝试占用该会话；已被占用（并发触发中）返回 False。"""
        if umo in self._inflight:
            return False
        self._inflight.add(umo)
        return True

    def release(self, umo: str) -> None:
        self._inflight.discard(umo)

    def is_inflight(self, umo: str) -> bool:
        return umo in self._inflight
