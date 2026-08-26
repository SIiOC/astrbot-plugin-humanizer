# -*- coding: utf-8 -*-
"""风格档案：数据结构、加载、校验。

档案是插件注入 LLM 提示词的核心数据。结构：
{
  "name": "日常口语风",
  "description": "像朋友闲聊一样自然",
  "persona": "像熟悉的朋友，随意但有分寸",
  "catchphrases": ["说实话", "我跟你说"],      # 口癖
  "sentence_patterns": ["多用短句", "带语气词 啊/呢/嘛"],
  "emotion_expressions": ["开心用「哈哈哈哈」", "惊讶用「哇」"],
  "avoid": ["官方腔", "排比句", "书面连接词"],
  "decision_rules": ["先确认背景再讨论", "数据 > 技术可行性 > 人情"],  # L3 决策模式
  "interaction_scripts": ["对上级先给结论再展开", "平级直接反问"],      # L4 人际脚本
  "corrections": [{"scene": "被夸时", "wrong": "客气推辞", "correct": "坦然接受"}],  # 纠错记录
  "examples": ["几句示例"]
}

规则：全部为可选的字符串/字符串列表字段；缺字段的档案仍可用（渲染时跳过）。
v2.3.0 新增 decision_rules / interaction_scripts（字符串列表）与 corrections（对象列表），
对应 colleague-skill 五层人格的 L3 决策、L4 人际与纠错记录。
不依赖 astrbot，便于单元测试。
"""

import json
import os

# 档案允许的顶层字段（其余字段保留但忽略，便于未来扩展）
ALLOWED_FIELDS = {
    "name", "description", "persona", "catchphrases",
    "sentence_patterns", "emotion_expressions", "avoid", "examples",
    "decision_rules", "interaction_scripts", "corrections",
}
# 必须为字符串列表的字段
LIST_FIELDS = {
    "catchphrases", "sentence_patterns", "emotion_expressions", "avoid", "examples",
    "decision_rules", "interaction_scripts",
}

MIN_NAME_LEN = 1
MAX_NAME_LEN = 32

# 纠错记录（corrections）约束：单条 200 字上限，最多 20 条
MAX_CORRECTION_CHARS = 200
MAX_CORRECTIONS = 20


def validate_profile(data) -> str | None:
    """校验档案 dict。返回 None 表示合法，否则返回错误信息字符串。"""
    if not isinstance(data, dict):
        return "档案必须是 JSON 对象"
    name = data.get("name", "")
    if not isinstance(name, str) or not (MIN_NAME_LEN <= len(name) <= MAX_NAME_LEN):
        return f"档案 name 需为 {MIN_NAME_LEN}-{MAX_NAME_LEN} 字符的字符串"
    for field in data:
        if field not in ALLOWED_FIELDS:
            return f"未知字段: {field}"
    for field in LIST_FIELDS:
        val = data.get(field)
        if val is None:
            continue
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            return f"字段 {field} 需为字符串列表"
        if len(val) > 50:
            return f"字段 {field} 条目过多（上限 50）"
    for field in ("description", "persona"):
        val = data.get(field)
        if val is not None and not isinstance(val, str):
            return f"字段 {field} 需为字符串"
    corr_err = validate_corrections(data.get("corrections"))
    if corr_err is not None:
        return corr_err
    return None


def validate_corrections(val) -> str | None:
    """校验 corrections 字段。返回 None 表示合法，否则返回错误信息字符串。

    结构：列表，每项为 dict {"scene": str, "wrong": str, "correct": str}，
    三项均非空字符串，单条各字段 ≤ MAX_CORRECTION_CHARS，列表 ≤ MAX_CORRECTIONS。
    """
    if val is None:
        return None
    if not isinstance(val, list):
        return "字段 corrections 需为列表"
    if len(val) > MAX_CORRECTIONS:
        return f"字段 corrections 条目过多（上限 {MAX_CORRECTIONS}）"
    for i, item in enumerate(val):
        if not isinstance(item, dict):
            return f"字段 corrections[{i}] 需为对象 {{scene, wrong, correct}}"
        for key in ("scene", "wrong", "correct"):
            v = item.get(key)
            if not isinstance(v, str) or not v.strip():
                return f"字段 corrections[{i}].{key} 需为非空字符串"
            if len(v.strip()) > MAX_CORRECTION_CHARS:
                return f"字段 corrections[{i}].{key} 过长（上限 {MAX_CORRECTION_CHARS} 字）"
    return None


def normalize_profile(data: dict) -> dict:
    """规范化：剔除未知字段、补空列表、剥离空白条目。输入须已通过校验。"""
    out = {}
    for field in ALLOWED_FIELDS:
        val = data.get(field)
        if val is None:
            if field in LIST_FIELDS:
                out[field] = []
            elif field == "corrections":
                out[field] = []
            else:
                out[field] = ""
            continue
        if field in LIST_FIELDS:
            out[field] = [str(x).strip() for x in val if str(x).strip()]
        elif field == "corrections":
            out[field] = normalize_corrections(val)
        else:
            out[field] = str(val).strip()
    return out


def normalize_corrections(val: list) -> list:
    """清洗 corrections：剥离各字段空白、丢弃空项。输入须已通过校验。"""
    out = []
    for item in val:
        cleaned = {k: str(item.get(k, "")).strip() for k in ("scene", "wrong", "correct")}
        if all(cleaned.values()):
            out.append(cleaned)
    return out


def add_correction(profile: dict, scene: str, wrong: str, correct: str):
    """向档案追加一条纠错记录。返回 (新档案, None) 或 (原档案, 错误信息)。

    纯函数：成功时返回带新记录的档案副本，不修改入参。
    """
    if not isinstance(profile, dict):
        return profile, "档案无效"
    scene = (scene or "").strip()
    wrong = (wrong or "").strip()
    correct = (correct or "").strip()
    if not (scene and wrong and correct):
        return profile, "场景、错误说法、正确说法均不能为空"
    if any(len(x) > MAX_CORRECTION_CHARS for x in (scene, wrong, correct)):
        return profile, f"单条纠错内容过长（上限 {MAX_CORRECTION_CHARS} 字）"
    cur = profile.get("corrections") or []
    if len(cur) >= MAX_CORRECTIONS:
        return profile, f"纠错记录已满（上限 {MAX_CORRECTIONS} 条），请先删除旧记录"
    new_profile = dict(profile)
    new_profile["corrections"] = list(cur) + [{"scene": scene, "wrong": wrong, "correct": correct}]
    return new_profile, None


def load_profile_file(path: str) -> dict | None:
    """读取单个档案文件。文件缺失/非法 JSON/校验失败时返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if validate_profile(data) is not None:
        return None
    return normalize_profile(data)


def list_profiles(styles_dir: str) -> list[dict]:
    """扫描 styles 目录下所有 *.json 档案，返回规范化后的档案列表。
    跳过无法解析的文件。结果按 name 排序。

    v2.8.1：os.listdir 包 try——目录被锁定/删除/移动时返回空列表
    （目录不可读当无档案，不抛，避免页面"风格读取失败"）。
    """
    profiles = []
    if not os.path.isdir(styles_dir):
        return profiles
    try:
        entries = sorted(os.listdir(styles_dir))
    except OSError:
        return profiles
    for fn in entries:
        if not fn.endswith(".json"):
            continue
        path = os.path.join(styles_dir, fn)
        p = load_profile_file(path)
        if p is not None:
            profiles.append(p)
    return profiles


def list_profile_names(styles_dir: str) -> list[str]:
    """返回 styles 目录下所有可用的档案名（按名称排序）。"""
    return [p["name"] for p in list_profiles(styles_dir)]


def find_profile(styles_dir: str, name: str) -> dict | None:
    """按 name 精确查找档案（区分大小写，再尝试忽略大小写）。"""
    for p in list_profiles(styles_dir):
        if p["name"] == name:
            return p
    for p in list_profiles(styles_dir):
        if p["name"].lower() == name.lower():
            return p
    return None


def save_profile_file(styles_dir: str, profile: dict) -> str:
    """保存档案到 styles 目录，返回保存的文件路径。
    文件名由 name 生成（非法文件名字符替换为 _）。"""
    name = profile.get("name", "unnamed")
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
    safe = safe or "unnamed"
    path = os.path.join(styles_dir, f"{safe}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return path
