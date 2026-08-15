# -*- coding: utf-8 -*-
"""
深度改写目标解析：决定 LLM 深度改写使用哪个 (provider_id, model)。

设计：
- rewrite_model 配置为空时，跟随当前会话使用的模型（行为与旧版一致）。
- 填写模型名时，优先在当前会话的 provider 上切换该模型（成本最低）；
  若当前 provider 不支持，则在所有已配置的 provider 中查找包含该模型的 provider；
  都找不到时回落当前会话模型，绝不报错中断。

本模块不依赖 astrbot，context 采用鸭子类型（具备 get_current_chat_provider_id /
get_all_providers 即可），便于单元测试。
"""

from __future__ import annotations

import logging

_logger = logging.getLogger("astrbot")


async def provider_has_model(context, provider_id: str, model: str, model_cache: dict) -> bool:
    """指定 provider 的可用模型列表是否包含目标模型（结果缓存到 model_cache）。

    get_models() 对部分 provider 是网络请求，缓存可避免每条消息重复查询。
    """
    if provider_id in model_cache:
        return model in model_cache[provider_id]
    models: list[str] = []
    try:
        providers = context.get_all_providers()
        prov = next(
            (p for p in providers if p.meta().id == provider_id), None
        )
        if prov is not None:
            models = list(await prov.get_models() or [])
    except Exception:
        models = []
    model_cache[provider_id] = models
    return model in models


async def collect_models(context, model_cache: dict) -> list[tuple[str, str, list[str]]]:
    """收集所有已配置 provider 的可用模型列表。

    返回 [(provider_id, provider_type, [模型名, ...])]，结果缓存到 model_cache。
    单个 provider 获取失败时模型列表为空，不中断整体收集。
    """
    try:
        providers = context.get_all_providers()
    except Exception:
        providers = []
    rows: list[tuple[str, str, list[str]]] = []
    for prov in providers:
        try:
            pid = prov.meta().id
            ptype = getattr(prov.meta(), "type", "")
        except Exception:
            continue
        if pid not in model_cache:
            try:
                models = list(await prov.get_models() or [])
            except Exception:
                models = []
            model_cache[pid] = models
        rows.append((pid, ptype, model_cache[pid]))
    return rows


async def resolve_rewrite_target(
    context, umo: str, configured: str, model_cache: dict
) -> tuple[str | None, str | None]:
    """解析深度改写目标，返回 (provider_id, model_name)。

    返回的 model_name 为 None 时表示跟随 provider 当前使用的模型（不传 model 参数）。
    provider_id 为 None 表示没有可用的提供商，调用方应跳过 LLM 改写。

    configured 支持两种格式：
    - 纯模型名（如 "deepseek-chat"）：按模型名在提供商中查找。
    - "提供商/模型"（如 "xiaomi-token-plan/mimo-v2.5-pro"）：先定位指定提供商，
      再在该提供商内使用该模型；提供商不存在时回落当前会话模型。
    """
    # 当前会话的 provider id
    try:
        current_pid = await context.get_current_chat_provider_id(umo=umo)
    except Exception:
        current_pid = None

    if not configured:
        # 未配置指定模型：跟随当前会话
        return current_pid, None
    if not current_pid:
        # 当前会话没有可用 provider，无法改写
        return None, None

    # 支持 "提供商/模型" 格式：configured 可能来自配置弹窗的 select_provider 选择器，
    # 其值为 provider 实例 id（真实格式如 "xiaomi-token-plan/mimo-v2.5-pro"）。
    # 先精确匹配完整实例 id，再按前缀匹配提供商，最后校验模型在该提供商内可用。
    if "/" in configured:
        provider_hint, _, model_name = configured.partition("/")
        provider_hint = provider_hint.strip()
        model_name = model_name.strip()
        if provider_hint and model_name:
            try:
                providers = context.get_all_providers()
            except Exception:
                providers = []
            # 1) 精确匹配：某 provider 实例 id 就等于整个 configured（type/model 复合 id）
            for prov in providers:
                try:
                    pid = prov.meta().id
                except Exception:
                    continue
                if pid == configured:
                    if await provider_has_model(context, pid, model_name, model_cache):
                        return pid, model_name
                    _logger.warning(
                        f"[Humanizer] 提供商 {provider_hint!r} 不支持模型 {model_name!r}，"
                        "深度改写回落当前会话模型"
                    )
                    return current_pid, None
            # 2) 前缀匹配：provider 实例 id 以 "hint/" 开头（如多个 mimo 实例）
            for prov in providers:
                try:
                    pid = prov.meta().id
                except Exception:
                    continue
                if pid == provider_hint or pid.startswith(provider_hint + "/"):
                    if await provider_has_model(context, pid, model_name, model_cache):
                        return pid, model_name
                    _logger.warning(
                        f"[Humanizer] 提供商 {provider_hint!r} 不支持模型 {model_name!r}，"
                        "深度改写回落当前会话模型"
                    )
                    return current_pid, None
            _logger.warning(
                f"[Humanizer] 未找到提供商 {provider_hint!r}，深度改写回落当前会话模型"
            )
            return current_pid, None

    # 优先在当前 provider 内切换模型（同 provider 切换成本最低）
    if await provider_has_model(context, current_pid, configured, model_cache):
        return current_pid, configured

    # 遍历所有 provider 查找包含该模型的
    try:
        providers = context.get_all_providers()
    except Exception:
        providers = []
    for prov in providers:
        try:
            pid = prov.meta().id
        except Exception:
            continue
        if pid == current_pid:
            continue
        if await provider_has_model(context, pid, configured, model_cache):
            return pid, configured

    # 找不到：回落当前会话模型
    _logger.warning(
        f"[Humanizer] 未找到支持模型 {configured!r} 的提供商，深度改写回落当前会话模型"
    )
    return current_pid, None
