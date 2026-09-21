# -*- coding: utf-8 -*-
"""
深度改写目标解析：决定 LLM 深度改写使用哪个 (provider_id, model)。

设计：
- rewrite_model 配置为空时，跟随当前会话使用的模型（行为与旧版一致）。
- 填写模型名时，优先在当前会话的 provider 上切换该模型（成本最低）；
  若当前 provider 不支持，则在所有已配置的 provider 中查找包含该模型的 provider；
  都找不到时回落当前会话模型，绝不报错中断。

本模块仅依赖 astrbot.api 的 logger（插件市场规范），context 采用鸭子类型
（具备 get_current_chat_provider_id / get_all_providers 即可），便于单元测试。
"""

from __future__ import annotations

from astrbot.api import logger


def provider_instance_id(p) -> str:
    """从任意 provider 实例取 id（chat/embedding/rerank 同一规则）。

    Provider 基类没有 get_provider_id()，需经 provider_config["id"] 或
    meta().id 取（见 astrbot/core/provider/provider.py）。
    v4.0 Phase 5 预备：main._chat_provider_id/_embedding_provider_id
    两处逐字重复实现的单一事实源。注意保留原语义细节：provider_config
    可读但 id 为空串时直接返回 ""（**不**回落 meta()），仅属性缺失/抛
    异常才走 meta 兜底。
    """
    try:
        return str(p.provider_config.get("id", "") or "")
    except Exception:  # noqa: BLE001
        pass
    try:
        return str(p.meta().id or "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def parse_configured_target(context, configured: str) -> tuple[str | None, str | None]:
    """解析辅助 LLM 的配置覆盖，返回 ``(provider_id, model)``。

    配置值兼容三种形态：空值表示不覆盖、裸模型名表示只覆盖模型，
    ``provider_id/model`` 表示覆盖提供商并尽量读取该实例的默认模型。
    未找到完整 provider 实例时保留旧行为：仅取斜杠后的模型名，交给
    调用方的默认 provider 继续执行。此函数只负责解析覆盖，不负责检查
    模型是否可用；深度改写的故障切换仍由 ``resolve_rewrite_target`` 负责。
    """
    value = str(configured or "").strip()
    if not value:
        return None, None
    if "/" not in value:
        return None, value

    try:
        provider = context.get_provider_by_id(value)
    except Exception:
        provider = None
    if provider is not None:
        try:
            model = provider.get_model() or None
        except Exception:
            model = None
        return value, model

    model = value.partition("/")[2] or value
    return None, model


async def provider_has_model(context, provider_id: str, model: str, model_cache: dict) -> bool:
    """指定 provider 的可用模型列表是否包含目标模型（结果缓存到 model_cache）。

    get_models() 对部分 provider 是网络请求，缓存可避免每条消息重复查询。
    v4.0.1：获取失败**不写缓存**——空列表一旦落缓存就永久命中"模型不存在"，
    provider 故障切换的可用性探测在重启前彻底失效（负缓存无 TTL 的坑）。
    失败返回 False 但下次重试；代价是坏 provider 期间每次调用多一次网络请求。
    """
    if provider_id in model_cache:
        return model in model_cache[provider_id]
    try:
        providers = context.get_all_providers()
        prov = next(
            (p for p in providers if p.meta().id == provider_id), None
        )
        if prov is None:
            return False
        models = list(await prov.get_models() or [])
    except Exception:
        return False
    model_cache[provider_id] = models
    return model in models


async def collect_models(context, model_cache: dict) -> list[tuple[str, str, list[str]]]:
    """收集所有已配置 provider 的可用模型列表。

    返回 [(provider_id, provider_type, [模型名, ...])]，结果缓存到 model_cache。
    单个 provider 获取失败时模型列表为空，不中断整体收集。
    v4.0.1：失败不写缓存（同 provider_has_model——防空列表永久缓存）。
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
                # 失败：本条按空列表展示（调用方只做展示），但不落缓存
                rows.append((pid, ptype, []))
                continue
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
                    logger.warning(
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
                    logger.warning(
                        f"[Humanizer] 提供商 {provider_hint!r} 不支持模型 {model_name!r}，"
                        "深度改写回落当前会话模型"
                    )
                    return current_pid, None
            logger.warning(
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
    logger.warning(
        f"[Humanizer] 未找到支持模型 {configured!r} 的提供商，深度改写回落当前会话模型"
    )
    return current_pid, None


def iter_failover_models(
    rows: list[tuple[str, str, list[str]]],
    preferred: tuple[str | None, str | None] = (None, None),
) -> list[tuple[str, str | None]]:
    """构造深度改写的候选模型序列（v2.6 的模型故障切换）。

    从 collect_models 的 [(provider_id, provider_type, [models])] 构造候选序列，
    供 _llm_rewrite 在"传输失败"时依次尝试下一个候选（内容校验失败不切换）。

    排序规则：
    - preferred（首选目标，来自 resolve_rewrite_target 的返回值）排第一：
      有模型名 → (provider_id, model_name)；无模型名 → (provider_id, None)（跟随默认）。
    - 其余 provider 按序补全，每个 provider 取其模型列表第一个（或 None 跟随默认，
      若该 provider 无可用模型列表）。
    - 去重（相同 (provider_id, model_name) 只保留一次），preferred 已在首位时不重复。

    返回 [(provider_id, model_name_or_None), ...]；无可选 provider 时返回空列表。
    """
    candidates: list[tuple[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()

    def _push(pid: str, model: str | None) -> None:
        key = (pid, model)
        if key not in seen:
            seen.add(key)
            candidates.append(key)

    pref_pid, pref_model = preferred
    if pref_pid:
        _push(pref_pid, pref_model)
    for pid, _ptype, models in rows:
        if pid == pref_pid:
            continue  # preferred 已入列
        if models:
            _push(pid, models[0])
        else:
            _push(pid, None)
    return candidates
