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
from datetime import datetime, time

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


def build_proactive_prompt(
    template: str,
    persona: str,
    last_user: str = "",
    last_ai: str = "",
    fallback_persona: str = "你是一个贴心、自然的聊天伙伴。",
) -> str:
    """拼接主动聊天的最终提示词。

    - persona 非空时替换模板里的 {persona} 占位符（用户配置的人设）；
      persona 为空时使用 fallback_persona 兜底。
    - {last_user}/{last_ai} 替换为最近聊天上下文。
    - 模板缺占位符或 format 失败时原样返回模板（不抛异常）。
    """
    filled_persona = persona.strip() or fallback_persona
    try:
        return template.format(
            persona=filled_persona,
            last_user=last_user or "",
            last_ai=last_ai or "",
        )
    except (KeyError, IndexError, ValueError):
        return template


def extract_last_messages(history_raw, max_chars: int = 200) -> tuple[str, str]:
    """从会话历史原始数据提取最近一条用户消息与 AI 消息文本。

    Args:
        history_raw: Conversation.history 的值（JSON 字符串，或已是 list）。
        max_chars: 单条消息截断长度。

    Returns:
        (last_user, last_ai)；无有效内容时为空串。任何解析失败都返回空串，
        不抛异常（调用方拿空串继续走兜底）。
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
            if role == "user" and not last_user:
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
)
_QUOTE_CHARS = ("「", "」", '"', "“", "”")


def is_plausible_greeting(text: str) -> bool:
    """判断主动消息生成结果是否像一句正常问候（而非内部推理/记录回顾）。

    任一异常信号命中即返回 False（调用方应放弃本次发送）：
      1. 文本过长（> 80 字，问候通常一两句）；
      2. 含引号/「」引用（引用用户原话做分析，不是问候）；
      3. 含记录回顾词（"根据以往记录""我已回复"等推理特征）。

    宁可漏发也不误发——主动消息是可选项，发不出比发错内容打扰用户好。
    """
    if not text:
        return False
    if len(text) > _MAX_GREETING_CHARS:
        return False
    if any(q in text for q in _QUOTE_CHARS):
        return False
    if any(w in text for w in _REASONING_SIGNAL_WORDS):
        return False
    return True
