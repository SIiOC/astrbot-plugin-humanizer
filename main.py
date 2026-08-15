# -*- coding: utf-8 -*-
"""
AstrBot 插件：AI 真人感润色（astrbot_plugin_humanizer）

整合 Humanizer-zh（中文 24 种 AI 写作模式）与 stop-slop（英文去 AI 痕迹规则），
通过 on_llm_response hook 自动对每条 AI 回复做人性化处理：
- 默认走规则清理（零成本、零延迟）
- 开启配置 enable_llm_rewrite 后，调用当前会话的大模型深度改写（更自然，消耗额外 token）

无需任何手动指令，插件启用后自动生效。
"""

import inspect
import os
import sys

# 确保插件根目录在 sys.path 中，否则不同版本/加载方式下可能无法导入同目录的
# humanizer_core 子包（表现为 "No module named 'humanizer_core'"）。
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star

from humanizer_core import (
    SYSTEM_PROMPT,
    humanize_text_detailed,
    is_blank,
    should_skip_conversa,
)
from humanizer_core.llm_target import collect_models, resolve_rewrite_target


class HumanizerPlugin(Star):
    """自动去除 AI 回复痕迹，让对话更像真人。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 递归保护：记录正在被本插件 LLM 改写的会话，防止 hook 内再次触发自身
        self._rewriting: set[str] = set()
        # 缓存 llm_generate 是否支持 system_prompt 参数（不同 AstrBot 版本签名不同）
        self._llm_supports_system_prompt: bool | None = None
        # 模型列表缓存（provider_id -> 可用模型名），避免每条消息都向模型商查询
        self._model_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # 自动处理：每条 AI 回复经过人性化润色
    # ------------------------------------------------------------------
    @filter.on_llm_response()
    async def humanize_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """在 AI 生成回复后自动润色，改写 resp.completion_text 即生效。"""
        if not self.config.get("enabled", True):
            return

        # Conversa 主动回复场景：走 agent pipeline，event 带 conversa_proactive 标记。
        # 此时 event.message_str 是主动回复的 prompt（不含 "[Conversa主动发起对话]" 标记），
        # should_skip_conversa 拦不住这里，改用 event extra 判断（与 Conversa 自身钩子一致）。
        # 始终清除 _llm_reasoning_content：否则框架 result_decorate 阶段会把推理模型的
        # 思考过程（"🤔 思考: ..."）注入消息链发送给用户。
        if event.get_extra("conversa_proactive"):
            event.set_extra("_llm_reasoning_content", None)
            return

        # 通用副作用：remove_reasoning 开启时，对所有回复清除推理模型的思考过程
        # （"🤔 思考: ..."），只显示正式回复内容。与 Conversa 场景的强制清除相比，
        # 这里可配置，且不影响后续润色流程。默认关闭：仅隐藏不阻止思考，
        # 模型照常思考、token 照常计费，由用户权衡后开启。
        if self.config.get("remove_reasoning", False):
            event.set_extra("_llm_reasoning_content", None)

        # conversa 系统触发场景：用户消息带固定标记（如「[Conversa主动发起对话]」），
        # 属于插件定时生成的问候/提示，整个链路跳过，不做规则清理也不做 LLM 改写。
        if should_skip_conversa(getattr(event, "message_str", None)):
            return

        text = getattr(resp, "completion_text", None)
        # 空白输出原样放行：模型可能输出空文本，若发去改写模型会被自行编造
        # 一句话当成正式回复（无中生有事故），此处直接返回，不产生任何新文本。
        if is_blank(text):
            return

        min_length = int(self.config.get("min_length", 8))
        max_chars = int(self.config.get("max_chars", 1500))
        if len(text.strip()) < min_length:
            return

        # 递归保护：本插件内部的 LLM 改写请求不再次处理
        origin = getattr(event, "unified_msg_origin", None) or ""
        if origin in self._rewriting:
            return

        enable_llm = bool(self.config.get("enable_llm_rewrite", False))

        # 长文本只做规则清理，防止 LLM 改写消耗过多 token
        if enable_llm and len(text) <= max_chars:
            rewritten = await self._llm_rewrite(event, text)
            if rewritten:
                resp.completion_text = rewritten
                return

        # 默认路径：规则清理（免费、即时）
        cleaned, hits = humanize_text_detailed(
            text, remove_emoji=bool(self.config.get("remove_emoji", True))
        )
        if hits and self.config.get("debug", False):
            logger.info(
                f"[Humanizer] 规则命中 {hits}: {text[:60]!r} -> {cleaned[:80]!r}"
            )
        if cleaned != text:
            resp.completion_text = cleaned

    # ------------------------------------------------------------------
    # 命令：查看 / 选择深度改写模型（动态读取用户已配置的模型列表）
    # ------------------------------------------------------------------
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("humanizer_models")
    async def list_models(self, event: AstrMessageEvent) -> None:
        """列出所有已配置提供商及其可用模型，供选择深度改写模型。"""
        rows = await collect_models(self.context, self._model_cache)
        if not rows:
            await event.send("尚未配置任何模型提供商。")
            return
        lines = ["已配置的提供商与可用模型："]
        idx = 1
        for pid, ptype, models in rows:
            if models:
                for m in models:
                    lines.append(f"{idx}. [{pid}] {m}")
                    idx += 1
            else:
                lines.append(f"- [{pid}]（未获取到模型列表，可手填模型名）")
        lines.append("用 /humanizer_model <编号> 选择；/humanizer_model off 恢复跟随当前会话。")
        await event.send("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("humanizer_model")
    async def set_rewrite_model(self, event: AstrMessageEvent, arg: str = "") -> None:
        """选择深度改写模型：/humanizer_model <编号|模型名|off>。"""
        arg = (arg or "").strip()
        if not arg:
            current = str(self.config.get("rewrite_model") or "").strip()
            shown = current or "（空，跟随当前会话）"
            await event.send(
                f"当前深度改写模型：{shown}\n"
                "用 /humanizer_models 查看可选模型，再 /humanizer_model <编号> 选择；"
                "也可直接 /humanizer_model <模型名> 手填；/humanizer_model off 恢复跟随当前会话。"
            )
            return
        if arg in ("off", "clear", "0"):
            self.config["rewrite_model"] = ""
            await self.config.save_config_async()
            await event.send("已恢复：深度改写跟随当前会话模型。")
            return

        rows = await collect_models(self.context, self._model_cache)
        flat = [(pid, m) for pid, _, models in rows for m in models]
        if arg.isdigit():
            n = int(arg)
            if 1 <= n <= len(flat):
                pid, model = flat[n - 1]
                self.config["rewrite_model"] = model
                await self.config.save_config_async()
                await event.send(f"已设置深度改写模型：{model}（提供商 {pid}）。")
                return
            await event.send(
                f"编号超出范围（1-{len(flat)}）。用 /humanizer_models 查看完整列表。"
            )
            return

        # 直接填模型名：校验是否存在于任一已配置提供商
        for pid, _, models in rows:
            if arg in models:
                self.config["rewrite_model"] = arg
                await self.config.save_config_async()
                await event.send(f"已设置深度改写模型：{arg}（提供商 {pid}）。")
                return
        await event.send(
            f"模型 {arg!r} 不在已配置提供商的模型列表中。用 /humanizer_models 查看可选模型。"
        )

    # ------------------------------------------------------------------
    # LLM 深度改写
    # ------------------------------------------------------------------
    async def _llm_rewrite(self, event: AstrMessageEvent, text: str) -> str | None:
        """调用当前会话的大模型按合并后的技能指南深度改写文本。

        失败时返回 None，由调用方回落到规则清理。
        """
        # 空白防御：不把空/纯空白文本发给改写模型（模型会自行造一句当正式回复），
        # 入口兜底检查，即使钩子层配置遗漏也不会走到模型调用。
        if is_blank(text):
            return None

        # 解析深度改写目标：配置了 rewrite_model 时优先用指定模型，
        # 未配置则跟随当前会话模型；解析失败回落当前会话。
        origin = getattr(event, "unified_msg_origin", None) or ""
        configured_model = str(self.config.get("rewrite_model") or "").strip()
        try:
            provider_id, model_name = await resolve_rewrite_target(
                self.context, origin, configured_model, self._model_cache
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 解析改写目标失败: {e}")
            provider_id, model_name = None, None

        if not provider_id:
            logger.warning("[Humanizer] 当前会话未配置可用的模型提供商，跳过 LLM 改写")
            return None

        # 递归保护标记（origin 已在上面解析目标时取得）
        self._rewriting.add(origin)
        try:
            kwargs = {"chat_provider_id": provider_id, "prompt": text}
            # 指定了改写模型时，把 model 传给 provider（text_chat 原生支持）
            if model_name:
                kwargs["model"] = model_name
            if self._llm_supports_system_prompt is None:
                try:
                    self._llm_supports_system_prompt = (
                        "system_prompt"
                        in inspect.signature(self.context.llm_generate).parameters
                    )
                except (TypeError, ValueError):
                    self._llm_supports_system_prompt = False

            if self._llm_supports_system_prompt:
                kwargs["system_prompt"] = SYSTEM_PROMPT
            else:
                # 旧版本不支持 system_prompt 参数，拼进 prompt 里
                kwargs["prompt"] = f"{SYSTEM_PROMPT}\n\n待处理的文本：\n{text}"

            llm_resp = await self.context.llm_generate(**kwargs)
            rewritten = getattr(llm_resp, "completion_text", None)
            if not rewritten or not rewritten.strip():
                return None
            return rewritten.strip()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] LLM 深度改写失败，回落规则清理: {e}")
            return None
        finally:
            self._rewriting.discard(origin)

    async def terminate(self):
        """插件卸载/停用时调用。"""
        self._rewriting.clear()
