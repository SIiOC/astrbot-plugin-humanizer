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


def build_fixtures(persona: str = "custom") -> dict:
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
    growth_scope = "a" * 64
    growth_diary = {
        "window_days": 7,
        "tz_offset_minutes": -480,
        "event_count": 18,
        "active_days": 5,
        "streak_days": 2,
        "days": [
            {"date": f"2026-10-{day:02d}", "user_turns": user, "bot_turns": bot,
             "proactive_turns": pro, "user_chars": user * 12, "bot_chars": bot * 20,
             "first_at": now - 86400 * (30 - day), "last_at": now - 86400 * (30 - day) + 3600}
            for day, user, bot, pro in (
                (24, 2, 2, 0), (25, 0, 0, 0), (26, 1, 1, 1), (27, 3, 3, 1),
                (28, 0, 0, 0), (29, 2, 2, 0), (30, 1, 1, 0),
            )
        ],
        "totals": {"user_turns": 9, "bot_turns": 9, "proactive_turns": 2,
                   "user_chars": 108, "bot_chars": 180},
        "active_hours": [0, 1, 0, 2, 0, 0, 0, 0, 3, 2, 0, 0,
                         1, 0, 0, 2, 0, 0, 3, 1, 0, 0, 1, 0],
    }
    # v4.8.1：--persona 让冒烟覆盖「人格已选中」的真实状态（提示条/总览 chip/主动开关）
    if "persona" in config and "preset" in config["persona"]:
        config["persona"]["preset"] = persona
    profile_labels = {
        "custom": "自定义",
        "reserved": "克制",
        "natural": "自然",
        "clingy": "黏人",
        "work": "工作",
    }
    profile_modes = {
        "custom": ("custom", "custom", "custom"),
        "reserved": ("simple", "simple", "reserved"),
        "natural": ("standard", "standard", "standard"),
        "clingy": ("full", "full", "clingy"),
        "work": ("simple", "simple", "reserved"),
    }
    modes = profile_modes.get(persona, profile_modes["custom"])
    return {
        "config": {"ok": True, "config": config, "schema_meta": meta, "options": {}},
        "status": {
            "ok": True,
            "status": {
                "enabled": True,
                "proactive": persona != "work",
                "proactive_quiet_hours": "23:00-08:00",
                "style_enabled": True,
                "active_style": "默认风格",
                "life_enabled": True,
                "tracked_sessions": 3,
                "styles": ["默认风格", "聊天风格"],
                # v4.8.0：跨域人格（服务端真实返回同名字段）
                "profile": persona,
                "profile_label": profile_labels.get(persona, persona),
                "awareness_mode": modes[0],
                "emotion_mode": modes[1],
                "proactive_preset": modes[2],
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
            "cache": {
                "hits": 3,
                "misses": 1,
                "hit_rate": 75.0,
                "recent": [True, False, True, True, False, True],
            },
            "inject": {
                "turns": 8,
                "total_chars": 960,
                "avg_chars": 120.0,
                "breakdown": {},
                "recent": [80, 120, 60, 0, 150, 90, 200, 110],
                # v4.8.0：声明式注入管线
                "pipeline": [
                    {"name": "time", "label": "时间上下文", "priority": 10,
                     "placement": "extra_tail", "depends_on": [], "last_chars": 90},
                    {"name": "emotion", "label": "情绪惯性", "priority": 30,
                     "placement": "system", "depends_on": [], "last_chars": 60},
                    {"name": "style", "label": "说话风格", "priority": 60,
                     "placement": "system", "depends_on": [], "last_chars": 220},
                ],
            },
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
        "growth/state": {"ok": True, "state": {"enabled": True, "scope_id": "", "scopes": [
            {"id": growth_scope, "event_count": 18, "last_event_ts": now}
        ], "degraded": False}},
        "growth/events": {"ok": True, "events": [
            {"schema_version": 1, "event_id": "u1", "type": "user_turn", "at": now - 300, "text_length": 12},
            {"schema_version": 1, "event_id": "b1", "type": "bot_turn", "at": now - 280, "text_length": 20, "source": "reply"},
            {"schema_version": 1, "event_id": "b2", "type": "bot_turn", "at": now - 260, "text_length": 18, "source": "proactive"},
        ]},
        "growth/diary": {"ok": True, "diary": growth_diary},
        "models": {"ok": True, "models": []},
    }


MOCK_JS = """
(() => {
  const DATA = __DATA__;
  window.AstrBotPluginPage = {
    ready: () => Promise.resolve({}),
    apiGet: (path) => Promise.resolve(DATA[path] || { ok: true }),
    apiPost: (path, body) => {
      // v4.8.2：模拟「人格快捷切换」真实副作用，便于冒烟走完整用户路径
      if (path === 'config/save' && body && body.persona && body.persona.preset) {
        const preset = body.persona.preset;
        const labels = { custom: '自定义', reserved: '克制', natural: '自然',
                         clingy: '黏人', work: '工作' };
        const st = DATA.status && DATA.status.status;
        if (st) {
          st.profile = preset;
          st.profile_label = labels[preset] || preset;
          st.proactive = preset !== 'work';
        }
      }
      return Promise.resolve({ ok: true, rules: (DATA.rules && DATA.rules.rules) || [] });
    },
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
    ap.add_argument("--theme", choices=("light", "night"), default="light", help="控制台主题")
    ap.add_argument(
        "--config-view",
        choices=("simple", "expert"),
        default="expert",
        help="配置页视图（expert=全量，simple=常用旋钮）",
    )
    ap.add_argument("--width", type=int, default=1440, help="视口宽度（响应式自检用）")
    ap.add_argument("--height", type=int, default=960, help="视口高度")
    ap.add_argument(
        "--persona",
        choices=("custom", "reserved", "natural", "clingy", "work"),
        default="custom",
        help="以某个人格预设渲染（检查提示条/总览 chip/主动状态）",
    )
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
    theme_init = (
        "try{localStorage.setItem('humanizer-console-theme','night')}catch(e){}"
        if args.theme == "night"
        else ""
    )
    # v4.8.0：冒烟默认用专家视图跑配置页，保证全量 .cfg-item 都被渲染；
    # --config-view simple 可单独验证简单视图（截图会保留切换条）。
    config_init = (
        "try{localStorage.setItem('humanizer-config-simple','%s')}catch(e){}"
        % ("1" if args.config_view == "simple" else "0")
    )
    # 简单视图下 .cfg-item 数量少，跳过「≥10 项」断言
    config_min_items = 10 if args.config_view == "expert" else 1
    suffix = "-night" if args.theme == "night" else ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=exe) if exe else p.chromium.launch(
                headless=True, channel="msedge")
            page = browser.new_page(viewport={"width": args.width, "height": args.height})
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url} ({r.failure})") if "127.0.0.1" not in r.url else None)
            page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                    if (m.type == "error" and "favicon" not in m.text) else None)
            page.add_init_script(
                theme_init
                + config_init
                + MOCK_JS.replace("__DATA__", json.dumps(build_fixtures(args.persona)))
            )
            page.goto(url, wait_until="load")
            page.wait_for_selector(".hz-menu .nav-item", timeout=20000)
            page.wait_for_timeout(900)
            theme_now = page.evaluate("document.documentElement.dataset.theme || 'light'")
            if theme_now != args.theme:
                errors.append(f"主题未生效: 期望 {args.theme}，实际 {theme_now}")

            overview_text = page.inner_text("body")
            if "时间：" not in overview_text:
                errors.append("总览页缺少时间档位 chip")
            if args.persona != "custom" and "表达基调：" not in overview_text:
                errors.append("总览页缺少人格 chip")
            # v4.8.0：首装向导按真实状态显示完成度
            # mock：语料/风格已完成；人格未定 → 2/3，persona=work 时人格也完成 → 3/3
            expected_done = "2 / 3" if args.persona == "custom" else "3 / 3"
            if "三步开始" not in overview_text:
                errors.append("总览缺少首装向导")
            if f"已完成 {expected_done}" not in overview_text:
                errors.append(f"首装向导完成度未按状态计算（期望已完成 {expected_done}）")

            # v4.8.2：人格快捷切换真实路径（点「工作」→ 确认 → chip 变更 → 切回自定义）
            if args.persona == "custom":
                try:
                    work_btn = page.get_by_role("button", name="工作", exact=True)
                    if not work_btn.count():
                        errors.append("总览缺少人格快捷切换按钮")
                    else:
                        work_btn.first.click()
                        page.wait_for_timeout(300)
                        dlg_btn = page.locator(".n-dialog").get_by_role(
                            "button", name="切换", exact=True
                        )
                        if not dlg_btn.count():
                            errors.append("人格切换缺少确认弹窗")
                        else:
                            dlg_btn.first.click()
                            page.wait_for_timeout(700)
                            try:
                                page.wait_for_function(
                                    "document.body.innerText.includes('表达基调：工作')",
                                    timeout=5000,
                                )
                            except Exception:  # noqa: BLE001
                                errors.append("人格快捷切换未生效（chip 未变为工作）")
                            page.screenshot(
                                path=os.path.join(args.shots, "1b-总览-人格切换.png"),
                                full_page=True,
                            )
                            # 恢复初始 mock 状态：重载页面（init script 会重建 fixtures）
                            page.reload(wait_until="load")
                            page.wait_for_selector(
                                ".hz-menu .nav-item", timeout=20000
                            )
                            page.wait_for_timeout(700)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"人格快捷切换异常: {e}")

            nav = page.locator(".hz-menu .nav-item")
            titles = [nav.nth(i).inner_text().strip() for i in range(nav.count())]
            pages.append(("nav", titles))
            # v4.8.0：导航按任务分组渲染，DOM 顺序为 像个人 → 别被识破 → 主动找人 → 调校排障
            expect = ["总览", "语料与风格", "成长档案", "记录回看", "真人感规则", "主动聊天", "配置", "统计"]
            if titles != expect:
                errors.append(f"导航顺序/数量不符: {titles}")

            for i, title in enumerate(expect):
                nav.nth(i).click()
                page.wait_for_timeout(650)
                shot = os.path.join(args.shots, f"{i + 1}-{title}{suffix}.png")
                page.screenshot(path=shot, full_page=True)
                body = page.inner_text("body")
                if len(body.strip()) < 20:
                    errors.append(f"{title}: 页面内容为空")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth - window.innerWidth"
                )
                if overflow > 2:
                    offenders = page.evaluate(
                        """() => {
                          const w = window.innerWidth;
                          const out = [];
                          for (const el of document.querySelectorAll('body *')) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.right > w + 1) {
                              const cls = String(el.className || '').split(' ').filter(Boolean).slice(0, 2).join('.');
                              out.push(`${el.tagName.toLowerCase()}${cls ? '.' + cls : ''} right=${Math.round(r.right)} w=${Math.round(r.width)}`);
                              if (out.length >= 5) break;
                            }
                          }
                          return out;
                        }"""
                    )
                    errors.append(
                        f"{title}: 页面横向溢出 {overflow}px：{'；'.join(offenders)}"
                    )
                pages.append((title, len(body)))
                if title == "成长档案":
                    scope_btn = page.locator(".scope-row").first
                    if not scope_btn.count():
                        errors.append("成长档案: mock 未提供可选会话")
                    else:
                        scope_btn.click()
                        page.wait_for_timeout(600)
                        growth_text = page.inner_text("body")
                        if "成长日记（事实版）" not in growth_text:
                            errors.append("成长档案: 选择会话后缺少成长日记")
                        if "连续记录" not in growth_text:
                            errors.append("成长档案: 成长日记缺少连续记录摘要")
                        page.screenshot(
                            path=os.path.join(args.shots, "3b-成长档案-日记.png"),
                            full_page=True,
                        )
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
                    if page.locator(".cfg-item").count() < config_min_items:
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


