# -*- coding: utf-8 -*-
"""Tests for the dependency-free async LLM call layer."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.llm_calls import (
    LLMCallSite,
    LLMTarget,
    _requires_chat_provider_id,
    invoke_llm,
    join_sections,
)


class TestJoinSections(unittest.TestCase):
    """v4.0：深度改写两处 prompt 拼接规则下沉后的行为契约。"""

    def test_nonempty_parts_joined_with_blank_line(self):
        self.assertEqual(join_sections("a", "b", "c"), "a\n\nb\n\nc")

    def test_falsy_parts_skipped_without_stray_blanks(self):
        self.assertEqual(join_sections("a", "", None, "b"), "a\n\nb")
        self.assertEqual(join_sections("a", "", None), "a")

    def test_empty_base_keeps_blank_line_prefix(self):
        # 复刻内联语义的关键边界：空 base + 非空 part 仍产生 \n\n 前缀
        # （system 后缀拼进 SYSTEM_PROMPT 的既有分隔行为，禁止 strip 化）
        self.assertEqual(join_sections("", "state"), "\n\nstate")


class TestInvokeLLM(unittest.TestCase):
    def test_builds_expected_kwargs_and_omits_absent_options(self):
        calls = []

        async def generate(**kwargs):
            calls.append(kwargs)
            return "ok"

        result = asyncio.run(
            invoke_llm(
                generate,
                prompt="request",
                provider_id="provider-a",
                model="model-a",
            )
        )

        self.assertEqual(result, "ok")
        self.assertEqual(
            calls,
            [{
                "chat_provider_id": "provider-a",
                "prompt": "request",
                "model": "model-a",
            }],
        )

    def test_none_provider_omits_chat_provider_id_keyword(self):
        """provider_id=None → 完全不传 chat_provider_id 键。

        对应旧代码 kwargs 不组装该键的调用形态（provider 自选会话模型），
        以及 text_chat 直调回退——意外关键字会漏进请求 payload。
        """
        calls = []

        async def generate(**kwargs):
            calls.append(kwargs)
            return "ok"

        asyncio.run(
            invoke_llm(generate, prompt="request", provider_id=None)
        )

        self.assertEqual(calls, [{"prompt": "request"}])
        self.assertNotIn("chat_provider_id", calls[0])

    def test_none_provider_raises_when_required_no_default(self):
        """v4.28：chat_provider_id 必填（无默认）而 provider_id=None → 边界 ValueError。

        旧行为会省略该键，让宿主在深层抛 `TypeError: missing 1 required
        keyword-only argument`——难以定位。此处必须在边界抛出可诊断错误。
        """

        async def generate(chat_provider_id, prompt, model=None):
            return "ok"

        with self.assertRaises(ValueError) as caught:
            asyncio.run(invoke_llm(generate, prompt="request", provider_id=None))
        self.assertIn("chat_provider_id", str(caught.exception))

    def test_none_provider_omits_keyword_when_parameter_has_default(self):
        """chat_provider_id 有默认值（旧框架形态）→ 照旧省略键，不抛错。"""

        calls = []

        async def generate(prompt, chat_provider_id=None):
            calls.append(chat_provider_id)
            return "ok"

        result = asyncio.run(invoke_llm(generate, prompt="request", provider_id=None))
        self.assertEqual(result, "ok")
        self.assertEqual(calls, [None])

    def test_none_provider_omits_keyword_for_kwargs_tail(self):
        """**kwargs 尾（text_chat 直调回退形态）→ 检测为"非必填"，照旧省略键。"""

        calls = []

        async def generate(**kwargs):
            calls.append(kwargs)
            return "ok"

        asyncio.run(invoke_llm(generate, prompt="request", provider_id=None))
        self.assertEqual(calls, [{"prompt": "request"}])
        self.assertNotIn("chat_provider_id", calls[0])

    def test_requires_chat_provider_id_signature_states(self):
        """_requires_chat_provider_id 三态：无默认必填 / 有默认 / 无该参数。"""

        async def required(chat_provider_id, prompt):
            return "ok"

        async def optional(chat_provider_id=None, prompt=""):
            return "ok"

        async def absent(**kwargs):
            return "ok"

        def positional_with_default(prompt, chat_provider_id="x"):
            return "ok"

        self.assertTrue(_requires_chat_provider_id(required))
        self.assertFalse(_requires_chat_provider_id(optional))
        self.assertFalse(_requires_chat_provider_id(absent))
        self.assertFalse(_requires_chat_provider_id(positional_with_default))

    def test_positive_provider_still_sent_when_required(self):
        """解析出真实 provider 时照常传键（修复路径的正向保证）。"""

        calls = []

        async def generate(chat_provider_id, prompt, model=None):
            calls.append((chat_provider_id, prompt, model))
            return "ok"

        asyncio.run(
            invoke_llm(generate, prompt="request", provider_id="provider-a")
        )
        self.assertEqual(calls, [("provider-a", "request", None)])

    def test_passes_system_prompt_when_supported(self):
        calls = []

        async def generate(**kwargs):
            calls.append(kwargs)
            return "ok"

        asyncio.run(
            invoke_llm(
                generate,
                prompt="request",
                provider_id="provider-a",
                system_prompt="instruction",
                supports_system_prompt=True,
            )
        )

        self.assertEqual(calls[0]["system_prompt"], "instruction")
        self.assertEqual(calls[0]["prompt"], "request")

    def test_old_signature_gets_system_prompt_in_prompt(self):
        calls = []

        async def generate(chat_provider_id, prompt, model=None):
            calls.append((chat_provider_id, prompt, model))
            return "ok"

        result = asyncio.run(
            invoke_llm(
                generate,
                prompt="request",
                provider_id="provider-a",
                model="model-a",
                system_prompt="instruction",
            )
        )

        self.assertEqual(result, "ok")
        self.assertEqual(calls, [("provider-a", "instruction\n\nrequest", "model-a")])

    def test_explicit_old_signature_capability_omits_system_kwarg(self):
        calls = []

        async def generate(**kwargs):
            calls.append(kwargs)
            return "ok"

        asyncio.run(
            invoke_llm(
                generate,
                prompt="request",
                provider_id="provider-a",
                system_prompt="instruction",
                supports_system_prompt=False,
            )
        )

        self.assertNotIn("system_prompt", calls[0])
        self.assertEqual(calls[0]["prompt"], "instruction\n\nrequest")

    def test_prompt_prefix_only_on_fold_branch(self):
        """prompt_prefix 只在折叠分支生效（复刻改写站点的「待处理的文本：」标签）。"""
        calls = []

        async def generate(**kwargs):
            calls.append(kwargs)
            return "ok"

        # 折叠分支（不支持 system_prompt）：前缀作为分隔符替换默认 \n\n，
        # 逐字复刻旧内联 `SYSTEM + "\n\n待处理的文本：\n" + body`
        asyncio.run(
            invoke_llm(
                generate,
                prompt="BODY",
                provider_id="provider-a",
                system_prompt="SYS",
                supports_system_prompt=False,
                prompt_prefix="\n\n待处理的文本：\n",
            )
        )
        self.assertEqual(calls[0]["prompt"], "SYS\n\n待处理的文本：\nBODY")

        # 原生分支（支持 system_prompt）：前缀必须被忽略（system 单独走关键字）
        calls.clear()
        asyncio.run(
            invoke_llm(
                generate,
                prompt="BODY",
                provider_id="provider-a",
                system_prompt="SYS",
                supports_system_prompt=True,
                prompt_prefix="\n\n待处理的文本：\n",
            )
        )
        self.assertEqual(calls[0]["system_prompt"], "SYS")
        self.assertEqual(calls[0]["prompt"], "BODY")

    def test_positive_timeout_propagates_timeout_error(self):
        async def generate(**kwargs):
            await asyncio.sleep(0.05)
            return "never"

        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(
                invoke_llm(
                    generate,
                    prompt="request",
                    provider_id="provider-a",
                    timeout=0.001,
                )
            )

    def test_cancellation_propagates_and_cancels_underlying_call(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def generate(**kwargs):
            started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async def run_test():
            task = asyncio.create_task(
                invoke_llm(
                    generate,
                    prompt="request",
                    provider_id="provider-a",
                    timeout=30,
                )
            )
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(cancelled.is_set())

        asyncio.run(run_test())

    def test_none_and_nonpositive_timeout_do_not_call_wait_for(self):
        async def generate(**kwargs):
            return "ok"

        with patch("humanizer_core.llm_calls.asyncio.wait_for") as wait_for:
            for timeout in (None, 0, -1):
                self.assertEqual(
                    asyncio.run(
                        invoke_llm(
                            generate,
                            prompt="request",
                            provider_id="provider-a",
                            timeout=timeout,
                        )
                    ),
                    "ok",
                )
            wait_for.assert_not_called()

    def test_exceptions_propagate_unchanged(self):
        expected = RuntimeError("provider failed")

        async def generate(**kwargs):
            raise expected

        with self.assertRaises(RuntimeError) as caught:
            asyncio.run(
                invoke_llm(
                    generate,
                    prompt="request",
                    provider_id="provider-a",
                )
            )
        self.assertIs(caught.exception, expected)

    def test_call_site_delegates_with_default_timeout_and_capability(self):
        calls = []

        async def generate(**kwargs):
            calls.append(kwargs)
            return "ok"

        site = LLMCallSite(timeout=5, supports_system_prompt=True)
        result = asyncio.run(
            site.invoke(
                generate,
                prompt="request",
                provider_id="provider-a",
                system_prompt="instruction",
            )
        )

        self.assertEqual(result, "ok")
        self.assertEqual(calls, [{
            "chat_provider_id": "provider-a",
            "prompt": "request",
            "system_prompt": "instruction",
        }])

    def test_llm_target_is_small_immutable_value(self):
        target = LLMTarget("provider-a", "model-a")
        self.assertEqual(target.provider_id, "provider-a")
        self.assertEqual(target.model, "model-a")
        with self.assertRaises(AttributeError):
            target.model = "other"


if __name__ == "__main__":
    unittest.main()
