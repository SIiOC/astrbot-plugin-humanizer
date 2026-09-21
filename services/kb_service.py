"""Dependency-injected knowledge-base orchestration.

This module deliberately knows nothing about AstrBot.  ``KBService`` talks to a
small set of duck-typed ports so it can be used by a transitional adapter and
unit-tested with ordinary fakes.

Port contract
-------------
``config_getter(key, default)`` returns a configuration value.  The only
configuration keys read by the service are ``create_kb`` and
``rerank_provider_id``; an omitted getter uses the defaults shown below.
``effective_corpus_rows()`` returns an iterable of dictionaries.  Rows with a
truthy, non-whitespace ``content`` are uploaded; ``source`` is used only for
``builtin``/``user`` grouping.  ``embedding_provider_resolver()`` returns a
provider id, or an empty value when the provider is not available.

``kb_manager`` is either supplied directly or found at ``context.kb_manager``.
It is expected to provide async ``get_kb_by_name``, ``create_kb`` and (when
needed) ``update_kb`` methods.  A KB object provides async
``upload_document``/``delete_document`` and optionally
``list_documents``/``count_documents``.  A supplied ``list_all_documents(kb)``
callback may replace the default paginated implementation.  Exceptions from
manager/document operations are treated like the current implementation:
configuration/update failures are logged and synchronization falls back to
upload; upload failures leave the KB false-ready; enumeration failures fall
back to upload.

``fingerprint_calculator(rows, embedding_id)`` returns the current index
fingerprint or ``None`` for an empty corpus.  If omitted, the existing pure
``humanizer_core.kb_state`` signature/fingerprint functions are used.
``persist_index_state(state)`` receives the complete mutable state mapping and
is called after a marker is claimed or an upload succeeds.  Exceptions from
this callback are swallowed after the in-memory state has been updated.
``kb_name(style_name)`` and ``kb_description(style_name, rows)`` are optional
formatters.  ``create_task(coro)`` and ``task_registry.track(task, name)`` are
optional; without the former ``asyncio.create_task`` is used.  ``retrieve_cache``
is optional and is cleared when the index is invalidated.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Optional


_MISSING = object()


@dataclass
class KBPorts:
    """External operations used by :class:`KBService`.

    All callbacks are intentionally structural rather than protocol classes.
    The aliases ``fingerprint`` and ``persist_state`` are accepted for callers
    that prefer shorter names; the more descriptive fields are canonical.
    """

    config_getter: Optional[Callable[..., Any]] = None
    effective_corpus_rows: Optional[Callable[[], Iterable[dict]]] = None
    kb_name: Optional[Callable[[str], str]] = None
    kb_description: Optional[Callable[[str, list[dict]], str]] = None
    embedding_provider_resolver: Optional[Callable[[], Any]] = None
    fingerprint_calculator: Optional[Callable[..., Optional[str]]] = None
    persist_index_state: Optional[Callable[[dict], Any]] = None
    context: Any = None
    kb_manager: Any = None
    list_all_documents: Optional[Callable[[Any], Awaitable[list]]] = None
    retrieval_formatter: Optional[Callable[..., Awaitable[str]]] = None
    task_registry: Any = None
    create_task: Optional[Callable[[Awaitable[Any]], Any]] = None
    retrieve_cache: Any = None
    corpus_hint: Optional[Callable[[], Any]] = None
    configured_rerank: Optional[Callable[[], Any]] = None
    logger: Any = None
    upload_group_size: int = 200
    upload_batch_size: int = 16
    fingerprint: Optional[Callable[..., Optional[str]]] = None
    persist_state: Optional[Callable[[dict], Any]] = None
    # Transitional injection: when the host already loaded persisted state,
    # reuse that exact dict instead of assigning over the host attribute after
    # its initialization hook (the v3.9.5 ordering contract).
    initial_index_state: Optional[dict[str, dict]] = None
    initial_ready: Optional[dict[str, bool]] = None
    initial_syncing: Optional[set[str]] = None
    initial_rerank_applied: Optional[dict[str, Optional[str]]] = None
    initial_generations: Optional[dict[str, int]] = None
    initial_tasks: Optional[set[Any]] = None

    def __post_init__(self) -> None:
        if self.fingerprint_calculator is None and self.fingerprint is not None:
            self.fingerprint_calculator = self.fingerprint
        if self.persist_index_state is None and self.persist_state is not None:
            self.persist_index_state = self.persist_state


class KBService:
    """Own knowledge-base runtime state and synchronization orchestration."""

    KB_UPLOAD_BATCH_SIZE = 16

    def __init__(self, ports: Optional[KBPorts] = None, **kwargs: Any) -> None:
        if ports is None:
            ports = KBPorts(**kwargs)
        elif kwargs:
            raise TypeError("pass either KBPorts or constructor keyword ports, not both")
        self.ports = ports

        self.ready = ports.initial_ready if ports.initial_ready is not None else {}
        self.syncing = ports.initial_syncing if ports.initial_syncing is not None else set()
        self.rerank_applied = (
            ports.initial_rerank_applied
            if ports.initial_rerank_applied is not None else {}
        )
        self.generations = ports.initial_generations if ports.initial_generations is not None else {}
        self.index_state = ports.initial_index_state if ports.initial_index_state is not None else {}
        self.corpus_hint_cache: Any = None
        self.corpus_fingerprint_cache: Optional[str] = None
        self.retrieve_cache = ports.retrieve_cache
        self.tasks = ports.initial_tasks if ports.initial_tasks is not None else set()

        # v4.0.3：删除服务内部的第二套 `_kb_*`/`_corpus_*` 别名副本。
        # v4.0 过渡期同时维护“公开名 + 私有别名”两份引用，任何一次
        # “改一份忘一份”都会让两套名字指向不同字典（难排查的隐性分叉）。
        # main 侧的 legacy 属性仍与这些公开对象绑定（见 main.__init__），
        # 因此对外契约不变。
        self._framework_loaded = False

    @property
    def framework_loaded(self) -> bool:
        return self._framework_loaded

    @framework_loaded.setter
    def framework_loaded(self, value: bool) -> None:
        self._framework_loaded = bool(value)

    # ------------------------------------------------------------------
    # Small port adapters
    # ------------------------------------------------------------------
    def _cfg(self, key: str, default: Any = None) -> Any:
        getter = self.ports.config_getter
        if getter is None:
            return default
        try:
            return getter(key, default)
        except TypeError:
            return getter(key)
        except Exception:
            return default

    def _embedding_provider(self) -> str:
        resolver = self.ports.embedding_provider_resolver
        if resolver is None:
            return ""
        try:
            return str(resolver() or "").strip()
        except Exception:
            return ""

    def resolve_embedding_provider(self) -> str:
        return self._embedding_provider()

    def _rows(self) -> list[dict]:
        getter = self.ports.effective_corpus_rows
        if getter is None:
            return []
        rows = getter()
        if rows is None:
            return []
        return list(rows)

    def _hint(self) -> Any:
        if self.ports.corpus_hint is None:
            return None
        try:
            return self.ports.corpus_hint()
        except Exception:
            return None

    def _manager(self) -> Any:
        manager = self.ports.kb_manager
        if manager is None:
            manager = getattr(self.ports.context, "kb_manager", None)
        if callable(manager) and not hasattr(manager, "create_kb"):
            try:
                manager = manager()
            except Exception:
                return None
        return manager

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    @staticmethod
    def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    @classmethod
    def _kb_inner(cls, kb: Any) -> Any:
        inner = cls._get_attr(kb, "kb", _MISSING)
        return kb if inner is _MISSING or inner is None else inner

    def _name(self, style_name: str) -> str:
        if self.ports.kb_name is not None:
            return str(self.ports.kb_name(style_name))
        try:
            from style_core.retrieve import sanitize_kb_name

            return sanitize_kb_name(style_name)
        except Exception:
            safe = "".join(c if c.isalnum() else "_" for c in str(style_name))
            return f"human_style_{safe}"

    def kb_name_for_style(self, style_name: str) -> str:
        return self._name(style_name)

    def _description(self, style_name: str, rows: list[dict]) -> str:
        if self.ports.kb_description is not None:
            return str(self.ports.kb_description(style_name, rows))
        try:
            from style_core.retrieve import build_kb_desc

            return build_kb_desc(style_name, rows)
        except Exception:
            return str(style_name)

    def kb_description_for_rows(self, style_name: str, rows: list[dict]) -> str:
        return self._description(style_name, rows)

    def _rerank_id(self) -> str:
        if self.ports.configured_rerank is not None:
            try:
                return str(self.ports.configured_rerank() or "").strip()
            except Exception:
                return ""
        return str(self._cfg("rerank_provider_id", "") or "").strip()

    def _calculate_fingerprint(
        self, rows: list[dict], embedding_id: str
    ) -> Optional[str]:
        callback = self.ports.fingerprint_calculator
        if callback is not None:
            try:
                return callback(rows, embedding_id)
            except TypeError:
                # A rows-only callback is convenient for tests and adapters.
                return callback(rows)
        from humanizer_core.kb_state import corpus_signature, index_fingerprint

        return index_fingerprint(corpus_signature(rows), embedding_id)

    async def _list_documents(self, kb: Any) -> list:
        callback = self.ports.list_all_documents
        if callback is not None:
            return list(await self._maybe_await(callback(kb)) or [])
        from humanizer_core.kb_state import iter_all_documents

        return await iter_all_documents(kb)

    async def list_all_kb_docs(self, kb: Any) -> list:
        """List all documents through the injected/default pagination port."""
        return await self._list_documents(kb)

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.ports, "logger", None)
        if logger is not None:
            fn = getattr(logger, level, None)
            if fn is not None:
                try:
                    fn(message)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Index state and readiness
    # ------------------------------------------------------------------
    def current_index_fingerprint(self, rows: Optional[Iterable[dict]] = None) -> Optional[str]:
        """Return the current corpus/provider fingerprint, or ``None`` when empty.

        The cache stores the corpus-side result.  ``corpus_hint`` is an
        optional cheap invalidation signal; a custom fingerprint callback is
        still called with rows because it may use fields beyond the default
        source/content signature.
        """
        embedding_id = self._embedding_provider()
        custom = self.ports.fingerprint_calculator is not None
        if rows is not None:
            effective = list(rows)
            if not effective:
                return None
            hint = self._hint()
            self.corpus_hint_cache = hint
            self.corpus_fingerprint_cache = None
            return self._calculate_fingerprint(effective, embedding_id)

        hint = self._hint()
        if (
            not custom
            and self.corpus_fingerprint_cache is not None
            and hint == self.corpus_hint_cache
        ):
            from humanizer_core.kb_state import index_fingerprint

            return index_fingerprint(self.corpus_fingerprint_cache, embedding_id)

        effective = self._rows()
        if not effective:
            return None
        if custom:
            fingerprint = self._calculate_fingerprint(effective, embedding_id)
        else:
            from humanizer_core.kb_state import corpus_signature, index_fingerprint

            signature = corpus_signature(effective)
            fingerprint = index_fingerprint(signature, embedding_id)
            self.corpus_fingerprint_cache = signature
        hint = self._hint()
        self.corpus_hint_cache = hint
        return fingerprint

    def index_fresh(self, kb_name: str) -> bool:
        """Compare persisted marker with current fingerprint.

        Fingerprint probing errors are deliberately treated as fresh, matching
        the old conservative non-blocking behavior.
        """
        try:
            fingerprint = self.current_index_fingerprint()
        except Exception:
            return True
        if fingerprint is None:
            return True
        marker = self.index_state.get(kb_name)
        return marker is not None and marker.get("fingerprint") == fingerprint

    def invalidate_index(self) -> None:
        """Invalidate readiness, fingerprint hints, and the optional retrieval cache."""
        self.corpus_hint_cache = None
        self.corpus_fingerprint_cache = None
        self.ready.clear()
        cache = self.retrieve_cache
        if cache is not None:
            try:
                cache.clear()
            except Exception:
                pass

    def persist_index_state(self) -> None:
        callback = self.ports.persist_index_state
        if callback is None:
            return
        try:
            callback(self.index_state)
        except Exception as exc:
            self._log("debug", f"[HumanStyle] KB 指纹状态写盘失败: {exc}")

    # ------------------------------------------------------------------
    # State ownership (v4.0: host no longer mutates KB state directly)
    # ------------------------------------------------------------------
    def invalidate_ready(self, kb_name: str) -> None:
        """Mark one KB not-ready so the next ensure() rebuilds it.

        Used where the host previously wrote ``_kb_ready[name] = False``
        (e.g. rerank drift detected mid-retrieval).
        """
        self.ready[kb_name] = False

    def forget(self, kb_name: str) -> None:
        """Drop all per-KB runtime state to force a content-level rebuild.

        Mirrors the ``/style_index`` sequence that previously popped
        ``_kb_ready`` / ``_kb_rerank_applied`` / ``_kb_index_state`` in main:
        readiness is cleared, rerank reconciliation must re-read KB reality,
        and the persisted fingerprint marker is removed so the next sync
        re-uploads content instead of trusting a stale batch count. The
        marker removal is persisted immediately (same as the old call site).
        """
        self.ready.pop(kb_name, None)
        self.rerank_applied.pop(kb_name, None)
        self.index_state.pop(kb_name, None)
        self.persist_index_state()

    def shutdown(self) -> list[Any]:
        """Retire per-instance KB state and detach tracked tasks.

        Clears readiness and the syncing guard, then returns the tracked
        background tasks so the host can await their cancellation (this
        service never awaits). Mirrors the old terminate sequence of
        ``_kb_ready.clear()`` + cancel each ``_kb_tasks`` + clear both sets.
        """
        tasks = list(self.tasks)
        self.ready.clear()
        self.syncing.clear()
        self.tasks.clear()
        return tasks

    # ------------------------------------------------------------------
    # Ensure/kick/rerank
    # ------------------------------------------------------------------
    async def ensure(self, kb_name: str, style_name: str) -> Optional[str]:
        """Ensure an index is ready, or enqueue one and return ``None``.

        ``None`` means either unavailable, negative-cached, or accepted for
        background synchronization.  A caller can distinguish the latter by
        checking ``kb_name in syncing``.
        """
        if kb_name in self.ready:
            if not self.ready[kb_name]:
                return None
            if self.index_fresh(kb_name):
                return kb_name
            self.ready[kb_name] = False
        if kb_name in self.syncing:
            return None
        if not self._cfg("create_kb", True):
            self.ready[kb_name] = False
            return None
        manager = self._manager()
        if manager is None or not hasattr(manager, "create_kb"):
            self._log("warning", "[HumanStyle] 框架不支持 kb_manager，检索功能禁用")
            self.ready[kb_name] = False
            return None
        embedding_id = self._embedding_provider()
        if not embedding_id:
            # Before the host's loaded signal an empty provider is a startup
            # race, not a terminal configuration failure.
            if not self.framework_loaded:
                self._log(
                    "debug",
                    "[HumanStyle] embedding provider 尚未就绪（框架加载中），"
                    "待 on_astrbot_loaded 后重试检索索引",
                )
                return None
            self._log(
                "warning",
                "[HumanStyle] 未配置 embedding provider，检索功能禁用"
                "（AstrBot 设置中配置 embedding 后可开启）",
            )
            self.ready[kb_name] = False
            return None
        rows = self._rows()
        if not any(str(row.get("content", "") or "").strip() for row in rows if isinstance(row, dict)):
            self.ready[kb_name] = False
            return None
        self.kick_sync(kb_name, style_name)
        return None

    def kick_sync(self, kb_name: str, style_name: str) -> Any:
        """Start one generation of background synchronization and retain its task."""
        self.syncing.add(kb_name)
        generation = self.generations.get(kb_name, 0) + 1
        self.generations[kb_name] = generation
        factory = self.ports.create_task or asyncio.create_task
        task = factory(self.sync_job(kb_name, style_name, generation))
        self.tasks.add(task)
        add_done = getattr(task, "add_done_callback", None)
        if add_done is not None:
            add_done(self.tasks.discard)
        registry = self.ports.task_registry
        if registry is not None and hasattr(registry, "track"):
            registry.track(task, f"kb:{kb_name}")
        return task

    async def rerank_drift(self, kb_name: str) -> bool:
        """Report whether explicitly configured rerank differs from KB reality."""
        wanted = self._rerank_id() or None
        if wanted is None:
            return False
        applied = self.rerank_applied.get(kb_name, _MISSING)
        if applied is _MISSING:
            manager = self._manager()
            helper = None
            if manager is not None and hasattr(manager, "get_kb_by_name"):
                try:
                    helper = await self._maybe_await(manager.get_kb_by_name(kb_name))
                except Exception:
                    helper = None
            inner = self._kb_inner(helper) if helper is not None else None
            applied = self._get_attr(inner, "rerank_provider_id", None)
            self.rerank_applied[kb_name] = applied
        return applied != wanted

    # ------------------------------------------------------------------
    # Synchronization
    # ------------------------------------------------------------------
    def _current_generation(self, kb_name: str, generation: int) -> bool:
        return not generation or generation == self.generations.get(kb_name)

    async def sync_job(self, kb_name: str, style_name: str, generation: int = 0) -> None:
        """Create/reuse, reconcile, and upload a KB index for one generation."""
        if not self._current_generation(kb_name, generation):
            return
        try:
            manager = self._manager()
            if manager is None or not hasattr(manager, "create_kb"):
                if self._current_generation(kb_name, generation):
                    self.ready[kb_name] = False
                return
            embedding_id = self._embedding_provider()
            if not embedding_id:
                if self._current_generation(kb_name, generation):
                    self.ready[kb_name] = False
                return
            rows = self._rows()
            texts = [
                row.get("content", "")
                for row in rows
                if isinstance(row, dict) and str(row.get("content", "") or "").strip()
            ]
            if not texts:
                if self._current_generation(kb_name, generation):
                    self.ready[kb_name] = False
                return
            description = self._description(style_name, rows)
            fingerprint = self.current_index_fingerprint(rows)
            if not self._current_generation(kb_name, generation):
                return

            wanted_rerank = self._rerank_id() or None
            kb = await self._maybe_await(manager.get_kb_by_name(kb_name)) if hasattr(manager, "get_kb_by_name") else None
            if not self._current_generation(kb_name, generation):
                return
            if kb is None:
                kb = await self._maybe_await(
                    manager.create_kb(
                        kb_name,
                        description=description,
                        embedding_provider_id=embedding_id,
                        rerank_provider_id=wanted_rerank,
                    )
                )
                # v4.0.3：提醒旧库残留——风格改名/重建会新建一个
                # `human_style_*` 知识库，旧库不会（也不应）被本插件自动删除。
                self._log(
                    "info",
                    f"[HumanStyle] 已创建检索知识库 {kb_name}；若曾改过风格名，"
                    "旧的 human_style_* 知识库不会自动清理，可在框架知识库页手动删除",
                )
            else:
                inner = self._kb_inner(kb)
                need_description = self._get_attr(inner, "description", None) != description
                need_rerank = bool(wanted_rerank) and self._get_attr(inner, "rerank_provider_id", None) != wanted_rerank
                if (need_description or need_rerank) and hasattr(manager, "update_kb"):
                    try:
                        kb_id = self._get_attr(inner, "kb_id", "")
                        updated = await self._maybe_await(
                            manager.update_kb(
                                kb_id,
                                kb_name,
                                description=description,
                                rerank_provider_id=wanted_rerank,
                            )
                        )
                        if updated is not None and updated is not kb:
                            # update_kb 成功会重建实例并替换注册表，
                            # 后续文档操作必须换用新实例
                            kb = updated
                            self._log(
                                "info",
                                f"[HumanStyle] 知识库 {kb_name} 配置已同步（描述/rerank）",
                            )
                        else:
                            self._log(
                                "warning",
                                f"[HumanStyle] 知识库 {kb_name} 配置同步未生效（框架回滚），"
                                "检查 embedding/rerank 供应商后可用 /style_index 重试",
                            )
                    except Exception as exc:
                        self._log(
                            "warning", f"[HumanStyle] 知识库 {kb_name} 配置同步失败: {exc}"
                        )
                if not self._current_generation(kb_name, generation):
                    return
            self.rerank_applied[kb_name] = wanted_rerank

            builtin_texts = [
                row["content"] for row in rows
                if isinstance(row, dict) and row.get("source") == "builtin" and str(row.get("content", "") or "").strip()
            ]
            user_texts = [
                row["content"] for row in rows
                if isinstance(row, dict) and row.get("source") == "user" and str(row.get("content", "") or "").strip()
            ]
            # 成功日志沿用旧口径：按来源统计**全部行**（非仅非空内容行）。
            builtin_cnt = sum(
                1 for row in rows if isinstance(row, dict) and row.get("source") == "builtin"
            )
            user_cnt = sum(
                1 for row in rows if isinstance(row, dict) and row.get("source") == "user"
            )
            upload_groups = [("__内置_", builtin_texts), ("__用户_", user_texts)]
            group_size = max(1, int(self.ports.upload_group_size or 200))
            batch_size = max(1, int(self.ports.upload_batch_size or self.KB_UPLOAD_BATCH_SIZE))

            try:
                can_list = self.ports.list_all_documents is not None or hasattr(kb, "list_documents")
                if can_list:
                    docs = await self._list_documents(kb)
                    names = [self._get_attr(doc, "doc_name", "") for doc in docs]
                    marker = self.index_state.get(kb_name)
                    fp_match = bool(fingerprint and marker and marker.get("fingerprint") == fingerprint)
                    statuses = []
                    for prefix, group_texts in upload_groups:
                        if not group_texts:
                            statuses.append((prefix, group_texts, True))
                            continue
                        expected = (len(group_texts) + group_size - 1) // group_size
                        actual = sum(1 for name in names if f"{kb_name}{prefix}" in str(name))
                        statuses.append((prefix, group_texts, actual >= expected))
                    complete = bool(statuses and all(ok for _, _, ok in statuses))
                    if complete and (fp_match or marker is None):
                        if not self._current_generation(kb_name, generation):
                            return
                        self.ready[kb_name] = True
                        if fingerprint and not fp_match:
                            self.index_state[kb_name] = {"fingerprint": fingerprint}
                            self.persist_index_state()
                            self._log(
                                "info",
                                f"[HumanStyle] 知识库 {kb_name} 批数齐全且无历史指纹，"
                                "已认领（写指纹不重传）",
                            )
                        else:
                            self._log(
                                "info",
                                f"[HumanStyle] 知识库 {kb_name} 指纹一致且批数齐全，跳过上传",
                            )
                        return
                    for prefix, group_texts, is_complete in statuses:
                        if not group_texts or (is_complete and fp_match):
                            continue
                        # 指纹变化（内容/模型换血）或分组不完整：清理旧组重传
                        reason = (
                            "指纹变化"
                            if (complete and not fp_match)
                            else "分组不完整"
                        )
                        for doc in docs:
                            name = str(self._get_attr(doc, "doc_name", ""))
                            if f"{kb_name}{prefix}" not in name:
                                continue
                            try:
                                await self._maybe_await(kb.delete_document(self._get_attr(doc, "doc_id", "")))
                            except Exception:
                                pass
                        self._log(
                            "info",
                            f"[HumanStyle] 知识库 {kb_name}{prefix} {reason}，已清除待重传",
                        )
                elif user_cnt == 0:
                    # 无用户语料来源：复用已存在的知识库即视为已同步。
                    # 旧实现直接 await kb.count_documents()，缺该方法时抛
                    # AttributeError 由外层 except 记「已同步检测失败」警告后
                    # 回退重传——此处保持同一路径（不加 hasattr 静默守卫）。
                    existing = await self._maybe_await(kb.count_documents())
                    if existing and existing > 0:
                        if self._current_generation(kb_name, generation):
                            self.ready[kb_name] = True
                            self._log(
                                "info",
                                f"[HumanStyle] 知识库 {kb_name} 已有 {existing} 个文档，跳过上传",
                            )
                            return
            except Exception as exc:
                self._log(
                    "warning",
                    f"[HumanStyle] 知识库 {kb_name} 已同步检测失败，本次按需重传: {exc}",
                )

            upload_ok = True
            for prefix, group_texts in upload_groups:
                if not group_texts:
                    continue
                for offset in range(0, len(group_texts), group_size):
                    if not self._current_generation(kb_name, generation):
                        return
                    chunk = group_texts[offset : offset + group_size]
                    try:
                        await self._maybe_await(
                            kb.upload_document(
                                file_name=f"{kb_name}{prefix}{offset}.txt",
                                file_content=None,
                                file_type="txt",
                                pre_chunked_text=chunk,
                                batch_size=batch_size,
                            )
                        )
                    except Exception as exc:
                        upload_ok = False
                        self._log(
                            "warning",
                            f"[HumanStyle] 语料写入知识库 {prefix}{offset} 批失败: {exc}",
                        )
            if not upload_ok:
                if self._current_generation(kb_name, generation):
                    self.ready[kb_name] = False
                    self._log(
                        "warning",
                        f"[HumanStyle] 知识库 {kb_name} 上传不完整，本轮检索禁用（重启自愈）",
                    )
                return
            if self._current_generation(kb_name, generation):
                self.ready[kb_name] = True
                if fingerprint:
                    self.index_state[kb_name] = {"fingerprint": fingerprint}
                    self.persist_index_state()
                self._log(
                    "info",
                    f"[HumanStyle] 有效语料已同步到知识库 {kb_name}"
                    f"（内置 {builtin_cnt} + 用户 {user_cnt} = {len(texts)} 条）",
                )
        except Exception as exc:
            if self._current_generation(kb_name, generation):
                self.ready[kb_name] = False
            self._log("warning", f"[HumanStyle] 知识库初始化失败，检索禁用: {exc}")
        finally:
            if self._current_generation(kb_name, generation):
                self.syncing.discard(kb_name)

    async def retrieve_section(
        self,
        kb_name: str,
        query: str,
        candidates: int,
        top_k: int,
        timeout: float,
    ) -> str:
        """Delegate retrieval formatting when a formatter port is supplied."""
        formatter = self.ports.retrieval_formatter
        if formatter is None:
            from style_core.retrieve import retrieve_section

            return await retrieve_section(
                self._manager(),
                kb_name=kb_name,
                query=query,
                candidates=candidates,
                top_k=top_k,
                timeout=timeout,
            )
        return await self._maybe_await(
            formatter(
                self._manager(),
                kb_name=kb_name,
                query=query,
                candidates=candidates,
                top_k=top_k,
                timeout=timeout,
            )
        )


__all__ = ["KBPorts", "KBService"]
