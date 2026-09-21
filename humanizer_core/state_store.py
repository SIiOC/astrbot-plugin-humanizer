# -*- coding: utf-8 -*-
"""Pure-Python persistence paths and store facade.

This module deliberately only wires the existing persistence stores together.  It
owns no schema and performs no migration or implicit writes.  In particular,
constructing :class:`DataPaths` or :class:`StateStore` does not create a
filesystem directory.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from astrbot.api import logger

from .commitments import CommitmentStore
from .state import (
    LifeStateStore,
    PersonaStateStore,
    TimeStateStore,
    _atomic_write_json,
)


@dataclass(frozen=True, slots=True)
class DataPaths:
    """Stable paths below a plugin data directory.

    The constructor and factories normalize the directory path only; they do
    not create it or any of its children.  The path properties are intentionally
    just paths, so callers remain responsible for choosing when and how to read
    or write each domain.
    """

    data_dir: Path

    _FILE_NAMES: ClassVar[dict[str, str]] = {
        "proactive_state": "proactive_state.json",
        "stats": "stats.json",
        "time_state": "time_state.json",
        "persona_state": "persona_state.json",
        "life_state": "life_state.json",
        "commitments": "commitments.json",
        "lang_profile": "lang_profile.json",
        "humaneness_rules": "humaneness_rules.json",
        "kb_index_state": "kb_index_state.json",
        "state_human_style": "state_human_style.json",
    }

    def __post_init__(self) -> None:
        # Path.absolute() is lexical normalization and does not create or
        # inspect the target directory.  Keeping one canonical Path also makes
        # all derived properties stable when a relative path is supplied.
        path = Path(self.data_dir).expanduser()
        if not path.is_absolute():
            path = path.absolute()
        object.__setattr__(self, "data_dir", path)

    @classmethod
    def from_data_dir(cls, data_dir: str | Path) -> "DataPaths":
        """Build paths for an already selected plugin data directory."""
        return cls(Path(data_dir))

    @classmethod
    def from_plugin_data_dir(cls, data_dir: str | Path) -> "DataPaths":
        """Descriptive alias for :meth:`from_data_dir`."""
        return cls.from_data_dir(data_dir)

    @classmethod
    def for_plugin(cls, data_dir: str | Path) -> "DataPaths":
        """Compatibility alias for callers naming the plugin explicitly."""
        return cls.from_data_dir(data_dir)

    def _file(self, key: str) -> Path:
        return self.data_dir / self._FILE_NAMES[key]

    @property
    def proactive_state(self) -> Path:
        return self._file("proactive_state")

    @property
    def stats(self) -> Path:
        return self._file("stats")

    @property
    def time_state(self) -> Path:
        return self._file("time_state")

    @property
    def persona_state(self) -> Path:
        return self._file("persona_state")

    @property
    def life_state(self) -> Path:
        return self._file("life_state")

    @property
    def commitments(self) -> Path:
        return self._file("commitments")

    @property
    def lang_profile(self) -> Path:
        return self._file("lang_profile")

    @property
    def humaneness_rules(self) -> Path:
        return self._file("humaneness_rules")

    @property
    def kb_index_state(self) -> Path:
        return self._file("kb_index_state")

    @property
    def state_human_style(self) -> Path:
        return self._file("state_human_style")

    @property
    def styles(self) -> Path:
        return self.data_dir / "styles"

    @property
    def corpora(self) -> Path:
        return self.data_dir / "corpora"

    # Explicit *_path and *_dir aliases make the distinction between a file
    # path and a directory obvious without changing the canonical names above.
    @property
    def proactive_state_path(self) -> Path:
        return self.proactive_state

    @property
    def stats_path(self) -> Path:
        return self.stats

    @property
    def time_state_path(self) -> Path:
        return self.time_state

    @property
    def persona_state_path(self) -> Path:
        return self.persona_state

    @property
    def life_state_path(self) -> Path:
        return self.life_state

    @property
    def commitments_path(self) -> Path:
        return self.commitments

    @property
    def lang_profile_path(self) -> Path:
        return self.lang_profile

    @property
    def humaneness_rules_path(self) -> Path:
        return self.humaneness_rules

    @property
    def kb_index_state_path(self) -> Path:
        return self.kb_index_state

    @property
    def state_human_style_path(self) -> Path:
        return self.state_human_style

    @property
    def styles_dir(self) -> Path:
        return self.styles

    @property
    def corpora_dir(self) -> Path:
        return self.corpora


def resolve_data_paths(data_dir: str | Path) -> DataPaths:
    """Factory function for code that prefers a function over a classmethod."""
    return DataPaths.from_data_dir(data_dir)


class StateStore:
    """Facade over the existing typed persistence stores.

    Only the four stores whose implementations already exist are constructed:
    ``time``, ``persona``, ``life`` and ``commitments``.  Other domains are
    exposed as stable paths so a later phase can choose their schemas and write
    policies without this facade making assumptions about them.
    """

    def __init__(self, data_dir: str | Path | DataPaths):
        self.paths = data_dir if isinstance(data_dir, DataPaths) else DataPaths.from_data_dir(data_dir)
        self.data_dir = self.paths.data_dir

        self.time = TimeStateStore(self.paths.time_state)
        self.persona = PersonaStateStore(self.paths.persona_state)
        self.life = LifeStateStore(self.paths.life_state)
        self.commitments = CommitmentStore(self.paths.commitments)

    # Typed-store aliases keep the facade readable at call sites that prefer
    # the word "store", while the short names above remain the public facade.
    @property
    def time_store(self) -> TimeStateStore:
        return self.time

    @property
    def persona_store(self) -> PersonaStateStore:
        return self.persona

    @property
    def life_store(self) -> LifeStateStore:
        return self.life

    @property
    def commitments_store(self) -> CommitmentStore:
        return self.commitments

    # Stable paths for domains that do not yet have a typed store here.
    @property
    def proactive(self) -> Path:
        return self.paths.proactive_state

    @property
    def proactive_path(self) -> Path:
        return self.paths.proactive_state

    @property
    def stats(self) -> Path:
        return self.paths.stats

    @property
    def stats_path(self) -> Path:
        return self.paths.stats

    @property
    def lang(self) -> Path:
        return self.paths.lang_profile

    @property
    def lang_path(self) -> Path:
        return self.paths.lang_profile

    @property
    def rules(self) -> Path:
        return self.paths.humaneness_rules

    @property
    def rules_path(self) -> Path:
        return self.paths.humaneness_rules

    @property
    def kb(self) -> Path:
        return self.paths.kb_index_state

    @property
    def kb_path(self) -> Path:
        return self.paths.kb_index_state

    @property
    def style(self) -> Path:
        return self.paths.state_human_style

    @property
    def style_path(self) -> Path:
        return self.paths.state_human_style

    @property
    def proactive_state(self) -> Path:
        return self.paths.proactive_state

    @property
    def proactive_state_path(self) -> Path:
        return self.paths.proactive_state

    @property
    def stats_path(self) -> Path:
        return self.paths.stats

    @property
    def time_state_path(self) -> Path:
        return self.paths.time_state

    @property
    def persona_state_path(self) -> Path:
        return self.paths.persona_state

    @property
    def life_state_path(self) -> Path:
        return self.paths.life_state

    @property
    def commitments_path(self) -> Path:
        return self.paths.commitments

    @property
    def lang_profile(self) -> Path:
        return self.paths.lang_profile

    @property
    def lang_profile_path(self) -> Path:
        return self.paths.lang_profile

    @property
    def humaneness_rules(self) -> Path:
        return self.paths.humaneness_rules

    @property
    def humaneness_rules_path(self) -> Path:
        return self.paths.humaneness_rules

    @property
    def kb_index_state(self) -> Path:
        return self.paths.kb_index_state

    @property
    def kb_index_state_path(self) -> Path:
        return self.paths.kb_index_state

    @property
    def state_human_style(self) -> Path:
        return self.paths.state_human_style

    @property
    def state_human_style_path(self) -> Path:
        return self.paths.state_human_style

    def flush_domains(
        self,
        callbacks: Mapping[str, Callable[..., Any]] | None = None,
        payloads: Mapping[str, Any] | None = None,
    ) -> dict[str, bool]:
        """Run explicitly supplied domain flush callbacks independently.

        A callback receives the matching payload when one is supplied,
        otherwise it is called with no arguments.  No default callbacks and no
        implicit JSON writes are invented here.  Each domain is isolated:
        callback failures are logged and reported as ``False`` while the other
        domains continue.  A payload without a callback is reported as a
        failure rather than silently discarded.
        """
        callback_map = callbacks or {}
        payload_map = payloads or {}
        if not isinstance(callback_map, Mapping):
            raise TypeError("callbacks must be a mapping")
        if not isinstance(payload_map, Mapping):
            raise TypeError("payloads must be a mapping")

        results: dict[str, bool] = {}
        domains = list(dict.fromkeys((*callback_map.keys(), *payload_map.keys())))
        for domain in domains:
            callback = callback_map.get(domain)
            if not callable(callback):
                logger.warning("[Humanizer] no flush callback for domain %s", domain)
                results[domain] = False
                continue
            try:
                if domain in payload_map:
                    callback(payload_map[domain])
                else:
                    callback()
            except Exception:  # noqa: BLE001 - one domain must not block others
                logger.exception("[Humanizer] flush failed for domain %s", domain)
                results[domain] = False
            else:
                results[domain] = True
        return results


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read JSON defensively, returning ``default`` on any read/decode error."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - persistence is best effort
        return default


def write_json(path: str | Path, payload: Any) -> None:
    """Write JSON through the existing atomic helper without changing schemas."""
    _atomic_write_json(Path(path), payload)


__all__ = [
    "CommitmentStore",
    "DataPaths",
    "LifeStateStore",
    "PersonaStateStore",
    "StateStore",
    "TimeStateStore",
    "_atomic_write_json",
    "read_json",
    "resolve_data_paths",
    "write_json",
]
