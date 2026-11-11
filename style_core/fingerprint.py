# -*- coding: utf-8 -*-
"""风格指纹：把「像真人」从形容词变成可注入的数字。

从用户语料池的 user 消息统计：长度分布、问句/感叹/句号/省略号/波浪号比例、
每条逗号数、语气词比例、最常用语气词。输出两部分：

1. ``compute_fingerprint``：结构化 dict（可落盘/可测试）；
2. ``fingerprint_prompt``：压缩成 4–6 行注入 system_prompt 的中文提示。

设计约束：
- 纯函数、零 astrbot 依赖、零网络、零 LLM；
- 样本不足（<20 条）时返回空提示，避免用几条消息带偏模型；
- 只描述「输出形式」（句长/标点/语气词），不描述内容，不存储原句。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

# 样本少于该值不生成提示（几条消息的统计没有代表性）。
MIN_SAMPLE = 20

# 只取最常用的几个语气词，避免把生僻字也塞进 prompt。
_PARTICLES = ("呢", "啦", "嘛", "哦", "呗", "呀", "啊", "嗯", "唔", "诶", "嗷", "哈")

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF\U0001FA70-\U0001FAFF\U00002600-\U000027BF]"
)


def _to_texts(rows: Iterable[Any]) -> list[str]:
    """把各种行格式归一成文本列表（只取用户侧）。"""
    users: list[str] = []
    others: list[str] = []
    for row in rows or []:
        if isinstance(row, str):
            text = row
        elif isinstance(row, dict):
            role = str(row.get("role", "") or "").strip().lower()
            text = row.get("content") or row.get("text") or ""
            if role and role not in ("user", "human"):
                if isinstance(text, str) and text.strip():
                    others.append(text)
                continue
        else:
            continue
        if isinstance(text, str) and text.strip():
            users.append(text)
    # 没有 role 标记的语料（纯 content 行）全部当用户文本。
    return users or others


def collect_user_texts(rows: Iterable[Any]) -> list[str]:
    """从语料行中收集用户侧文本（公开函数，便于测试/工具复用）。"""
    return _to_texts(rows)


def _ratio(values: list[bool]) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if v) / len(values)


def compute_fingerprint(texts: Iterable[str], *, sample_limit: int = 5000) -> dict:
    """统计用户消息的「输出形式」指纹。

    返回字段均为 JSON 可序列化；样本为空时返回 ``{"sample_size": 0}``。
    """
    cleaned = [t.strip() for t in texts if isinstance(t, str) and t.strip()]
    if sample_limit > 0:
        cleaned = cleaned[-sample_limit:]
    n = len(cleaned)
    if n == 0:
        return {"version": 1, "sample_size": 0}

    lengths = sorted(len(t) for t in cleaned)

    def percentile(p: float) -> int:
        idx = min(len(lengths) - 1, max(0, int(round((len(lengths) - 1) * p))))
        return lengths[idx]

    particle_hits = Counter()
    for text in cleaned:
        for ch in _PARTICLES:
            if ch in text:
                particle_hits[ch] += 1

    comma_total = sum(text.count("，") + text.count(",") for text in cleaned)
    top_particles = [p for p, _ in particle_hits.most_common(3)]

    return {
        "version": 1,
        "sample_size": n,
        "avg_chars": round(sum(lengths) / n, 1),
        "median_chars": percentile(0.5),
        "p10_chars": percentile(0.1),
        "p90_chars": percentile(0.9),
        "short_ratio": round(_ratio([ln < 10 for ln in lengths]), 4),
        "long_ratio": round(_ratio([ln >= 40 for ln in lengths]), 4),
        "question_ratio": round(_ratio(["？" in t or "?" in t for t in cleaned]), 4),
        "exclaim_ratio": round(_ratio(["！" in t or "!" in t for t in cleaned]), 4),
        "period_ratio": round(_ratio(["。" in t or "." in t for t in cleaned]), 4),
        "ellipsis_ratio": round(_ratio(["……" in t or "..." in t for t in cleaned]), 4),
        "tilde_ratio": round(_ratio(["~" in t or "～" in t for t in cleaned]), 4),
        "emoji_ratio": round(_ratio([bool(_EMOJI_RE.search(t)) for t in cleaned]), 4),
        "comma_per_msg": round(comma_total / n, 2),
        "particle_ratio": round(_ratio([any(p in t for p in _PARTICLES) for t in cleaned]), 4),
        "top_particles": top_particles,
    }


def fingerprint_prompt(fingerprint: dict | None) -> str:
    """把指纹压缩成注入段；样本不足/无效返回空串。"""
    if not isinstance(fingerprint, dict):
        return ""
    try:
        n = int(fingerprint.get("sample_size") or 0)
    except (TypeError, ValueError):
        return ""
    if n < MIN_SAMPLE:
        return ""

    def pct(key: str) -> int:
        try:
            return int(round(float(fingerprint.get(key) or 0) * 100))
        except (TypeError, ValueError):
            return 0

    avg = fingerprint.get("avg_chars", 0)
    median = fingerprint.get("median_chars", 0)
    p10 = fingerprint.get("p10_chars", 0)
    p90 = fingerprint.get("p90_chars", 0)
    top = fingerprint.get("top_particles") or []
    top_text = "、".join(str(x) for x in top[:3]) if top else "（无明显偏好）"

    lines = [
        "【你的真实说话数据（来自你过去的聊天，写的时候向这些数字靠拢）】",
        f"- 样本 {n} 条：平均 {avg} 字，中位 {median} 字；最少 10% 少于 {p10} 字，最多 10% 多于 {p90} 字。",
        f"- 短句(<10字) {pct('short_ratio')}%，长段(>=40字) {pct('long_ratio')}%；"
        f"问句 {pct('question_ratio')}%，感叹 {pct('exclaim_ratio')}%，句号 {pct('period_ratio')}%。",
        f"- 省略号 {pct('ellipsis_ratio')}%，波浪号 {pct('tilde_ratio')}%，"
        f"每条平均 {fingerprint.get('comma_per_msg', 0)} 个逗号；"
        f"带语气词的消息 {pct('particle_ratio')}%，最常用：{top_text}。",
        "【硬性表达习惯（比统计更重要，每条回复都要检查）】",
        "- 每 3 条回复至少 1 条少于 10 字：可以只回「嗯」「……好」「不知道诶」这种半句。",
        "- 每 2 条至少 1 条带语气词（啊/呢/吧/哦/啦），优先放句尾。",
        "- 每 2–3 条至少 1 条用「……」表示停顿/迟疑；不要每条都用句号收尾。",
        "- 接话不是追问：默认只接住对方的话（回应/吐槽/补充），不提问。",
        "- 只有同时满足才追问：①对方刚说了未闭合的具体信息（计划/困扰/选择/结果/"
        "时间地点）；②这个细节影响你怎么接；③问题指向具体的人/事/时间/原因；"
        "④最近 3 条内没问过。一条最多一个问题。",
        "- 禁止豆包式提问：空泛的「你呢/你说呢/你怎么看/还有吗/想聊点什么」、"
        "复述对方原话的提问、每条都问、用问题填空白。对方在抱怨或情绪低落时"
        "只接情绪，不追问。",
        "生成时像这些真实消息一样断句：该短就短，不要每条都写成完整、匀称的段落；"
        "语气词/省略号按上面的比例自然出现，不要堆。",
    ]
    return "\n".join(lines)


def select_exemplars(
    texts: Iterable[str], fingerprint: dict | None = None, *, limit: int = 3
) -> list[str]:
    """从真实语料里挑 2–3 条「语气锚点」示例，供 few-shot 注入。

    取长度分位附近的三条（短/中/长），而不是随机抽——让模型同时看到
    「短句怎么停」「中句怎么接」「长句怎么展开」。只返回原文，不做改写；
    内容属于用户自己的语料，调用方负责只在本地 prompt 使用。
    """
    cleaned = [t.strip() for t in texts if isinstance(t, str) and len(t.strip()) >= 2]
    if not cleaned or limit <= 0:
        return []
    fp = fingerprint if isinstance(fingerprint, dict) else {}
    lengths = sorted(len(t) for t in cleaned)
    n = len(lengths)

    def has_style_signal(text: str) -> bool:
        return (
            "……" in text
            or "..." in text
            or any(p in text for p in _PARTICLES)
            or text[:1] in "嗯哦啊唔诶"
        )

    # 优先选「本身带省略号/语气词」的真实消息，让 few-shot 真的示范语言习惯；
    # 风格样本不足时才退回纯长度分位。
    style_pool = [t for t in cleaned if has_style_signal(t)]
    pool = style_pool if len(style_pool) >= 3 else cleaned
    pool_lengths = sorted(len(t) for t in pool)
    ellipsis_pool = [t for t in pool if "……" in t or "..." in t]

    def pick(target: int, candidates: list[str] | None = None) -> str | None:
        values = candidates or pool
        if not values:
            return None
        ordered = sorted(set(values), key=lambda t: (abs(len(t) - target), len(t)))
        for item in ordered:
            if item not in seen:
                return item
        return None

    def quantile(values: list[int], p: float) -> int:
        return values[min(len(values) - 1, max(0, int(round((len(values) - 1) * p))))]

    targets = [
        quantile(pool_lengths, 0.1),
        quantile(pool_lengths, 0.5),
        quantile(pool_lengths, 0.9),
    ]
    picked: list[str] = []
    seen: set[str] = set()
    for index, target in enumerate(targets):
        # 前两条优先从「带省略号」的样本里挑，保证 few-shot 至少示范一次停顿；
        # 第三条回到全池，避免三条都是同一种语气。
        candidates = ellipsis_pool if index < 2 and len(ellipsis_pool) >= 2 else pool
        item = pick(target, candidates)
        if not item:
            item = pick(target, pool)
        if not item:
            continue
        seen.add(item)
        picked.append(" ".join(item.split())[:80])
        if len(picked) >= limit:
            break
    return picked


def exemplar_prompt(exemplars: list[str] | None) -> str:
    """把语气锚点渲染成 few-shot 段；空列表返回空串。"""
    items = [e.strip() for e in (exemplars or []) if isinstance(e, str) and e.strip()]
    if not items:
        return ""
    lines = ["【语气锚点（来自你的真实消息，模仿节奏、停顿、省略号和语气词，不要照抄内容）】"]
    for item in items[:3]:
        lines.append(f"- {item}")
    return "\n".join(lines)

