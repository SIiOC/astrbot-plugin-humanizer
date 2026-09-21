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
from typing import Iterable

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


async def iter_all_documents(kb, page_size: int = 100) -> list:
    """分页聚合 KB 全部文档（v4.0 Phase 4 自 main 下沉，逐字等价）。

    框架 list_documents 默认只取 100 条。kb 由调用方注入（duck-typed
    list_documents/count_documents 协程），本模块保持零 astrbot 依赖。
    容错语义（不可变更，均有测试钉死）：
    - 无 list_documents 属性 → 空列表
    - count_documents 异常 → total=None（仅依赖页长判断终止）
    - 单页请求异常 → 丢弃后续页、保留已累计部分
    - 空页/短页/offset 达 total → 正常终止
    """
    docs: list = []
    if not hasattr(kb, "list_documents"):
        return docs
    try:
        total = await kb.count_documents()
    except Exception:  # noqa: BLE001
        total = None
    offset = 0
    while True:
        try:
            page = await kb.list_documents(offset=offset, limit=page_size) or []
        except Exception:  # noqa: BLE001
            break
        if not page:
            break
        docs.extend(page)
        offset += len(page)
        if len(page) < page_size or (total is not None and offset >= int(total)):
            break
    return docs


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "corpus_signature",
    "file_hint",
    "index_fingerprint",
    "iter_all_documents",
    "load_state",
    "save_state",
]
