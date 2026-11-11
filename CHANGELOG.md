# v4.2.0（2026-11-11 · 公开合并版）

本版把 4.1.9 之后的所有内部迭代合并为一个公开版本，不再逐次发版。

## 主要变化
- 控制台：8 页（总览/配置/语料与风格/主动聊天/记录回看/真人感规则/成长/统计），
  配置 8 组 138 键、15 条命令、23 个 Web 路由。
- 成长观察页：默认关闭，只记录消息元数据，不保存正文，不按天数自动晋级。
- 语风学习：新增 `/style_learn [preview|apply N|status]`，只读私聊记录、
  清洗后增量写入用户语料池；不新增配置键、不调用 LLM。
- 风格系统：风格指纹、实际发送审计（`--from-log`）、自然追问提示词。
- 发送行为：移除机械式句尾补词、风格短气泡与全部分段发送；长回复整条发送，
  语气词/省略号由提示词与模型自然生成。
- 隐私与发布：`pre_release_scan.py`、`release.py` 发布门禁、CHANGELOG 归档。

## 验证
- 全量 1580 passed / 1 skipped / 177 subtests；live 同版本通过。

# v4.1.9（2026-10-22 · 语义一致性审查修复）

- **档位（H1）**：`_time_flag` / `_emo_flag` 在 custom（默认档）下回读已保存的细分开关——
  此前直接用调用点默认值，导致 8 个布尔细分键（`rhythm_enable` / `continuity_inject` /
  `include_calendar` / `include_first_seen` / `include_last_chat` /
  `emotion_heat_drift_enable` / `emotion_reunion_inject` / `emotion_cold_war`）的用户设置全部失效。
- **检索索引（H2）**：`create_kb=false` 时 `/style_index` 仍可手动重建索引（该开关只约束自动同步）；
  失败提示补齐真实原因，不再把「关闭自动建库」归因成「语料为空 / 未配置 embedding」。
- **QC 口径（M1/M2）**：配置提示与事件流文案统一为「仅记录、不改写、不额外调用模型」；
  `humanize.enabled` 提示明确 QC 检测独立运行（与实现一致）。
- **注入开关（M3/M5）**：`style.enabled` 与 `enable_gap` 提示改为与实现一致（只关闭对应注入，
  其余由各自开关控制；生活状态由 `enable_life` 独立控制）。
- **风格空值（M4）**：`active_style` 提示明确「留空自动使用第一个可用档案并写回」，不再承诺「空 = 不注入」。
- **配置保存（M8）**：控制台保存失败时回滚内存修改，不再出现「提示失败但本进程内已生效」。
- **控制台失败态（M6）**：配置/状态接口返回 `degraded` 标记；总览/配置/统计/主动/记录页显示错误条，
  不再把后端故障渲染成「关闭 / 空 / 0 / 无记录」。
- **主动状态页（M7）**：补齐会话白名单、连续未回复上限、自适应间隔字段，并按会话给出暂停原因。
- **主动消息历史（L2）**：回看只认插件写入的完整合成句，用户自发 `[主动消息]` 前缀文本不再误标。
- **主动消息去痕（L4）**：Agent Pipeline 与轻量回退两条路径统一走同一入口，受 `humanize.enabled`
  与 `min_length` 约束（此前 pipeline 不去痕、轻量路径无条件去痕且忽略两个配置）。
- **统计（L1）**：文档「10 项」更正为 9 项；`qc_hits` 说明为「命中至少一条规则的消息数」。
- **总览（L3）**：情绪卡更名为「最近情绪」并显示时间，不再把存储态当作实时「当前情绪」。

# v4.1.8（2026-10-21 · 总览首卡文案纠偏）

- **误导修复**：总览第一张状态卡原标签「插件总开关」，实际读取的是 `humanize.enabled`
  （润色去痕开关，schema 明确写明「不控制时间/情绪/风格/主动」，且 v4.1.0 起已不是插件总开关）。
  用户可能误以为关掉它就禁用整个插件，因此改名为「润色去痕」，并加副文案
  「本地规则清理；不影响风格注入 / 感知 / 主动聊天」。
- **深链**：该卡点击跳转由 `/config` 改为 `/config?group=humanize`，配置页支持 `?group=` 参数
  直接打开对应分组（此前会落在第一个分组）。
- 其余状态卡（主动聊天/生活状态/风格注入）标签与配置分组一致，保持不动。

# v4.1.7（2026-10-21 · 预发布检查修复）

- **UI 修复**：状态卡补 `box-sizing: border-box`——此前卡片实际高度比网格行高多 46px，
  总览两行卡片会重叠约 30px（深色底上不易察觉）；修复后卡片与行高一致、行间距均匀。
- **统计页**：9 张卡从 4 列（末行只剩 1 张孤卡）改为 **3×3 均衡网格**；底部说明条增加间距。
- **包内容清理**：随包分发的 `webui/README.md` 去掉本机绝对路径与过期产物名（顺带更新
  图标数量与版本说明）；`package_plugin.py` 文档中的本机路径改为通用示例。
- 验证：全量 1293 passed / 3 skipped；Playwright 7 页 0 JS 错误；rebuilt 产物
  `index-B9yGshej.js` / `index-BV_fj3NS.css`；打包 77 文件。

# v4.1.6（2026-10-21 · 修复插件目录内的框架配置副本泄漏）

- **问题**：AstrBot 的 `get_astrbot_root()` 未设置 `ASTRBOT_ROOT` 时取「当前工作目录」；
  从插件根目录运行 pytest / 导入框架，会把 `data/cmd_config.json`（含 dashboard 口令
  哈希）与 `data/t2i_templates/` 生成到插件目录，存在随目录分享/打包外泄的风险
  （打包脚本本身已排除 `data/`，但直接复制目录仍会带走）。
- **修复**：新增 `tests/conftest.py`，在导入 astrbot 前从 `PYTHONPATH` 探测并设置
  `ASTRBOT_ROOT`，测试不再在插件目录生成 `data/`；新增
  `tests/test_plugin_local_data_guard.py` 守卫（插件目录出现 `data/cmd_config.json` 即失败，
  并校验 `.gitignore` 与打包排除均含 `data/`）。
- **文案**：启动告警补充处理指引——删除/移走该 `data/` 目录；开发测试时设置
  `ASTRBOT_ROOT=<AstrBot 根目录>`。
- 已清理本机工作副本与 live 插件目录内的泄漏副本（移入隔离目录，未删除）。

# v4.1.5（2026-10-21 · 配置页排版重做）

- **设置卡网格**：配置页从「顶部标签 + 表单行」改为**两列设置卡**——每一项是自包含卡片
  （标签 + 说明问号 + 键名水印 + 控件），控件类型不同（开关/数字/下拉/文本）也保持整齐对齐；
  长文本项（textarea）独占整行，窄屏自动降为单列。
- **分组信息**：每个分组标题行显示说明与「N 项」徽标，档位键仍置顶。
- **保存条**：吸底操作条改为「有 N 项未保存修改 / 配置已是最新」+ 放弃修改 / 保存配置，
  保存按钮在无改动时禁用。
- 控制台其余页面与后端接口不变（7 页、130 键、19 路由）。

# v4.1.4（2026-10-21 · 控制台 UI 优化）

- **导航**：顶部菜单加页面图标（总览/配置/语料与风格/主动聊天/记录回看/真人感规则/统计），
  选中态图标转品牌粉。
- **配置页**：单列长表单改为**两列响应式网格**（顶部标签，textarea 独占整行），页面高度约减半；
  新增「有未保存修改」提示（与载入快照比较）。
- **真人感规则页**：规则卡片改**两列网格**；新增 全部 / 注入型 / 质检型 / 已停用 筛选，
  与搜索框叠加生效。
- **总览**：状态卡可点击直达对应页面（配置/主动聊天/语料/记录回看），hover 显示跳转箭头。
- **细节**：暗色细滚动条与文本选中色；图标集随新增箭头图标重新生成。

# v4.1.3（2026-10-21 · 档位可见性 + 控制台细节）

- **状态出口补档位**：`web_status()` 新增 `awareness_mode` / `emotion_mode` /
  `proactive_preset` 三个只读字段（默认 `custom`），控制台与二次开发可直接读取当前档位。
- **总览档位 chips**：总览首屏新增三枚 chip，显示「时间 / 情绪 / 主动」当前档位
  （`custom` 显示为「按细分开关」，simple/standard/full/reserved/clingy 显示中文语义）。
- **配置页档位置顶**：三组档位键固定排在所属分组最前，不用滚到组尾找。
- **冒烟脚本增强**：`tools/verify_console.py` 新增断言——总览档位 chip、三组配置页档位项；
  7 页仍 0 错误。
- **测试**：新增 `tests/test_fix_v413_status.py`（状态出口/总览/配置页置顶接线）。

# v4.1.2（2026-10-21 · 对外文案梳理 + 控制台体验优化）

> 无发版计划外的行为改动；本版聚焦「对外可见文案一致性」与控制台可用性。

## 对外文案纪律

- 按最新对外文案要求梳理用户可见文件（metadata help、README、安装说明、CHANGELOG、
  `_conf_schema.json` 描述/提示、控制台页面）：不再出现其它插件/项目名称与推荐替换其它方案
  的表述，历史条目统一改为中性描述；内部代码注释与测试保留出处。
- 新增 `tests/test_public_copy.py`：扫描用户可见文件中的外部插件名与替代表述，
  并校验配置面板分组文案与当前 6 组一致。
- 修正配置面板残留：`proactive` 分组描述/提示不再宣传已移除的承诺簿；历法感知提示
  改为中性表述；README 主题描述与当前 Moonshot 式暗色主题一致（原写作「星穹甜心」为
  旧主题遗留）。

## 控制台体验

- **枚举配置渲染下拉**：schema 自带 `options` 的键（时间/情绪/主动三组档位）在配置页
  渲染为下拉框，并给 custom/simple/standard/full/reserved/clingy 附中文语义标签。
- **离线图标**：新增 `webui/scripts/gen-icons.mjs` 生成本地 lucide 图标集
  （`src/icons.generated.ts`，27 个），控制台不再请求 Iconify 在线 API——内网/离线
  环境图标不再空白，也消除了控制台的外部网络错误。
- **控制台运行时冒烟工具**：新增 `tools/verify_console.py`（Playwright + 本机 Edge，
  mock 桥接数据），逐页打开 7 个页面、收集 JS 错误并截图；当前 0 错误通过。

## 其他

- `package_plugin.py` 排除 `_verify/`（控制台截图目录在工作区级，不进产物）。
- 重建控制台产物并同步线上；配置 6 组 130 键、命令 14 条不变。

# v4.1.1（2026-10-20 · 承诺簿移除 + P1 优化 + Phase 8 收口 + 打包卫生）

> 承接 v4.1.0 功能裁剪：本版移除承诺簿（记忆职责归一），并落地 P1 优化项、
> Phase 8 收口与发布/打包基础设施。

## 承诺簿移除

- 删除 `humanizer_core/commitments.py`、配置键 8 个（`commitments_enable` /
  `commitments_track_groups` / `llm_confirm` / `inject_in_chat` / `remind_grace_days` /
  `commitments_extract_model` / `commitments_extract_timeout` / `commitments_debug`）、
  命令 `/commitment_list|done|drop`、`commitments.json` 读写与相关测试；
  `<time_context>` 的承诺到期行、stats `commitment_captured` 一并移除。
- 记忆/承诺职责统一交给记忆类插件（记忆类方案 等）；旧配置值忽略即可。

## P1 优化（评审清单 ⑤–⑫）

- **lang_mirror 短语质量**：新增 `prune_phrases()`——按「频次×长度」保留并剔除互相包含的
  n-gram 碎片（「比基/基尼/尼比基尼」这类「比基尼」滑窗碎片不再被注入为高频短语）；
  采集与渲染两处都过同一条去重叠规则。
- **QC 观测**：新增 stats `qc_checked`；QC 检查与润色开关解耦（关掉去痕也统计命中）。
- **输入状态平台闸门**：`aiocqhttp` / `qq_official` / `qq_official_webhook` 实测不传播
  input_status，直接跳过输入状态处理（不再空转）。
- **主动消息发送兜底**：pipeline 发送未确认时改走直发通道重发一次，成功照常记历史与
  `proactive_sent`，仍失败才告警放弃。
- **观测补全**：stats 新增 `typing_delay_applied` / `debounce_merged`（共 10 项）。
- **配置档位（合并同质开关）**：新增 `time/awareness_mode`（custom/simple/standard/full）、
  `emotion/emotion_mode`（同四档）、`proactive/proactive_preset`（custom/reserved/standard/clingy）。
  默认 `custom` 完全保持原细分开关行为，档位只在读取时覆盖、不改写用户配置；
  实现在 `humanizer_core/presets.py`（纯函数）。

## Phase 8 收口

- 按项目 2026-09-12 的 Phase 8 结论（main 已无「纯逻辑大块」，剩余体量是框架适配编排）
  完成收尾：全仓死方法扫描 0 项；配置读取统一经 `TypedConfig`（`_group/_group_num`
  委托门面）；本批移除改写/复读/承诺簿后 `main.py` 6192 → 约 5300 行，保留
  hook 注册 + 装配 + 框架适配编排；REFACTOR_PROGRESS.md 追加 Phase 8 收口记录。

## 发布与打包基础设施

- 新增 `package_plugin.py`：标准库 zipfile 打包市场 zip（顶层目录固定、`--dry-run` 预览、
  `--force` 覆盖、SHA256 输出），排除 `.git/`、`__pycache__/`、`tests/`、`tools/`、内部
  `REFACTOR_PROGRESS.md`、`SEED_MANIFEST.json`、`pages/humanizer-console.bak*` 等。
- 恢复 `.gitignore`（工作副本原先被删）并补充 bak/node_modules/dist 规则。
- 前端源码补齐为**可构建工程**：`webui/` 增加 `package.json` / `package-lock.json` /
  `vite.config.ts` / `tsconfig.json` / `index.html` / `src/env.d.ts`，按 v4.0.x 产物反推
  补齐 `src/composables/useBridge.ts`（AstrBotPluginPage 桥 + /api/plug 回落），新增
  `RulesView.vue` 第 7 页，更新 Config 分组标签、Stats 计数与 Overview 仪表盘；
  并用源码重建 `pages/humanizer-console`（产物 `index-D0H0Vkx4.js` / `index-BMXvfWun.css`）。
  新增 `tests/test_console_build_contract.py` 钉死 index→assets 引用、7 页标题与桥接协议。
- 清理包内杂物：`pages/humanizer-console.bak-*`（1.78 MB）移出插件目录（未删除）。

## 测试基线

- 全量 pytest：**1281 passed / 3 skipped / 35 subtests**（exit 0）；全部 py `py_compile` 通过；
  `main/web_api/humanizer_core/style_core` import 冒烟通过。
- 新增 `tests/test_fix_v411_p1.py`（档位纯函数、短语去重叠、P1 接线 12 例）；
  删除随承诺簿下线的 `test_commitments*`，同步调整 split/facade/provider-wiring 等契约测试。

# v4.1.0（2026-10-20 · 功能裁剪 + 发送链修复）

> 依据作者对功能清单的取舍：移除「没什么用」的 LLM 深度改写族与应声虫复读，保留插件分段发送
> （框架 segmented_reply 不满足需求，作为补充能力保留）；其余功能不动。测试基线见下方验收数字。

## 功能移除

- **LLM 深度改写**：删除 `humanize.enable_llm_rewrite` / `rewrite_model` / `rewrite_timeout` /
  `rewrite_total_timeout` / `rewrite_max_candidates` / `llm_rewrite_concurrency` 六键，
  以及 `_llm_rewrite` / `_rewrite_once` / `_rewrite_timeout_seconds` / `_style_rewrite_suffix` /
  `_rewrite_state_line` 与 `humanizer_core/prompt.py`、`humanizer_core/llm_budget.py`；
  `humanize.enabled` 保留为「润色去痕开关」，回复只走本地规则清理。
- **模型故障切换**：删除 `humanizer_core/llm_target.iter_failover_models`；`resolve_rewrite_target`
  保留（主动消息生成仍需要「跟随当前会话模型」的解析）。
- **改写模型命令**：删除 `/humanizer_models`、`/humanizer_model`（命令 19 → 17）；
  删除 Web 端点 `models/set-rewrite`（路由 20 → 19）及 `web_read_model` /
  `web_set_rewrite_model` / `web_rewrite_model` 三个 facade（控制台状态页改走新增 `web_status()`）。
- **思考内容移除**：删除 `humanize.remove_reasoning`（与宿主 `provider_settings.display_reasoning_text`
  重复且不省 token）；cron 主动消息的思考清除保留。
- **应声虫复读**：删除整个 `parrot` 配置分组（14 键）、`humanizer_core/parrot.py`、`parrot_state.json`
  读写、`_parrot_*` 钩子与相关测试。
- 连带：`humanize.max_chars`（仅改写用）删除；stats 移除 llm_rewrite/rewrite_switched/
  rewrite_exhausted/rewrite_rejected/qc_fixed 五个计数（12 → 7）；QC 质检型规则降级为
  「只检测计数 + 日志，不改写」。

## 发送链修复（此前 humanize 总闸会连坐）

- `humanize_response` 的「本轮为 LLM 人格聊天产出」标记（`_humanizer_llm_replied`）改到
  `humanize.enabled` 判断**之前**写入；此前关闭「润色去痕」会让 `_is_llm_reply()` 恒 False，
  普通回复的拟人打字延迟与分段连发静默失效（仅 cron 主动消息仍分段）。
- `/commitment_list`、`/commitment_done`、`/commitment_drop` 补
  `@filter.permission_type(ADMIN)`（其余 16 条管理命令早已有）。
- 墙钟行自动跟随宿主：`_framework_injects_datetime()` 读取
  `provider_settings.datetime_system_prompt`，宿主已注入 `Current datetime` 时跳过插件墙钟行，
  避免同一请求两份时间。

## 配置与测试

- `_conf_schema.json`：7 组 157 键 → **6 组 135 键**（humanize 12→4、parrot 组删除）。
- 测试：基线 1456 passed / 3 skipped → 本版 **1317 passed / 3 skipped / 35 subtests**（删除
  随功能下线的用例，绿）+ `py_compile` 全绿；另修复 3 个测试文件硬编码的本机临时目录
  导致的跨机器失败（改用系统临时目录）。

# v4.0.6（2026-09-29 · 修复批：改写模型解析 + v4.0.4 回归恢复 + 契约对账）

> 触发原因：①运行时告警「提供商 'xiaomi-token-plan' 不支持模型 'mimo-v2.6-flash'」
> ——框架 Xiaomi Token Plan 适配器的 get_models() 硬编码名单未跟上新模型，插件侧
> 误判回落；②全量审查发现 v4.0.4 重构时误删两处 v4.0.3 钉子（凭据副本护栏、
> 旧库残留提示）+ 一处幻觉引用；③7 个契约测试未随 v4.0.4 的路由恢复/服务化对账。

## 深度改写模型解析：信任 provider 实例自声明（修复 mimo-v2.6-flash 回落）

- `humanizer_core/llm_target.py` 新增 `_provider_declares_model()`：当配置为
  完整复合实例 id（`provider/模型`）且实例自身（`get_model()` 或
  `provider_config["model"]`）声明的模型与目标严格一致时直接放行，不再依赖
  适配器可能过期的 `get_models()` 枚举名单；
- 声明不一致/读取失败仍走原列表校验与回落，前缀匹配、裸模型名路径零改动；
- 框架侧已核验无二次闸门（`llm_generate` kwargs 透传，anthropic 线
  `model or get_model()` 直进请求），语义与 `_call_llm_for_profile` 形态 2 一致；
- 已知残留（有意不收口，上游名单更新后自愈）：schema 动态下拉与
  `/humanizer_models` 列表仍由 `get_models()` 驱动，新模型手填可用但列表选不到。

## v4.0.4 回归恢复（全量审查定性：3 处真回归）

- 恢复 `_warn_stray_runtime_config()` 启动护栏（v4.0.3 引入、v4.0.4 重构误删）：
  插件目录残留 `data/cmd_config.json`（含 dashboard 口令哈希）时启动告警；
- 补回 kb_service 新建知识库时的旧库残留提示
  （「旧的 human_style_* 知识库不会自动清理」，v4.0.4 重写 sync_job 时丢失）；
- 订正 `humanizer_core/commitments.py` docstring 的幻觉引用
  （`main._life_commitment_check` 从未实现，改为描述实际的窗口制注入+手动核销）。

## 性能修复补充（2026-10-13 · 本地未发布）

- 移除 `main.py` 装配 `KBPorts` 时与默认算法等价的自定义指纹回调，
  恢复 KBService 基于文件修改时间/大小的语料签名缓存；稳定语料不再每轮
  读取、合并和哈希，检索缓存键也能取得非空的语料签名。
- 保留 embedding provider 与索引结构版本对最终指纹的影响；语料文件提示
  改变或显式失效后重新计算，真正自定义指纹算法的服务接口不变。
- 深度改写先尝试首选模型，仅在传输失败且预算仍允许重试时枚举备用模型；
  首选成功、内容校验失败、仅允许一次尝试或预算耗尽时不做备用列表探测。
  保留故障切换排序、候选去重、内容拒绝回落、并发限制和取消清理；
  备用模型枚举也受剩余总预算约束，超时取消枚举并释放改写并发槽。
- 新增默认指纹缓存行为/装配契约测试与改写异步编排测试，覆盖缓存失效、
  备用列表异常、候选顺序、预算边界及信号量/递归标志释放。
- 主动聊天维护循环、现有兼容入口和发布资产均未修改；本批不提升版本号。

## 契约测试对账（7 项，随 v4.0.4 设计现状更新断言）

- 路由表 17→20：styles/build 与 models 两族为 v4.0.4 有意恢复的兼容入口；
- 唯一僵尸端点收敛为 styles/import-colleague（已并入 styles/generate
  source=colleague）；
- KBService 私有名断言反转：v4.0.4 服务化后别名即实现本体，改为锚定
  「同引用绑定 + 状态容器只在 __init__ 绑定」；
- web facade 断言随 models 端点恢复更新（web_set_rewrite_model 合法回归）。

# v4.0.5（2026-09-21 · 市场审核修复：日志记录器统一）

> 触发原因：插件市场审核驳回——humanizer_core 下 5 个模块使用 Python 内置
> `logging.getLogger` 而非 astrbot.api 的 logger，违反「日志记录器必须且只能
> `from astrbot.api import logger`」的规范。本版无任何行为变更，仅统一日志记录器；
> 测试基线 1437 passed / 35 subtests（与修复前完全一致，零回归）。

## 日志记录器统一（审核违规项全清）

- `humanizer_core/typing.py`、`state.py`、`state_store.py`、`debounce.py`、
  `llm_target.py` 全部由 `import logging` + `logging.getLogger(...)` 改为
  `from astrbot.api import logger`（astrbot.api 的 logger 为按调用模块路由的
  代理，底层仍是标准 Logger，`.warning/.exception` 等方法全部可用）；
- `llm_target.py` 原先 `logging.getLogger("astrbot")` 借名取全局日志记录器，
  同样违规，已改为官方导入，4 处调用点 `_logger.` → `logger.`；
- 全仓 `import logging` / `logging.` 引用清零（grep 复核通过）；
- 相应更正 5 个模块 docstring 中「零 astrbot 依赖」的过时表述——日志依赖
  astrbot.api（市场规范所迫），其余逻辑仍为纯函数；受此影响这 5 个模块的
  单测需在 astrbot 可导入的环境（宿主 venv）下运行，测试基线不受影响。

# v4.0.4（2026-09-21 · 发布前审查修复批：语料对齐 + 控制台补齐 + 发布适配）

> 触发原因：外审发现分发物 `corpora/base.jsonl` 与它自己的构建脚本
> `tools/build_base_corpus.py` 长期不一致，且控制台有一处承诺过的下拉实际不存在。
> 本版不引入新功能，全部为一致性与健壮性修复；测试基线 1369 passed / 60 skipped / 35 subtests。
>
> **版本号说明**：上一份构建（v4.0.2 + 31 行小修）已于 2026-09-19 以 **4.0.3** 部署/发布，
> 但归档目录的 metadata 未同步、仍写着 4.0.2。本次内容与之不同源，故推进到 **4.0.4**
> 以免版本撞车与市场判重缓存（同 v2.9.6 的做法）。

## 内置语料池：已评估，按决定不过滤

发布前审查发现 `corpora/base.jsonl` 与它自己的构建脚本
`tools/build_base_corpus.py` 长期不一致（分发文件有 22.3% 的行超过脚本
`is_noise` 的 60 字上限）。逐版比对定位到根因：

| 版本 | 问答对 | 中位长度 | 超 60 字占比 |
|------|--------|----------|--------------|
| v2.1.2 / v3.0.0 | 3000 | 10 字 | 0% |
| v3.10.0 / v4.0.0 | 6000 | 41 字 | 31.9% |
| v4.0.2 / 现行 | 10379 | 30 字 | 22.3% |

**v3.10.0 换了语料来源/切分方式**（分词短句 → 保留多轮原句），但构建脚本的
`is_noise` 长度窗（4~60）与 `--total` 默认值（3000）没跟着改。即：文件并不是脏，
是脚本描述的现实过期了；超长的多轮原句是有意保留的检索上下文。

曾按「长度窗 60→100 + 重滤语料」实现并通过测试（10379 → 9853 对），
**经确认后决定不回退该过滤、维持 20758 行原始语料**，相关改动已全部撤销：
`corpora/base.jsonl` 与 `tools/build_base_corpus.py` 均恢复 v4.0.2 原样，
防漂移测试一并移除。诊断结论保留在此，供将来重新决策时参考——若哪天想收紧，
长度窗取 100 是有数据依据的（81-100 字有 1944 行，101 字以上仅 154 行）。

## 控制台

- **「时间线生成模型」下拉修复**：`_collect_dynamic_options` 原产出
  `life/extract_model`——v3.9.0 分组重构后 `life` 组已并入 `time`（键名改为
  `life_extract_model`），该键成了死键，前端按 `time/life_extract_model` 查表
  永远查不到，控制台把此字段渲染成纯文本框，而安装说明承诺它是下拉。
  改为产出 5 个现行键：`humanize/rewrite_model`、`style/extract_model`、
  `time/life_extract_model`、`proactive/commitments_extract_model`、
  `parrot/judge_model`。
- **数组型配置可编辑**：控制台配置页原按 `typeof 值` 推断控件类型，
  `typeof []` 落 `skip`，导致 `typing/command_prefixes`（指令前缀列表）在控制台
  既看不到也改不了。改为优先读 schema 声明的 `type`：`list` → "每行一条"文本框
  （读时 `join('
')`、写时 `split + trim + 去空`，落盘仍是 `string[]`）。
  `file` 类型维持不渲染（语料上传走「语料与风格」页），已在安装说明注明。
  源码改动 `webui/src/views/ConfigView.vue` + `webui/src/components/StatCard.vue`，
  已重构建（工具链确定性复现验证通过：无改动重建 hash 与原包一致）。
- **硬编码端口移除**：`StatCard.vue` 跳转原写死 `http://127.0.0.1:6185/`，改端口 /
  走反代 / 用局域网 IP 访问面板时必然失效；改为 `${window.location.origin}/`。
- **冗余端点下线**：`POST /styles/import-colleague` 撤除——它与 `styles/generate`
  的 `source=colleague` 分支**逐行重复**，v2.9.4 的 await/解包三重修复被迫改两遍。
  新增契约测试钉死"全模块仅一处 `_load_colleague_input` 调用"。
  `styles/build` 与 `models/set-rewrite` 保留为兼容入口（前端零调用），
  ROUTE_SPECS 已注明，勿再复制实现。路由 20 → 19。

## 配置文案（_conf_schema.json）

- `typing.delay_max` / `typing.total_delay_cap` 原**描述完全相同**
  （"目标总延迟上限（秒）"）但语义不同，用户必混淆；改为
  「目标总延迟上限（软，秒）」/「目标总延迟硬上限（秒）」，hint 中明确
  "软上限决定想等多久、硬上限决定最多等多久"。
- `style.retrieval_timeout` hint 去除自我重复的两段解释与内部日期备注。
- `typing.dedupe_rewrite` hint 去除"（2026-09-06 实证）"内部备注。
- `emotion.emotion_soothe_boost` hint 去除"v4.1.0 起"引用（该版本未发布）。
- `parrot.prob_normal`：原标注"（预留）"易误判为死键，实际是可用功能
  （非搞怪消息的复读概率，默认 0 = 只学舌搞怪消息）——改文案说明清楚，**不删键**。
- `typing.command_prefixes` hint 补控制台编辑格式与"留空 = 关闭指令识别"的后果。
- `time.schedule` hint 补富语法（`HH:MM-HH:MM 安排 | 心情:… | 地点:…` 与自然时段名），
  此前只有 README 提到、配置面板发现不了。

## 文档同步

- README：控制台"6 个页面"→**7 个**（补「真人感规则」页）；配置页"五组"→七组；
  语义分区"六个"→**七个**（补「复读 · 应声虫学舌」行）；总览页补仪表盘字段；
  安装目录树由 v1.x 时代 4 模块更新为现行全量结构；「许可」节补
  `corpora/base.jsonl` 四个来源（LCCC / 豆瓣多轮 / dgk 影视字幕 / chatterbot-corpus）
  及许可证与过滤规则；新增「内置语料池」说明段（含防漂移测试提示）。
- 安装说明：分区数 6→7、组名对齐 schema（"时间流动与生活"→"感知 · 时间与节奏" 等）、
  补 parrot 组；下拉清单改为实际支持的 9 项并注明两个控件仅在原生配置表单可编辑。
- metadata.yaml help：补「情绪×对话热度耦合」与「应声虫复读」（此前完全缺席），
  版本号 4.0.2 → 4.0.3。

## 代码卫生

- 清理 9 个未使用 import：`main.py`(random / compute_next_delay)、
  `humanizer_core/commitments.py`(extract_json_object)、`kb_state.py`(Optional)、
  `parrot.py`(Any)、`retrieval_plan.py`(Optional)、`task_registry.py`(Optional)、
  `services/proactive_state.py`(bump_sulky)、`web_api.py`(read_pool)。
  `web_api.py` 的 `Context` 为 TYPE_CHECKING 类型标注，加 `# noqa: F401`。

## 发布适配（对照 AstrBot 插件市场标准核对）

对照本机 AstrBot 4.28.0 源码 `astrbot/core/star/updater.py::validate_plugin_metadata`
与官方《AstrBot 插件市场 JSON 规范 2026-06-27》逐条核对，硬性门槛全过：
metadata 4 个必填字段齐备且非空 / ZIP 1.73MB（上限 16MB）/ zip 顶层目录名 ==
`metadata.name` / `plugin_id` = `SIiOC/astrbot_plugin_wanna_be_human` 合法 /
`repo` 为合规 HTTPS GitHub URL / 包内无 `.git`、`__pycache__`、`node_modules`、
`.pytest_cache`、`tests`。另做两项适配：

- **`astrbot_version` 补上界**：`">=4.5.7"` → `">=4.5.7,<5"`。原先只有下界，
  AstrBot 5.x 发布后会静默装上一个未必兼容的版本。已用 `packaging.SpecifierSet`
  验证：4.5.7 / 4.24.2 / 4.28.0 / 4.99.99 通过，5.0.0 与 3.9.0 拒绝。
  官方文档范例即为 `>=4.16,<5`。
- **补声明 `support_platforms`**：列出全部 20 个合法适配器 key（取值对照
  `astrbot/core/star/filter/platform_adapter_type.py::ADAPTER_NAME_2_TYPE`；
  官方文档漏列 `webchat`，以代码为准）。本插件经 LLM 钩子与通用消息事件工作，
  不调用特定平台私有 API，故支持面覆盖全部适配器；平台相关能力（如「对方正在输入」
  感知）在所选平台不支持时自动静默降级，不影响主功能。
  该字段经核实为**纯信息字段**——只加载进 `StarMetadata` 并在 WebUI 展示，
  无任何安装/加载门槛，声明不会限制安装。
  （注：v1.1.1 曾移除 `support_platforms: all`，当时删得对——`all` 不是合法 key；
  本次是按现行规范补合法 key 列表，不是把 `all` 加回来。）

## 兼容性

- 配置键零增删、零默认值变更（157 键 / 7 组不变）；迁移逻辑未动。
- `corpora/base.jsonl` 由 10379 对降至 9853 对（-5.07%），检索覆盖面基本不变。
- 控制台资源文件名变更（Vite content hash），`pages/humanizer-console/index.html` 已同步。
- 撤除 1 个前端零调用的冗余端点；AstrBot 原生配置表单行为不变。

# v4.0.2（2026-09-17 · 文档订正 + 回归钉子）

- `_read_capped` 描述订正（CHANGELOG v4.0.1 条目 + main.py docstring）：旧实现按字符 `limit//4` 读，中文场景实际只用约 3/4 字节预算——是**少读**、从未超限；初版描述"可超上限约 1/4"因果说反。
- `migrate_group_merges` 补 4 条「改名键不双写」回归测试（extract_model→commitments_extract_model、life_extract_model 变体、保名键混合、未知键照旧兜底）——v4.0.1 的修复此前只有手工验证、无测试钉子。

# v4.0.1（2026-09-17 · 外审修复批）

> 外部模型两轮逐行审查（记忆类方案与本插件）后的集中修复。无行为改版，全部向后兼容；测试基线 1390 passed / 3 skipped（宿主 venv）。

## 修复：主动消息生命周期（P1×2）

- **死会话永不回收**：`prune_stale` 原用 `triggers`（下次触发时间）判 24h 过期——但触发时间恒被重排到未来，主动开启时判式永远为假，triggers/unanswered/last_user_ts/followups 四表无限增长。改用**用户最后发言时间**（last_user_ts）判过期，并取两表并集防孤儿条目；机器人自己的主动发送不算"活动"。
- **连续未回复无硬上限**：常规主动此前只靠 `unanswered` 参与间隔放大（封顶 240 分钟）拉长节奏、从不停发。新增 **`proactive_max_unanswered`**（默认 6，0=关）：达到上限暂停该会话主动发送直至用户发言（note_user_message 清零即自动恢复）；暂停期间照常重排，调度状态完整、面板可见。

## 修复：防抖与发送管线

- **自愈守卫 TOCTOU**：结算事件置位与等待协程被唤醒之间有一个事件循环窗口，窗口内的新消息此前被误判为"无等待者的死会话"而整轮丢弃。会话登记 `waiter_task`（bind_waiter），守卫只在该任务确实已结束时才丢弃；等待者活着则走正常追加（由它合并结算）。
- **输入保护被打断**：`absorb_activity` 此前无条件重置防抖计时器——用户"正在输入"挂起的等待被表情/语音打断、按 debounce_time 提前结算。is_typing 期间只登记 item 不动计时器。
- **NameError 控制流**：`_pipeline_failed` 改为函数入口预绑定（同 v3.9.5 的 cron_event 手法）。
- **terminate 落盘顺序**：先停 `_time_flush_task`/`_life_task` 再终局落盘（防维护循环用较早快照覆盖终局状态）。

## 修复：缓存与承诺

- **llm_target 空列表永久缓存**：provider `get_models()` 失败此前照样写入空列表缓存——provider 故障切换的可用性探测"模型不存在"永久命中直到重启。失败不再写缓存（坏 provider 期间每次探测多一次网络请求，是可接受的代价）。
- **承诺 ID 碰撞**：原式 `毫秒时间戳+len(text)%97`，同批次共用同一 now_ts，两条同长度文本必同 ID（`mark_resolved` 误伤）。加 `uuid4().hex[:8]` 随机段。
- **parse_llm_array 字符串盲区**：括号配平扫描无字符串状态机，正文含 `]`（如"喜欢[收藏]之类"）时提前截断、整批解析失败丢弃。补 in_str/esc 状态机。

## 修复：时间与节奏边界

- `gap_context` NaN 防御（NaN 比较全假会一路落到「隔了一周多」）。
- `rhythm_heat` 负 gap（时钟回拨）不再判 hot，NaN 按 warm 兜底。
- `parse_time_slot` 跨午夜（`23:00-01:00`）返回当日段+次日凌晨段两段（原截断为当日段，凌晨误判空闲）。
- `settle_delay` NaN 显式兜底（行为不变，语义明确化——实测 NaN 落 max 比较恒假，原实现碰巧安全但脆）。

## 修复：杂项

- 检索缓存 `clear()` 引入代数版本号：in-flight 任务完成后不再把已失效数据回填缓存（不取消任务，等待者不受波及）。
- `_read_capped` 按字节截断（v4.0.2 订正描述：原按字符 `limit//4`，中文 3B/字实际只用了约 3/4 字节预算——偏保守的**少读**、从未超限；现按字节截断用满上限）。
- `_is_group_event` 回退路径改精确段匹配（`umo.split(":")[1]`）。
- `_parrot_pending` 类型标注对齐实际四元组 `(模式, 任务, 原话, 时间戳)`。
- kb_service `framework_loaded` 重复赋值去重。
- config_migrate 兜底搬运排除已按显式规则搬移的源键（防改名键新旧名并存）。

# v4.1.0（未发布 · 待与波 2 合流发布；热度耦合与应声虫复读实际已随 v4.0.0 部署上线，版本号归位待波 2 合流时一并处理）

## 新增：情绪惯性 × 对话热度耦合

- **问题**：此前情绪推进的正面来源只有安抚词池（16 个关键词命中才转 appy）、负面来源只有主动消息未回复计数——与节奏引擎算出的对话热度（hot/warm/cold）完全脱钩：热聊半小时情绪纹丝不动，话题慢慢冷掉也不会有"兴致淡了"的反应。
- **热度成为第四输入源（漂移叠加式）**：`decay_and_soothe` 推进顺序升级为 时间半衰期衰减 → 逐条衰减 → **热度漂移** → 安抚命中。hot 每条向 appy 漂移、cold 每条向 sulky 漂移；与逐条衰减 ×0.6 平衡后的稳态分别约 **0.50（轻快档）**与 **0.25（淡淡档）**——**对话热度是情绪的主导来源**。
- **权重再平衡（用户反馈"降关键词、升热聊"，同日二次调参）**：①安抚关键词从**一锤定音的固定 +0.4** 降格为**可配的加分项**（新键 `emotion_soothe_boost`，默认 0.2 ≈ 一条热聊消息的量级；**设 0 = 安抚词完全不参与**——不增量也不转方向，与 hot/cold 的"0=关方向"同契约；审查轮修复：初版把 0 误落回默认量，等于没有关词通道**且**清空词池还会回落内置池，两条"关"的路全堵死）——冷场节奏里零星"哈哈"不再能主导情绪，方向获胜保留：冷场中的好话仍直转 appy；②hot 漂移量 0.12→0.2（首条即注入，稳态 0.50）。cold 维持 0.10（两条起注入，负面建得比正面慢）；方向切换即时（单条消息翻转情绪方向）。
- **方向切换语义**：hot 从 sulky 转向 appy（对方回得快，气性就该消）；cold 反之。初见守卫钉在纯层：`prev_seen` 无记录时 cold 一律按 warm 处理——首条消息的"冷档"是初见不是冷场，不摆脸色。
- **热度同源**：heat 由节奏引擎 `rhythm_heat` 经 `_time_snapshot` 快照计算（`previous_seen ← _prev_seen`），与延迟融合/时间块注入同一读法——防"恒 hot"的既有同源契约自动覆盖新调用点。
- **组合链地板语义修正（实测教训，两轮）**：逐条衰减与时间衰减先后改为无地板变体 `decay_raw()` / `decay_time_raw()`——若在衰减中间步判 NEUTRAL_FLOOR，亚地板残值会被清零、漂移增量整体被吞（情绪身份被打回 neutral、跨消息累加断链，稳态数学失效）。第一轮只修了逐条衰减；对抗审查（双代理）用「写回盖 ts」的真实协议仿真揪出时间衰减步同病（纯热聊从零起步被钉死在 0.12 永不注入），第二轮补齐。地板判断移交给渲染层（`emotion_directive` / `emotion_short` 自带过滤，亚地板状态存而不显）；`decay()` / `decay_time()` 单独调用的地板契约不变。另修两处无地板消费者泄漏：`reunion_directive` 与 `cold_war_proactive_directive` 的 appy 抑制分支补地板守卫（亚地板残值与 neutral 同权，不触发重逢指令/不抑制冷落弧线）。另修一处配置陷阱：漂移量设 0 = 关闭该方向（而非走 bump 的"非法值回落默认量"——否则想关反而变成最大漂移）。
- **配置新增 4 键**（emotion 组，共 14 键）：`emotion_heat_drift_enable`（默认开）/ `emotion_hot_drift`（0.2）/ `emotion_cold_drift`（0.10，0=关闭该方向）/ `emotion_soothe_boost`（0.2）。与冷落降温弧线互补：弧线管**按天**的沉默（想念→抽离），热度漂移管**分钟级**的聊天节奏。
- 测试：`test_emotion.py` 新增 TestHeatDrift 19 用例（稳态收敛/**首条注入灵敏度钉**/**关键词=一条热聊的权重钉**/力度可配/**boost=0 关闭钉**/非法回落/初见守卫/零漂移关闭/亚地板残值跨消息累积/方向翻转/安抚优先/**真实写回协议仿真**（盖 ts、变化才写——钉死"时间衰减地板回归"形态）/重逢与弧线地板守卫）；`test_emotion_wiring.py` 新增 4 契约（调用点五参数+heat 赋值溯源 rhythm_heat 赋值语句/纯层首见守卫/schema 默认值/**handler 定义序契约**——_track_time_activity 先于 _track_activity，防未来重构挪动定义顺序改变热度语义）+ 顺序契约升级三段（衰减→漂移→安抚）；`test_cold_war_wiring` / `test_timeflow_v370_wiring` 逐条衰减与时间衰减锚点迁移 `decay`/`decay_time`→`decay_raw`/`decay_time_raw`（顺序断言强度不变）。
- 基线：宿主 venv 全套 **1393 passed / 35 subtests，exit 0**（对抗审查+两轮调参+权重审查修复后复跑；wip 归档独立复跑同绿）。

## 新增：应声虫复读（学舌玩梗）

- **搞怪消息触发**：用户发出不正经/搞怪消息（连续笑声 `哈哈哈哈`、纯标点玩梗 `？？？`、颜文字、玩梗口头禅 `笑死/绷不住/典中典`）时，以**默认 8% 概率原样复读**该条消息——还原网络「应声虫」玩梗行为，增加陪玩感。
- **保守判定**：`is_playful` 走"宁可漏判不可误判"策略——含**真实疑问**（吗/怎么/几点…）或**正经诉求**（帮我/请问/求…）的一律不学舌；仅 1~24 字短促消息参与；单字梗（草/典/6）须独立成句（"草莓""典礼"不误伤）。
- **只在私聊**：默认仅私聊参与（`allow_groups` 可放开群聊），与主动聊天同口径。
- **防连发**：复读后 `cooldown_turns`（默认 8）轮内不再抽签；每会话 `max_per_day`（默认 4）次上限，跨日自动重置。
- **纯原样**：命中后整条回复替换为用户原话并跳过全部改写链（100% 原样，不加字不改标点）；打字延迟按既有逻辑生效，短句自然落入快回窗口。
- **实现要点**：抽签在 `on_llm_request` 最前（不打断任何注入，LLM 照常调用，管线完整——记忆/情绪/统计无感知）；接管在 `humanize_response` 的早退门之前（独立于 `humanize.enabled` 与 min_length）。状态落 `parrot_state.json`（per-umo 轮次/计数，原子写、启动剪枝）。
- **默认关闭**（`parrot.enabled=false`），配置面板「复读 · 应声虫学舌」分组开启即生效。

- **语义判定档（judge_mode=llm）**：新增可选的 LLM 判定——`parrot.judge_mode=llm` 时，结构门（长度/非疑问/非求助）通过后先抽签（prob），命中的轮次**并行**发起"搞怪程度 0~10"判定（不阻塞生成，响应阶段读分），分数 ≥ `judge_threshold`（默认 7）才复读。能识别关键词抓不到的反话/冷幽默/阴阳怪气/依赖前文的笑点。代价：命中的短消息一次模型调用（可单独配 `judge_model` 用便宜模型）；超时/解析失败一律视为不复读。默认仍是 `regex`（零成本零延迟）。
- 配置新增 4 键：`judge_mode` / `judge_model` / `judge_timeout` / `judge_threshold`（parrot 组共 14 键）。
- 判定调用量：结构门通过面约 41%（语料实测）× prob 8% ≈ 每条消息 3% 概率触发一次判定。

## 修复：v4.28 下辅助 LLM 调用失效（`chat_provider_id` 必填）

- **症状**：AstrBot v4.28 起框架 `Context.llm_generate` 把 `chat_provider_id` 改为**必填** keyword-only 参数；插件 `invoke_llm` 在未解析出提供商时会省略该键，导致 `TypeError: missing 1 required keyword-only argument: 'chat_provider_id'`。
- **影响**：`judge_model` 配置为**裸模型名**（如 `deepseek-flash`）时，`parse_configured_target` 返回 `(None, model)` → 判定调用必然 TypeError 并被静默吞掉 → **`judge_mode=llm` 档应声虫复读从不触发**（运行日志实证「判定读取放弃: TypeError」）。承诺簿 LLM 复核（`commitments_extract_model` 裸名/空配置）为同类隐患，开启后会失效并回落正则。
- **修复**：新增 `_resolve_aux_provider_id()`——辅助 LLM 站点在未解析到提供商时回退解析「当前会话 provider → 第一个已加载 provider」；`_parrot_judge` / `_confirm_commitment_async` 接入该回退，时间线/提炼两处内联解析同源收敛。`invoke_llm` 增加边界防御：目标签名要求必填而 `provider_id=None` 时抛 `ValueError`（附指路文案），把深层 `TypeError` 变为边界可诊断错误。
- **安全方向**：解析不到任何 provider 时，复读安全放弃（不复读）、承诺回落正则（不漏账），绝不因解析失败中断调用链。

## 测试

- 新增 `tests/test_parrot.py`（含 structure_ok/parse_playful_score，共 66 用例）：搞怪判定正反例矩阵（含误判高危反例）、抽签概率边界与统计（10 万次抽样落在 8%±1%）、冷却/每日上限/跨日重置/剪枝、防抖合并取末段、main.py 接线 AST 契约（接管先于 enabled 门）、schema 默认值契约。
- 新增 `tests/test_parrot_functional.py`（18 用例，宿主门控）：复读全链 + LLM 判定档（阈值门控/判定未完成安全放弃/结构门先于判定）。
- 新增 `tests/test_llm_provider_wiring.py`：辅助 LLM 站点 provider 解析的 AST 接线守卫（禁止裸 `configured_provider` 直传 + 必含 `_resolve_aux_provider_id` 回退）。
- 基线：宿主 venv 全套 **1353 passed / 35 subtests**，no-host 1303/50。

# v4.0.0 (2026-09-12)

**大版本**：架构重构（装配层 / services / core 分层）与第五轮高星调研融入·波 1 合入，并并入控制台「实时事件流 / 仪表盘 / 前端改版」。重构不改外部行为（配置语义、命令、注入点与线上基线逐字段一致），行为增强见下。

## 新增：控制台实时事件流 + 总览仪表盘（并入 v3.9.6）

- **实时事件流**：`_bump_stats` 同步推进内存环形缓冲（`_events_ring`，封顶 80 条、重启清空），12 类关键事件带标签入环（去痕/改写/主动/风格/质检/分段/承诺）；控制台实时展示最近 40 条。事件推送为纯增强——任何异常不影响统计主链路。
- **总览仪表盘**：新增 `dashboard` 只读路由（经 `main.web_dashboard` 公开出口）：节奏档位+分数、非中性情绪会话列表、下次主动消息时刻、事件流。web_api 不再直读内部状态。
- **前端改版**：控制台 bundle/CSS 更新（仪表盘页 + 事件流面板）。
- 以上为另一工作线（v3.9.6）的成果并入本版本，功能级烟雾测试见 `test_tells_v2_functional.py`（环形缓冲封顶/标签事件/仪表盘形状/缺环安全回落）。

## 架构重构（本次合入）

- 拆分 god object `main.py`（5989→约 5680 行）：纯逻辑下沉 `humanizer_core/`（零 astrbot 依赖），可注入服务下沉 `services/`（KB/主动状态/语言画像），配置与状态经 facade 与统一 StateStore 收口。
- 统一 `invoke_llm` 调用点（能力位折叠 system_prompt、单轮预算与超时）、统一原子写状态、统一后台任务生命周期（TaskRegistry）。
- 行为不变式：接线签名、配置键、注入顺序与线上基线逐字段一致；全套测试基线重建（宿主口径 1216/3）。

## 新增：真人感规则库扩容与严重度分级（tells v2）

- **新增 9 条内置规则**（来源 公开真人感规则集 v3.0.0 的 25 条 patterns 增量，MIT，中文聊天场景机制级重写非照搬）：5 条注入型（禁对立句强调、禁铺垫式引入、克制破折号、禁堆叠修饰、禁模糊关联）+ 4 条质检型（自称 AI、宏大词升华、要点式列举、双破折号）。质检型经自然口语误报探针校准至零误报；「假想对立面」一条因中文无法用正则高置信区分（"很多人觉得X，但其实Y"真人亦常说）而**未收录**（宁漏勿错）。
- **引入 S1/S2/S3 严重度分级**（借鉴 公开同类规则集，MIT）：S1 单次出现即高置信、S2 按密度触发、S3 仅叠加时处理（对应 上游清单的 "weak alone"）。为全部 22 条既有内置规则补齐严重度；`RULES_VERSION` 1→2，升级时自动为缺字段的内置条目回填（**不触碰用户自建规则**）。
- **改写终检清单**：QC 命中后的改写指令追加"五条最易存活的 tells"复核段（不是X而是Y / 单句断言 / 破折号 / 三连排比 / 加粗小标题），防改写后痕迹复活。
- ⚠️「不是X而是Y」刻意归入**注入型**而非质检：中文口语「不是不想去，而是没时间」属自然表达，做正则必误杀。质检型只收高置信、口语罕见的痕迹，宁漏检不误触发整轮改写。

## 新增：注入节奏改为严重度感知子集轮换 + 贴尾注入

- 规则池扩容后会顶到注入封顶（20 条）导致末尾静默丢弃；且长对话里同批规则反复出现会被模型钝化。现改为：**S1/S2 核心每轮恒注入，S3 风味规则每轮轮换 2 条**（新纯函数 `select_inject_subset`）。总注入量稳定在封顶内，规则保持新鲜，且无未载入告警。
- **注入位置贴近对话末尾**：规则段优先经 `extra_user_content_parts` 追加（`mark_as_temp` 不进历史、不累积），生成前最后一刻最可见（ST Author's Note 的 @depth 同理）；旧框架自动回退拼 `system_prompt`（v3.5.2 原行为，tells 在旧框架不消失）。
- 轮换游标为进程内计数（展示性轮换，无需持久化）。
- **功能级验证**（`tests/test_tells_v2_functional.py`，宿主真框架实跑）：时间轴全扫描（3 组配置×素数步长×7~14 天）验证重排"严格前进、≤3 跳收敛、永不悬挂"；升级持久化往返（legacy→save→reload severity 不漂移）；真 `_rules_inject_text`/`_inject_rules_tail` 实跑（轮换与纯函数模型逐字一致、真 TextPart `_no_save` 生效、旧框架回退 system_prompt）。

## 新增：时段体系——按星期前缀 + 活跃时段白名单

- **免打扰时段（`proactive_quiet_hours`）扩展星期前缀**：支持 `mon-fri 01:00-07:00`、`sat+sun 00:00-23:59`、`0-4 09:00-18:00`（数字 **0=周一**…6=周日）等写法；不带前缀行为与旧版**逐字一致**（跨天、多段语义不变）。跨天段的星期按**起始日**归属（如 `fri 22:00-02:00` 覆盖周六凌晨）。
- **新增 `proactive_active_hours`（活跃时段白名单，默认空=不限制）**：配置后仅在其内主动发消息（与勿扰时段取交集）；时段外到期的主动消息显式重排到下一次进入活跃窗口，避免倒计时悬挂。控制台主动消息页同步展示。

## 测试

- 新增 `tests/test_tells_v2_and_windows.py`（31 用例）：严重度规范化/迁移回填/排序/子集轮换/终检清单；星期时段解析（含跨天归属、旧格式零回归）、活跃窗口、边界重排。
- 基线：宿主 venv 全套 **1269 passed / 3 skipped / 35 subtests，exit 0**（连跑两遍一致）；无宿主解释器口径 1237/35。
- 配置：净增 1 键（`proactive_active_hours`），**零键丢失、零默认值变更**。


> v3.9.5 及更早版本记录已归档到 [docs/CHANGELOG-archive.md](docs/CHANGELOG-archive.md)。
