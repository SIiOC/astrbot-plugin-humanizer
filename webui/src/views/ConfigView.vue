<template>
  <n-spin :show="loading">
    <template v-if="!loading">
      <n-alert v-if="loadError" type="error" :bordered="false" class="mb-4">
        配置读取失败：{{ loadError }}。当前显示为空表单，请检查后端日志或重载插件后再试（已禁用保存，避免用不完整表单覆盖配置）。
      </n-alert>
      <n-input
        v-model:value="search"
        clearable
        placeholder="搜索配置项：标签 / 键名 / 说明"
        class="cfg-search"
      />
      <!-- v4.8.0：简单/专家视图——简单视图按域只露关键旋钮，专家视图给全量 -->
      <div class="cfg-viewbar">
        <span class="cfg-viewhint">
          {{ simpleView ? '简单视图：只显示每个分组的常用旋钮；搜索始终覆盖全部配置项' : '专家视图：显示全部配置项' }}
        </span>
        <n-switch v-model:value="simpleView" size="small">
          <template #checked>简单</template>
          <template #unchecked>专家</template>
        </n-switch>
      </div>
      <n-alert v-if="pendingImport" type="info" :bordered="false" class="import-preview">
        <div class="import-title">
          导入预览：将修改 <b>{{ pendingImport.changes.length }}</b> 项<template v-if="pendingImport.ignored.length">，忽略 <b>{{ pendingImport.ignored.length }}</b> 项</template><template v-if="pendingImport.same">（{{ pendingImport.same }} 项无变化）</template>
        </div>
        <ul v-if="pendingImport.changes.length" class="import-list">
          <li v-for="c in pendingImport.changes.slice(0, 5)" :key="c.group + '.' + c.key">
            {{ c.label }}：{{ String(c.from) }} → {{ String(c.to) }}
          </li>
        </ul>
        <p v-if="pendingImport.ignored.length" class="import-ignored">
          忽略示例：{{ pendingImport.ignored.slice(0, 3).join('；') }}<span v-if="pendingImport.ignored.length > 3"> …</span>
        </p>
        <div class="import-actions">
          <n-button size="small" type="primary" :disabled="!pendingImport.changes.length" @click="applyImport">
            应用导入
          </n-button>
          <n-button size="small" tertiary @click="pendingImport = null">取消</n-button>
        </div>
      </n-alert>
      <n-card class="cfg-card" content-style="padding: 6px 20px 22px;">
        <n-tabs v-model:value="activeTab" type="line" animated>
          <n-tab-pane
            v-for="(group, gname) in groups"
            :key="gname"
            :name="gname"
            :tab="tabLabel(gname, group.label)"
          >
            <n-alert
              v-if="gname === 'persona' && personaPreset !== 'custom'"
              type="info"
              :bordered="false"
              class="persona-note"
            >
              当前「{{ personaLabel }}」表达基调统一控制时间 / 情绪 / 主动三域。下方各组细分开关与域档位仍会保留，但暂不生效；切回「自定义」即可按细分开关工作。
            </n-alert>
            <div class="group-head">
              <p class="group-hint">{{ group.hint }}</p>
              <span class="group-count">{{ Object.keys(visibleItems(gname)).length }} / {{ itemCount(group) }} 项<template v-if="simpleView && !search.trim()">（简单视图）</template></span>
            </div>

            <div class="cfg-grid">
              <div
                v-for="(meta, key) in visibleItems(gname)"
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
                    :min="meta.min"
                    :max="meta.max"
                    :precision="meta.integer ? 0 : undefined"
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
            <p v-if="!Object.keys(visibleItems(gname)).length" class="group-hint cfg-empty">
              没有匹配「{{ search }}」的配置项。
            </p>
          </n-tab-pane>
        </n-tabs>
      </n-card>

      <div class="actions">
        <n-tag v-if="dirty" type="warning" round size="small">
          有 {{ dirtyCount }} 项未保存修改
        </n-tag>
        <n-tag v-else type="success" round size="small">配置已是最新</n-tag>
        <span class="actions-spacer" />
        <n-button tertiary @click="exportConfig">导出配置</n-button>
        <n-button tertiary @click="triggerImport">导入配置</n-button>
        <input
          ref="importInput"
          type="file"
          accept="application/json,.json"
          class="hidden-file"
          @change="onImportFile"
        />
        <n-button tertiary @click="load">放弃修改</n-button>
        <n-button type="primary" :loading="saving" :disabled="!dirty || !!loadError" @click="save">
          保存配置
        </n-button>
      </div>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
  persona: '表达基调 · 一键预设',
  style: '表达 · 说话风格与语料',
  humanize: '表达 · 润色去痕',
  time: '感知 · 时间与节奏',
  emotion: '感知 · 情绪惯性',
  proactive: '主动 · 聊天与追问',
  typing: '发送 · 延迟分段与防护',
  growth: '成长档案 · 私聊元数据',
}
const GROUP_HINTS: Record<string, string> = {
  persona: '一个旋钮同时决定时间/情绪/主动三域；选「自定义」才完全按细分开关工作',
  style: '风格档案、语料检索与真人感规则注入',
  humanize: '本地规则清理 AI 写作痕迹（不调用 LLM）；规则质检开关也在本组',
  time: '时间感知档位、间隙/节奏/历法/生活状态',
  emotion: '跨消息的轻微情绪状态与时间衰减',
  proactive: '主动聊天预设、话题选择与轻追问',
  typing: '打字延迟、消息分段与防抖防护',
  growth: '仅私聊按会话与宿主角色隔离；仅保存消息元数据，不保存消息正文；不会按天数自动晋级。日志损坏时只读且不写回。',
}

// 枚举型配置（schema 带 options）的人类可读标签；未列出的值原样显示。
// v4.8.1 自检：中文优先（旧版英文前缀对普通用户是噪音）。
const OPTION_LABELS: Record<string, string> = {
  custom: '自定义（按细分开关）',
  simple: '简化',
  standard: '标准',
  full: '完整',
  reserved: '克制',
  clingy: '黏人',
  natural: '自然',
  work: '工作',
}
function optLabel(v: string): string {
  return OPTION_LABELS[v] || v
}

// v4.8.1 自检：人格生效时明确提示「细分开关暂不生效」，避免用户改了没反应
const PERSONA_LABELS: Record<string, string> = {
  custom: '自定义',
  reserved: '克制',
  natural: '自然',
  clingy: '黏人',
  work: '工作',
}
const personaPreset = computed(() => String(draft.persona?.preset || 'custom'))
const personaLabel = computed(
  () => PERSONA_LABELS[personaPreset.value] || personaPreset.value,
)

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

// v4.4.0：配置导入/导出（仅改草稿，导入后仍需手动保存）
const importInput = ref<HTMLInputElement | null>(null)

function exportConfig() {
  const payload = {
    exported_at: new Date().toISOString(),
    config: JSON.parse(JSON.stringify(draft)),
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'humanizer-config.json'
  a.click()
  URL.revokeObjectURL(url)
}

function triggerImport() {
  importInput.value?.click()
}

// v4.6.0：导入先按配置项类型校验并生成预览，确认后才写入草稿
type ImportChange = {
  group: string
  key: string
  label: string
  from: any
  to: any
}
const pendingImport = ref<{
  changes: ImportChange[]
  ignored: string[]
  same: number
} | null>(null)

function validateImportValue(meta: any, value: unknown): string | null {
  const kind = meta?.kind
  if (kind === 'switch') {
    return typeof value === 'boolean' ? null : '需要布尔值'
  }
  if (kind === 'number') {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '需要数字'
    if (meta.integer && !Number.isInteger(value)) return '需要整数'
    if (typeof meta.min === 'number' && value < meta.min) return `不能小于 ${meta.min}`
    if (typeof meta.max === 'number' && value > meta.max) return `不能大于 ${meta.max}`
    return null
  }
  if (kind === 'select') {
    if (typeof value !== 'string') return '需要字符串选项'
    if (value === '') return null
    const options = Array.isArray(meta.options) ? meta.options : []
    return options.some((o: any) => o.value === value) ? null : '不在可选范围内'
  }
  if (kind === 'text' || kind === 'textarea') {
    return typeof value === 'string' ? null : '需要字符串'
  }
  return '不支持的类型'
}

// v4.7.0：复杂键（数组/对象，如 custom_corpus_files）不做控件，但导入时也要校验类型
function validateComplexValue(current: unknown, value: unknown): string | null {
  if (Array.isArray(current)) {
    if (!Array.isArray(value)) return '需要列表'
    if (!value.every((item) => typeof item === 'string')) return '列表项必须都是字符串'
    return null
  }
  if (current !== null && typeof current === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return '需要对象'
    return null
  }
  return typeof value === typeof current ? null : '类型不符'
}

function applyImport() {
  if (!pendingImport.value) return
  let applied = 0
  for (const c of pendingImport.value.changes) {
    draft[c.group][c.key] = c.to
    applied += 1
  }
  pendingImport.value = null
  message.success(`已应用 ${applied} 项配置，确认无误后点击「保存配置」`)
}

function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const parsed = JSON.parse(String(reader.result || '{}'))
      const payload = parsed && parsed.config ? parsed.config : parsed
      if (!payload || typeof payload !== 'object') {
        throw new Error('文件不是配置对象')
      }
      const changes: ImportChange[] = []
      const ignored: string[] = []
      let same = 0
      for (const gname of Object.keys(groups.value)) {
        const src = (payload as any)[gname]
        if (!src || typeof src !== 'object') continue
        const items = groups.value[gname].items || {}
        for (const [key, meta] of Object.entries(items)) {
          if (!(key in src)) continue
          const value = (src as any)[key]
          const err = validateImportValue(meta, value)
          const label = (meta as any).label || key
          if (err) {
            ignored.push(`${label}（${err}）`)
            continue
          }
          if (JSON.stringify(draft[gname][key]) === JSON.stringify(value)) {
            same += 1
            continue
          }
          changes.push({
            group: gname,
            key,
            label,
            from: draft[gname][key],
            to: value,
          })
        }
        // v4.7.0：复杂键也纳入导入（导出会包含它们，不处理会静默丢失）
        for (const key of Object.keys(draft[gname] || {})) {
          if (key in items || !(key in src)) continue
          const current = draft[gname][key]
          const value = (src as any)[key]
          const label = `${key}（复杂项）`
          const reason = validateComplexValue(current, value)
          if (reason) {
            ignored.push(`${label}（${reason}）`)
            continue
          }
          if (JSON.stringify(current) === JSON.stringify(value)) {
            same += 1
            continue
          }
          changes.push({ group: gname, key, label, from: current, to: value })
        }
        for (const key of Object.keys(src)) {
          if (!(key in (draft[gname] || {}))) ignored.push(`${gname}.${key}（未知键）`)
        }
      }
      for (const gname of Object.keys(payload as any)) {
        if (!(gname in groups.value)) ignored.push(`${gname}（未知分组）`)
      }
      if (!changes.length && !ignored.length) {
        pendingImport.value = null
        message.warning('文件与当前配置一致，无需导入')
        return
      }
      pendingImport.value = { changes, ignored, same }
    } catch (err: any) {
      pendingImport.value = null
      message.error(`导入失败：${err?.message || err}`)
    }
  }
  reader.readAsText(file, 'utf-8')
}

function itemCount(group: any): number {
  return Object.keys(group?.items || {}).length
}

// v4.3.0：配置项搜索——按标签/键名/说明过滤当前分组显示
const search = ref('')

// v4.8.0：简单/专家视图。简单视图按域只露关键旋钮；localStorage 记忆选择。
const SIMPLE_KEYS: Record<string, string[]> = {
  persona: ['preset'],
  style: ['enabled', 'active_style', 'active_style_autofallback', 'enable_retrieval', 'rules_enable', 'qc_enable'],
  humanize: ['enabled', 'remove_emoji'],
  time: ['awareness_mode', 'enable_gap', 'gap_threshold_minutes', 'enable_life'],
  emotion: ['emotion_mode', 'emotion_enable'],
  proactive: ['proactive_preset', 'enable_proactive', 'proactive_quiet_hours', 'proactive_active_hours'],
  typing: ['enable', 'delay_min', 'delay_max', 'split_enable'],
  growth: ['enabled'],
}
const SIMPLE_VIEW_KEY = 'humanizer-config-simple'
const simpleView = ref(true)
try {
  simpleView.value = localStorage.getItem(SIMPLE_VIEW_KEY) !== '0'
} catch {
  simpleView.value = true
}
watch(simpleView, (value) => {
  try {
    localStorage.setItem(SIMPLE_VIEW_KEY, value ? '1' : '0')
  } catch {
    /* 忽略 */
  }
})

function visibleItems(gname: string): Record<string, any> {
  const items = groups.value[gname]?.items || {}
  const q = search.value.trim().toLowerCase()
  if (q) {
    const out: Record<string, any> = {}
    for (const [key, meta] of Object.entries(items)) {
      const hay = `${(meta as any).label || ''} ${key} ${(meta as any).hint || ''}`.toLowerCase()
      if (hay.includes(q)) out[key] = meta
    }
    return out
  }
  if (!simpleView.value) return items
  const allow = SIMPLE_KEYS[gname] || []
  const out: Record<string, any> = {}
  for (const key of allow) {
    if (items[key]) out[key] = items[key]
  }
  return out
}
watch(search, (value) => {
  if (!value.trim()) return
  if (Object.keys(visibleItems(activeTab.value)).length) return
  const target = Object.keys(groups.value).find(
    (g) => Object.keys(visibleItems(g)).length > 0,
  )
  if (target) activeTab.value = target
})

// v4.7.0：搜索时在分组 tab 上显示匹配数，跨组命中不再被隐藏
function tabLabel(gname: string, label: string): string {
  const q = search.value.trim()
  if (!q) return label
  return `${label} (${Object.keys(visibleItems(gname)).length})`
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
            integer: kmeta.type === 'int',
            label: kmeta.description || key,
            hint: kmeta.hint || '',
            min: typeof kmeta.min === 'number' ? kmeta.min : undefined,
            max: typeof kmeta.max === 'number' ? kmeta.max : undefined,
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
      const detail = res?.errors
        ? Object.entries(res.errors)
            .slice(0, 3)
            .map(([k, v]) => `${k}: ${v}`)
            .join('；')
        : ''
      message.error(
        '保存失败: ' +
          ((res && res.error) || '未知错误') +
          (detail ? `（${detail}）` : ''),
      )
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
  /* v4.8.1 自检：卡片是 flex/grid 子项时允许收缩，避免 tabs 把页面撑宽 */
  min-width: 0;
}
.cfg-card :deep(.n-tabs),
.cfg-card :deep(.n-tabs-nav) {
  min-width: 0;
}
.cfg-card :deep(.n-tabs-nav) {
  margin-bottom: 2px;
}
.persona-note {
  margin: 10px 0 0;
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
  background: rgba(76, 54, 30, 0.06);
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
  border: 1px solid var(--hz-hairline);
  border-radius: 14px;
  background: var(--hz-card-2);
  transition: border-color 0.2s var(--hz-ease), background 0.2s var(--hz-ease);
}
.cfg-item:hover {
  border-color: rgba(164, 85, 43, 0.30);
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

/* v4.3.0：配置项搜索框 */
.cfg-search {
  max-width: 460px;
  margin-bottom: 14px;
}
/* v4.8.0：简单/专家视图切换条 */
.cfg-viewbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 14px;
  padding: 8px 14px;
  border: 1px solid var(--hz-border);
  border-radius: 10px;
  background: var(--hz-card-2);
}
.cfg-viewhint {
  font-size: 12.5px;
  color: var(--hz-text-2);
}
.cfg-empty {
  margin-top: 12px;
  opacity: 0.7;
}
/* v4.4.0：导入配置的隐藏文件选择器 */
.hidden-file {
  display: none;
}
/* v4.6.0：导入预览 */
.import-preview {
  margin-bottom: 14px;
}
.import-title {
  font-size: 13px;
  line-height: 1.6;
}
.import-list {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--hz-text-2);
}
.import-ignored {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--hz-text-3);
}
.import-actions {
  margin-top: 10px;
  display: flex;
  gap: 8px;
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
  background: rgba(242, 233, 216, 0.86);
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
