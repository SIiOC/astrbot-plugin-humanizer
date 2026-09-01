"""
拟人打字延迟（纯逻辑层）。

模拟真人「阅读 → 犹豫 → 打字 → 被打断」的回复耗时分布：
- 各成分用时从对数正态分布采样（左偏、偶有长尾），避免均匀随机的机械感；
- 打字耗时与回复字数成正比（可配速度区间）；
- 小概率"干扰事件"（去倒水/被喊）制造长尾；
- 时段系数：深夜/凌晨打字变慢（困）；
- 分段发送时只有首条承担完整延迟，后续条目仅短间隙。

零 astrbot 依赖，可独立单测。速度参数集中于常量表，便于调参。
"""

import asyncio
import builtins
import logging
import math
import random
from typing import Awaitable, Callable, List, Optional, Tuple

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


# ===================== 能力注册表 =====================
# Humanizer 只做"何时亮输入指示"的决策，"怎么亮"是平台特化
# （QQ: set_input_status / 微信: 无此能力）。伴侣插件在启动时注册
# handler，Humanizer 发送前调用；未注册则静默跳过，两边零耦合。
# handler 契约: async def handler(umo: str, peer_id: str, duration: float) -> None
# Humanizer 自己持有睡眠时序，handler 只负责"点亮"信号本身。
#
# ⚠️ 注册表必须锚在进程级单例（builtins 属性）而非本模块全局变量：
# Humanizer main.py 的 _purge_own_submodules() 会在加载时把
# humanizer_core.* 从 sys.modules 踢掉重导入——模块级列表会被重置成
# 空表，而伴侣插件持有的还是旧模块对象里的引用，两边就此失联
# （2026-09-02 实证：注册成功但钩子侧永远查到空表）。

TypingHandler = Callable[[str, str, float], Awaitable[None]]

_REG_ATTR = "_humanizer_typing_handlers"


def _registry() -> List[TypingHandler]:
    """取进程级共享注册表；不存在则创建。"""
    reg = getattr(builtins, _REG_ATTR, None)
    if reg is None:
        reg = []
        setattr(builtins, _REG_ATTR, reg)
    return reg


def register_typing_indicator(handler: TypingHandler) -> None:
    """注册输入指示 handler（伴侣插件启动时调用；重复注册忽略）。"""
    reg = _registry()
    if handler not in reg:
        reg.append(handler)
        logger.info(
            "[Typing] 输入指示能力已注册: %s",
            getattr(handler, "__qualname__", handler),
        )


def unregister_typing_indicator(handler: TypingHandler) -> None:
    """注销（伴侣插件卸载时调用，未注册过则忽略）。"""
    reg = _registry()
    if handler in reg:
        reg.remove(handler)
        logger.info("[Typing] 输入指示能力已注销")


async def fire_typing_indicator(umo: str, peer_id: str, duration: float) -> None:
    """向所有已注册 handler 广播"开始打字"事件；异常吞掉不阻塞回复但记 warning。"""
    reg = _registry()
    if not reg:
        logger.warning("[Typing] 广播时注册表为空（伴侣插件未注册成功？）")
        return
    for h in list(reg):
        try:
            await asyncio.wait_for(h(umo, peer_id, duration), timeout=5.0)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Typing] 指示 handler 失败(忽略): {e}")


def has_typing_indicator() -> bool:
    """是否已有任何输入指示能力注册（诊断/配置面展示用）。"""
    return len(_registry()) > 0
