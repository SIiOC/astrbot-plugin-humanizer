# -*- coding: utf-8 -*-
"""真人感规则集（v3.5.2，纯函数 + 轻存储、零 astrbot 依赖）。

用户可见可调的对话规则库（humaneness_rules.json），与既有三层
（rules_zh/en 机械去痕、风格档案 decision_rules、改写链指南）并存：

- inject 注入型：渲染成指令段进 system_prompt（生成前约束）
- qc 质检型：对生成后的回复做关键词/正则命中检查，命中触发一次
  针对性改写（不循环、不吞消息）

匹配语义（对普通用户零门槛）：默认把 pattern 按「，/,/|」拆成关键词做
子串匹配（与安抚词池同一逻辑）；以 "re:" 前缀开头才按正则解析（高级）。

存储范式照 PersonaStateStore：{"version": 1, "rules": [...]}，原子写，
损坏按空表处理。
"""

from __future__ import annotations

import re
import time
from functools import lru_cache
from typing import Any, Iterable, Optional

from .state import _atomic_write_json

RULES_VERSION = 1
RULE_TYPES = ("inject", "qc")

# 渲染封顶：注入段最多条数 / 单条内容最大长度（防 prompt 膨胀）
INJECT_MAX_RULES = 20
INJECT_MAX_CONTENT = 60

_REGEX_PREFIX = "re:"

# 内置预置规则（builtin=True 不可删除、只能停用；首次启动幂等落盘）
BUILTIN_RULES: list[dict] = [
    {
        "id": "builtin-time-aware",
        "name": "时间感知检查",
        "type": "inject",
        "enabled": True,
        "content": "回复必须与当前时间上下文一致：深夜不安排白天的事，不忽略刚过去的长时间沉默；时间信息只在自然需要时提及。",
    },
    {
        "id": "builtin-interjection-cap",
        "name": "语气词限额",
        "type": "inject",
        "enabled": True,
        "content": "“噗”“哈哈”这类语气词大约每10句最多出现1次，绝不连用。",
    },
    {
        "id": "builtin-no-oath",
        "name": "禁宣誓句",
        "type": "qc",
        "enabled": True,
        "content": "不用宣誓式表达，像普通人说话，不需要赌咒自证。",
        "qc_pattern": "我发誓，真的没骗你，千真万确，不骗你，我对天",
    },
    {
        "id": "builtin-length-mirror",
        "name": "长度镜像",
        "type": "inject",
        "enabled": True,
        "content": "回复长度尽量镜像对方：对方一句你一句，对方长段你才展开，别对短消息回大段。",
    },
    {
        "id": "builtin-no-stage-direction",
        "name": "禁表演感描写",
        "type": "inject",
        "enabled": True,
        "content": "不写（微笑）（看向窗外）*动作* 这类表演感舞台指示，只输出要说的话。",
    },
    # ---- v3.6.0 补库（来源：blader/humanizer 35 条 AI 写作痕迹的聊天向子集，
    #      #20 客服腔收尾 / #21 免责开头 / #22 过度附和；机制级重写非照搬）----
    {
        "id": "builtin-no-forced-question",
        "name": "禁强行提问收尾",
        "type": "inject",
        "enabled": True,
        "content": "别每条回复都用问句收尾；真人聊天经常只说自己的事，不一定反问对方。",
    },
    {
        "id": "builtin-no-support-tone",
        "name": "禁客服腔收尾",
        "type": "inject",
        "enabled": True,
        "content": "不用客服式说话：不说「希望这有帮助」「有问题随时问我」这类收尾，像朋友一样自然结束。",
    },
    {
        "id": "builtin-no-flattery",
        "name": "禁过度附和",
        "type": "inject",
        "enabled": True,
        "content": "不过度附和：不说「你说得太对了」「好问题」这类讨好开场，同意就自然接话，有不同看法就说出来。",
    },
    {
        "id": "builtin-qc-support-tone",
        "name": "客服腔命中检查",
        "type": "qc",
        "enabled": True,
        "content": "不用客服式收尾（「希望这有帮助」「有问题随时找我」）。",
        "qc_pattern": "re:希望(这|以上|这些)?(对你|给你们)?(有所|有|所)?帮助|如果还有任何问题|有问题(随时|可以随时)(问|找|联系)我",
    },
    {
        "id": "builtin-qc-flattery",
        "name": "过度附和命中检查",
        "type": "qc",
        "enabled": True,
        "content": "不用讨好式开场（「你说得太对了」「好问题」）。",
        "qc_pattern": "re:^你说得太对(了)?|^好问题[!!！。]|^问得(好|不错)[!!！。]",
    },
]


def _gen_id() -> str:
    return "r-" + str(int(time.time() * 1000))[-9:]


def normalize_rule(raw: Any) -> Optional[dict]:
    """清洗单条规则；非法返回 None（load 与 add 共用）。"""
    if not isinstance(raw, dict):
        return None
    rid = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    rtype = str(raw.get("type") or "").strip()
    content = str(raw.get("content") or "").strip()
    if not rid or not name or rtype not in RULE_TYPES or not content:
        return None
    out: dict = {
        "id": rid,
        "name": name,
        "type": rtype,
        "enabled": bool(raw.get("enabled", True)),
        "builtin": bool(raw.get("builtin", False)),
        "content": content,
    }
    if rtype == "qc":
        pat = str(raw.get("qc_pattern") or "").strip()
        out["qc_pattern"] = pat if pat else content
    return out


def load_rules(path) -> list[dict]:
    """读规则库；文件缺失/损坏/结构非法一律按空表（调用方迁移预置后落盘）。"""
    import json
    from pathlib import Path

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    items = raw.get("rules") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        r = normalize_rule(it)
        if r is not None:
            out.append(r)
    return out


def save_rules(path, rules: Iterable[dict]) -> None:
    from pathlib import Path

    _atomic_write_json(Path(path), {"version": RULES_VERSION, "rules": list(rules)})


def migrate_builtins(rules: list[dict]) -> tuple[list[dict], int]:
    """把内置预置规则补进库（按 id 幂等），保留既有条目的 enabled 状态。"""
    have = {r["id"] for r in rules}
    added = 0
    out = list(rules)
    for b in BUILTIN_RULES:
        if b["id"] not in have:
            out.append({**b, "builtin": True})
            added += 1
    return out, added


def find_rule(rules: list[dict], key: str) -> tuple[Optional[dict], str]:
    """按 1 起始序号 / id / 名字查规则。返回 (规则或 None, 错误说明)。"""
    k = str(key or "").strip()
    if not k:
        return None, "缺少规则序号或名字"
    if k.isdigit():
        idx = int(k)
        if 1 <= idx <= len(rules):
            return rules[idx - 1], ""
        return None, f"序号超范围（1~{len(rules)}）"
    for r in rules:
        if r["id"] == k or r["name"] == k:
            return r, ""
    return None, f"找不到规则 {k!r}"


def add_rule(
    rules: list[dict], name: str, rtype: str, content: str, qc_pattern: str = ""
) -> tuple[list[dict], str]:
    """新增用户规则。返回 (新列表, 错误说明)；错误说明为空串表示成功。"""
    name = str(name or "").strip()
    rtype = str(rtype or "").strip().lower()
    content = str(content or "").strip()
    if not name:
        return rules, "规则名不能为空"
    if rtype not in RULE_TYPES:
        return rules, "类型必须是 inject 或 qc"
    if not content:
        return rules, "规则内容不能为空"
    if any(r["name"] == name for r in rules):
        return rules, f"已存在同名规则 {name!r}"
    entry = {
        "id": _gen_id(),
        "name": name,
        "type": rtype,
        "enabled": True,
        "builtin": False,
        "content": content,
    }
    if rtype == "qc":
        pat = str(qc_pattern or "").strip()
        entry["qc_pattern"] = pat if pat else content
    return rules + [entry], ""


def delete_rule(rules: list[dict], key: str) -> tuple[list[dict], str]:
    r, err = find_rule(rules, key)
    if err:
        return rules, err
    if r.get("builtin"):
        return rules, "内置规则不可删除，可用 /rules_off 停用"
    return [x for x in rules if x["id"] != r["id"]], ""


def toggle_rule(rules: list[dict], key: str, enabled: bool) -> tuple[list[dict], str]:
    r, err = find_rule(rules, key)
    if err:
        return rules, err
    out = []
    for x in rules:
        if x["id"] == r["id"]:
            x = dict(x)
            x["enabled"] = bool(enabled)
        out.append(x)
    return out, ""


# ---- QC 匹配 ----

@lru_cache(maxsize=256)
def _compiled_regex(pattern: str):
    return re.compile(pattern)


def _qc_violation(text: str, rule: dict) -> bool:
    """单条 qc 规则是否命中。pattern 以 re: 开头按正则，否则按关键词拆分。"""
    if not isinstance(text, str) or not text.strip():
        return False
    pat = str(rule.get("qc_pattern") or rule.get("content") or "").strip()
    if not pat:
        return False
    if pat.startswith(_REGEX_PREFIX):
        expr = pat[len(_REGEX_PREFIX):].strip()
        if not expr:
            return False
        try:
            return bool(_compiled_regex(expr).search(text))
        except re.error:
            return False
    keywords = [w for w in pat.replace("，", ",").replace("|", ",").split(",") if w.strip()]
    return any(w.strip() in text for w in keywords)


def qc_violations(text: str, rules: Iterable[dict]) -> list[dict]:
    """返回命中的 qc 规则列表（仅 enabled）。"""
    if not isinstance(text, str) or not text.strip():
        return []
    return [
        r
        for r in rules
        if r.get("type") == "qc" and r.get("enabled") and _qc_violation(text, r)
    ]


# ---- 渲染 ----

def _clip(s: str, limit: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def render_inject_section(rules: Iterable[dict]) -> str:
    """渲染注入型规则段；无可用规则返回空串（不占 token）。

    封顶：最多 INJECT_MAX_RULES 条、单条内容截 INJECT_MAX_CONTENT 字。
    """
    items = [
        r
        for r in rules
        if r.get("type") == "inject" and r.get("enabled")
    ]
    if not items:
        return ""
    lines = ["【真人感规则】以下是你的说话习惯约束，每条都要遵守："]
    for r in items[:INJECT_MAX_RULES]:
        lines.append(f"- {_clip(r['content'], INJECT_MAX_CONTENT)}")
    if len(items) > INJECT_MAX_RULES:
        lines.append(f"（另有 {len(items) - INJECT_MAX_RULES} 条规则未载入）")
    return "\n".join(lines)


def render_qc_instruction(violated: list[dict]) -> str:
    """QC 命中后给改写模型的针对性指令（短，省 token）。"""
    if not violated:
        return ""
    lines = ["【必须去除的内容】原文出现了以下违规表达，改写时务必去掉或换自然的说法："]
    for r in violated[:5]:
        name = str(r.get("name") or "").strip()
        body = _clip(str(r.get("content") or ""), 50)
        lines.append(f"- {name}：{body}" if name else f"- {body}")
    return "\n".join(lines)


__all__ = [
    "BUILTIN_RULES",
    "INJECT_MAX_CONTENT",
    "INJECT_MAX_RULES",
    "RULE_TYPES",
    "RULES_VERSION",
    "add_rule",
    "delete_rule",
    "find_rule",
    "load_rules",
    "migrate_builtins",
    "normalize_rule",
    "qc_violations",
    "render_inject_section",
    "render_qc_instruction",
    "save_rules",
    "toggle_rule",
]
