<template>
  <n-spin :show="loading">
    <template v-if="!loading">
      <n-alert v-if="loadError" type="error" :bordered="false" class="mb-4">
        配置读取失败：{{ loadError }}。当前显示为空表单，请检查后端日志或重载插件后再试。
      </n-alert>
      <n-card class="cfg-card" content-style="padding: 6px 20px 22px;">
        <n-tabs v-model:value="activeTab" type="line" animated>
          <n-tab-pane
            v-for="(group, gname) in groups"
            :key="gname"
            :name="gname"
            :tab="group.label"
          >
            <div class="group-head">
              <p class="group-hint">{{ group.hint }}</p>
              <span class="group-count">{{ itemCount(group) }} 项</span>
            </div>

            <div class="cfg-grid">
              <div
                v-for="(meta, key) in group.items"
                :key="key"
                class="cfg-item"
                :class="{ wide: meta.kind === 'textarea' }"
              >
                <div class="cfg-item-head">
                  <span class="cfg-label">{{ meta.label || key }}</span>
                  <n-tooltip
                    v-if="meta.hint"
                    trigger="hover"
                    placement="top-start"
                    style="max-width: 420px"
                  >
                    <template #trigger>
                      <Icon icon="lucide:circle-help" class="lbl-info" />
                    </template>
                    <span class="tip-text">{{ meta.hint }}</span>
                  </n-tooltip>
                  <span class="cfg-key" :title="key">{{ key }}</span>
                </div>

                <div class="cfg-item-ctl">
                  <template v-if="meta.kind === 'switch'">
                    <n-switch v-model:value="draft[gname][key]" />
                    <span class="switch-state">
                      {{ draft[gname][key] ? '已开启' : '已关闭' }}
                    </span>
                  </template>
                  <n-input-number
                    v-else-if="meta.kind === 'number'"
                    v-model:value="draft[gname][key]"
                    class="ctl-number"
                  />
                  <n-select
                    v-else-if="meta.kind === 'select'"
                    v-model:value="draft[gname][key]"
                    :options="selOpts(gname, key)"
                    clearable
                    filterable
                    placeholder="默认 / 自动"
                  />
                  <n-input
                    v-else-if="meta.kind === 'textarea'"
                    v-model:value="draft[gname][key]"
                    type="textarea"
                    :autosize="{ minRows: 3, maxRows: 8 }"
                  />
                  <n-input
                    v-else
                    v-model:value="draft[gname][key]"
                    placeholder=""
                  />
                </div>
              </div>
            </div>
          </n-tab-pane>
        </n-tabs>
      </n-card>

      <div class="actions">
        <n-tag v-if="dirty" type="warning" round size="small">
          有 {{ dirtyCount }} 项未保存修改
        </n-tag>
        <n-tag v-else type="success" round size="small">配置已是最新</n-tag>
        <span class="actions-spacer" />
        <n-button tertiary @click="load">放弃修改</n-button>
        <n-button type="primary" :loading="saving" :disabled="!dirty" @click="save">
          保存配置
        </n-button>
      </div>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NInput,
  NInputNumber,
  NSelect,
  NSpin,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  NTooltip,
  useMessage,
} from 'naive-ui'
import { Icon } from '@iconify/vue'
import { useBridge } from '@/composables/useBridge'

const { apiGet, apiPost } = useBridge()
const message = useMessage()
const route = useRoute()
// v4.1.8：支持 /config?group=humanize 深链，从总览卡片直达对应分组
const activeTab = ref('')

const loading = ref(true)
const saving = ref(false)
const groups = ref<any>({})
const draft = reactive<Record<string, Record<string, any>>>({})
// v4.1.9：后端读取失败会返回 degraded 标记，页面必须显式提示而不是显示空表单
const loadError = ref('')
// v4.1.5：未保存修改（按配置项逐项比较，显示具体数量）
const baselineSnapshot = ref<Record<string, Record<string, any>> | null>(null)

const GROUP_LABELS: Record<string, string> = {
  style: '表达 · 说话风格与语料',
  humanize: '表达 · 润色去痕',
  time: '感知 · 时间与节奏',
  emotion: '感知 · 情绪惯性',
  proactive: '主动 · 聊天与追问',
  typing: '发送 · 延迟分段与防护',
}
const GROUP_HINTS: Record<string, string> = {
  style: '风格档案、语料检索与真人感规则注入',
  humanize: '本地规则清理 AI 写作痕迹（不调用 LLM）；规则质检开关也在本组',
  time: '时间感知档位、间隙/节奏/历法/生活状态',
  emotion: '跨消息的轻微情绪状态与时间衰减',
  proactive: '主动聊天预设、话题选择与轻追问',
  typing: '打字延迟、消息分段与防抖防护',
}

// 枚举型配置（schema 带 options）的人类可读标签；未列出的值原样显示
const OPTION_LABELS: Record<string, string> = {
  custom: 'custom · 按细分开关',
  simple: 'simple · 简化',
  standard: 'standard · 标准',
  full: 'full · 完整',
  reserved: 'reserved · 克制',
  clingy: 'clingy · 黏人',
}
function optLabel(v: string): string {
  return OPTION_LABELS[v] || v
}

const dirtyCount = computed(() => {
  const base = baselineSnapshot.value
  if (loading.value || !base) return 0
  let n = 0
  for (const g of Object.keys(draft)) {
    const bg = base[g] || {}
    for (const k of Object.keys(draft[g])) {
      if (JSON.stringify(bg[k]) !== JSON.stringify(draft[g][k])) n += 1
    }
  }
  return n
})
const dirty = computed(() => dirtyCount.value > 0)

function itemCount(group: any): number {
  return Object.keys(group?.items || {}).length
}

// 下拉控件候选项：load() 时后端动态枚举结果已映射进 items[key].options
function selOpts(g: unknown, key: string | number) {
  const gg = groups.value[g as string]
  return gg?.items?.[key as string]?.options || []
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res: any = await apiGet('config')
    if (!res || !res.ok) throw new Error((res && res.error) || '配置读取失败')
    if (res.degraded) loadError.value = String(res.error || '后端配置不完整')
    const config = res.config || {}
    const schemaMeta = res.schema_meta || {}
    // 后端动态枚举的下拉选项（key 形如 "style/embedding_provider_id"）
    const dynOptions: Record<string, string[]> = res.options || {}
    groups.value = {}
    for (const g of Object.keys(GROUP_LABELS)) {
      const values = config[g] || {}
      const gmeta = schemaMeta[g] || {}
      groups.value[g] = {
        label: GROUP_LABELS[g] || g,
        hint: GROUP_HINTS[g] || '',
        items: {},
      }
      draft[g] = {}
      // 档位键置顶（否则按配置文件键序常落在分组末尾，不易发现）
      const MODE_KEYS = new Set(['awareness_mode', 'emotion_mode', 'proactive_preset'])
      const valueKeys = Object.keys(values)
      const orderedKeys = [
        ...valueKeys.filter(k => MODE_KEYS.has(k)),
        ...valueKeys.filter(k => !MODE_KEYS.has(k)),
      ]
      for (const key of orderedKeys) {
        draft[g][key] = values[key]
        const kmeta = (gmeta.items && gmeta.items[key]) || {}
        // 渲染语义类型归一化：boolean → 开关、number → 数字框、
        // 长文本 → textarea、其余文本 → 输入框；数组等复杂类型不渲染控件。
        const t = typeof values[key]
        let kind =
          t === 'boolean'
            ? 'switch'
            : t === 'number'
              ? 'number'
              : t === 'string' && String(values[key]).length > 60
                ? 'textarea'
                : t === 'string'
                  ? 'text'
                  : 'skip' // 数组等复杂类型（如 custom_corpus_files）不做控件——防误改类型
        // 后端枚举到动态选项的键 → 下拉；schema 自带 options 的枚举键同样下拉。
        const opts: string[] = [...(dynOptions[`${g}/${key}`] || [])]
        const schemaOpts: string[] = Array.isArray(kmeta.options)
          ? kmeta.options.filter((o: unknown) => typeof o === 'string')
          : []
        for (const o of schemaOpts) {
          if (!opts.includes(o)) opts.push(o)
        }
        if (opts.length) {
          const cur = draft[g][key]
          if (typeof cur === 'string' && cur && !opts.includes(cur)) {
            opts.unshift(cur)
          }
          kind = 'select'
        }
        if (kind !== 'skip') {
          groups.value[g].items[key] = {
            kind,
            label: kmeta.description || key,
            hint: kmeta.hint || '',
            options: kind === 'select' ? opts.map(o => ({ label: optLabel(o), value: o })) : [],
          }
        }
      }
    }
    const requested = String(route.query.group || '')
    activeTab.value =
      requested && groups.value[requested]
        ? requested
        : Object.keys(groups.value)[0] || ''
    baselineSnapshot.value = JSON.parse(JSON.stringify(draft))
  } catch (e: any) {
    loadError.value = e?.message || String(e)
    message.error('配置读取失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    // draft 是 reactive() 的 Proxy，postMessage 结构化克隆无法克隆 Proxy，
    // 必须深拷贝成普通对象再传给桥（否则报 "could not be cloned"）。
    const payload: Record<string, any> = {}
    for (const g of Object.keys(draft)) {
      payload[g] = JSON.parse(JSON.stringify(draft[g]))
    }
    const res: any = await apiPost('config/save', payload)
    if (res && res.ok) {
      message.success('配置已保存')
      await load()
    } else {
      message.error('保存失败: ' + ((res && res.error) || '未知错误'))
    }
  } catch (e: any) {
    message.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.cfg-card {
  --n-padding-middle: 4px 20px 22px;
}
.cfg-card :deep(.n-tabs-nav) {
  margin-bottom: 2px;
}

/* 分组标题：说明 + 项数徽标 */
.group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 0 16px;
}
.group-hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--hz-text-3);
}
.group-count {
  flex-shrink: 0;
  padding: 2px 10px;
  border: 1px solid var(--hz-hairline);
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.05);
  font-size: 12px;
  color: var(--hz-text-3);
  font-variant-numeric: tabular-nums;
}

/* 两列设置卡：每项自包含，控制类型不同也不会破坏对齐 */
.cfg-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.cfg-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 96px;
  padding: 13px 15px 14px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 14px;
  background: var(--hz-card-2);
  transition: border-color 0.2s var(--hz-ease), background 0.2s var(--hz-ease);
}
.cfg-item:hover {
  border-color: rgba(255, 110, 199, 0.24);
}
.cfg-item.wide {
  grid-column: 1 / -1;
}
.cfg-item-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 18px;
}
.cfg-label {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--hz-text-2);
}
.lbl-info {
  flex-shrink: 0;
  font-size: 14px;
  opacity: 0.5;
  cursor: help;
}
.tip-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.cfg-key {
  margin-left: auto;
  max-width: 42%;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-family: var(--hz-mono, ui-monospace, monospace);
  font-size: 10.5px;
  color: var(--hz-text-3);
  opacity: 0.55;
}
.cfg-item-ctl {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}
.cfg-item-ctl :deep(.n-input),
.cfg-item-ctl :deep(.n-base-selection) {
  width: 100%;
}
.switch-state {
  font-size: 12px;
  color: var(--hz-text-3);
}
.ctl-number {
  width: 160px !important;
}

/* 吸底操作条：左侧状态、右侧操作 */
.actions {
  position: sticky;
  bottom: 0;
  margin-top: 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  background: rgba(10, 10, 10, 0.82);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  backdrop-filter: blur(16px) saturate(140%);
  border-top: 1px solid var(--hz-hairline);
  z-index: 10;
}
.actions-spacer {
  flex: 1;
}

@media (max-width: 900px) {
  .cfg-grid {
    grid-template-columns: 1fr;
  }
  .cfg-item.wide {
    grid-column: auto;
  }
}
</style>
