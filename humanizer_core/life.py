# -*- coding: utf-8 -*-
"""
动态一天状态（v2.5）纯函数模块。

为 AI 维护一个随真实时间推进的「现在在做什么 / 心情」：
- 日程模板：多行 "HH:MM 描述" 映射一天各时段在做什么；模板未覆盖的
  时段用兜底文案（如深夜休息）。
- 心情：按日期确定性哈希从心情池选一个——同一天内稳定、跨天变化，
  不消耗任何模型调用、无随机漂移（可复现、可测试）。
- 注入块：渲染成「【你的当前状态】」文本块，由 main.py 经 on_llm_request
  注入到所有对话的 LLM 请求，让回复带生活感。

设计约束：不依赖 astrbot，全部为纯函数（便于单元测试），零 token 零 IO。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

# 一天中自然时段（与 proactive.py 保持一致，独立维护避免循环依赖）
_NATURAL_SLOTS = (
    (0, 5, "深夜"),
    (5, 8, "凌晨"),
    (8, 11, "上午"),
    (11, 13, "中午"),
    (13, 17, "下午"),
    (17, 19, "傍晚"),
    (19, 23, "晚上"),
    (23, 24, "深夜"),
)

_WEEKDAY_CN = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

# 默认心情池（可配置覆盖）
DEFAULT_MOOD_POOL = (
    "平静",
    "有点小开心",
    "专注",
    "有点累",
    "放松",
    "期待",
    "略感无聊",
    "元气满满",
)

# 默认日程模板：多行 "HH:MM 描述"。以 00:00 为首项作全天兜底
#（描述会随真实时间映射到对应时段）。用户可在配置里整体替换。
DEFAULT_SCHEDULE = (
    "00:00 夜深了，在休息\n"
    "08:00 刚醒，在赖床\n"
    "09:00 在吃早饭\n"
    "09:30 开始一天的工作/学习\n"
    "12:00 午饭时间，在吃饭\n"
    "13:30 午后小憩\n"
    "14:30 继续工作/学习\n"
    "18:30 下班，在回家的路上\n"
    "19:30 晚饭时间\n"
    "21:00 自由时间，在刷手机/看书\n"
    "23:30 准备睡觉"
)

_SCHEDULE_LINE_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s+(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class LifeSnapshot:
    """某个时刻 AI 的一天状态快照（纯数据）。"""

    doing: str = ""
    mood: str = ""
    date_label: str = ""
    time_label: str = ""
    slot: str = ""

    def render(self) -> str:
        """渲染为注入文本块（供 on_llm_request 追加进 LLM 请求）。"""
        lines = ["【你的当前状态】"]
        if self.date_label:
            lines.append(f"现在是 {self.date_label}")
        if self.time_label:
            lines.append(f"时间是 {self.time_label}")
        if self.doing:
            lines.append(f"你正在：{self.doing}")
        if self.mood:
            lines.append(f"心情：{self.mood}")
        return "\n".join(lines)

    def __bool__(self) -> bool:
        return bool(self.doing or self.mood or self.date_label or self.time_label)


def parse_schedule(text: str) -> list[tuple[int, str]]:
    """解析日程模板为有序 [(当日分钟数, 描述)] 列表。

    无效行（不匹配 HH:MM 描述、无描述）静默跳过；描述为空的行跳过。
    解析结果按时间排序（模板通常有序，此处防御性排序）。
    """
    entries: list[tuple[int, str]] = []
    if not text:
        return entries
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _SCHEDULE_LINE_RE.match(line)
        if not m:
            continue
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            continue
        desc = m.group(3).strip()
        if not desc:
            continue
        entries.append((hour * 60 + minute, desc))
    entries.sort(key=lambda item: item[0])
    return entries


def resolve_doing(schedule: list[tuple[int, str]], now: datetime) -> str:
    """按真实时刻从日程中取「现在在做什么」。

    规则：取「不大于当前时刻」的最后一条；若当前时刻早于首条（模板首项
    不是 00:00），用首条描述兜底（视为昨日延续）。空模板返回空串。
    """
    if not schedule:
        return ""
    minute = now.hour * 60 + now.minute
    current: tuple[int, str] | None = None
    for entry in schedule:
        if entry[0] <= minute:
            current = entry
        else:
            break
    if current is None:
        # 当前时刻早于模板首条：用首条兜底
        return schedule[0][1]
    return current[1]


def mood_for_day(now: datetime, pool: tuple[str, ...] = DEFAULT_MOOD_POOL) -> str:
    """按日期确定性选心情：同日稳定、跨天变化（无随机、可复现）。

    用日期（本地 YYYY-MM-DD）的 SHA256 取模选心情池。心情池为空返回空串。
    """
    if not pool:
        return ""
    day = f"{now.year:04d}-{now.month:02d}-{now.day:02d}"
    digest = hashlib.sha256(day.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(pool)
    return pool[idx]


def time_slot_of(now: datetime) -> str:
    """返回当前时刻的自然时段名（凌晨/早上/上午/中午/下午/傍晚/晚上/深夜）。"""
    minute = now.hour * 60 + now.minute
    for start, end, name in _NATURAL_SLOTS:
        if start * 60 <= minute < end * 60:
            return name
    return "深夜"  # 兜底（正常不会走到）


def build_life_context(
    now: datetime,
    *,
    schedule: str = DEFAULT_SCHEDULE,
    fallback_doing: str = "",
    mood_pool: tuple[str, ...] = DEFAULT_MOOD_POOL,
    enable_mood: bool = True,
) -> str:
    """组装注入文本块（主入口）。

    - doing 取 resolve_doing；模板为空或取不到时用 fallback_doing 兜底。
    - mood 取 mood_for_day（enable_mood=False 时置空）。
    - 渲染为「【你的当前状态】」文本块；时间标签为 8月18日 周二 晚上 21:35 样式。
    """
    doing = resolve_doing(parse_schedule(schedule), now)
    if not doing:
        doing = fallback_doing
    mood = mood_for_day(now, mood_pool) if enable_mood else ""
    slot = time_slot_of(now)
    date_label = f"{now.month}月{now.day}日 {_WEEKDAY_CN[now.weekday()]}"
    time_label = f"{slot} {now.hour:02d}:{now.minute:02d}"
    return LifeSnapshot(
        doing=doing,
        mood=mood,
        date_label=date_label,
        time_label=time_label,
        slot=slot,
    ).render()


__all__ = [
    "DEFAULT_MOOD_POOL",
    "DEFAULT_SCHEDULE",
    "LifeSnapshot",
    "build_life_context",
    "mood_for_day",
    "parse_schedule",
    "resolve_doing",
    "time_slot_of",
]
