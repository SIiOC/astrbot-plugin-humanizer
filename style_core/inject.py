# -*- coding: utf-8 -*-
"""档案 + 检索示例 → system_prompt 指令段渲染。

注入内容带清晰的分隔标记，便于用户从系统提示词里识别和删除。
不依赖 astrbot，便于单元测试。
"""

SECTION_HEADER = "【人类对话风格】"
SECTION_FOOTER = "【/人类对话风格】"
EXAMPLE_HEADER = "【参考的人类对话示例（模仿其语气，不要照抄）】"
EXAMPLE_FOOTER = "【/参考示例】"

MAX_EXAMPLE_CHARS = 120  # 单条示例最大展示字符数
MAX_EXAMPLES = 5         # 单次注入最大示例条数


def _fmt_list(items, prefix="  - "):
    return "\n".join(f"{prefix}{x}" for x in items)


def build_style_section(profile: dict) -> str:
    """把风格档案渲染成注入 system_prompt 的指令段。

    profile 须为已规范化的档案（缺字段为空列表/空字符串）。
    返回带分隔标记的完整段落；档案全空时返回空字符串（不注入）。
    """
    lines = [SECTION_HEADER, "回复时遵循以下人类说话风格："]

    persona = profile.get("persona", "")
    if persona:
        lines.append(f"- 人设：{persona}")

    catchphrases = profile.get("catchphrases", [])
    if catchphrases:
        lines.append("- 口癖：偶尔自然地使用" + "、".join(f"「{c}」" for c in catchphrases))

    patterns = profile.get("sentence_patterns", [])
    if patterns:
        lines.append("- 句式：" + _fmt_list(patterns, "").replace("\n", "；"))

    emotions = profile.get("emotion_expressions", [])
    if emotions:
        lines.append("- 情绪表达：" + "；".join(emotions))

    avoid = profile.get("avoid", [])
    if avoid:
        lines.append("- 避免：" + "、".join(avoid))

    examples = profile.get("examples", [])
    if examples:
        lines.append("- 语气参考示例：")
        lines.append(_fmt_list(examples[:MAX_EXAMPLES]))

    lines.append(SECTION_FOOTER)

    # 档案全空（只有 name）时视为无效，不注入
    body = lines[1:-1]
    if len(body) <= 1:  # 只有 "回复时遵循以下人类说话风格："
        return ""
    return "\n".join(lines) + "\n"


def build_example_section(rows, top_k: int = MAX_EXAMPLES) -> str:
    """把检索到的人类对话片段渲染成示例段。

    rows: 检索结果列表，元素为 dict，含 "user"/"assistant" 或 "content" 键
          （与 base.jsonl 语料池格式一致：user/assistant 交替行成对）。
    rows 为空时返回空字符串。
    """
    pairs = _pair_rows(rows)
    if not pairs:
        return ""
    lines = [EXAMPLE_HEADER, "下面这些是人类真实的对话片段，模仿它们说话的语气和用词："]
    shown = 0
    for u, a in pairs:
        if shown >= top_k:
            break
        lines.append(f"- 人：{_truncate(u)}")
        lines.append(f"  回应：{_truncate(a)}")
        shown += 1
    lines.append(EXAMPLE_FOOTER)
    return "\n".join(lines) + "\n"


def _pair_rows(rows) -> list[tuple[str, str]]:
    """把语料池行配对成 (user, assistant)。

    兼容两种输入：成对 dict {"role": "user"/"assistant", "content"} 相邻交替；
    或单条 dict {"user": ..., "assistant": ...}。
    """
    pairs = []
    if not rows:
        return pairs
    if "user" in rows[0] and "assistant" in rows[0]:
        for r in rows:
            u = r.get("user", "")
            a = r.get("assistant", "")
            if u and a:
                pairs.append((u, a))
        return pairs
    # role/content 交替格式
    i = 0
    while i + 1 < len(rows):
        r1, r2 = rows[i], rows[i + 1]
        if r1.get("role") == "user" and r2.get("role") == "assistant":
            u = r1.get("content", "")
            a = r2.get("content", "")
            if u and a:
                pairs.append((u, a))
            i += 2
        else:
            i += 1
    return pairs


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) > MAX_EXAMPLE_CHARS:
        return text[:MAX_EXAMPLE_CHARS] + "…"
    return text
