<template>
  <n-spin :show="loading">
    <template v-if="!loading">
      <n-grid :cols="4" responsive="screen" item-responsive :x-gap="16" :y-gap="24">
        <n-grid-item span="4 s:2 m:1" v-for="(s, i) in stats" :key="s.label">
          <StatCard v-bind="s" :delay="i * 25" />
        </n-grid-item>
      </n-grid>

      <n-alert v-if="loadError" type="error" :bordered="false" class="hz-section stats-hint">
        统计读取失败：{{ loadError }}（下列计数器按 0 显示，不代表真实值）
      </n-alert>
      <template v-else>
        <div class="stats-actions">
          <n-button size="small" tertiary :loading="resetting" @click="confirmReset">
            重置计数
          </n-button>
        </div>
        <n-alert type="info" :bordered="false" class="hz-section hz-reveal stats-hint" style="animation-delay: 480ms">
          统计自本版本起开始累计（v2.8）。历史数据不追溯；计数器持久化在插件数据目录 stats.json，重置后立即写盘。
        </n-alert>
      </template>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NAlert, NButton, NGrid, NGridItem, NSpin, useDialog, useMessage } from 'naive-ui'
import StatCard from '@/components/StatCard.vue'
import { useBridge } from '@/composables/useBridge'

const { apiGet, apiPost } = useBridge()
const dialog = useDialog()
const message = useMessage()
const loading = ref(true)
const resetting = ref(false)
const statsData = ref<any>({})
const loadError = ref('')

const stats = computed(() => [
  { label: '规则清理命中', value: String(statsData.value.rules_hit ?? 0), icon: 'lucide:broom', tone: 'blue' },
  { label: '主动消息已发送', value: String(statsData.value.proactive_sent ?? 0), icon: 'lucide:send', tone: 'pink' },
  { label: '风格提炼', value: String(statsData.value.style_built ?? 0), icon: 'lucide:sparkles', tone: 'amber' },
  { label: '主动让位', value: String(statsData.value.proactive_interject_dropped ?? 0), icon: 'lucide:hand', tone: 'orange', sub: '生成期间用户发言，本次不发送' },
  { label: '质检命中消息', value: String(statsData.value.qc_hits ?? 0), icon: 'lucide:scan-search', tone: 'violet', sub: '命中至少一条规则的消息数（仅记录）' },
  { label: '质检检查消息', value: String(statsData.value.qc_checked ?? 0), icon: 'lucide:clipboard-check', tone: 'teal', sub: '执行过质检的消息数' },
  { label: '分段发送', value: String(statsData.value.split_sent ?? 0), icon: 'lucide:split', tone: 'cyan' },
  { label: '打字延迟生效', value: String(statsData.value.typing_delay_applied ?? 0), icon: 'lucide:keyboard', tone: 'green' },
  { label: '防抖合并', value: String(statsData.value.debounce_merged ?? 0), icon: 'lucide:layers', tone: 'indigo' },
  { label: '质检命中规则', value: String(statsData.value.qc_rule_hits ?? 0), icon: 'lucide:scan-search', tone: 'violet', sub: '命中规则条数（一条消息可中多条）' },
  { label: '主动失败', value: String(statsData.value.proactive_failed ?? 0), icon: 'lucide:power', tone: 'orange', sub: '生成/发送被放弃的次数' },
  { label: '主动超时', value: String(statsData.value.proactive_timeout ?? 0), icon: 'lucide:clock', tone: 'teal', sub: '生成超时放弃的次数' },
])

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res: any = await apiGet('stats')
    if (res && res.ok) statsData.value = res.stats || {}
    else loadError.value = (res && res.error) || '后端未返回有效数据'
  } catch (e: any) {
    loadError.value = e?.message || String(e)
    console.error('统计读取失败:', e)
  } finally {
    loading.value = false
  }
}

function confirmReset() {
  dialog.warning({
    title: '重置统计计数',
    content: '将把全部统计计数器清零并立即写入 stats.json。历史累计数据无法恢复，确定继续？',
    positiveText: '重置',
    negativeText: '取消',
    onPositiveClick: async () => {
      resetting.value = true
      try {
        const res: any = await apiPost('stats/reset', {})
        if (res && res.ok) {
          message.success('统计计数已重置')
          await load()
        } else {
          message.error('重置失败: ' + ((res && res.error) || '未知错误'))
        }
      } catch (e: any) {
        message.error('重置失败: ' + (e?.message || String(e)))
      } finally {
        resetting.value = false
      }
    },
  })
}

onMounted(load)
</script>

<style scoped>
.stats-hint {
  margin-top: 12px;
}
.stats-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}
/* v4.8.1 自检：网格子项默认 min-width:auto，窄屏会把页面撑宽 */
:deep(.n-grid-item) {
  min-width: 0;
}
@media (max-width: 640px) {
  .stats-actions {
    justify-content: flex-start;
  }
}
</style>
