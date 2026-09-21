# -*- coding: utf-8 -*-
"""持久化模块（日志按插件市场规范统一走 astrbot.api 的 logger）。

- TimeStateStore：time_state.json，会话最近活动时间 {umo: 墙钟秒}
- LifeStateStore：life_state.json（当日）+ history/life_state_YYYY.MM.DD.json（近 N 天）

全部本地文件原子读写（tmp + os.replace），失败只记日志、不影响对话。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from astrbot.api import logger

from .time_flow import LifeState

_TIME_STATE_VERSION = 3
_PERSONA_STATE_VERSION = 1
_HISTORY_FILE_RE = re.compile(r"life_state_(\d{4}\.\d{2}\.\d{2})\.json$")


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _history_name(date: str) -> str:
    return f"life_state_{date.replace('-', '.')}.json"


class TimeStateStore:
    """time_state.json —— v3: {"version": 3, "last_seen": {...},
    "first_seen": {...}, "user_seen": {...}, "ai_seen": {...}}。

    v3.7.0 起带 first_seen（相识起点，供「认识第 N 天」注入）；v3.8.0 起
    带 user_seen/ai_seen 双向打点（供「对方/你最后发言 X」注入）——last_seen
    语义不变（用户与 Bot 任一活动的合并最大值），旧调用方零改动。

    兼容读写：load() 只回 last_seen；first_seen 走 load_first_seen()，
    双向表走 load_sides()——v1/v2 文件/缺键返回空表（回填逻辑在调用方：
    first 拿 last 兜底；user 拿 last 兜底，ai 侧无依据不回填，等真实记账收敛）。
    """

    def __init__(self, path: Path):
        self._path = Path(path)

    def _read(self) -> dict:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _filter_ts(mapping) -> dict[str, float]:
        out: dict[str, float] = {}
        if isinstance(mapping, dict):
            for k, v in mapping.items():
                if isinstance(k, str) and k and isinstance(v, (int, float)) and v > 0:
                    out[k] = float(v)
        return out

    def load(self) -> dict[str, float]:
        return self._filter_ts(self._read().get("last_seen"))

    def load_first_seen(self) -> dict[str, float]:
        return self._filter_ts(self._read().get("first_seen"))

    def load_sides(self) -> tuple[dict[str, float], dict[str, float]]:
        """双向打点表 (user_seen, ai_seen)（v3.8.0）；v1/v2/缺键返回两空表。"""
        raw = self._read()
        return (
            self._filter_ts(raw.get("user_seen")),
            self._filter_ts(raw.get("ai_seen")),
        )

    def save(
        self,
        last_seen: dict[str, float],
        first_seen: dict[str, float] | None = None,
        user_seen: dict[str, float] | None = None,
        ai_seen: dict[str, float] | None = None,
    ) -> None:
        try:
            _atomic_write_json(
                self._path,
                {
                    "version": _TIME_STATE_VERSION,
                    "last_seen": last_seen,
                    "first_seen": dict(first_seen or {}),
                    "user_seen": dict(user_seen or {}),
                    "ai_seen": dict(ai_seen or {}),
                },
            )
        except Exception as e:
            logger.warning(f"[Humanizer] time_state 写盘失败: {e}")

    @staticmethod
    def prune(
        last_seen: dict[str, float], now_ts: float, max_age_days: int = 30
    ) -> dict[str, float]:
        cutoff = now_ts - max_age_days * 86400.0
        return {k: v for k, v in last_seen.items() if v >= cutoff}

    @staticmethod
    def restrict(mapping: dict[str, float], keep_keys) -> dict[str, float]:
        """按 last_seen 清理后的键集收缩另一张表（first/user/ai 与主表同步收缩）。"""
        keys = set(keep_keys)
        return {k: v for k, v in mapping.items() if k in keys}


class PersonaStateStore:
    """persona_state.json —— v3.5.1 情绪惯性状态。

    {"version": 1, "emotions": {umo: {"emotion": str, "intensity": float}}}
    损坏/缺失按空表处理（调用方以 neutral 兜底），单条非法直接丢弃。
    """

    def __init__(self, path: Path):
        self._path = Path(path)

    def load(self) -> dict[str, dict]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        emos = raw.get("emotions") if isinstance(raw, dict) else None
        if not isinstance(emos, dict):
            return {}
        out: dict[str, dict] = {}
        for umo, st in emos.items():
            if not (isinstance(umo, str) and umo and isinstance(st, dict)):
                continue
            emo = st.get("emotion")
            val = st.get("intensity")
            if emo in ("neutral", "sulky", "appy") and isinstance(val, (int, float)):
                entry = {"emotion": emo, "intensity": float(val)}
                # ts 透传：重启后 prune 依赖它判断陈旧，丢了会把全表当陈旧清除
                ts = st.get("ts")
                if isinstance(ts, (int, float)) and ts > 0:
                    entry["ts"] = float(ts)
                out[umo] = entry
        return out

    def save(self, emotions: dict[str, dict]) -> None:
        try:
            _atomic_write_json(
                self._path,
                {"version": _PERSONA_STATE_VERSION, "emotions": emotions},
            )
        except Exception as e:
            logger.warning(f"[Humanizer] persona_state 写盘失败: {e}")

    @staticmethod
    def prune(
        emotions: dict[str, dict], now_ts: float, max_age_days: int = 14
    ) -> dict[str, dict]:
        """按条目时间戳清理陈旧会话；无 ts 的条目视为陈旧一并清除。"""
        cutoff = now_ts - max_age_days * 86400.0
        out = {}
        for k, st in emotions.items():
            ts = st.get("ts") if isinstance(st, dict) else None
            if isinstance(ts, (int, float)) and ts >= cutoff:
                out[k] = st
        return out


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


__all__ = ["LifeStateStore", "PersonaStateStore", "TimeStateStore", "_atomic_write_json"]
