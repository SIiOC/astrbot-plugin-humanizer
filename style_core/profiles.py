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
  "examples": ["几句示例"]
}

规则：全部为可选的字符串/字符串列表字段；缺字段的档案仍可用（渲染时跳过）。
不依赖 astrbot，便于单元测试。
"""

import json
import os

# 档案允许的顶层字段（其余字段保留但忽略，便于未来扩展）
ALLOWED_FIELDS = {
    "name", "description", "persona", "catchphrases",
    "sentence_patterns", "emotion_expressions", "avoid", "examples",
}
# 必须为字符串列表的字段
LIST_FIELDS = {
    "catchphrases", "sentence_patterns", "emotion_expressions", "avoid", "examples",
}

MIN_NAME_LEN = 1
MAX_NAME_LEN = 32


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
    return None


def normalize_profile(data: dict) -> dict:
    """规范化：剔除未知字段、补空列表、剥离空白条目。输入须已通过校验。"""
    out = {}
    for field in ALLOWED_FIELDS:
        val = data.get(field)
        if val is None:
            if field in LIST_FIELDS:
                out[field] = []
            else:
                out[field] = ""
            continue
        if field in LIST_FIELDS:
            out[field] = [str(x).strip() for x in val if str(x).strip()]
        else:
            out[field] = str(val).strip()
    return out


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
    跳过无法解析的文件。结果按 name 排序。"""
    profiles = []
    if not os.path.isdir(styles_dir):
        return profiles
    for fn in sorted(os.listdir(styles_dir)):
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
