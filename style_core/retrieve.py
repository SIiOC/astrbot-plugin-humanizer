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


# ---------------------------------------------------------------------------
# v4.0 Phase 4：知识库命名/描述/结果扁平化的单一事实源（自 main.py 下沉）。
# 注意与下方 flatten_results 的区别：KB 检索结果按分数排序、无说话人语义，
# main 渲染注入段消费的是**不带 role** 的 {"content": ...} 行；
# flatten_results 的交替 user/assistant 形态是历史独立插件（human_style
# v1.x 自建向量库备选路径）的兼容读法，两者刻意不合并
# （tests/test_retrieve.py + test_style_kb_format 分别钉死各自契约）。
# ---------------------------------------------------------------------------

def sanitize_kb_name(style_name: str) -> str:
    """风格名 → 检索知识库名（非字母数字一律下划线，前缀 human_style_）。"""
    safe = "".join(c if c.isalnum() else "_" for c in style_name)
    return f"human_style_{safe}"


def build_kb_desc(style_name: str, rows: list[dict]) -> str:
    """检索知识库描述文案（内置/用户语料计数）；多处构建点共用单一事实源。"""
    builtin_cnt = sum(1 for r in rows if r.get("source") == "builtin")
    user_cnt = sum(1 for r in rows if r.get("source") == "user")
    return (
        f"人类对话风格 · 检索库 · 风格「{style_name}」"
        f" · 有效语料 内置 {builtin_cnt} + 用户 {user_cnt} = {len(rows)} 条"
        f" · 由 astrbot_plugin_wanna_be_human 自动创建，请勿手动删除；"
        f"关闭“自动创建检索知识库”或删除此库不影响风格档案"
    )


def flatten_content_rows(raw) -> list[dict]:
    """框架 kb_manager.retrieve() 返回 → 无角色 {"content"} 行列表。

    兼容 dict（{"results": [...]}）/直接 list/None；元素取
    content|chunk|text 首个非空，strip 后收录；任何异常结构 → 空列表
    （调用方静默回退纯风格注入，绝不影响回复）。
    """
    try:
        if raw is None:
            return []
        if isinstance(raw, dict):
            results = raw.get("results", [])
        elif isinstance(raw, list):
            results = raw
        else:
            return []
        rows = []
        for item in results:
            if not isinstance(item, dict):
                continue
            content = item.get("content") or item.get("chunk") or item.get("text")
            if content:
                rows.append({"content": str(content).strip()})
        return rows
    except Exception:  # noqa: BLE001
        return []


async def retrieve_section(
    kb_manager,
    *,
    kb_name: str,
    query: str,
    candidates: int,
    top_k: int,
    timeout: float,
) -> str:
    """单次底层检索 + 渲染（v4.0 Phase 4 自 main._kb_retrieve_section 下沉）。

    kb_manager 由调用方注入（duck-typed 协程 retrieve），保持本模块零
    astrbot 依赖、可用 fake 测试。语义逐字保留：
    - 正超时经 asyncio.wait_for 包裹（v3.4.5 事故同型防线：检索走
      embedding/rerank 供应商 HTTP，无超时挂起会卡死 on_llm_request 钩子）；
    - 结果经 flatten_content_rows 扁平化，空结果返回 ""；
    - 渲染委托 inject.build_example_section（延迟导入避免模块级依赖环）。
    - wait_for 超时/调用异常**不吞**，由调用方兜底（回退纯风格注入）。
    """
    import asyncio

    from . import inject

    result = await asyncio.wait_for(
        kb_manager.retrieve(
            query, kb_names=[kb_name], top_k_fusion=candidates, top_m_final=top_k
        ),
        timeout=timeout,
    )
    rows = flatten_content_rows(result)
    if not rows:
        return ""
    return inject.build_example_section(rows, top_k)


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
