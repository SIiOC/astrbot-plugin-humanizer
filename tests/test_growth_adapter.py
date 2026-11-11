# -*- coding: utf-8 -*-
"""Behavioral boundary tests for optional request and delivery wiring."""
import asyncio
import ast
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from services.growth_adapter import GrowthAdapter
from humanizer_core.inject_pipeline import INJECTORS
from humanizer_core.metrics import INJECT_KEYS

ROOT = Path(__file__).resolve().parent.parent


class Event:
    def __init__(self, umo='qq:FriendMessage:example', platform='aiocqhttp', span='turn-one', text='private body'):
        self.unified_msg_origin = umo
        self.message_str = text
        self.trace = SimpleNamespace(span_id=span)
        self.extra = {}
        self.platform = platform
        self.sent = []
        self.fail = False
        self.result = SimpleNamespace(chain=[])

    def get_platform_name(self):
        return self.platform

    def get_extra(self, key):
        return self.extra.get(key)

    def set_extra(self, key, value):
        self.extra[key] = value

    def get_result(self):
        return self.result

    async def send(self, chain):
        if self.fail:
            raise OSError('test failure')
        self.sent.append(chain)
        self._has_send_oper = True


def chain(text):
    return SimpleNamespace(chain=[SimpleNamespace(text=text)])


class TestGrowthAdapter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'plugin'
        self.cfg = {'enabled': True}
        self.persona = ['role-a', {'prompt': 'configured role A'}, None, False]
        self.resolve = AsyncMock(side_effect=lambda **kwargs: tuple(self.persona))
        self.context = SimpleNamespace(
            persona_manager=SimpleNamespace(resolve_selected_persona=self.resolve),
            get_config=lambda **kw: {},
        )
        self.adapter = GrowthAdapter(self.root, lambda: self.cfg, self.context)
        self.req = SimpleNamespace(conversation=SimpleNamespace(persona_id='role-a'))

    async def asyncTearDown(self):
        self.adapter.close()
        self.temp.cleanup()

    async def test_disabled_never_resolves_persona_or_touches_paths(self):
        self.cfg['enabled'] = False
        event = Event()
        with patch.object(Path, 'open', side_effect=AssertionError('IO')), patch.object(Path, 'iterdir', side_effect=AssertionError('IO')):
            self.assertEqual(await self.adapter.prepare(event, self.req), ('', ''))
            self.adapter.observe_delivery(event)
            self.assertFalse(self.adapter.note_bot(event, 10))
            self.adapter.tick(300)
            self.assertEqual(self.adapter.snapshot()['scopes'], [])
        self.resolve.assert_not_awaited()
        self.assertEqual(event.extra, {})
        self.assertFalse(self.root.exists())

    async def test_request_repetition_and_split_delivery_count_once(self):
        event = Event()
        first = await self.adapter.prepare(event, self.req)
        self.assertTrue(first[0])
        await self.adapter.prepare(event, self.req)
        scope = event.extra['_humanizer_growth_scope']
        self.adapter.observe_delivery(event)
        self.adapter.observe_delivery(event)
        await event.send(chain('first fragment'))
        await event.send(chain('second fragment'))
        state = self.adapter.snapshot(scope)
        self.assertEqual(state['user_turns'], 1)
        self.assertEqual(state['bot_turns'], 1)
        self.assertEqual(state['stage'], 0)
        rows = self.adapter.events(scope)
        bot = next(r for r in rows if r['type'] == 'bot_turn')
        self.assertEqual(bot['text_length'], len('first fragment'))
        data = (self.root / 'growth' / scope / 'events.jsonl').read_text(encoding='utf-8')
        self.assertNotIn(event.message_str, data)
        self.assertNotIn(event.unified_msg_origin, data)
        self.assertNotIn('configured role A', data)
        self.assertNotIn('first fragment', data)

    async def test_failed_send_has_no_bot_record_and_retry_can_succeed(self):
        event = Event()
        await self.adapter.prepare(event, self.req)
        self.adapter.observe_delivery(event)
        event.fail = True
        with self.assertRaises(OSError):
            await event.send(chain('not sent'))
        scope = event.extra['_humanizer_growth_scope']
        self.assertEqual(self.adapter.snapshot(scope)['bot_turns'], 0)
        event.fail = False
        await event.send(chain('acknowledged'))
        self.assertEqual(self.adapter.snapshot(scope)['bot_turns'], 1)

    async def test_cron_group_and_unknown_session_are_rejected(self):
        for umo in ('qq:GroupMessage:group', 'unknown', 'qq:Unknown:123'):
            event = Event(umo=umo, platform='cron')
            self.assertEqual(await self.adapter.prepare(event, self.req), ('', ''))
            self.adapter.observe_delivery(event)
        self.resolve.assert_not_awaited()
        self.assertFalse(self.root.exists())

    async def test_cron_does_not_count_synthetic_user_and_failed_transport(self):
        event = Event(platform='cron')
        await self.adapter.prepare(event, self.req)
        # A new proactive event has no user observation to inject or persist.
        self.assertFalse(self.root.exists())
        async def false_send(message):
            return False
        event.send = false_send
        self.adapter.observe_delivery(event)
        self.assertFalse(await event.send(chain('not delivered')))
        scope = event.extra['_humanizer_growth_scope']
        self.assertEqual(self.adapter.snapshot(scope)['event_count'], 0)

    async def test_proactive_marker_survives_real_platform_substitution(self):
        event = Event(platform='aiocqhttp')
        event.extra['humanizer_proactive'] = True
        await self.adapter.prepare(event, self.req)
        async def silent_failure(message):
            return None
        event.send = silent_failure
        self.adapter.observe_delivery(event)
        await event.send(chain('not delivered'))
        scope = event.extra['_humanizer_growth_scope']
        self.assertEqual(self.adapter.snapshot(scope)['bot_turns'], 0)
        event._has_send_oper = True
        await event.send(chain('confirmed'))
        rows = self.adapter.events(scope)
        bot = next(r for r in rows if r['type'] == 'bot_turn')
        self.assertEqual(bot['source'], 'proactive')

    async def test_missing_conversation_clears_previous_binding(self):
        event = Event()
        await self.adapter.prepare(event, self.req)
        self.assertTrue(event.extra['_humanizer_growth_scope'])
        await self.adapter.prepare(event, SimpleNamespace())
        self.assertIsNone(event.extra['_humanizer_growth_scope'])
        self.assertFalse(self.adapter.note_bot(event, 5))

    async def test_image_only_private_message_still_counts_as_one_turn(self):
        event = Event(text='')
        await self.adapter.prepare(event, self.req)
        scope = event.extra['_humanizer_growth_scope']
        self.assertEqual(self.adapter.snapshot(scope)['user_turns'], 1)
        rows = self.adapter.events(scope)
        turn = next(r for r in rows if r['type'] == 'user_turn')
        self.assertEqual(turn['text_length'], 0)

    async def test_private_chat_matches_host_enum_with_literal_fallback(self):
        from services.growth_adapter import _FRIEND_TYPES

        self.assertIn('FriendMessage', _FRIEND_TYPES)
        self.assertTrue(self.adapter._private(Event(umo='qq:FriendMessage:1')))
        self.assertFalse(self.adapter._private(Event(umo='qq:GroupMessage:1')))
        self.assertFalse(self.adapter._private(Event(umo='qq:friendmessage:1')))

    async def test_persona_and_content_changes_separate_scopes(self):
        one = Event(span='one')
        await self.adapter.prepare(one, self.req)
        self.persona[0] = 'role-b'
        two = Event(span='two')
        await self.adapter.prepare(two, self.req)
        self.persona[1] = {'prompt': 'edited role B'}
        three = Event(span='three')
        await self.adapter.prepare(three, self.req)
        scopes = [e.extra['_humanizer_growth_scope'] for e in (one, two, three)]
        self.assertEqual(len(set(scopes)), 3)
        self.assertEqual(len(self.adapter.snapshot()['scopes']), 3)
        self.assertEqual(self.adapter.snapshot()['scope_id'], '')

    async def test_resolution_failure_does_not_guess_shared_scope(self):
        self.resolve.side_effect = RuntimeError('no persona')
        event = Event()
        self.assertEqual(await self.adapter.prepare(event, self.req), ('', ''))
        self.assertFalse(self.adapter.note_bot(event, 10))
        self.assertFalse(self.root.exists())

    async def test_disable_after_prepare_disables_observed_write(self):
        event = Event()
        await self.adapter.prepare(event, self.req)
        self.adapter.observe_delivery(event)
        self.cfg['enabled'] = False
        await event.send(chain('transport still works'))
        self.assertEqual(len(event.sent), 1)
        self.assertEqual(self.adapter.snapshot()['scopes'], [])
        self.cfg['enabled'] = True
        scope = event.extra['_humanizer_growth_scope']
        self.assertEqual(self.adapter.snapshot(scope)['bot_turns'], 0)

    async def test_core_write_error_never_changes_transport_result(self):
        event = Event()
        await self.adapter.prepare(event, self.req)
        self.adapter.observe_delivery(event)
        with patch.object(self.adapter.service, 'note_bot', side_effect=OSError('disk')):
            await event.send(chain('reply'))
        self.assertEqual(len(event.sent), 1)

    async def test_scope_without_conversation_is_not_inferred(self):
        self.assertEqual(await self.adapter.prepare(Event(), SimpleNamespace()), ('', ''))
        self.assertFalse(self.root.exists())


class TestGrowthWiring(unittest.TestCase):
    def test_registry_preserves_existing_relative_order_and_metrics(self):
        self.assertEqual([s.name for s in INJECTORS if not s.name.startswith('growth')],
                         ['time', 'discipline', 'emotion', 'rules', 'lang', 'style', 'examples'])
        for spec in INJECTORS:
            self.assertIn(spec.record_key, INJECT_KEYS)

    def test_no_new_background_loop_or_tool(self):
        tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8'))
        self.assertEqual(sum(isinstance(n, ast.While) and isinstance(n.test, ast.Constant) and n.test.value is True for n in ast.walk(tree)), 3)
        src = (ROOT / 'main.py').read_text(encoding='utf-8')
        self.assertNotIn('add_llm_tools', src)
        self.assertIn('growth.observe_delivery(event)', src)
        self.assertIn('await asyncio.to_thread(growth.tick, time.time())', src)

    def test_schema_defaults_match_runtime_defaults(self):
        from humanizer_core.growth_engine import DEFAULTS
        schema = json.loads((ROOT / '_conf_schema.json').read_text(encoding='utf-8'))
        self.assertEqual({k: v['default'] for k, v in schema['growth']['items'].items()}, DEFAULTS)

    def test_temp_context_guard_exists(self):
        src = (ROOT / 'main.py').read_text(encoding='utf-8')
        self.assertIn('callable(getattr(TextPart, "mark_as_temp", None))', src)
