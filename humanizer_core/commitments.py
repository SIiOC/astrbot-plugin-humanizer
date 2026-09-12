# -*- coding: utf-8 -*-
"""承诺簿（v3.8.0，纯函数 + 轻存储、零 astrbot 依赖）。

机制级参考 xuqian13_autonomous_planning_plugin（麦麦规划插件，AGPL-3.0）的
「承诺 → pending → 次日核销」闭环设计：本模块按其思想以 Humanizer 自身的
状态/注入范式独立实现（未照搬代码；Humanizer 整体 AGPL-3.0，同源无碍）。

捕获的是 **Bot 许下的承诺**（"明天帮你查"），而非用户陈述——拟人点在
"它说过的事第二天会自己想起来"。捕捉 = 正则初筛（必须有显式时间锚点，
宁缺勿滥）+ 可选 LLM 后台确认；兑现 = 次日时间线生成时让 LLM 顺带核销
（见 main._life_commitment_check，复用既有生成管线、不另开调用）。

条目结构（commitments.json 持久化）::

    {"version": 1, "commitments": [
      {"id": "c-20260908-1a2b", "umo": "...", "text": "帮你查插件报错",
       "due_date": "2026-09-09", "created_ts": 1788..., "source": "regex",
       "status": "pending|done|expired", "resolved_ts": null}, ...]}
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Iterable, Optional

from .state import _atomic_write_json

COMMIT_VERSION = 1

# 每会话 pending 上限 / 过期宽限天数（超期未核销自动转 expired，不再打扰）
MAX_PENDING_PER_UMO = 6
EXPIRE_GRACE_DAYS = 7

_CN_NUMS = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}

# 显式时间锚点（无锚点句直接放弃：模糊的"改天请你吃饭"不是可核销的承诺）
_ANCHOR_RES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?:今天|今晚|今夜|今儿)"), "today"),
    (re.compile(r"(?:明晚|明早|明儿|明天|明日)"), "tomorrow"),
    (re.compile(r"大后天"), "d3"),
    (re.compile(r"后天"), "d2"),
    (re.compile(r"下下(?:周|星期|个周|个星期)([一二三四五六日天1-7]?)"), "w14"),
    (re.compile(r"(?:下周|下星期|下个周|下个星期)([一二三四五六日天1-7]?)"), "w7"),
    (re.compile(r"(?:周|星期|礼拜)([一二三四五六日天1-7])"), "week"),
    (re.compile(r"(?:这|本)?(?:周末|星期天|星期日)"), "weekend"),
    (re.compile(r"(?:过|再过)([一二三四五六两日]|1[0-9]|2[0-9]|30|[2-9])个?(?:天|日)"), "plus"),
    (re.compile(r"(\d{1,2})月(\d{1,2})[日号]"), "md"),
    (re.compile(r"(\d{1,2})/(\d{1,2})"), "mds"),
]

# 承诺动作句式。中文聊天常省略主语（"明天帮你查"），所以"帮你/替你/给你 +
# 具体动作动词"允许无主语；但纯"我会/我去/我来"类仍要求第一人称显式词，
# 且疑问句（吗/呢/？）在 extract 层整体排除——"要不要帮你查？"是提议不是承诺。
_ACTION = r"(?:查|问|看|弄|写|做|带|试|记|提醒|搞定|解决|发|准备|安排|办)"
_PROMISE_RES = [
    re.compile(r"(?:帮你|替你|给你)(?:%s|好好%s|试试)" % (_ACTION, _ACTION)),
    re.compile(r"(?:我|咱们?|俺)(?:来|去|会|一定|肯定|保证|尽量|争取|说啥都|帮你|给你|替你)"),
    re.compile(r"(?:到时|到时候|回头|明天|后天|改天)提醒你"),
    re.compile(r"包在(?:我|俺)身上"),
]

# 明确不是承诺的形态（问候/客套/即时行为）
_NON_COMMIT = re.compile(
    r"(见面|拜拜|晚安|早安|睡了|起床|下次再|回头再说|开玩笑|你说得|你觉得|你以为)"
)

_DATE_FMT = "%Y-%m-%d"


def _resolve_anchor(kind: str, m: re.Match, now: datetime) -> Optional[str]:
    """锚点 → 具体日期字符串；无法解析返回 None。"""
    try:
        if kind == "today":
            return now.strftime(_DATE_FMT)
        if kind == "tomorrow":
            return (now + timedelta(days=1)).strftime(_DATE_FMT)
        if kind == "d2":
            return (now + timedelta(days=2)).strftime(_DATE_FMT)
        if kind == "d3":
            return (now + timedelta(days=3)).strftime(_DATE_FMT)
        if kind == "plus":
            raw = m.group(1)
            n = _CN_NUMS.get(raw)
            if n is None:
                n = int(raw)
            if not 1 <= n <= 30:
                return None
            return (now + timedelta(days=n)).strftime(_DATE_FMT)
        if kind in ("w7", "w14"):
            wd_raw = m.group(1)
            if not wd_raw:
                target = 1  # "下周" 无数值 → 下周一
            elif wd_raw.isdigit():
                target = 7 if int(wd_raw) % 7 == 0 else int(wd_raw) % 7
            else:
                target = _CN_NUMS.get(wd_raw, 7)  # 日/天 → 7（周日）
            monday = (now - timedelta(days=now.weekday())) + timedelta(
                days=7 if kind == "w7" else 14
            )
            return (monday + timedelta(days=target - 1)).strftime(_DATE_FMT)
        if kind == "week":
            target = _CN_NUMS.get(m.group(1), 7)
            delta = (target - 1 - now.weekday()) % 7
            if delta == 0:
                delta = 7  # 今天就是周X：说"周X"通常指下一个
            return (now + timedelta(days=delta)).strftime(_DATE_FMT)
        if kind == "weekend":
            delta = (5 - now.weekday()) % 7  # 到周六
            if delta == 0:
                return now.strftime(_DATE_FMT)
            return (now + timedelta(days=delta)).strftime(_DATE_FMT)
        if kind in ("md", "mds"):
            mo, da = int(m.group(1)), int(m.group(2))
            if not (1 <= mo <= 12 and 1 <= da <= 31):
                return None
            try:
                due = now.replace(month=mo, day=da)
            except ValueError:
                return None
            if due.date() < now.date():
                due = due.replace(year=now.year + 1)  # 已过 → 明年（跨年夜承诺场景）
            return due.strftime(_DATE_FMT)
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def parse_due_date(text: str, now: datetime) -> Optional[str]:
    """从承诺句中解析到期日（北京时间自然日）；无锚点/非法返回 None。"""
    for rx, kind in _ANCHOR_RES:
        m = rx.search(text or "")
        if m:
            due = _resolve_anchor(kind, m, now)
            if due:
                return due
    return None


def regex_extract_commitments(text: str, now: datetime, max_items: int = 2) -> list[dict]:
    """正则初筛：从 Bot 回复文本提取候选承诺 [{text, due_date}]。

    句子级扫描（。！？换行切句），要求同句含 显式时间锚点 + 第一人称承诺
    句式，且避开客套/问候形态。上限 max_items 条；一切宁缺勿滥——LLM
    确认开着时这里是粗筛，关着时这里是唯一防线。
    """
    if not isinstance(text, str) or not text.strip():
        return []
    out: list[dict] = []
    seen: set[str] = set()
    # 分句只切 。；\n ——保留 ？/? 作为"疑问句结尾"证据（"要不要明天帮你查？"
    # 是提议不是承诺，必须排除；陈述句内的"吗/呢"误杀率反而更高，不做子串排除）
    for frag in re.split(r"[。；;\n]+", text):
        for sent in (s.strip() for s in frag.split("！") if s.strip()):
            if not (6 <= len(sent) <= 60):
                continue
            if sent.endswith(("？", "?")):
                continue
            if _NON_COMMIT.search(sent):
                continue
            due = parse_due_date(sent, now)
            if not due:
                continue
            if not any(p.search(sent) for p in _PROMISE_RES):
                continue
            key = due + sent[:12]
            if key in seen:
                continue
            seen.add(key)
            out.append({"text": sent, "due_date": due})
            if len(out) >= max_items:
                return out
    return out


def normalize_commitment(raw, umo: str, now_ts: float) -> Optional[dict]:
    """清洗单条承诺（LLM 输出/手动导入共用）；非法返回 None。"""
    if not isinstance(raw, dict) or not umo:
        return None
    text = " ".join(str(raw.get("text") or "").split())
    due = str(raw.get("due_date") or "").strip()
    if not text or len(text) > 100:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        return None
    try:
        datetime.strptime(due, _DATE_FMT)
    except ValueError:
        return None
    src = str(raw.get("source") or "regex")
    if src not in ("regex", "llm", "tool", "manual"):
        src = "llm"
    return {
        "id": f"c-{int(now_ts * 1000) % 10**9:09d}-{len(text) % 97:02d}",
        "umo": umo,
        "text": text,
        "due_date": due,
        "created_ts": float(now_ts),
        "source": src,
        "status": "pending",
        "resolved_ts": None,
    }


def add_commitments(
    commitments: list[dict], new_items: Iterable[dict], now_ts: float = None
) -> tuple[list[dict], int]:
    """合入新承诺（去重 + 每会话 pending 上限）。返回 (新列表, 实际加入数)。"""
    now_ts = time.time() if now_ts is None else float(now_ts)
    out = list(commitments)
    added = 0
    for it in new_items or []:
        if not isinstance(it, dict):
            continue
        entry = normalize_commitment(it, it.get("umo", ""), now_ts)
        if entry is None:
            continue
        pending_same = [
            c
            for c in out
            if c.get("umo") == entry["umo"]
            and c.get("status") == "pending"
        ]
        if len(pending_same) >= MAX_PENDING_PER_UMO:
            continue
        if any(
            c.get("umo") == entry["umo"]
            and c.get("due_date") == entry["due_date"]
            and str(c.get("text", ""))[:12] == entry["text"][:12]
            for c in out
        ):
            continue
        out.append(entry)
        added += 1
    return out, added


def due_for_date(commitments: list[dict], umo: str, today_str: str) -> list[dict]:
    """今晨到期（含更早未处理的，由调用方先 expire）的 pending 承诺。"""
    return [
        c
        for c in commitments
        if c.get("umo") == umo
        and c.get("status") == "pending"
        and str(c.get("due_date", "")) <= today_str
    ]


def due_today(
    commitments: list[dict], umo: str, today_str: str, grace_days: int = 2
) -> list[dict]:
    """到期当日提醒（v3.8.0 核销设计）：只提醒 due 当天、最迟逾期 grace_days 天。

    无自动核销信号下天天提醒变骚扰；改为此窗口制——窗口内每日提一次，
    出窗静默，超 EXPIRE_GRACE_DAYS 由 expire_stale 作废。手动
    /commitment_done 可随时关闭。
    """
    try:
        today = datetime.strptime(today_str, _DATE_FMT)
        floor = (today - timedelta(days=max(int(grace_days), 0))).strftime(_DATE_FMT)
    except (TypeError, ValueError):
        return due_for_date(commitments, umo, today_str)
    return [
        c
        for c in commitments
        if c.get("umo") == umo
        and c.get("status") == "pending"
        and floor <= str(c.get("due_date", "")) <= today_str
    ]


def render_commitment_line(items: list[dict], today_str: str) -> str:
    """到期承诺注入行（进当日时间线生成 prompt 与对话侧上下文）；空表返回空串。"""
    if not items:
        return ""
    parts = []
    for c in items[:3]:
        due = str(c.get("due_date", ""))
        text = str(c.get("text", ""))[:60]
        prefix = "今天" if due == today_str else f"{due} 定的"
        parts.append(f"「{text}」（{prefix}）")
    return (
        "你答应过对方的事到期了：" + "、".join(parts) +
        "。今天做到了就在聊天里自然地主动汇报；做不到就主动、轻量地说明或改期，"
        "别当作没说过。"
    )


def mark_resolved(
    commitments: list[dict], ids: Iterable[str], done: bool, now_ts: float = None
) -> tuple[list[dict], int]:
    """按 id 批量核销/作废。返回 (新列表, 实际改动数)。"""
    now_ts = time.time() if now_ts is None else float(now_ts)
    wanted = {i for i in ids if i}
    changed = 0
    out = []
    for c in commitments:
        if c.get("id") in wanted and c.get("status") == "pending":
            c = dict(c)
            c["status"] = "done" if done else "expired"
            c["resolved_ts"] = now_ts
            changed += 1
        out.append(c)
    return out, changed


def expire_stale(commitments: list[dict], now: datetime) -> tuple[list[dict], int]:
    """pending 超过 EXPIRE_GRACE_DAYS 天到期 → expired（不无限追账）。"""
    cutoff = (now - timedelta(days=EXPIRE_GRACE_DAYS)).strftime(_DATE_FMT)
    changed = 0
    out = []
    for c in commitments:
        if (
            c.get("status") == "pending"
            and str(c.get("due_date", "")) < cutoff
        ):
            c = dict(c)
            c["status"] = "expired"
            c["resolved_ts"] = now.timestamp()
            changed += 1
        out.append(c)
    return out, changed


def prune_for_save(
    commitments: list[dict], now_ts: float, keep_days: int = 14
) -> list[dict]:
    """落盘瘦身：已核销/作废条目超 keep_days 清除；pending 全保留。"""
    cutoff = now_ts - keep_days * 86400.0
    return [
        c
        for c in commitments
        if c.get("status") == "pending"
        or (isinstance(c.get("resolved_ts"), (int, float)) and c["resolved_ts"] >= cutoff)
        or not c.get("resolved_ts")
    ]


def parse_llm_commitments(llm_text, now: datetime, today_str: str, max_items: int = 3) -> list[dict]:
    """解析承诺提取 LLM 的 JSON 数组输出 [{text, due_date}]。

    LLM 偶发不守格式：逐条清洗（缺 text/日期非法/日期早于今天 → 丢弃），
    整体失败返回空表（调用方静默）。日期缺"明年"心智：早于今天不自动+1年，
    直接丢——错锚比漏锚伤害大。
    """
    from .time_flow import extract_json_object  # 复用容忍 markdown 的解析器

    out: list[dict] = []
    items = parse_llm_array(llm_text)
    for it in items:
        if not isinstance(it, dict):
            continue
        text = " ".join(str(it.get("text") or "").split())
        due = str(it.get("due_date") or "").strip()
        if not text or len(text) > 100:
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due) or due < today_str:
            continue
        try:
            datetime.strptime(due, _DATE_FMT)
        except ValueError:
            continue
        out.append({"text": text[:100], "due_date": due, "source": "llm"})
        if len(out) >= max_items:
            break
    return out


def parse_llm_array(llm_text) -> list:
    """从 LLM 文本提取 JSON 数组（容忍代码块围栏与前后杂文）。"""
    import json

    if not isinstance(llm_text, str) or not llm_text.strip():
        return []
    s = llm_text.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", s).strip()
    try:
        data = json.loads(s)
        if isinstance(data, list):
            return data
    except ValueError:
        pass
    start = s.find("[")
    while start != -1:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "[":
                depth += 1
            elif s[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(s[start : i + 1])
                        if isinstance(data, list):
                            return data
                    except ValueError:
                        break
                break
        start = s.find("[", start + 1)
    return []


class CommitmentStore:
    """commitments.json —— 原子读写；损坏按空表（调用方兜底）。"""

    def __init__(self, path):
        from pathlib import Path

        self._path = Path(path)

    def load(self) -> list[dict]:
        import json

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        items = raw.get("commitments") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return []
        out = []
        for it in items:
            if (
                isinstance(it, dict)
                and isinstance(it.get("id"), str)
                and isinstance(it.get("umo"), str)
                and it.get("umo")
                and isinstance(it.get("text"), str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(it.get("due_date") or ""))
                and str(it.get("status") or "pending")
                in ("pending", "done", "expired")
            ):
                out.append(it)
        return out

    def save(self, commitments: list[dict]) -> bool:
        try:
            _atomic_write_json(
                self._path, {"version": COMMIT_VERSION, "commitments": list(commitments)}
            )
            return True
        except Exception:  # noqa: BLE001
            return False


__all__ = [
    "COMMIT_VERSION",
    "EXPIRE_GRACE_DAYS",
    "MAX_PENDING_PER_UMO",
    "CommitmentStore",
    "add_commitments",
    "due_for_date",
    "due_today",
    "expire_stale",
    "mark_resolved",
    "normalize_commitment",
    "parse_due_date",
    "parse_llm_array",
    "parse_llm_commitments",
    "prune_for_save",
    "regex_extract_commitments",
    "render_commitment_line",
]
