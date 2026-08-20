# -*- coding: utf-8 -*-
"""
AstrBot 插件：好想成为人类啊（astrbot_plugin_humanizer）

v2.1.0 起整合人类对话风格（原 astrbot_plugin_human_style）：

- 生成前（on_llm_request）：注入从人类语料提炼的「说话风格档案」+ 检索示例
- 生成后（on_llm_response）：规则清理/LLM 深度改写去除 AI 痕迹；
  深度改写时把当前风格的口癖/句式追加进改写 Prompt，实现"先真人化改写再注入口癖"

另含 Humanizer-zh（中文 24 种 AI 写作模式）与 stop-slop（英文去 AI 痕迹规则）、
主动聊天（用户沉默后自然续聊）。
"""

import asyncio
import inspect
import json
import os
import shutil
import sys
import time
from datetime import datetime

# 确保插件根目录在 sys.path 中，否则不同版本/加载方式下可能无法导入同目录的
# humanizer_core / style_core 子包（表现为 "No module named 'humanizer_core'"）。
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
from style_core import inject
from style_core.corpus import (
    append_pairs_to_pool,
    merge_pool_rows,
    new_files,
    parse_corpus_text,
    pool_stats,
    read_pool,
    sample_merged,
)
from style_core.extract_prompt import build_extract_prompt, build_refine_prompt, parse_profile_json
from style_core.profiles import (
    find_profile,
    list_profile_names,
    list_profiles,
    normalize_profile,
    save_profile_file,
    validate_profile,
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
    """让对话更像真人：生成前注入人类对话风格，生成后去除 AI 痕迹。"""

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
        # ---------------- 人类对话风格（原 human_style v1.3.7 吸入） ----------------
        self._root = _PLUGIN_DIR
        # 种子档案目录（随插件分发；市场升级 zip 覆盖只影响这里）
        self._seed_styles_dir = os.path.join(self._root, "styles")
        # 运行时档案目录：优先 plugin_data（用户提炼的档案升级不丢），失败退回种子目录
        self._styles_dir = self._seed_styles_dir
        self._corpora_dir = os.path.join(self._root, "corpora")
        # 用户语料池/状态文件：统一放本插件数据目录（data/plugin_data/astrbot_plugin_humanizer/）
        self._user_corpus_path = os.path.join(self._corpora_dir, "user_corpus.jsonl")
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

            user_dir = os.path.join(
                get_astrbot_plugin_data_path(), "astrbot_plugin_humanizer"
            )
            os.makedirs(user_dir, exist_ok=True)
            self._user_corpus_path = os.path.join(user_dir, "user_corpus.jsonl")
            # 风格档案运行目录：plugin_data/styles，首次运行从种子目录拷入（不覆盖已有）
            styles_dir = os.path.join(user_dir, "styles")
            os.makedirs(styles_dir, exist_ok=True)
            if os.path.isdir(self._seed_styles_dir):
                for fn in os.listdir(self._seed_styles_dir):
                    if fn.endswith(".json"):
                        _src = os.path.join(self._seed_styles_dir, fn)
                        _dst = os.path.join(styles_dir, fn)
                        if os.path.exists(_src) and not os.path.exists(_dst):
                            shutil.copy(_src, _dst)
            self._styles_dir = styles_dir
            # 数据迁移：原独立插件 astrbot_plugin_human_style 的用户语料
            legacy_dir = os.path.join(
                get_astrbot_plugin_data_path(), "astrbot_plugin_human_style"
            )
            legacy_corpus = os.path.join(legacy_dir, "user_corpus.jsonl")
            if os.path.exists(legacy_corpus) and not os.path.exists(self._user_corpus_path):
                shutil.copy(legacy_corpus, self._user_corpus_path)
                logger.info("[Humanizer] 已迁移原 human_style 数据: user_corpus.jsonl")
            # state.json 统一以最终名 state_human_style.json 迁入（与 proactive_state.json
            # 区分）；历史构建可能以旧名残留的重复文件在此归位/清理
            _final_state = os.path.join(user_dir, "state_human_style.json")
            _old_state = os.path.join(user_dir, "state.json")
            _legacy_state = os.path.join(legacy_dir, "state.json")
            if not os.path.exists(_final_state):
                if os.path.exists(_old_state):
                    shutil.move(_old_state, _final_state)
                elif os.path.exists(_legacy_state):
                    shutil.copy(_legacy_state, _final_state)
                    logger.info("[Humanizer] 已迁移原 human_style 数据: state.json")
            elif os.path.exists(_old_state):
                os.remove(_old_state)  # 重复残留清理
        except Exception:  # noqa: BLE001
            pass  # 取不到 plugin_data 时退回插件目录，至少不崩
        self._state_style_path = os.path.join(
            os.path.dirname(self._user_corpus_path), "state_human_style.json"
        )
        # 旧版迁移：早期用户语料在 corpora/custom.jsonl，首次合并前搬入用户池
        try:
            legacy = os.path.join(self._corpora_dir, "custom.jsonl")
            if not os.path.exists(self._user_corpus_path) and os.path.exists(legacy):
                os.makedirs(os.path.dirname(self._user_corpus_path), exist_ok=True)
                shutil.copy(legacy, self._user_corpus_path)
                logger.info("[Humanizer] 已迁移旧语料池 corpora/custom.jsonl → 用户语料池")
        except Exception:  # noqa: BLE001
            pass
        self._imported_files: set[str] = set(self._load_style_state()["imported_files"])
        # 提炼防并发锁（同一时刻只跑一次 LLM 提炼/融合）
        self._building = False
        # 检索相关状态：知识库名 -> 是否已就绪；同步中集合防重复上传
        self._kb_ready: dict[str, bool] = {}
        self._kb_syncing: set[str] = set()
        # 自动提炼标记：无论成败，本次运行只尝试一次（避免反复调 LLM）
        self._auto_built = False
        # 风格启动任务句柄（initialize 中启动，terminate 清理）
        self._style_task: asyncio.Task | None = None
        # 动态注入配置界面选项（风格下拉 / embedding provider 下拉）
        try:
            self._inject_schema_options()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Humanizer] 注入配置选项失败: {e}")

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

    def _cfg(self, key: str, default=None):
        """读取"人类对话风格"分组的配置值。"""
        group = self.config.get("style")
        return group.get(key, default) if isinstance(group, dict) else default

    def _set_cfg(self, key: str, value) -> None:
        """写入"人类对话风格"分组的配置值（分组不存在时兜底创建）。"""
        group = self.config.setdefault("style", {})
        group[key] = value

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
        """插件激活时启动后台任务（框架生命周期钩子）。

        此时事件循环一定在运行，create_task 安全。基类默认空实现，
        这里覆盖以启动：主动聊天调度循环 + 风格启动任务（语料导入/自动提炼/
        配置驱动提炼/检索索引预同步，串行执行避免并发提炼冲突）。
        """
        if self._proactive_task is None:
            try:
                self._proactive_task = asyncio.create_task(self._proactive_loop())
            except RuntimeError:
                # 极端情况下事件循环仍不可用，静默放弃（terminate 兜底）
                self._proactive_task = None
        if self._style_task is None:
            try:
                # 不 await：_startup_tasks 内含 LLM 提炼，阻塞会拖慢整个启动
                self._style_task = asyncio.create_task(self._startup_tasks())
            except RuntimeError:
                self._style_task = None
                self._auto_built = True  # 无事件循环则跳过自动提炼

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
    def _style_rewrite_suffix(self) -> str:
        """构建追加到改写 Prompt 末尾的风格段（口癖/句式融合点）。

        口癖白名单是**动态**的：每次深度改写都实时读取当前用户启用的风格档案
        （find_profile + _effective_active_style 兜底），渲染该档案自己的
        catchphrases/sentence_patterns——不硬编码任何具体口癖。
        因此不同用户/不同人设下自动切换：新用户用随插件分发的「默认风格」，
        导入自己的语料提炼出专属风格后白名单随之变化，无需手动配置。

        与清理规则的冲突消解（写在指令里，让模型单次改写稳定输出）：
        - 口癖属于角色设定，不得被当作"填充短语/软化语气"删除；
        - 只删固定 AI 套话（值得注意的是/此外/至关重要等）；
        - 口癖与去痕冲突时保留口癖。

        style.enabled 关闭 / 无启用风格 / 档案缺失/字段全空时返回空串（不追加，
        行为同 v2.0.1）。
        """
        try:
            if not self._cfg("enabled", True):
                return ""
            active = self._effective_active_style()
            if not active:
                return ""
            profile = find_profile(self._styles_dir, active)
            if profile is None:
                return ""
            parts = []
            # 动态白名单：来自当前启用档案（用户语料提炼产物或分发的默认档案）
            catchphrases = [c for c in profile.get("catchphrases", []) if c][:5]
            patterns = [p for p in profile.get("sentence_patterns", []) if p][:4]
            emotions = [e for e in profile.get("emotion_expressions", []) if e][:3]
            if catchphrases:
                parts.append(
                    "口癖白名单（角色设定，不得视为填充短语或软化语气而删除；"
                    "偶尔自然使用，不强行堆砌）："
                    + "、".join(f"「{c}」" for c in catchphrases)
                )
            if patterns:
                parts.append("句式习惯：" + "；".join(patterns))
            if emotions:
                parts.append("情绪表达：" + "；".join(emotions))
            if not parts:
                return ""
            return (
                "\n\nAdditional style guidance（角色说话风格，优先级高于"
                "「删除填充短语/信任读者」等去痕规则；仅删除固定 AI 套话如"
                "「值得注意的是」「此外」「至关重要」，不要误删下方口癖；"
                "若口癖与去痕冲突，保留口癖；在不改变原意的前提下让文本"
                "自然带有这些特点）：\n- "
                + "\n- ".join(parts)
            )
        except Exception:  # noqa: BLE001
            return ""

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
                kwargs["system_prompt"] = SYSTEM_PROMPT + self._style_rewrite_suffix()
            else:
                # 旧版本不支持 system_prompt 参数，拼进 prompt 里
                kwargs["prompt"] = (
                    f"{SYSTEM_PROMPT}{self._style_rewrite_suffix()}"
                    f"\n\n待处理的文本：\n{text}"
                )

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

    # ------------------------------------------------------------------
    # 人类对话风格：配置界面动态选项 + 自定义语料（原 human_style 吸入）
    # ------------------------------------------------------------------
    @staticmethod
    def _embedding_provider_id(p) -> str:
        """从 embedding provider 实例取 id。

        EmbeddingProvider 基类没有 get_provider_id() 方法，
        需通过 meta().id 或 provider_config["id"] 取（见 astrbot/core/provider/provider.py）。
        """
        try:
            return str(p.provider_config.get("id", "") or "")
        except Exception:  # noqa: BLE001
            pass
        try:
            return str(p.meta().id or "")
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _inject_schema_options(self) -> None:
        """往配置 schema 里注入动态下拉选项，让 WebUI 显示可选值。

        - active_style：扫描 styles/ 目录的风格名
        - embedding_provider_id：已配置的 embedding provider id
        注入的是内存 schema 对象（WebUI 立即生效）；插件每次加载都会重建。

        注意：embedding provider 的实例化可能晚于插件 __init__（异步加载），
        因此 __init__ 里注入可能拿到空列表；on_astrbot_loaded 钩子会在框架
        加载完成后再次注入补齐。
        """
        try:
            schema = self.config.schema
            if not isinstance(schema, dict):
                return
            style_group = schema.get("style", {}).get("items", {})
            if not isinstance(style_group, dict):
                return
            # 风格下拉
            names = list_profile_names(self._styles_dir)
            active = style_group.get("active_style")
            if isinstance(active, dict):
                active["options"] = names
            # embedding provider 下拉
            try:
                providers = self.context.get_all_embedding_providers()
                options = []
                for p in providers:
                    pid = self._embedding_provider_id(p)
                    if pid:
                        options.append(pid)
                emb = style_group.get("embedding_provider_id")
                if isinstance(emb, dict):
                    emb["options"] = options
            except Exception:  # noqa: BLE001
                # provider 尚未加载时留空下拉，运行时自动探测兜底
                pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 配置选项注入失败: {e}")

    @filter.on_astrbot_loaded()
    async def _on_astrbot_loaded(self) -> None:
        """框架加载完成：embedding provider 已就绪，重新注入配置选项。"""
        try:
            self._inject_schema_options()
            emb_options = self._get_schema_option("embedding_provider_id")
            if emb_options:
                logger.info(f"[HumanStyle] embedding provider 选项已就绪: {emb_options}")
            else:
                logger.warning("[HumanStyle] 未发现已启用的 embedding provider（WebUI 下拉将为空）")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 框架加载后重新注入配置选项失败: {e}")

    def _get_schema_option(self, key: str) -> list:
        """读取 schema 中某配置项当前的 options（用于调试/验证）。"""
        try:
            schema = self.config.schema
            style_group = schema.get("style", {}).get("items", {})
            item = style_group.get(key, {})
            if isinstance(item, dict):
                return item.get("options", [])
        except Exception:  # noqa: BLE001
            pass
        return []

    def _effective_corpus_rows(self) -> list[dict]:
        """有效语料 = 内置 base 池 + 用户导入池 合并（跨池去重）。

        每行额外注入 source 字段（builtin/user），供检索按来源分组展示。
        返回拷贝而非原地修改，避免污染 pool_stats 等纯计数函数读到的行。
        """
        base = read_pool(os.path.join(self._corpora_dir, "base.jsonl"))
        user = read_pool(self._user_corpus_path)
        tagged = [dict(r, source="builtin") for r in base] + [
            dict(r, source="user") for r in user
        ]
        return merge_pool_rows(tagged)

    def _load_style_state(self) -> dict:
        """读取风格插件状态（已导入语料文件列表）。"""
        try:
            with open(self._state_style_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"imported_files": []}

    def _save_style_state(self) -> None:
        try:
            data = {
                "imported_files": sorted(self._imported_files),
            }
            with open(self._state_style_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning(f"[HumanStyle] 状态保存失败: {e}")

    async def _load_custom_corpus_files(self) -> None:
        """读取配置里用户上传的自定义语料文件，导入用户语料池（与 base 结合）。

        file 类型配置存相对路径（files/...，位于 data/plugin_data/<本插件名>/ 下）；
        幂等：追加去重，重复加载不会产生重复数据。
        """
        try:
            files = self._cfg("custom_corpus_files") or []
            if not isinstance(files, list) or not files:
                return
            # 插件数据目录（file 上传落地处；兼容原 human_style 插件的上传目录）
            base_dir = None
            try:
                from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

                pd = get_astrbot_plugin_data_path()
                mine = os.path.join(pd, "astrbot_plugin_humanizer")
                legacy = os.path.join(pd, "astrbot_plugin_human_style")
                base_dir = mine
                self._style_upload_dirs = [mine, legacy]
            except Exception:  # noqa: BLE001
                base_dir = None
                self._style_upload_dirs = []
            imported = 0
            for rel in files:
                if not isinstance(rel, str) or rel in self._imported_files:
                    continue
                abs_path = ""
                if os.path.isabs(rel):
                    abs_path = rel
                else:
                    for d in getattr(self, "_style_upload_dirs", [base_dir] if base_dir else []):
                        cand = os.path.join(d, rel)
                        if os.path.isfile(cand):
                            abs_path = cand
                            break
                if not abs_path or not os.path.isfile(abs_path):
                    continue
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    pairs = parse_corpus_text(text, os.path.basename(abs_path))
                    added = append_pairs_to_pool(self._user_corpus_path, pairs)
                    self._imported_files.add(rel)
                    self._save_style_state()
                    imported += added
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[HumanStyle] 自定义语料 {rel} 导入失败: {e}")
            if imported:
                logger.info(f"[HumanStyle] 自定义语料已导入 {imported} 对到用户语料池（与内置语料结合）")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 自定义语料加载失败: {e}")

    async def _maybe_extract_from_config(self) -> None:
        """配置界面驱动的提炼动作（不阻塞启动，失败静默）。

        1. 上传新语料 + auto_extract_on_upload → 自动提炼「我的风格」并启用
        2. rebuild_style 勾选 → 用有效语料重新提炼当前启用风格并自动复位开关
        """
        try:
            # 场景 2：rebuild_style 触发器优先（用户显式勾选）
            if self._cfg("rebuild_style", False):
                target = str(self._cfg("active_style") or "").strip() or "我的风格"
                logger.info(f"[HumanStyle] 配置触发：重新提炼风格「{target}」…")
                await self._build_profile(target, n=50, reply_to=None)
                self._set_cfg("rebuild_style", False)
                await self.config.save_config_async()
                logger.info(f"[HumanStyle] 风格「{target}」已重新提炼")
                return
            # 场景 1：检测新增上传的语料文件（先确保已导入进用户池，再提炼）
            files = self._cfg("custom_corpus_files") or []
            new = new_files(files, sorted(self._imported_files))
            if not new:
                return
            await self._load_custom_corpus_files()
            if not self._cfg("auto_extract_on_upload", True):
                return
            logger.info(f"[HumanStyle] 检测到 {len(new)} 个新上传语料文件，自动提炼「我的风格」…")
            await self._build_profile("我的风格", n=50, reply_to=None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 配置驱动提炼失败（已跳过）: {e}")

    async def _startup_tasks(self) -> None:
        """风格启动初始化任务（串行执行，避免并发提炼冲突）。

        1. 导入配置里上传的自定义语料文件
        2. 确保有默认风格（无档案时自动提炼）
        3. 配置界面驱动的提炼动作（新上传自动提炼 / rebuild_style）
        4. 后台预同步检索索引（首条消息到达时知识库已就绪）
        """
        try:
            await self._load_custom_corpus_files()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 启动导入自定义语料失败: {e}")
        try:
            await self._maybe_auto_build_default()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 自动默认风格失败: {e}")
        try:
            await self._maybe_extract_from_config()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 配置驱动提炼失败: {e}")
        try:
            if self._cfg("create_kb", True) and self._cfg("enable_retrieval", True):
                style_name = self._effective_active_style()
                if style_name:
                    kb_name = self._kb_name(style_name)
                    if not self._kb_ready.get(kb_name):
                        await self._ensure_kb(kb_name, style_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 启动预同步检索索引失败: {e}")

    def _effective_active_style(self) -> str:
        """当前生效风格：优先配置的 active_style；为空时兜底用 styles 里第一个档案。

        保证「当前启用风格」与实际生效状态永远一致——即使后台自动提炼尚未完成，
        或配置页显示为空，回复也已带上第一套可用风格。
        """
        active = str(self._cfg("active_style") or "").strip()
        if active and find_profile(self._styles_dir, active) is not None:
            return active
        names = list_profile_names(self._styles_dir)
        if names:
            # 顺手持久化兜底结果，让配置页下次读取即显示实际生效风格
            if active != names[0]:
                self._set_cfg("active_style", names[0])
                try:
                    asyncio.ensure_future(self.config.save_config_async())
                except (RuntimeError, Exception):  # noqa: BLE001
                    pass
            return names[0]
        return ""

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req) -> None:
        """在 LLM 生成前注入风格指令（基础）+ 检索示例（进阶，可选）。

        任何异常都静默跳过注入，绝不影响回复。
        """
        if not self._cfg("enabled", True):
            return
        try:
            active = self._effective_active_style()
            if not active:
                return
            profile = find_profile(self._styles_dir, active)
            if profile is None:
                return
            section = inject.build_style_section(profile)
            if not section:
                return
            req.system_prompt = (req.system_prompt or "") + "\n" + section

            # 进阶：检索相似人类对话片段作为示例
            if self._cfg("enable_retrieval", False):
                examples = await self._retrieve_examples(event, profile)
                if examples:
                    req.system_prompt += "\n" + examples
        except Exception as e:  # noqa: BLE001
            if self._cfg("debug", False):
                logger.warning(f"[HumanStyle] 注入失败（已跳过）: {e}")

    async def _retrieve_examples(self, event: AstrMessageEvent, profile: dict) -> str:
        """按当前用户消息检索语料池 top-k 片段，渲染为示例段。

        失败/未配置 embedding 时返回空字符串（静默回退纯风格注入）。
        """
        query = getattr(event, "message_str", None) or ""
        if not query.strip():
            return ""
        kb_name = self._kb_name(profile["name"])
        try:
            kb = await self._ensure_kb(kb_name, profile["name"])
            if kb is None:
                return ""
            top_k = int(self._cfg("retrieve_top_k", 3) or 3)
            top_k = max(1, min(top_k, 5))
            result = await self.context.kb_manager.retrieve(
                query, kb_names=[kb_name], top_k_fusion=top_k, top_m_final=top_k
            )
            rows = self._flatten_kb_results(result)
            if not rows:
                return ""
            return inject.build_example_section(rows, top_k)
        except Exception as e:  # noqa: BLE001
            if self._cfg("debug", False):
                logger.warning(f"[HumanStyle] 检索失败（已回退纯风格注入）: {e}")
            return ""

    def _kb_name(self, style_name: str) -> str:
        safe = "".join(c if c.isalnum() else "_" for c in style_name)
        return f"human_style_{safe}"

    async def _ensure_kb(self, kb_name: str, style_name: str):
        """确保知识库存在且已同步语料池。返回 kb 名；不可用时返回 None。

        索引建在「有效语料」上（内置 base + 用户导入合并），
        保证用户导入的语料也参与检索。

        防重复机制：
        - 同步进行中（_kb_syncing）→ 直接返回 None（不重复触发上传）
        - 知识库已有分组文档 → 视为已同步，跳过上传（重启不重传）
        - 失败 → 负缓存（_kb_ready[kb]=False），本运行不再重试（/style_index 可手动重建）
        """
        if self._kb_ready.get(kb_name):
            return kb_name
        if kb_name in self._kb_syncing:
            return None  # 同步中，跳过本次（不阻塞、不重复上传）
        if not self._cfg("create_kb", True):
            # 用户关闭「自动创建检索知识库」：不建库、不检索
            self._kb_ready[kb_name] = False
            return None
        kb_manager = getattr(self.context, "kb_manager", None)
        if kb_manager is None or not hasattr(kb_manager, "create_kb"):
            logger.warning("[HumanStyle] 框架不支持 kb_manager，检索功能禁用")
            self._kb_ready[kb_name] = False
            return None
        # 取 embedding provider id：优先配置，其次自动探测，都没有则禁用
        embedding_id = self._resolve_embedding_provider()
        if not embedding_id:
            logger.warning(
                "[HumanStyle] 未配置 embedding provider，检索功能禁用"
                "（AstrBot 设置中配置 embedding 后可开启）"
            )
            self._kb_ready[kb_name] = False
            return None
        rows = self._effective_corpus_rows()
        texts = [r.get("content", "") for r in rows if r.get("content", "").strip()]
        if not texts:
            self._kb_ready[kb_name] = False
            return None

        builtin_cnt = sum(1 for r in rows if r.get("source") == "builtin")
        user_cnt = sum(1 for r in rows if r.get("source") == "user")
        desc = (
            f"人类对话风格 · 检索库 · 风格「{style_name}」"
            f" · 有效语料 内置 {builtin_cnt} + 用户 {user_cnt} = {len(rows)} 条"
            f" · 由 astrbot_plugin_humanizer 自动创建，请勿手动删除；"
            f"关闭“自动创建检索知识库”或删除此库不影响风格档案"
        )
        self._kb_syncing.add(kb_name)
        try:
            # 复用已存在的知识库（插件重载后不重复创建），否则创建
            kb = await kb_manager.get_kb_by_name(kb_name)
            if kb is None:
                kb = await kb_manager.create_kb(
                    kb_name, description=desc, embedding_provider_id=embedding_id
                )
            else:
                # 存量描述刷新：旧库实时更新配比
                try:
                    if getattr(kb.kb, "description", None) != desc:
                        await kb_manager.update_kb(kb.kb.kb_id, description=desc)
                        kb.kb.description = desc
                except Exception:  # noqa: BLE001
                    pass
            # 按来源分组准备上传文本（提前计算，供完整性检测与上传共用）
            builtin_texts = [r["content"] for r in rows if r.get("source") == "builtin" and r.get("content", "").strip()]
            user_texts = [r["content"] for r in rows if r.get("source") == "user" and r.get("content", "").strip()]
            upload_groups = [("__内置_", builtin_texts), ("__用户_", user_texts)]
            batch = 200
            # 已同步检测：按文档名前缀统计实际文档数，与期望批数比对——
            # 只看"前缀存在"会漏掉同步中断导致的缺块；不完整的分组删除后整组重传（幂等）
            try:
                if hasattr(kb, "list_documents"):
                    docs = await kb.list_documents()
                    names = [getattr(d, "doc_name", "") for d in docs]
                    group_status = []
                    for prefix, group_texts in upload_groups:
                        if not group_texts:
                            group_status.append((prefix, group_texts, True))
                            continue
                        expected = (len(group_texts) + batch - 1) // batch
                        actual = sum(1 for n in names if f"{kb_name}{prefix}" in n)
                        group_status.append((prefix, group_texts, actual >= expected))
                    if group_status and all(ok for _, _, ok in group_status):
                        self._kb_ready[kb_name] = True
                        logger.info(f"[HumanStyle] 知识库 {kb_name} 各分组批数齐全，跳过上传")
                        return kb_name
                    # 不完整分组：删除该前缀的现有文档，整组重传（修复中断缺块）
                    for prefix, group_texts, is_complete in group_status:
                        if group_texts and not is_complete:
                            for d in docs:
                                dn = getattr(d, "doc_name", "")
                                if f"{kb_name}{prefix}" in dn:
                                    try:
                                        await kb.delete_document(getattr(d, "doc_id", ""))
                                    except Exception:  # noqa: BLE001
                                        pass
                            logger.info(f"[HumanStyle] 知识库 {kb_name}{prefix} 分组不完整，已清除待重传")
                elif user_cnt == 0:
                    existing = await kb.count_documents()
                    if existing and existing > 0:
                        self._kb_ready[kb_name] = True
                        logger.info(f"[HumanStyle] 知识库 {kb_name} 已有 {existing} 个文档，跳过上传")
                        return kb_name
            except Exception:  # noqa: BLE001
                pass
            # 写入文档：按来源分组上传，file_name 前缀 __内置_ / __用户_ 在 WebUI DocumentsTab 全链可见
            for prefix, group_texts in upload_groups:
                if not group_texts:
                    continue
                for i in range(0, len(group_texts), batch):
                    chunk = group_texts[i:i + batch]
                    try:
                        await kb.upload_document(
                            file_name=f"{kb_name}{prefix}{i}.txt",
                            file_content=None,
                            file_type="txt",
                            pre_chunked_text=chunk,
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[HumanStyle] 语料写入知识库 {prefix}{i} 批失败: {e}")
            self._kb_ready[kb_name] = True
            logger.info(f"[HumanStyle] 有效语料已同步到知识库 {kb_name}（内置 {builtin_cnt} + 用户 {user_cnt} = {len(texts)} 条）")
            return kb_name
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 知识库初始化失败，检索禁用: {e}")
            self._kb_ready[kb_name] = False
            return None
        finally:
            self._kb_syncing.discard(kb_name)

    def _resolve_embedding_provider(self) -> str:
        """解析 embedding provider id。

        优先用户配置的 embedding_provider_id；配置为空或不可用时，
        自动探测第一个已配置的 embedding provider；都没有则返回空（检索禁用）。
        """
        configured = str(self._cfg("embedding_provider_id") or "").strip()
        try:
            providers = self.context.get_all_embedding_providers()
            if not providers:
                return ""
            if configured:
                for p in providers:
                    pid = self._embedding_provider_id(p)
                    if pid == configured:
                        return pid
                # 配置的 id 不在已配置 providers 中：回落自动探测
                logger.warning(
                    f"[HumanStyle] 配置的 embedding provider {configured!r} 不可用，自动探测替代"
                )
            first = providers[0]
            return self._embedding_provider_id(first)
        except Exception:  # noqa: BLE001
            return ""

    def _flatten_kb_results(self, result) -> list[dict]:
        """框架 kb_manager.retrieve() 返回结构 → 语料池行列表。"""
        try:
            if result is None:
                return []
            if isinstance(result, dict):
                results = result.get("results", [])
            elif isinstance(result, list):
                results = result
            else:
                return []
            rows = []
            for i, item in enumerate(results):
                if not isinstance(item, dict):
                    continue
                content = item.get("content") or item.get("chunk") or item.get("text")
                if content:
                    role = "user" if i % 2 == 0 else "assistant"
                    rows.append({"role": role, "content": str(content).strip()})
            return rows
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------------
    # 人类对话风格：管理命令（原 human_style 吸入）
    # ------------------------------------------------------------------
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("style_list")
    async def style_list(self, event: AstrMessageEvent, arg: str = "") -> None:
        """列出所有风格档案 + 当前启用项。"""
        profiles = list_profiles(self._styles_dir)
        if not profiles:
            await event.send(
                "没有任何风格档案。\n"
                "用 /style_build base 从内置语料提炼，或 /style_import 导入自己的语料。"
            )
            return
        active = str(self._cfg("active_style") or "")
        lines = ["可用的说话风格档案："]
        for p in profiles:
            mark = " → 启用中" if p["name"] == active else ""
            desc = p.get("description", "")
            lines.append(f"- {p['name']}{mark}{('：' + desc) if desc else ''}")
        lines.append(f"\n用 /style_use <名称> 切换。检索注入：{'开' if self._cfg('enable_retrieval', False) else '关'}")
        await event.send("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("style_use")
    async def style_use(self, event: AstrMessageEvent, arg: str = "") -> None:
        """启用某风格：/style_use <名称>。"""
        name = (arg or "").strip()
        if not name:
            active = str(self._cfg("active_style") or "")
            await event.send(f"当前启用风格：{active or '（无）'}。用 /style_use <名称> 切换。")
            return
        profile = find_profile(self._styles_dir, name)
        if profile is None:
            names = ", ".join(p["name"] for p in list_profiles(self._styles_dir)) or "（无）"
            await event.send(f"找不到风格 {name!r}。可用：{names}")
            return
        self._set_cfg("active_style", profile["name"])
        await self.config.save_config_async()
        await event.send(f"已启用风格：{profile['name']}。之后每条回复都会带上这套说话风格。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("style_import")
    async def style_import(self, event: AstrMessageEvent, arg: str = "") -> None:
        """导入语料：/style_import <文件路径|语料文本>。

        导入的语料进入「用户语料池」，与内置 base 自动合并参与提炼与检索。
        兼容旧式调用：/style_import <风格名> <文件|文本>（忽略风格名，统一进用户池）。
        """
        parts = arg.split(maxsplit=2)
        if not parts:
            await event.send(
                "用法：/style_import <文件路径|语料文本>\n"
                "支持 txt（每行一句）、jsonl、json 数组、csv。"
            )
            return
        # 旧式 `<名称> <文件|文本>` 或 `<文件|文本>` 兼容
        if len(parts) >= 2:
            body = parts[1].strip()
            # 若首个参数不像文件/文本（长度短且含中文/名称），视为旧式名称
            first = parts[0].strip()
            candidate0 = os.path.expanduser(first)
            if os.path.isfile(candidate0) or len(first) > 16 or not first:
                body = first
        else:
            body = parts[0].strip()

        text = body
        filename = ""
        candidate = os.path.expanduser(body)
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                filename = os.path.basename(candidate)
            except OSError as e:
                await event.send(f"读取文件失败：{e}")
                return

        pairs = parse_corpus_text(text, filename)
        if not pairs:
            await event.send("未能从输入中解析出有效对话对（内容过短或格式无法识别）。")
            return

        added = append_pairs_to_pool(self._user_corpus_path, pairs)
        if added == 0:
            await event.send(
                f"没有新增内容（全部重复）。用户语料池当前 {pool_stats(self._user_corpus_path)['pairs']} 对。"
            )
            return
        await event.send(
            f"已导入 {added} 对到用户语料池（与内置 base 自动结合，共 "
            f"{pool_stats(self._user_corpus_path)['pairs']} 对）。\n"
            "用 /style_build <风格名> 提炼，或 /style_refine <风格名> <新语料> 增量融合。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("style_build")
    async def style_build(self, event: AstrMessageEvent, arg: str = "") -> None:
        """全量提炼：/style_build <风格名> [样本数]。用「有效语料」（base+用户导入合并）提炼档案。"""
        parts = arg.split()
        if not parts:
            await event.send("用法：/style_build <风格名> [样本数]。样本数默认 50。")
            return
        name = parts[0].strip()
        n = 50
        if len(parts) > 1 and parts[1].isdigit():
            n = int(parts[1])
        if self._building:
            await event.send("已有提炼任务在运行，请稍后再试。")
            return
        if not self._effective_corpus_rows():
            await event.send("有效语料为空（内置语料池缺失且无用户语料）。")
            return
        await self._build_profile(name, n=n, reply_to=event)

    async def _build_profile(self, name: str, n: int, reply_to: AstrMessageEvent | None,
                             pool_name: str | None = None) -> None:
        """从「有效语料」采样 n 句 → LLM 提炼档案 → 保存。

        有效语料 = 内置 base 池 + 用户导入池 合并（用户语料优先采样）；
        用户导入的语料与插件本体语料始终结合参与提炼。
        pool_name 参数保留仅为兼容旧调用，实际始终使用有效语料。
        """
        base = read_pool(os.path.join(self._corpora_dir, "base.jsonl"))
        user = read_pool(self._user_corpus_path)
        sampled = sample_merged(base, user, n * 2)  # 行数 = 句子数（user/assistant 各算一句）
        sentences = [r.get("content", "") for r in sampled if r.get("content", "").strip()]
        if len(sentences) < 4:
            if reply_to:
                await reply_to.send("有效语料太少了（不足 4 句），无法提炼。")
            return
        prompt = build_extract_prompt(sentences)
        result = await self._call_llm_for_profile(prompt, reply_to)
        if result is None:
            return
        profile = normalize_profile(result)
        # 保证 name 与命令一致（LLM 可能起别的名）
        profile["name"] = name
        save_profile_file(self._styles_dir, profile)
        self._set_cfg("active_style", name)
        await self.config.save_config_async()
        # 刷新配置界面的风格下拉（新风格立即可选）
        self._inject_schema_options()
        if reply_to:
            await reply_to.send(
                f"风格档案「{name}」已生成并启用（基于有效语料）。\n"
                f"人设：{profile.get('persona', '')}\n"
                f"口癖：{'、'.join('「' + c + '」' for c in profile.get('catchphrases', [])[:5]) or '无'}\n"
                "用 /style_list 查看所有档案。"
            )

    async def _maybe_auto_build_default(self) -> None:
        """首次使用确保有可用风格（语料驱动为主体）。

        优先级：
        1. 已有启用风格 → 不动
        2. styles/ 已有档案（如随插件分发的语料预提炼档案）→ 直接启用，不重复调 LLM
        3. 都没有 → 从内置语料池 base 自动提炼「默认风格」
        无论成败只尝试一次（本次运行不再重试，避免反复消耗 LLM）。
        """
        if self._auto_built:
            return
        self._auto_built = True
        try:
            if not self._cfg("auto_build_default", True):
                return
            if str(self._cfg("active_style") or "").strip():
                return  # 已有启用风格（升级用户），不覆盖
            names = list_profile_names(self._styles_dir)
            if names:
                # 已有档案（随插件分发的语料预提炼档案）：直接启用
                self._set_cfg("active_style", names[0])
                await self.config.save_config_async()
                self._inject_schema_options()
                logger.info(f"[HumanStyle] 已启用现有风格档案: {names[0]}")
                return
            pool_path = os.path.join(self._corpora_dir, "base.jsonl")
            stats = pool_stats(pool_path)
            if stats["empty"] and pool_stats(self._user_corpus_path)["empty"]:
                return
            logger.info("[HumanStyle] 首次使用：正在用有效语料自动提炼默认风格…")
            await self._build_profile("默认风格", n=50, reply_to=None)
            logger.info("[HumanStyle] 默认风格已自动生成并启用")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] 自动提炼默认风格失败: {e}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("style_refine")
    async def style_refine(self, event: AstrMessageEvent, arg: str = "") -> None:
        """增量融合：/style_refine <风格名> <新语料文件|文本>。旧档案 + 新语料 → 融合版。"""
        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            await event.send("用法：/style_refine <风格名> <新语料文件|文本>。")
            return
        name = parts[0].strip()
        body = parts[1].strip()
        profile = find_profile(self._styles_dir, name)
        if profile is None:
            await event.send(f"找不到风格 {name!r}。先用 /style_build 或 /style_import 生成档案。")
            return
        text = body
        filename = ""
        candidate = os.path.expanduser(body)
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                filename = os.path.basename(candidate)
            except OSError as e:
                await event.send(f"读取文件失败：{e}")
                return
        pairs = parse_corpus_text(text, filename)
        if not pairs:
            await event.send("未能从输入中解析出有效对话对。")
            return
        # 新语料并入用户语料池（与 base 结合，之后全量重建也包含它）
        append_pairs_to_pool(self._user_corpus_path, pairs)
        if self._building:
            await event.send("已有提炼任务在运行，请稍后再试。")
            return
        # 采样新语料句子
        all_new = []
        for u, a in pairs:
            all_new.append(u)
            all_new.append(a)
        import random as _random
        rng = _random.Random(42)
        sentences = rng.sample(all_new, min(60, len(all_new)))
        prompt = build_refine_prompt(profile, sentences)
        await event.send("正在融合新旧语料，生成更新后的风格档案…")
        result = await self._call_llm_for_profile(prompt, event)
        if result is None:
            return
        new_profile = normalize_profile(result)
        new_profile["name"] = name
        save_profile_file(self._styles_dir, new_profile)
        self._set_cfg("active_style", name)
        await self.config.save_config_async()
        await event.send(
            f"风格档案「{name}」已融合更新。\n"
            f"人设：{new_profile.get('persona', '')}\n"
            f"口癖：{'、'.join('「' + c + '」' for c in new_profile.get('catchphrases', [])[:5]) or '无'}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("style_index")
    async def style_index(self, event: AstrMessageEvent, arg: str = "") -> None:
        """手动重建检索索引：/style_index <风格名>。语料池变化后同步知识库。"""
        name = (arg or "").strip()
        if not name:
            await event.send("用法：/style_index <风格名>。")
            return
        kb_name = self._kb_name(name)
        self._kb_ready.pop(kb_name, None)
        self._kb_syncing.discard(kb_name)
        kb = await self._ensure_kb(kb_name, name)
        if kb is None:
            await event.send(
                "检索索引未建立：语料池为空，或未配置 embedding provider"
                "（AstrBot 设置中配置 embedding 后可开启）。"
            )
            return
        await event.send(f"检索索引已同步：{kb_name}。")

    # ------------------------------------------------------------------
    # 人类对话风格：LLM 提炼调用
    # ------------------------------------------------------------------
    @staticmethod
    def _chat_provider_id(p) -> str:
        """从 chat Provider 实例取 id。

        Provider 基类没有 get_provider_id() 方法，需通过
        provider_config["id"] 或 meta().id 取（见 astrbot/core/provider/provider.py）。
        """
        try:
            return str(p.provider_config.get("id", "") or "")
        except Exception:  # noqa: BLE001
            pass
        try:
            return str(p.meta().id or "")
        except Exception:  # noqa: BLE001
            pass
        return ""

    async def _call_llm_for_profile(self, prompt: str, reply_to: AstrMessageEvent | None) -> dict | None:
        """调用 LLM 提炼/融合，返回档案 dict；失败返回 None（并尝试向 reply_to 报错）。"""
        if self._building:
            return None
        self._building = True
        try:
            provider_id = None
            try:
                umo = getattr(reply_to, "unified_msg_origin", None) if reply_to else None
                provider_id = await self.context.get_current_chat_provider_id(umo)
            except Exception:  # noqa: BLE001
                provider_id = None
            if not provider_id:
                # 兜底：取第一个已加载的 chat provider
                try:
                    providers = self.context.get_all_providers()
                    if providers:
                        provider_id = self._chat_provider_id(providers[0])
                except Exception:  # noqa: BLE001
                    pass
            if not provider_id:
                if reply_to:
                    await reply_to.send("当前未配置可用的模型提供商，无法提炼。")
                return None
            kwargs = {"chat_provider_id": provider_id, "prompt": prompt}
            # extract_model 可能是三种形态：
            #   1. 空 → 跟随当前会话模型
            #   2. 完整 provider id（ProviderSelector 存储格式，如 xiaomi-token-plan/mimo-v2.5-pro）
            #      → 用该实例作 chat_provider_id，model 取其实例模型（避免把完整 id 当 model 传给 API）
            #   3. 裸模型名 → 在当前会话 provider 上切换模型
            configured = str(self._cfg("extract_model") or "").strip()
            model_name = None
            if configured:
                if "/" in configured:
                    try:
                        inst = self.context.get_provider_by_id(configured)
                    except Exception:  # noqa: BLE001
                        inst = None
                    if inst is not None:
                        # 形态 2：完整 provider id 命中
                        kwargs["chat_provider_id"] = configured
                        try:
                            model_name = inst.get_model() or None
                        except Exception:  # noqa: BLE001
                            model_name = None
                    else:
                        # 形态 3：pid/model 或裸名，取后半段作模型名
                        model_name = configured.partition("/")[2] or configured
                else:
                    model_name = configured
            if model_name:
                kwargs["model"] = model_name
            if self._llm_supports_system_prompt is None:
                try:
                    self._llm_supports_system_prompt = (
                        "system_prompt" in inspect.signature(self.context.llm_generate).parameters
                    )
                except (TypeError, ValueError):
                    self._llm_supports_system_prompt = False
            llm_resp = await self.context.llm_generate(**kwargs)
            text = getattr(llm_resp, "completion_text", None) or ""
            data = parse_profile_json(text)
            if data is None:
                if reply_to:
                    await reply_to.send("LLM 返回内容无法解析为有效的风格档案，请重试。")
                return None
            err = validate_profile(data)
            if err is not None:
                if reply_to:
                    await reply_to.send(f"LLM 输出的档案不合法（{err}），请重试。")
                return None
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[HumanStyle] LLM 提炼失败: {e}")
            if reply_to:
                await reply_to.send(f"LLM 调用失败：{e}")
            return None
        finally:
            self._building = False

    async def terminate(self):
        """插件卸载/停用时调用。"""
        # 停用前保存主动聊天状态（重启/停用后仍保留"聊过会话"跟踪）
        self._save_proactive_state()
        self._rewriting.clear()
        self._kb_ready.clear()
        if self._style_task:
            self._style_task.cancel()
            try:
                await self._style_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._style_task = None
        if self._proactive_task:
            self._proactive_task.cancel()
            try:
                await self._proactive_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._proactive_task = None
