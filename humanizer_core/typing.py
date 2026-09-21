"""
拟人打字延迟（纯逻辑层）。

模拟真人「阅读 → 犹豫 → 打字 → 被打断」的回复耗时分布：
- 各成分用时从对数正态分布采样（左偏、偶有长尾），避免均匀随机的机械感；
- 打字耗时与回复字数成正比（可配速度区间）；
- 小概率"干扰事件"（去倒水/被喊）制造长尾；
- 时段系数：深夜/凌晨打字变慢（困）。

核心逻辑为纯函数；日志按插件市场规范统一走 astrbot.api 的 logger。
速度参数集中于常量表，便于调参。

历史注：v3.4.0 曾附带「正在输入」指示能力注册表（广播给伴侣插件调
NapCat set_input_status），2026-09-02 实测 QQ 9.9.32 + NapCat 4.18.19
上输入状态双向不传播（真实打字也无推送，腾讯侧限制），随 v3.4.2 移除。
"""

import math
import random
import re
from typing import Optional

from astrbot.api import logger

# ===================== 参数表（秒） =====================

# 阅读耗时：每字耗时区间与总上限
READ_PER_CHAR_RANGE = (0.10, 0.20)   # 100~200ms/字
READ_MAX = 4.0

# 反应犹豫：基线区间；对方消息越长基线越高
HESITATE_BASE_RANGE = (0.8, 3.0)
HESITATE_LONG_INBOUND = 60           # 入站超过此字数，犹豫基线上调
HESITATE_LONG_BONUS = (1.0, 2.5)     # 长消息额外犹豫区间

# 打字速度：每字耗时区间（1.5~4 字/秒 → 0.25~0.67s/字）
TYPE_PER_CHAR_RANGE = (0.25, 0.60)
TYPE_BASE = (0.3, 1.2)               # 起手耗时（切窗口/点开对话）

# 干扰事件：概率与额外时长
INTERRUPT_PROB = 0.08
INTERRUPT_EXTRA_RANGE = (5.0, 20.0)

# 对数正态抖动 sigma（越大越散）
LOGNORMAL_SIGMA = 0.45

# 时段系数：(起始小时, 结束小时, 系数)，按本地时间匹配（支持跨午夜）
NIGHT_SLOWDOWN = [
    (23, 24, 1.3),   # 23:00~24:00 困了
    (0, 3, 1.3),     # 凌晨前段
    (3, 7, 1.6),     # 凌晨后段（基本该睡）
]
DAY_FACTOR = 1.0

# 总延迟上限（秒）——防抖等待与本延迟叠加后的保护
TOTAL_DELAY_CAP = 90.0

# 分段发送：后续条目间隙
SEGMENT_GAP_RANGE = (0.5, 3.0)
SEGMENT_GAP_LONG_PROB = 0.2          # 边想边打的概率
SEGMENT_GAP_LONG_RANGE = (4.0, 8.0)


# ===================== 分段发送（v3.6.0） =====================

# 拆分默认参数：短回复不拆；段数上限防刷屏
SPLIT_THRESHOLD = 40        # 全文不超过此长度不拆
SPLIT_MAX_SEGMENTS = 3      # 最多拆成几条
SPLIT_MIN_PART = 8          # 短于此的段并入上一条

# 句末标点（保留其后的引号/括号闭合）；不含英文句点，防止切碎小数与缩写
_SENTENCE_END_RE = re.compile(r"[。！？!?…]+[”’）】」』》]*")

# 超长单句兜底切点（逗号类 + 空格）
_FALLBACK_CUT_MARKS = "，,；;：: "


def split_reply_bubbles(
    text: str,
    threshold: int = SPLIT_THRESHOLD,
    max_segments: int = SPLIT_MAX_SEGMENTS,
    min_part: int = SPLIT_MIN_PART,
) -> list:
    """把长回复按句读拆成多条聊天气泡（v3.6.0，纯函数）。

    依据真人「连发几条短消息」的习惯（同类拟人项目共识做法），规则：
    - 全文 ≤ threshold 或没有自然切点时返回原文单段（拆不动不强拆）；
    - 先按换行/句末标点切句，短段（< min_part）并入上一条；
    - 超长单句在逗号/分号处兜底切，切点至少在半窗之后，否则按长度硬切；
    - 段数上限 max_segments，溢出内容并回最后一条。

    只切不造：所有段按顺序拼回与原文一致（仅去除各段首尾空白；换行
    按切点处理会被拍平——多行长回复拆分后是无换行的短句流），
    绝不丢字、不补标点。
    """
    clean = (text or "").strip()
    if not clean:
        return []
    try:
        threshold = max(1, int(threshold))
        max_segments = max(1, int(max_segments))
        min_part = max(1, int(min_part))
    except (TypeError, ValueError):
        threshold, max_segments, min_part = (
            SPLIT_THRESHOLD,
            SPLIT_MAX_SEGMENTS,
            SPLIT_MIN_PART,
        )
    min_part = min(min_part, threshold)  # 防手滑：短段阈值大于拆分阈值无意义
    if len(clean) <= threshold:
        return [clean]

    # 1) 切句（换行也是切点；句末标点归属前句）
    sentences: list = []
    for line in re.split(r"\n+", clean):
        line = line.strip()
        if not line:
            continue
        start = 0
        for m in _SENTENCE_END_RE.finditer(line):
            piece = line[start : m.end()].strip()
            if piece:
                sentences.append(piece)
            start = m.end()
        tail = line[start:].strip()
        if tail:
            sentences.append(tail)
    if not sentences:
        return [clean]

    # 2) 短段并入上一条（首条过短保持独立——「嗯。」单独一条也是人话）
    merged: list = []
    for piece in sentences:
        if merged and len(merged[-1]) < min_part:
            merged[-1] += piece
        else:
            merged.append(piece)

    # 3) 超长段兜底切：优先逗号/分号，切点至少在半窗之后，否则硬切
    pieces: list = []
    for seg in merged:
        if len(seg) <= threshold:
            pieces.append(seg)
            continue
        rest = seg
        while len(rest) > threshold:
            window = rest[: threshold + 1]
            cut = 0
            for mark in _FALLBACK_CUT_MARKS:
                cut = max(cut, window.rfind(mark) + 1)
            # cut<=0 必须并入硬切条件：threshold=1 时 threshold//2=0，
            # 原 `cut < threshold//2` 恒 False → cut=0 空切不前进 → 死循环
            # （2026-09-07 审查发现，实测卡死事件循环）
            if cut <= 0 or cut < threshold // 2:
                cut = threshold
            pieces.append(rest[:cut].strip())
            rest = rest[cut:].strip()
        if rest:
            pieces.append(rest)

    # 4) 复检短段（兜底切可能产出残段）+ 段数上限
    final: list = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if final and len(final[-1]) < min_part:
            final[-1] += piece
        else:
            final.append(piece)
    if len(final) >= 2 and len(final[-1]) < min_part:
        final[-2] += final[-1]
        final.pop()
    if len(final) > max_segments:
        final = final[: max_segments - 1] + ["".join(final[max_segments - 1 :])]
    return final if final else [clean]


# ===================== 基础采样 =====================

def _lnsample(mean: float, rng: Optional[random.Random] = None) -> float:
    """对数正态采样：中位数=mean，sigma 控制散布。"""
    r = rng or random
    return math.exp(math.log(max(mean, 1e-6)) + r.gauss(0, LOGNORMAL_SIGMA))


def _uni(lo: float, hi: float, rng: Optional[random.Random] = None) -> float:
    r = rng or random
    return r.uniform(lo, hi)


# ===================== 时段系数 =====================

def time_factor(hour: Optional[int]) -> float:
    """按本地小时返回打字速度系数；hour 为 None 时不加成。"""
    if hour is None:
        return DAY_FACTOR
    for lo, hi, fac in NIGHT_SLOWDOWN:
        # 支持跨午夜区间（lo > hi 时视为 lo~24 + 0~hi）
        if lo <= hi:
            if lo <= hour < hi:
                return fac
        elif hour >= lo or hour < hi:
            return fac
    return DAY_FACTOR


# ===================== 主计算 =====================

def compute_delay(
    reply_text: str,
    inbound_len: int = 0,
    hour: Optional[int] = None,
    rng: Optional[random.Random] = None,
) -> float:
    """计算首条回复的拟人延迟（秒）。

    reply_text: 即将发出的回复文本（决定打字耗时）
    inbound_len: 对方消息长度（决定阅读与犹豫）
    hour: 本地小时 0~23（时段系数）；None 不加成
    rng: 注入随机源（单测用）
    返回值保证 >= 0 且 <= TOTAL_DELAY_CAP。
    """
    # 阅读耗时（上限截断）
    inbound = max(0, inbound_len)
    read = min(inbound * _uni(*READ_PER_CHAR_RANGE, rng=rng), READ_MAX)
    # 犹豫（长入站消息加成）
    hes = _uni(*HESITATE_BASE_RANGE, rng=rng)
    if inbound >= HESITATE_LONG_INBOUND:
        hes += _uni(*HESITATE_LONG_BONUS, rng=rng)
    # 打字：起手 + 每字耗时（截去空白）
    n_chars = len([c for c in reply_text if not c.isspace()])
    typing = _uni(*TYPE_BASE, rng=rng) + n_chars * _uni(*TYPE_PER_CHAR_RANGE, rng=rng)
    # 合成并对整体施加对数正态抖动 + 时段系数
    base = read + hes + typing
    total = _lnsample(max(base, 0.5), rng=rng) * time_factor(hour)
    # 干扰事件长尾
    r = rng or random
    if r.random() < INTERRUPT_PROB:
        total += _uni(*INTERRUPT_EXTRA_RANGE, rng=rng)
    return max(0.0, min(total, TOTAL_DELAY_CAP))


def segment_gap(
    index: int,
    rng: Optional[random.Random] = None,
    gap_range=SEGMENT_GAP_RANGE,
    long_prob=SEGMENT_GAP_LONG_PROB,
    long_range=SEGMENT_GAP_LONG_RANGE,
) -> float:
    """分段发送中第 index 条（1 起，0 为首条）之前的间隙秒数。

    首条（index=0）无间隙——完整延迟已由 compute_delay 计算；
    后续条短间隙，可配置概率"边想边打"拉长（v3.7.1 起三参数可调，
    默认值即旧常量，向后兼容）。

    防御：区间非法（任一 <=0 或 min>max 互换后仍非法）回落内置默认；
    long_prob 钳到 [0,1]。
    """
    if index <= 0:
        return 0.0
    r = rng or random

    def _win(w, fallback):
        try:
            lo, hi = float(w[0]), float(w[1])
        except (TypeError, ValueError, IndexError):
            return fallback
        if lo <= 0 or hi <= 0:
            return fallback
        if lo > hi:
            lo, hi = hi, lo
        return (lo, hi)

    gap = _win(gap_range, SEGMENT_GAP_RANGE)
    lng = _win(long_range, SEGMENT_GAP_LONG_RANGE)
    try:
        p = float(long_prob)
    except (TypeError, ValueError):
        p = SEGMENT_GAP_LONG_PROB
    p = max(0.0, min(p, 1.0))
    if r.random() < p:
        return _uni(*lng, rng=rng)
    return _uni(*gap, rng=rng)


# v3.5.0 节奏引擎：hot 状态下的"快打"速度（秒/非空字符）。绝对窗口之外
# 保留一点长度相关性——长回复在热聊里也不该秒回得像预知未来，但明显
# 快于正常打字（正常约 0.25~0.60 s/字）。
RHYTHM_HOT_TYPE_SPEED = 0.06


def apply_rhythm_delay(
    delay: float,
    heat: str,
    n_chars: int = 0,
    hot_window=(1.5, 4.0),
    cold_window=(10.0, 25.0),
    delay_min: float = 0.0,
    delay_max: float = 0.0,
    total_cap: float = 90.0,
    rng: Optional[random.Random] = None,
) -> float:
    """打字延迟与对话热度状态直接融合（v3.5.0，取代旧乘法系数）。

    - hot（连续快聊）：**覆盖**为 hot_window 内随机值 + 快打耗时
      （0.06 s/字）——快回意图优先，忽略 delay_min（两者方向相反），
      尊重 delay_max 上限。
    - cold（冷开场）：在当前延迟上**叠加** cold_window 内随机值
      （"隔了一会儿才看到消息"的拾起延迟）——与 delay_min 同向，
      叠加后仍尊重 delay_max。
    - warm / 窗口非法（任一 <=0）：维持传入延迟不动（warm 的自然基线
      即 compute_delay 本身）。

    窗口 min>max 自动互换（防手滑）；结果统一截到 [0, total_cap]。
    rng 可注入（单测）；传入前 delay 已经过调用方的用户区间裁剪。
    """
    r = rng or random

    def _win(w):
        try:
            lo, hi = float(w[0]), float(w[1])
        except (TypeError, ValueError, IndexError):
            return None
        if lo <= 0 or hi <= 0:
            return None
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi

    result = float(delay)
    if heat == "hot":
        w = _win(hot_window)
        if w:
            result = r.uniform(w[0], w[1]) + max(0, n_chars) * RHYTHM_HOT_TYPE_SPEED
            if delay_max > 0:
                result = min(result, delay_max)
    elif heat == "cold":
        w = _win(cold_window)
        if w:
            result = result + r.uniform(w[0], w[1])
            if delay_max > 0:
                result = min(result, delay_max)
    if total_cap and total_cap > 0:
        result = max(0.0, min(result, total_cap))
    return result


def settle_delay(target_delay: float, elapsed: float) -> float:
    """补足式延迟（v3.5.x）：目标总延迟减去本轮已自然耗时，下限 0。

    v3.4 的打字延迟是「额外 sleep」；但 2026-09-06 日志 112 轮实证，
    v3.5 链路（防抖等待 + 记忆检索 + agent 工具循环）自然耗时中位约
    49 秒，叠加人工延迟只会推高总响应（cold 附加最恶劣，p90 逼近两分
    钟）。语义改为「目标总延迟」：compute_delay/apply_rhythm_delay 的
    输出不再是要额外等待的时长，而是对方消息到达后的总延迟目标——
    自然耗时已达标时补足为零（hot 快回窗口在重链路下由此自然退化、
    cold 附加不再推高总延迟），链路变快（换快模型/关检索）时自动重新
    接管兜底。

    Args:
        target_delay: compute_delay/apply_rhythm_delay 算出的目标总延迟。
        elapsed: 对方消息到达至今的自然耗时（message_obj.timestamp 起）。

    Returns:
        实际还需 sleep 的秒数，[0, target_delay]。
    """
    target = float(target_delay or 0.0)
    elapsed = float(elapsed or 0.0)
    # v4.0.1：显式 NaN 防御（语义明确化——实测 NaN 落进 max 比较恒为假，
    # 行为上等价于 elapsed=0/target=0，但依赖该隐式行为太脆）：
    # elapsed NaN → 当作零自然耗时，按完整目标补足
    if target != target:
        target = 0.0
    if elapsed != elapsed:
        elapsed = 0.0
    return max(0.0, target - max(0.0, elapsed))
