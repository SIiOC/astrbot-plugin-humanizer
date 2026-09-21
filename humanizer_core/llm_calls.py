# -*- coding: utf-8 -*-
"""Dependency-free async LLM invocation primitives.

The callable passed to :func:`invoke_llm` is duck-typed.  This module does
not import the host application or decide what call-site policy should apply
to failures.  ``None`` and non-positive timeouts intentionally mean no
``asyncio.wait_for`` wrapper; positive timeouts use ``asyncio.wait_for``.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

_T = TypeVar("_T")
LLMGenerate = Callable[..., Awaitable[_T]]


@dataclass(frozen=True)
class LLMTarget:
    """Provider and optional model selected for one LLM call."""

    provider_id: str
    model: str | None = None


def join_sections(base: str, *parts: str | None) -> str:
    """按「非空段落前置空行」规则拼接 prompt（v4.0 深度改写站点共用）。

    复刻内联语义逐字一致：base 恒定保留（**包括空串**——空 base + 非空
    part 仍产生 ``\\n\\n`` 前缀，这是改写 system 后缀拼进 SYSTEM_PROMPT 后
    的既有分隔行为，禁止"顺手清理"成 strip 版）；falsy 的 part（None/""）
    整个跳过，不产生多余空行。
    """
    out = base
    for part in parts:
        if part:
            out += f"\n\n{part}"
    return out


def _accepts_system_prompt(llm_generate: Callable[..., Any]) -> bool:
    """Best-effort signature check for a named ``system_prompt`` argument."""

    try:
        parameters = inspect.signature(llm_generate).parameters
    except (TypeError, ValueError):
        return False
    parameter = parameters.get("system_prompt")
    if parameter is not None and parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    ):
        return True
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _requires_chat_provider_id(llm_generate: Callable[..., Any]) -> bool:
    """Best-effort check: does the callable demand ``chat_provider_id``?

    AstrBot v4.28 makes ``chat_provider_id`` a **required** keyword-only
    argument on ``Context.llm_generate`` (``inspect.Parameter.empty`` default).
    Older callables either omitted the argument entirely or gave it a default,
    and direct ``provider.text_chat`` fallbacks never accept it.  When the
    parameter is required we must not silently drop the keyword (the host then
    raises a deep, hard-to-trace ``TypeError``); callers are told to resolve a
    real provider id instead.  A ``**kwargs`` tail cannot tell us a concrete
    requirement, so it is treated as "not required".
    """

    try:
        parameters = inspect.signature(llm_generate).parameters
    except (TypeError, ValueError):
        return False
    parameter = parameters.get("chat_provider_id")
    return (
        parameter is not None
        and parameter.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and parameter.default is inspect.Parameter.empty
    )


def _prepend_system_prompt(
    prompt: str, system_prompt: str, separator: str = "\n\n"
) -> str:
    """Carry a system instruction through an old callable without that kwarg.

    ``separator`` joins the two blocks; the deep-rewrite fallback passes its own
    separator (``\\n\\n待处理的文本：\\n``) so the labeled body matches the legacy
    inline string exactly rather than stacking an extra blank line.
    """

    if not system_prompt:
        return prompt
    if not prompt:
        return system_prompt
    return f"{system_prompt}{separator}{prompt}"


async def invoke_llm(
    llm_generate: LLMGenerate[_T],
    *,
    prompt: str,
    provider_id: str | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
    timeout: float | None = None,
    supports_system_prompt: bool | None = None,
    prompt_prefix: str | None = None,
) -> _T:
    """Invoke an asynchronous LLM callable with compatible keyword args.

    ``provider_id`` is sent as the host API's ``chat_provider_id`` keyword.
    When it is ``None`` the keyword is omitted entirely — this preserves the
    legacy call shape for providers that resolve the session provider
    themselves, and for direct ``provider.text_chat`` fallbacks that do not
    accept ``chat_provider_id`` at all (an unexpected keyword would leak into
    the request payload there).  **Exception**: when the callable marks
    ``chat_provider_id`` as required (AstrBot v4.28), omitting it is a bug — a
    :class:`ValueError` is raised here so the failure surfaces at the boundary
    with a clear message instead of a deep ``TypeError`` from the host.
    ``model`` and ``system_prompt`` are omitted when absent.  If a system
    prompt is supplied but unsupported by the callable, it is prepended to the
    user prompt instead of passing an unsupported keyword.

    ``prompt_prefix`` (optional) is emitted **only on that folding branch**: it
    reproduces legacy calls that labeled the user text under the folded system
    prompt (e.g. the deep-rewrite site's ``\\n\\n待处理的文本：\\n``).  It is
    ignored when the system prompt is passed as a real keyword, matching the old
    inline branch that only added the label in the fallback path.

    When capability is not supplied explicitly, ``inspect.signature``
    determines it.

    A positive timeout is enforced with :func:`asyncio.wait_for`.  A timeout,
    task cancellation, or exception from the callable is deliberately not
    caught, so the caller remains responsible for its failure policy.
    """

    kwargs: dict[str, Any] = {"prompt": prompt}
    if provider_id is not None:
        kwargs["chat_provider_id"] = provider_id
    elif _requires_chat_provider_id(llm_generate):
        raise ValueError(
            "invoke_llm: callable requires 'chat_provider_id' but provider_id "
            "is None; resolve a concrete provider id at the call site "
            "(AstrBot v4.28 made this keyword mandatory)."
        )
    if model is not None:
        kwargs["model"] = model

    if system_prompt is not None:
        supports = (
            supports_system_prompt
            if supports_system_prompt is not None
            else _accepts_system_prompt(llm_generate)
        )
        if supports:
            kwargs["system_prompt"] = system_prompt
        else:
            separator = prompt_prefix if prompt_prefix is not None else "\n\n"
            kwargs["prompt"] = _prepend_system_prompt(prompt, system_prompt, separator)

    awaitable = llm_generate(**kwargs)
    if timeout is not None and timeout > 0:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    return await awaitable


@dataclass(frozen=True)
class LLMCallSite:
    """Explicit defaults for a family of low-level LLM calls."""

    timeout: float | None = None
    supports_system_prompt: bool | None = None

    async def invoke(
        self,
        llm_generate: LLMGenerate[_T],
        *,
        prompt: str,
        provider_id: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        prompt_prefix: str | None = None,
    ) -> _T:
        """Delegate this call-site invocation to :func:`invoke_llm`."""

        return await invoke_llm(
            llm_generate,
            prompt=prompt,
            provider_id=provider_id,
            model=model,
            system_prompt=system_prompt,
            timeout=self.timeout,
            supports_system_prompt=self.supports_system_prompt,
            prompt_prefix=prompt_prefix,
        )

    async def call(
        self,
        llm_generate: LLMGenerate[_T],
        *,
        prompt: str,
        provider_id: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        prompt_prefix: str | None = None,
    ) -> _T:
        """Alias for :meth:`invoke` for call-site-oriented callers."""

        return await self.invoke(
            llm_generate,
            prompt=prompt,
            provider_id=provider_id,
            model=model,
            system_prompt=system_prompt,
            prompt_prefix=prompt_prefix,
        )


__all__ = ["LLMCallSite", "LLMTarget", "invoke_llm", "join_sections"]
