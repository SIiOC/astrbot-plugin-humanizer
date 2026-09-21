# -*- coding: utf-8 -*-
"""发送前决策的纯函数（v4.0 Phase 7，从 main._typing_delay_before_send 下沉）。

钩子里三类**纯判定**可离线测试，框架读取（event.get_extra / get_result /
message_obj.timestamp）刻意留在 main 适配层：

- `voice_only_sent(sent_keys)`：本轮是否已通过 send_message_to_user 发过
  Record 语音（事件级组件键以 ``record:`` 前缀登记，v3.4.4）；
- `dedupe_hit(text, sent_texts, threshold)`：待发文本与本轮已发文本的复读
  相似度（命中返回正分，否则 0.0；相似度算法委托 dedupe.match_sent_text）；
- `resolve_delay_bounds(delay, delay_min, delay_max, total_cap)`：用户自定义
  延迟区间的**顺序契约**——先手感互换 → 再上界裁剪 → 再下界抬升 → 最后总上限
  夹逼（顺序不可换：先换后裁与先裁后换结果不同）。
"""

from __future__ import annotations

from typing import Any, Optional

from humanizer_core.dedupe import match_sent_text
from humanizer_core.typing import split_reply_bubbles

_VOICE_KEY_PREFIX = "record:"


def voice_only_sent(sent_keys: Any) -> bool:
    """sent_keys 里是否登记过 Record 语音组件（``record:<path>``）。

    非 list / 空 / 无匹配均返回 False（放行文字正文）。
    """
    if not isinstance(sent_keys, list):
        return False
    return any(
        isinstance(k, str) and k.startswith(_VOICE_KEY_PREFIX) for k in sent_keys
    )


def dedupe_hit(
    text: str,
    sent_texts: Any,
    threshold: float,
) -> float:
    """待发文本与本轮已发文本的复读相似度；命中返回正分，否则 0.0。

    text 空白或 sent_texts 非 list/为空时直接 0.0（不判重）。
    """
    if not isinstance(sent_texts, list) or not sent_texts:
        return 0.0
    if not isinstance(text, str) or not text.strip():
        return 0.0
    return match_sent_text(text, sent_texts, threshold)


def resolve_delay_bounds(
    delay: float,
    delay_min: float = 0.0,
    delay_max: float = 0.0,
    total_cap: float = 90.0,
) -> float:
    """把原始 delay 依次施加用户区间与总上限，返回最终延迟（秒）。

    顺序契约（与旧内联实现逐字一致，不可换序）：
    1. delay_min>0 且 delay_max>0 且 min>max → 互换（防手滑）；
    2. delay_max>0 → 上界裁剪；
    3. delay_min>0 → 下界抬升；
    4. 无条件夹到 [0, total_cap]（total_cap<=0 时结果为 0，保留旧语义）。

    0 表示"不限制"（第 1/2/3 步的 >0 守卫即此意）。
    """
    d_min = float(delay_min or 0.0)
    d_max = float(delay_max or 0.0)
    if d_min > 0 and d_max > 0 and d_min > d_max:
        d_min, d_max = d_max, d_min
    result = float(delay)
    if d_max > 0:
        result = min(result, d_max)
    if d_min > 0:
        result = max(result, d_min)
    cap = float(total_cap if total_cap is not None else 0.0)
    result = max(0.0, min(result, cap))
    return result


def split_plan(
    text: str,
    *,
    enabled: bool,
    threshold: float = 40.0,
    max_segments: int = 3,
    min_part: int = 8,
) -> Optional[list[str]]:
    """分段发送方案：enabled 且拆出 >1 段时返回气泡列表，否则 None。

    None 语义 = 不拆（功能关 / 文本空 / 拆分结果 ≤1 段）——调用方保持
    待发链不动，交框架原路发送。拆分算法委托 typing.split_reply_bubbles。
    """
    if not enabled:
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    bubbles = split_reply_bubbles(
        text,
        threshold=threshold,
        max_segments=max_segments,
        min_part=min_part,
    )
    if len(bubbles) <= 1:
        return None
    return list(bubbles)


def backfill_bubbles(bubbles: list, failed_at: Optional[int]) -> list:
    """某段发送失败时，回填待发链的未发段（失败段起，含失败段）。

    无失败（None）返回空列表（不回填）。越界/非法下标安全回落空列表，
    保证"失败段+未发段交回框架"的兜底不因下标错误而丢内容。
    """
    if failed_at is None:
        return []
    try:
        idx = int(failed_at)
    except (TypeError, ValueError):
        return []
    if idx < 0:
        idx = 0
    return list(bubbles[idx:])


__all__ = [
    "backfill_bubbles",
    "dedupe_hit",
    "resolve_delay_bounds",
    "split_plan",
    "voice_only_sent",
]
