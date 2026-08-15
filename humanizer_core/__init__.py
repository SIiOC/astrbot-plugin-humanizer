# -*- coding: utf-8 -*-
"""
AI 回复人性化核心模块。

将 Humanizer-zh 与 stop-slop 两个技能的规则整合为统一的文本处理入口：
- 自动检测文本语言（中文/英文）
- 中文走 rules_zh（Humanizer-zh 的 24 种模式）
- 英文走 rules_en（stop-slop 的 core rules + references）
- 可选 LLM 深度改写提示词见 prompt.py

语言检测说明：以 CJK 字符占有效字符比例 >= 0.3 判定中文。混排文本可能误判，
因此规则设计上保证副作用最小（例如空白折叠不再触碰换行），
即使误判到另一语言规则集，也只做保守的机械清理，不会破坏原文结构。
"""

import re

from . import rules_en, rules_zh
from .prompt import SYSTEM_PROMPT

__all__ = [
    "humanize_text",
    "humanize_text_detailed",
    "detect_language",
    "should_skip_conversa",
    "is_blank",
    "SYSTEM_PROMPT",
]

# conversa 插件系统触发的用户消息标记（命中时整条链路跳过）：
# - "[Conversa主动发起对话]"：conversa main.py 1862 行保存主动回复历史时写入的用户消息
# - "[conversa主动回复请求"：线上补充的形态（前缀匹配，未闭合的方括号也覆盖）
# 此类系统生成的问候/提示不应进入去 AI 味处理，新形态直接在此追加即可。
CONVERSA_SKIP_MARKERS = (
    "[Conversa主动发起对话]",
    "[conversa主动回复请求",
)


def should_skip_conversa(event_text) -> bool:
    """判断用户消息是否带 conversa 系统触发标记。

    供 main.py 的 on_llm_response 钩子在处理前调用：命中则整个插件跳过
    （规则清理与 LLM 改写都不执行）。None/空文本返回 False（由空白防御兜底）。
    """
    if not event_text:
        return False
    return any(marker in event_text for marker in CONVERSA_SKIP_MARKERS)


def is_blank(text) -> bool:
    """判断文本是否为空或纯空白。

    改写链路防御：定时触发场景下模型可能输出空文本，若把空白文本发给改写
    模型，模型会自行造一句（如「没有收到需要处理的文本」）并被当成正式回复，
    即无中生有事故。钩子与 _llm_rewrite 入口都应先经此检查。
    """
    return text is None or not str(text).strip()

# CJK 统一表意文字及其扩展区
_CJK_RE = re.compile(
    "[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\U00020000-\U0002a6df]"
)
# 有效字符（字母 + CJK）：数字、标点、空白都不参与比例计算——
# 否则日期/数字区间（如 "2020——2026"）会稀释 CJK 占比导致中文误判成英文
_LETTER_RE = re.compile(r"[A-Za-z\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\U00020000-\U0002a6df]")
# 中文判定阈值与最小汉字数：少于 2 个汉字（如 "Hello 猫"）不算中文文本
_CJK_THRESHOLD = 0.25
_CJK_MIN_COUNT = 2


def detect_language(text: str) -> str:
    """检测文本语言。

    以"字母 + CJK"为有效字符，CJK 占比 >= 0.25 且至少 2 个汉字时判定为中文。
    数字/标点/空白不参与计算，避免 "2020——2026"、混排文本稀释 CJK 占比而误判。
    返回 "zh" 或 "en"。
    """
    if not text:
        return "en"
    letters = "".join(_LETTER_RE.findall(text))
    if not letters:
        return "en"
    cjk_count = len(_CJK_RE.findall(letters))
    if cjk_count < _CJK_MIN_COUNT:
        return "en"
    return "zh" if (cjk_count / len(letters)) >= _CJK_THRESHOLD else "en"


def _emoji_only_removal(text: str) -> str:
    """仅移除表情符号（作为独立阶段，供命中检测与调试日志使用）。"""
    return rules_zh.remove_emoji(text)


def _run_stages(text: str, stages) -> list[str]:
    """依次执行规则阶段，返回实际发生变化的阶段名列表。"""
    hits = []
    current = text
    for name, fn in stages:
        result = fn(current)
        if result != current:
            hits.append(name)
            current = result
    return current, hits


def humanize_text(text: str, remove_emoji: bool = True) -> str:
    """对文本执行规则化人性化处理。

    Args:
        text: 待处理的文本。
        remove_emoji: 是否移除表情符号。

    Returns:
        处理后的文本（处理前后无变化时返回原文）。
        需要命中阶段信息时请使用 humanize_text_detailed。
    """
    result, _ = humanize_text_detailed(text, remove_emoji=remove_emoji)
    return result


def humanize_text_detailed(
    text: str, remove_emoji: bool = True
) -> tuple[str, list[str]]:
    """同 humanize_text，但总是返回 (结果文本, 命中阶段列表)。"""
    if not text:
        return text, []

    original = text
    current = text
    hits: list[str] = []

    if remove_emoji:
        current = _emoji_only_removal(current)
        if current != original:
            hits.append("emoji")

    lang = detect_language(current)
    if lang == "zh":
        current, stage_hits = _run_stages(current, rules_zh.ZH_STAGES)
    else:
        current, stage_hits = _run_stages(current, rules_en.EN_STAGES)
    hits.extend(stage_hits)

    # 处理无变化时返回原文，避免误报
    final = current.strip() if current != original else original
    # 防御：整段被规则删空时返回原文，避免把 AI 回复清空
    if not final:
        final = original
    return final, hits
