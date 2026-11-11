/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// 本项目仅在 Vite 配置中使用 Node URL 的这两个导出。
declare module 'node:url' {
  export function fileURLToPath(url: string | URL): string
  export const URL: typeof globalThis.URL
}

// AstrBot 插件页桥（由宿主注入）——协议见 useBridge.ts
interface AstrBotPluginPageBridge {
  ready(): Promise<unknown>
  apiGet(path: string, params?: Record<string, unknown>): Promise<any>
  apiPost(path: string, body?: unknown): Promise<any>
  upload(path: string, file: File): Promise<any>
  download(
    path: string,
    params?: Record<string, unknown>,
    filename?: string,
  ): Promise<void>
}

interface Window {
  AstrBotPluginPage?: AstrBotPluginPageBridge
}
