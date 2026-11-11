<template>
  <n-spin :show="loading">
    <template v-if="!loading">
      <n-alert v-if="loadError" type="error" :bordered="false" class="hz-section">
        控制台数据读取失败：{{ loadError }}（以下状态可能显示为空 / 为 0，不代表真实情况）
      </n-alert>
      <!-- hero：白字大标题 + 灰副题 + 状态胶囊（背后极淡呼吸光） -->
      <section class="hero">
        <div class="hero-glow" aria-hidden="true"></div>
        <h1 class="hero-title">好想成为人类啊</h1>
        <p class="hero-sub">
          人类风格注入 · AI 痕迹去除 · 主动续聊。日常使用在聊天窗口，这里查看与调整插件状态。
        </p>
        <div class="hero-chips hz-reveal" style="animation-delay: 120ms">
          <span class="chip" :title="status.started_at ? `启动于 ${fmtTime(status.started_at)}` : '插件运行版本'">
            <Icon icon="lucide:badge-check" style="font-size: 14px" />
            运行版本：{{ status.version || '未知' }}
          </span>
          <span class="chip">
            <Icon icon="lucide:badge-check" style="font-size: 14px" />
            当前风格：{{ status.active_style || '未启用' }}
          </span>
          <router-link class="chip chip-link" to="/config?group=persona" title="点击切换表达基调（克制/自然/黏人/工作）">
            <Icon icon="lucide:users" style="font-size: 14px" />
            表达基调：{{ status.profile_label || '自定义' }}
          </router-link>
          <span
            v-if="status.active_style_invalid"
            class="chip chip-warn"
            :title="`配置项 active_style 为「${status.active_style_configured || '空'}」，但实际生效为「${status.active_style || '无'}」；可到配置页修正，或重新开启「风格留空时自动回退」`"
          >
            风格配置已失效
          </span>
          <span class="chip">
            <Icon icon="lucide:message-circle" style="font-size: 14px" />
            主动聊天：{{ status.proactive ? '开' : '关' }}
          </span>
          <span class="chip">
            <Icon icon="lucide:sunrise" style="font-size: 14px" />
            生活状态：{{ status.life_enabled ? '开' : '关' }}
          </span>
          <router-link class="chip chip-link" to="/config?group=time" title="点击调整时间感知档位">
            <Icon icon="lucide:clock" style="font-size: 14px" />
            时间：{{ modeLabel(status.awareness_mode) }}
          </router-link>
          <router-link class="chip chip-link" to="/config?group=emotion" title="点击调整情绪机制档位">
            <Icon icon="lucide:heart" style="font-size: 14px" />
            情绪：{{ modeLabel(status.emotion_mode) }}
          </router-link>
          <router-link class="chip chip-link" to="/config?group=proactive" title="点击调整主动聊天预设">
            <Icon icon="lucide:message-circle" style="font-size: 14px" />
            主动：{{ modeLabel(status.proactive_preset) }}
          </router-link>
        </div>
      </section>

      <!-- v4.8.0：首装三步向导（按真实状态显示完成度，可关闭，仅首次展示） -->
      <section v-if="showOnboarding" class="hz-section onboarding hz-reveal" style="animation-delay: 100ms">
        <n-card>
          <div class="onb-head">
            <span>第一次用？三步开始</span>
            <span class="onb-progress" :class="{ done: onboardingAllDone }">
              已完成 {{ onboardingDone }} / {{ onboardingSteps.length }}
            </span>
          </div>
          <ul class="onb-steps">
            <li v-for="s in onboardingSteps" :key="s.key" class="onb-step" :class="{ done: s.done }">
              <span class="onb-check">{{ s.done ? '✓' : '○' }}</span>
              <span class="onb-copy">
                <span class="onb-title">{{ s.title }}</span>
                <span class="onb-detail">{{ s.detail }}</span>
              </span>
              <router-link v-if="!s.done" :to="s.to" class="onb-link">
                <n-button size="tiny" tertiary>{{ s.cta }}</n-button>
              </router-link>
              <span v-else class="onb-badge">已完成</span>
            </li>
          </ul>
          <div class="onb-actions">
            <router-link to="/styles">
              <n-button size="small" type="primary">去导入语料</n-button>
            </router-link>
            <router-link to="/config">
              <n-button size="small" tertiary>打开配置</n-button>
            </router-link>
            <n-button size="small" quaternary @click="dismissOnboarding">
              {{ onboardingAllDone ? '完成，收起' : '知道了，不再提示' }}
            </n-button>
          </div>
        </n-card>
      </section>

      <!-- v4.8.2：人格快捷切换（直接写配置，无需进配置页） -->
      <section class="hz-section persona-switch hz-reveal" style="animation-delay: 160ms">
        <n-card title="表达基调预设">
          <p class="dim persona-hint">
            一个旋钮统一决定时间 / 情绪 / 主动三域；点击立即写入配置，不会改写你保存的细分开关。
          </p>
          <div class="persona-actions">
            <n-button
              v-for="p in PERSONAS"
              :key="p.value"
              size="small"
              :type="currentProfile === p.value ? 'primary' : 'default'"
              :ghost="currentProfile !== p.value"
              :loading="switchingPersona === p.value"
              :disabled="!!switchingPersona || currentProfile === p.value"
              @click="switchPersona(p.value)"
            >
              {{ p.label }}
            </n-button>
            <span class="persona-current">当前：{{ status.profile_label || '自定义' }}</span>
          </div>
        </n-card>
      </section>

      <!-- 状态瓷贴（瀑布入场 + 开关呼吸点） -->
      <section class="hz-section">
        <n-grid :cols="4" responsive="screen" item-responsive :x-gap="16" :y-gap="16">
          <n-grid-item span="4 s:2 m:1" v-for="card in cards" :key="card.label">
            <StatCard v-bind="card" />
          </n-grid-item>
        </n-grid>
      </section>

      <!-- 最近趋势：注入字符 / 检索缓存命中（内存态，最近 20 轮） -->
      <section class="hz-section hz-reveal" style="animation-delay: 240ms">
        <n-grid :cols="2" responsive="screen" item-responsive :x-gap="16" :y-gap="16">
          <n-grid-item span="2 s:2 m:1">
            <n-card title="最近注入字符">
              <SparkBars :values="injectRecent" />
              <p class="dim trend-hint">最近 {{ injectRecent.length }} 轮，每根柱子为单轮注入字符数。</p>
            </n-card>
          </n-grid-item>
          <n-grid-item span="2 s:2 m:1">
            <n-card title="检索缓存命中">
              <SparkBars :values="cacheRecent" hit-mode />
              <p class="dim trend-hint">最近 {{ cacheRecent.length }} 次检索：橄榄=命中，灰色=未命中。</p>
            </n-card>
          </n-grid-item>
        </n-grid>
      </section>

      <!-- v4.8.2：声明式注入管线的本轮构成 -->
      <section v-if="pipeline.length" class="hz-section hz-reveal" style="animation-delay: 270ms">
        <n-card title="本轮注入构成">
          <div class="pipe-list">
            <div v-for="p in pipeline" :key="p.name" class="pipe-row">
              <span class="pipe-label">{{ p.label }}</span>
              <div class="pipe-track">
                <span class="pipe-fill" :style="{ width: pipeWidth(p) }"></span>
              </div>
              <span class="pipe-num">{{ p.last_chars }} 字</span>
            </div>
          </div>
          <p class="dim trend-hint">
            来自声明式注入管线：顺序、落点与依赖集中声明；0 字表示该注入器本轮未生效。
          </p>
        </n-card>
      </section>

      <!-- 仪表盘：节奏 / 情绪 / 实时事件流 -->
      <section class="hz-section hz-reveal" style="animation-delay: 300ms">
        <n-grid :cols="2" responsive="screen" item-responsive :x-gap="16" :y-gap="16">
          <n-grid-item span="2 s:2 m:1">
            <n-card title="对话节奏">
              <div class="viz-row">
                <n-tag round :type="rhythmTagType" size="large">{{ rhythmLabel }}</n-tag>
                <span class="viz-score">{{ rhythmScore }}</span>
                <span class="dim">近段活跃度（0-100）</span>
              </div>
              <p class="viz-hint">
                节奏取自最近活跃会话的「距上次交流」时长：热聊/常态/冷场会改变主动消息与语气策略。
              </p>
            </n-card>
          </n-grid-item>
          <n-grid-item span="2 s:2 m:1">
            <n-card title="最近情绪">
              <template v-if="latestEmotion">
                <div class="viz-row">
                  <n-tag round type="primary">{{ emotionLabel }}</n-tag>
                  <span class="viz-score">{{ Math.round((latestEmotion.intensity || 0) * 100) }}%</span>
                </div>
                <p class="viz-hint">
                  会话 {{ shortUmo(latestEmotion.umo) }} · {{ fmtTime(latestEmotion.ts) }} 记录 ·
                  情绪强度随时间衰减；被冷落会蔫、被安抚会开心。
                </p>
              </template>
              <p v-else class="viz-hint">当前所有会话情绪平静。</p>
            </n-card>
          </n-grid-item>
        </n-grid>
      </section>

      <section class="hz-section hz-reveal" style="animation-delay: 420ms">
        <n-grid :cols="2" responsive="screen" item-responsive :x-gap="16" :y-gap="16">
          <n-grid-item span="2 s:2 m:1">
            <n-card title="可用风格档案">
              <n-space align="center">
                <n-tag v-if="status.active_style" type="primary" round>
                  {{ status.active_style }}
                </n-tag>
                <n-tag v-else size="small" round>未启用</n-tag>
                <span class="dim">
                  共 {{ (status.styles || []).length }} 个档案：{{
                    (status.styles || []).join('、') || '（无）'
                  }}
                </span>
              </n-space>
            </n-card>
          </n-grid-item>
          <n-grid-item span="2 s:2 m:1">
            <n-card title="实时事件流">
              <template v-if="events.length">
                <div v-for="(ev, i) in events" :key="i" class="event-row">
                  <span class="event-time">{{ fmtTime(ev.ts) }}</span>
                  <n-tag size="small" round>{{ ev.tag }}</n-tag>
                  <span class="event-msg">{{ ev.msg }}</span>
                </div>
              </template>
              <p v-else class="viz-hint">暂无事件（插件运行后会自动记录去痕/主动/分段等行为）。</p>
            </n-card>
          </n-grid-item>
          <n-grid-item span="2 s:2 m:2">
            <n-card title="最近清理明细">
              <template v-if="cleanup.length">
                <div v-for="(row, i) in cleanup" :key="i" class="event-row">
                  <span class="event-time">{{ fmtTime(row.ts) }}</span>
                  <n-tag size="small" round type="success">{{ (row.hits || []).join(' / ') || '命中' }}</n-tag>
                  <span class="event-msg">{{ row.before }} → {{ row.after }}</span>
                </div>
              </template>
              <p v-else class="viz-hint">
                暂无记录：在「配置 → 润色去痕」开启 debug 后，最近 10 次规则命中会显示在这里。
              </p>
            </n-card>
          </n-grid-item>
        </n-grid>
      </section>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NGrid,
  NGridItem,
  NSpace,
  NSpin,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import { Icon } from '@iconify/vue'
import StatCard from '@/components/StatCard.vue'
import SparkBars from '@/components/SparkBars.vue'
import { useBridge } from '@/composables/useBridge'

const { apiGet, apiPost } = useBridge()
const dialog = useDialog()
const message = useMessage()
const loading = ref(true)
const status = ref<any>({})
const dash = ref<any>({})
const corpus = ref<any>({})
const loadError = ref('')
// v4.7.0：首装向导只在第一次进入时展示，关闭后写 localStorage
const ONBOARDING_KEY = 'humanizer-onboarding-dismissed'
const showOnboarding = ref(false)
try {
  showOnboarding.value = localStorage.getItem(ONBOARDING_KEY) !== '1'
} catch {
  showOnboarding.value = false
}
function dismissOnboarding() {
  showOnboarding.value = false
  try {
    localStorage.setItem(ONBOARDING_KEY, '1')
  } catch {
    /* 忽略 */
  }
}
const injectRecent = computed(() =>
  (dash.value.inject?.recent || []).map((v: any) => Number(v) || 0),
)

// v4.8.2：人格快捷切换 + 注入管线可视化
const PERSONAS = [
  { value: 'reserved', label: '克制' },
  { value: 'natural', label: '自然' },
  { value: 'clingy', label: '黏人' },
  { value: 'work', label: '工作' },
  { value: 'custom', label: '自定义' },
]
const currentProfile = computed(() => String(status.value.profile || 'custom'))

// v4.8.0：首装向导不再写死文案——按语料/风格/人格的真实状态显示完成度
const corpusUser = computed(() => Number(corpus.value.user) || 0)
const corpusTotal = computed(() => Number(corpus.value.total) || 0)
const corpusLoaded = ref(false)
const onboardingSteps = computed(() => {
  const styleName = String(status.value.active_style || '')
  const styleCount = (status.value.styles || []).length
  const styleEnabled = status.value.style_enabled !== false
  const customized = ['profile', 'awareness_mode', 'emotion_mode', 'proactive_preset'].some(
    k => String(status.value[k] || 'custom') !== 'custom',
  )
  return [
    {
      key: 'corpus',
      done: corpusLoaded.value && corpusTotal.value > 0,
      title: '准备语料',
      detail: !corpusLoaded.value
        ? '语料数据读取失败，刷新后可重试'
        : corpusTotal.value > 0
          ? corpusUser.value > 0
            ? `已有 ${corpusTotal.value} 对语料（自己导入 ${corpusUser.value} 对）`
            : `内置 ${corpusTotal.value} 对可用；导入自己的聊天记录会更像你`
          : '还没有可用语料',
      to: '/styles',
      cta: '去导入',
    },
    {
      key: 'style',
      done: !!styleName && styleEnabled,
      title: '启用一套说话风格',
      detail: styleName
        ? styleEnabled
          ? `当前风格：${styleName}（共 ${styleCount} 个）`
          : `风格已配置但未启用：${styleName}`
        : '还没有启用风格',
      to: '/styles',
      cta: '去生成',
    },
    {
      key: 'persona',
      done: customized,
      title: '定下表达基调 / 节奏',
      detail: customized
        ? `当前表达基调：${status.value.profile_label || '自定义'}`
        : '可选：一键表达基调，或按细分开关细调',
      to: '/config?group=persona',
      cta: '去选择',
    },
  ]
})
const onboardingDone = computed(
  () => onboardingSteps.value.filter(s => s.done).length,
)
const onboardingAllDone = computed(
  () => onboardingDone.value === onboardingSteps.value.length,
)
const switchingPersona = ref('')
const pipeline = computed(() => dash.value.inject?.pipeline || [])
const pipelineMax = computed(() =>
  Math.max(1, ...pipeline.value.map((p: any) => Number(p.last_chars) || 0)),
)
function pipeWidth(p: any): string {
  const n = Number(p.last_chars) || 0
  if (!n) return '0%'
  return `${Math.max(3, Math.round((n / pipelineMax.value) * 100))}%`
}
function switchPersona(value: string) {
  if (!value || value === currentProfile.value) return
  const label = PERSONAS.find(p => p.value === value)?.label || value
  dialog.warning({
    title: '切换表达基调',
    content: `将把表达基调切换为「${label}」并立即保存配置。细分开关不会被改写，切回「自定义」即可恢复按细分开关工作。`,
    positiveText: '切换',
    negativeText: '取消',
    onPositiveClick: async () => {
      switchingPersona.value = value
      try {
        const r = await apiPost('config/save', { persona: { preset: value } })
        if (!r || r.ok === false) throw new Error(r?.error || '保存失败')
        message.success(`已切换为「${label}」`)
        await load()
      } catch (e: any) {
        message.error(e?.message || String(e))
      } finally {
        switchingPersona.value = ''
      }
    },
  })
}
const cacheRecent = computed(() => (dash.value.cache?.recent || []).map((v: any) => !!v))

const cards = computed(() => [
  {
    label: '润色去痕',
    value: onoff(status.value.enabled),
    status: status.value.enabled ? 'on' : 'off',
    icon: 'lucide:broom',
    sub: '本地规则清理；不影响风格注入 / 感知 / 主动聊天',
    delay: 0,
    goto: '/config?group=humanize',
  },
  {
    label: '主动聊天',
    value: onoff(status.value.proactive),
    status: status.value.proactive ? 'on' : 'off',
    icon: 'lucide:message-circle',
    delay: 60,
    goto: '/proactive',
  },
  {
    label: '生活状态',
    value: onoff(status.value.life_enabled),
    status: status.value.life_enabled ? 'on' : 'off',
    icon: 'lucide:sunrise',
    delay: 120,
    goto: '/config',
  },
  {
    label: '风格注入',
    value: onoff(status.value.style_enabled),
    status: status.value.style_enabled ? 'on' : 'off',
    icon: 'lucide:sparkles',
    delay: 180,
    goto: '/styles',
  },
  {
    label: '跟踪会话',
    value: String(status.value.tracked_sessions ?? 0),
    icon: 'lucide:users',
    delay: 240,
    goto: '/records',
  },
  {
    label: '可用风格',
    value: String((status.value.styles || []).length),
    icon: 'lucide:library',
    delay: 300,
    goto: '/styles',
  },
  {
    label: '检索缓存命中率',
    value: `${dash.value.cache?.hit_rate ?? 0}%`,
    icon: 'lucide:history',
    sub: `命中 ${dash.value.cache?.hits ?? 0} / 未命中 ${dash.value.cache?.misses ?? 0}`,
    delay: 360,
  },
  {
    label: '注入字符/轮',
    value: String(dash.value.inject?.avg_chars ?? 0),
    icon: 'lucide:file-text',
    sub: `累计 ${dash.value.inject?.total_chars ?? 0} 字符 · 共 ${dash.value.inject?.turns ?? 0} 轮`,
    delay: 420,
  },
])

const rhythm = computed(() => dash.value.rhythm || { mode: 'cold', score: 0 })
const cleanup = computed(() => dash.value.cleanup || [])
const rhythmLabel = computed(() => {
  const m = rhythm.value.mode
  return m === 'hot' ? '热聊 HOT' : m === 'warm' ? '常态 WARM' : '冷场 COLD'
})
const rhythmTagType = computed(() => {
  const m = rhythm.value.mode
  return m === 'hot' ? 'error' : m === 'warm' ? 'success' : 'default'
})
const rhythmScore = computed(() => String(Math.round(Number(rhythm.value.score) || 0)))
const events = computed(() => (dash.value.events || []).slice(0, 10))
const latestEmotion = computed(() => (dash.value.emotions || [])[0] || null)
const emotionLabel = computed(() => {
  const e = latestEmotion.value?.emotion
  return e === 'appy' ? '开心 😊' : e === 'sulky' ? '有点蔫 😞' : '平静'
})

const MODE_LABELS: Record<string, string> = {
  custom: '按细分开关',
  simple: '简化',
  standard: '标准',
  full: '完整',
  reserved: '克制',
  clingy: '黏人',
}
function modeLabel(v: unknown): string {
  const key = String(v || 'custom')
  return MODE_LABELS[key] || key
}
function onoff(v: unknown): string {
  return v ? '开' : '关'
}
function shortUmo(umo: unknown): string {
  return String(umo || '').slice(-8)
}
function fmtTime(ts: unknown): string {
  const d = new Date(Number(ts) * 1000)
  if (isNaN(d.getTime())) return '--:--'
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

async function load() {
  // 审计修正：三个接口相互独立，任一失败（尤其新增的 corpus）不能拖垮整页；
  // 用 allSettled 分别处理，语料失败时向导显示"读取失败"而不是误报"没有语料"。
  const [s, d, c] = await Promise.allSettled([
    apiGet('status'),
    apiGet('dashboard'),
    apiGet('corpus'),
  ])
  try {
    if (s.status === 'fulfilled') {
      const sval: any = s.value
      if (sval && sval.ok) {
        status.value = sval.status || {}
        if (sval.status && sval.status.error) loadError.value = String(sval.status.error)
      } else if (sval && sval.error) {
        loadError.value = String(sval.error)
      }
    } else {
      loadError.value = String((s.reason as any)?.message || s.reason || '状态读取失败')
    }
    if (d.status === 'fulfilled') {
      const dval: any = d.value
      if (dval && dval.ok) dash.value = dval
      else if (dval && dval.error) loadError.value = loadError.value || String(dval.error)
    }
    if (c.status === 'fulfilled' && c.value && (c.value as any).ok) {
      corpus.value = c.value
      corpusLoaded.value = true
    } else {
      corpusLoaded.value = false
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hero {
  position: relative;
  padding: 36px 0 16px;
  /* v4.8.1 自检：光晕是右侧出血装饰，限制在本区块内避免页面横向溢出 */
  overflow: hidden;
}
.hero-glow {
  position: absolute;
  top: -130px;
  right: -90px;
  width: 560px;
  height: 400px;
  border-radius: 50%;
  background: radial-gradient(
    closest-side,
    rgba(164, 85, 43, 0.10),
    rgba(107, 122, 69, 0.06) 55%,
    transparent 100%
  );
  animation: hz-breathe 8s ease-in-out infinite;
  pointer-events: none;
}
.hero-title,
.hero-sub,
.hero-chips {
  position: relative;
}
.hero-title {
  font-family: var(--hz-font-head);
  font-size: 52px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.1;
  margin: 0;
  color: var(--hz-text);
}
.hero-sub {
  font-size: 16.5px;
  color: var(--hz-text-2);
  margin: 16px 0 0;
  max-width: 680px;
  line-height: 1.65;
}
.hero-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 26px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border-radius: var(--hz-radius-pill);
  background: var(--hz-card);
  border: 1px solid var(--hz-hairline);
  font-size: 13px;
  color: var(--hz-text-2);
  transition: border-color 0.25s var(--hz-ease), color 0.25s var(--hz-ease);
}
.chip:hover {
  border-color: rgba(164, 85, 43, 0.35);
  color: var(--hz-text);
}
.chip-warn {
  border-color: rgba(152, 70, 31, 0.42);
  color: var(--hz-pink);
  background: var(--hz-pink-soft);
}
.chip-link {
  text-decoration: none;
}
.onboarding :deep(.n-card__content) {
  padding-top: 12px;
}
.onb-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-family: var(--hz-font-head);
  font-size: 20px;
  font-weight: 600;
  color: var(--hz-text);
}
.onb-progress {
  font-family: var(--hz-font-body, inherit);
  font-size: 12.5px;
  font-weight: 500;
  color: var(--hz-text-3);
  border: 1px solid var(--hz-hairline);
  border-radius: 999px;
  padding: 3px 10px;
  white-space: nowrap;
}
.onb-progress.done {
  color: var(--hz-green, #5d7a3a);
  border-color: rgba(93, 122, 58, 0.35);
  background: rgba(93, 122, 58, 0.08);
}
.onb-steps {
  list-style: none;
  margin: 14px 0 16px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.onb-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.onb-check {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  border-radius: 50%;
  border: 1px solid var(--hz-hairline);
  font-size: 11px;
  color: var(--hz-text-3);
  background: var(--hz-card-2);
}
.onb-step.done .onb-check {
  color: #fff;
  border-color: transparent;
  background: var(--hz-green, #5d7a3a);
}
.onb-copy {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.onb-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--hz-text);
}
.onb-step.done .onb-title {
  color: var(--hz-text-2);
}
.onb-detail {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--hz-text-3);
}
.onb-link {
  flex: 0 0 auto;
  text-decoration: none;
}
.onb-badge {
  flex: 0 0 auto;
  font-size: 11.5px;
  color: var(--hz-green, #5d7a3a);
  white-space: nowrap;
}
.onb-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
/* v4.8.2：人格快捷切换 */
.persona-hint {
  margin: 0 0 12px;
}
.persona-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.persona-current {
  margin-left: 4px;
  font-size: 12.5px;
  color: var(--hz-text-2);
}
/* v4.8.2：注入管线构成 */
.pipe-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pipe-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pipe-label {
  flex: 0 0 76px;
  font-size: 12.5px;
  color: var(--hz-text-2);
}
.pipe-track {
  flex: 1 1 auto;
  height: 10px;
  border-radius: 999px;
  background: var(--hz-card-2);
  overflow: hidden;
}
.pipe-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--hz-accent, #98461f);
  transition: width 0.4s var(--hz-ease);
}
.pipe-num {
  flex: 0 0 58px;
  text-align: right;
  font-size: 12px;
  color: var(--hz-text-3);
}
.chip .iconify {
  color: var(--hz-pink);
}
.dim {
  font-size: 13px;
  color: var(--hz-text-2);
}
.trend-hint {
  margin: 0;
  font-size: 12px;
}
.viz-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.viz-score {
  font-size: 26px;
  font-weight: 700;
  color: var(--hz-text);
  font-variant-numeric: tabular-nums;
}
.viz-hint {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--hz-text-3);
}
.event-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid var(--hz-hairline);
  font-size: 13px;
}
.event-row:last-child {
  border-bottom: none;
}
.event-time {
  color: var(--hz-text-3);
  font-family: var(--hz-mono, monospace);
  font-size: 12px;
}
.event-msg {
  color: var(--hz-text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
