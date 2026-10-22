# -*- coding: utf-8 -*-
"""
llm_target 解析逻辑测试：深度改写目标（provider_id, model）的解析。

用 mock context（鸭子类型）验证：
- 未配置模型时跟随当前会话
- 指定模型时优先在当前 provider 内切换
- 当前 provider 不支持时在其它 provider 中查找
- 都找不到时回落当前会话模型
- 异常时安全回落
"""

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from humanizer_core.llm_target import (
    collect_models,
    parse_configured_target,
    provider_has_model,
    resolve_rewrite_target,
)


class FakeProvider:
    def __init__(self, pid: str, models: list[str]):
        self._pid = pid
        self._models = models

    def meta(self):
        return type("Meta", (), {"id": self._pid})()

    async def get_models(self):
        return self._models


class FakeContext:
    """模拟 AstrBot Context 的鸭子类型实现。"""

    def __init__(self, current_pid: str, providers: list[FakeProvider]):
        self.current_pid = current_pid
        self.providers = providers

    async def get_current_chat_provider_id(self, umo: str) -> str:
        return self.current_pid

    def get_all_providers(self):
        return self.providers


class TestConfiguredTarget(unittest.TestCase):
    def test_empty_config_has_no_override(self):
        ctx = FakeContext("current", [])
        self.assertEqual(parse_configured_target(ctx, ""), (None, None))

    def test_bare_model_is_model_override(self):
        ctx = FakeContext("current", [])
        self.assertEqual(parse_configured_target(ctx, "  model-a  "), (None, "model-a"))

    def test_existing_provider_id_uses_provider_default_model(self):
        class ProviderWithDefault(FakeProvider):
            def get_model(self):
                return "model-a"

        provider = ProviderWithDefault("provider-a/model-a", ["model-a"])
        ctx = FakeContext("current", [provider])
        # The provider object is deliberately resolved by the fake context below.
        ctx.get_provider_by_id = lambda value: provider if value == provider._pid else None
        self.assertEqual(
            parse_configured_target(ctx, "provider-a/model-a"),
            ("provider-a/model-a", "model-a"),
        )

    def test_missing_provider_keeps_model_suffix(self):
        ctx = FakeContext("current", [])
        ctx.get_provider_by_id = lambda value: None
        self.assertEqual(
            parse_configured_target(ctx, "missing/model-a"),
            (None, "model-a"),
        )


class TestProviderInstanceId(unittest.TestCase):
    """v4.0：main 两处逐字重复的 provider id 提取下沉后的行为契约。"""

    def _cfg_obj(self, pid):
        class P:
            provider_config = {"id": pid}

            def meta(self):
                raise AssertionError("provider_config 可读时不应触达 meta()")

        return P()

    def test_reads_provider_config_first(self):
        from humanizer_core.llm_target import provider_instance_id

        self.assertEqual(provider_instance_id(self._cfg_obj("openai-main")), "openai-main")

    def test_empty_config_id_returns_empty_without_meta_fallback(self):
        # 保留原语义细节：provider_config 可读但 id 空串 → 直接 ""（不回落 meta）
        from humanizer_core.llm_target import provider_instance_id

        self.assertEqual(provider_instance_id(self._cfg_obj("")), "")
        self.assertEqual(provider_instance_id(self._cfg_obj(None)), "")

    def test_meta_fallback_when_config_missing(self):
        from humanizer_core.llm_target import provider_instance_id

        class P:
            def meta(self):
                return type("M", (), {"id": "deepseek-x"})()

        self.assertEqual(provider_instance_id(P()), "deepseek-x")

    def test_both_paths_broken_returns_empty(self):
        from humanizer_core.llm_target import provider_instance_id

        class P:
            def meta(self):
                raise RuntimeError("boom")

        self.assertEqual(provider_instance_id(P()), "")


class TestSyncSchemaOptions(unittest.TestCase):
    """（已移除：模型选择改为 _special: select_provider 弹窗，不再写 schema options）"""


class TestCollectModels(unittest.TestCase):
    def test_collects_all_providers(self):
        providers = [
            FakeProvider("openai-main", ["gpt-4o", "gpt-4o-mini"]),
            FakeProvider("deepseek-alt", ["deepseek-chat"]),
        ]
        ctx = FakeContext("openai-main", providers)
        rows = self.run_collect(ctx)
        self.assertEqual(len(rows), 2)
        by_id = {pid: models for pid, _, models in rows}
        self.assertEqual(by_id["openai-main"], ["gpt-4o", "gpt-4o-mini"])
        self.assertEqual(by_id["deepseek-alt"], ["deepseek-chat"])

    def test_provider_meta_exception_skipped(self):
        class BadProvider(FakeProvider):
            def meta(self):
                raise RuntimeError("broken")

        providers = [BadProvider("bad", ["x"]), FakeProvider("good", ["gpt-4o"])]
        ctx = FakeContext("good", providers)
        rows = self.run_collect(ctx)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "good")

    def test_get_models_exception_empty_list(self):
        class BrokenProvider(FakeProvider):
            async def get_models(self):
                raise RuntimeError("api down")

        ctx = FakeContext("broken", [BrokenProvider("broken", ["x"])])
        rows = self.run_collect(ctx)
        self.assertEqual(rows[0][1:], ("", []))  # 模型列表为空，不中断

    def test_collect_uses_cache(self):
        calls = {"n": 0}

        class CountingProvider(FakeProvider):
            async def get_models(self):
                calls["n"] += 1
                return self._models

        ctx = FakeContext("counting", [CountingProvider("counting", ["gpt-4o"])])
        cache: dict[str, list[str]] = {}
        self.run_collect(ctx, cache)
        self.run_collect(ctx, cache)
        self.assertEqual(calls["n"], 1)

    def run_collect(self, ctx, cache=None):
        import asyncio

        return asyncio.run(collect_models(ctx, cache if cache is not None else {}))


class TestResolveRewriteTarget(unittest.TestCase):
    def setUp(self):
        self.providers = [
            FakeProvider("openai-main", ["gpt-4o", "gpt-4o-mini"]),
            FakeProvider("deepseek-alt", ["deepseek-chat", "deepseek-reasoner"]),
        ]

    def test_provider_model_hint_format(self):
        """配置为 "提供商/模型" 格式：定位指定提供商并指定模型。"""
        providers = [
            FakeProvider("xiaomi-token-plan", ["mimo-v2.5-pro", "mimo-v2.5"]),
            FakeProvider("openai-main", ["gpt-4o"]),
        ]
        ctx = FakeContext("openai-main", providers)
        pid, model = self.run_resolve(ctx, "xiaomi-token-plan/mimo-v2.5-pro")
        self.assertEqual(pid, "xiaomi-token-plan")
        self.assertEqual(model, "mimo-v2.5-pro")

    def test_provider_model_hint_not_found_falls_back(self):
        """提供商不存在：回落当前会话模型。"""
        ctx = FakeContext("openai-main", self.providers)
        pid, model = self.run_resolve(ctx, "nonexistent-provider/gpt-4o")
        self.assertEqual(pid, "openai-main")
        self.assertIsNone(model)

    def test_real_composite_id_exact_match(self):
        """真实 AstrBot provider id 是 type/model 复合格式（select_provider 存储值）：
        精确匹配完整实例 id。"""
        providers = [
            FakeProvider("xiaomi-token-plan/mimo-v2.5-pro", ["mimo-v2.5-pro", "mimo-v2.5"]),
            FakeProvider("openai-main", ["gpt-4o"]),
        ]
        ctx = FakeContext("openai-main", providers)
        pid, model = self.run_resolve(ctx, "xiaomi-token-plan/mimo-v2.5-pro")
        self.assertEqual(pid, "xiaomi-token-plan/mimo-v2.5-pro")
        self.assertEqual(model, "mimo-v2.5-pro")

    def test_real_composite_id_uses_declared_model_when_list_is_stale(self):
        """实例已锁定新模型时，不被适配器过期的 get_models() 名单拦截。"""
        class DeclaredOnlyProvider(FakeProvider):
            def get_model(self):
                return "mimo-v2.6-flash"

            async def get_models(self):
                raise AssertionError("精确实例已声明模型，不应查询过期列表")

        providers = [
            DeclaredOnlyProvider(
                "xiaomi-token-plan/mimo-v2.6-flash", ["mimo-v2.5-pro"]
            ),
            FakeProvider("openai-main", ["gpt-4o"]),
        ]
        ctx = FakeContext("openai-main", providers)
        pid, model = self.run_resolve(
            ctx, "xiaomi-token-plan/mimo-v2.6-flash"
        )
        self.assertEqual(
            (pid, model),
            ("xiaomi-token-plan/mimo-v2.6-flash", "mimo-v2.6-flash"),
        )

    def test_exact_instance_declared_mismatch_keeps_list_fallback(self):
        """实例声明不一致时仍保留原有模型列表校验和回落。"""
        class MismatchedDeclaredProvider(FakeProvider):
            def get_model(self):
                return "mimo-v2.6-pro"

        providers = [
            MismatchedDeclaredProvider(
                "xiaomi-token-plan/mimo-v2.6-flash", ["mimo-v2.6-pro"]
            ),
            FakeProvider("openai-main", ["gpt-4o"]),
        ]
        ctx = FakeContext("openai-main", providers)
        pid, model = self.run_resolve(
            ctx, "xiaomi-token-plan/mimo-v2.6-flash"
        )
        self.assertEqual((pid, model), ("openai-main", None))

    def test_real_composite_id_prefix_match(self):
        """复合 id 带不同模型后缀：按前缀找到对应提供商。"""
        providers = [
            FakeProvider("deepseek/deepseek-v4-pro", ["deepseek-v4-pro"]),
            FakeProvider("deepseek/deepseek-v4-flash", ["deepseek-v4-flash"]),
        ]
        ctx = FakeContext("deepseek/deepseek-v4-pro", providers)
        pid, model = self.run_resolve(ctx, "deepseek/deepseek-v4-flash")
        self.assertEqual(pid, "deepseek/deepseek-v4-flash")
        self.assertEqual(model, "deepseek-v4-flash")

    def test_provider_model_hint_model_not_supported(self):
        """提供商存在但模型不在其列表：回落当前会话模型。"""
        ctx = FakeContext("openai-main", self.providers)
        pid, model = self.run_resolve(ctx, "openai-main/deepseek-chat")
        self.assertEqual(pid, "openai-main")
        self.assertIsNone(model)

    def test_empty_config_follows_current(self):
        """未配置模型：跟随当前会话，不传 model。"""
        ctx = FakeContext("openai-main", self.providers)
        pid, model = self.run_resolve(ctx, "")
        self.assertEqual(pid, "openai-main")
        self.assertIsNone(model)

    def test_model_in_current_provider(self):
        """指定模型且当前 provider 支持：留在当前 provider 并指定模型。"""
        ctx = FakeContext("openai-main", self.providers)
        pid, model = self.run_resolve(ctx, "gpt-4o-mini")
        self.assertEqual(pid, "openai-main")
        self.assertEqual(model, "gpt-4o-mini")

    def test_model_in_other_provider(self):
        """当前 provider 不支持，在其它 provider 中找到。"""
        ctx = FakeContext("openai-main", self.providers)
        pid, model = self.run_resolve(ctx, "deepseek-chat")
        self.assertEqual(pid, "deepseek-alt")
        self.assertEqual(model, "deepseek-chat")

    def test_model_not_found_falls_back(self):
        """任何 provider 都不支持：回落当前会话模型（不指定 model）。"""
        ctx = FakeContext("openai-main", self.providers)
        pid, model = self.run_resolve(ctx, "nonexistent-model")
        self.assertEqual(pid, "openai-main")
        self.assertIsNone(model)

    def test_no_current_provider(self):
        """当前会话没有 provider：直接返回 (None, None)，不改写。"""
        ctx = FakeContext("", self.providers)
        pid, model = self.run_resolve(ctx, "gpt-4o")
        self.assertIsNone(pid)
        self.assertIsNone(model)

    def test_current_provider_get_models_raises(self):
        """当前 provider 的 get_models 抛异常：安全回落到其它 provider / 当前会话。"""
        class BrokenProvider(FakeProvider):
            async def get_models(self):
                raise RuntimeError("api down")

        providers = [BrokenProvider("broken", []), FakeProvider("good", ["gpt-4o"])]
        ctx = FakeContext("broken", providers)
        pid, model = self.run_resolve(ctx, "gpt-4o")
        self.assertEqual(pid, "good")
        self.assertEqual(model, "gpt-4o")

    def test_context_get_current_raises(self):
        """get_current_chat_provider_id 抛异常：回落 None，不改写。"""
        class BadContext(FakeContext):
            async def get_current_chat_provider_id(self, umo: str):
                raise RuntimeError("no session")

        ctx = BadContext("x", self.providers)
        pid, model = self.run_resolve(ctx, "gpt-4o")
        self.assertIsNone(pid)

    def test_model_cache_hit(self):
        """缓存生效：第二次查询不再调用 get_models。"""
        calls = {"n": 0}

        class CountingProvider(FakeProvider):
            async def get_models(self):
                calls["n"] += 1
                return self._models

        ctx = FakeContext("counting", [CountingProvider("counting", ["gpt-4o"])])
        cache: dict[str, list[str]] = {}
        pid, model = self.run_resolve(ctx, "gpt-4o", cache=cache)
        self.assertEqual(model, "gpt-4o")
        pid, model = self.run_resolve(ctx, "gpt-4o", cache=cache)
        self.assertEqual(calls["n"], 1, "第二次查询应命中缓存")

    def test_provider_has_model_empty_models(self):
        """空模型列表的 provider 返回 False 且不抛异常。"""
        ctx = FakeContext("empty", [FakeProvider("empty", [])])
        self.assertFalse(
            self.run_has(ctx, "empty", "anything")
        )

    def run_resolve(self, ctx, configured, cache=None):
        import asyncio

        # 注意不能用 cache or {}：空 dict 是 falsy，会把传入的缓存丢成新 dict
        cache = cache if cache is not None else {}
        return asyncio.run(resolve_rewrite_target(ctx, "umo-1", configured, cache))

    def run_has(self, ctx, pid, model):
        import asyncio

        return asyncio.run(provider_has_model(ctx, pid, model, {}))


if __name__ == "__main__":
    unittest.main()
