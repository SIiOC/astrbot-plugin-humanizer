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
