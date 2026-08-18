# -*- coding: utf-8 -*-
"""
AstrBot 插件：好想成为人类啊（astrbot_plugin_humanizer）

整合 Humanizer-zh（中文 24 种 AI 写作模式）与 stop-slop（英文去 AI 痕迹规则），
通过 on_llm_response hook 自动对每条 AI 回复做人性化处理：
- 默认走规则清理（零成本、零延迟）
- 开启配置 enable_llm_rewrite 后，调用当前会话的大模型深度改写（更自然，消耗额外 token）

无需任何手动指令，插件启用后自动生效。
"""

import asyncio
import inspect
import json
import os
import sys
import time
from datetime import datetime

# 确保插件根目录在 sys.path 中，否则不同版本/加载方式下可能无法导入同目录的
# humanizer_core 子包（表现为 "No module named 'humanizer_core'"）。
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from astrbot.api import AstrBotConfig, logger
from astrbot.api.all import MessageChain
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star

from humanizer_core import (
    SYSTEM_PROMPT,
    humanize_text,
    humanize_text_detailed,
    is_blank,
)
from humanizer_core.config_migrate import migrate_flat_to_groups, migrate_proactive_key_names
from humanizer_core.llm_target import collect_models, resolve_rewrite_target
from humanizer_core.proactive import (
    ProactiveInFlightGuard,
    build_proactive_prompt,
    compute_next_delay,
    extract_last_messages,
    in_quiet,
    is_plausible_greeting,
    strip_reasoning_markers,
    was_already_sent_by_agent,
)

# 尝试导入官方 Agent Pipeline API（用于主动消息走完整管线，使 human_style、
# angel_memory 等插件的 on_llm_request 上下文注入对主动消息生效）。
# 旧版本框架缺少这些 API 时自动降级到轻量路径（llm_generate + send_message）。
try:
    from astrbot.core.cron.events import CronMessageEvent
    from astrbot.core.astr_main_agent import build_main_agent, MainAgentBuildConfig
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.platform.message_session import MessageSession
    from astrbot.core.pipeline.context_utils import call_event_hook
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
    from astrbot.core.pipeline.respond.stage import RespondStage
    from astrbot.core.star.star_handler import EventType
    from astrbot.core.message.message_event_result import ResultContentType

    HAS_AGENT_PIPELINE = True
except ImportError:
    HAS_AGENT_PIPELINE = False

# 新消息模型（用于把主动消息写回会话历史；旧版本框架用 dict 降级）
try:
    from astrbot.core.agent.message import (
        AssistantMessageSegment,
        UserMessageSegment,
        TextPart,
    )

    HAS_NEW_MESSAGE_API = True
except ImportError:
    HAS_NEW_MESSAGE_API = False

# 插件数据目录（主动聊天"聊过会话"状态持久化；旧框架降级为不持久化）
try:
    from astrbot.api.star import StarTools

    HAS_STARTOOLS = True
except ImportError:
    HAS_STARTOOLS = False

# 主动聊天的内置提示词模板：{persona} 会被替换为当前会话的人设（用户在
# AstrBot 配置的人格 prompt，读取失败则用兜底句）；{last_user}/{last_ai}
# 替换为会话最近一条用户/AI 消息（可能为空），用于生成贴合上下文的问候。
_DEFAULT_PROACTIVE_PROMPT = (
    "{persona}对方已经有一段时间没有发言了，"
    "请主动发起一句轻松的问候或话题，让对方愿意继续聊下去。\n"
    "要求：简短（一两句话即可）、自然、不要寒暄套话（如'在吗''最近怎么样'这类），"
    "可以结合下面的聊天背景自然切入。\n\n"
    "最近的聊天记录：\n用户最后说：{last_user}\n你最后说：{last_ai}"
)

# 主动消息 agent 生成超时（秒）：模型挂起时避免阻塞整个调度循环
_PROACTIVE_AGENT_TIMEOUT = 120


class HumanizerPlugin(Star):
    """自动去除 AI 回复痕迹，让对话更像真人。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 配置结构迁移：v1.3.0 起配置为 humanize/proactive 两个分组，
        # 旧版扁平结构在此迁移（保留用户设置），迁移后立即保存。
        try:
            if migrate_flat_to_groups(self.config):
                self.config.save_config()
                logger.info("[Humanizer] 配置已从扁平结构迁移为 humanize/proactive 分组")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 配置迁移失败: {e}")
        # v2.0.0：主动聊天键名差异化（idle_* → silence_*），旧键自动迁移保留用户设置。
        try:
            if migrate_proactive_key_names(self.config):
                self.config.save_config()
                logger.info("[Humanizer] 主动聊天配置键名已迁移（idle_* → silence_*）")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 主动聊天键名迁移失败: {e}")
        # 递归保护：记录正在被本插件 LLM 改写的会话，防止 hook 内再次触发自身
        self._rewriting: set[str] = set()
        # 缓存 llm_generate 是否支持 system_prompt 参数（不同 AstrBot 版本签名不同）
        self._llm_supports_system_prompt: bool | None = None
        # 模型列表缓存（provider_id -> 可用模型名），避免每条消息都向模型商查询
        self._model_cache: dict[str, list[str]] = {}
        # 主动聊天：会话下次触发时间戳（umo -> 墙钟秒 time.time()）。
        # 用户发消息时按"沉默时长+随机波动"排定；触发后按同样规则重排。
        # 用墙钟而非单调时钟，配合持久化文件实现重启后保留"聊过"状态。
        self._next_trigger_ts: dict[str, float] = {}
        # 触发状态持久化文件（data/plugin_data/<name>/proactive_state.json）
        self._state_file = self._resolve_state_file()
        # 脏标记：状态变更只置位，由调度循环每 30 秒落盘一次（避免每条消息
        # 同步写文件阻塞事件循环）；terminate 时无条件保存。
        self._state_dirty = False
        self._load_proactive_state()
        # 后台调度任务（每 30 秒检查沉默触发）
        # 主动聊天调度任务：在 initialize()（框架生命周期，事件循环已运行）中启动，
        # 不能在 __init__ 里 create_task——插件实例化可能早于事件循环，会抛 RuntimeError
        # 且被吞掉后调度循环永不启动（主动消息不触发的根因）。
        self._proactive_task: asyncio.Task | None = None
        # 正在主动聊天中的会话集合（umo）：热重载瞬间新老实例并存时，
        # 防止同一会话被两个循环实例并发触发各发一条；正常单实例顺序执行下不会命中。
        self._proactive_inflight = ProactiveInFlightGuard()

    # ------------------------------------------------------------------
    # 配置读取辅助：v1.3.0 起配置为 humanize/proactive 两个分组，
    # 迁移失败或极端场景下兼容旧扁平键。
    # ------------------------------------------------------------------
    def _h(self, key: str, default=None):
        """读取"润色设置"分组的配置值。"""
        group = self.config.get("humanize")
        return group.get(key, default) if isinstance(group, dict) else default

    def _p(self, key: str, default=None):
        """读取"主动聊天"分组的配置值。"""
        group = self.config.get("proactive")
        return group.get(key, default) if isinstance(group, dict) else default

    def _set_h(self, key: str, value) -> None:
        """写入"润色设置"分组的配置值（分组不存在时兜底创建）。"""
        group = self.config.setdefault("humanize", {})
        group[key] = value

    def _p_int(self, key: str, default: int) -> int:
        """读取整型配置；值非法（None/非数字）时返回默认值（不吞掉合法的 0）。"""
        val = self._p(key, default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_group_event(event: AstrMessageEvent, umo: str) -> bool:
        """判断事件是否来自群聊（用于主动聊天默认只跟踪私聊）。

        优先用框架 API get_message_type()；异常时回退解析 umo 字符串
        （格式 platform:MessageType:session_id，如 aiocqhttp:GroupMessage:123）。
        """
        try:
            mt = event.get_message_type()
            if mt is not None and "GROUP" in str(mt).upper():
                return True
            if mt is not None and "FRIEND" in str(mt).upper():
                return False
        except Exception:  # noqa: BLE001
            pass
        return "GroupMessage" in umo

    # ------------------------------------------------------------------
    # 主动聊天状态持久化：重启 AstrBot 不丢"聊过会话"跟踪。
    # 文件：data/plugin_data/<plugin_name>/proactive_state.json
    # 内容：{umo: 下次触发墙钟时间戳}。加载时把已过期条目顺延重排，
    # 避免重启后立即补发一波主动消息。
    # ------------------------------------------------------------------
    def _resolve_state_file(self):
        """获取状态文件路径；无 StarTools（旧框架）时返回 None（不持久化）。"""
        try:
            if HAS_STARTOOLS:
                data_dir = StarTools.get_data_dir("astrbot_plugin_humanizer")
                data_dir.mkdir(parents=True, exist_ok=True)
                return data_dir / "proactive_state.json"
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Humanizer] 获取数据目录失败，主动聊天状态不持久化: {e}")
        return None

    def _load_proactive_state(self) -> None:
        """启动时从文件恢复触发状态；文件缺失/损坏时静默使用空状态。"""
        if not self._state_file:
            return
        try:
            path = self._state_file
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            now = time.time()
            for umo, ts in data.items():
                if not isinstance(umo, str) or not isinstance(ts, (int, float)):
                    continue
                if ts <= now:
                    # 已过期的触发点：顺延一个周期，避免重启后立即补发
                    idle = self._p_int("silence_after_minutes", 45)
                    fluc = self._p_int("silence_fluctuation_minutes", 15)
                    ts = now + compute_next_delay(idle, fluc) * 60
                self._next_trigger_ts[umo] = float(ts)
            if self._next_trigger_ts:
                logger.info(
                    f"[Humanizer] 已恢复 {len(self._next_trigger_ts)} 个会话的主动聊天状态"
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 加载主动聊天状态失败（忽略）: {e}")

    def _save_proactive_state(self) -> None:
        """把触发状态原子写入文件（temp + rename，崩溃不产生截断损坏的半文件）。

        失败静默（不影响主流程）；调用后清除脏标记。
        """
        if not self._state_file:
            return
        try:
            path = self._state_file
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._next_trigger_ts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, path)
            self._state_dirty = False
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Humanizer] 保存主动聊天状态失败: {e}")

    async def initialize(self):
        """插件激活时启动主动聊天调度循环（框架生命周期钩子）。

        此时事件循环一定在运行，create_task 安全。基类默认空实现，
        这里覆盖以启动后台调度；默认关闭的 enable_proactive 由循环内开关控制。
        """
        if self._proactive_task is None:
            try:
                self._proactive_task = asyncio.create_task(self._proactive_loop())
            except RuntimeError:
                # 极端情况下事件循环仍不可用，静默放弃（terminate 兜底）
                self._proactive_task = None

    # ------------------------------------------------------------------
    # 主动聊天：用户沉默 N 分钟后，插件主动发消息（默认关闭）
    # ------------------------------------------------------------------
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def _track_activity(self, event: AstrMessageEvent):
        """用户发消息时刷新主动聊天状态（独立于 enabled 开关）。

        - 排定下次触发时间：当前 + 沉默时长（±15 随机波动，下限 30 分钟）
        - 未回复计数清零（用户主动发言 = 已回复）
        只有"有实际内容"的消息才处理，过滤输入状态等空事件。
        """
        text = getattr(event, "message_str", None) or ""
        if not text.strip():
            return
        umo = getattr(event, "unified_msg_origin", None) or ""
        if not umo:
            return
        # 群聊过滤：默认仅私聊触发主动聊天（群内任何成员发言都会刷新计时器，
        # 群沉默后机器人主动插话容易打扰大家）；proactive_track_groups 开启才跟踪群聊。
        if not self._p("proactive_track_groups", False) and self._is_group_event(event, umo):
            return
        idle_minutes = self._p_int("silence_after_minutes", 45)
        fluctuation = self._p_int("silence_fluctuation_minutes", 15)
        delay_minutes = compute_next_delay(idle_minutes, fluctuation)
        self._next_trigger_ts[umo] = time.time() + delay_minutes * 60
        self._state_dirty = True

    async def _proactive_loop(self):
        """后台调度：每 30 秒检查所有活跃会话是否到达下次触发时间。

        触发条件：到达 next_trigger_ts 且不在免打扰时段。
        触发后（无论成败）按沉默时长随机重排下次触发，避免 30 秒轮询刷屏。
        只对已启用 enable_proactive 的实例运行；单会话异常不影响整体。
        """
        try:
            while True:
                await asyncio.sleep(30)
                try:
                    # 状态落盘放在开关判断之前：功能关闭时跟踪状态变更也能持久化
                    if self._state_dirty:
                        self._save_proactive_state()
                    if not self._p("enable_proactive", False):
                        continue
                    idle_minutes = self._p_int("silence_after_minutes", 45)
                    fluctuation = self._p_int("silence_fluctuation_minutes", 15)
                    quiet = str(self._p("proactive_quiet_hours") or "").strip()
                    now_ts = time.time()
                    now_dt = datetime.now()
                    # 清理长期未更新的触发记录（超过 24 小时未重排），避免内存累积
                    stale = [
                        umo
                        for umo, ts in self._next_trigger_ts.items()
                        if now_ts - ts > 24 * 3600
                    ]
                    if stale:
                        for umo in stale:
                            self._next_trigger_ts.pop(umo, None)
                        self._state_dirty = True
                    # 状态有变更时落盘（每轮至多一次，替代每条消息同步写）
                    if self._state_dirty:
                        self._save_proactive_state()
                    for umo, next_ts in list(self._next_trigger_ts.items()):
                        if now_ts < next_ts:
                            continue
                        if in_quiet(now_dt, quiet):
                            continue
                        # 先按沉默时长随机重排下次触发，再执行发送：生成/发送可能耗时
                        # 数十秒，若重排放在调用后，此期间触发时间保持"已到期"，热重载
                        # 保存状态时落盘的将是过期时间，新实例读到会再补发一次。
                        delay_minutes = compute_next_delay(idle_minutes, fluctuation)
                        self._next_trigger_ts[umo] = now_ts + delay_minutes * 60
                        self._state_dirty = True
                        try:
                            await self._proactive_chat(umo)
                        except Exception as e:  # noqa: BLE001
                            logger.warning(f"[Humanizer] 主动聊天失败({umo}): {e}")
                except Exception as e:  # noqa: BLE001
                    # 单轮 tick 异常只记 warning，循环继续——防止整个调度循环被永久杀死
                    logger.warning(f"[Humanizer] 主动聊天调度单轮异常: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            logger.error(f"[Humanizer] 主动聊天调度循环异常退出: {e}")

    async def _proactive_chat(self, umo: str) -> bool:
        """对指定会话主动发一条消息。

        优先走完整 Agent Pipeline（CronMessageEvent + build_main_agent）：
        - 手动补发 OnLLMRequestEvent 钩子，human_style（风格）、angel_memory（记忆）
          等插件的上下文注入对主动消息生效；
        - 发送走 ResultDecorateStage + RespondStage，angel_memory 的记忆巩固
          （after_message_sent）也会触发。
        旧框架（无 Agent Pipeline API）或 pipeline 失败时，回落到轻量路径
        （llm_generate → humanize_text → send_message）。

        失败静默（记 warning），绝不影响插件其他功能。
        """
        # 并发防御：同一会话已在主动聊天中（热重载瞬间新老实例并存等）直接返回，
        # 避免两个循环实例各发一条。
        if not self._proactive_inflight.try_acquire(umo):
            logger.warning(f"[Humanizer] 主动聊天已在发送中，跳过重复触发: {umo}")
            return False
        try:
            # 生成目标：与深度改写共用 resolve_rewrite_target（rewrite_model 或当前会话）
            configured_model = str(self._h("rewrite_model") or "").strip()
            provider_id, model_name = await resolve_rewrite_target(
                self.context, umo, configured_model, self._model_cache
            )
            if not provider_id:
                logger.warning(f"[Humanizer] 主动聊天跳过：{umo} 无可用模型提供商")
                return False

            # 拼接提示词：人设（当前会话）+ 最近聊天上下文
            last_user, last_ai = "", ""
            try:
                last_user, last_ai = await self._get_last_messages(umo)
            except Exception:  # noqa: BLE001
                pass
            persona = await self._get_curr_persona_prompt(umo)
            template = str(
                self._p("proactive_prompt") or _DEFAULT_PROACTIVE_PROMPT
            )
            prompt = build_proactive_prompt(
                template, persona, last_user=last_user, last_ai=last_ai
            )

            # 完整 Agent Pipeline 路径：使风格/记忆等插件注入生效
            if HAS_AGENT_PIPELINE:
                try:
                    response_text, cron_event, conversation = (
                        await self._generate_proactive_reply(umo, prompt)
                    )
                    if response_text:
                        # 发送前剥离残留思维链（推理模型可能把思考拼进 completion_text）
                        response_text = strip_reasoning_markers(response_text)
                        # 问候合理性校验：若生成结果是内部推理/记录回顾（如
                        # "根据以往记录…我已回复…"），不是问候，放弃本次发送
                        if not response_text or not is_plausible_greeting(response_text):
                            logger.warning(
                                f"[Humanizer] 主动消息非正常问候，放弃发送({umo}): {response_text[:50]!r}"
                            )
                            return False
                        sent = await self._send_via_stages(cron_event, response_text)
                        if sent:
                            # 确认发送成功后写回历史（保持上下文连续）
                            await self._save_proactive_history(
                                umo, response_text, conversation
                            )
                            logger.info(
                                f"[Humanizer] 主动聊天已发送给 {umo}: {response_text[:40]}..."
                            )
                            return True
                        # 模型在 agent 运行中已通过 send_message_to_user 工具直发过
                        # 该会话（如改写后的最终文本与工具文本不一致，框架去重不会
                        # 拦截），视为已发送：跳过管线重发，仅写回历史保持上下文连续。
                        if was_already_sent_by_agent(cron_event):
                            logger.warning(
                                f"[Humanizer] 主动消息已由 agent 工具直发，跳过管线重发({umo})"
                            )
                            await self._save_proactive_history(
                                umo, response_text, conversation
                            )
                            return True
                        logger.warning(
                            f"[Humanizer] 主动聊天发送未确认（pipeline）: {umo}"
                        )
                        return False
                    # pipeline 无文本：回落到轻量路径
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"[Humanizer] 主动聊天 pipeline 失败，回退轻量路径: {e}"
                    )

            # 轻量路径（旧框架降级 / pipeline 不可用或失败）：
            # LLM 生成 → 去 AI 痕迹 → 直接发送。
            llm_resp = None
            try:
                kwargs: dict = {"chat_provider_id": provider_id, "prompt": prompt}
                if model_name:
                    kwargs["model"] = model_name
                llm_resp = await self.context.llm_generate(**kwargs)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[Humanizer] 主动聊天 llm_generate 失败，回退 text_chat: {e}")
                try:
                    prov = await self.context.get_using_provider_async(umo=umo)
                    if prov is not None:
                        t_kwargs: dict = {"prompt": prompt}
                        if model_name:
                            t_kwargs["model"] = model_name
                        llm_resp = await prov.text_chat(**t_kwargs)
                except Exception as e2:  # noqa: BLE001
                    logger.warning(f"[Humanizer] 主动聊天 text_chat 回退失败: {e2}")
            if llm_resp is None:
                return False

            text = getattr(llm_resp, "completion_text", None)
            if is_blank(text):
                return False
            # 先剥离残留思维链，再去 AI 痕迹（推理模型可能把思考拼进 completion_text）
            text = strip_reasoning_markers(str(text))
            if is_blank(text):
                return False
            # 问候合理性校验：非问候（内部推理/记录回顾）放弃发送
            if not is_plausible_greeting(text):
                logger.warning(
                    f"[Humanizer] 主动消息非正常问候，放弃发送({umo}): {text[:50]!r}"
                )
                return False
            cleaned = humanize_text(
                text,
                remove_emoji=bool(self._h("remove_emoji", True)),
            )
            if is_blank(cleaned):
                return False
            chain = MessageChain().message(cleaned)
            ok = await self.context.send_message(umo, chain)
            if ok:
                # 确认发送成功后写回历史（保持上下文连续）
                await self._save_proactive_history(umo, cleaned)
                logger.info(f"[Humanizer] 主动聊天已发送给 {umo}: {cleaned[:40]}...")
                return True
            logger.warning(f"[Humanizer] 主动聊天发送失败（无匹配平台）: {umo}")
            return False
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 主动聊天失败({umo}): {e}")
            return False
        finally:
            self._proactive_inflight.release(umo)

    async def _generate_proactive_reply(
        self, umo: str, prompt: str
    ) -> tuple[str | None, object | None, object | None]:
        """通过 CronMessageEvent + build_main_agent 走完整 Agent Pipeline 生成主动回复。

        在 build 之后手动补发 OnLLMRequestEvent 钩子（build_main_agent 本身不触发
        该事件），使 human_style（改 system_prompt）、angel_memory（写
        extra_user_content_parts）等插件的上下文注入对主动消息生效。

        返回 (response_text, cron_event, conversation)；失败或无文本时
        conversation 为 None。
        """
        session = MessageSession.from_str(umo)
        cron_event = CronMessageEvent(
            context=self.context,
            session=session,
            message=prompt,
            extras={"humanizer_proactive": True},
        )
        # 主动场景禁用发消息工具：cron 平台元数据默认 support_proactive_message=True，
        # 会让 build_main_agent 注入 SendMessageToUserTool。模型偶发调用它直发一条后，
        # 插件还会用最终文本走 _send_via_stages 再发一次（框架去重仅在文本完全一致时
        # 生效），导致同一轮消息偶现双发。主动消息由插件统一发送，agent 只需生成文本，
        # 因此覆写为 False 移除该工具。发送阶段 _send_via_stages 会临时换回真实平台
        # meta，不影响实际投递。
        if HAS_AGENT_PIPELINE:
            try:
                cron_event.platform_meta = PlatformMetadata(
                    name="cron",
                    description="CronJob",
                    id=session.platform_id,
                    support_proactive_message=False,
                )
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[Humanizer] 覆写主动事件平台元数据失败: {e}")

        # 组装 MainAgentBuildConfig：从会话的 provider_settings 取用户配置，
        # 其余用 AstrBot 默认值；仅传当前框架版本存在的字段（__dataclass_fields__ 过滤）。
        astr_conf = self.context.get_config(umo=umo)
        provider_settings = astr_conf.get("provider_settings", {}) if astr_conf else {}
        config_fields = getattr(MainAgentBuildConfig, "__dataclass_fields__", {})
        # 需要从会话配置读取的字段与默认值（其余字段交给框架默认）
        _config_defaults: dict[str, object] = {
            "tool_call_timeout": 120,
            "tool_schema_mode": "full",
            "sanitize_context_by_modalities": False,
            "context_limit_reached_strategy": "truncate_by_turns",
            "llm_compress_instruction": "",
            "llm_compress_provider_id": "",
            "max_context_length": -1,
            "dequeue_context_length": 1,
            "safety_mode_strategy": "system_prompt",
            "computer_use_runtime": "local",
            "max_quoted_fallback_images": 20,
        }
        config_kwargs = {
            key: provider_settings.get(key, default)
            for key, default in _config_defaults.items()
            if key in config_fields
        }
        # 主动消息走流式=False + 关闭安全模式（与定时/主动场景一致，避免额外拦截）
        config_kwargs["streaming_response"] = False
        config_kwargs["llm_safety_mode"] = False
        # 主动问候不需要定时/定时器工具（避免 agent 反复调工具跑满步骤）
        if "add_cron_tools" in config_fields:
            config_kwargs["add_cron_tools"] = False
        config_kwargs["provider_settings"] = provider_settings
        if "timezone" in config_fields:
            config_kwargs["timezone"] = astr_conf.get("timezone") if astr_conf else None
        if "llm_compress_keep_recent_ratio" in config_fields:
            config_kwargs["llm_compress_keep_recent_ratio"] = provider_settings.get(
                "llm_compress_keep_recent_ratio", 0.15
            )
        elif "llm_compress_keep_recent" in config_fields:
            config_kwargs["llm_compress_keep_recent"] = provider_settings.get(
                "llm_compress_keep_recent", 4
            )

        config = MainAgentBuildConfig(**config_kwargs)

        result = await build_main_agent(
            event=cron_event,
            plugin_context=self.context,
            config=config,
            provider=None,
            req=None,
            apply_reset=False,
        )
        if not result or not result.agent_runner:
            logger.warning(f"[Humanizer] build_main_agent 返回空结果: {umo}")
            return None, cron_event

        # 手动补发 OnLLMRequestEvent：human_style / angel_memory 等插件的
        # on_llm_request 上下文注入在此生效（build_main_agent 不触发该钩子）。
        if await call_event_hook(cron_event, EventType.OnLLMRequestEvent, result.provider_request):
            if result.reset_coro:
                result.reset_coro.close()
            logger.debug(f"[Humanizer] OnLLMRequestEvent 终止主动消息: {umo}")
            return None, cron_event

        if result.reset_coro:
            await result.reset_coro

        runner = result.agent_runner
        # 超时保护：模型挂起时 step_until_done 可能长时间阻塞；调度是单任务顺序执行，
        # 一个会话卡住会阻塞所有会话的主动聊天，必须加超时。
        try:
            await asyncio.wait_for(
                self._drain_runner(runner), timeout=_PROACTIVE_AGENT_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"[Humanizer] 主动消息 agent 生成超时({umo})")
            return None, cron_event, None

        llm_resp = runner.get_final_llm_resp()
        if not llm_resp or not llm_resp.completion_text:
            logger.debug(f"[Humanizer] Agent 无文本响应: {umo}")
            return None, cron_event

        response_text = llm_resp.completion_text.strip()
        if not response_text:
            return None, cron_event, None
        # 附带会话对象，供发送成功后写回历史
        conversation = getattr(result.provider_request, "conversation", None)
        return response_text, cron_event, conversation

    async def _drain_runner(self, runner: object) -> None:
        """跑完 agent runner 的所有步骤（供 wait_for 超时包裹）。"""
        async for _ in runner.step_until_done(30):
            pass

    async def _save_proactive_history(
        self, umo: str, response_text: str, conversation: object | None = None
    ) -> None:
        """把主动消息写回会话历史（确认发送成功后调用，避免失败污染历史）。

        写入"假用户消息（[主动消息] 前缀）+ 主动回复"消息对，让会话上下文连续：
        - 下次 _get_last_messages 能提取到主动消息；
        - angel_memory 等记忆插件的记忆巩固能看到这次交互。
        优先用新消息模型（UserMessageSegment/AssistantMessageSegment），
        旧框架降级为 dict 格式。任何失败仅记 warning，不影响主流程。
        """
        try:
            conv_mgr = self.context.conversation_manager
            if conversation is None:
                curr_cid = await conv_mgr.get_curr_conversation_id(umo)
                if not curr_cid:
                    logger.debug(f"[Humanizer] 会话为空，跳过主动消息历史写回: {umo}")
                    return
                conversation = await conv_mgr.get_conversation(umo, curr_cid)
            if not conversation:
                logger.debug(f"[Humanizer] 会话不存在，跳过历史写回: {umo}")
                return
            cid = getattr(conversation, "cid", None)
            if not cid:
                return

            # 中性标记前缀：标注这是插件主动发起的内容（不引用任何具体插件）
            user_prompt = "[主动消息] 请自然地延续对话。"
            if HAS_NEW_MESSAGE_API:
                try:
                    user_msg = UserMessageSegment(content=[TextPart(text=user_prompt)])
                    assistant_msg = AssistantMessageSegment(
                        content=[TextPart(text=response_text)]
                    )
                    await conv_mgr.add_message_pair(
                        cid=cid,
                        user_message=user_msg,
                        assistant_message=assistant_msg,
                    )
                    return
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"[Humanizer] add_message_pair(新API) 失败，降级 dict: {e}")

            await conv_mgr.add_message_pair(
                cid=cid,
                user_message={"role": "user", "content": user_prompt},
                assistant_message={"role": "assistant", "content": response_text},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 主动消息历史写回失败({umo}): {e}")

    async def _send_via_stages(self, event: object, text: str) -> bool:
        """通过完整装饰/响应阶段发送主动消息（ResultDecorateStage + RespondStage）。

        主动消息作为 LLM 结果走标准装饰链（分段、TTS、引用处理等），
        并让 RespondStage 分发 after_message_sent 事件——angel_memory 等插件的
        记忆巩固钩子因此被触发。框架未提供 plugin_manager 时降级为直接发送。
        """
        try:
            result = event.plain_result(text)
            result.set_result_content_type(ResultContentType.LLM_RESULT)
            event.set_result(result)
            setattr(event, "__is_llm_reply", True)

            plugin_manager = getattr(self.context, "_star_manager", None)
            if not plugin_manager:
                # 降级：直接发送
                result = event.get_result()
                if result and result.chain:
                    await event.send(result)
                    event.clear_result()
                    return True
                event.clear_result()
                return False

            pipe_ctx = PipelineContext(
                self.context.get_config(umo=event.unified_msg_origin),
                plugin_manager,
                event.get_platform_id(),
            )

            old_platform_meta = event.platform_meta
            platform = self.context.get_platform_inst(event.get_platform_id())
            if platform:
                event.platform_meta = platform.meta()

            send_count = 0
            original_send = event.send

            async def tracked_send(*args, **kwargs):
                nonlocal send_count
                r = await original_send(*args, **kwargs)
                send_count += 1
                return r

            event.send = tracked_send
            try:
                for stage_cls in (ResultDecorateStage, RespondStage):
                    stage = stage_cls()
                    await stage.initialize(pipe_ctx)
                    processed = stage.process(event)
                    if hasattr(processed, "__aiter__"):
                        async for _ in processed:
                            pass
                    else:
                        await processed
                    if event.is_stopped():
                        break
                return send_count > 0
            finally:
                event.send = original_send
                event.platform_meta = old_platform_meta
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[Humanizer] 主动消息发送阶段失败({getattr(event, 'unified_msg_origin', '?')}): {e}"
            )
            return False

    async def _get_last_messages(self, umo: str) -> tuple[str, str]:
        """从会话历史取最近一条用户消息与 AI 消息（用于上下文拼接）。

        会话历史存于 Conversation.history（JSON 字符串，消息为 {role, content}
        dict 列表），解析方式与 AstrBot 主 agent 一致（json.loads(history)）。
        具体解析逻辑见 proactive.extract_last_messages（纯函数，可离线测试）。
        """
        last_user, last_ai = "", ""
        try:
            conv_mgr = self.context.conversation_manager
            cid = await conv_mgr.get_curr_conversation_id(umo)
            if not cid:
                return last_user, last_ai
            conv = await conv_mgr.get_conversation(umo, cid)
            if not conv or not conv.history:
                return last_user, last_ai
            last_user, last_ai = extract_last_messages(conv.history)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 读取会话历史失败({umo}): {e}")
        return last_user, last_ai

    async def _get_curr_persona_prompt(self, umo: str) -> str:
        """获取当前会话生效的人设提示词（用户在 AstrBot 配置的人格 prompt）。

        解析链路与主 agent 一致：
        conversation.persona_id → persona_manager.resolve_selected_persona → persona["prompt"]。
        读取失败或无人设时返回空串，由调用方使用兜底句。
        """
        try:
            conv_mgr = self.context.conversation_manager
            cid = await conv_mgr.get_curr_conversation_id(umo)
            if not cid:
                return ""
            conv = await conv_mgr.get_conversation(umo, cid)
            conv_persona_id = getattr(conv, "persona_id", None) if conv else None
            # 从 umo 解析平台名（如 "aiocqhttp:GroupMessage:123" → "aiocqhttp"）
            platform_name = umo.split(":")[0] if ":" in umo else "webchat"
            _, persona, _, _ = (
                await self.context.persona_manager.resolve_selected_persona(
                    umo=umo,
                    conversation_persona_id=conv_persona_id,
                    platform_name=platform_name,
                    provider_settings={},
                )
            )
            if persona and isinstance(persona, dict):
                return str(persona.get("prompt") or "").strip()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 读取会话人设失败({umo}): {e}")
        return ""

    # ------------------------------------------------------------------
    # 自动处理：每条 AI 回复经过人性化润色
    # ------------------------------------------------------------------
    @filter.on_llm_response()
    async def humanize_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """在 AI 生成回复后自动润色，改写 resp.completion_text 即生效。"""
        if not self._h("enabled", True):
            return

        # 通用拦截：CronMessageEvent（定时/主动消息，platform 名固定为 "cron"，
        # 如各主动聊天插件、官方定时任务）生成的回复不做润色，并清除推理模型的
        # 思考内容——避免 "🤔 思考: ..." 注入发送给用户。这类消息是插件
        # 主动生成的问候/提示，不需要（也不应）再套用去 AI 痕迹规则。
        if event.get_platform_name() == "cron":
            event.set_extra("_llm_reasoning_content", None)
            return

        # 通用副作用：remove_reasoning 开启时，对所有回复清除推理模型的思考过程
        # （"🤔 思考: ..."），只显示正式回复内容。默认关闭：仅隐藏不阻止思考，
        # 模型照常思考、token 照常计费，由用户权衡后开启。
        if self._h("remove_reasoning", False):
            event.set_extra("_llm_reasoning_content", None)

        text = getattr(resp, "completion_text", None)
        # 空白输出原样放行：模型可能输出空文本，若发去改写模型会被自行编造
        # 一句话当成正式回复（无中生有事故），此处直接返回，不产生任何新文本。
        if is_blank(text):
            return

        min_length = int(self._h("min_length", 8))
        max_chars = int(self._h("max_chars", 300))
        if len(text.strip()) < min_length:
            return

        # 递归保护：本插件内部的 LLM 改写请求不再次处理
        origin = getattr(event, "unified_msg_origin", None) or ""
        if origin in self._rewriting:
            return

        enable_llm = bool(self._h("enable_llm_rewrite", False))

        # 长文本只做规则清理，防止 LLM 改写消耗过多 token
        if enable_llm and len(text) <= max_chars:
            rewritten = await self._llm_rewrite(event, text)
            if rewritten:
                resp.completion_text = rewritten
                return

        # 默认路径：规则清理（免费、即时）
        cleaned, hits = humanize_text_detailed(
            text, remove_emoji=bool(self._h("remove_emoji", True))
        )
        if hits and self._h("debug", False):
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
            current = str(self._h("rewrite_model") or "").strip()
            shown = current or "（空，跟随当前会话）"
            await event.send(
                f"当前深度改写模型：{shown}\n"
                "用 /humanizer_models 查看可选模型，再 /humanizer_model <编号> 选择；"
                "也可直接 /humanizer_model <模型名> 手填；/humanizer_model off 恢复跟随当前会话。"
            )
            return
        if arg in ("off", "clear", "0"):
            self._set_h("rewrite_model", "")
            await self.config.save_config_async()
            await event.send("已恢复：深度改写跟随当前会话模型。")
            return

        rows = await collect_models(self.context, self._model_cache)
        flat = [(pid, m) for pid, _, models in rows for m in models]
        if arg.isdigit():
            n = int(arg)
            if 1 <= n <= len(flat):
                pid, model = flat[n - 1]
                self._set_h("rewrite_model", model)
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
                self._set_h("rewrite_model", arg)
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
        configured_model = str(self._h("rewrite_model") or "").strip()
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
            rewritten = rewritten.strip()
            # 防御：改写结果比原文膨胀过多（> 2 倍）说明模型过度发挥
            # （推理模型常把"改写"当成"扩写/创作"），此时回落规则清理，
            # 避免把简短回复扩写成怪怪的长篇。
            if len(rewritten) > len(text.strip()) * 2:
                logger.warning(
                    f"[Humanizer] 改写结果过长（{len(rewritten)} > 2×{len(text.strip())}），回落规则清理"
                )
                return None
            return rewritten
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] LLM 深度改写失败，回落规则清理: {e}")
            return None
        finally:
            self._rewriting.discard(origin)

    async def terminate(self):
        """插件卸载/停用时调用。"""
        # 停用前保存主动聊天状态（重启/停用后仍保留"聊过会话"跟踪）
        self._save_proactive_state()
        self._rewriting.clear()
        if self._proactive_task:
            self._proactive_task.cancel()
            try:
                await self._proactive_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._proactive_task = None
