# -*- coding: utf-8 -*-
"""colleague-skill 产物 → Humanizer 风格档案 的导入器。

colleague-skill（github.com/titanwings/colleague-skill）把一个真实人物的
五层人格（persona.md）+ 元信息（meta.json）蒸馏成独立技能。本模块把这类
产物转换为 Humanizer 的档案 JSON 结构（见 style_core/profiles.py），
映射规则：
  L0 核心人格 / L1 身份   → persona
  L2 表达风格（口癖/句式/情绪）→ catchphrases / sentence_patterns / emotion_expressions
  L3 决策模式             → decision_rules
  L4 人际脚本             → interaction_scripts
  L5 边界雷区             → avoid
  corrections 段          → corrections（若 persona.md 含纠错记录）

转换依赖 LLM（格式转换 prompt），本模块只做 prompt 构造与 meta.json 容错解析，
不发起 LLM 调用，便于单元测试。不依赖 astrbot。
"""

import json
import re

# meta.json 中会并入转换 prompt 的字段（标签/印象最能补充档案描述）
_META_BRIEF_FIELDS = ("profile", "tags", "impression")

# 转换 prompt 中的档案字段说明（与 extract_prompt._FIELD_GUIDE 保持同步。
# v2.9.4 终审修复：name 要求 LLM 起一个 1-8 字名（保存时由调用方强制覆盖）——
# 此前要求留空 "" 会被 validate_profile 的 MIN_NAME_LEN=1 拒绝，导致整链失败）
_FIELD_GUIDE = """{
  "name": "根据人物起一个 1-8 字的名字",
  "description": "一句话描述",
  "persona": "人设",
  "catchphrases": ["口癖"],
  "sentence_patterns": ["句式"],
  "emotion_expressions": ["情绪表达"],
  "avoid": ["避免"],
  "decision_rules": ["决策模式"],
  "interaction_scripts": ["人际脚本"],
  "corrections": [{"scene": "场景", "wrong": "错误说法", "correct": "正确说法"}],
  "examples": ["示例"]
}"""


def parse_colleague_meta(text: str) -> dict | None:
    """容错解析 colleague-skill 的 meta.json 文本。失败返回 None。

    容错方式：剥 markdown 围栏、取首个 { 到最后一个 }、JSON 解析。
    """
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(t[start:end + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def build_colleague_import_prompt(meta: dict | None, persona_text: str, source_note: str = "") -> str:
    """组装格式转换 prompt：colleague persona/meta → Humanizer 档案 JSON。

    meta 为 parse_colleague_meta 的产物（可 None）；persona_text 为 persona.md
    全文（五层人格结构）。返回完整 prompt 字符串。
    """
    lines = [
        "你是一位人格建模专家。下面是一个真实人物的人格档案（来自 colleague-skill 的",
        "五层人格产物），请把它转换成一份「说话风格档案」，用于指导聊天机器人",
        "在回复时模仿这个人的说话方式与判断方式。",
    ]
    if source_note:
        lines.append(f"（来源：{source_note}）")
    lines.append("")
    if meta:
        lines.append("【人物元信息（meta.json）】")
        brief = {k: meta.get(k) for k in _META_BRIEF_FIELDS if meta.get(k) is not None}
        if brief:
            lines.append(json.dumps(brief, ensure_ascii=False, indent=2))
            lines.append("")
    lines.append("【五层人格档案（persona.md）】")
    lines.append("----------")
    lines.append(persona_text.strip() or "（空）")
    lines.append("----------")
    lines.append("")
    lines.append("请把上述内容映射为以下 JSON 结构（不要输出任何其他文字、不要用 markdown 代码块包裹）：")
    lines.append(_FIELD_GUIDE)
    lines.append("")
    lines.append("映射规则：")
    lines.append("- 核心人格/身份 → persona；表达风格（口癖/句式/情绪）→ catchphrases / "
                 "sentence_patterns / emotion_expressions")
    lines.append("- 决策模式 → decision_rules；人际脚本 → interaction_scripts；边界雷区 → avoid")
    lines.append("- 若 persona.md 含「纠错记录」，转成 corrections 数组（每项含 scene/wrong/correct）；"
                 "没有则为 []")
    lines.append("- catchphrases 等引用原句时必须原文照抄，不要改写或编造")
    lines.append("- 某个维度素材不足时，对应字段用空数组 []")
    lines.append('- name 按人物起一个 1-8 字的名字，不要留空（保存时会被调用方覆盖）')
    return "\n".join(lines)
