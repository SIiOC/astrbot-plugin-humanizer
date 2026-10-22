<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="moonshotOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <header class="hz-nav">
          <div class="hz-nav-inner">
            <router-link to="/" class="brand">
              <span class="brand-tile">
                <Icon icon="lucide:heart" style="font-size: 15px" />
              </span>
              <span class="brand-text">好想成为人类啊</span>
            </router-link>
            <nav class="hz-menu">
              <router-link
                v-for="item in navItems"
                :key="item.path"
                :to="item.path"
                class="nav-item"
                :class="{ active: item.path === route.path }"
              >
                <Icon :icon="item.icon || 'lucide:dot'" class="nav-icon" />
                <span>{{ item.title }}</span>
              </router-link>
            </nav>
          </div>
        </header>

        <main class="hz-main">
          <div v-if="route.name !== 'overview'" class="page-head">
            <h1 class="page-title">{{ currentTitle }}</h1>
            <p v-if="currentSubtitle" class="page-sub">{{ currentSubtitle }}</p>
          </div>
          <router-view v-slot="{ Component }">
            <transition name="page" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
          <footer class="hz-footer">好想成为人类啊 · AstrBot Humanizer 控制台</footer>
        </main>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import type { GlobalThemeOverrides } from 'naive-ui'
import {
  NConfigProvider,
  NDialogProvider,
  NMessageProvider,
  darkTheme,
  dateZhCN,
  zhCN,
} from 'naive-ui'
import { Icon } from '@iconify/vue'
import { routes } from '@/router'
import { useBridge } from '@/composables/useBridge'

const route = useRoute()
const { init } = useBridge()

const navItems = routes
  .filter(r => r.meta?.title)
  .map(r => ({
    path: r.path,
    title: r.meta!.title as string,
    icon: (r.meta?.icon as string) || 'lucide:dot',
  }))

const currentTitle = computed(() => (route.meta?.title as string) || '')
const currentSubtitle = computed(() => (route.meta?.subtitle as string) || '')

// v3.1 Moonshot 式暗色主题：纯黑底 × 深灰面板 × 明度分层文字。
// 品牌粉只做点缀（按钮/选中/开关）；组件质感由 tokens.css 统一。
const moonshotOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#c93a86',
    primaryColorHover: '#d94fa0',
    primaryColorPressed: '#b02e73',
    primaryColorSuppl: '#c93a86',
    infoColor: '#5ea0ff',
    infoColorHover: '#7fb3ff',
    infoColorPressed: '#4a86e0',
    successColor: '#34c77b',
    successColorHover: '#4fd58e',
    successColorPressed: '#28a765',
    warningColor: '#f5a623',
    warningColorHover: '#ffbb47',
    warningColorPressed: '#d18b12',
    errorColor: '#ff5d5d',
    errorColorHover: '#ff7a7a',
    errorColorPressed: '#e04848',
    bodyColor: '#0a0a0a',
    cardColor: '#161616',
    modalColor: '#1a1a1a',
    popoverColor: '#1e1e1e',
    textColorBase: '#f2f2f4',
    textColor1: '#f2f2f4',
    textColor2: '#b9b9bf',
    textColor3: '#7a7a80',
    placeholderColor: '#5a5a60',
    dividerColor: 'rgba(255, 255, 255, 0.07)',
    borderColor: 'rgba(255, 255, 255, 0.12)',
    borderRadius: '12px',
    borderRadiusSmall: '8px',
    fontWeightStrong: '700',
    boxShadow1: '0 4px 16px rgba(0, 0, 0, 0.4)',
    boxShadow2: '0 8px 28px rgba(0, 0, 0, 0.5)',
    boxShadow3: '0 16px 44px rgba(0, 0, 0, 0.6)',
  },
  Card: {
    borderRadius: '20px',
    color: '#161616',
    colorEmbedded: '#1c1c1c',
    titleFontWeightMedium: '600',
    titleFontSizeMedium: '17px',
    borderColor: 'rgba(255, 255, 255, 0.055)',
  },
  Button: {
    borderRadius: '9999px',
    borderRadiusSmall: '9999px',
    borderRadiusLarge: '9999px',
    fontWeight: '500',
  },
  Input: {
    borderRadius: '12px',
    color: '#141414',
    colorDisabled: '#101010',
    border: '1px solid rgba(255, 255, 255, 0.14)',
    borderHover: '1px solid rgba(255, 255, 255, 0.26)',
    borderFocus: '1px solid #ff6ec7',
    borderActive: '1px solid #ff6ec7',
    borderSelected: '1px solid #ff6ec7',
    boxShadowFocus: '0 0 0 3px rgba(255, 110, 199, 0.12)',
    placeholderColor: '#5a5a60',
  },
  Select: {
    peers: {
      InternalSelection: {
        borderRadius: '12px',
        color: '#141414',
        border: '1px solid rgba(255, 255, 255, 0.14)',
        borderHover: '1px solid rgba(255, 255, 255, 0.26)',
        borderActive: '1px solid #ff6ec7',
        borderFocus: '1px solid #ff6ec7',
      },
    },
  },
  DataTable: {
    thColor: '#121212',
    thTextColor: '#8a8a8f',
    thFontWeight: '600',
    tdColor: '#161616',
    tdColorHover: 'rgba(255, 255, 255, 0.04)',
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
  Tag: { borderRadius: '9999px' },
  Tabs: {
    barColor: '#ff6ec7',
    tabTextColorLine: '#9a9a9f',
    tabTextColorActiveLine: '#f2f2f4',
    tabTextColorHoverLine: '#f2f2f4',
    tabFontMedium: '15px',
    tabFontWeightActive: '600',
  },
  Form: {
    labelTextColor: '#f2f2f4',
    labelFontWeight: '500',
  },
  Switch: {
    railColorActive: '#c93a86',
  },
  Popover: { borderRadius: '14px' },
  Modal: { borderRadius: '20px' },
  Tooltip: { borderRadius: '10px' },
}

onMounted(async () => {
  await init()
})
</script>

<style scoped>
/* ===== 顶部导航（Moonshot 式：黑底毛玻璃、纯文字、小字号） ===== */
.hz-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(10, 10, 10, 0.72);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  backdrop-filter: blur(20px) saturate(140%);
  border-bottom: 1px solid var(--hz-hairline);
}

.hz-nav-inner {
  max-width: var(--hz-content-w);
  margin: 0 auto;
  height: var(--hz-nav-h);
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  flex-shrink: 0;
}

.brand-tile {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background: var(--hz-pink-solid);
  color: #fff;
}

.brand-text {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--hz-text);
  white-space: nowrap;
  letter-spacing: 0.01em;
}

.hz-menu {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: none;
}
.hz-menu::-webkit-scrollbar {
  display: none;
}

/* 纯文字导航：层级靠明度，选中态白字 + 极淡面板 */
.nav-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--hz-radius-pill);
  font-size: 13.5px;
  color: var(--hz-text-2);
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.2s var(--hz-ease), background 0.2s var(--hz-ease);
}
.nav-item:hover {
  color: var(--hz-text);
}
.nav-item.active {
  color: var(--hz-text);
  font-weight: 600;
  background: rgba(255, 255, 255, 0.08);
}
.nav-icon {
  font-size: 14px;
  color: var(--hz-text-3);
  transition: color 0.2s var(--hz-ease);
}
.nav-item:hover .nav-icon,
.nav-item.active .nav-icon {
  color: var(--hz-pink);
}

/* ===== 内容区：居中定宽 + 大留白 ===== */
.hz-main {
  max-width: var(--hz-content-w);
  margin: 0 auto;
  padding: 40px 24px 72px;
  min-height: calc(100vh - var(--hz-nav-h));
  display: flex;
  flex-direction: column;
}

.page-head {
  margin-bottom: 32px;
}

.page-title {
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.03em;
  margin: 0;
  color: var(--hz-text);
}

.page-sub {
  font-size: 15px;
  color: var(--hz-text-2);
  margin: 10px 0 0;
  max-width: 640px;
  line-height: 1.65;
}

.hz-footer {
  margin-top: auto;
  padding-top: 64px;
  text-align: center;
  font-size: 12px;
  color: var(--hz-text-3);
}

/* 页面切换：淡入 + 轻微上移 */
.page-enter-active,
.page-leave-active {
  transition: opacity 0.22s var(--hz-ease), transform 0.22s var(--hz-ease);
}
.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-leave-to {
  opacity: 0;
}
</style>
