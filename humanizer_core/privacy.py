# -*- coding: utf-8 -*-
"""隐私脱敏（v4.7.0）。

控制台「最近清理明细」只用于调试排障，但 before/after 片段来自用户回复，
可能包含手机号、邮箱、QQ 号/验证码等。统一在写入内存环前掩码，避免调试
信息外泄；该模块只做文本替换，无副作用，便于单测。
"""

import re

_PATTERNS = (
    # 邮箱（先处理，避免 @ 前缀被长数字规则截断）
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[邮箱]"),
    # 中国大陆手机号：保留前 3 后 4
    (
        re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:],
    ),
    # 5-12 位连续数字（QQ 号、验证码、订单号等）：保留前 2 后 2
    (
        re.compile(r"(?<!\d)\d{5,12}(?!\d)"),
        lambda m: m.group(0)[:2] + "***" + m.group(0)[-2:],
    ),
)


def mask_pii(text: str) -> str:
    """对文本中的邮箱/手机号/长数字做掩码；异常时原样返回。"""
    out = str(text or "")
    for pattern, repl in _PATTERNS:
        try:
            out = pattern.sub(repl, out)
        except Exception:  # noqa: BLE001
            pass
    return out
