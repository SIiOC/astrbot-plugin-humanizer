# -*- coding: utf-8 -*-
"""多格式语料解析、去重、采样与语料池管理。

语料池文件格式（与 corpora/base.jsonl 一致）：每行一个 JSON 对象
{"role": "user"|"assistant", "content": "..."}，user/assistant 两行交替组成一个问答对。

支持导入格式（/style_import 自动识别）：
- txt  按行：每行一句
- jsonl：{"role":..., "content":...} 或 {"content":...}
- json 数组：["句1","句2"] 或 [{"content":...}] 或 [{"user":..., "assistant":...}]
- csv：含 content/text/query/response 列

不依赖 astrbot，便于单元测试。
"""

import csv
import hashlib
import io
import json
import os
import random

MIN_SENT_LEN = 2     # 导入语料的最短长度（字符）
MAX_SENT_LEN = 200   # 导入语料的最长长度（字符）


def _normalize_pair(user: str, assistant: str) -> tuple[str, str] | None:
    u = (user or "").strip()
    a = (assistant or "").strip()
    if not u or not a:
        return None
    if len(u) < MIN_SENT_LEN or len(u) > MAX_SENT_LEN:
        return None
    if len(a) < MIN_SENT_LEN or len(a) > MAX_SENT_LEN:
        return None
    return (u, a)


def parse_txt(text: str) -> list[tuple[str, str]]:
    """txt 按行：相邻两行组成问答对。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    pairs = []
    i = 0
    while i + 1 < len(lines):
        p = _normalize_pair(lines[i], lines[i + 1])
        if p:
            pairs.append(p)
        i += 2
    return pairs


def parse_jsonl(text: str) -> list[tuple[str, str]]:
    """jsonl：逐行解析 dict。
    - {"role": "user"/"assistant", "content": "..."} 相邻交替成对
    - {"content": "..."} 相邻两行成对
    - {"user": "...", "assistant": "..."} 单行即一对
    """
    pairs = []
    buf = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if "user" in obj and "assistant" in obj:
            p = _normalize_pair(obj.get("user", ""), obj.get("assistant", ""))
            if p:
                pairs.append(p)
            continue
        content = obj.get("content")
        if content is None:
            continue
        role = obj.get("role", "")
        if role == "assistant":
            buf.append(content)
            if len(buf) >= 2:
                p = _normalize_pair(buf[-2], buf[-1])
                if p:
                    pairs.append(p)
        elif role == "user":
            buf.append(content)
        else:
            # 无 role 标记（仅 {"content": ...}）：相邻两行直接配对
            buf.append(content)
            if len(buf) >= 2:
                p = _normalize_pair(buf[-2], buf[-1])
                if p:
                    pairs.append(p)
    return pairs


def parse_json_array(text: str) -> list[tuple[str, str]]:
    """json 数组：
    - ["句1","句2",...] 相邻交替成对
    - [{"content": ...}] 相邻成对
    - [{"user":..., "assistant":...}] 单条成对
    """
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(arr, list):
        return []
    pairs = []
    prev = None
    for item in arr:
        if isinstance(item, str):
            if prev is None:
                prev = item
            else:
                p = _normalize_pair(prev, item)
                if p:
                    pairs.append(p)
                prev = None
        elif isinstance(item, dict):
            if "user" in item and "assistant" in item:
                p = _normalize_pair(item.get("user", ""), item.get("assistant", ""))
                if p:
                    pairs.append(p)
            elif "content" in item:
                content = str(item.get("content", "")).strip()
                if prev is None:
                    prev = content
                else:
                    p = _normalize_pair(prev, content)
                    if p:
                        pairs.append(p)
                    prev = None
    return pairs


def parse_csv(text: str) -> list[tuple[str, str]]:
    """csv：取 query/response 或 user/assistant 或 content/text 列。"""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    fn = [f.strip().lower() for f in reader.fieldnames]
    q_col = next((c for c in ("query", "user", "q") if c in fn), None)
    r_col = next((c for c in ("response", "assistant", "answer", "a") if c in fn), None)
    if q_col is None or r_col is None:
        # 退化为 content/text 列相邻成对
        c_col = next((c for c in ("content", "text") if c in fn), None)
        if c_col is None:
            return []
        rows = [row.get(c_col, "") for row in reader]
        pairs = []
        i = 0
        while i + 1 < len(rows):
            p = _normalize_pair(rows[i], rows[i + 1])
            if p:
                pairs.append(p)
            i += 2
        return pairs
    pairs = []
    for row in reader:
        p = _normalize_pair(row.get(q_col, ""), row.get(r_col, ""))
        if p:
            pairs.append(p)
    return pairs


def parse_corpus_text(text: str, filename: str = "") -> list[tuple[str, str]]:
    """按内容自动识别格式并解析。filename 可辅助判断扩展名。

    返回问答对列表 [(user, assistant), ...]。
    """
    name = (filename or "").lower()
    stripped = text.strip()
    if not stripped:
        return []
    if name.endswith(".csv"):
        return parse_csv(text)
    if name.endswith(".jsonl"):
        return parse_jsonl(text)
    if name.endswith(".json"):
        return parse_json_array(stripped)
    if name.endswith(".txt"):
        return parse_txt(text)
    # 无扩展名：启发式
    if stripped.startswith("["):
        arr = parse_json_array(stripped)
        if arr:
            return arr
    if "\t" in stripped or "," in stripped:
        csv_pairs = parse_csv(text)
        if csv_pairs:
            return csv_pairs
    jsonl_pairs = parse_jsonl(text)
    if jsonl_pairs:
        return jsonl_pairs
    return parse_txt(text)


# ---------------------------------------------------------------- 语料池管理 --

def pair_key(user: str, assistant: str) -> str:
    return hashlib.md5((user + "\u0001" + assistant).encode("utf-8")).hexdigest()


def read_pool(path: str) -> list[dict]:
    """读取语料池文件（role/content 交替行）。文件不存在/损坏返回空列表。"""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "content" in obj:
                rows.append(obj)
    return rows


def write_pool(path: str, rows: list[dict]) -> None:
    """把语料池行写回文件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_pairs_to_pool(path: str, pairs: list[tuple[str, str]]) -> int:
    """把新问答对追加进语料池，按内容哈希去重。

    返回实际新增的问答对数。
    """
    existing = read_pool(path)
    seen = set()
    for row in existing:
        u = row.get("content", "") if row.get("role") == "user" else ""
        # 用相邻配对重建 key 太绕，直接对 content 去重（user/assistant 各自去重）
        seen.add(hashlib.md5(row.get("content", "").encode("utf-8")).hexdigest())
    added = 0
    new_rows = []
    for u, a in pairs:
        ku = hashlib.md5(u.encode("utf-8")).hexdigest()
        ka = hashlib.md5(a.encode("utf-8")).hexdigest()
        if ku in seen and ka in seen:
            continue
        new_rows.append({"role": "user", "content": u})
        new_rows.append({"role": "assistant", "content": a})
        seen.add(ku)
        seen.add(ka)
        added += 1
    if added:
        write_pool(path, existing + new_rows)
    return added


def sample_pool(rows: list[dict], n: int, seed: int = 42) -> list[dict]:
    """从语料池行中采样 n 行（按内容随机抽样）。rows 为空返回空列表。"""
    if not rows:
        return []
    rng = random.Random(seed)
    n = min(n, len(rows))
    return rng.sample(rows, n)


def merge_pool_rows(*row_lists) -> list[dict]:
    """合并多个语料池行列表，按 content 哈希跨池去重（先到者保留）。

    用于把内置 base 池与用户导入池合并成「有效语料」。
    None/空列表视为无内容。
    """
    seen = set()
    merged = []
    for rows in row_lists:
        if not rows:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            content = str(row.get("content", "") or "")
            if not content:
                continue
            key = hashlib.md5(content.encode("utf-8")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
    return merged


def sample_merged(base_rows: list[dict], user_rows: list[dict], n_lines: int,
                  seed: int = 42) -> list[dict]:
    """从「有效语料」（base + 用户导入）采样，用户语料优先。

    规则：
    - 用户语料够 n_lines 则全部从用户语料采样
    - 不够则用户语料全采，不足部分从 base 补足
    n_lines 为行数（自动取偶数，保证 user/assistant 成对）。
    """
    if n_lines <= 0:
        return []
    n_lines = n_lines if n_lines % 2 == 0 else n_lines - 1
    if n_lines <= 0:
        return []
    rng = random.Random(seed)
    user_rows = list(user_rows)
    rng.shuffle(user_rows)
    picked = user_rows[:n_lines]
    need = n_lines - len(picked)
    if need > 0 and base_rows:
        base_rows = list(base_rows)
        rng.shuffle(base_rows)
        picked.extend(base_rows[:need])
    return picked


def pool_stats(path: str) -> dict:
    """语料池统计：总行数、问答对数、空池判定。"""
    rows = read_pool(path)
    return {
        "lines": len(rows),
        "pairs": len(rows) // 2,
        "empty": len(rows) == 0,
    }


def new_files(files: list, imported: list) -> list[str]:
    """返回配置中尚未导入过的文件（相对路径）列表。

    用于检测用户在配置界面新上传的语料文件：只有新增的文件才触发导入/提炼。
    """
    imported_set = set(imported or [])
    result = []
    for f in files or []:
        if isinstance(f, str) and f not in imported_set:
            result.append(f)
    return result

