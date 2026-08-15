# -*- coding: utf-8 -*-
"""
英文 AI 痕迹清理规则。

基于 stop-slop（core rules + references/phrases.md + references/structures.md）。
只处理高置信度的机械痕迹，保守设计：不删除在对话中可能有实际意义的词
（如 just、really），不重写句子结构。

本模块不依赖 astrbot，纯 Python 实现，便于本地单元测试。
"""

import re

# ---------------------------------------------------------------------------
# 1. Throat-Clearing Openers（喉清式开场）
# ---------------------------------------------------------------------------
_THROAT_CLEARING = [
    re.compile(r"^(Here's the thing\s*[:]\s*)", re.I),
    re.compile(r"^(Here's what [^.]*?[:]\s*)", re.I),
    re.compile(r"^(Here's why [^.]*?[:]\s*)", re.I),
    re.compile(r"^(The uncomfortable truth is[,\s]+)", re.I),
    re.compile(r"^(It turns out( that)?[,\s]+)", re.I),
    re.compile(r"^(The real [^.]*? is\s*[:]?\s*)", re.I),
    re.compile(r"^(Let me be clear\s*[:]?\s*)", re.I),
    re.compile(r"^(The truth is[,\s]+)", re.I),
    re.compile(r"^(I'll say it again\s*[:]\s*)", re.I),
    re.compile(r"^(I'm going to be honest[,\s]+)", re.I),
    re.compile(r"^(Can we talk about[,\s]+)", re.I),
    re.compile(r"^(Here's what I find interesting\s*[:]\s*)", re.I),
    re.compile(r"^(Here's the problem though\s*[:]\s*)", re.I),
    re.compile(r"^(Look[,\s]+)", re.I),
    # "Simply put," 是固定短语，整体删除（只删副词会留下破碎的 "Put,"）
    re.compile(r"^(Simply put\s*[,:：]\s*)", re.I),
]

# ---------------------------------------------------------------------------
# 2. Emphasis Crutches（强调拐杖）
# ---------------------------------------------------------------------------
_EMPHASIS_CRUTCHES = [
    re.compile(r"\s*Full stop\.", re.I),
    re.compile(r"\s*Period\.", re.I),
    re.compile(r"\s*Let that sink in\.", re.I),
    re.compile(r"\s*Make no mistake\s*[:]?\s*", re.I),
    re.compile(r"\s*Here's why that matters\s*[:]?\s*", re.I),
    re.compile(r"\s*This matters because\s*", re.I),
]

# ---------------------------------------------------------------------------
# 3. Filler Phrases（填充短语）
# ---------------------------------------------------------------------------
_FILLERS = [
    re.compile(r"^(At its core[,\s]+)", re.I),
    re.compile(r"^(At the end of the day[,\s]+)", re.I),
    re.compile(r"^(When it comes to[,\s]+)", re.I),
    re.compile(r"^(In a world where[,\s]+)", re.I),
    re.compile(r"^(The reality is[,\s]+)", re.I),
    re.compile(r"^(It's worth noting( that)?[,\s]+)", re.I),
    re.compile(r"^(In today's [^,.]+?[,\s]+)", re.I),
    re.compile(r"^(In this section, we'll[^.]*\.\s*)", re.I),
    re.compile(r"^(As we'll see[,\s]+)", re.I),
]

# ---------------------------------------------------------------------------
# 4. Meta-Commentary（自我指涉旁白）
# ---------------------------------------------------------------------------
_META_COMMENTARY = [
    re.compile(r"^(Let me walk you through[^.]*\.\s*)", re.I),
    re.compile(r"^(I want to explore[^.]*\.\s*)", re.I),
    re.compile(r"^(You already know this, but[,\s]+)", re.I),
    re.compile(r"^(But that's another post\.?\s*)", re.I),
]

# ---------------------------------------------------------------------------
# 5. Business Jargon（商业行话替换表）
# ---------------------------------------------------------------------------
_JARGON_MAP = [
    (r"\bnavigate (?:the )?(challenges?|complexity)\b", "handle \1"),
    (r"\bunpack (analysis|the)\b", "explain \1"),
    (r"\blean into\b", "embrace"),
    (r"\blandscape\b", "situation"),
    (r"\bgame[- ]changer\b", "important change"),
    (r"\bdouble down on\b", "commit to"),
    (r"\bdeep dive into\b", "look at"),
    (r"\btake a step back\b", "reconsider"),
    (r"\bmoving forward\b", "next"),
    (r"\bcircle back\b", "revisit"),
    (r"\bon the same page\b", "aligned"),
]

# ---------------------------------------------------------------------------
# 6. Adverbs（高频空泛副词）——收敛后的保守清单
# ---------------------------------------------------------------------------
# 只保留最典型、几乎总是虚词强调的副词；移除在对话中常含实义的词：
# truly（truly believe）、deeply（deeply care）、honestly（honestly, I think）、
# genuinely（genuinely interested）等不再删除。
_ADVERBS = [
    r"\bliterally\b",
    r"\bsimply\b",
    r"\bfundamentally\b",
    r"\binherently\b",
    r"\binevitably\b",
    r"\binterestingly\b",
    r"\bimportantly\b",
    r"\bcrucially\b",
]

# 统一删除：空泛副词 + 可选逗号 + 尾随空白（任意位置）。
# 仅当被删副词位于句首（全文开头或句子边界后）时，将下一个字母大写，
# 保证句子规整；句中删除不改动原文大小写。
_ADVERB_PATTERN = re.compile(
    r"(^|[.!?]\s*)?(?:literally|simply|fundamentally|inherently|inevitably|interestingly|importantly|crucially)\b,?(\s+)([A-Za-z])",
    re.I,
)


def _clean_adverbs(text: str) -> str:
    def repl(m):
        head, space, nxt = m.group(1), m.group(2), m.group(3)
        if head is not None:
            return head + space + nxt.upper()
        return space + nxt

    return _ADVERB_PATTERN.sub(repl, text)

# ---------------------------------------------------------------------------
# 7. Em-Dash（破折号）
# ---------------------------------------------------------------------------
# 仅处理 em-dash（—）。en-dash（–）常用于数字/时间区间（如 2020–2026），
# 属于合法用法，一律保留。
# 中文破折号"——"两侧邻接汉字，不属于英文 em-dash 用法，即使语言检测
# 误判为英文也不应被替换（负向断言保护）。
_EM_DASH = re.compile(r"(?<![\u4e00-\u9fff])—(?![\u4e00-\u9fff])")


def _fix_em_dashes(text: str) -> str:
    """把 em-dash 替换为逗号（保留前后空格则用", "）。"""
    return _EM_DASH.sub(", ", text)


# ---------------------------------------------------------------------------
# 8. 其他明确短语
# ---------------------------------------------------------------------------
_MISC = [
    re.compile(r"\s*The implications are significant\.?", re.I),
    re.compile(r"\s*The stakes are high\.?", re.I),
    re.compile(r"\s*The reasons are structural\.?", re.I),
    re.compile(r"\s*The consequences are real\.?", re.I),
]


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
# 只折叠空格/制表符，不碰换行：多段落、代码块、Markdown 结构得以保留
_SPACES = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
# 删除/替换片段后留下的标点粘连修复
_PUNCT_SPACE = re.compile(r"\s+([,.;:!?])")
# Markdown 代码块保护：折叠空白前用占位符抽出，折叠后放回，
# 否则代码缩进会被折叠、Python/缩进敏感代码的语义被破坏
_FENCE_RE = re.compile(r"```.*?```", re.S)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _protect_code(text: str) -> tuple[str, list[str]]:
    """抽出围栏代码块与行内代码，替换为占位符，返回 (保护后文本, 原文列表)。"""
    blocks: list[str] = []

    def repl(m: re.Match) -> str:
        blocks.append(m.group(0))
        return f"\x00{len(blocks) - 1}\x00"

    text = _FENCE_RE.sub(repl, text)
    text = _INLINE_CODE_RE.sub(repl, text)
    return text, blocks


def _restore_code(text: str, blocks: list[str]) -> str:
    """把占位符还原为代码原文。"""
    for i, block in enumerate(blocks):
        text = text.replace(f"\x00{i}\x00", block)
    return text


def _tidy_whitespace(text: str) -> str:
    """折叠多余空格/制表符、收敛连续换行、修复标点前多余空格（不触碰换行与代码块）。"""
    protected, blocks = _protect_code(text)
    protected = _SPACES.sub(" ", protected)
    protected = _MULTI_NEWLINE.sub("\n\n", protected)
    protected = _PUNCT_SPACE.sub(r"\1", protected)
    return _restore_code(protected, blocks)


def _clean_phrases(text: str) -> str:
    """删除短语类规则（清喉开场、强调拐杖、填充语、元评论、模糊声明）。"""
    for pat in _THROAT_CLEARING + _EMPHASIS_CRUTCHES + _FILLERS + _META_COMMENTARY + _MISC:
        text = pat.sub("", text)
    return text


def _clean_jargon(text: str) -> str:
    """商业行话替换。"""
    for pattern, repl in _JARGON_MAP:
        text = re.sub(pattern, repl, text, flags=re.I)
    return text


# 按顺序执行的英文规则阶段，供 clean_en 与 humanizer_core 的命中检测复用
EN_STAGES = [
    ("phrases", _clean_phrases),
    ("jargon", _clean_jargon),
    ("adverbs", _clean_adverbs),
    ("em_dash", _fix_em_dashes),
    ("whitespace", _tidy_whitespace),
]


def clean_en(text: str) -> str:
    """按顺序执行全部英文规则。"""
    for _, fn in EN_STAGES:
        text = fn(text)
    cleaned = text.strip()
    # 防御：整段被规则删空时返回原文，避免把 AI 回复清空
    return cleaned if cleaned else text
