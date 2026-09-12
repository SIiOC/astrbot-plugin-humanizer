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

import itertools
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
    # ---- v3.8.0 时间行为规则（参考时笺 time_awareness TIME_GUIDE 的适用子集
    #      （MIT），按 Humanizer 的 time_context 注入形态改写，非照搬）----
    {
        "id": "builtin-time-no-fabricate",
        "name": "时间只依据注入",
        "type": "inject",
        "enabled": True,
        "content": "绝对时间只以当前时间上下文为准，不编造或推测日期时刻；对方没问就不报时。",
    },
    {
        "id": "builtin-time-colloquial",
        "name": "时间口语化",
        "type": "inject",
        "enabled": True,
        "content": "时间用口语说：「刚才」「大半夜」「好久没聊」，别「10点32分」「65小时没联系」这样报数。",
    },
    {
        "id": "builtin-gap-tone",
        "name": "间隔调语气",
        "type": "inject",
        "enabled": True,
        "content": "按聊天间隔调语气：很久没聊可自然流露想念或惊喜，刚聊过就保持连贯，别忽然生分。",
    },
    {
        "id": "builtin-calendar-natural",
        "name": "历法自然贴合",
        "type": "inject",
        "enabled": True,
        "content": "农历、节气、纪念日等历法信息自然贴合聊天，别照念日历；敏感日安静贴心。",
    },
    # ---- v3.9.0 补库（来源：petergyang/no-ai-slop 10+ AI 写作痕迹的对话向
    #      子集（MIT），中文场景机制级重写非照搬；QC 模式刻意保守——只收口语
    #      中罕见的高置信痕迹，宁可漏检也不误触发整轮改写）----
    {
        "id": "builtin-qc-sublimation",
        "name": "升华句命中检查",
        "type": "qc",
        "enabled": True,
        "content": "不用升华句式收尾（「这不仅是什么，更是什么」）。",
        "qc_pattern": "re:这(不仅|不只是)[^。！？]{0,20}(更是|也是)",
    },
    {
        "id": "builtin-qc-vague-source",
        "name": "模糊归因命中检查",
        "type": "qc",
        "enabled": True,
        "content": "不引用模糊来源（「研究表明」「专家表示」），像朋友说话不报参考文献。",
        "qc_pattern": "re:(研究|科学)(表明|显示)|专家(表示|指出)",
    },
    {
        "id": "builtin-qc-lecture-opener",
        "name": "说教开头命中检查",
        "type": "qc",
        "enabled": True,
        "content": "不用说教式开头（「记住：」「听好了」）。",
        "qc_pattern": "re:^(记住|请注意|听好了|你要知道)[，,：:]",
    },
    {
        "id": "builtin-qc-summary-opener",
        "name": "总结开头命中检查",
        "type": "qc",
        "enabled": True,
        "content": "闲聊不写总结段开头（「总之」「综上所述」）。",
        "qc_pattern": "re:^(总之|总的来说|总而言之|综上)[，,。！？]",
    },
    {
        "id": "builtin-no-essay-ending",
        "name": "禁作文式收尾",
        "type": "inject",
        "enabled": True,
        "content": "聊天不写作文收尾：不总结陈词、不展望升华，话说到就停，留白给对方接。",
    },
    {
        "id": "builtin-no-lecture-tone",
        "name": "禁说教语气",
        "type": "inject",
        "enabled": True,
        "content": "分享看法时像朋友闲聊，不像老师讲课：不列要点一二三、不「你应该」，点到为止。",
    },
    {
        "id": "builtin-no-parallelism",
        "name": "克制排比",
        "type": "inject",
        "enabled": True,
        "content": "克制工整排比与三连对仗（「既又还」式），真人打字随手，句子参差才自然。",
    },
    {
        "id": "builtin-no-dramatic-ending",
        "name": "禁戏剧化揭示收尾",
        "type": "inject",
        "enabled": True,
        "content": "不用戏剧化揭示收尾：不「重点是：」式冒号揭底，不单句断言耍帅，平静说完。",
    },
]


_ID_SEQ = itertools.count()


def _gen_id() -> str:
    """新规则 id：毫秒时间戳 + 进程内自增序号。

    v3.9.5 修复：原先只用秒级以上的毫秒时间戳，同一毫秒内的连续调用会生成
    完全相同的 id（批量导入、脚本化添加、快速连点必现）。而 toggle_rule /
    delete_rule / find_rule 都按 id 匹配，重复 id 会让一次操作同时命中多条
    规则——停用一条却停用一片，删除一条却删掉一片。
    """
    return "r-" + str(int(time.time() * 1000))[-9:] + "-" + str(next(_ID_SEQ))


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
