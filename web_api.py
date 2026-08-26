# -*- coding: utf-8 -*-
"""
Humanizer 插件页面（Plugin Pages）后端薄封装。

通过 AstrBot 的 register_web_api 机制注册一组端点，供
pages/humanizer-console/ 前端（Vue3+Vite 构建产物）调用。
复用 main.py 已有方法与纯函数（style_core/*、humanizer_core/*），
不引入新业务逻辑。

端点：
- 配置：GET /config、POST /config/save
- 状态：GET /status
- 风格：GET /styles、POST /styles/use、POST /styles/build、
         POST /styles/correct、POST /styles/import-colleague
- 语料：GET /corpus、POST /corpus/import
- 主动聊天：GET /proactive
- 模型：GET /models、POST /models/set-rewrite
- 记录：GET /sessions、GET /sessions/history
- 统计：GET /stats

版本守卫：register_web_api 是 v4.24.2 引入的 Plugin Pages API；在旧版本
（Humanizer 声明兼容 >=4.5.7）上静默跳过注册，页面不加载，插件其余功能不受影响。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot.api.star import Context

PLUGIN_NAME = "astrbot_plugin_humanizer"
_PAGE_PREFIX = f"/{PLUGIN_NAME}"

# v2.9.4：路由表改为「方法名」规格（模块级常量，可被测试直接校验完整性）。
# 曾发生的事故：方法以绑定形式写在函数局部列表里，某次编辑错位使类缺失
# get_stats 属性 → 注册循环 AttributeError 被吞 → 全部路由丢失、页面 404。
ROUTE_SPECS: tuple[tuple[str, str, list[str], str], ...] = (
    ("config", "get_config", ["GET"], "读取配置"),
    ("config/save", "save_config", ["POST"], "保存配置"),
    ("status", "get_status", ["GET"], "运行时状态"),
    ("styles", "list_styles", ["GET"], "风格档案列表"),
    ("styles/use", "use_style", ["POST"], "切换风格"),
    ("styles/build", "build_style", ["POST"], "提炼风格"),
    ("styles/generate", "generate_style", ["POST"], "生成风格档案"),
    ("styles/correct", "correct_style", ["POST"], "记录纠错"),
    ("styles/import-colleague", "import_colleague", ["POST"], "导入人格文本"),
    ("corpus", "get_corpus", ["GET"], "语料统计"),
    ("corpus/import", "import_corpus", ["POST"], "导入语料文本"),
    ("corpus/upload", "upload_corpus", ["POST"], "上传语料文件"),
    ("proactive", "get_proactive", ["GET"], "主动聊天状态"),
    ("models", "list_models", ["GET"], "模型列表"),
    ("models/set-rewrite", "set_rewrite_model", ["POST"], "设置改写模型"),
    ("sessions", "list_sessions", ["GET"], "会话列表"),
    ("sessions/history", "get_session_history", ["GET"], "会话消息流"),
    ("stats", "get_stats", ["GET"], "统计"),
)


def register_web_routes(context: "Context", plugin) -> None:
    """注册所有页面 API 路由（有 register_web_api 才注册，旧版本静默跳过）。"""
    if not hasattr(context, "register_web_api"):
        return
    api = HumanizerWebAPI(plugin)
    registered = 0
    for suffix, attr, methods, description in ROUTE_SPECS:
        handler = getattr(api, attr, None)
        if not callable(handler):
            # 类缺方法的编辑错位事故必须在此暴露，而不是静默丢掉整批路由
            _log_error(f"端点 {attr} 缺失于 HumanizerWebAPI，/…/{suffix} 未注册")
            continue
        try:
            context.register_web_api(
                f"{_PAGE_PREFIX}/{suffix}", handler, methods, description
            )
            registered += 1
        except Exception as e:  # noqa: BLE001
            _log_error(f"端点 {_PAGE_PREFIX}/{suffix} 注册失败: {e}")
    total = len(ROUTE_SPECS)
    if registered == total:
        _log_info(f"插件控制台 Web API 已注册 {registered}/{total} 个端点")
    else:
        _log_error(f"插件控制台 Web API 仅注册 {registered}/{total} 个端点（有缺失！）")


class HumanizerWebAPI:
    """页面数据接口。复用插件实例的配置与业务方法，不持有独立状态。"""

    def __init__(self, plugin) -> None:
        self.plugin = plugin

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    async def get_config(self) -> Any:
        from astrbot.api.web import json_response

        # v2.8.1：包 try——config 文件损坏/加载失败时返回空配置而非 500，
        # 避免页面"配置读取失败"。
        try:
            config = self.plugin.config
            groups = ("humanize", "proactive", "style", "life")
            result = {
                g: (dict(config.get(g, {})) if isinstance(config.get(g), dict) else {})
                for g in groups
            }
        except Exception:  # noqa: BLE001
            result = {g: {} for g in ("humanize", "proactive", "style", "life")}
        # v2.9：附带 _conf_schema.json 的 description/hint（前端用于中文 label 与提示）
        meta = _load_config_schema()
        return json_response({"ok": True, "config": result, "schema_meta": meta})

    async def save_config(self) -> Any:
        from astrbot.api.web import json_response, request

        try:
            payload = await request.json() or {}
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "请求体不是有效 JSON"}, status_code=400)
        groups = ("humanize", "proactive", "style", "life")
        updates = {g: payload.get(g) for g in groups if isinstance(payload.get(g), dict)}
        if not updates:
            return json_response({"ok": False, "error": "没有可保存的配置分组"}, status_code=400)
        for g, values in updates.items():
            current = self.plugin.config.get(g)
            if not isinstance(current, dict):
                current = {}
                self.plugin.config[g] = current
            # 只合并已有键（不接受任意新键），避免脏数据
            for key, value in values.items():
                if key in current:
                    current[key] = value
        try:
            await self.plugin.config.save_config_async()
        except Exception:  # noqa: BLE001
            try:
                self.plugin.config.save_config()
            except Exception:  # noqa: BLE001
                return json_response({"ok": False, "error": "配置保存失败"}, status_code=500)
        return json_response({"ok": True, "saved": list(updates)})

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    async def get_status(self) -> Any:
        from astrbot.api.web import json_response

        plugin = self.plugin
        status = {
            "enabled": bool(plugin._h("enabled", True)),
            "llm_rewrite": bool(plugin._h("enable_llm_rewrite", False)),
            "rewrite_model": str(plugin._h("rewrite_model") or ""),
            "proactive": bool(plugin._p("enable_proactive", False)),
            "proactive_quiet_hours": str(plugin._p("proactive_quiet_hours") or ""),
            "style_enabled": bool(plugin._cfg("enabled", True)),
            "active_style": str(plugin._cfg("active_style") or ""),
            "life_enabled": bool(plugin._life("enable_life", True)),
            "tracked_sessions": len(getattr(plugin, "_next_trigger_ts", {}) or {}),
        }
        # 风格档案列表
        try:
            names = [p.get("name", "") for p in _list_profiles(plugin)]
            status["styles"] = [n for n in names if n]
        except Exception:  # noqa: BLE001
            status["styles"] = []
        return json_response({"ok": True, "status": status})

    # ------------------------------------------------------------------
    # 风格管理
    # ------------------------------------------------------------------
    async def list_styles(self) -> Any:
        from astrbot.api.web import json_response

        try:
            profiles = _list_profiles(self.plugin)
            current = self.plugin._effective_active_style()
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"风格读取失败: {e}"}, status_code=500)
        return json_response({"ok": True, "styles": profiles, "current": current})

    async def use_style(self) -> Any:
        from astrbot.api.web import json_response, request

        try:
            payload = await request.json() or {}
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "请求体不是有效 JSON"}, status_code=400)
        name = str(payload.get("name") or "").strip()
        # 与档案校验（1-32 字）对齐——超限名会导致写盘成功但读取校验永远失败
        if not (1 <= len(name) <= 32):
            return json_response({"ok": False, "error": "风格名需 1-32 个字符"}, status_code=400)
        try:
            from style_core.profiles import find_profile

            if find_profile(self.plugin._styles_dir, name) is None:
                return json_response({"ok": False, "error": f"风格 {name!r} 不存在"}, status_code=404)
            self.plugin._set_cfg("active_style", name)
            await self.plugin.config.save_config_async()
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"切换失败: {e}"}, status_code=500)
        return json_response({"ok": True, "name": name})

    async def build_style(self) -> Any:
        """从有效语料提炼风格（LLM 调用，受 _building 单飞锁保护）。"""
        from astrbot.api.web import json_response, request

        try:
            payload = await request.json() or {}
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "请求体不是有效 JSON"}, status_code=400)
        name = str(payload.get("name") or "").strip()
        # 与档案校验（1-32 字）对齐——超限名会导致写盘成功但读取校验永远失败
        if not (1 <= len(name) <= 32):
            return json_response({"ok": False, "error": "风格名需 1-32 个字符"}, status_code=400)
        try:
            if self.plugin._building:
                return json_response({"ok": False, "error": "已有提炼任务进行中，请稍候"}, status_code=409)
            await self.plugin._build_profile(name, 50, reply_to=None)
            # _build_profile 的失败路径（语料不足/LLM 失败等）不抛异常，
            # 必须校验产物确实生成，避免"假成功"
            from style_core.profiles import find_profile

            if find_profile(self.plugin._styles_dir, name) is None:
                return json_response(
                    {"ok": False, "error": f"提炼未产出档案（常见原因：有效语料不足 4 句，或 LLM 调用失败），「{name}」未生成"},
                    status_code=500,
                )
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"提炼失败: {e}"}, status_code=500)
        return json_response({"ok": True, "name": name})

    async def correct_style(self) -> Any:
        """记录纠错（纯规则解析追加"TA 绝不会这样说"，无需 LLM）。"""
        from astrbot.api.web import json_response, request

        try:
            payload = await request.json() or {}
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "请求体不是有效 JSON"}, status_code=400)
        name = str(payload.get("name") or "").strip()
        body = str(payload.get("body") or "").strip()
        if not name or not body:
            return json_response({"ok": False, "error": "缺少风格名或纠错内容"}, status_code=400)
        try:
            from style_core.profiles import add_correction, find_profile, save_profile_file

            profile = find_profile(self.plugin._styles_dir, name)
            if profile is None:
                return json_response({"ok": False, "error": f"风格 {name!r} 不存在"}, status_code=404)
            # 解析 "场景：错误 → 正确"
            if "→" not in body and "->" not in body:
                return json_response({"ok": False, "error": "格式应为：场景：错误说法 → 正确说法"}, status_code=400)
            arrow = "→" if "→" in body else "->"
            scene_part, _, fix_part = body.partition(arrow)
            scene, _, wrong = scene_part.partition("：")
            # 半角冒号回退：仅当全角分隔未取到 wrong 时尝试（此前条件写反恒不生效）
            if not wrong and ":" in scene_part:
                scene, _, wrong = scene_part.partition(":")
            wrong = wrong.strip()
            correct = fix_part.strip()
            if not scene.strip() or not wrong or not correct:
                return json_response({"ok": False, "error": "场景/错误说法/正确说法不能为空"}, status_code=400)
            new_profile = add_correction(profile, scene.strip(), wrong, correct)
            save_profile_file(self.plugin._styles_dir, new_profile)
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"纠错失败: {e}"}, status_code=500)
        return json_response({"ok": True})

    async def import_colleague(self) -> Any:
        """导入 colleague 人格产物为风格档案（LLM 转换一次）。"""
        from astrbot.api.web import json_response, request

        try:
            payload = await request.json() or {}
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "请求体不是有效 JSON"}, status_code=400)
        name = str(payload.get("name") or "").strip()
        body = str(payload.get("body") or "").strip()
        if not name or not body:
            return json_response({"ok": False, "error": "缺少风格名或 persona 内容"}, status_code=400)
        if not (1 <= len(name) <= 32):
            return json_response({"ok": False, "error": "风格名需 1-32 个字符"}, status_code=400)
        try:
            if self.plugin._building:
                return json_response({"ok": False, "error": "已有提炼任务进行中，请稍候"}, status_code=409)
            # v2.9.4 审查修复：_load_colleague_input 是 async 且返回 (persona_text, meta_text)
            # （此前缺 await + 解包顺序反 + 对已解析 dict 二次 parse_profile_json，三重 bug 必 500）
            from style_core.colleague_import import build_colleague_import_prompt, parse_colleague_meta
            from style_core.profiles import normalize_profile, save_profile_file

            persona_text, meta_text = await self.plugin._load_colleague_input(body)
            if not persona_text and not meta_text:
                return json_response(
                    {"ok": False, "error": "未能读取到有效输入（需 persona.md/meta.json 文本或路径）"},
                    status_code=400,
                )
            prompt = build_colleague_import_prompt(parse_colleague_meta(meta_text), persona_text)
            profile = await self.plugin._call_llm_for_profile(prompt, reply_to=None)
            if not profile:
                return json_response({"ok": False, "error": "LLM 转换无结果"}, status_code=500)
            profile = normalize_profile(profile)
            profile["name"] = name
            save_profile_file(self.plugin._styles_dir, profile)
            self.plugin._bump_stats("style_built")
            self.plugin._set_cfg("active_style", name)
            await self.plugin.config.save_config_async()
            self.plugin._inject_schema_options()
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"导入失败: {e}"}, status_code=500)
        return json_response({"ok": True, "name": name})

    async def generate_style(self) -> Any:
        """统一「生成风格档案」入口（v2.9）：数据来源二选一。

        - source=corpus：从有效语料池采样 + LLM 提炼（原「提炼新风格」）
        - source=colleague：解析 colleague 人格文本 + LLM 转换（原「导入 colleague 人格」）

        两分支共用同一 LLM 调用链（_call_llm_for_profile + 保存/启用/统计/schema 刷新）。
        """
        from astrbot.api.web import json_response, request

        try:
            payload = await request.json() or {}
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "请求体不是有效 JSON"}, status_code=400)
        name = str(payload.get("name") or "").strip()
        source = str(payload.get("source") or "corpus").strip()
        body = str(payload.get("body") or "").strip()
        if not name:
            return json_response({"ok": False, "error": "缺少风格名"}, status_code=400)
        if source not in ("corpus", "colleague"):
            return json_response({"ok": False, "error": f"未知数据来源: {source}"}, status_code=400)
        try:
            if self.plugin._building:
                return json_response({"ok": False, "error": "已有生成任务进行中，请稍候"}, status_code=409)

            from style_core.profiles import normalize_profile, save_profile_file

            if source == "corpus":
                # 语料池提炼：采样有效语料 → build_extract_prompt → LLM
                from style_core.corpus import read_pool, sample_merged
                from style_core.extract_prompt import build_extract_prompt

                base = read_pool(os.path.join(self.plugin._corpora_dir, "base.jsonl"))
                user = read_pool(self.plugin._user_corpus_path)
                sampled = sample_merged(base, user, 100)
                sentences = [r.get("content", "") for r in sampled if r.get("content", "").strip()]
                if len(sentences) < 4:
                    return json_response(
                        {"ok": False, "error": "有效语料太少了（不足 4 句），请先在「语料」页导入一些对话。"},
                        status_code=400,
                    )
                prompt = build_extract_prompt(sentences)
            else:
                # colleague 人格导入：解析输入 → build_colleague_import_prompt → LLM
                if not body:
                    return json_response(
                        {"ok": False, "error": "colleague 来源需要粘贴 persona.md/meta.json 文本或填写路径"},
                        status_code=400,
                    )
                from style_core.colleague_import import build_colleague_import_prompt, parse_colleague_meta

                # v2.9.4 审查修复：await + 正确解包顺序 (persona_text, meta_text)
                persona_text, meta_text = await self.plugin._load_colleague_input(body)
                if not persona_text and not meta_text:
                    return json_response(
                        {"ok": False, "error": "未能读取到有效输入（需 persona.md/meta.json 文本或路径）"},
                        status_code=400,
                    )
                prompt = build_colleague_import_prompt(parse_colleague_meta(meta_text), persona_text)

            result = await self.plugin._call_llm_for_profile(prompt, reply_to=None)
            if not result:
                return json_response({"ok": False, "error": "LLM 生成无结果"}, status_code=500)
            # _call_llm_for_profile 返回的已是解析+校验过的 dict（两个分支同型）
            profile = result
            profile = normalize_profile(profile)
            profile["name"] = name
            save_profile_file(self.plugin._styles_dir, profile)
            self.plugin._bump_stats("style_built")
            self.plugin._set_cfg("active_style", name)
            await self.plugin.config.save_config_async()
            self.plugin._inject_schema_options()
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"生成失败: {e}"}, status_code=500)
        return json_response({"ok": True, "name": name, "source": source})

    # ------------------------------------------------------------------
    # 语料
    # ------------------------------------------------------------------
    async def get_corpus(self) -> Any:
        from astrbot.api.web import json_response

        try:
            from style_core.corpus import pool_stats, read_pool

            user = pool_stats(self.plugin._user_corpus_path)
            # _corpora_dir 是 str（os.path.join 结果），不能用 / 拼接
            builtin = pool_stats(
                str(os.path.join(self.plugin._corpora_dir, "base.jsonl"))
            )
            effective = self.plugin._effective_corpus_rows()
            # 行数÷2 才是问答对数（user/assistant 各一行），与 pool_stats 口径一致
            eff_pairs = sum(1 for r in effective if r.get("content", "").strip()) // 2
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"语料读取失败: {e}"}, status_code=500)
        return json_response(
            {
                "ok": True,
                "user": user,
                "builtin": builtin,
                "effective": {"pairs": eff_pairs, "rows": len(effective)},
                "corpus_path": str(self.plugin._user_corpus_path),
            }
        )

    async def import_corpus(self) -> Any:
        from astrbot.api.web import json_response, request

        try:
            payload = await request.json() or {}
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "请求体不是有效 JSON"}, status_code=400)
        text = str(payload.get("text") or "").strip()
        if not text:
            return json_response({"ok": False, "error": "没有可导入的语料"}, status_code=400)
        try:
            from style_core.corpus import append_pairs_to_pool, parse_corpus_text

            pairs = parse_corpus_text(text, filename="page-import")
            if not pairs:
                return json_response({"ok": False, "error": "未能从文本解析出任何语料"}, status_code=400)
            inserted = append_pairs_to_pool(self.plugin._user_corpus_path, pairs)
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"导入失败: {e}"}, status_code=500)
        return json_response({"ok": True, "inserted": inserted})

    async def upload_corpus(self) -> Any:
        """上传语料文件导入（v2.9.4）。桥固定字段名 file；支持 txt/json/jsonl/csv。

        文件字节按 UTF-8 解码后走 parse_corpus_text（与粘贴文本同一解析链），
        大小上限 10MB（桥上传通道 60s 超时内绰绰有余）。
        """
        from astrbot.api.web import json_response, request

        try:
            files = await request.files()
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "读取上传内容失败"}, status_code=400)
        upload_file = None
        try:
            upload_file = files.get("file")
        except Exception:  # noqa: BLE001
            upload_file = None
        if upload_file is None:
            # 兜底：字段名不符时取第一个文件
            try:
                for value in files.values():
                    upload_file = value
                    break
            except Exception:  # noqa: BLE001
                pass
        if upload_file is None:
            return json_response(
                {"ok": False, "error": "没有接收到文件（上传字段名须为 file）"}, status_code=400
            )
        filename = str(getattr(upload_file, "filename", "") or "")
        suffix_ok = filename.lower().endswith((".txt", ".json", ".jsonl", ".csv"))
        if not suffix_ok:
            return json_response(
                {"ok": False, "error": "仅支持 txt / json / jsonl / csv 语料文件"}, status_code=400
            )
        try:
            data = await upload_file.read()
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"读取文件失败: {e}"}, status_code=400)
        if len(data) > 10 * 1024 * 1024:
            return json_response({"ok": False, "error": "文件超过 10MB 上限"}, status_code=413)
        if not data.strip():
            return json_response({"ok": False, "error": "文件内容为空"}, status_code=400)
        try:
            from style_core.corpus import append_pairs_to_pool, parse_corpus_text

            text = data.decode("utf-8", errors="replace")
            pairs = parse_corpus_text(text, filename=filename or "upload.txt")
            if not pairs:
                return json_response({"ok": False, "error": "未能从文件解析出任何语料"}, status_code=400)
            inserted = append_pairs_to_pool(self.plugin._user_corpus_path, pairs)
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"导入失败: {e}"}, status_code=500)
        return json_response({"ok": True, "inserted": inserted, "filename": filename})

    # ------------------------------------------------------------------
    # 主动聊天状态
    # ------------------------------------------------------------------
    async def get_proactive(self) -> Any:
        from astrbot.api.web import json_response

        plugin = self.plugin
        now = __import__("time").time()
        quiet = str(plugin._p("proactive_quiet_hours") or "")
        rows = []
        try:
            triggers = getattr(plugin, "_next_trigger_ts", {}) or {}
            unanswered = getattr(plugin, "_proactive_unanswered", {}) or {}
            last_user_ts = getattr(plugin, "_last_user_ts", {}) or {}
            for umo, ts in sorted(triggers.items()):
                next_trigger = ts
                status = "静默中" if now < next_trigger else "已到期"
                # 是否在勿扰时段被压制
                try:
                    from humanizer_core.proactive import in_quiet

                    in_quiet_now = in_quiet(__import__("datetime").datetime.now(), quiet)
                except Exception:  # noqa: BLE001
                    in_quiet_now = False
                if in_quiet_now:
                    status = "勿扰中"
                last_ts = last_user_ts.get(umo, 0)
                silence_hours = max(round((now - last_ts) / 3600), 0) if last_ts else 0
                rows.append(
                    {
                        "umo": umo,
                        "status": status,
                        "next_trigger": (
                            __import__("datetime").datetime.fromtimestamp(next_trigger).strftime("%m-%d %H:%M")
                            if next_trigger else "-"
                        ),
                        "unanswered": int(unanswered.get(umo, 0)),
                        "silence_hours": silence_hours,
                    }
                )
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"状态读取失败: {e}"}, status_code=500)
        return json_response(
            {
                "ok": True,
                "enabled": bool(plugin._p("enable_proactive", False)),
                "silence_after_minutes": plugin._p_int("silence_after_minutes", 45),
                "silence_fluctuation_minutes": plugin._p_int("silence_fluctuation_minutes", 15),
                "quiet_hours": quiet,
                "quiet_grace_minutes": plugin._p_int("proactive_quiet_grace_minutes", 5),
                "pout_on_unanswered": bool(plugin._p("proactive_pout_on_unanswered", False)),
                "sessions": rows,
            }
        )

    # ------------------------------------------------------------------
    # 模型
    # ------------------------------------------------------------------
    async def list_models(self) -> Any:
        from astrbot.api.web import json_response

        try:
            from humanizer_core.llm_target import collect_models

            rows = await collect_models(self.plugin.context, self.plugin._model_cache)
            current = str(self.plugin._h("rewrite_model") or "")
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"模型列表读取失败: {e}"}, status_code=500)
        return json_response(
            {
                "ok": True,
                "models": [{"provider": pid, "type": ptype, "models": models} for pid, ptype, models in rows],
                "current": current,
            }
        )

    async def set_rewrite_model(self) -> Any:
        from astrbot.api.web import json_response, request

        try:
            payload = await request.json() or {}
        except Exception:  # noqa: BLE001
            return json_response({"ok": False, "error": "请求体不是有效 JSON"}, status_code=400)
        model = str(payload.get("model") or "").strip()
        try:
            self.plugin._set_h("rewrite_model", model)
            await self.plugin.config.save_config_async()
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"设置失败: {e}"}, status_code=500)
        return json_response({"ok": True, "model": model})

    # ------------------------------------------------------------------
    # 会话历史（记录回看）
    # ------------------------------------------------------------------
    async def list_sessions(self) -> Any:
        from astrbot.api.web import json_response

        try:
            sessions = await self._enumerate_sessions()
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"会话枚举失败: {e}"}, status_code=500)
        return json_response({"ok": True, "sessions": sessions})

    async def get_session_history(self) -> Any:
        from astrbot.api.web import json_response, request

        try:
            umo = str(request.query.get("umo", "") or "")
        except Exception:  # noqa: BLE001
            umo = ""
        if not umo:
            return json_response({"ok": False, "error": "缺少 umo 参数"}, status_code=400)
        try:
            messages = await self._read_session_history(umo)
        except Exception as e:  # noqa: BLE001
            return json_response({"ok": False, "error": f"会话读取失败: {e}"}, status_code=500)
        return json_response({"ok": True, "umo": umo, "messages": messages})

    async def _enumerate_sessions(self) -> list[dict[str, Any]]:
        """列出有会话历史的会话（v2.9.4 修复：真实调用框架异步 API）。

        数据源两路合并：
        - conversation_manager.get_conversations()（真实存在的全量异步接口）
        - 主动聊天跟踪过的会话（_next_trigger_ts）
        """
        sessions: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _push(umo: str) -> None:
            if umo and umo not in seen:
                seen.add(umo)
                sessions.append({"umo": umo, "label": umo, "has_history": True})

        # 框架全量会话列表（async，必须 await）
        try:
            mgr = self.plugin.context.conversation_manager
            if mgr is not None and hasattr(mgr, "get_conversations"):
                rows = await mgr.get_conversations()
                for row in rows or []:
                    _push(str(getattr(row, "unified_msg_origin", "") or ""))
        except Exception as e:  # noqa: BLE001
            _log_warn(f"枚举框架会话失败: {e}")
        # 主动聊天跟踪的会话补充
        for umo in list(getattr(self.plugin, "_next_trigger_ts", {}) or {}):
            _push(str(umo))
        return sorted(sessions, key=lambda s: s["umo"])

    async def _read_session_history(self, umo: str) -> list[dict[str, Any]]:
        """读取单会话历史为消息列表（v2.9.4 修复：get_curr_conversation_id /
        get_conversation 都是 async，必须 await——此前漏写导致永远拿不到历史）。

        返回 [{role, text, thinking(可选), proactive(bool)}]；
        思考过程从消息的 think parts 提取（AstrBot 框架已持久化）。
        失败抛异常由 handler 转 error 响应（不再静默吞掉）。
        """
        mgr = self.plugin.context.conversation_manager
        cid = await mgr.get_curr_conversation_id(umo)
        if not cid:
            return []
        conv = await mgr.get_conversation(umo, cid)
        if conv is None or not getattr(conv, "history", None):
            return []
        return _parse_conversation_history(conv.history)

    async def get_stats(self) -> Any:
        """统计计数器（v2.9.4 注意：必须保持在类体内——曾因编辑错位被吞进
        模块级辅助函数体内，导致整个路由注册批失败、页面全 404）。"""
        from astrbot.api.web import json_response

        return json_response({"ok": True, "stats": dict(getattr(self.plugin, "_stats", {}))})


def _log_warn(msg: str) -> None:
    try:
        from astrbot.api import logger

        logger.warning(f"[Humanizer] {msg}")
    except Exception:  # noqa: BLE001
        pass


def _log_error(msg: str) -> None:
    try:
        from astrbot.api import logger

        logger.error(f"[Humanizer] {msg}（请在 WebUI 重载本插件或重启 AstrBot 恢复页面功能）")
    except Exception:  # noqa: BLE001
        pass


def _log_info(msg: str) -> None:
    try:
        from astrbot.api import logger

        logger.info(f"[Humanizer] {msg}")
    except Exception:  # noqa: BLE001
        pass


def _load_config_schema() -> dict[str, Any]:
    """读取插件 _conf_schema.json 的分组/键元信息（description/hint/type）。

    v2.9：供前端渲染中文表单 label 与提示。读取失败返回空 dict（前端回落键名）。
    """
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_conf_schema.json")
        import json

        with open(path, encoding="utf-8") as f:
            schema = json.load(f)
        meta: dict[str, Any] = {}
        for group, ginfo in schema.items():
            if not isinstance(ginfo, dict):
                continue
            items = ginfo.get("items") if isinstance(ginfo.get("items"), dict) else {}
            meta[group] = {
                "description": ginfo.get("description", ""),
                "hint": ginfo.get("hint", ""),
                "items": {
                    k: {
                        "description": v.get("description", ""),
                        "hint": v.get("hint", ""),
                        "type": v.get("type", ""),
                    }
                    for k, v in items.items()
                    if isinstance(v, dict)
                },
            }
        return meta
    except Exception:  # noqa: BLE001
        return {}


def _list_profiles(plugin) -> list[dict[str, Any]]:
    """复用 main.py 的风格档案读取（避免重复实现）。"""
    from style_core.profiles import list_profiles

    try:
        return list_profiles(plugin._styles_dir)
    except Exception:  # noqa: BLE001
        return []


def _parse_conversation_history(history_raw) -> list[dict[str, Any]]:
    """解析会话历史（JSON 字符串或 list）为消息列表。

    兼容 AstrBot 的两种存储格式：
    - 旧版：{"role": "user"/"assistant", "content": "文本"}
    - 新版（ThinkPart）：content 为 [{type, text|think}, ...]
    主动消息（本插件写入的 [主动消息] 前缀）标记 proactive=True。
    """
    import json

    if isinstance(history_raw, str):
        try:
            history = json.loads(history_raw)
        except (ValueError, TypeError):
            return []
    else:
        history = history_raw
    if not isinstance(history, list):
        return []
    messages: list[dict[str, Any]] = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = msg.get("content")
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = str(part.get("type") or "")
                if ptype == "think":
                    thinking_parts.append(str(part.get("think") or ""))
                else:
                    txt = part.get("text")
                    if txt is not None:
                        text_parts.append(str(txt))
        elif isinstance(content, dict):
            # 部分版本 content 是 {"text": ...} / {"think": ...}
            if content.get("think"):
                thinking_parts.append(str(content.get("think")))
            if content.get("text") is not None:
                text_parts.append(str(content.get("text")))
        text = "".join(text_parts).strip()
        if not text and not thinking_parts:
            continue
        item: dict[str, Any] = {"role": role}
        if text:
            item["text"] = text
        if thinking_parts:
            item["thinking"] = "\n".join(p for p in thinking_parts if p).strip()
        if text.startswith("[主动消息]"):
            item["proactive"] = True
        messages.append(item)
    return messages


__all__ = ["register_web_routes", "HumanizerWebAPI"]
