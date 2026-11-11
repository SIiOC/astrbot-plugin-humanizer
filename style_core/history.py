# -*- coding: utf-8 -*-
"""从 AstrBot 会话库采集「用户本人」的语料（P0 手动学习）。

只读 SQLite 的 conversations 表，不改库；输出仍遵循语料池的问答对格式：
[(user_text, assistant_text), ...]。清洗规则针对 AstrBot 的消息内容结构：

- content 可能是 str，也可能是 [{"type": "text", "text": "..."}]；
- 用户消息常带 ``<system_reminder>...</system_reminder>``，必须剥掉；
- 命令、URL、纯表情、过短/过长、重复消息不进入语料。

模块不依赖 astrbot，便于单元测试；数据库路径由调用方注入。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3

MIN_USER_LEN = 2
MAX_USER_LEN = 120
MAX_ASSISTANT_LEN = 200
MAX_SCAN_MESSAGES = 600

_REMINDER_RE = re.compile(r"<system_reminder>.*?</system_reminder>", re.S | re.I)
_CMD_PREFIXES = ("/", "#", "／")
_URL_RE = re.compile(r"(https?://|www\.|t\.me/)", re.I)
_WORD_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")


def _extract_text(content) -> str:
    """从 AstrBot 消息 content 中取纯文本。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        # 只取用户可见的 text；think/tool 等内部内容不进语料。
        if item.get("type") not in (None, "text", "plain"):
            continue
        text = item.get("text")
        if text is None:
            text = item.get("content")
        if isinstance(text, str) and text:
            parts.append(text)
    return "".join(parts)


def clean_user_text(raw: str) -> str | None:
    """清洗一条用户消息；不合格返回 None。保留原始标点/错别字/口语碎片。"""
    if not isinstance(raw, str):
        return None
    text = _REMINDER_RE.sub("", raw)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if text.startswith(_CMD_PREFIXES):
        return None
    if _URL_RE.search(text):
        return None
    if not _WORD_RE.search(text):
        return None
    if not (MIN_USER_LEN <= len(text) <= MAX_USER_LEN):
        return None
    return text


def clean_assistant_text(raw: str) -> str | None:
    """清洗配对用的助手消息；只用于保持语料池的问答对格式。"""
    if not isinstance(raw, str):
        return None
    text = _REMINDER_RE.sub("", raw)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) < MIN_USER_LEN:
        return None
    return text[:MAX_ASSISTANT_LEN]


def pairs_from_messages(messages: list[dict], *, limit: int = 200) -> list[tuple[str, str]]:
    """从一段消息序列提取 (user, assistant) 对；跳过无下一条助手回复的用户消息。"""
    pairs: list[tuple[str, str]] = []
    for idx, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        user = clean_user_text(_extract_text(message.get("content")))
        if not user:
            continue
        # 只和紧挨着的下一条助手回复配对；中间隔着用户消息时不能跨过去配。
        nxt = messages[idx + 1] if idx + 1 < len(messages) else None
        if not isinstance(nxt, dict) or nxt.get("role") != "assistant":
            continue
        assistant = clean_assistant_text(_extract_text(nxt.get("content")))
        if assistant:
            pairs.append((user, assistant))
            if len(pairs) >= limit:
                break
    return pairs


def collect_pairs_from_db(
    db_path: str,
    *,
    user_id_like: str = "",
    platform_id: str = "",
    conversation_limit: int = 20,
    pair_limit: int = 200,
) -> list[tuple[str, str]]:
    """从最近若干会话收集用户消息对；按用户文本去重。

    ``user_id_like`` 传发送者 QQ 号即可（内部按 ``%:QQ`` 匹配 AstrBot 的
    ``platform:FriendMessage:QQ`` 结构）；群聊的 user_id 是群号，本函数
    只适合私聊。返回按时间从旧到新排列，最多 ``pair_limit`` 对。
    """
    if not db_path or not os.path.exists(db_path):
        return []
    clauses = []
    params: list[str] = []
    if user_id_like:
        clauses.append("user_id LIKE ?")
        params.append(f"%:{user_id_like}")
    if platform_id:
        clauses.append("platform_id = ?")
        params.append(platform_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        "SELECT content FROM conversations"
        + where
        + " ORDER BY updated_at DESC LIMIT ?"
    )
    params.append(str(max(1, int(conversation_limit))))
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()

    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    # rows 是最新在前；反过来按时间从旧到新扫描。
    for row in reversed(rows):
        try:
            messages = json.loads(row["content"])
        except (TypeError, ValueError):
            continue
        if not isinstance(messages, list):
            continue
        for user, assistant in pairs_from_messages(messages, limit=pair_limit):
            key = hashlib.md5(user.encode("utf-8")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            pairs.append((user, assistant))
            if len(pairs) >= pair_limit:
                break
        if len(pairs) >= pair_limit:
            break
    return pairs


def filter_new_pairs(path: str, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """去掉语料池里已存在的用户文本（按 user content 去重）。"""
    from .corpus import read_pool

    existing = set()
    for row in read_pool(path):
        if isinstance(row, dict) and row.get("role") == "user":
            content = str(row.get("content", "") or "")
            if content:
                existing.add(hashlib.md5(content.encode("utf-8")).hexdigest())
    fresh: list[tuple[str, str]] = []
    for user, assistant in pairs:
        key = hashlib.md5(user.encode("utf-8")).hexdigest()
        if key in existing:
            continue
        fresh.append((user, assistant))
        existing.add(key)
    return fresh


def summarize_pairs(pairs: list[tuple[str, str]]) -> dict:
    """给命令预览用的轻量统计；不返回消息原文。"""
    lengths = [len(user) for user, _ in pairs]
    return {
        "count": len(pairs),
        "avg_len": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "short": sum(1 for n in lengths if n < 10),
        "max_len": max(lengths) if lengths else 0,
    }
