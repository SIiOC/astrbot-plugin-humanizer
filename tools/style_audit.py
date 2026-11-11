# -*- coding: utf-8 -*-
"""风格审计：对比「用户真实语料」与「bot 最近回复」的输出形式分布。

只读 AstrBot 的 data_v4.db 与本插件 user_corpus.jsonl，不打印聊天内容。
用于 v4.9.4/v4.9.5 风格指纹上线前后的实际效用验证：

    python tools/style_audit.py
    python tools/style_audit.py --limit 60 --json audit.json

指标：平均/中位句长、短句/长段比例、问句/感叹/句号/省略号比例、逗号数、语气词比例。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from style_core.corpus import read_pool
from style_core.fingerprint import collect_user_texts, compute_fingerprint

_COMPARE_KEYS = (
    ("avg_chars", "平均句长"),
    ("median_chars", "中位句长"),
    ("short_ratio", "短句占比"),
    ("long_ratio", "长段占比"),
    ("question_ratio", "问句占比"),
    ("ellipsis_ratio", "省略号占比"),
    ("particle_ratio", "语气词占比"),
    ("comma_per_msg", "逗号/条"),
)


def _content_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return ""


def load_conversation(db_path: str, conversation_id: str = "") -> tuple[str, list[dict]]:
    """返回 (conversation_id, messages)；只读，找不到返回 ("", [])。"""
    if not os.path.exists(db_path):
        return "", []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        if conversation_id:
            row = con.execute(
                "select conversation_id, content from conversations where conversation_id=?",
                (conversation_id,),
            ).fetchone()
        else:
            row = con.execute(
                "select conversation_id, content from conversations "
                "where platform_id='qq_napcat' order by updated_at desc limit 1"
            ).fetchone()
        if not row:
            return "", []
        try:
            data = json.loads(row["content"])
        except (TypeError, ValueError):
            return row["conversation_id"], []
        return row["conversation_id"], [m for m in data if isinstance(m, dict)]
    finally:
        con.close()


def assistant_texts(messages: list[dict], limit: int = 40, after_index: int = 0) -> list[str]:
    """取 after_index 之后的 assistant 文本（用于只看重载后的新回复）。"""
    texts = []
    for message in messages[max(0, int(after_index)):]:
        if message.get("role") == "assistant":
            text = _content_text(message).strip()
            if text:
                texts.append(text)
    return texts[-max(1, limit):]


_SENT_RE = re.compile(r"Prepare to send - .*?: (.*)$")


def parse_sent_texts(log_path: str, limit: int = 40) -> list[str]:
    """从 astrbot.log 的 ``Prepare to send`` 行提取**实际发送**的文本。

    DB 的 conversation content 可能是实现层改写前的原始 LLM 回复；只有发送
    日志才包含最终发给用户的文本（含风格实现层修改）。找不到日志返回 []。
    """
    if not log_path or not os.path.exists(log_path):
        return []
    texts: list[str] = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "Prepare to send - " not in line:
                    continue
                match = _SENT_RE.search(line)
                if match:
                    text = match.group(1).strip()
                    if text:
                        texts.append(text)
    except OSError:
        return []
    return texts[-max(1, limit):]


def check_goal(target: dict, actual: dict, rows: list[dict]) -> list[dict]:
    """按目标硬指标判定（8 项偏差 + 句长/省略号/语气词/短句）。"""
    deviations = sum(1 for row in rows if row["status"] != "ok")
    avg_target = float(target.get("avg_chars") or 0)
    avg_actual = float(actual.get("avg_chars") or 0)
    return [
        {
            "label": "8 项偏差 ≤3",
            "actual": f"{deviations}/8",
            "pass": deviations <= 3,
        },
        {
            "label": f"平均句长 {avg_target:.1f}±7",
            "actual": f"{avg_actual:.1f}",
            "pass": abs(avg_actual - avg_target) <= 7,
        },
        {
            "label": "省略号 ≥25%",
            "actual": f"{float(actual.get('ellipsis_ratio') or 0) * 100:.0f}%",
            "pass": float(actual.get("ellipsis_ratio") or 0) >= 0.25,
        },
        {
            "label": "语气词 ≥30%",
            "actual": f"{float(actual.get('particle_ratio') or 0) * 100:.0f}%",
            "pass": float(actual.get("particle_ratio") or 0) >= 0.30,
        },
        {
            "label": "短句 <10字 ≥8%",
            "actual": f"{float(actual.get('short_ratio') or 0) * 100:.0f}%",
            "pass": float(actual.get("short_ratio") or 0) >= 0.08,
        },
    ]


def compare(target: dict, actual: dict) -> list[dict]:
    rows = []
    for key, label in _COMPARE_KEYS:
        t = float(target.get(key) or 0)
        a = float(actual.get(key) or 0)
        delta = round(a - t, 3)
        rows.append(
            {
                "key": key,
                "label": label,
                "target": t,
                "actual": a,
                "delta": delta,
                "status": "ok" if _within(key, t, a) else "偏差",
            }
        )
    return rows


def _within(key: str, target: float, actual: float) -> bool:
    """宽松的「同量级」判定；不是精确统计检验。"""
    if key in ("avg_chars", "median_chars"):
        return abs(actual - target) <= max(4.0, target * 0.35)
    if key == "comma_per_msg":
        return abs(actual - target) <= 0.5
    if key.endswith("_ratio"):
        return abs(actual - target) <= 0.15
    return abs(actual - target) <= 1.0


def _fmt(value: float, key: str) -> str:
    if key.endswith("_ratio"):
        return f"{value * 100:.0f}%"
    return f"{value:.1f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="对比用户语料与 bot 回复的风格分布")
    ap.add_argument("--db", default="", help="data_v4.db 路径；缺省取 ASTRBOT_ROOT/data/data_v4.db")
    ap.add_argument("--corpus", default="", help="user_corpus.jsonl 路径")
    ap.add_argument("--conversation-id", default="", help="指定会话；缺省取最近 QQ 私聊")
    ap.add_argument("--limit", type=int, default=40, help="取最近 N 条 bot 回复")
    ap.add_argument(
        "--after-index",
        type=int,
        default=0,
        help="只看第 N 条消息之后的新回复（重载后验证用，例如 86）",
    )
    ap.add_argument("--json", default="", help="把报告写到 JSON 文件")
    ap.add_argument(
        "--from-log",
        nargs="?",
        const="auto",
        default=None,
        help="从 astrbot.log 的 Prepare to send 提取实际发送文本（推荐，含实现层修改）",
    )
    ap.add_argument("--strict", action="store_true", help="有偏差时返回非零（默认只报告）")
    args = ap.parse_args(argv)

    root = os.environ.get("ASTRBOT_ROOT", "")
    db_path = args.db or os.path.join(root, "data", "data_v4.db")
    corpus_path = args.corpus or os.path.join(
        root, "data", "plugin_data", "astrbot_plugin_wanna_be_human", "user_corpus.jsonl"
    )
    if not os.path.exists(corpus_path):
        print(f"[style-audit] 找不到语料: {corpus_path}")
        return 2

    target = compute_fingerprint(collect_user_texts(read_pool(corpus_path)))
    source = "log" if args.from_log is not None else "db"
    conversation_id = ""
    messages: list[dict] = []
    if source == "log":
        log_path = (
            os.path.join(root, "data", "logs", "astrbot.log")
            if args.from_log == "auto"
            else args.from_log
        )
        replies = parse_sent_texts(log_path, args.limit)
        conversation_id = f"log:{os.path.basename(log_path)}"
    else:
        conversation_id, messages = load_conversation(db_path, args.conversation_id)
        if not messages:
            print(f"[style-audit] 找不到会话（db={db_path}）")
            return 2
        replies = assistant_texts(messages, args.limit, args.after_index)
    if not replies:
        report = {
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "after_index": args.after_index,
            "corpus_sample": target.get("sample_size", 0),
            "reply_sample": 0,
            "rows": [],
            "goal_checks": [],
            "goal_pass": False,
            "note": "没有可审计回复；请先正常聊 5–10 轮",
        }
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"没有可审计回复（source={source}）。")
        print("无法判定：请先正常聊 5–10 轮，再运行本工具。")
        return 0 if not args.strict else 1
    actual = compute_fingerprint(replies)
    goal_checks = check_goal(target, actual, compare(target, actual))

    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "conversation_id": conversation_id,
        "message_count": len(messages),
        "after_index": args.after_index,
        "corpus_sample": target.get("sample_size", 0),
        "reply_sample": actual.get("sample_size", 0),
        "rows": compare(target, actual),
        "goal_checks": goal_checks,
        "goal_pass": all(item["pass"] for item in goal_checks),
    }
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"会话: {conversation_id}  语料样本: {report['corpus_sample']}  bot 回复样本: {report['reply_sample']}")
    print(f"{'指标':<10} {'语料目标':>10} {'bot 实际':>10} {'差值':>10}  状态")
    for row in report["rows"]:
        key = row["key"]
        print(
            f"{row['label']:<10} {_fmt(row['target'], key):>10} {_fmt(row['actual'], key):>10} "
            f"{_fmt(row['delta'], key):>10}  {row['status']}"
        )
    deviations = sum(1 for row in report["rows"] if row["status"] != "ok")
    print(f"偏差项: {deviations}/{len(report['rows'])}")
    print("目标判定:", "达标" if report["goal_pass"] else "未达标")
    for item in goal_checks:
        print(f"  [{'通过' if item['pass'] else '未通过'}] {item['label']}：{item['actual']}")
    return 1 if args.strict and deviations else 0


if __name__ == "__main__":
    raise SystemExit(main())
