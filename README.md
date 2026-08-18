# astrbot_plugin_humanizer — 好想成为人类啊

自动去除 AI 回复中的写作痕迹，让对话更自然、更有真人感。**插件启用后无需任何手动指令，每条 AI 回复都会自动经过人性化处理。**

整合自两个技能：

- **[Humanizer-zh](https://github.com/op7418/Humanizer-zh)**：中文 24 种 AI 写作模式（基于维基百科 [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)）
- **[stop-slop](https://github.com/hardikpandya/stop-slop)**：英文去 AI 痕迹核心规则与参考表

## 安装

### 方式一：WebUI 安装 zip（推荐）

在 AstrBot WebUI 的「插件管理」→ 安装插件中，选择本插件打包的 `astrbot_plugin_humanizer.zip` 上传安装，或直接拖入。

### 方式二：手动放置

将 `astrbot_plugin_humanizer` 文件夹（或解压 zip）放入 AstrBot 的 `data/plugins/` 目录：

```
AstrBot/
└── data/
    └── plugins/
        └── astrbot_plugin_humanizer/
            ├── metadata.yaml
            ├── main.py
            ├── _conf_schema.json
            ├── README.md
            └── humanizer_core/
                ├── __init__.py
                ├── llm_target.py
                ├── rules_zh.py
                ├── rules_en.py
                └── prompt.py
```

然后在 WebUI 的插件管理里启用/重载该插件。

> 要求 AstrBot >= 4.5.7（依赖 `on_llm_response` hook 与插件配置注入机制）。

## 使用

启用即生效，无需任何命令。处理流程：

1. 每条 AI 回复生成后，`on_llm_response` hook 自动接管
2. 自动检测语言（中文/英文）：
   - 中文：清除 AI 客套话（"希望这对您有帮助"等）、知识截止免责声明、填充语（"值得注意的是""此外"等）、"——"破折号滥用、过度限定、表情符号、通用积极结尾、否定式排比开头等
   - 英文：清除 throat-clearing openers、emphasis crutches、filler phrases、空泛副词、em-dash、商业行话、meta-commentary 等
3. 开启配置 `enable_llm_rewrite` 后，先调用大模型按合并后的技能指南深度改写，失败自动回落规则清理。默认跟随当前会话的模型；可在 `rewrite_model` 中指定用于深度改写的模型，或直接用命令选择（见下）。

## 深度改写模型选择

配置弹窗里的「深度改写模型」提供 **"选择提供商" 按钮**——点击弹出对话框，列出你所有已配置的提供商与模型，选中即保存（值为 `提供商/模型`，如 `xiaomi-token-plan/mimo-v2.5-pro`），无需手填。留空（不选择）则跟随当前会话模型。也可用命令查看/选择：

- `/humanizer_models`：列出所有已配置提供商及其可用模型（带编号）
- `/humanizer_model <编号>`：从列表中选择一个模型
- `/humanizer_model <模型名>`：直接指定模型名（会校验存在于已配置提供商）
- `/humanizer_model off`：恢复跟随当前会话模型
- `/humanizer_model`：查看当前设置

命令为管理员权限，效果等价于修改 `rewrite_model` 配置项并自动保存。

## 主动聊天（默认关闭）

用户沉默一段时间后，插件主动调用大模型生成一句自然的话发到该会话，实现"主动找用户聊天"。

- **开关**：`enable_proactive`（默认 `false`）。开启后，插件会在聊过的会话中检测沉默时长。**默认仅跟踪私聊**；`proactive_track_groups` 开启后才跟踪群聊。
- **重启不丢状态**：聊过会话的跟踪状态持久化在插件数据目录，重启 AstrBot 后无需重新发消息激活（超 24 小时无活动的会话自动清理）。
- **触发时机**：`silence_after_minutes`（默认 45 分钟）——用户最后一条消息后多久触发；`silence_fluctuation_minutes`（默认 15）控制随机波动幅度（45±15 = 30~60 分钟，填 0 固定不波动，均受 30 分钟下限约束）。触发后按同样规则随机重排下次。
- **勿扰时段**：`proactive_quiet_hours`（默认 `01:00-07:00` 凌晨勿扰；如 `22:00-07:00` 支持跨天），此时间段内不主动发。
- **提示词**：`proactive_prompt`（留空用内置模板），支持 `{persona}`、`{last_user}`、`{last_ai}` 占位符。`{persona}` 自动替换为**该会话在 AstrBot 中配置的人设**（未配置则用兜底句），主动消息会以你的人设口吻发起。
- **内容**：主动消息走**完整 Agent Pipeline**（CronMessageEvent + build_main_agent）——**human_style（风格）、angel_memory（记忆）等其他插件的上下文注入对主动消息生效**，问候会带上你配置的风格与记忆；发送走完整装饰/响应阶段（分段、TTS、记忆巩固等）。旧框架不支持时自动回落到轻量路径（直接生成 + 去 AI 痕迹 + 发送）。

⚠️ **副作用**：每次主动消息都会调用一次大模型（消耗 token）；可能打扰用户；建议配合勿扰时段使用。仅在"聊过"的会话触发，不会对陌生人发消息。

## 配置项

配置弹窗按两个平级分组展示（大标题）：

**① 润色设置**（humanize）——自动去除 AI 回复中的写作痕迹：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `true` | 总开关 |
| `enable_llm_rewrite` | `false` | 是否调用大模型深度改写（更自然，但每条消息额外消耗 token） |
| `rewrite_model` | 空 | 深度改写使用的模型名。留空跟随当前会话模型；填写模型名（如 `gpt-4o`、`deepseek-chat`）时，优先在当前会话的提供商内切换，不支持则自动在其它已配置提供商中查找，都找不到回落当前会话模型。**插件运行后配置弹窗会显示为你已配置模型的下拉列表**，也可用 `/humanizer_model` 命令选择 |
| `remove_emoji` | `true` | 移除表情符号 |
| `remove_reasoning` | `false` | 移除思考过程：隐藏模型生成的"🤔 思考: ..."，回复只显示正式内容（默认关闭，仅隐藏不阻止思考，见下方副作用说明） |
| `min_length` | `8` | 短于此长度的回复不处理 |
| `max_chars` | `300` | 长于此长度的回复只做规则清理，不 LLM 改写 |
| `debug` | `false` | 规则命中时输出命中阶段日志，便于排查误伤 |

**② 主动聊天**（proactive）——用户沉默后主动发消息：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `enable_proactive` | `false` | 主动聊天总开关（用户沉默后主动发消息） |
| `proactive_track_groups` | `false` | 是否跟踪群聊（默认仅私聊；群内任何成员发言都会刷新计时器，慎用） |
| `silence_after_minutes` | `45` | 静默多少分钟后触发主动聊天（下限 30，触发后重排） |
| `silence_fluctuation_minutes` | `15` | 静默时长随机波动幅度（±分钟，0=固定不波动） |
| `proactive_quiet_hours` | `01:00-07:00` | 主动聊天勿扰时段（`HH:MM-HH:MM`，支持跨天，空=不限） |
| `proactive_prompt` | 空 | 主动聊天消息的提示词模板（支持 `{persona}`/`{last_user}`/`{last_ai}`），留空用内置 |

> 旧版扁平配置会自动迁移到分组结构，用户设置不丢失；v2.0.0 起主动聊天键名改为 `silence_*`（旧键名自动迁移）。

## 设计说明

- **规则保守**：只处理高置信度的机械痕迹（套话、填充语、标点、高频词），不重写语义、不删减实质内容，避免误伤正常对话。
- **保留结构**：空白折叠只作用于空格/制表符，**换行符不受影响**——多段落回复、Markdown 表格、代码块结构完整保留；仅将 3 个及以上连续空行收敛为 2 个。
- **破折号区分处理**：中文破折号仅在出现 ≥2 次且两侧都是实际文字（插入式用法）时收敛为逗号，声音延长（"啊——"）等合法用法保留；英文仅处理 em-dash（—），en-dash（–）数字区间（如 2020–2026）保留。
- **递归保护**：LLM 改写请求不会再次触发本插件的 hook，防止死循环。
- **指定改写模型**：`rewrite_model` 支持跨提供商查找目标模型（模型列表结果缓存，避免每条消息重复向模型商查询）。
- **版本兼容**：自动检测 `llm_generate` 是否支持 `system_prompt` 参数，兼容不同 AstrBot 版本签名。

## ⚠️ 副作用与注意事项

使用前请了解以下行为，避免预期偏差：

- **移除思考 ≠ 阻止思考**：`remove_reasoning` 默认关闭；开启后只是让思考内容不显示在回复里，**模型仍会照常思考，思考产生的 token 照常计费**（推理模型如 mimo-v2.5-pro、deepseek-reasoner 的思考 token 通常更贵）。想真正省 token，请在模型提供商配置中关闭 thinking（如 `anth_thinking_config`），或改用非推理模型。
- **思考被无差别移除**：`remove_reasoning` 开启后，**所有**回复的思考内容都会被清除，包括你可能想查看的推理过程。如需查看某个模型的思考，请关闭此开关。
- **深度改写消耗额外 token**：开启 `enable_llm_rewrite` 后，每条消息会额外调用一次大模型，token 消耗和延迟都会增加；`max_chars` 只限制长文本跳过改写，不限制改写本身的成本。
- **规则清理可能误伤**：去 AI 痕迹的规则采用保守设计，但在个别情况下仍可能误删内容（如免责声明、破折号、英文副词）。如发现误伤，可关闭 `debug` 查看命中日志、关闭相关规则或整体关闭插件。
- **语言检测**：中英混排文本可能误判走另一语言规则集，但规则副作用已最小化（不破坏换行、代码块、数字区间等结构）。

## 许可

MIT。规则内容分别基于 Humanizer-zh 与 stop-slop（均为 MIT 许可）。
