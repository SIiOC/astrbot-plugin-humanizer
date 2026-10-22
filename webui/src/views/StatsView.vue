<template>
  <n-spin :show="loading">
    <template v-if="!loading">
      <n-grid :cols="3" responsive="screen" item-responsive :x-gap="16" :y-gap="24">
        <n-grid-item span="3 s:2 m:1" v-for="(s, i) in stats" :key="s.label">
          <StatCard v-bind="s" :delay="i * 60" />
        </n-grid-item>
      </n-grid>

      <n-alert v-if="loadError" type="error" :bordered="false" class="hz-section stats-hint">
        统计读取失败：{{ loadError }}（下列计数器按 0 显示，不代表真实值）
      </n-alert>
      <n-alert v-else type="info" :bordered="false" class="hz-section hz-reveal stats-hint" style="animation-delay: 480ms">
        统计自本版本起开始累计（v2.8）。历史数据不追溯；计数器持久化在插件数据目录 stats.json。
      </n-alert>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NAlert, NGrid, NGridItem, NSpin } from 'naive-ui'
import StatCard from '@/components/StatCard.vue'
import { useBridge } from '@/composables/useBridge'

const { apiGet } = useBridge()
const loading = ref(true)
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
])

onMounted(async () => {
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
})
</script>

<style scoped>
.stats-hint {
  margin-top: 20px;
}
</style>
