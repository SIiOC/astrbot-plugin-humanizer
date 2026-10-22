# 控制台前端源码（webui/）

好想成为人类啊·AstrBot 插件控制台（Vue 3 + Vite + Naive UI）。构建产物直接写入
`../pages/humanizer-console/`，由 AstrBot 插件页以 iframe 加载。

## 目录

```
webui/
├── package.json           # 依赖与构建脚本
├── package-lock.json      # 锁定版本（构建可复现）
├── vite.config.ts         # base=./、outDir=../pages/humanizer-console
├── tsconfig.json / src/env.d.ts
├── index.html             # 入口 HTML
└── src/
    ├── main.ts            # 挂载 + hash 路由 + tokens.css
    ├── App.vue            # 顶栏导航 + 页面容器
    ├── router/index.ts    # 7 页路由
    ├── components/StatCard.vue
    ├── composables/
    │   ├── useBridge.ts   # AstrBotPluginPage 桥（apiGet/apiPost/upload/download）
    │   └── useCountUp.ts
    ├── styles/tokens.css  # Moonshot 式暗色设计 token
    └── views/
        ├── OverviewView.vue    # 总览（状态 + 对话节奏/情绪/事件流）
        ├── ConfigView.vue      # 配置（按 schema 分组动态渲染）
        ├── StylesView.vue      # 语料与风格
        ├── ProactiveView.vue   # 主动聊天
        ├── RecordsView.vue     # 记录回看
        ├── RulesView.vue       # 真人感规则
        └── StatsView.vue       # 统计
```

## 来源与补齐过程

- 基线：早期归档的 v3.2.0 前端源码（12 个源文件，仅含 `src/`）。
- v4.1.1 补齐：`package.json`、`package-lock.json`、`vite.config.ts`、`tsconfig.json`、
  `index.html`、`src/env.d.ts`、`src/composables/useBridge.ts`（协议从 v4.0.x 构建产物反推）；
  并新增 `RulesView.vue`（第 7 页）、更新 Config 分组标签、Stats 计数项与 Overview 仪表盘。
- 已用本源码重新构建并部署 `pages/humanizer-console`（产物名以 index.html 引用为准）。

## 构建

```bash
cd webui
npm install
npm run build          # 输出到 ../pages/humanizer-console（会清空旧产物）
```

- Node 18+（本机验证 Node 24 / npm 11）。
- **Windows 若报 `remove ... esbuild-*.tmp: Access is denied`**：esbuild 清理系统 TEMP
  被占用/杀软锁住，把 TEMP/TMP 指到工作区再构建即可：
  `$env:TEMP='<工作区>\.tmp'; $env:TMP=$env:TEMP; npm run build`。
- 构建后务必确认 `pages/humanizer-console/index.html` 引用的 `./assets/*.js|css` 存在
  （`tests/test_console_build_contract.py` 已钉死该契约）。

## 开发模式

```bash
npm run dev
```

浏览器直接打开时没有宿主注入的 `window.AstrBotPluginPage`，`useBridge` 会自动回落到
同源 `/api/plug/astrbot_plugin_wanna_be_human/<路由>`（需 AstrBot 正在运行且已登录；
跨 origin 时会被浏览器拦截，属于预期）。

## 主题与产物

主题沿用 Moonshot 式暗色 token（`src/styles/tokens.css`，与旧构建同源）。旧 minified
产物无源码可对照，视觉细节可能与上一版略有差异（页面结构、卡片质感一致）；功能与
接口以当前 `web_api.py`（19 路由）为准。

## 枚举配置与离线图标（v4.1.2）

- 配置页对 `_conf_schema.json` 中带 `options` 的键渲染为下拉框（时间/情绪/主动三组档位），
  `custom / simple / standard / full / reserved / clingy` 带中文语义标签。
- 总览首屏展示三组当前档位 chip；配置页档位键置顶（v4.1.3）。
- v4.1.4 UI：导航图标、配置页两列网格 + 未保存提示、规则页两列 + 筛选、状态卡可跳转。
- v4.1.5 UI：配置页改为两列「设置卡」网格（每项自包含标签/键名/控件），组内项数徽标，
  未保存项计数 + 放弃/保存操作条。
- v4.1.7 UI：统计卡 3×3 均衡网格、状态卡改为 border-box（修掉卡片与网格行高不一致导致的
  两行重叠）、卡片间距统一。
- v4.1.9 UI 与接口：七页统一「读取失败显示错误条」；主动聊天页新增暂停原因列与白名单/
  未回复上限/自适应间隔策略说明；统计页标签明确 qc 计数为「消息数」；总览情绪卡改为
  「最近情绪」并显示记录时间；记录回看增加过期响应丢弃。构建产物已重建。
- 图标不依赖在线 Iconify API：`npm run icons` 扫描 `src/` 用到的 `lucide:*` 图标并生成
  `src/icons.generated.ts`（内置 30 个，随构建产物一起分发）。改动图标用法后重新生成并提交。

## 运行时冒烟（Playwright）

```bash
python tools/verify_console.py          # 用本机 Edge + mock 桥数据打开 7 个页面
```

逐页检查渲染、收集 JS 错误/失败请求并截图（默认输出到工作区 `_verify/console/`）；
当前 7 页 0 错误通过。该工具需要本机安装 Edge/Chromium（无需 playwright 下载浏览器）。
