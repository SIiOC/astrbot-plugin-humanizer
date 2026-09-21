# -*- coding: utf-8 -*-
"""应声虫复读（v4.1.0）：搞怪消息触发时原样学舌。

用户定案（2026-09-14）：
- 仅在用户发出**不正经/搞怪消息**（连续笑声、纯标点玩梗、颜文字、玩梗口头禅）
  时抽签，命中则 bot 原样复读该条消息（学舌玩梗，网络"应声虫"梗）。
- 概率作用于"搞怪命中"这一层（默认 8%），全局复读率因此天然低于 10%。
- 纯原样：不加字、不改标点。
- 判定显式排除：长句（>max_len）、真实疑问、正经诉求——宁可漏判不可误判
  （误判会把正常问答变成鹦鹉，破坏可用性）。

本模块保持 humanizer_core 的纯函数约定：不 import astrbot、不做 IO、
随机源可注入（rng 缺省 random）。所有对文本的判断都可单独测试。
"""

from __future__ import annotations

import random
import re
from typing import Optional

# ---- 搞怪信号 --------------------------------------------------------------

# 连续笑声/拟声（3 连及以上才当搞怪；"哈哈"这种两连在正经句里太常见）
_LAUGH = re.compile(r"(哈{3,}|嘿{3,}|呵{3,}|嘻{3,}|吼{3,}|嗷{2,}|呜呜{2,}|嘎{3,})")
# 数字梗
_NUM_MEME = re.compile(r"(233+|666+|888+|hhhh+|嗷嗷+)", re.I)
# 拉长音（破折号/波浪号/省略号 3 连以上）
_STRETCH = re.compile(r"([—–~～]{2,}|。{3,})")
# 纯标点玩梗：问号/感叹号 2 连以上，或问号感叹号混排
_PUNCT_MEME = re.compile(r"([？?]{2,}|[！!]{3,}|[？?！!]{2,})")
# 颜文字：成对括号包裹的符号组合。要求括号内至少含一个非"字母数字"字符
# （◉ω◉ 这类混合符号也算），且括号内**不含汉字**——语料实证（2026-09-14
# 三审）：（微微后退，但仍注视著艾莉亚）这类 RP 动作描写会被裸符号判定
# 误收，负向前瞻排除 CJK 后只留真颜文字。
_KAOMOJI = re.compile(
    r"[(（](?![^)）]*[\u4e00-\u9fff])[^)）]{0,12}[^\w)）][^)）]{0,12}[)）]"
)
# emoji（粗略区间，够用即可）
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]"
)

# 玩梗口头禅（**多字**子串匹配；单字梗一律走 _MEME_STANDALONE，
# 否则"草莓/典礼/孝顺"这类正常词会被子串误判）
_MEME_WORDS = (
    "笑死", "笑不活", "笑死我了", "绷不住", "蚌埠", "难绷",
    "破防", "乐了", "乐死", "裂开", "离谱", "逆天",
    "麻了", "栓q", "典中典", "孝死", "急眼", "我服了", "绝了", "寄了",
)
# 独立成句的玩梗短词（须整条消息等于才命中，防子串误伤）
_MEME_STANDALONE = ("草", "艹", "淦", "典", "孝", "寄", "6")

# ---- 排除门（先于命中判定，拿不准一律 False）-------------------------------

# 真实疑问（真在问事，不该复读）
_REAL_QUESTION = re.compile(r"(吗|呢|怎么|为什么|为啥|如何|哪里|哪个|几点|多少|是不是|能不能|可不可以)")
# 正经诉求（求助/指令/恳求，绝不复读；"求你"为 2026-09-14 三审补——
# 语料实证"不——！停下……求你……"这类恳求句会被 —— 命中门放进）
_REQUEST = re.compile(r"(帮我|请问|求求|求你|求助|怎么办|帮我查|教教|能不能帮|麻烦你|帮忙)")

__all__ = [
    "is_playful",
    "structure_ok",
    "parse_playful_score",
    "should_parrot",
    "cooldown_ok",
    "daily_ok",
    "record",
    "prune",
    "pick_parrot_segment",
    "ParrotState",
]

_STATE_VERSION = 1


def _zh_len(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


def structure_ok(text: str, min_len: int = 1, max_len: int = 24) -> bool:
    """结构门（**不依赖搞怪关键词**）：长度窗 + 非真实疑问 + 非正经诉求。

    v4.1.0 LLM 判定档的前置门：先廉价地筛掉"结构上就不该复读"的消息
    （太长/在问事/在求助），再去问 LLM 搞怪程度，避免浪费调用。
    正则档的 is_playful 也复用它，保证两档结构口径一致、不漂移。
    """
    if not text:
        return False
    t = text.strip()
    if not t:
        return False
    if len(t) < max(1, int(min_len)) or len(t) > max(1, int(max_len)):
        return False
    if _REAL_QUESTION.search(t):
        return False
    if _REQUEST.search(t):
        return False
    return True


def is_playful(text: str, min_len: int = 1, max_len: int = 24,
               extra_words: Optional[list[str]] = None) -> bool:
    """判定一条消息是否为"不正经/搞怪"，值得考虑学舌（正则档）。

    保守策略：结构门任一不满足即 False。宁可漏判（不学舌），不可误判
    （把正经问答变鹦鹉）。
    """
    if not structure_ok(text, min_len, max_len):
        return False
    t = text.strip()
    # 命中门（任一即可）
    if _LAUGH.search(t) or _NUM_MEME.search(t) or _STRETCH.search(t):
        return True
    if _PUNCT_MEME.search(t):
        return True
    if _KAOMOJI.search(t) or len(_EMOJI.findall(t)) >= 2:
        return True
    # 玩梗词（子串）
    if any(w in t for w in _MEME_WORDS):
        return True
    # 独立成句的玩梗短词
    if t in _MEME_STANDALONE:
        return True
    # 用户扩展词（逗号分隔；子串匹配）
    for w in (extra_words or []):
        w = w.strip()
        if w and w in t:
            return True
    return False


def parse_playful_score(text: Optional[str]) -> Optional[int]:
    """解析判定模型返回的搞怪分（0~10）；无法解析返回 None。

    约定模型只回一个数字（提示词明确要求）。容错：取文本里第一个
    0~10 的独立数字；**解析不出=不搞怪**（安全方向，宁可漏判）。
    超范围钳到 [0,10]。
    """
    if not text:
        return None
    # 边界用"前后非数字"的 lookaround（\b 对中文无效——中文属 \w，
    # "9分" 里 9 与 分 之间不构成 \b 边界）。
    m = re.search(r"(?<!\d)(10|[0-9])(?!\d)", str(text))
    if not m:
        return None
    return max(0, min(10, int(m.group(1))))


def should_parrot(playful: bool, prob: float, prob_normal: float = 0.0,
                  rng: Optional[random.Random] = None) -> bool:
    """抽签是否复读。playful 用 prob；非搞怪走 prob_normal（默认 0=不复读）。

    prob/prob_normal 会被钳到 [0,1]；非数字回落 0（宁可不复读）。
    """
    def _clamp(x) -> float:
        try:
            return min(max(float(x), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.0

    p = _clamp(prob) if playful else _clamp(prob_normal)
    if p <= 0.0:
        return False
    r = rng or random
    return r.random() < p


# ---- 冷却与每日上限（纯函数，状态由调用方持有/落盘）-------------------------


class ParrotState:
    """应声虫状态存取（per-umo）。

    文件形状::

        {"version": 1, "turns": {umo: int}, "counts": {umo: [date, n]},
         "last": {umo: ts}}

    - ``turns``：会话累计轮次计数（每次结算 +1），用于冷却"复读后 N 轮内不再抽"。
    - ``counts``：``[YYYY-MM-DD, 当日已复读次数]``，跨日自动重置。
    - ``last``：最近一次复读的轮次号，冷却判定的锚点。
    """

    def __init__(self, raw: Optional[dict] = None):
        raw = raw if isinstance(raw, dict) else {}
        turns = raw.get("turns")
        counts = raw.get("counts")
        last = raw.get("last")
        self.turns: dict[str, int] = {
            k: int(v) for k, v in turns.items()
        } if isinstance(turns, dict) else {}
        self.counts: dict[str, list] = {}
        if isinstance(counts, dict):
            for k, v in counts.items():
                if isinstance(v, list) and len(v) == 2:
                    try:
                        self.counts[k] = [str(v[0]), int(v[1])]
                    except (TypeError, ValueError):
                        continue
        self.last: dict[str, int] = {
            k: int(v) for k, v in last.items()
        } if isinstance(last, dict) else {}

    # ---- 序列化 ----
    def to_dict(self) -> dict:
        return {
            "version": _STATE_VERSION,
            "turns": self.turns,
            "counts": self.counts,
            "last": self.last,
        }

    @classmethod
    def load(cls, raw: Optional[dict]) -> "ParrotState":
        return cls(raw)

    # ---- 轮次 ----
    def bump_turn(self, umo: str) -> int:
        """结算轮次 +1，返回当前轮次号。"""
        n = int(self.turns.get(umo, 0)) + 1
        self.turns[umo] = n
        return n

    def turn(self, umo: str) -> int:
        return int(self.turns.get(umo, 0))


def cooldown_ok(state: ParrotState, umo: str, cooldown_turns: int) -> bool:
    """距上次复读是否已过冷却轮数（从未复读过=True）。"""
    try:
        cd = max(0, int(cooldown_turns))
    except (TypeError, ValueError):
        cd = 0
    if cd <= 0:
        return True
    last = state.last.get(umo)
    if last is None:
        return True
    return (state.turn(umo) - int(last)) >= cd


def daily_ok(state: ParrotState, umo: str, date: str, max_per_day: int) -> bool:
    """当日复读次数是否未达上限。跨日自动视为 0。"""
    try:
        cap = int(max_per_day)
    except (TypeError, ValueError):
        cap = 0
    if cap <= 0:
        return False  # 上限设 0 = 禁用
    cur = state.counts.get(umo)
    if not cur or cur[0] != date:
        return True
    return int(cur[1]) < cap


def daily_used(state: ParrotState, umo: str, date: str) -> int:
    cur = state.counts.get(umo)
    if not cur or cur[0] != date:
        return 0
    return int(cur[1])


def record(state: ParrotState, umo: str, date: str) -> None:
    """记录一次复读：更新当日计数 + 冷却锚点（轮次号）。"""
    used = daily_used(state, umo, date)
    state.counts[umo] = [date, used + 1]
    state.last[umo] = state.turn(umo)


def prune(state: ParrotState, active_umos: Optional[set] = None,
          max_umos: int = 512) -> ParrotState:
    """剪枝：只留活跃会话；仍超量则按轮次号保留最近的。

    状态文件本就不大，这里是防御性上界（防长期运行会话数无界增长）。
    """
    if active_umos is not None:
        keep = set(active_umos)
        state.turns = {k: v for k, v in state.turns.items() if k in keep}
        state.counts = {k: v for k, v in state.counts.items() if k in keep}
        state.last = {k: v for k, v in state.last.items() if k in keep}
    try:
        cap = max(1, int(max_umos))
    except (TypeError, ValueError):
        cap = 512
    if len(state.turns) > cap:
        # 按轮次号降序保留 cap 个最活跃会话
        top = sorted(state.turns.items(), key=lambda kv: kv[1], reverse=True)[:cap]
        keep = {k for k, _ in top}
        state.turns = {k: v for k, v in state.turns.items() if k in keep}
        state.counts = {k: v for k, v in state.counts.items() if k in keep}
        state.last = {k: v for k, v in state.last.items() if k in keep}
    return state


# ---- 防抖合并文本取段 ------------------------------------------------------


def pick_parrot_segment(merged_text: str, separator: str = "\n") -> str:
    """从防抖合并文本里取"最后一条"（学舌只针对用户刚发的那句）。

    合并符缺省换行（与 debounce 的 merge_separator 默认一致）。取空段
    时回退整串。多条连发时用户当下在意的是最后一句，复读它也最自然。
    """
    if not merged_text:
        return ""
    sep = separator or "\n"
    parts = [p.strip() for p in merged_text.split(sep)]
    parts = [p for p in parts if p]
    return parts[-1] if parts else merged_text.strip()
