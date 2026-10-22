# -*- coding: utf-8 -*-
"""Tests for the Phase 1 pure-Python persistence infrastructure."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from humanizer_core.state import (
    LifeStateStore,
    PersonaStateStore,
    TimeStateStore,
    _atomic_write_json as state_atomic_write_json,
)
from humanizer_core.state_store import (
    DataPaths,
    StateStore,
    _atomic_write_json,
    resolve_data_paths,
)
from humanizer_core.time_flow import LifeState, TimelineEntry


class TestDataPaths(unittest.TestCase):
    def test_resolves_all_stable_paths_without_creating_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "plugin-data" / "nested"
            paths = DataPaths.from_data_dir(data_dir)

            self.assertEqual(paths.data_dir, data_dir.absolute())
            self.assertFalse(data_dir.exists())
            expected_files = {
                "proactive_state": "proactive_state.json",
                "stats": "stats.json",
                "time_state": "time_state.json",
                "persona_state": "persona_state.json",
                "life_state": "life_state.json",
                "lang_profile": "lang_profile.json",
                "humaneness_rules": "humaneness_rules.json",
                "kb_index_state": "kb_index_state.json",
                "state_human_style": "state_human_style.json",
            }
            for attr, filename in expected_files.items():
                self.assertEqual(getattr(paths, attr), data_dir.absolute() / filename)
                self.assertEqual(getattr(paths, f"{attr}_path"), getattr(paths, attr))
            self.assertEqual(paths.styles, data_dir.absolute() / "styles")
            self.assertEqual(paths.corpora, data_dir.absolute() / "corpora")
            self.assertEqual(paths.styles_dir, paths.styles)
            self.assertEqual(paths.corpora_dir, paths.corpora)

    def test_factory_aliases_resolve_same_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected = DataPaths.from_data_dir(Path(tmp)).data_dir
            self.assertEqual(resolve_data_paths(tmp).data_dir, expected)
            self.assertEqual(DataPaths.for_plugin(tmp).data_dir, expected)
            self.assertEqual(DataPaths.from_plugin_data_dir(tmp).data_dir, expected)


class TestStateStore(unittest.TestCase):
    def test_constructs_existing_typed_stores_and_exposes_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            store = StateStore(data_dir)

            self.assertIs(store.data_dir, store.paths.data_dir)
            self.assertIsInstance(store.time, TimeStateStore)
            self.assertIsInstance(store.persona, PersonaStateStore)
            self.assertIsInstance(store.life, LifeStateStore)
            self.assertIs(store.time_store, store.time)
            self.assertIs(store.persona_store, store.persona)
            self.assertIs(store.life_store, store.life)
            self.assertEqual(store.proactive, store.paths.proactive_state)
            self.assertEqual(store.stats, store.paths.stats)
            self.assertEqual(store.lang, store.paths.lang_profile)
            self.assertEqual(store.rules, store.paths.humaneness_rules)
            self.assertEqual(store.kb, store.paths.kb_index_state)
            self.assertEqual(store.style, store.paths.state_human_style)
            self.assertFalse(data_dir.exists())

    def test_reexports_existing_atomic_writer(self):
        self.assertIs(_atomic_write_json, state_atomic_write_json)

    def test_existing_store_schemas_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = StateStore(root)

            store.time.save({"umo": 100.0})
            store.persona.save(
                {"umo": {"emotion": "neutral", "intensity": 0.5, "ts": 100.0}}
            )
            life = LifeState(
                date="2026-09-11",
                holiday="无",
                schedule_summary="日常",
                timeline=[TimelineEntry("08:00-09:00", "早餐")],
                status="ok",
                generated_at="2026-09-11 08:00",
            )
            store.life.set(life)

            self.assertEqual(
                json.loads(store.paths.time_state.read_text(encoding="utf-8")),
                {
                    "version": 3,
                    "last_seen": {"umo": 100.0},
                    "first_seen": {},
                    "user_seen": {},
                    "ai_seen": {},
                },
            )
            self.assertEqual(
                json.loads(store.paths.persona_state.read_text(encoding="utf-8")),
                {
                    "version": 1,
                    "emotions": {
                        "umo": {"emotion": "neutral", "intensity": 0.5, "ts": 100.0}
                    },
                },
            )
            self.assertEqual(
                json.loads(store.paths.life_state.read_text(encoding="utf-8")),
                life.to_dict(),
            )

    def test_flush_domains_isolates_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            seen = []

            def good(payload):
                seen.append(payload)

            def bad(payload):
                seen.append(("bad", payload))
                raise RuntimeError("one domain failed")

            result = store.flush_domains(
                callbacks={"good": good, "bad": bad},
                payloads={"good": {"value": 1}, "bad": {"value": 2}},
            )

            self.assertEqual(result, {"good": True, "bad": False})
            self.assertEqual(seen, [{"value": 1}, ("bad", {"value": 2})])

    def test_flush_domains_does_not_invent_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            target = store.paths.stats
            result = store.flush_domains(payloads={"stats": {"count": 1}})
            self.assertEqual(result, {"stats": False})
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
