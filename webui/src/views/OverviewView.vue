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
          <span class="chip">
            <Icon icon="lucide:badge-check" style="font-size: 14px" />
            当前风格：{{ status.active_style || '未启用' }}
          </span>
          <span class="chip">
            <Icon icon="lucide:message-circle" style="font-size: 14px" />
            主动聊天：{{ status.proactive ? '开' : '关' }}
          </span>
          <span class="chip">
            <Icon icon="lucide:sunrise" style="font-size: 14px" />
            生活状态：{{ status.life_enabled ? '开' : '关' }}
          </span>
          <span class="chip" title="时间感知档位">
            <Icon icon="lucide:clock" style="font-size: 14px" />
            时间：{{ modeLabel(status.awareness_mode) }}
          </span>
          <span class="chip" title="情绪机制档位">
            <Icon icon="lucide:heart" style="font-size: 14px" />
            情绪：{{ modeLabel(status.emotion_mode) }}
          </span>
          <span class="chip" title="主动聊天预设">
            <Icon icon="lucide:message-circle" style="font-size: 14px" />
            主动：{{ modeLabel(status.proactive_preset) }}
          </span>
        </div>
      </section>

      <!-- 状态瓷贴（瀑布入场 + 开关呼吸点） -->
      <section class="hz-section">
        <n-grid :cols="3" responsive="screen" item-responsive :x-gap="16" :y-gap="16">
          <n-grid-item span="3 s:2 m:1" v-for="card in cards" :key="card.label">
            <StatCard v-bind="card" />
          </n-grid-item>
        </n-grid>
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
        </n-grid>
      </section>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NAlert,
  NCard,
  NGrid,
  NGridItem,
  NSpace,
  NSpin,
  NTag,
} from 'naive-ui'
import { Icon } from '@iconify/vue'
import StatCard from '@/components/StatCard.vue'
import { useBridge } from '@/composables/useBridge'

const { apiGet } = useBridge()
const loading = ref(true)
const status = ref<any>({})
const dash = ref<any>({})
const loadError = ref('')

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
])

const rhythm = computed(() => dash.value.rhythm || { mode: 'cold', score: 0 })
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

onMounted(async () => {
  try {
    const [s, d] = await Promise.all([apiGet('status'), apiGet('dashboard')])
    if (s && s.ok) {
      status.value = s.status || {}
      if (s.status && s.status.error) loadError.value = String(s.status.error)
    } else if (s && s.error) {
      loadError.value = String(s.error)
    }
    if (d && d.ok) dash.value = d
    else if (d && d.error) loadError.value = loadError.value || String(d.error)
  } catch (e: any) {
    loadError.value = e?.message || String(e)
    console.error('加载总览失败:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.hero {
  position: relative;
  padding: 36px 0 16px;
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
    rgba(255, 110, 199, 0.06),
    rgba(94, 160, 255, 0.035) 55%,
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
  font-size: 52px;
  font-weight: 700;
  letter-spacing: -0.035em;
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
  border: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 13px;
  color: var(--hz-text-2);
  transition: border-color 0.25s var(--hz-ease), color 0.25s var(--hz-ease);
}
.chip:hover {
  border-color: rgba(255, 110, 199, 0.3);
  color: var(--hz-text);
}
.chip .iconify {
  color: var(--hz-pink);
}
.dim {
  font-size: 13px;
  color: var(--hz-text-2);
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
