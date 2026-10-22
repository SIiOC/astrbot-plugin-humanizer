<template>
  <n-spin :show="loading">
    <template v-if="!loading">
      <n-alert v-if="loadError" type="error" class="mb-4" :bordered="false">
        主动聊天状态读取失败：{{ loadError }}（下表可能为空，不代表没有跟踪会话）
      </n-alert>

      <n-alert v-if="!enabled" type="warning" class="mb-4" :bordered="false">
        主动聊天未启用（「配置」页「主动聊天」分组的开关未开启）。开启后，聊过的会话才会在静默后触发主动消息。
      </n-alert>

      <div class="hz-section">
        <n-card title="会话触发状态">
          <n-data-table
            :columns="columns"
            :data="rows"
            :bordered="false"
            size="small"
          />
          <n-empty v-if="!rows.length" description="暂无跟踪中的会话（聊过且未超 24 小时活动）" size="small" class="mt-4" />
        </n-card>
      </div>

      <div class="hz-section">
        <n-card title="策略说明">
          <p class="note">
            触发：用户最后消息后 {{ silence }}±{{ fluctuation }} 分钟（下限 30）→ 触发主动消息并随机重排。
            勿扰：{{ quiet || '不限制' }} 内不发送；到期触发会重排到勿扰结束 + 宽限 {{ grace }} 分钟。
            活跃时段：{{ active || '不限制' }} 之外到期会重排到下一窗口起点。
            会话白名单：{{ allowlistText }}。
            连续未回复上限：{{ maxUnansweredText }}。
            未回复间隔放大：{{ scaleText }}。
            未回复小情绪：{{ pout ? '开启' : '关闭' }}（连续未回复时逐次递进语气，用户回复即恢复）。
          </p>
        </n-card>
      </div>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { DataTableColumns } from 'naive-ui'
import { NAlert, NCard, NDataTable, NEmpty, NSpin } from 'naive-ui'
import { useBridge } from '@/composables/useBridge'

const { apiGet } = useBridge()
const loading = ref(true)
const state = ref<any>({})
const loadError = ref('')

const enabled = computed(() => !!state.value.enabled)
const silence = computed(() => state.value.silence_after_minutes ?? 45)
const fluctuation = computed(() => state.value.silence_fluctuation_minutes ?? 15)
const quiet = computed(() => state.value.quiet_hours || '')
const grace = computed(() => state.value.quiet_grace_minutes ?? 5)
const pout = computed(() => !!state.value.pout_on_unanswered)
const rows = computed(() => state.value.sessions || [])
const active = computed(() => state.value.active_hours || '')
const allowlist = computed<string[]>(() => state.value.session_allowlist || [])
const allowlistText = computed(() =>
  allowlist.value.length ? `${allowlist.value.length} 个会话（窗口外不发送）` : '不限制（所有会话）',
)
const maxUnanswered = computed(() => Number(state.value.max_unanswered ?? 6))
const maxUnansweredText = computed(() =>
  maxUnanswered.value > 0
    ? `${maxUnanswered.value} 条（达到后暂停该会话，用户再发言自动恢复）`
    : '不限制',
)
const scaleText = computed(() => {
  if (!state.value.silence_scale_enable) return '关闭'
  const step = Number(state.value.silence_scale_step ?? 0.3)
  const cap = Number(state.value.silence_scale_cap_minutes ?? 240)
  return `开启（每次 +${Math.round(step * 100)}%，封顶 ${cap} 分钟）`
})

const columns: DataTableColumns<any> = [
  { title: '会话', key: 'umo', ellipsis: { tooltip: true } },
  { title: '状态', key: 'status', width: 110 },
  { title: '暂停原因', key: 'paused_reason', width: 170 },
  { title: '下次触发', key: 'next_trigger', width: 170 },
  { title: '未回复', key: 'unanswered', width: 70 },
  { title: '用户静默', key: 'silence_hours', width: 90 },
]

onMounted(async () => {
  try {
    const res: any = await apiGet('proactive')
    if (!res || !res.ok) throw new Error((res && res.error) || '状态读取失败')
    state.value = res
  } catch (e: any) {
    loadError.value = e?.message || String(e)
    console.error('主动聊天状态读取失败:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.mb-4 {
  margin-bottom: 20px;
}
.mt-4 {
  margin-top: 20px;
}
.note {
  font-size: 14px;
  color: var(--hz-text-2);
  line-height: 1.75;
  margin: 0;
}
</style>
