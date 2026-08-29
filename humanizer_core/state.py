# -*- coding: utf-8 -*-
"""持久化模块（零 astrbot 依赖）。

- TimeStateStore：time_state.json，会话最近活动时间 {umo: 墙钟秒}
- LifeStateStore：life_state.json（当日）+ history/life_state_YYYY.MM.DD.json（近 N 天）

全部本地文件原子读写（tmp + os.replace），失败只记日志、不影响对话。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from .time_flow import LifeState

logger = logging.getLogger(__name__)

_TIME_STATE_VERSION = 1
_HISTORY_FILE_RE = re.compile(r"life_state_(\d{4}\.\d{2}\.\d{2})\.json$")


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _history_name(date: str) -> str:
    return f"life_state_{date.replace('-', '.')}.json"


class TimeStateStore:
    """time_state.json —— {"version": 1, "last_seen": {umo: 墙钟秒}}。"""

    def __init__(self, path: Path):
        self._path = Path(path)

    def load(self) -> dict[str, float]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        last = raw.get("last_seen") if isinstance(raw, dict) else None
        if not isinstance(last, dict):
            return {}
        out: dict[str, float] = {}
        for k, v in last.items():
            if isinstance(k, str) and k and isinstance(v, (int, float)) and v > 0:
                out[k] = float(v)
        return out

    def save(self, last_seen: dict[str, float]) -> None:
        try:
            _atomic_write_json(
                self._path, {"version": _TIME_STATE_VERSION, "last_seen": last_seen}
            )
        except Exception as e:
            logger.warning(f"[Humanizer] time_state 写盘失败: {e}")

    @staticmethod
    def prune(
        last_seen: dict[str, float], now_ts: float, max_age_days: int = 30
    ) -> dict[str, float]:
        cutoff = now_ts - max_age_days * 86400.0
        return {k: v for k, v in last_seen.items() if v >= cutoff}


class LifeStateStore:
    """life_state.json（当日）+ history/（近 N 天），按日期归档。"""

    MAX_HISTORY = 7

    def __init__(self, path: Path):
        self._path = Path(path)
        self._history_dir = self._path.parent / "history"
        self._data: LifeState | None = None
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = LifeState.from_dict(raw)
        except Exception:
            self._data = None

    def current(self) -> LifeState | None:
        return self._data if (self._data is not None and self._data.status == "ok") else None

    def current_for_date(self, date: str) -> LifeState | None:
        cur = self.current()
        if cur is not None and cur.date == date:
            return cur
        return None

    def get_by_date(self, date: str) -> LifeState | None:
        cur = self.current()
        if cur is not None and cur.date == date:
            return cur
        try:
            raw = json.loads(
                (self._history_dir / _history_name(date)).read_text(encoding="utf-8")
            )
            return LifeState.from_dict(raw)
        except Exception:
            return None

    def set(self, state: LifeState) -> None:
        self._data = state
        try:
            _atomic_write_json(self._path, state.to_dict())
            same = self._history_dir / _history_name(state.date)
            if same.exists():
                same.unlink()  # 同日历史清除，避免双份
        except Exception as e:
            logger.warning(f"[Humanizer] life_state 写盘失败: {e}")
        self._prune_history()

    def get_recent_history(self, before_date: str, limit: int = 3) -> list[LifeState]:
        out: list[LifeState] = []
        try:
            names = sorted(self._history_dir.glob("life_state_*.json"), reverse=True)
        except Exception:
            return []
        for p in names:
            m = _HISTORY_FILE_RE.search(p.name)
            if not m:
                continue
            if m.group(1).replace(".", "-") >= before_date:
                continue
            try:
                st = LifeState.from_dict(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
            if st is not None and st.status == "ok":
                out.append(st)
                if len(out) >= limit:
                    break
        return out

    def archive_before_generation(self, target_date: str) -> None:
        """当前状态不是目标日期时，归档进 history 并清空当日文件。"""
        cur = self._data
        if cur is None or cur.date == target_date:
            return
        try:
            self._history_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(
                self._history_dir / _history_name(cur.date), cur.to_dict()
            )
        except Exception as e:
            logger.warning(f"[Humanizer] life_state 归档失败: {e}")
        self._data = None
        try:
            self._path.unlink(missing_ok=True)
        except Exception:
            pass
        self._prune_history()

    def _prune_history(self, keep: int = 7) -> None:
        try:
            names = sorted(
                (
                    p
                    for p in self._history_dir.glob("life_state_*.json")
                    if _HISTORY_FILE_RE.search(p.name)
                ),
                reverse=True,
            )
            for p in names[max(0, keep) :]:
                p.unlink(missing_ok=True)
        except Exception:
            pass


__all__ = ["LifeStateStore", "TimeStateStore", "_atomic_write_json"]
