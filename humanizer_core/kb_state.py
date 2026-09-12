# -*- coding: utf-8 -*-
"""KB 索引指纹状态（v3.9.5，纯函数 + 原子存取，零 astrbot 依赖）。

解决的问题：语料导入/提炼后旧索引被继续使用（批次数量相同即误判"已同步"），
以及 embedding 变更后向量索引不重建。指纹 = 语料内容序列 + embedding
provider + 索引结构版本的 SHA-256；rerank 不进指纹（由 _rerank_drift
单独治理，rerank 变化只 update 不重传）。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Iterable, Optional

from .state import _atomic_write_json

# 分块/上传布局变化时 +1（触发全量重建）
INDEX_SCHEMA_VERSION = 2


def corpus_signature(rows: Iterable[dict]) -> str:
    """有效语料行的内容签名（source+content 稳定序列 → SHA-256）。"""
    h = hashlib.sha256()
    for r in rows:
        if not isinstance(r, dict):
            continue
        src = str(r.get("source", "") or "")
        content = str(r.get("content", "") or "")
        h.update(src.encode("utf-8", "replace"))
        h.update(b"\x00")
        h.update(content.encode("utf-8", "replace"))
        h.update(b"\x01")
    return h.hexdigest()


def index_fingerprint(corpus_sig: str, embedding_id: str = "") -> str:
    """索引新鲜度指纹：语料签名 + embedding provider + 结构版本。"""
    h = hashlib.sha256()
    h.update(str(corpus_sig or "").encode("utf-8", "replace"))
    h.update(b"|")
    h.update(str(embedding_id or "").encode("utf-8", "replace"))
    h.update(b"|")
    h.update(str(INDEX_SCHEMA_VERSION).encode("ascii"))
    return h.hexdigest()


def file_hint(path) -> tuple:
    """语料源文件的廉价变更提示（mtime_ns, size）；不存在返回 (0, 0)。"""
    try:
        st = Path(path).stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def load_state(path) -> dict:
    """读取 kb_index_state.json；损坏/缺失按空表（各 KB 视为需一次性重建）。"""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    kbs = raw.get("kbs") if isinstance(raw, dict) else None
    out: dict[str, dict] = {}
    if isinstance(kbs, dict):
        for name, st in kbs.items():
            if isinstance(name, str) and isinstance(st, dict) and st.get("fingerprint"):
                out[name] = st
    return out


def save_state(path, state: dict) -> None:
    """原子写全量指纹状态。"""
    _atomic_write_json(
        Path(path),
        {"version": 1, "updated": time.time(), "kbs": dict(state or {})},
    )


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "corpus_signature",
    "file_hint",
    "index_fingerprint",
    "load_state",
    "save_state",
]
