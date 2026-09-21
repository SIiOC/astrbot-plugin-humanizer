# -*- coding: utf-8 -*-
"""
配置结构迁移：扁平结构 → humanize/proactive 两个分组。

v1.3.0 之前 _conf_schema.json 是扁平结构（enabled、enable_llm_rewrite、rewrite_model ...
全部在顶层）。v1.3.0 之后改为两个平级 object 分组：
- "humanize"：润色设置
- "proactive"：主动聊天

AstrBot 的 AstrBotConfig 用新 schema 生成嵌套默认配置后，会把已保存的扁平配置
合并到顶层（self.update(conf)），因此会出现"顶层既有 humanize/proactive 分组
（默认值），又有旧的扁平键（用户设置）"的混合状态。本模块负责把旧扁平键的
用户设置迁移进对应分组，并删除旧扁平键，最后保存。

纯函数、不依赖 astrbot，便于单元测试。
"""

from __future__ import annotations

# 旧版扁平结构的所有顶层键
_OLD_TOP_KEYS = (
    "enabled",
    "enable_llm_rewrite",
    "rewrite_model",
    "remove_emoji",
    "remove_reasoning",
    "min_length",
    "max_chars",
    "debug",
    "enable_proactive",
    "idle_after_minutes",
    "idle_fluctuation_minutes",
    "proactive_quiet_hours",
    "proactive_prompt",
)

# 各分组包含的键
_HUMANIZE_KEYS = (
    "enabled",
    "enable_llm_rewrite",
    "rewrite_model",
    "remove_emoji",
    "remove_reasoning",
    "min_length",
    "max_chars",
    "debug",
)
_PROACTIVE_KEYS = (
    "enable_proactive",
    "idle_after_minutes",
    "idle_fluctuation_minutes",
    "proactive_quiet_hours",
    "proactive_prompt",
)

# v2.0.0：主动聊天键名差异化（与同生态插件错开命名）。旧键 → 新键，
# 迁移函数只搬旧键值，新键在 schema 有默认值，不会覆盖用户其他设置。
_PROACTIVE_KEY_RENAMES = {
    "idle_after_minutes": "silence_after_minutes",
    "idle_fluctuation_minutes": "silence_fluctuation_minutes",
}


def migrate_flat_to_groups(config: dict) -> bool:
    """把扁平结构的配置迁移为 humanize/proactive 分组。

    就地修改 config；返回是否发生了迁移。已是新结构或无需迁移时返回 False。
    用户设置（旧扁平键的值）会被保留并覆盖进对应分组，绝不丢失。
    """
    # 存在旧扁平键才需要迁移
    old_present = [k for k in _OLD_TOP_KEYS if k in config]
    if not old_present:
        return False

    # 确保分组存在（schema 默认可能已生成，也可能没有）
    humanize = config.setdefault("humanize", {})
    proactive = config.setdefault("proactive", {})

    # 旧扁平值覆盖进分组（保留用户设置）
    for k in _HUMANIZE_KEYS:
        if k in config:
            humanize[k] = config[k]
    for k in _PROACTIVE_KEYS:
        if k in config:
            proactive[k] = config[k]

    # 删除旧扁平键
    for k in _OLD_TOP_KEYS:
        config.pop(k, None)

    return True


def migrate_proactive_key_names(config: dict) -> bool:
    """把主动聊天旧键名迁移为新键名（idle_* → silence_*）。

    顶层与 proactive 分组内的旧键都会被检查：有值且新键不存在时，
    值搬入新键并删除旧键。就地修改 config；返回是否发生了迁移。
    """
    changed = False
    group = config.get("proactive") if isinstance(config, dict) else None
    for source in (config, group if isinstance(group, dict) else None):
        if not isinstance(source, dict):
            continue
        for old, new in _PROACTIVE_KEY_RENAMES.items():
            if old in source and new not in source:
                source[new] = source[old]
                source.pop(old, None)
                changed = True
    return changed


# ---------------------------------------------------------------------------
# v3.8.1 引入、v3.9.0 随版发布的分组重构迁移：语义分区合并（life→time、debounce/send_discipline→typing、
# humaneness→style、commitments→proactive）。旧组键有用户值且新键不存在时搬入，
# 迁移后删除旧组。debug 类键不做数值搬迁，仅按 OR 语义并入目标组调试开关。
# ---------------------------------------------------------------------------

# (源组, 源键) -> (目标组, 目标键)；源值非缺失即搬（目标已有值不覆盖）
_GROUP_MERGE_MOVES = {
    ("humaneness", "rules_enable"): ("style", "rules_enable"),
    ("humaneness", "qc_enable"): ("style", "qc_enable"),
    ("life", "enable_life"): ("time", "enable_life"),
    ("life", "enable_llm_timeline"): ("time", "enable_llm_timeline"),
    ("life", "extract_model"): ("time", "life_extract_model"),
    ("life", "prompt_template"): ("time", "prompt_template"),
    ("life", "schedule"): ("time", "schedule"),
    ("life", "fallback_doing"): ("time", "fallback_doing"),
    ("life", "day_note"): ("time", "day_note"),
    ("life", "mood_enabled"): ("time", "mood_enabled"),
    ("life", "mood_pool"): ("time", "mood_pool"),
    ("debounce", "enable"): ("typing", "debounce_enable"),
    ("debounce", "debounce_time"): ("typing", "debounce_time"),
    ("debounce", "enable_adaptive_debounce"): ("typing", "enable_adaptive_debounce"),
    ("debounce", "adaptive_min_wait"): ("typing", "adaptive_min_wait"),
    ("debounce", "adaptive_max_wait"): ("typing", "adaptive_max_wait"),
    ("debounce", "adaptive_max_total_wait"): ("typing", "adaptive_max_total_wait"),
    ("debounce", "adaptive_short_message_threshold"): ("typing", "adaptive_short_message_threshold"),
    ("debounce", "max_session_wait"): ("typing", "max_session_wait"),
    ("debounce", "command_prefixes"): ("typing", "command_prefixes"),
    ("debounce", "merge_separator"): ("typing", "merge_separator"),
    ("debounce", "enable_recall_filter"): ("typing", "enable_recall_filter"),
    ("debounce", "enable_typing_detection"): ("typing", "enable_typing_detection"),
    ("debounce", "max_typing_wait"): ("typing", "max_typing_wait"),
    ("send_discipline", "enabled"): ("typing", "send_discipline_enabled"),
    ("send_discipline", "debug"): ("typing", "send_discipline_debug"),
    ("commitments", "enable"): ("proactive", "commitments_enable"),
    ("commitments", "track_groups"): ("proactive", "commitments_track_groups"),
    ("commitments", "llm_confirm"): ("proactive", "llm_confirm"),
    ("commitments", "inject_in_chat"): ("proactive", "inject_in_chat"),
    ("commitments", "remind_grace_days"): ("proactive", "remind_grace_days"),
    ("commitments", "extract_model"): ("proactive", "commitments_extract_model"),
    ("commitments", "extract_timeout"): ("proactive", "commitments_extract_timeout"),
    ("commitments", "debug"): ("proactive", "commitments_debug"),
}

# OR 合并：源真值且目标为假值时，目标继承真值（调试开关语义）
_GROUP_MERGE_OR = [
    ("humaneness", "debug", "style", "debug"),
    ("life", "debug", "time", "debug"),
]

# 迁移完成后应消失的源组
_GROUP_MERGE_SOURCES = ("humaneness", "life", "debounce", "send_discipline", "commitments")

# 源组 -> 目标组（v3.9.5：搬运显式清单之外的剩余键用，防用户数据丢失）
_GROUP_MERGE_TARGETS = {
    "humaneness": "style",
    "life": "time",
    "debounce": "typing",
    "send_discipline": "typing",
    "commitments": "proactive",
}


def migrate_group_merges(config: dict) -> bool:
    """v3.8.1 编写、v3.9.0 发布的分组重构：把被合并组的用户设置搬入新组，删除旧组。

    就地修改 config；返回是否发生了迁移。规则：
    - 搬移仅在「源键存在且目标键不存在」时执行（不覆盖用户新设置）；
    - debug 类开关按 OR 语义并入目标组调试键；
    - 显式清单之外的剩余键按源组→目标组兜底搬运（v3.9.5，防静默丢数据）；
    - 全部搬移完成后删除空/已迁移的源组。
    """
    if not isinstance(config, dict):
        return False
    changed = False

    def _grp(name):
        g = config.get(name)
        return g if isinstance(g, dict) else None

    for (sg, sk), (dg, dk) in _GROUP_MERGE_MOVES.items():
        src, dst = _grp(sg), _grp(dg)
        if src is None or sk not in src:
            continue
        if dst is None:
            dst = config[dg] = {}
        if dk not in dst:
            dst[dk] = src[sk]
            changed = True

    for sg, sk, dg, dk in _GROUP_MERGE_OR:
        src, dst = _grp(sg), _grp(dg)
        if src is None or sk not in src:
            continue
        if dst is None:
            dst = config[dg] = {}
        if not dst.get(dk) and src.get(sk):
            dst[dk] = src[sk]
            changed = True

    # v3.9.5 修复：显式清单之外的剩余键原先随源组一起被删除——用户若在旧组里
    # 留下未被列出的键（手改、未来键、历史残留），迁移即静默丢数据。此处按
    # 源组→目标组兜底搬运，目标组已有同名键时不覆盖（用户新设置优先）。
    # v4.0.1：已按显式规则搬/并过的**源键**不再兜底搬运——改名搬移
    # （如 extract_model→commitments_extract_model）会把旧名键原样抄进
    # 目标组，造成同义键在新旧两个名字下并存，被完整性检查永久留存。
    moved_source_keys = {
        (sg, sk) for (sg, sk) in _GROUP_MERGE_MOVES
    } | {
        (sg, sk) for sg, sk, _dg, _dk in _GROUP_MERGE_OR
    }
    for sg, dg in _GROUP_MERGE_TARGETS.items():
        src = _grp(sg)
        if not src:
            continue
        dst = _grp(dg)
        if dst is None:
            dst = config[dg] = {}
        for sk, sv in list(src.items()):
            if (sg, sk) in moved_source_keys:
                continue
            if sk not in dst:
                dst[sk] = sv
                changed = True

    for sg in _GROUP_MERGE_SOURCES:
        if sg in config:
            config.pop(sg, None)
            changed = True
    return changed
