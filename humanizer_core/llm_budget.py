# -*- coding: utf-8 -*-
"""插件额外 LLM 调用的单轮预算（v3.9.5，纯对象，零依赖）。

治理对象：深度改写候选切换、QC 二次改写等"一条回复内的多次模型尝试"。
不限制 AstrBot 主 Agent。deadline 用单调时钟；max_attempts 限逻辑尝试
次数（一次尝试 = 一个候选模型的一次调用）。
"""

from __future__ import annotations

import time
from typing import Callable, Optional


class LLMBudget:
    def __init__(
        self,
        total_timeout: float = 120.0,
        max_attempts: int = 2,
        clock: Callable[[], float] = time.monotonic,
    ):
        try:
            total_timeout = float(total_timeout)
        except (TypeError, ValueError):
            total_timeout = 120.0
        self._clock = clock or time.monotonic
        self.deadline: Optional[float] = (
            self._clock() + total_timeout if total_timeout > 0 else None
        )
        try:
            n = int(max_attempts)
        except (TypeError, ValueError):
            n = 2
        self.max_attempts = n if n >= 1 else 2  # 非法/非正值回落默认
        self.used = 0

    @property
    def exhausted(self) -> bool:
        if self.used >= self.max_attempts:
            return True
        return self.deadline is not None and self._clock() >= self.deadline

    def remaining(self) -> Optional[float]:
        """剩余预算秒数；无 deadline 返回 None（不限总时长）。"""
        if self.deadline is None:
            return None
        return max(0.05, self.deadline - self._clock())

    def per_call_timeout(self, cap: float) -> float:
        """单次调用的超时上限 = min(配置 cap, 剩余预算)；无 deadline 取 cap。"""
        rem = self.remaining()
        if rem is None:
            return float(cap)
        return min(float(cap), rem)

    def record_attempt(self) -> None:
        self.used += 1


__all__ = ["LLMBudget"]
