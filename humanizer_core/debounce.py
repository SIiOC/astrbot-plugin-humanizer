"""
聊天防抖核心逻辑（纯逻辑层）。

出处与许可：防抖能力衍生自 aliveriver 的 astrbot_plugin_continuous_message
（AGPL-3.0，https://github.com/aliveriver/astrbot_plugin_continuous_message），
经独立插件 astrbot_plugin_chat_debounce 修复已知问题后于 v3.2.0 并入本插件。
依据 AGPL-3.0 保留出处；本插件整体以 GNU AGPL-3.0 及其后版本（任选）分发，
源码：https://github.com/SIiOC/astrbot-plugin-humanizer。零 astrbot 依赖，可独立单测。

本模块不依赖 AstrBot 运行时，可独立单元测试：
- 自适应等待时长的计算规则（全部参数集中为模块级常量表，便于调参）
- DebounceEngine：会话表、可重置计时器、统一的结算请求入口

设计要点（相对上游原型的已知问题修复）：
- 所有"立即结算"路径统一走 _request_flush()：先取消计时器再置位事件，
  杜绝撤回清空等路径遗留旧计时器、误触发下一轮会话（原版缺陷 1）；
- 计时器协程持有会话对象引用并做代际校验（sessions[uid] is session），
  即使计时器意外泄漏，也不可能触发到另一轮会话；
- 输入状态暂停/恢复保留"剩余等待"，不再丢弃自适应状态（原版缺陷）；
- wait_flush() 带硬死线兜底，计时器丢失或用户持续输入时仍能结算。
"""

import asyncio
import logging
import time
from collections import namedtuple
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("humanizer.debounce")

# ===================== 自适应防抖参数表 =====================

# 消息长度分桶：(长度上限, 基础等待秒数, 原因标签)；超过最后一段使用 VERY_LONG_BASE_WAIT
LENGTH_BUCKETS: List[Tuple[int, float, str]] = [
    (3, 4.0, "very_short"),
    (10, 3.2, "short"),
    (30, 2.7, "medium"),
    (80, 1.8, "long"),
]
VERY_LONG_BASE_WAIT = 1.0
VERY_LONG_LABEL = "very_long"

# 结尾标点修正
UNFINISHED_ENDINGS = ("...", "…", "，", "、", "：", ":")  # 话没说完，愿意继续等
UNFINISHED_BONUS = 1.8
QUESTION_ENDINGS = ("？", "?")
QUESTION_DISCOUNT = 0.8
SENTENCE_ENDINGS = ("。", "！", "!")
SENTENCE_DISCOUNT = 0.5
# 无标点结尾（口语化断句）按长度追加
PLAIN_END_PUNCT_CHARS = "。！？!?，、：:；;,.…"
PLAIN_END_BONUS: List[Tuple[int, float]] = [
    (10, 0.8),
    (30, 0.7),
    (80, 0.3),
]

# 连续短句加成：连续第 N 条短消息时的追加等待（取满足的最高档）
SHORT_STREAK_BONUS: List[Tuple[int, float]] = [
    (2, 0.3),
    (3, 0.6),
    (4, 0.8),
]

# 停止输入后恢复计时的最小等待（剩余可能已为负，钳到该值尽快结算）
RESUME_MIN_WAIT = 0.5

SubmitResult = namedtuple("SubmitResult", ["action", "wait", "reason"])
# action: "started" 新会话（调用方需等待并结算）| "appended" 追加并重置计时 | "flushed" 立即结算


class DebounceEngine:
    """私聊消息防抖引擎。

    会话字段：
      uid, buffer(文本列表), images(图片列表), items(含 message_id 明细),
      flush_event(asyncio.Event), timer_task, is_typing,
      started_at(首条时间戳), pending_wait/timer_started_at(被输入状态打断前的计时快照),
      last_wait, short_message_count
    """

    def __init__(
        self,
        debounce_time: float = 2.0,
        enable_adaptive_debounce: bool = True,
        adaptive_min_wait: float = 1.0,
        adaptive_max_wait: float = 6.0,
        adaptive_max_total_wait: float = 12.0,
        adaptive_short_message_threshold: int = 10,
        max_session_wait: float = 60.0,
        now_fn: Callable[[], float] = time.monotonic,
    ):
        self.debounce_time = debounce_time
        self.enable_adaptive_debounce = enable_adaptive_debounce
        self.adaptive_min_wait = adaptive_min_wait
        self.adaptive_max_wait = adaptive_max_wait
        self.adaptive_max_total_wait = adaptive_max_total_wait
        self.adaptive_short_message_threshold = adaptive_short_message_threshold
        self.max_session_wait = max_session_wait
        self._now = now_fn
        self.sessions: Dict[str, dict] = {}

    # ---------------- 查询 ----------------

    def has_session(self, uid: str) -> bool:
        return uid in self.sessions

    def get_session(self, uid: str) -> Optional[dict]:
        return self.sessions.get(uid)

    def pop_session(self, uid: str) -> Optional[dict]:
        return self.sessions.pop(uid, None)

    # ---------------- 等待时长计算 ----------------

    def _is_short_message(self, text: str) -> bool:
        return len((text or "").strip()) <= self.adaptive_short_message_threshold

    def calculate_wait(
        self, text: str, session: Optional[dict] = None
    ) -> Tuple[float, bool, str]:
        """根据消息形态计算下一轮等待；返回 (等待秒数, 是否立即结算, 原因)。"""
        if not self.enable_adaptive_debounce:
            return self.debounce_time, False, "fixed_debounce"

        clean = (text or "").strip()
        length = len(clean)
        reasons: List[str] = []

        wait = VERY_LONG_BASE_WAIT
        label = VERY_LONG_LABEL
        for cap, bucket_wait, bucket_label in LENGTH_BUCKETS:
            if length <= cap:
                wait = bucket_wait
                label = bucket_label
                break
        reasons.append(label)

        if clean.endswith(UNFINISHED_ENDINGS):
            wait += UNFINISHED_BONUS
            reasons.append("unfinished_punctuation")
        elif clean.endswith(QUESTION_ENDINGS):
            wait -= QUESTION_DISCOUNT
            reasons.append("question_end")
        elif clean.endswith(SENTENCE_ENDINGS):
            wait -= SENTENCE_DISCOUNT
            reasons.append("sentence_end")
        elif clean and clean[-1] not in PLAIN_END_PUNCT_CHARS:
            for cap, bonus in PLAIN_END_BONUS:
                if length <= cap:
                    wait += bonus
                    break
            reasons.append("chat_plain_end")

        if session is not None:
            count = self._bump_short_streak(session, clean)
            streak_bonus = 0.0
            for threshold, bonus in SHORT_STREAK_BONUS:
                if count >= threshold:
                    streak_bonus = bonus
            if streak_bonus > 0:
                wait += streak_bonus
                reasons.append(f"short_streak_{count}")

        wait = max(self.adaptive_min_wait, min(wait, self.adaptive_max_wait))

        if session is not None and session.get("started_at") is not None:
            elapsed = self._now() - session["started_at"]
            remaining = self.adaptive_max_total_wait - elapsed
            if remaining <= 0:
                return 0.0, True, ",".join(reasons + ["max_total_wait_reached"])
            if wait > remaining:
                wait = max(0.0, remaining)
                reasons.append("limited_by_total_wait")

        return wait, False, ",".join(reasons) or "adaptive"

    def _bump_short_streak(self, session: dict, clean_text: str) -> int:
        if len(clean_text) <= self.adaptive_short_message_threshold:
            session["short_message_count"] = session.get("short_message_count", 0) + 1
        else:
            session["short_message_count"] = 0
        return session["short_message_count"]

    # ---------------- 计时器管理 ----------------

    def _cancel_timer(self, session: dict) -> None:
        task = session.get("timer_task")
        if task is not None:
            task.cancel()
            session["timer_task"] = None

    def _arm_timer(self, session: dict, duration: float) -> None:
        self._cancel_timer(session)
        session["pending_wait"] = duration
        session["last_wait"] = duration
        session["timer_started_at"] = self._now()
        session["timer_task"] = asyncio.create_task(
            self._timer_coroutine(session, duration)
        )

    async def _timer_coroutine(self, session: dict, duration: float) -> None:
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            return
        # 代际守卫：只有当前注册的仍是同一个会话对象才允许触发，
        # 泄漏的旧计时器永远无法误触发新一轮会话。
        if self.sessions.get(session["uid"]) is session:
            self._request_flush(session)

    def _request_flush(self, session: dict) -> None:
        """统一的立即结算入口：先取消计时器再置位事件。"""
        self._cancel_timer(session)
        session["flush_event"].set()

    def request_flush(self, uid: str) -> bool:
        """按用户请求立即结算（指令/撤回清空等路径）。无会话时为无害空操作。"""
        session = self.sessions.get(uid)
        if session is None:
            return False
        self._request_flush(session)
        return True

    # ---------------- 消息提交 ----------------

    def submit(
        self,
        uid: str,
        text: str = "",
        image_urls: Optional[List[str]] = None,
        message_id=None,
    ) -> SubmitResult:
        image_urls = list(image_urls or [])
        existing = self.sessions.get(uid)

        if existing is not None:
            existing["items"].append(
                {"message_id": message_id, "text": text, "images": list(image_urls)}
            )
            if text:
                existing["buffer"].append(text)
            existing["images"].extend(image_urls)

            next_wait, flush_now, reason = self.calculate_wait(text, existing)
            if flush_now:
                self._request_flush(existing)
                return SubmitResult("flushed", next_wait, reason)
            self._arm_timer(existing, next_wait)
            return SubmitResult("appended", next_wait, reason)

        session = {
            "uid": uid,
            "buffer": [text] if text else [],
            "images": list(image_urls),
            "items": [
                {"message_id": message_id, "text": text, "images": list(image_urls)}
            ],
            "flush_event": asyncio.Event(),
            "timer_task": None,
            "is_typing": False,
            "started_at": self._now(),
            "pending_wait": 0.0,
            "timer_started_at": self._now(),
            "last_wait": 0.0,
            "short_message_count": 1 if self._is_short_message(text) else 0,
        }
        self.sessions[uid] = session
        initial_wait, _, reason = self.calculate_wait(text)
        self._arm_timer(session, initial_wait)
        return SubmitResult("started", initial_wait, reason)

    def absorb_activity(self, uid: str, message_id=None) -> bool:
        """吸收无文本内容的活动消息（表情/语音等未识别组件）。

        有活跃会话时：登记空 item 并把计时器重置为固定防抖时长（不动短句连击计数），
        防止这类消息绕过防抖独立触发 LLM；无会话时返回 False，由调用方放行。
        """
        session = self.sessions.get(uid)
        if session is None:
            return False
        session["items"].append({"message_id": message_id, "text": "", "images": []})
        self._arm_timer(session, self.debounce_time)
        return True

    # ---------------- 撤回过滤 ----------------

    def remove_message(self, uid: str, message_id) -> Tuple[int, bool]:
        """从待合并队列移除指定消息并重建 buffer/images。

        返回 (移除条数, 移除后队列是否为空)。是否触发结算由调用方决定。
        """
        session = self.sessions.get(uid)
        if session is None:
            return 0, False

        before = len(session["items"])
        session["items"] = [
            item
            for item in session["items"]
            if str(item.get("message_id")) != str(message_id)
        ]
        removed = before - len(session["items"])
        if removed <= 0:
            return 0, False

        session["buffer"] = [item["text"] for item in session["items"] if item["text"]]
        session["images"] = [
            url for item in session["items"] for url in item.get("images", [])
        ]
        return removed, len(session["items"]) == 0

    # ---------------- 输入状态 ----------------

    def pause_for_typing(self, uid: str, max_typing_wait: float) -> Optional[float]:
        """进入"正在输入"状态：挂起原计时，启动保护计时器。

        保护时长受会话硬死线约束（min(max_typing_wait, 硬死线余量)），
        超过硬死线则直接结算。重复通知会续期保护，但同样受硬死线钳制。
        """
        session = self.sessions.get(uid)
        if session is None:
            return None
        session["is_typing"] = True
        remaining_total = self.max_session_wait - (self._now() - session["started_at"])
        protection = min(max_typing_wait, remaining_total)
        if protection <= 0:
            self._request_flush(session)
            return 0.0
        self._cancel_timer(session)
        session["timer_task"] = asyncio.create_task(
            self._timer_coroutine(session, protection)
        )
        return protection

    def resume_after_typing(self, uid: str) -> Optional[float]:
        """离开"正在输入"状态：恢复被打断前的剩余等待。

        仅在确实处于输入状态时生效（天然过滤重复的停止输入通知）。
        """
        session = self.sessions.get(uid)
        if session is None or not session.get("is_typing"):
            return None
        session["is_typing"] = False
        elapsed_since_arm = self._now() - session.get("timer_started_at", self._now())
        remaining = session.get("pending_wait", 0.0) - elapsed_since_arm
        wait = max(remaining, RESUME_MIN_WAIT)
        self._arm_timer(session, wait)
        return wait

    # ---------------- 等待与收尾 ----------------

    async def wait_flush(self, uid: str, timeout: Optional[float] = None) -> None:
        """阻塞直到结算事件置位；timeout 为会话硬死线兜底。

        即使计时器任务因异常丢失（无人 set），超时后也会主动请求结算，
        保证缓冲的消息不会被无限期吞掉。
        """
        session = self.sessions.get(uid)
        if session is None:
            return
        flush_event = session["flush_event"]
        deadline = self._now() + (self.max_session_wait if timeout is None else timeout)
        while self.sessions.get(uid) is session and not flush_event.is_set():
            remaining = deadline - self._now()
            if remaining <= 0:
                self._request_flush(session)
                break
            try:
                await asyncio.wait_for(flush_event.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                continue

    def shutdown(self) -> int:
        """插件卸载时清理全部会话与计时器，返回丢弃的会话数。"""
        for session in list(self.sessions.values()):
            self._cancel_timer(session)
        count = len(self.sessions)
        self.sessions.clear()
        return count
