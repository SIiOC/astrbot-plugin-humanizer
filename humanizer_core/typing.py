"""
拟人打字延迟（纯逻辑层）。

模拟真人「阅读 → 犹豫 → 打字 → 被打断」的回复耗时分布：
- 各成分用时从对数正态分布采样（左偏、偶有长尾），避免均匀随机的机械感；
- 打字耗时与回复字数成正比（可配速度区间）；
- 小概率"干扰事件"（去倒水/被喊）制造长尾；
- 时段系数：深夜/凌晨打字变慢（困）。

零 astrbot 依赖，可独立单测。速度参数集中于常量表，便于调参。

历史注：v3.4.0 曾附带「正在输入」指示能力注册表（广播给伴侣插件调
NapCat set_input_status），2026-09-02 实测 QQ 9.9.32 + NapCat 4.18.19
上输入状态双向不传播（真实打字也无推送，腾讯侧限制），随 v3.4.2 移除。
"""

import logging
import math
import random
from typing import Optional

logger = logging.getLogger("humanizer.typing")

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


def segment_gap(index: int, rng: Optional[random.Random] = None) -> float:
    """分段发送中第 index 条（1 起，0 为首条）之前的间隙秒数。

    首条（index=0）无间隙——完整延迟已由 compute_delay 计算；
    后续条短间隙，少数概率"边想边打"拉长。
    """
    if index <= 0:
        return 0.0
    r = rng or random
    if r.random() < SEGMENT_GAP_LONG_PROB:
        return _uni(*SEGMENT_GAP_LONG_RANGE, rng=rng)
    return _uni(*SEGMENT_GAP_RANGE, rng=rng)


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
