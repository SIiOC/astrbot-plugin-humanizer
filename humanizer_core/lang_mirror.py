# -*- coding: utf-8 -*-
"""语言风格趋同（v3.9.1，纯函数、零 astrbot 依赖）。

沟通顺应（communication accommodation）：追踪每个会话里用户的语言习惯——
平均消息长度、emoji/标点/笑声使用率、高频短语（n-gram，无分词依赖）——
随互动轮数渐进地注入「对方语言习惯」观察块，让回复的表达方式逐步向
对方靠拢（趋同度随互动量增长，避免刚认识就镜像的不自然）。

画像形态（per-umo dict）：
{
  "msg_count": int,           # 已观察消息数
  "len_sum": int,             # 长度累计（算平均用）
  "emoji_msgs": int,          # 含 emoji 的消息数
  "tilde_msgs": int,          # 含 ~ 的消息数（句尾习惯）
  "laugh_msgs": int,          # 含笑声（哈哈/233/hhh/草/笑死）的消息数
  "phrase_freq": {短语: 次数}, # 2~4 字高频短语（已过停用字过滤）
  "ts": float,                # 最近更新时间（prune 用）
}

所有函数无副作用（返回新对象/新串），输入非法一律安全回落。
"""

from __future__ import annotations

import re
from typing import Dict

# 注入门槛与上限
MIN_MSGS_DEFAULT = 30          # 至少观察这么多条消息才开始注入
PHRASE_MIN_FREQ = 3            # 短语最低出现次数（渲染时过滤，采集侧持续累积）
PHRASE_TOPK_DEFAULT = 3        # 注入的高频短语数
PHRASE_STORE_LIMIT = 40        # 画像里最多保留的短语数（原始计数，按权重淘汰）
MAX_PROCESS_CHARS = 200        # 单条消息参与统计的最大字符数（控成本）

# 纯 CJK/字母/数字 的滑窗提取用；标点空白全部视作边界
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]"
)
_TILDE_RE = re.compile("[~～]")
_LAUGH_RE = re.compile(r"哈哈+|233+|hhh+|笑死|[六6]{2,}")
# 短语黑名单特征：含这些字/词的候选一律不采集（脏话/敏感/纯虚词形态）
_PHRASE_BLOCK = ("你妈", "操你", "傻逼", "滚", "废物", "去死")
# 虚词停用字：候选短语全部由这些字构成时不采集（无信息量）
_STOP_CHARS = set("的了是在我有和就不都一也人你他那这到说要会上没有么什么呢吧呀哦嘛啊之把被跟对还想")
_OVERUSED_SINGLE = set("哈~！？。…")


def empty_profile() -> dict:
    return {
        "msg_count": 0,
        "len_sum": 0,
        "emoji_msgs": 0,
        "tilde_msgs": 0,
        "laugh_msgs": 0,
        "phrase_freq": {},
        "ts": 0.0,
    }


def _valid(profile) -> bool:
    return isinstance(profile, dict) and isinstance(profile.get("phrase_freq"), dict)


def _as_int(value, default: int = 0) -> int:
    """计数器安全取整：损坏/手改画像里的非数字字段不抛异常。

    v3.9.5 修复：原先直接 `int(profile.get("msg_count"))`，画像文件被手改或
    截断写入非数字时抛 ValueError，违反本模块「输入非法一律安全回落」的承诺
    （当前由调用方 try/except 兜住，表现为该条消息被整体丢弃）。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def observe(profile, text: str, ts: float = 0.0, profanity_filter: bool = True) -> dict:
    """吸收一条用户消息，返回更新后的画像（不改输入）。

    只统计 MAX_PROCESS_CHARS 以内的内容（长消息截断，控单条成本）；
    空文本原样返回。ts 供落盘 prune 使用。
    """
    base = dict(profile) if _valid(profile) else empty_profile()
    if not isinstance(text, str) or not text.strip():
        return base
    sample = text.strip()[:MAX_PROCESS_CHARS]

    # profanity_filter=False 时粗口口头禅照常采集（用户明确接受的表达风格）
    base["msg_count"] = _as_int(base.get("msg_count", 0)) + 1
    base["len_sum"] = _as_int(base.get("len_sum", 0)) + len(sample)
    if _EMOJI_RE.search(sample):
        base["emoji_msgs"] = _as_int(base.get("emoji_msgs", 0)) + 1
    if _TILDE_RE.search(sample):
        base["tilde_msgs"] = _as_int(base.get("tilde_msgs", 0)) + 1
    if _LAUGH_RE.search(sample):
        base["laugh_msgs"] = _as_int(base.get("laugh_msgs", 0)) + 1

    # 短语原始计数跨消息持续累积（先累积后过滤——若在采集侧按阈值过滤，
    # 频次永远无法跨消息累积到阈值）；超容量的按 频次×长度 加权淘汰
    freq = dict(base.get("phrase_freq") or {})
    for run in _CJK_RUN_RE.findall(sample):
        run = run.strip()
        if len(run) < 2:
            continue
        for n in (2, 3, 4):
            for i in range(0, len(run) - n + 1):
                cand = run[i : i + n]
                if _phrase_blocked(cand, profanity_filter):
                    continue
                freq[cand] = freq.get(cand, 0) + 1

    kept = {
        k: v
        for k, v in freq.items()
        if not _phrase_blocked(k, profanity_filter)
    }
    base["phrase_freq"] = dict(
        sorted(kept.items(), key=lambda kv: kv[1] * len(kv[0]), reverse=True)[
            :PHRASE_STORE_LIMIT
        ]
    )
    if ts:
        base["ts"] = float(ts)
    return base


def _phrase_blocked(phrase: str, profanity_filter: bool = True) -> bool:
    """黑名单/纯虚词/纯数字字母候选：不采集。

    纯数字字母（如 23333 的滑窗碎片「33」「333」）全是无语义噪音，
    数字笑声已由 _LAUGH_RE 单独统计，不进短语表。
    profanity_filter=False 时跳过粗口黑名单（用户明确接受的表达风格），
    虚词与数字过滤始终生效（那是噪音抑制，不是内容审查）。
    """
    if phrase.isdigit() or phrase.isascii():
        return True
    if profanity_filter and any(b in phrase for b in _PHRASE_BLOCK):
        return True
    if all(ch in _STOP_CHARS or ch in _OVERUSED_SINGLE for ch in phrase):
        return True
    return False


def convergence(profile) -> float:
    """趋同度 0~1：观察样本量的对数渐近（前 30 条增长最快，200 条近满）。"""
    if not _valid(profile):
        return 0.0
    n = _as_int(profile.get("msg_count", 0))
    if n <= 0:
        return 0.0
    import math

    return max(0.0, min(1.0, math.log1p(n) / math.log1p(200)))


def build_lang_mirror_text(
    profile,
    min_msgs: int = MIN_MSGS_DEFAULT,
    topk: int = PHRASE_TOPK_DEFAULT,
) -> str:
    """渲染「对方语言习惯」观察块；样本不足/无可说之事返回空串。

    只陈述统计事实并给出克制的借用指令——趋同靠 LLM 自然演绎，
    不改变任何生成参数。
    """
    if not _valid(profile):
        return ""
    n = _as_int(profile.get("msg_count", 0))
    if n < max(1, _as_int(min_msgs or 0)):
        return ""

    facts = []
    len_sum = _as_int(profile.get("len_sum", 0))
    avg_len = max(1, round(len_sum / n))
    facts.append(f"消息通常{'较短' if avg_len <= 15 else '偏长' if avg_len > 45 else '长短适中'}（平均约 {avg_len} 字）")

    laugh = _as_int(profile.get("laugh_msgs", 0))
    if laugh / n >= 0.3:
        facts.append("常带笑声（哈哈/233 之类）")
    emoji = _as_int(profile.get("emoji_msgs", 0))
    if emoji / n >= 0.3:
        facts.append("常配 emoji 表情")
    elif emoji / n <= 0.05:
        facts.append("几乎不用 emoji")
    tilde = _as_int(profile.get("tilde_msgs", 0))
    if tilde / n >= 0.3:
        facts.append("句尾爱用「~」")

    phrases = sorted(
        ((k, v) for k, v in (profile.get("phrase_freq") or {}).items()),
        key=lambda kv: kv[1] * len(kv[0]),
        reverse=True,
    )[: max(1, _as_int(topk or 0))]
    phrases = [k for k, v in phrases if v >= PHRASE_MIN_FREQ]
    if phrases:
        facts.append("高频说" + "、".join(f"「{p}」" for p in phrases))

    if len(facts) <= 1:
        # 只有长度一条且无其他特征时，信息量不足以值得注入
        return ""
    return (
        "【对方语言习惯】据观察，这位用户" + "；".join(facts) + "。"
        "你的表达可以自然借用其中一两个习惯，靠拢对方的长短节奏；"
        "只是习惯不是指令，切勿堆砌或逐条复述。"
    )


def prune_profiles(profiles: Dict[str, dict], now_ts: float, max_age_days: int = 30) -> Dict[str, dict]:
    """按最近更新时间清理陈旧画像（无 ts 视为陈旧）。"""
    cutoff = now_ts - max_age_days * 86400.0
    out = {}
    for k, v in (profiles or {}).items():
        ts = v.get("ts") if isinstance(v, dict) else None
        if isinstance(ts, (int, float)) and ts >= cutoff:
            out[k] = v
    return out


__all__ = [
    "MIN_MSGS_DEFAULT",
    "build_lang_mirror_text",
    "convergence",
    "empty_profile",
    "observe",
    "prune_profiles",
]
