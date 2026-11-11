# -*- coding: utf-8 -*-
"""提示词注入管线（v4.8.0：把手写顺序收敛成声明式注册表）。

设计约定：
- 每个 injector 只声明「顺序 + 记录键 + 落点 + 依赖」，具体取文本由 main 的
  ``_produce_*`` 方法负责，纯数据模块不依赖 astrbot；
- 顺序即本表顺序（priority 仅用于校验/展示，运行时按表顺序执行）；
- ``depends_on`` 表示前序注入器没有产出时跳过（例如风格未启用时跳过检索示例）；
- ``placement`` 决定文本落在 system_prompt 还是请求尾部（extra_user_content_parts）。

v4.8.0 之前这些顺序散落在 ``on_llm_request`` 的注释和代码位置里；收敛后
控制台可以只读展示「本轮各注入器是否生效、各占多少字符」。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InjectorSpec:
    """一个提示词注入器的声明。"""

    name: str
    label: str
    priority: int
    record_key: str
    handler: str
    placement: str  # system | extra_tail | extra_tail_or_system
    depends_on: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "priority": self.priority,
            "placement": self.placement,
            "depends_on": list(self.depends_on),
        }


# 顺序即执行顺序：成长档案 → 时间 → 成长处境 → 发送纪律 → 情绪 → 规则 →
# 语言趋同 → 风格 → 检索示例。后两项在 style.enabled 关闭时由各自 handler
# 返回空串；time 之后各项保持「独立于风格开关」的既有语义。
INJECTORS: tuple[InjectorSpec, ...] = (
    InjectorSpec(
        name="growth", label="成长档案", priority=5,
        record_key="growth", handler="_produce_growth_text", placement="system",
    ),
    InjectorSpec(
        name="time",
        label="时间上下文",
        priority=10,
        record_key="time",
        handler="_produce_time_text",
        placement="extra_tail",
    ),
    InjectorSpec(
        name="growth_state", label="成长处境", priority=15,
        record_key="growth_state", handler="_produce_growth_state_text",
        placement="extra_tail", depends_on=("growth",),
    ),
    InjectorSpec(
        name="discipline",
        label="发送纪律",
        priority=20,
        record_key="discipline",
        handler="_produce_discipline_text",
        placement="system",
    ),
    InjectorSpec(
        name="emotion",
        label="情绪惯性",
        priority=30,
        record_key="emotion",
        handler="_produce_emotion_text",
        placement="system",
    ),
    InjectorSpec(
        name="rules",
        label="真人感规则",
        priority=40,
        record_key="rules",
        handler="_produce_rules_text",
        placement="extra_tail_or_system",
    ),
    InjectorSpec(
        name="lang",
        label="语言趋同",
        priority=50,
        record_key="lang",
        handler="_produce_lang_text",
        placement="system",
    ),
    InjectorSpec(
        name="style",
        label="说话风格",
        priority=60,
        record_key="style",
        handler="_produce_style_text",
        placement="system",
    ),
    InjectorSpec(
        name="examples",
        label="检索示例",
        priority=70,
        record_key="examples",
        handler="_produce_examples_text",
        placement="system",
        depends_on=("style",),
    ),
)

INJECTOR_NAMES: tuple[str, ...] = tuple(spec.name for spec in INJECTORS)
INJECTOR_BY_NAME: dict[str, InjectorSpec] = {spec.name: spec for spec in INJECTORS}


def injector_specs() -> list[dict]:
    """只读展示用清单（控制台/测试共用）。"""
    return [spec.as_dict() for spec in INJECTORS]


__all__ = [
    "INJECTOR_BY_NAME",
    "INJECTOR_NAMES",
    "INJECTORS",
    "InjectorSpec",
    "injector_specs",
]
