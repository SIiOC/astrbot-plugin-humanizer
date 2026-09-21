# -*- coding: utf-8 -*-
"""后台任务注册表（v3.9.5）。

统一登记 fire-and-forget 任务（承诺确认/生活生成/KB 自愈/配置保存等），
done callback 消费异常防 "Task exception was never retrieved"；close 后
拒绝新任务；cancel_all 取消并等待，供 terminate 收尾。
"""

from __future__ import annotations

import asyncio

class TaskRegistry:
    def __init__(self):
        self._tasks: dict[asyncio.Task, str] = {}
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def __len__(self) -> int:
        return len(self._tasks)

    def track(self, task: asyncio.Task, name: str = "") -> asyncio.Task:
        """登记任务；closed 后不再登记（任务本身照常运行，调用方自担）。"""
        if self._closed or task.done():
            return task
        self._tasks[task] = str(name or task.get_name())
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, t: asyncio.Task) -> None:
        self._tasks.pop(t, None)
        if not t.cancelled():
            t.exception()  # 消费异常

    def close(self) -> None:
        self._closed = True

    async def cancel_all(self, timeout: float = 5.0) -> None:
        pending = [t for t in self._tasks if not t.done()]
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.wait(pending, timeout=timeout)
        self._tasks.clear()


__all__ = ["TaskRegistry"]
