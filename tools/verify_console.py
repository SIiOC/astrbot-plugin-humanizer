# -*- coding: utf-8 -*-
"""控制台构建产物运行时冒烟（Playwright + 本机 Edge，无网络依赖）。

用法：
    python tools/verify_console.py [--shots 目录]

流程：用 http.server 托管 pages/humanizer-console，基于 _conf_schema.json 生成
mock 桥接数据（window.AstrBotPluginPage），逐页打开 7 个页面，收集 JS 错误并截图。
退出码 0 = 7 页均可渲染且无 JS 异常。
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "pages", "humanizer-console")
SCHEMA = os.path.join(ROOT, "_conf_schema.json")

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def build_fixtures() -> dict:
    schema = json.load(open(SCHEMA, encoding="utf-8"))
    config = {}
    meta = {}
    for group, g in schema.items():
        config[group] = {}
        items_meta = {}
        for key, item in (g.get("items") or {}).items():
            default = item.get("default")
            if default is None:
                default = "" if item.get("type") == "string" else 0
            config[group][key] = default
            m = {
                "description": item.get("description", ""),
                "hint": item.get("hint", ""),
                "type": item.get("type", ""),
            }
            if item.get("options"):
                m["options"] = list(item["options"])
            items_meta[key] = m
        meta[group] = {
            "description": g.get("description", ""),
            "hint": g.get("hint", ""),
            "items": items_meta,
        }
    now = 1759000000
    return {
        "config": {"ok": True, "config": config, "schema_meta": meta, "options": {}},
        "status": {
            "ok": True,
            "status": {
                "enabled": True,
                "proactive": True,
                "proactive_quiet_hours": "23:00-08:00",
                "style_enabled": True,
                "active_style": "默认风格",
                "life_enabled": True,
                "tracked_sessions": 3,
                "styles": ["默认风格", "聊天风格"],
            },
        },
        "dashboard": {
            "ok": True,
            "rhythm": {"mode": "warm", "score": 55.5},
            "emotions": [
                {"umo": "qq:FriendMessage:123456", "emotion": "appy", "intensity": 0.6, "ts": now}
            ],
            "next_proactive": now + 1800,
            "events": [
                {"ts": now, "tag": "去痕", "msg": "规则清理命中 2 处"},
                {"ts": now - 60, "tag": "分段", "msg": "回复拆分为 2 条消息发送"},
                {"ts": now - 120, "tag": "主动", "msg": "主动消息已发送"},
            ],
        },
        "stats": {
            "ok": True,
            "stats": {
                "rules_hit": 12,
                "proactive_sent": 3,
                "style_built": 1,
                "proactive_interject_dropped": 2,
                "qc_hits": 0,
                "qc_checked": 40,
                "split_sent": 5,
                "typing_delay_applied": 22,
                "debounce_merged": 7,
            },
        },
        "rules": {
            "ok": True,
            "rules": [
                {"id": "r1", "name": "不主动提自己是 AI", "type": "inject", "severity": "S2",
                 "enabled": True, "builtin": True, "content": "不要自称 AI 或语言模型。"},
                {"id": "r2", "name": "禁宣誓句", "type": "qc", "severity": "S1",
                 "enabled": False, "builtin": False, "content": "不用宣誓式表达。",
                 "qc_pattern": "我发誓，千真万确"},
            ],
        },
        "styles": {"ok": True, "styles": [{"name": "默认风格", "source": "builtin", "count": 30}],
                   "current": "默认风格"},
        "corpus": {"ok": True, "total": 10379, "builtin": 10379, "user": 0, "files": []},
        "proactive": {
            "ok": True,
            "enabled": True,
            "silence_after_minutes": 45,
            "silence_fluctuation_minutes": 15,
            "quiet_hours": "23:00-08:00",
            "quiet_grace_minutes": 5,
            "pout_on_unanswered": True,
            "sessions": [
                {"umo": "qq:FriendMessage:123456", "status": "静默中",
                 "next_trigger": "12:45", "unanswered": 1, "silence_hours": 0.5}
            ],
        },
        "sessions": {"ok": True, "sessions": [{"umo": "qq:FriendMessage:123456", "label": "QQ 好友 123456"}]},
        "models": {"ok": True, "models": []},
    }


MOCK_JS = """
(() => {
  const DATA = __DATA__;
  window.AstrBotPluginPage = {
    ready: () => Promise.resolve({}),
    apiGet: (path) => Promise.resolve(DATA[path] || { ok: true }),
    apiPost: (path) => Promise.resolve({ ok: true, rules: (DATA.rules && DATA.rules.rules) || [] }),
    upload: () => Promise.resolve({ ok: true }),
    download: () => Promise.resolve(),
  };
})();
"""


def start_server() -> ThreadingHTTPServer:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=DIST)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default=os.path.join(os.path.dirname(ROOT), "_verify", "console"))
    args = ap.parse_args()
    os.makedirs(args.shots, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        print(f"SKIP: playwright 不可用: {e}")
        return 0

    exe = next((p for p in EDGE_PATHS if os.path.exists(p)), None)
    httpd = start_server()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    errors: list[str] = []
    pages = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=exe) if exe else p.chromium.launch(
                headless=True, channel="msedge")
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url} ({r.failure})") if "127.0.0.1" not in r.url else None)
            page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                    if (m.type == "error" and "favicon" not in m.text) else None)
            page.add_init_script(MOCK_JS.replace("__DATA__", json.dumps(build_fixtures())))
            page.goto(url, wait_until="load")
            page.wait_for_selector(".hz-menu .nav-item", timeout=20000)
            page.wait_for_timeout(900)

            overview_text = page.inner_text("body")
            if "时间：按细分开关" not in overview_text:
                errors.append("总览页缺少时间档位 chip")

            nav = page.locator(".hz-menu .nav-item")
            titles = [nav.nth(i).inner_text().strip() for i in range(nav.count())]
            pages.append(("nav", titles))
            expect = ["总览", "配置", "语料与风格", "主动聊天", "记录回看", "真人感规则", "统计"]
            if titles != expect:
                errors.append(f"导航顺序/数量不符: {titles}")

            for i, title in enumerate(expect):
                nav.nth(i).click()
                page.wait_for_timeout(650)
                shot = os.path.join(args.shots, f"{i + 1}-{title}.png")
                page.screenshot(path=shot, full_page=True)
                body = page.inner_text("body")
                if len(body.strip()) < 20:
                    errors.append(f"{title}: 页面内容为空")
                pages.append((title, len(body)))
                if title == "配置":
                    page.get_by_text("感知 · 时间与节奏", exact=False).first.click()
                    page.wait_for_timeout(500)
                    page.screenshot(
                        path=os.path.join(args.shots, "2b-配置-时间档位.png"),
                        full_page=True,
                    )
                    tab_text = page.inner_text("body")
                    if "时间感知档位" not in tab_text:
                        errors.append("配置页「时间与节奏」缺少档位项")
                    if page.locator(".cfg-item").count() < 10:
                        errors.append("配置页设置卡数量异常（.cfg-item）")
                    for tab_label, expect in (
                        ("感知 · 情绪惯性", "情绪机制档位"),
                        ("主动 · 聊天与追问", "主动聊天预设"),
                    ):
                        page.get_by_text(tab_label, exact=False).first.click()
                        page.wait_for_timeout(400)
                        if expect not in page.inner_text("body"):
                            errors.append(f"配置页缺少 {expect}")
            browser.close()
    finally:
        httpd.shutdown()

    print("== pages ==")
    for name, val in pages:
        print(f"  {name}: {val}")
    print(f"== errors ({len(errors)}) ==")
    for e in errors:
        print("  -", e)
    print("shots:", args.shots)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())


