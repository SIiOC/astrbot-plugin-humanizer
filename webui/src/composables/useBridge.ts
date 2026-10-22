/**
 * AstrBot 插件页桥接（从 v4.0.x 构建产物反推，协议与宿主 dashboard 一致）。
 *
 * 宿主在 iframe 里注入 `window.AstrBotPluginPage`，提供 ready/apiGet/apiPost/
 * upload/download 五个方法；在浏览器里直接打开开发服务器时没有该对象，
 * 回落到同源的 `/api/plug/<插件名>/<路由>`（需要 AstrBot 正在运行且已登录）。
 */

export const PLUGIN_NAME = 'astrbot_plugin_wanna_be_human'

let inited = false
let readyPromise: Promise<unknown> | null = null

function getBridge(): AstrBotPluginPageBridge | null {
  if (typeof window === 'undefined') return null
  return window.AstrBotPluginPage ?? null
}

export function useBridge() {
  const bridge = getBridge()

  async function init(): Promise<unknown> {
    if (inited && readyPromise) return readyPromise
    if (!bridge) {
      console.warn('[Bridge] AstrBotPluginPage 不可用，可能在独立开发模式下运行')
      return null
    }
    try {
      readyPromise = await bridge.ready()
      inited = true
      return readyPromise
    } catch (e) {
      console.error('[Bridge] 初始化失败:', e)
      return null
    }
  }

  async function apiGet(
    path: string,
    params?: Record<string, unknown>,
  ): Promise<any> {
    if (bridge) return bridge.apiGet(path, params)
    const url = new URL(`/api/plug/${PLUGIN_NAME}/${path}`, window.location.origin)
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== null && v !== undefined) url.searchParams.set(k, String(v))
      })
    }
    return (await fetch(url.toString())).json()
  }

  async function apiPost(path: string, body?: unknown): Promise<any> {
    if (bridge) return bridge.apiPost(path, body)
    const res = await fetch(`/api/plug/${PLUGIN_NAME}/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    })
    return res.json()
  }

  async function upload(path: string, file: File): Promise<any> {
    if (bridge) return bridge.upload(path, file)
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`/api/plug/${PLUGIN_NAME}/${path}`, {
      method: 'POST',
      body: form,
    })
    return res.json()
  }

  async function download(
    path: string,
    params?: Record<string, unknown>,
    filename = 'download.json',
  ): Promise<void> {
    if (bridge) {
      await bridge.download(path, params, filename)
      return
    }
    const url = new URL(`/api/plug/${PLUGIN_NAME}/${path}`, window.location.origin)
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== null && v !== undefined) url.searchParams.set(k, String(v))
      })
    }
    const blob = await (await fetch(url.toString())).blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return { init, apiGet, apiPost, upload, download }
}
