# -*- coding: utf-8 -*-
"""语料 → 风格档案的 LLM 提炼/融合提示词构造。

纯字符串构造，无 LLM 调用，便于单元测试。
输出要求：让 LLM 只返回一个 JSON 对象，符合 style_core/profiles.py 的档案结构。
"""

# 档案字段说明，注入提炼提示词，约束 LLM 输出
_FIELD_GUIDE = """输出一个 JSON 对象（不要输出任何其他文字、不要用 markdown 代码块包裹），字段：
- "name": 给这套风格起一个简短的名字（2-8 个中文字符）
- "description": 一句话描述这套风格给人的感觉（20 字以内）
- "persona": 用一句话描述说话者的人设（如"像熟悉的朋友，随意但有分寸"）
- "catchphrases": 从中提炼 2-5 个出现频率高的口头禅/习惯用语（原文照抄）
- "sentence_patterns": 3-6 条句式特征（如"多用短句""爱用语气词 啊/呢/嘛"）
- "emotion_expressions": 2-4 条情绪表达习惯（如"开心用「哈哈哈哈」""惊讶用「哇」"）
- "avoid": 3-5 条这套语料里不出现/很少出现的表达（书面语、官方腔等）
- "examples": 从中挑选 3-5 句最有代表性的原句作为示例"""


def build_extract_prompt(sampled: list[str], source_note: str = "") -> str:
    """全量提炼提示词。sampled 为采样到的语料句子列表。"""
    lines = [
        "你是一位语言风格分析专家。下面是一些人类真实对话的句子，",
        "请分析这些句子的共同语言风格，提炼出一份「说话风格档案」，",
        "用于指导聊天机器人在回复时模仿这种人类说话方式。",
    ]
    if source_note:
        lines.append(f"（语料来源：{source_note}）")
    lines.append("")
    lines.append("语料句子（每行一句）：")
    lines.append("----------")
    for i, s in enumerate(sampled, 1):
        lines.append(f"{i}. {s}")
    lines.append("----------")
    lines.append(_FIELD_GUIDE)
    lines.append("")
    lines.append("要求：catchphrases 等引用原句时必须原文照抄，不要改写或编造；"
                 "如果某类特征不明显，该字段用空数组 []。")
    return "\n".join(lines)


def build_refine_prompt(old_profile: dict, sampled: list[str], source_note: str = "") -> str:
    """增量融合提示词：旧档案 + 新语料 → 融合版档案。

    old_profile 为已有档案（规范化 dict），sampled 为新语料的采样句子。
    """
    import json as _json

    old = _json.dumps(old_profile, ensure_ascii=False, indent=2)
    lines = [
        "你是一位语言风格分析专家。现有聊天机器人正在使用一份说话风格档案，",
        "现在补充了一些新的真实人类对话句子，请把新语料中值得吸收的语言特点",
        "融合进旧档案，输出一份更新后的风格档案。",
    ]
    if source_note:
        lines.append(f"（新语料来源：{source_note}）")
    lines.append("")
    lines.append("【旧档案】")
    lines.append(old)
    lines.append("")
    lines.append("【新增语料句子】")
    lines.append("----------")
    for i, s in enumerate(sampled, 1):
        lines.append(f"{i}. {s}")
    lines.append("----------")
    lines.append(_FIELD_GUIDE)
    lines.append("")
    lines.append("要求：")
    lines.append("- 保留旧档案中仍然成立的特点（口癖、句式、避免项不要无故丢弃）")
    lines.append("- 从新语料中吸收明显的新特点，并补充进对应字段")
    lines.append("- name 保持不变（除非新风格差异太大，可微调但不超过 8 字）")
    lines.append("- catchphrases 等引用原句时必须原文照抄，不要改写或编造")
    lines.append("- 只输出 JSON 对象，不要输出任何其他文字")
    return "\n".join(lines)


def parse_profile_json(text: str) -> dict | None:
    """从 LLM 输出中提取档案 JSON。

    容错：去掉 markdown 代码块围栏、找首个 { 到最后一个 } 之间的内容。
    解析失败返回 None。
    """
    import json as _json
    import re as _re

    if not text:
        return None
    t = text.strip()
    # 去掉 ```json ... ``` 围栏
    t = _re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=_re.I)
    # 找首个 { 到最后一个 }
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = _json.loads(t[start:end + 1])
    except _json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data
