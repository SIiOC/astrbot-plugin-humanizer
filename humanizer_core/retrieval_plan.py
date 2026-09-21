# -*- coding: utf-8 -*-
"""检索规划纯函数（v4.0 Phase 4/8，从 main._retrieve_examples 下沉）。

把检索前的参数派生（top_k 夹逼、rerank 候选池、检索超时校验、缓存键
摘要）集中为可离线单测的纯函数；框架读取（event/kb_manager/config）与
IO 编排留在 main 适配层。

语义逐字对齐旧内联实现：
- top_k：`max(1, min(cfg, 5))`，cfg 非法回落 3；
- 候选池：仅 rerank 生效时放大到 `max(top_k, min(cfg_default_12, 30))`；
  非 rerank 时恒等于 top_k；
- 检索超时：非法/非正一律回落 5.0（v3.7.0 事故同型防线）；
- 缓存键摘要：查询完整规范化文本的 sha256 前 24 位（前缀截断会让长查询
  前 64 字相同者错误命中同一缓存）。
"""

from __future__ import annotations

import hashlib
from typing import Any

_TOP_K_DEFAULT = 3
_TOP_K_MAX = 5
_RERANK_CANDIDATES_DEFAULT = 12
_RERANK_CANDIDATES_MAX = 30
_RETRIEVAL_TIMEOUT_DEFAULT = 5.0


def clamp_top_k(raw: Any, default: int = _TOP_K_DEFAULT) -> int:
    """检索 top_k：非法回落 default，再夹到 [1, 5]。"""
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = default
    return max(1, min(val, _TOP_K_MAX))


def resolve_candidates(
    rerank_active: bool,
    top_k: int,
    raw_candidates: Any = None,
) -> int:
    """检索候选池大小。

    非 rerank：恒等于 top_k（候选池==top_k 时重排只在几条内换序，无价值）。
    rerank 生效：`int(raw or 12)`（0/None/空 → 12；非法 → 12），
    再夹到 [top_k, 30]（候选池不得小于 top_k）。
    """
    if not rerank_active:
        return top_k
    try:
        val = int(raw_candidates or _RERANK_CANDIDATES_DEFAULT)
    except (TypeError, ValueError):
        val = _RERANK_CANDIDATES_DEFAULT
    return max(top_k, min(val, _RERANK_CANDIDATES_MAX))


def resolve_retrieval_timeout(
    raw: Any, default: float = _RETRIEVAL_TIMEOUT_DEFAULT
) -> float:
    """检索超时（秒）：非法/非正一律回落 default（防无超时挂起卡死钩子）。"""
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    if not (val > 0):
        return default
    return val


def query_digest(query: str) -> str:
    """查询完整规范化文本的摘要（空白折叠 + sha256 前 24 位）。"""
    norm = " ".join(str(query or "").split())
    return hashlib.sha256(norm.encode("utf-8", "replace")).hexdigest()[:24]


__all__ = [
    "clamp_top_k",
    "query_digest",
    "resolve_candidates",
    "resolve_retrieval_timeout",
]
