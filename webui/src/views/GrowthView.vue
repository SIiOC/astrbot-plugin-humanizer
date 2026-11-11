<template>
  <n-spin :show="summaryLoading">
    <template v-if="!summaryLoading">
      <n-alert v-if="loadError" type="error" :bordered="false" class="mb-4">
        成长档案状态读取失败：{{ loadError }}
      </n-alert>

      <n-alert v-if="!enabled && !loadError" type="warning" :bordered="false" class="mb-4">
        成长档案当前未启用；开启后仅在私聊记录元数据。可到
        <router-link to="/config?group=growth">配置页开启</router-link>；此页不会修改任何经历。
      </n-alert>

      <n-alert v-if="degraded" type="error" :bordered="false" class="mb-4">
        成长日志无法正常读取（{{ state.error || summaryState.error || '后端已标记为降级' }}）。当前不是正常空态，页面仅展示可读的只读信息，不会写回日志。
      </n-alert>

      <n-alert v-if="!degraded && !loadError && (pendingTotal > 0 || rejectedTotal > 0 || stuckTotal > 0)" type="warning" :bordered="false" class="mb-4">
        <template v-if="pendingTotal > 0">
          待写 {{ pendingTotal }} 条元数据仅存在内存中，退出进程前未落盘可能丢失。
        </template>
        <template v-if="stuckTotal > 0">
          无法写入 {{ stuckTotal }} 条（配额已满或存储报错）；调整配置或处理存储问题后才会重试。
        </template>
        <template v-if="rejectedTotal > 0">
          队列满时已拒收 {{ rejectedTotal }} 条（未保存，无法补写）。
        </template>
      </n-alert>

      <n-alert v-if="summaryState.available === false && !loadError" type="info" :bordered="false" class="mb-4">
        成长档案后端不可用（本次运行未装配成长服务）。页面保持只读空态，不会修改任何数据。
      </n-alert>

      <n-alert v-if="summaryState.scopes_truncated" type="info" :bordered="false" class="mb-4">
        会话数量超过单次读取上限，这里只列出前一部分；可用会话短标签在受控接口中单独查询。
      </n-alert>

      <div class="growth-actions">
        <span class="readonly-note">只读视图 · 不自动选择会话 · 手动刷新</span>
        <n-button size="small" tertiary :loading="summaryLoading || detailLoading || eventsLoading || diaryLoading" @click="refresh">
          刷新
        </n-button>
      </div>

      <div class="growth-layout">
        <n-card title="会话摘要" class="growth-card">
          <p class="card-note">仅显示会话的短 hash 标签，不暴露会话标识。选择会话后才读取对应状态与元数据事件。</p>
          <n-empty
            v-if="!scopes.length && !degraded && !loadError"
            description="暂无可选会话"
            size="small"
          />
          <div v-else class="scope-list">
            <button
              v-for="item in scopes"
              :key="item.id"
              type="button"
              class="scope-row"
              :class="{ selected: item.id === currentScope }"
              :aria-pressed="item.id === currentScope"
              @click="selectScope(item.id)"
            >
              <span class="scope-label">会话 #{{ shortScope(item.id) }}</span>
              <span class="scope-meta">观察积累 · {{ item.event_count ?? 0 }} 条事件</span>
              <span class="scope-last">{{ formatTimestamp(item.last_event_ts) }}</span>
            </button>
          </div>
        </n-card>

        <n-card title="成长状态" class="growth-card">
          <n-spin :show="detailLoading">
            <template v-if="currentScope">
              <n-alert v-if="detailError" type="error" :bordered="false" class="mb-3">
                当前会话状态读取失败：{{ detailError }}
              </n-alert>
              <div v-if="!detailError" class="state-content">
                <div class="state-heading">
                  <div>
                    <span class="eyebrow">当前会话</span>
                    <h2>会话 #{{ shortScope(currentScope) }}</h2>
                  </div>
                  <n-tag :type="state.cap_reached ? 'warning' : 'success'" round>
                    {{ state.cap_reached ? '已达上限' : '只读' }}
                  </n-tag>
                </div>
                <div class="stage-box">
                  <span class="eyebrow">当前阶段</span>
                  <strong>观察积累</strong>
                  <p>当前仅记录并展示事件元数据；阶段晋升语义尚未启用，不会按天数自动晋级。</p>
                </div>
                <n-grid :cols="2" responsive="screen" item-responsive :x-gap="12" :y-gap="12" class="state-grid">
                  <n-grid-item span="2 s:1">
                    <div class="metric"><span>用户话轮</span><b>{{ state.user_turns ?? 0 }}</b></div>
                  </n-grid-item>
                  <n-grid-item span="2 s:1">
                    <div class="metric"><span>回复话轮</span><b>{{ state.bot_turns ?? 0 }}</b></div>
                  </n-grid-item>
                  <n-grid-item span="2 s:1">
                    <div class="metric"><span>元数据事件</span><b>{{ state.event_count ?? 0 }}</b></div>
                  </n-grid-item>
                  <n-grid-item span="2 s:1">
                    <div class="metric"><span>已知天数</span><b>{{ Number(state.days_known ?? 0).toFixed(1) }}</b></div>
                  </n-grid-item>
                </n-grid>
                <n-alert v-if="state.cap_reached" type="warning" :bordered="false" class="mt-3">
                  已达到事件记录上限，后续仅保留只读展示，不会继续写入事件。
                </n-alert>
              </div>
            </template>
            <div v-else class="unselected-state">
              <n-empty description="尚未选择会话" size="small" />
              <p>这里不会默认选中任何会话。请从左侧选择一个短 hash 标签。</p>
            </div>
          </n-spin>
        </n-card>
      </div>

      <n-card v-if="currentScope" title="成长日记（事实版）" class="growth-card diary-card">
        <p class="card-note">
          只聚合已存储的元数据（条数 / 字数 / 时段），不含聊天内容；按本地时区显示最近
          {{ diary.window_days || 7 }} 天。关闭成长档案后不会生成或补写任何数据。
        </p>
        <n-alert v-if="diaryError" type="error" :bordered="false" class="mb-3">
          成长日记读取失败：{{ diaryError }}
        </n-alert>
        <n-spin :show="diaryLoading">
          <template v-if="!diaryError">
            <div class="diary-totals">
              <div class="diary-total"><span>用户话轮</span><b>{{ diary.totals?.user_turns ?? 0 }}</b></div>
              <div class="diary-total"><span>回复话轮</span><b>{{ diary.totals?.bot_turns ?? 0 }}</b></div>
              <div class="diary-total"><span>其中主动</span><b>{{ diary.totals?.proactive_turns ?? 0 }}</b></div>
              <div class="diary-total"><span>连续记录</span><b>{{ diary.streak_days ?? 0 }} 天</b></div>
            </div>
            <div class="diary-days">
              <div
                v-for="row in diaryRows"
                :key="row.date"
                class="diary-row"
                :class="{ empty: row.total === 0 }"
              >
                <span class="diary-date">{{ row.label }}</span>
                <div class="diary-bars" :title="`用户 ${row.user_turns} 条 / 回复 ${row.bot_turns} 条`">
                  <span class="diary-bar user" :style="{ width: barWidth(row.user_turns) }"></span>
                  <span class="diary-bar bot" :style="{ width: barWidth(row.bot_turns) }"></span>
                </div>
                <span class="diary-counts">{{ row.user_turns }} / {{ row.bot_turns }}</span>
              </div>
            </div>
            <div class="diary-hours" aria-label="窗口内活跃时段分布">
              <span
                v-for="(count, hour) in diary.active_hours || []"
                :key="hour"
                class="diary-hour"
                :class="{ on: count > 0 }"
                :title="`${hour}:00 · ${count} 条事件`"
              ></span>
            </div>
            <p class="card-note diary-foot">
              左：用户话轮；右：回复话轮；色条按窗口内最大值归一化。底部 24 格为 0–23 点活跃分布。
            </p>
          </template>
        </n-spin>
      </n-card>

      <n-card v-if="currentScope" title="元数据事件（最近 50 条）" class="growth-card events-card">
        <n-alert v-if="eventsError" type="error" :bordered="false" class="mb-3">
          事件读取失败：{{ eventsError }}
        </n-alert>
        <n-spin :show="eventsLoading">
          <n-data-table
            v-if="!eventsError"
            :columns="eventColumns"
            :data="events"
            :bordered="false"
            size="small"
            :scroll-x="560"
          />
          <n-empty v-if="!eventsError && !events.length && !eventsLoading" description="该会话暂无元数据事件" size="small" />
        </n-spin>
      </n-card>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { DataTableColumns } from 'naive-ui'
import { NAlert, NButton, NCard, NDataTable, NEmpty, NGrid, NGridItem, NSpin, NTag } from 'naive-ui'
import { useBridge } from '@/composables/useBridge'

type ScopeSummary = {
  id: string
  stage_name?: string
  event_count?: number
  last_event_ts?: string | number | null
}

type GrowthState = {
  enabled?: boolean
  scope_id?: string
  stage?: number
  stage_name?: string
  stage_reason?: string
  user_turns?: number
  bot_turns?: number
  event_count?: number
  days_known?: number
  last_event_ts?: string | number | null
  degraded?: boolean
  error?: string
  scopes?: ScopeSummary[]
  cap_reached?: boolean
  pending_writes?: number
  stuck_writes?: number
  rejected_writes?: number
  queue_full?: boolean
  scopes_truncated?: boolean
  available?: boolean
  busy?: boolean
}

type GrowthEvent = {
  schema_version?: number
  event_id?: string
  scope_id?: string
  type?: string
  kind?: string
  at?: string | number | null
  text_length?: number
  source?: string
}

type GrowthDiaryDay = {
  date: string
  user_turns?: number
  bot_turns?: number
  proactive_turns?: number
  user_chars?: number
  bot_chars?: number
  first_at?: number | null
  last_at?: number | null
}

type GrowthDiary = {
  window_days?: number
  tz_offset_minutes?: number
  event_count?: number
  active_days?: number
  streak_days?: number
  days?: GrowthDiaryDay[]
  totals?: Record<string, number>
  active_hours?: number[]
}

const { apiGet } = useBridge()
const summaryLoading = ref(true)
const detailLoading = ref(false)
const eventsLoading = ref(false)
const diaryLoading = ref(false)
const loadError = ref('')
const detailError = ref('')
const eventsError = ref('')
const diaryError = ref('')
const state = ref<GrowthState>({})
const summaryState = ref<GrowthState>({})
const scopes = ref<ScopeSummary[]>([])
const events = ref<GrowthEvent[]>([])
const diary = ref<GrowthDiary>({
  window_days: 7,
  streak_days: 0,
  days: [],
  totals: {},
  active_hours: [],
})
const currentScope = ref('')
let summaryRequest = 0
let scopeRequest = 0

const enabled = computed(() => !!summaryState.value.enabled)
const degraded = computed(() => !!summaryState.value.degraded || !!state.value.degraded)
const pendingTotal = computed(() =>
  Math.max(state.value.pending_writes ?? 0, summaryState.value.pending_writes ?? 0),
)
const rejectedTotal = computed(() =>
  Math.max(state.value.rejected_writes ?? 0, summaryState.value.rejected_writes ?? 0),
)
const stuckTotal = computed(() =>
  Math.max(state.value.stuck_writes ?? 0, summaryState.value.stuck_writes ?? 0),
)

const eventKindLabel: Record<string, string> = {
  start: '开始',
  user_turn: '用户话轮',
  bot_turn: '回复话轮',
}

const diaryMax = computed(() =>
  Math.max(
    1,
    ...(diary.value.days || []).map(day => Math.max(day.user_turns || 0, day.bot_turns || 0)),
  ),
)
const diaryRows = computed(() =>
  [...(diary.value.days || [])].reverse().map(day => ({
    ...day,
    total: (day.user_turns || 0) + (day.bot_turns || 0),
    label: diaryDayLabel(day.date),
  })),
)
function barWidth(value?: number): string {
  const count = Number(value) || 0
  if (!count) return '0%'
  return `${Math.max(4, Math.round((count / diaryMax.value) * 100))}%`
}
function diaryDayLabel(raw: string): string {
  const parsed = new Date(`${raw}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return raw
  const weekdays = '日一二三四五六'
  return `${parsed.getMonth() + 1}/${parsed.getDate()} 周${weekdays[parsed.getDay()]}`
}

const eventColumns: DataTableColumns<GrowthEvent> = [
  {
    title: '类型',
    key: 'type',
    width: 110,
    render: (row) => eventKindLabel[row.type || row.kind || ''] || '其他',
  },
  {
    title: '时间',
    key: 'at',
    width: 180,
    render: (row) => formatTimestamp(row.at),
  },
  {
    title: '消息长度',
    key: 'text_length',
    width: 110,
    render: (row) => row.text_length == null ? '—' : String(row.text_length),
  },
  {
    title: '来源',
    key: 'source',
    width: 120,
    render: (row) => row.source === 'reply' ? '对话回复' : row.source === 'proactive' ? '主动消息' : '—',
  },
]

function shortScope(value: string): string {
  return /^[a-f0-9]{64}$/i.test(value) ? value.slice(0, 8) : '未知'
}

function formatTimestamp(value: string | number | null | undefined): string {
  if (value == null || value === '') return '暂无记录'
  const timestamp = typeof value === 'number' && value < 1e12 ? value * 1000 : value
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '时间无效'
  return date.toLocaleString()
}

function isCurrent(token: number, scopeId: string): boolean {
  return token === scopeRequest && scopeId === currentScope.value
}

async function loadSummary() {
  const token = ++summaryRequest
  summaryLoading.value = true
  loadError.value = ''
  try {
    const res: any = await apiGet('growth/state')
    if (token !== summaryRequest) return
    if (!res?.ok) throw new Error(res?.error || '后端未返回有效状态')
    const next = (res.state || {}) as GrowthState
    summaryState.value = next
    scopes.value = Array.isArray(next.scopes) ? next.scopes : []
    if (!currentScope.value) state.value = next
  } catch (e: any) {
    if (token === summaryRequest) {
      loadError.value = e?.message || String(e)
      console.error('成长档案汇总读取失败:', e)
    }
  } finally {
    if (token === summaryRequest) summaryLoading.value = false
  }
}

async function selectScope(scopeId: string) {
  if (!/^[a-f0-9]{64}$/i.test(scopeId)) return
  const token = ++scopeRequest
  currentScope.value = scopeId
  state.value = {}
  detailLoading.value = true
  eventsLoading.value = true
  diaryLoading.value = true
  detailError.value = ''
  eventsError.value = ''
  diaryError.value = ''
  events.value = []
  diary.value = { window_days: 7, streak_days: 0, days: [], totals: {}, active_hours: [] }

  const [stateResult, eventsResult, diaryResult] = await Promise.allSettled([
    apiGet('growth/state', { scope: scopeId }),
    apiGet('growth/events', { scope: scopeId, limit: 50 }),
    apiGet('growth/diary', {
      scope: scopeId,
      days: 7,
      tz_offset_minutes: -new Date().getTimezoneOffset(),
    }),
  ])
  if (!isCurrent(token, scopeId)) return

  if (stateResult.status === 'fulfilled' && stateResult.value?.ok) {
    const next = (stateResult.value.state || {}) as GrowthState
    state.value = { ...next, scopes: scopes.value }
  } else {
    detailError.value = stateResult.status === 'rejected'
      ? stateResult.reason?.message || String(stateResult.reason)
      : stateResult.value?.error || '后端未返回有效状态'
  }
  if (eventsResult.status === 'fulfilled' && eventsResult.value?.ok) {
    events.value = Array.isArray(eventsResult.value.events) ? eventsResult.value.events : []
  } else {
    eventsError.value = eventsResult.status === 'rejected'
      ? eventsResult.reason?.message || String(eventsResult.reason)
      : eventsResult.value?.error || '后端未返回有效事件'
  }
  if (diaryResult.status === 'fulfilled' && diaryResult.value?.ok) {
    diary.value = (diaryResult.value.diary || {}) as GrowthDiary
  } else {
    diaryError.value = diaryResult.status === 'rejected'
      ? diaryResult.reason?.message || String(diaryResult.reason)
      : diaryResult.value?.error || '后端未返回有效成长日记'
  }
  detailLoading.value = false
  eventsLoading.value = false
  diaryLoading.value = false
}

async function refresh() {
  const selected = currentScope.value
  await loadSummary()
  if (selected && selected === currentScope.value) await selectScope(selected)
}

onMounted(loadSummary)
onBeforeUnmount(() => {
  summaryRequest += 1
  scopeRequest += 1
})
</script>

<style scoped>
.mb-3 { margin-bottom: 12px; }
.mb-4 { margin-bottom: 20px; }
.mt-3 { margin-top: 12px; }
.growth-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.readonly-note, .card-note, .unselected-state p {
  color: var(--hz-text-3);
  font-size: 12px;
  line-height: 1.7;
}
.growth-layout {
  display: grid;
  grid-template-columns: minmax(240px, 0.8fr) minmax(0, 1.2fr);
  gap: 16px;
}
.growth-card { min-width: 0; }
.card-note { margin: 0 0 12px; }
/* v4.9.1：成长日记（事实版） */
.diary-totals {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.diary-total {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--hz-hairline);
  border-radius: 10px;
  background: var(--hz-card-2);
}
.diary-total span { font-size: 11.5px; color: var(--hz-text-3); }
.diary-total b { font-size: 16px; color: var(--hz-text); }
.diary-days { display: flex; flex-direction: column; gap: 6px; }
.diary-row {
  display: grid;
  grid-template-columns: 86px minmax(0, 1fr) 56px;
  align-items: center;
  gap: 10px;
}
.diary-row.empty { opacity: 0.55; }
.diary-date { font-size: 12px; color: var(--hz-text-3); white-space: nowrap; }
.diary-bars {
  display: flex;
  flex-direction: column;
  gap: 3px;
  height: 14px;
  justify-content: center;
}
.diary-bar {
  display: block;
  height: 5px;
  min-width: 0;
  border-radius: 999px;
  transition: width 0.3s var(--hz-ease);
}
.diary-bar.user { background: var(--hz-pink); }
.diary-bar.bot { background: var(--hz-green, #5d7a3a); }
.diary-counts {
  font-size: 11.5px;
  color: var(--hz-text-3);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.diary-hours {
  display: grid;
  grid-template-columns: repeat(24, minmax(0, 1fr));
  gap: 3px;
  margin-top: 12px;
}
.diary-hour {
  height: 10px;
  border-radius: 3px;
  background: var(--hz-card-2);
}
.diary-hour.on { background: var(--hz-pink); opacity: 0.85; }
.diary-foot { margin: 10px 0 0; }
@media (max-width: 640px) {
  .diary-totals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .diary-row { grid-template-columns: 76px minmax(0, 1fr) 48px; gap: 8px; }
}
.scope-list { display: grid; gap: 8px; }
.scope-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 3px 10px;
  width: 100%;
  padding: 11px 12px;
  border: 1px solid var(--hz-hairline);
  border-radius: 10px;
  color: var(--hz-text-2);
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: border-color .2s, background .2s;
}
.scope-row:hover, .scope-row.selected { border-color: var(--hz-pink); background: var(--hz-pink-soft); }
.scope-row:focus-visible { outline: 2px solid var(--hz-pink); outline-offset: 2px; }
.scope-label { font-family: var(--hz-mono, ui-monospace, monospace); font-size: 12px; }
.scope-meta, .scope-last { color: var(--hz-text-3); font-size: 11px; }
.scope-last { grid-column: 2; grid-row: 1 / span 2; align-self: center; text-align: right; }
.state-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.eyebrow { display: block; color: var(--hz-text-3); font-size: 11px; letter-spacing: .06em; }
.state-heading h2 { margin: 4px 0 0; font-size: 18px; font-weight: 600; }
.stage-box { margin: 18px 0 14px; padding: 14px; border-radius: 10px; background: var(--hz-pink-soft); }
.stage-box strong { display: block; margin-top: 4px; font-size: 18px; color: var(--hz-text); }
.stage-box p { margin: 5px 0 0; color: var(--hz-text-2); font-size: 12px; line-height: 1.65; }
.metric { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border: 1px solid var(--hz-hairline); border-radius: 8px; color: var(--hz-text-3); font-size: 12px; }
.metric b { color: var(--hz-text); font-size: 16px; font-weight: 600; }
.unselected-state { padding: 26px 8px 18px; text-align: center; }
.events-card { margin-top: 16px; }
:deep(.n-card-header__main) { min-width: 0; }
@media (max-width: 720px) {
  .growth-layout { grid-template-columns: 1fr; }
}
@media (max-width: 390px) {
  .growth-actions { align-items: flex-start; }
  .scope-row { grid-template-columns: 1fr; }
  .scope-last { grid-column: 1; grid-row: auto; text-align: left; }
}
</style>
