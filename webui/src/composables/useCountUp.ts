import { onUnmounted, ref, watch, type Ref } from 'vue'

/**
 * 数字滚动动画：源值是纯数字（可含千分位/小数）时从 0 缓动滚到目标值，
 * 非数字文本（开/关、模型名等）原样展示。尊重系统"减少动态效果"设置。
 */
export function useCountUp(source: Ref<string>, duration = 900) {
  const display = ref(source.value)
  let raf = 0
  onUnmounted(() => cancelAnimationFrame(raf))

  function animateTo(target: number, decimals: number) {
    cancelAnimationFrame(raf)
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      display.value = source.value
      return
    }
    const start = performance.now()
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      display.value = (target * eased).toFixed(decimals)
      if (p < 1) raf = requestAnimationFrame(step)
      else display.value = source.value
    }
    raf = requestAnimationFrame(step)
  }

  watch(
    source,
    v => {
      const m = /^\s*(\d[\d,]*(?:\.\d+)?)\s*$/.exec(v ?? '')
      if (!m) {
        cancelAnimationFrame(raf)
        display.value = v
        return
      }
      const raw = m[1].replace(/,/g, '')
      const decimals = raw.includes('.') ? raw.split('.')[1].length : 0
      animateTo(parseFloat(raw), decimals)
    },
    { immediate: true },
  )

  return display
}
