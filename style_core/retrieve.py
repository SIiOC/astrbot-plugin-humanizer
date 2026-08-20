# -*- coding: utf-8 -*-
"""检索结果的格式化与兜底。

main.py 调用框架 kb_manager.retrieve() 得到原始结果后，
交给本模块格式化为注入用的示例行；任何异常/空结果都返回 []，
由调用方静默回退纯风格注入，绝不影响回复。
不依赖 astrbot，便于单元测试。
"""

# kb_manager.retrieve() 返回结构（框架知识库）：
# {"context_text": ..., "results": [{"chunk_id", "content", "score", ...}, ...]}
# 若接入备选路径（自建向量库），返回结构统一在 main.py 转成以下两种之一：
#   成对 dict: {"user": ..., "assistant": ...}
#   交替行:    {"role": ..., "content": ...}

MAX_RESULTS = 20  # 单次最多接受的结果数


def flatten_results(raw) -> list[dict]:
    """把框架检索原始返回展平为语料池行列表。

    兼容：
    - {"results": [...]}（框架 kb_manager 结构）
    - [...]（直接列表）
    - None / 异常对象
    元素含 "content" 或 "chunk" 或 "text" 键则提取为行。
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        results = raw.get("results")
        if not isinstance(results, list):
            return []
        items = results
    elif isinstance(raw, list):
        items = raw
    else:
        return []
    rows = []
    for i, item in enumerate(items[:MAX_RESULTS]):
        if not isinstance(item, dict):
            continue
        content = item.get("content") or item.get("chunk") or item.get("text")
        if content:
            # 检索结果本身无说话人标记，交替标注 user/assistant 以成对展示
            role = "user" if i % 2 == 0 else "assistant"
            rows.append({"role": role, "content": str(content).strip()})
    return rows


def to_example_rows(rows: list[dict], top_k: int) -> list[dict]:
    """把展平行截断到 top_k（偶数对齐，保证 user/assistant 成对）。"""
    if not rows:
        return []
    rows = rows[: top_k * 2]
    return rows
