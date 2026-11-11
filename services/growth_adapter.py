# -*- coding: utf-8 -*-
"""Optional request/confirmed-delivery adapter; never changes sending policy.

Only metadata reaches the engine. UMO and resolved persona are transient scope
inputs, not event fields. A failed persona resolution disables this request.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

from humanizer_core.growth_engine import normalize_config
from humanizer_core.growth_service import GrowthService


def _friend_message_types() -> frozenset[str]:
    """Resolve the host's private-chat enum only if the framework is already up.

    Importing ``astrbot.core`` here would initialize the framework and, without
    ASTRBOT_ROOT, make it write ``data/cmd_config.json`` under the current
    directory (observed leak). The literal stays as the documented fallback.
    """
    values = {"FriendMessage"}
    if "astrbot" in sys.modules:
        try:
            from astrbot.core.platform.message_type import MessageType  # type: ignore

            values.add(str(MessageType.FRIEND_MESSAGE.value))
        except Exception:
            pass
    return frozenset(values)


_FRIEND_TYPES = _friend_message_types()


class GrowthAdapter:
    def __init__(self, data_dir: Path | None, config_getter: Callable, context):
        self._config_getter = config_getter
        self._context = context
        self.service = GrowthService(data_dir, self._config())
        self._last_tick = 0.0

    def _config(self) -> dict:
        try:
            return normalize_config(self._config_getter())
        except Exception:
            return normalize_config({})

    def _active(self) -> bool:
        cfg = self._config()
        self.service.configure(cfg)
        return cfg['enabled']

    @staticmethod
    def _private(event) -> bool:
        # CronMessageEvent.message_obj.type is always FRIEND_MESSAGE. The UMO,
        # not is_private_chat(), is authoritative for synthesized events too.
        try:
            parts = str(event.unified_msg_origin).split(':', 2)
            return len(parts) == 3 and parts[1] in _FRIEND_TYPES and bool(parts[0] and parts[2])
        except Exception:
            return False

    @staticmethod
    def _get(event, key, default=None):
        try:
            value = event.get_extra(key)
            return default if value is None else value
        except Exception:
            return getattr(event, key, default)

    @staticmethod
    def _set(event, key, value):
        try:
            event.set_extra(key, value)
        except Exception:
            setattr(event, key, value)

    @classmethod
    def _turn_id(cls, event) -> str:
        value = cls._get(event, '_humanizer_growth_turn')
        if not value:
            span = getattr(getattr(event, 'trace', None), 'span_id', None)
            value = hashlib.sha256(str(span or uuid.uuid4().hex).encode()).hexdigest()
            cls._set(event, '_humanizer_growth_turn', value)
        return value

    async def prepare(self, event, req) -> tuple[str, str]:
        """Bind once per request event, count a user turn, render cached facts."""
        if not self._active() or not self._private(event):
            return '', ''
        try:
            self._set(event, '_humanizer_growth_scope', None)
            conversation = getattr(req, 'conversation', None)
            if conversation is None:
                return '', ''
            manager = self._context.persona_manager
            cfg = self._context.get_config(umo=event.unified_msg_origin) or {}
            selected, persona, _, special = await manager.resolve_selected_persona(
                umo=event.unified_msg_origin,
                conversation_persona_id=conversation.persona_id,
                platform_name=event.get_platform_name(),
                provider_settings=cfg.get('provider_settings', {}),
            )
            # Include content identity too: editing a persona in place must not
            # silently reuse a different personality's observations.
            persona_prompt = persona.get('prompt', '') if isinstance(persona, Mapping) else ''
            content_key = hashlib.sha256(str(persona_prompt).encode('utf-8')).hexdigest()
            scope = hashlib.sha256(json.dumps(
                [str(event.unified_msg_origin), selected, bool(special), content_key], ensure_ascii=True,
            ).encode('utf-8')).hexdigest()
            self._set(event, '_humanizer_growth_scope', scope)
            turn = self._turn_id(event)
            now = time.time()
            if event.get_platform_name() != 'cron' and not self._get(event, 'humanizer_proactive', False):
                # Every private inbound message counts as one user turn; an
                # image-only message records length 0 and exposes no content.
                text = str(getattr(event, 'message_str', '') or '').strip()
                await asyncio.to_thread(self.service.note_user, scope, 'user:' + turn, now, min(len(text), 1000000))
            return await asyncio.to_thread(self.service.render, scope, now)
        except Exception:
            # Do not guess an "unknown" persona or combine unrelated scopes.
            self._set(event, '_humanizer_growth_scope', None)
            return '', ''

    def note_bot(self, event, text_length: int, source: str = 'reply') -> bool:
        if not self._active() or not self._private(event):
            return False
        scope = self._get(event, '_humanizer_growth_scope')
        if not scope or type(text_length) is not int or text_length <= 0:
            return False
        try:
            return self.service.note_bot(scope, 'bot:' + self._turn_id(event), time.time(), min(text_length, 1000000), source)
        except Exception:
            return False

    def observe_delivery(self, event) -> None:
        """Observe successful send returns, including the split-bubble path.

        after_message_sent also runs after some send failures and is skipped for
        a cleared split chain. Do not use it as an acknowledgement. Each turn is
        counted once; text_length is the first acknowledged text fragment only.
        """
        if not self._active() or not self._private(event):
            return
        if not self._get(event, '_humanizer_growth_scope'):
            return
        if self._get(event, '_humanizer_growth_observed', False):
            return
        original_send = event.send

        async def observed_send(message, *args, **kwargs):
            outcome = await original_send(message, *args, **kwargs)
            try:
                # Cron send can return normally after a False transport result.
                is_cron = bool(self._get(event, 'humanizer_proactive', False)) or event.get_platform_name() == 'cron'
                if outcome is False or (is_cron and not getattr(event, '_has_send_oper', False)):
                    return outcome
                chain = getattr(message, 'chain', ()) or ()
                length = sum(len(str(getattr(comp, 'text', '') or '')) for comp in chain)
                if length:
                    await asyncio.to_thread(self.note_bot, event, length, 'proactive' if is_cron else 'reply')
            except Exception:
                pass
            return outcome

        event.send = observed_send
        self._set(event, '_humanizer_growth_observed', True)

    def tick(self, now: float) -> None:
        if not self._active():
            return
        interval = self.service.config['tick_minutes'] * 60
        if now - self._last_tick >= interval:
            self.service.tick(now)
            self._last_tick = now

    def snapshot(self, scope_id: str = '') -> dict:
        self.service.configure(self._config())
        return self.service.snapshot(scope_id)

    def events(self, scope_id: str = '', limit: int = 50) -> list:
        self.service.configure(self._config())
        return self.service.events(scope_id, limit)

    def close(self) -> None:
        self.service.close()
