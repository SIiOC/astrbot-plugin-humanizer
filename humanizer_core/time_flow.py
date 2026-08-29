# -*- coding: utf-8 -*-
"""对话间时间流动感知 —— 纯函数模块（零 astrbot 依赖，可独立单测）。

职责（v3.0 并入）：
- 墙钟格式化（Asia/Shanghai 固定时区）
- 对话间隙粗粒度分档（距上次交流，不暴露分钟精度）
- <time_context> 注入块组装（合并：墙钟 + 间隙 + 生活状态，单一事实源）
- 可选 LLM 生活时间线：时间线解析、当前时段匹配、时段文案组装
  （每天预生成一天的安排，对话时按分钟选中当前时段；失败回退日程模板）
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    CHINA_TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # 缺 tzdata 的环境兜底为固定东八区偏移
    CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


# ============================================================
# 墙钟
# ============================================================

def now_cn() -> datetime:
    return datetime.now(CHINA_TZ)


def minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def format_wall_clock(now: datetime) -> str:
    return (
        f"{now.year}年{now.month:02d}月{now.day:02d}日 "
        f"{_WEEKDAYS[now.weekday()]} {now.hour:02d}:{now.minute:02d}"
    )


# ============================================================
# 对话间隙（粗粒度分档，避免"65 小时 12 分钟前"式机器精度）
# ============================================================

def gap_context(
    last_ts: float | None,
    now_ts: float | None,
    threshold_minutes: int = 30,
) -> str:
    """距上次交流的粗粒度文案；不足阈值/未知/时钟回拨时返回空串（视为连续对话）。"""
    if last_ts is None or now_ts is None:
        return ""
    try:
        minutes = (float(now_ts) - float(last_ts)) / 60.0
    except (TypeError, ValueError):
        return ""
    if minutes < max(1, int(threshold_minutes)):
        return ""
    if minutes < 120:
        return "隔了个把小时"
    if minutes < 360:
        return "隔了几个小时"
    if minutes < 1440:
        return "隔了大半天"
    days = minutes / 1440.0
    if days < 2:
        return "隔了一天"
    if days < 3:
        return "隔了两天"
    if days < 7:
        return "隔了好几天"
    return "隔了一周多"


def _precise_elapsed_text(seconds: float) -> str:
    """总秒数→中文时长的精确分档（按阈值分档）。

    入参用 round 而非 int 截断：两个时钟源相减存在微秒级浮点噪声
    （如 7499.9999），截断会凭空少一分钟。
    """
    seconds = max(0, round(seconds))
    if seconds < 60:
        return "不到1分钟"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}分钟"
    hours, rm = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}小时{rm}分钟" if rm else f"{hours}小时"
    days, rh = divmod(hours, 24)
    return f"{days}天{rh}小时" if rh else f"{days}天"


def gap_context_mixed(
    last_ts: float | None,
    now_ts: float | None,
    threshold_minutes: int = 30,
) -> str:
    """混合分档：短精确、长粗（<阈值空串 / 30m-24h 精确到分钟 / ≥24h 粗粒度）。

    语义与 gap_context 完全一致（不足阈值=视为连续对话；恰好等于阈值开始注入；
    未知/回拨空串），仅阈值以上 24 小时内的文案改为精确时长形态。
    """
    if last_ts is None or now_ts is None:
        return ""
    try:
        seconds = float(now_ts) - float(last_ts)
        if seconds != seconds:  # NaN
            return ""
        minutes = seconds / 60.0
    except (TypeError, ValueError):
        return ""
    if minutes < max(1, int(threshold_minutes)):
        return ""
    if minutes < 1440:
        return _precise_elapsed_text(seconds)
    days = minutes / 1440.0
    if days < 2:
        return "隔了一天"
    if days < 3:
        return "隔了两天"
    if days < 7:
        return "隔了好几天"
    return "隔了一周多"


# ============================================================
# <time_context> 注入块（合并构建器）
# ============================================================

def build_state_block(
    now: datetime,
    gap_text: str = "",
    state_text: str = "",
    include_wall_clock: bool = True,
    state_label: str = "当前状态",
) -> str:
    """组装统一的时间上下文注入块（墙钟 + 距上次交流 + 生活状态）。

    单一事实源：墙钟只出现一次；生活状态行标签可切换——
    - LLM 时间线模式：state_label="当前时段"（"下午 · 咖啡店打工 · 心情带劲"）
    - 基础模式：state_label="当前状态"（"正在吃早饭 · 心情平静"）
    调用方保证至少有一项内容，否则返回的空块由调用方过滤。
    """
    lines = ["<time_context>"]
    if include_wall_clock:
        lines.append(f"当前时间：{format_wall_clock(now)}")
    if gap_text:
        lines.append(f"距上次交流：{gap_text}")
    if state_text:
        lines.append(f"{state_label}：{state_text}")
    lines.append("以上为真实时间，请以此为准；与话题无关时无需主动提及时间。")
    lines.append("</time_context>")
    return "\n".join(lines)


def build_time_block(
    now: datetime,
    gap_text: str = "",
    slot_text: str = "",
    include_wall_clock: bool = True,
) -> str:
    """LLM 时间线模式注入块（时段行用「当前时段」标签，兼容历史格式）。"""
    return build_state_block(
        now, gap_text, slot_text,
        include_wall_clock=include_wall_clock,
        state_label="当前时段",
    )


# ============================================================
# 时段解析（自然时段 + 具体 HH:MM-HH:MM）
# ============================================================

_NATURAL_SLOTS: dict[str, tuple[int, int]] = {
    "凌晨": (0, 360),
    "早上": (360, 540),
    "上午": (540, 720),
    "中午": (720, 840),
    "下午": (840, 1080),
    "傍晚": (1080, 1200),
    "晚上": (1200, 1380),
    "深夜": (1380, 1440),
}
NATURAL_SLOT_NAMES = tuple(_NATURAL_SLOTS)

_TIME_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-–—~]\s*(\d{1,2}):(\d{2})")

# 时间线条目可选附加字段（注册表驱动：新增字段只需改这里）
OPTIONAL_FIELDS: dict[str, str] = {"mood": "心情", "location": "地点", "note": "备注"}

_EXTRA_KEY_ALIAS = {"心情": "mood", "地点": "location", "备注": "note"}


@dataclass(frozen=True, slots=True)
class TimeInterval:
    start: int  # 当日分钟数 [0, 1440)
    end: int

    def contains(self, minute: int) -> bool:
        return self.start <= minute < self.end


def parse_time_slot(time_str: str) -> tuple[TimeInterval, ...] | None:
    """解析时段串：具体 "HH:MM-HH:MM"（跨午夜截断为当日段）或含自然时段名。

    返回区间元组；无法解析返回 None。
    """
    s = (time_str or "").strip()
    if not s:
        return None
    m = _TIME_RANGE_RE.fullmatch(s)
    if m:
        h1, m1, h2, m2 = (int(g) for g in m.groups())
        if not (0 <= h1 <= 23 and 0 <= m1 <= 59):
            return None
        if not (0 <= h2 <= 24 and 0 <= m2 <= 59):
            return None
        if h2 == 24 and m2 != 0:
            return None
        start = h1 * 60 + m1
        end = h2 * 60 + m2
        if end == start:
            return None
        if end < start:  # 跨午夜（如 23:00-01:00）截断为当日段
            end = 1440
        return (TimeInterval(start, end),)
    for name, (a, b) in _NATURAL_SLOTS.items():
        if name in s:
            return (TimeInterval(a, b),)
    return None


def _is_specific(time_str: str) -> bool:
    return bool(_TIME_RANGE_RE.fullmatch((time_str or "").strip()))


def section_of(minute: int) -> str:
    """当日分钟数所属的自然时段名。"""
    for name, (a, b) in _NATURAL_SLOTS.items():
        if a <= minute < b:
            return name
    return "深夜"


# ============================================================
# 时间线条目与生活状态
# ============================================================

@dataclass(slots=True)
class TimelineEntry:
    time: str  # "HH:MM-HH:MM" 或自然时段名
    schedule: str  # 在做什么（简短名词短语）
    extra_fields: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.time = str(self.time or "").strip()
        self.schedule = str(self.schedule or "").strip()
        raw = self.extra_fields if isinstance(self.extra_fields, dict) else {}
        extras: dict[str, str] = {}
        for key in OPTIONAL_FIELDS:
            val = raw.get(key)
            if val is not None and str(val).strip():
                extras[key] = str(val).strip()
        self.extra_fields = extras

    @property
    def valid(self) -> bool:
        return bool(self.time) and bool(self.schedule) and parse_time_slot(self.time) is not None

    @classmethod
    def from_dict(cls, data) -> "TimelineEntry | None":
        if not isinstance(data, dict):
            return None
        time_ = str(data.get("time", "") or "").strip()
        schedule = str(data.get("schedule", "") or "").strip()
        if not time_ or not schedule:
            return None
        entry = cls(time_, schedule, {k: data.get(k) for k in OPTIONAL_FIELDS})
        return entry if entry.valid else None

    def to_dict(self) -> dict:
        d = {"time": self.time, "schedule": self.schedule}
        d.update(self.extra_fields)
        return d


@dataclass(slots=True)
class LifeState:
    date: str  # YYYY-MM-DD
    holiday: str = "无"
    schedule_summary: str = ""
    timeline: list[TimelineEntry] = field(default_factory=list)
    status: str = "ok"  # ok / failed（ok 要求至少 1 条有效时间线）
    generated_at: str = ""

    @classmethod
    def from_dict(cls, data) -> "LifeState | None":
        if not isinstance(data, dict):
            return None
        date = str(data.get("date", "") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return None
        timeline: list[TimelineEntry] = []
        for raw in data.get("timeline") or []:
            entry = TimelineEntry.from_dict(raw)
            if entry is not None:
                timeline.append(entry)
        ok = data.get("status", "ok") == "ok" and bool(timeline)
        return cls(
            date=date,
            holiday=str(data.get("holiday", "") or "无").strip() or "无",
            schedule_summary=str(data.get("schedule_summary", "") or "").strip(),
            timeline=timeline,
            status="ok" if ok else "failed",
            generated_at=str(data.get("generated_at", "") or "").strip(),
        )

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "holiday": self.holiday,
            "schedule_summary": self.schedule_summary,
            "timeline": [e.to_dict() for e in self.timeline],
            "status": self.status,
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True, slots=True)
class SlotMatch:
    entry: TimelineEntry
    slot_name: str  # 按当前分钟归档的自然时段名
    interval: TimeInterval | None
    synthesized: bool = False


def select_current_slot(timeline, minute: int) -> SlotMatch | None:
    """选取当前分钟所在的时段：具体区间优先于自然时段，无命中合成"空闲"。

    minute 取值 [0, 1440)；空时间线返回 None。
    """
    entries = [e for e in timeline if isinstance(e, TimelineEntry) and e.valid]
    if not entries or not (0 <= minute < 1440):
        return None
    # 1) 具体区间优先
    for e in entries:
        if _is_specific(e.time):
            for iv in parse_time_slot(e.time) or ():
                if iv.contains(minute):
                    return SlotMatch(e, section_of(minute), iv, False)
    # 2) 自然时段
    for e in entries:
        if not _is_specific(e.time):
            for iv in parse_time_slot(e.time) or ():
                if iv.contains(minute):
                    return SlotMatch(e, section_of(minute), iv, False)
    # 3) 无命中：合成"空闲"（不继承旧时段的附加字段，心情由调用方按需补）
    return SlotMatch(
        TimelineEntry(section_of(minute), "空闲", {}),
        section_of(minute),
        None,
        True,
    )


# ============================================================
# 日程模板解析（LLM 生成失败时的回退）
# ============================================================

def parse_schedule_template(text: str) -> list[TimelineEntry]:
    """解析多行日程模板，每行 "HH:MM-HH:MM 安排 | 心情:平静 | 地点:家"。

    自然时段名同样支持（"下午 咖啡店打工"）；# 开头与空行跳过；坏行忽略。
    """
    entries: list[TimelineEntry] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        extras: dict[str, str] = {}
        main = line
        if "|" in line:
            main, *rest = line.split("|")
            for seg in rest:
                m = re.fullmatch(r"\s*(心情|地点|备注)\s*[:：]\s*(.+?)\s*", seg)
                if m:
                    extras[_EXTRA_KEY_ALIAS[m.group(1)]] = m.group(2)
        m = re.match(r"^(\S+)\s+(.+)$", main.strip())
        if not m:
            continue
        entry = TimelineEntry(m.group(1), m.group(2).strip(), extras)
        if entry.valid:
            entries.append(entry)
    return entries


def basic_schedule_to_timeline(text: str) -> list[TimelineEntry]:
    """把基础日程模板（每行 "HH:MM 描述"）转为时间线条目（回退链第二级）。

    条目 i 覆盖 [t_i, t_{i+1})，最后一条覆盖到 24:00；早于首条的时间由
    select_current_slot 合成「空闲」。复用 life.parse_schedule 的解析规则
    （坏行忽略、按时间排序）。空输入/无有效行返回空列表。
    """
    from .life import parse_schedule

    points = parse_schedule(text or "")
    entries: list[TimelineEntry] = []
    for i, (start, desc) in enumerate(points):
        end = points[i + 1][0] if i + 1 < len(points) else 1440
        if end <= start:  # 同分钟两行的防御：至少给 1 分钟
            end = start + 1
        entries.append(
            TimelineEntry(
                f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}",
                desc,
                {},
            )
        )
    return entries


# ============================================================
# 心情（时间线未提供时的确定性兜底：同日同时段稳定，跨日变化）
# ============================================================

_DEFAULT_MOOD_POOL = ("平静", "还行", "有点困", "蛮好", "期待")


def mood_for_slot(date: str, slot_name: str, pool: str = "") -> str:
    items = [m.strip() for m in (pool or "").replace("，", ",").split(",") if m.strip()]
    if not items:
        items = list(_DEFAULT_MOOD_POOL)
    digest = hashlib.sha256(f"{date}|{slot_name}".encode("utf-8")).hexdigest()
    return items[int(digest[:8], 16) % len(items)]


# ============================================================
# 时段文案
# ============================================================

def build_life_slot_text(
    state: LifeState | None,
    match: SlotMatch | None,
    mood_enabled: bool = True,
    mood_pool: str = "",
) -> str:
    """组装 "下午 · 咖啡店打工 · 心情平静 · 在咖啡店（今日：…）" 式时段文案。"""
    if match is None:
        return ""
    head = match.entry.schedule
    if _is_specific(match.entry.time):
        head = f"{match.slot_name}（{match.entry.time}） · {head}"
    else:
        head = f"{match.slot_name} · {head}"
    parts = [head]
    mood = match.entry.extra_fields.get("mood", "")
    if not mood and mood_enabled:
        date = state.date if state is not None else ""
        mood = mood_for_slot(date, match.slot_name, mood_pool)
    if mood:
        parts.append(f"心情{mood}")
    location = match.entry.extra_fields.get("location", "")
    if location:
        parts.append(f"在{location}" if not location.startswith("在") else location)
    note = match.entry.extra_fields.get("note", "")
    if note:
        parts.append(note)
    text = " · ".join(parts)
    summary = (state.schedule_summary if state is not None else "") or ""
    if summary:
        text = f"{text}（今日：{summary}）"
    return text


# ============================================================
# 模型输出 JSON 提取（容忍 markdown 代码块与前后杂文）
# ============================================================

def extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    s = str(text)
    start = s.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(s)):
            c = s[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start : i + 1])
                    except ValueError:
                        break
        start = s.find("{", start + 1)
    return None


__all__ = [
    "CHINA_TZ",
    "LifeState",
    "NATURAL_SLOT_NAMES",
    "OPTIONAL_FIELDS",
    "SlotMatch",
    "TimeInterval",
    "TimelineEntry",
    "build_life_slot_text",
    "build_state_block",
    "build_time_block",
    "extract_json_object",
    "format_wall_clock",
    "gap_context",
    "gap_context_mixed",
    "minute_of_day",
    "mood_for_slot",
    "now_cn",
    "parse_schedule_template",
    "parse_time_slot",
    "section_of",
    "select_current_slot",
]
