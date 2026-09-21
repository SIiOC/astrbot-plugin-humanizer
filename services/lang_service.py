# -*- coding: utf-8 -*-
"""语言风格趋同画像的状态所有权（v4.0 Phase 6 第三片）。

从 `main.HumanizerPlugin` 下沉 lang_profile.json 的**内存容器**与三类操作
（采集 / 剪枝 / 载入），保持 v3.9.1 全部语义与 v3.9.5 的"剪枝回写内存"修复：

- 采集：`lang_mirror_enable` 守卫 + `lang_mirror_profanity_filter` 透传，
  纯统计零 LLM 成本；异常吞掉记 debug（采集失败不得影响对话主链）。
- 剪枝：`prune_profiles(profiles, now)` 剔除 30 天外陈旧画像；**结果原地回写
  到同一 dict 对象**（V3.9.5 修复：旧实现只写文件不回写内存，长期运行会
  无限保留所有见过会话的画像）。原地清空+更新而非重新赋值——这样 main
  侧 `_lang_profiles` 别名与服务始终指向同一对象，杜绝悬空引用。
- 载入：缺失/损坏按空表；只保留 dict 型画像项。

`_lang_dirty`（脏标记）刻意留在 main：bool 无法跨对象共享引用，且刷盘节拍
由 `_time_flush_loop` 统一驱动。服务只返回"是否发生变更"。

不依赖 AstrBot：config / logger / clock 均为注入依赖，可离线单测。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from humanizer_core.lang_mirror import (
    observe as lang_observe,
    prune_profiles as prune_lang_profiles,
)


class LangMirrorState:
    """持有语言画像字典并负责其采集/剪枝/载入。"""

    def __init__(
        self,
        *,
        store_path: str | os.PathLike[str] | None = None,
        config_getter: Optional[Callable[..., Any]] = None,
        logger: Any = None,
        clock: Callable[[], float] = None,  # type: ignore[assignment]
        observe_fn: Callable[..., Any] = lang_observe,
        prune_fn: Callable[..., Any] = prune_lang_profiles,
    ) -> None:
        self.store_path = Path(store_path) if store_path else None
        self._config = config_getter
        self._logger = logger
        if clock is None:
            import time as _time

            clock = _time.time
        self._clock = clock
        self._observe_fn = observe_fn
        self._prune_fn = prune_fn
        # 公开字典：main 侧 `_lang_profiles` 绑定到**同一对象**（非副本）。
        self.profiles: dict[str, dict] = {}

    # -- 依赖适配 ---------------------------------------------------------
    def _cfg(self, key: str, default: Any) -> Any:
        getter = self._config
        if getter is None:
            return default
        try:
            return getter(key, default)
        except TypeError:
            try:
                return getter(key)
            except Exception:  # noqa: BLE001
                return default
        except Exception:  # noqa: BLE001
            return default

    def _log(self, level: str, message: str) -> None:
        if self._logger is None:
            return
        fn = getattr(self._logger, level, None)
        if fn is not None:
            try:
                fn(message)
            except Exception:  # noqa: BLE001
                pass

    # -- 载入 -------------------------------------------------------------
    def load(self) -> None:
        """从 store_path 载入画像；缺失/损坏按空表，只保留 dict 型项。

        原地清空+更新，保持 `profiles` 对象标识稳定（别名不悬空）。
        """
        loaded: dict[str, dict] = {}
        path = self.store_path
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                profs = raw.get("profiles") if isinstance(raw, dict) else None
                loaded = {
                    k: v for k, v in (profs or {}).items() if isinstance(v, dict)
                }
            except Exception:  # noqa: BLE001
                loaded = {}
        self.profiles.clear()
        self.profiles.update(loaded)

    # -- 采集 -------------------------------------------------------------
    def observe(self, umo: str, text: str) -> bool:
        """采集一条用户消息的语言习惯；返回是否发生变更（供置脏标记）。

        受 `lang_mirror_enable` 守卫；粗口过滤由 `lang_mirror_profanity_filter`
        控制。异常吞掉记 debug——采集失败不得影响对话主链。
        """
        if not bool(self._cfg("lang_mirror_enable", True)):
            return False
        try:
            self.profiles[umo] = self._observe_fn(
                self.profiles.get(umo),
                text,
                ts=self._clock(),
                profanity_filter=bool(
                    self._cfg("lang_mirror_profanity_filter", True)
                ),
            )
            return True
        except Exception as e:  # noqa: BLE001
            self._log("debug", f"[Humanizer] 语言画像采集失败: {e}")
            return False

    # -- 剪枝 -------------------------------------------------------------
    def prune(self, now: float | None = None) -> dict[str, dict]:
        """剪枝陈旧画像并**原地回写** `profiles`；返回用于落盘的快照。

        V3.9.5 修复契约：剪枝结果必须回到内存（否则长期运行无限累积画像）。
        原地清空+更新保证别名不悬空；返回值是独立副本，供调用方写入文件。
        """
        if now is None:
            now = self._clock()
        pruned = self._prune_fn(self.profiles, now)
        if len(pruned) != len(self.profiles):
            self.profiles.clear()
            self.profiles.update(pruned)
        return dict(pruned)

    def text_for(self, umo: str, *, min_msgs: int, topk: int) -> str:
        """渲染某会话的语言趋同注入文本（无画像/样本不足返回空串）。"""
        from humanizer_core.lang_mirror import build_lang_mirror_text

        return build_lang_mirror_text(
            self.profiles.get(umo), min_msgs=min_msgs, topk=topk
        )


__all__ = ["LangMirrorState"]
