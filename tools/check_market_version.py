#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查插件市场版本与本机工作副本的差距（v4.7.0）。

用途：发布后确认「GitHub 推送 → 市场收录」是否已跟进，避免出现
「本机 v4.7.0、市场还停在 v4.1.9」却无人发现的情况。

用法：
    python tools/check_market_version.py [--repo SIiOC/astrbot-plugin-humanizer] [--json]

退出码：0=市场版本与本机一致；1=市场落后（打印差距）；2=检查失败（网络/数据异常）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
MARKET_URL = "https://api.soulter.top/astrbot/plugins"


def local_version(root: Path = PLUGIN_ROOT) -> str:
    """读取 metadata.yaml 的 version。"""
    text = (root / "metadata.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*['\"]?([^'\"\n]+)", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_entry(data: dict, repo: str, name: str) -> dict | None:
    """从市场 JSON 中按仓库地址/插件名找到条目。"""
    for key, entry in (data or {}).items():
        if not isinstance(entry, dict):
            continue
        if entry.get("repo", "").rstrip("/").lower().endswith(
            repo.rstrip("/").lower().split("github.com/")[-1]
        ):
            return entry
        if entry.get("name") == name:
            return entry
    return None


def version_tuple(version: str) -> tuple[int, ...]:
    """把 x.y.z 转成可比较元组（非数字部分忽略）。"""
    parts = re.findall(r"\d+", version or "")
    return tuple(int(part) for part in parts[:3]) or (0,)


def fetch_market(url: str = MARKET_URL, timeout: int = 30) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "humanizer-version-check"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查插件市场版本")
    parser.add_argument("--repo", default="SIiOC/astrbot-plugin-humanizer")
    parser.add_argument("--name", default="astrbot_plugin_wanna_be_human")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    local = local_version()
    try:
        data = fetch_market()
    except Exception as exc:  # noqa: BLE001
        print(f"[market-check] 无法访问市场接口: {exc}", file=sys.stderr)
        return 2
    entry = extract_entry(data, args.repo, args.name)
    if not entry:
        print("[market-check] 市场未收录该插件（检查 repo/name）", file=sys.stderr)
        return 2
    market = str(entry.get("version") or "")
    behind = version_tuple(market) < version_tuple(local)
    payload = {
        "local": local,
        "market": market,
        "commit_sha": entry.get("commit_sha"),
        "updated_at": entry.get("updated_at"),
        "behind": behind,
        "up_to_date": market == local,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[market-check] 本机 {local or '未知'} / 市场 {market or '未知'}")
        if payload["up_to_date"]:
            print("[market-check] 市场已是最新版本")
        elif behind:
            print(f"[market-check] 市场落后（commit {entry.get('commit_sha', '')[:8]}，"
                  f"更新于 {entry.get('updated_at', '')}）")
        else:
            print("[market-check] 市场版本高于本机（可能已发布新版本）")
    return 0 if payload["up_to_date"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
