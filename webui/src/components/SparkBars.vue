<template>
  <div class="spark" role="img" :aria-label="aria">
    <span
      v-for="(v, i) in nums"
      :key="i"
      class="spark-bar"
      :style="{ height: height(v), background: color(v) }"
      :title="title(v)"
    ></span>
  </div>
  <p v-if="!nums.length" class="spark-empty">暂无数据，产生一次回复后出现</p>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  values: (number | boolean)[]
  hitMode?: boolean
}>()

const nums = computed(() =>
  (props.values || []).map((v) => (typeof v === 'boolean' ? (v ? 1 : 0) : Number(v) || 0)),
)
const max = computed(() => Math.max(1, ...nums.value))
const aria = computed(() => (props.hitMode ? '最近检索缓存命中序列' : '最近注入字符趋势'))

function height(v: number): string {
  if (props.hitMode) return v > 0 ? '100%' : '32%'
  return Math.max(8, Math.round((v / max.value) * 100)) + '%'
}

function color(v: number): string {
  if (!props.hitMode) return 'var(--hz-pink)'
  return v > 0 ? 'var(--hz-olive)' : 'rgba(76, 54, 30, 0.16)'
}

function title(v: number): string {
  return props.hitMode ? (v > 0 ? '命中' : '未命中') : `${v} 字符`
}
</script>

<style scoped>
.spark {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 46px;
  margin: 6px 0 4px;
}
.spark-bar {
  flex: 1;
  min-width: 2px;
  border-radius: 3px 3px 1px 1px;
  transition: height 0.3s var(--hz-ease);
}
.spark-empty {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--hz-text-3);
}
</style>
