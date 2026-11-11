# -*- coding: utf-8 -*-
"""Readonly API validation, growth wiring, and packaging boundary contracts."""
import ast
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from humanizer_core.inject_pipeline import INJECTORS
from humanizer_core.metrics import INJECT_KEYS
from web_api import HumanizerWebAPI, _load_config_schema, _validate_config_value

ROOT = Path(__file__).resolve().parent.parent


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code


def _fake_host_web(query):
    """Stand-in for the host's astrbot.api.web module, used only per call."""
    module = types.ModuleType("astrbot.api.web")
    module.request = SimpleNamespace(query=query)
    module.json_response = lambda payload, status_code=200: _Response(payload, status_code)
    return module


class TestGrowthAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.diary_calls = []
        self.api = HumanizerWebAPI(SimpleNamespace(
            web_growth_state=lambda scope: self.calls.append(('state', scope)) or {'scopes': []},
            web_growth_events=lambda scope, limit: self.calls.append(('events', scope, limit)) or [],
            web_growth_diary=lambda scope, days, tz: self.diary_calls.append((scope, days, tz)) or {'days': []},
        ))

    async def _call(self, method, query):
        fake = _fake_host_web(query)
        with patch.dict(sys.modules, {'astrbot.api.web': fake}):
            return await getattr(self.api, method)()

    async def test_invalid_scope_is_rejected_before_facade(self):
        for scope in ('../x', 'a' * 65, 'A' * 64, '%2e%2e', ['a']):
            response = await self._call('get_growth_state', {'scope': scope})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.calls, [])

    async def test_limit_is_bounded_before_facade(self):
        for limit in ('0', '101', '-1', 'NaN', '10000', 5):
            response = await self._call('get_growth_events', {'limit': limit})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.calls, [])

    async def test_summary_never_selects_first_scope(self):
        response = await self._call('get_growth_state', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, [('state', '')])
        self.assertEqual(response.payload['ok'], True)
        self.assertEqual(response.payload['state'], {'scopes': []})

    async def test_events_require_explicit_scope(self):
        for query in ({}, {'scope': ''}, {'scope': None}):
            response = await self._call('get_growth_events', query)
            self.assertEqual(response.status_code, 400, query)
        self.assertEqual(self.calls, [], "an empty scope must not reach the facade")

    async def test_events_use_explicit_scope(self):
        response = await self._call('get_growth_events', {'scope': 'a' * 64, 'limit': '100'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, [('events', 'a' * 64, 100)])

    async def test_diary_requires_explicit_scope(self):
        for query in ({}, {'scope': ''}, {'scope': None}, {'scope': '../x'}):
            response = await self._call('get_growth_diary', query)
            self.assertEqual(response.status_code, 400, query)
        self.assertEqual(self.diary_calls, [])

    async def test_diary_bounds_before_facade(self):
        for query in (
            {'scope': 'a' * 64, 'days': '0'},
            {'scope': 'a' * 64, 'days': '31'},
            {'scope': 'a' * 64, 'days': 'abc'},
            {'scope': 'a' * 64, 'tz_offset_minutes': '841'},
            {'scope': 'a' * 64, 'tz_offset_minutes': '-841'},
            {'scope': 'a' * 64, 'tz_offset_minutes': 'x'},
        ):
            response = await self._call('get_growth_diary', query)
            self.assertEqual(response.status_code, 400, query)
        self.assertEqual(self.diary_calls, [])

    async def test_diary_uses_validated_params(self):
        response = await self._call(
            'get_growth_diary',
            {'scope': 'a' * 64, 'days': '7', 'tz_offset_minutes': '-480'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.diary_calls, [('a' * 64, 7, -480)])
        self.assertEqual(response.payload['ok'], True)
        self.assertEqual(response.payload['diary'], {'days': []})

    async def test_diary_error_does_not_leak_details(self):
        def fail(scope, days, tz):
            raise OSError('private path and account')

        self.api.plugin.web_growth_diary = fail
        response = await self._call('get_growth_diary', {'scope': 'a' * 64})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private', json.dumps(response.payload, ensure_ascii=False))

    async def test_error_does_not_leak_exception_details(self):
        def fail(scope):
            raise OSError('private path and account')

        self.api.plugin.web_growth_state = fail
        response = await self._call('get_growth_state', {})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private', json.dumps(response.payload, ensure_ascii=False))


class TestGrowthConfig(unittest.TestCase):
    def test_bounds_are_exposed_and_validated(self):
        schema = _load_config_schema()['growth']['items']
        for key, valid, invalid in (
            ('identity_budget', 600, 901),
            ('situation_budget', 260, 401),
            ('tick_minutes', 5, 0),
            ('max_events', 20000, 99),
            ('max_events', 150000, 150001),
        ):
            item = schema[key]
            self.assertIsNone(_validate_config_value(item, valid))
            self.assertIsNotNone(_validate_config_value(item, invalid))
            self.assertIn('min', item)
            self.assertIn('max', item)


class TestGrowthWiring(unittest.TestCase):
    """Source-level pinning: no new loop, no tool, no fallback that persists context."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / 'main.py').read_text(encoding='utf-8')
        cls.tree = ast.parse(cls.src)

    def test_existing_injector_relative_order_is_unchanged(self):
        names = [spec.name for spec in INJECTORS]
        self.assertEqual(names[:2], ['growth', 'time'])
        self.assertEqual(names[2], 'growth_state')
        self.assertEqual(
            [n for n in names if not n.startswith('growth')],
            ['time', 'discipline', 'emotion', 'rules', 'lang', 'style', 'examples'],
        )
        for spec in INJECTORS:
            self.assertIn(spec.record_key, INJECT_KEYS)

    def test_no_new_loop_or_llm_tool(self):
        loops = sum(
            1 for node in ast.walk(self.tree)
            if isinstance(node, ast.While)
            and isinstance(node.test, ast.Constant) and node.test.value is True
        )
        self.assertEqual(loops, 3, '不得新增后台循环')
        self.assertNotIn('add_llm_tools', self.src)

    def test_growth_hooks_are_wired_lazily(self):
        self.assertIn('growth.observe_delivery(event)', self.src)
        self.assertIn('await asyncio.to_thread(growth.tick, time.time())', self.src)
        self.assertIn('await asyncio.to_thread(growth.close)', self.src)
        self.assertIn('getattr(self, "_growth", None)', self.src)

    def test_situation_injection_requires_temp_part_support(self):
        self.assertIn('callable(getattr(TextPart, "mark_as_temp", None))', self.src)

    def test_schema_defaults_match_runtime_defaults(self):
        from humanizer_core.growth_engine import DEFAULTS

        schema = json.loads((ROOT / '_conf_schema.json').read_text(encoding='utf-8'))
        self.assertEqual(
            {k: v['default'] for k, v in schema['growth']['items'].items()}, DEFAULTS
        )


class TestManifestPackaging(unittest.TestCase):
    def test_stale_assets_remain_locally_but_not_in_package(self):
        spec = importlib.util.spec_from_file_location(
            'growth_package_test', ROOT / 'package_plugin.py'
        )
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            console = root / 'pages/humanizer-console'
            assets = console / 'assets'
            assets.mkdir(parents=True)
            (assets / 'active.js').write_text('new', encoding='utf-8')
            (assets / 'active.css').write_text('style', encoding='utf-8')
            stale = assets / 'old.js'
            stale.write_text('old', encoding='utf-8')
            (console / 'index.html').write_text(
                '<script src="./assets/active.js"></script>'
                '<link rel="stylesheet" href="./assets/active.css">',
                encoding='utf-8',
            )
            manifest = console / '.vite/manifest.json'
            manifest.parent.mkdir()
            manifest.write_text(
                json.dumps({'index.html': {'file': 'assets/active.js', 'css': ['assets/active.css']}}),
                encoding='utf-8',
            )
            (root / 'events.jsonl').write_text('private', encoding='utf-8')
            with patch.object(package, 'PLUGIN_DIR', root):
                files, _excluded = package.collect_files()
                names = [p.relative_to(root).as_posix() for p in files]
                self.assertIn('pages/humanizer-console/assets/active.js', names)
                self.assertNotIn('pages/humanizer-console/assets/old.js', names)
                self.assertNotIn('events.jsonl', names)
                self.assertTrue(stale.is_file(), 'packaging must never delete stale files')

    def test_cross_generation_index_is_rejected(self):
        spec = importlib.util.spec_from_file_location(
            'growth_package_crossgen', ROOT / 'package_plugin.py'
        )
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            console = root / 'pages/humanizer-console'
            (console / 'assets').mkdir(parents=True)
            (console / 'assets/old-entry.js').write_text('old build', encoding='utf-8')
            (console / 'index.html').write_text(
                '<script src="./assets/new-entry.js"></script>', encoding='utf-8'
            )
            manifest = console / '.vite/manifest.json'
            manifest.parent.mkdir()
            manifest.write_text(
                json.dumps({'index.html': {'file': 'assets/old-entry.js'}}), encoding='utf-8'
            )
            with patch.object(package, 'PLUGIN_DIR', root):
                with self.assertRaises(package.PackageError):
                    package._current_console_assets()
