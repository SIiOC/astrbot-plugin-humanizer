/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
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
