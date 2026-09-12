# -*- coding: utf-8 -*-
"""检索结果缓存（v3.9.5，有界 TTL-LRU + in-flight 合并）。

只缓存成功且非空的最终结果；异常/超时/取消不写缓存。同一 key 的并发
请求共享同一个底层任务（asyncio.shield），取消任一等待者不会取消共享
任务本身。进程内缓存，不落盘、不跨重启。
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Hashable, Optional


class RetrieveCache:
    def __init__(self, maxsize: int = 256, ttl: float = 60.0):
        self._maxsize = max(1, int(maxsize or 256))
        self._ttl = max(1.0, float(ttl or 60.0))
        self._data: "OrderedDict[Hashable, tuple[float, Any]]" = OrderedDict()
        self._inflight: dict[Hashable, asyncio.Task] = {}
        self.hits = 0
        self.misses = 0

    # ---- 同步缓存面 ----
    def get(self, key: Hashable, now: Optional[float] = None) -> Any:
        ent = self._data.get(key)
        if ent is None:
            return None
        expires, value = ent
        if (now if now is not None else time.monotonic()) >= expires:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def put(self, key: Hashable, value: Any, now: Optional[float] = None) -> None:
        if not value:
            return  # 空结果不缓存（失败/无命中语义）
        ts = now if now is not None else time.monotonic()
        self._data[key] = (ts + self._ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    # ---- 异步合并面 ----
    async def get_or_create(
        self, key: Hashable, factory: Callable[[], Awaitable[Any]]
    ) -> Any:
        hit = self.get(key)
        if hit is not None:
            self.hits += 1
            return hit
        self.misses += 1
        task = self._inflight.get(key)
        if task is None or task.done():
            task = asyncio.ensure_future(factory())
            self._inflight[key] = task

            def _done(t: asyncio.Task, k: Hashable = key) -> None:
                if self._inflight.get(k) is t:
                    self._inflight.pop(k, None)
                if not t.cancelled():
                    exc = t.exception()  # 消费异常，防 "never retrieved"
                    if exc is not None:
                        return
                    # 由 leader 落缓存（follower 也走同一 await 路径）
                    try:
                        value = t.result()
                    except Exception:  # noqa: BLE001
                        return
                    if value:
                        self.put(k, value)

            task.add_done_callback(_done)
        return await asyncio.shield(task)


__all__ = ["RetrieveCache"]
