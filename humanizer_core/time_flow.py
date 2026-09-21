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
# 历法感知（v3.7.0，lunar_python 软依赖）
# ============================================================
# 软导入：缺库时历法功能静默关闭（calendar_facts 返回空 facts、注入行
# 省略），插件其余功能完全不受影响。lunar_python 为纯 Python 库、无重依赖。

try:
    from lunar_python import Solar  # type: ignore
except Exception:  # noqa: BLE001
    Solar = None

# 固定公历敏感日（纪念/哀悼类，不宜庆祝调侃）；值同时是默认敏感词表成员
_SOLAR_SENSITIVE_DATES = {
    "05-12": "防灾减灾日",
    "07-07": "七七事变纪念日",
    "09-18": "九一八纪念日",
    "12-13": "国家公祭日",
}
# 固定农历敏感日（月, 日；闰月为负月码，不单列——闰清明之外的闰月节日罕见）
_LUNAR_SENSITIVE_DATES = {
    (7, 15): "中元节",
    (10, 1): "寒衣节",
}
# 默认敏感词表：文本包含匹配（节日/节气名）+ 上两张日期表的名称
DEFAULT_SENSITIVE_KEYWORDS = (
    "清明",
    "中元节",
    "寒衣节",
    "国家公祭日",
    "九一八纪念日",
    "七七事变纪念日",
    "防灾减灾日",
)


def calendar_facts(now: datetime, sensitive_keywords=None) -> dict:
    """当日历法事实（v3.7.0）。缺 lunar_python 时除 date 外全部为空。

    返回字段：
    - date: "YYYY-MM-DD"
    - lunar_text: "农历七月十六" 或 ""
    - festival_text: "中秋节" 或 ""（传统节日，多个用 · 连接）
    - term_text: "处暑" 或 ""（仅当日交节的节气）
    - sensitive_name: 命中的敏感日名或 ""

    敏感日判定三路：①关键词文本包含（节日/节气名，覆盖清明/中秋类）
    ②固定农历日期表（中元/寒衣，不依赖节日库覆盖度）③固定公历日期表。
    sensitive_keywords 传空/None 用内置默认表；自定义表追加传入即可。
    """
    facts = {
        "date": f"{now.year:04d}-{now.month:02d}-{now.day:02d}",
        "lunar_text": "",
        "festival_text": "",
        "term_text": "",
        "sensitive_name": "",
    }
    if Solar is None:
        return facts
    try:
        solar = Solar.fromYmd(now.year, now.month, now.day)
        lunar = solar.getLunar()
    except Exception:  # noqa: BLE001
        return facts
    try:
        month_cn = str(lunar.getMonthInChinese())
        day_cn = str(lunar.getDayInChinese())
        if month_cn and day_cn:
            facts["lunar_text"] = f"农历{month_cn}月{day_cn}"
    except Exception:  # noqa: BLE001
        pass
    try:
        festivals = [
            str(f).strip() for f in (lunar.getFestivals() or []) if str(f).strip()
        ]
    except Exception:  # noqa: BLE001
        festivals = []
    try:
        # 公历节日并入（国庆/劳动节/教师节等）；农历优先、去重保序
        for f in (solar.getFestivals() or []):
            fs = str(f).strip()
            if fs and fs not in festivals:
                festivals.append(fs)
    except Exception:  # noqa: BLE001
        pass
    term = ""
    try:
        jq = lunar.getJieQi()
        term = str(jq).strip() if jq else ""
    except Exception:  # noqa: BLE001
        term = ""
    facts["festival_text"] = "·".join(festivals)
    facts["term_text"] = term

    keywords = tuple(
        str(k).strip() for k in (sensitive_keywords or DEFAULT_SENSITIVE_KEYWORDS)
        if str(k).strip()
    ) or tuple(DEFAULT_SENSITIVE_KEYWORDS)
    haystack = f"{facts['festival_text']} {facts['term_text']}"
    mmdd = f"{now.month:02d}-{now.day:02d}"
    lunar_md = None
    try:
        lunar_md = (abs(int(lunar.getMonth())), int(lunar.getDay()))
    except Exception:  # noqa: BLE001
        lunar_md = None
    for kw in keywords:
        if kw in haystack:
            facts["sensitive_name"] = kw
            break
        if _SOLAR_SENSITIVE_DATES.get(mmdd) == kw:
            facts["sensitive_name"] = kw
            break
        if lunar_md is not None and _LUNAR_SENSITIVE_DATES.get(lunar_md) == kw:
            facts["sensitive_name"] = kw
            break
    return facts


def build_calendar_line(facts: dict, sensitive_guard: bool = True) -> str:
    """由 calendar_facts 组装历法注入行；无农历信息返回空串（不占 prompt）。

    常规日："今天是农历七月十六 · 中秋节 · 处暑"
    敏感日（guard 开）："今天是中元节（农历七月十五）——今天适合安静、贴心"
    "的话题：别庆祝、别开玩笑、别过度活跃。"
    """
    if not isinstance(facts, dict):
        return ""
    parts = [
        p
        for p in (
            str(facts.get("lunar_text", "") or ""),
            str(facts.get("festival_text", "") or ""),
            str(facts.get("term_text", "") or ""),
        )
        if p
    ]
    summary = " · ".join(parts)
    sensitive = str(facts.get("sensitive_name", "") or "")
    if sensitive and sensitive_guard:
        detail = f"（{summary}）" if summary else ""
        return (
            f"今天是{sensitive}{detail}——今天适合安静、贴心的话题："
            "别庆祝、别开玩笑、别过度活跃。"
        )
    if not summary:
        return ""
    return f"今天是{summary}"


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
    if minutes != minutes:  # NaN 防御：比较全为假会一路落到「隔了一周多」
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
    rhythm_text: str = "",
    continuity_line: str = "",
    calendar_line: str = "",
    days_line: str = "",
    last_chat_line: str = "",
    commitment_line: str = "",
) -> str:
    """组装统一的时间上下文注入块（墙钟 + 距上次交流 + 生活状态 + 节奏 + 连续性）。

    单一事实源：墙钟只出现一次；生活状态行标签可切换——
    - LLM 时间线模式：state_label="当前时段"（"下午 · 咖啡店打工 · 心情带劲"）
    - 基础模式：state_label="当前状态"（"正在吃早饭 · 心情平静"）
    - rhythm_text（v3.5.0 节奏引擎）：可选的对话节奏指令行（hot/cold 档注入，
      warm 档为空串不注入）
    - continuity_line（v3.6.0 连续性分级）：可选的「隔了多久、该用什么方式
      重新开口」指令行（短中断/隔夜/隔几天/久别各有一档，连续聊天为空串）
    - calendar_line（v3.7.0 历法感知）：可选的农历/节日/节气行（敏感日自带
      说话护栏）；days_line（v3.7.0 相识天数）：可选的「认识第 N 天」行
    - last_chat_line（v3.8.0 双向间隔）：可选的「对方最后发言 X · 你最后
      发言 Y」行（两侧独立计时，gap/连续性只有合并口径）
    - commitment_line（v3.8.0 承诺簿）：可选的「你答应过对方的事到期了」
      行（当日待办性质，放块尾、紧邻收尾护栏行）
    调用方保证至少有一项内容，否则返回的空块由调用方过滤。
    """
    lines = ["<time_context>"]
    if include_wall_clock:
        lines.append(f"当前时间：{format_wall_clock(now)}")
    if gap_text:
        lines.append(f"距上次交流：{gap_text}")
    if last_chat_line:
        lines.append(last_chat_line)
    if state_text:
        lines.append(f"{state_label}：{state_text}")
    if rhythm_text:
        lines.append(rhythm_text)
    if continuity_line:
        lines.append(continuity_line)
    if calendar_line:
        lines.append(calendar_line)
    if days_line:
        lines.append(days_line)
    if commitment_line:
        lines.append(commitment_line)
    lines.append("以上为真实时间，请以此为准；与话题无关时无需主动提及时间。")
    lines.append("</time_context>")
    return "\n".join(lines)


# v3.5.0 节奏引擎：对话热度三档，阈值从主动消息触发间隔（silence_after_minutes）
# 派生——默认 hot < 间隔×0.2，warm < 间隔×0.667（≈2/3），cold 其余；两个分界
# 比例可由用户配置（rhythm_hot_ratio / rhythm_cold_ratio），默认即未调整时的方案。
# 间隔本身即"距用户最后发言"，主动消息触发时刻（间隔±波动）天然落在 cold 段
# 末尾，节奏与主动消息闭环。
def rhythm_heat(
    now_ts: float,
    last_user_ts,
    silence_minutes,
    hot_ratio: float = 0.2,
    cold_ratio: float = 0.667,
) -> str:
    """按距用户最后发言的间隔推导对话热度（"hot" / "warm" / "cold"）。

    纯派生、无状态：分档阈值 = silence_after_minutes（主动消息触发间隔）×
    hot_ratio 与 cold_ratio，用户调整主动消息间隔时分档自动缩放。
    防御：last_user_ts 缺失/非正数 → cold（无记录视为冷开场）；
    silence_minutes 非法（<=0）→ warm（禁用节奏，不注入指令）；
    比例非法或 hot_ratio ≥ cold_ratio → 回落默认 0.2/0.667。
    """
    try:
        silence = float(silence_minutes)
    except (TypeError, ValueError):
        return "warm"
    if silence <= 0:
        return "warm"
    try:
        hot_r = float(hot_ratio)
        cold_r = float(cold_ratio)
    except (TypeError, ValueError):
        hot_r, cold_r = 0.2, 0.667
    if not (0 < hot_r < cold_r < 1):
        hot_r, cold_r = 0.2, 0.667
    if not isinstance(last_user_ts, (int, float)) or last_user_ts <= 0:
        return "cold"
    gap = float(now_ts) - float(last_user_ts)
    if gap < 0:
        return "warm"  # 时钟回拨/时间戳异常：不判 hot（负数会小于一切阈值）
    if gap != gap:  # NaN 同理按 warm 兜底
        return "warm"
    if gap < silence * 60 * hot_r:
        return "hot"
    if gap < silence * 60 * cold_r:
        return "warm"
    return "cold"


RHYTHM_DIRECTIVES = {
    "hot": "你们正在连续聊天中：回复保持轻快、简短、自然，像熟人热聊那样，别端着别长篇大论。",
    "cold": "这个话题已经有一阵子没活跃了（或刚重新开启）：第一条回复轻描淡写、一句带过，别热情过头，像老熟人重新开口那样自然。",
    "warm": "",
}


# ============================================================
# 连续性分级（v3.6.0 对话间时间流逝感知）
# ============================================================
# 把「距上次交流」的时长翻译成关系连续性档位，并给出各档的说话方式。
# 与节奏档互补：节奏管 <30min 的回复快慢，连续性管 ≥30min 的开口方式——
# 短中断/同日回归/隔夜/隔几天/久别重逢，各有各的分寸。

CONTINUITY_DIRECTIVES = {
    "short_break": (
        "距上一条消息才过了一会儿——像中途离开了一下回来接着聊，"
        "直接接上刚才的话头就行，不用重新打招呼。"
    ),
    "same_day": (
        "上次交流是今天早些时候——同一天稍后回来，可以自然承接今天前面"
        "聊过的内容（「刚才」「今天」），别当作新话题重新开场。"
    ),
    "overnight": (
        "距上次交流隔了一夜——已经是新的一天：像隔天重新联系那样自然，"
        "可以衔接「昨天/昨晚」聊过的事，别装作对话还在原地继续。"
    ),
    "days": (
        "距上次交流隔了好几天——像几天没聊后重新开口：可以自然问问"
        "「这几天怎么样」，别假装刚聊过，也别一口气翻旧账。"
    ),
    "long_absence": (
        "距上次交流隔了很久（一周以上）——久别重逢：自然提一句「好久没聊」"
        "就好，别表现得像被冷落，也别追问对方为什么没来。"
    ),
}


def continuity_label(
    prev_ts,
    now_ts,
    threshold_minutes: int = 30,
) -> str:
    """把距上次交流的时长翻译成连续性档位（v3.6.0，纯函数）。

    档位：continuous（连续，不注入）/ short_break / same_day / overnight /
    days / long_absence；时刻缺失或时钟回拨返回空串。

    分档先看绝对间隔、再看跨自然日（北京时间）：跨午夜但间隔不足 2 小时
    仍算短中断（深夜连聊），跨 1 个自然日即算隔夜——「隔了一夜」是关系
    语感，不追求 24 小时的机器精度。
    """
    try:
        gap = float(now_ts) - float(prev_ts)
    except (TypeError, ValueError):
        return ""
    if gap != gap or gap <= 0:  # NaN / 回拨
        return ""
    try:
        threshold = max(1, int(threshold_minutes))
    except (TypeError, ValueError):
        threshold = 30
    minutes = gap / 60.0
    if minutes < threshold:
        return "continuous"
    if minutes < 120:
        return "short_break"
    try:
        prev_dt = datetime.fromtimestamp(float(prev_ts), CHINA_TZ)
        now_dt = datetime.fromtimestamp(float(now_ts), CHINA_TZ)
    except (OverflowError, OSError, ValueError):
        return ""
    crossed = (now_dt.date() - prev_dt.date()).days
    if crossed <= 0:
        return "same_day"
    if crossed == 1:
        return "overnight"
    if crossed < 7:
        return "days"
    return "long_absence"


def continuity_text(
    prev_ts,
    now_ts,
    threshold_minutes: int = 30,
) -> str:
    """连续性注入行（v3.6.0）：连续聊天/时刻未知返回空串（不占 prompt）。"""
    label = continuity_label(prev_ts, now_ts, threshold_minutes)
    return CONTINUITY_DIRECTIVES.get(label, "")


def acquaintance_days(first_ts, now_ts) -> int:
    """相识天数（v3.7.0，纯函数）：按北京时间自然日差 + 1（首日 = 第 1 天）。

    自然日语义：同一自然日内无论几点都算第 1 天，跨过午夜才 +1——
    不用 ``// 86400``（UTC 对齐会在东八区早 8 点才换天、且 23:50 首聊
    00:10 就跳第 2 天）。时刻缺失/非法/时钟回拨返回 0（调用方跳过注入）。
    """
    try:
        first = float(first_ts)
        now = float(now_ts)
    except (TypeError, ValueError):
        return 0
    if first != first or now != now or first <= 0 or now < first:
        return 0
    try:
        first_date = datetime.fromtimestamp(first, CHINA_TZ).date()
        now_date = datetime.fromtimestamp(now, CHINA_TZ).date()
    except (OverflowError, OSError, ValueError):
        return 0
    return (now_date - first_date).days + 1


# ============================================================
# 双向间隔感知（v3.8.0，相对时间渲染移植自时笺 time_awareness
# core/last_chat_tracker.py::_relative，MIT License © time_awareness 作者）
# ============================================================

def _relative_last(ts, now_ts) -> str:
    """墙钟秒→「刚刚 / X 分钟前 / X 小时前 / X 天前 / MM-DD」分档。

    与 gap_context_mixed 的粗粒度语感互补：这里两侧各自独立渲染，
    超过一周回落到具体日期（"上次聊天"太久时数字间隔失去语感意义）。
    入参非法/NaN 返回空串；负数（时钟倒走）兜底"刚刚"——与源实现一致。
    """
    try:
        secs = float(now_ts) - float(ts)
    except (TypeError, ValueError):
        return ""
    if secs != secs:  # NaN
        return ""
    if secs < 0:
        return "刚刚"
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{int(secs // 60)} 分钟前"
    if secs < 86400:
        return f"{int(secs // 3600)} 小时前"
    if secs < 86400 * 7:
        return f"{int(secs // 86400)} 天前"
    try:
        return datetime.fromtimestamp(float(ts), CHINA_TZ).strftime("%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


def render_last_chat_line(user_ts, ai_ts, now_ts=None) -> str:
    """双向「上次发言」注入行（v3.8.0，纯函数）。

    区别于 gap/连续性（合并的"距上次交流"，一侧口径）：这里用户与 Bot
    各自独立计时——主动消息发出后用户一直没回、或用户连发 Bot 久未回，
    两侧差值本身即是语行情报。

    规则：任一侧缺失只显示另一侧；两侧全无、或两侧都在 1 分钟内（正在
    即时对话，这行纯属噪音）返回空串（调用方不注入）。
    措辞按 Bot 第一人称视角："对方最后发言 X · 你最后发言 Y"。
    """
    if now_ts is None:
        now_ts = now_cn().timestamp()
    parts = []
    try:
        has_user = user_ts is not None and float(user_ts) > 0
    except (TypeError, ValueError):
        has_user = False
    try:
        has_ai = ai_ts is not None and float(ai_ts) > 0
    except (TypeError, ValueError):
        has_ai = False
    if has_user:
        rel = _relative_last(user_ts, now_ts)
        if rel:
            parts.append(("对方最后发言", rel, user_ts, now_ts))
    if has_ai:
        rel = _relative_last(ai_ts, now_ts)
        if rel:
            parts.append(("你最后发言", rel, ai_ts, now_ts))
    if not parts:
        return ""
    # 即时对话中不注入（分档"刚刚"=<60s）：双侧都刚刚、或只剩一条
    # "刚刚"（新会话对方开口即触发、本侧无记录）都是零信息量噪音。
    if all(p[1] == "刚刚" for p in parts):
        return ""
    return " · ".join(f"{label} {rel}" for label, rel, _, _ in parts)


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
        if end < start:
            # v4.0.1：跨午夜（如 23:00-01:00）返回当日段+次日凌晨段两段。
            # 原实现截断为当日段——凌晨的后半段凭空消失，生活时间线在
            # 00:00-01:00 会误判为"空闲"。
            return (TimeInterval(start, 1440), TimeInterval(0, end))
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
    "CONTINUITY_DIRECTIVES",
    "DEFAULT_SENSITIVE_KEYWORDS",
    "LifeState",
    "NATURAL_SLOT_NAMES",
    "OPTIONAL_FIELDS",
    "SlotMatch",
    "TimeInterval",
    "TimelineEntry",
    "acquaintance_days",
    "basic_schedule_to_timeline",
    "build_calendar_line",
    "build_life_slot_text",
    "build_state_block",
    "build_time_block",
    "calendar_facts",
    "continuity_label",
    "continuity_text",
    "extract_json_object",
    "format_wall_clock",
    "gap_context",
    "gap_context_mixed",
    "minute_of_day",
    "render_last_chat_line",
    "mood_for_slot",
    "now_cn",
    "parse_schedule_template",
    "parse_time_slot",
    "rhythm_heat",
    "RHYTHM_DIRECTIVES",
    "section_of",
    "select_current_slot",
]
