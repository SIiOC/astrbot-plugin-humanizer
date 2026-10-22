<template>
  <div
    class="stat-card hz-lift hz-reveal"
    :class="{ clickable: !!goto }"
    :style="delay ? { animationDelay: delay + 'ms' } : undefined"
    @click="go"
  >
    <div class="stat-top">
      <span v-if="status" class="hz-dot" :class="status"></span>
      <Icon v-if="icon" :icon="icon" class="stat-icon" />
      <span class="stat-k">{{ label }}</span>
      <Icon v-if="goto" icon="lucide:arrow-up-right" class="stat-goto" />
    </div>
    <div class="stat-v">{{ display }}</div>
    <div v-if="sub" class="stat-sub">{{ sub }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, type PropType } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useCountUp } from '@/composables/useCountUp'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  sub: { type: String, default: '' },
  icon: { type: String, default: '' },
  /** 值的运行状态：on 绿色呼吸点 / off 静止暗点（仅状态类卡片传） */
  status: { type: String as PropType<'on' | 'off'>, default: '' },
  /** 入场瀑布延迟（毫秒） */
  delay: { type: Number, default: 0 },
  /** 可点击跳转的路由（v4.1.4：总览卡片直达对应页面） */
  goto: { type: String, default: '' },
})

const router = useRouter()
const display = useCountUp(computed(() => props.value))

function go() {
  if (props.goto) router.push(props.goto)
}
</script>

<style scoped>
/* Moonshot 式面板：亮一档深灰、无边框阴影、灰阶图标 + 大号白数字 */
.stat-card {
  box-sizing: border-box;
  background: var(--hz-card);
  border: 1px solid rgba(255, 255, 255, 0.055);
  border-radius: var(--hz-radius-card);
  padding: 22px 24px;
  min-height: 108px;
  height: 100%;
  position: relative;
  transition: border-color 0.22s var(--hz-ease), transform 0.22s var(--hz-ease);
}
.stat-card.clickable {
  cursor: pointer;
}
.stat-card.clickable:hover {
  border-color: rgba(255, 110, 199, 0.32);
  transform: translateY(-2px);
}
.stat-goto {
  margin-left: auto;
  font-size: 14px;
  color: var(--hz-text-3);
  opacity: 0;
  transition: opacity 0.2s var(--hz-ease), color 0.2s var(--hz-ease);
}
.stat-card.clickable:hover .stat-goto {
  opacity: 1;
  color: var(--hz-pink);
}
.stat-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.stat-icon {
  font-size: 16px;
  color: var(--hz-text-3);
}
.stat-k {
  font-size: 13px;
  color: var(--hz-text-2);
}
.stat-v {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.15;
  margin-top: 14px;
  color: var(--hz-text);
  word-break: break-all;
  font-variant-numeric: tabular-nums;
}
.stat-sub {
  font-size: 12px;
  color: var(--hz-text-3);
  margin-top: 6px;
  word-break: break-all;
  line-height: 1.5;
}
</style>
