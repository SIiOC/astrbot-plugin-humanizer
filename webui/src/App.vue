<template>
  <n-config-provider
    :theme="themeMode === 'night' ? darkTheme : null"
    :theme-overrides="activeOverrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
  >
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
              <div v-for="group in navGroups" :key="group.name" class="nav-group">
                <span class="nav-group-label">{{ group.name }}</span>
                <router-link
                  v-for="item in group.items"
                  :key="item.path"
                  :to="item.path"
                  class="nav-item"
                  :class="{ active: item.path === route.path }"
                >
                  <Icon :icon="item.icon || 'lucide:dot'" class="nav-icon" />
                  <span>{{ item.title }}</span>
                </router-link>
              </div>
            </nav>
            <button
              class="theme-toggle"
              type="button"
              :title="themeMode === 'night' ? '切换到日间（暖沙）' : '切换到夜间（暖沙·夜）'"
              @click="toggleTheme"
            >
              {{ themeMode === 'night' ? '日间' : '夜间' }}
            </button>
          </div>
        </header>

        <main class="hz-main">
          <div v-if="route.name !== 'overview'" class="page-head">
            <h1 class="page-title">{{ currentTitle }}</h1>
            <p v-if="currentSubtitle" class="page-sub">{{ currentSubtitle }}</p>
          </div>
          <div v-if="routeLoading" class="route-loading">
            <span>页面加载中…</span>
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
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
const router = useRouter()
const { init } = useBridge()

// v4.8.0 审计修正：懒加载 chunk 拉取期间的轻量提示。
// 不用 Suspense（与 transition/out-in 组合会触发 insertBefore DOM 错误），
// 改为路由钩子 + 120ms 延迟，避免快 chunk 闪烁。
const routeLoading = ref(false)
let routeLoadingTimer: ReturnType<typeof setTimeout> | null = null
router.beforeEach(() => {
  if (routeLoadingTimer) clearTimeout(routeLoadingTimer)
  routeLoadingTimer = setTimeout(() => {
    routeLoading.value = true
  }, 120)
})
router.afterEach(() => {
  if (routeLoadingTimer) {
    clearTimeout(routeLoadingTimer)
    routeLoadingTimer = null
  }
  routeLoading.value = false
})

const navItems = routes
  .filter(r => r.meta?.title)
  .map(r => ({
    path: r.path,
    title: r.meta!.title as string,
    icon: (r.meta?.icon as string) || 'lucide:dot',
    group: (r.meta?.group as string) || '其他',
  }))

// v4.8.0：导航按「用户任务」分组，路由与后端 API 完全不变。
const NAV_GROUPS = ['像个人', '别被识破', '主动找人', '调校排障']
const navGroups = NAV_GROUPS.map(name => ({
  name,
  items: navItems.filter(item => item.group === name),
})).filter(group => group.items.length > 0)

const currentTitle = computed(() => (route.meta?.title as string) || '')
const currentSubtitle = computed(() => (route.meta?.subtitle as string) || '')

// v4.5.0 暖沙大地色（Warm Sand）：米棕纸面 × 奶白面板 × 赭石强调 × 衬线标题。
// 亮色主题（不传 darkTheme），组件质感由 tokens.css 统一。
const moonshotOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#98461f',
    primaryColorHover: '#b05a2c',
    primaryColorPressed: '#7d3817',
    primaryColorSuppl: '#98461f',
    infoColor: '#6b7a45',
    infoColorHover: '#7f8f55',
    infoColorPressed: '#59683a',
    successColor: '#6b7a45',
    successColorHover: '#7f8f55',
    successColorPressed: '#59683a',
    warningColor: '#b7791f',
    warningColorHover: '#cd8d2e',
    warningColorPressed: '#96620f',
    errorColor: '#b23a2b',
    errorColorHover: '#c74b3b',
    errorColorPressed: '#932d20',
    bodyColor: 'transparent',
    cardColor: '#fbf5e9',
    modalColor: '#fbf5e9',
    popoverColor: '#fffdf7',
    textColorBase: '#2c241b',
    textColor1: '#2c241b',
    textColor2: '#5c4f3f',
    textColor3: '#6f5d49',
    placeholderColor: '#7a6852',
    dividerColor: 'rgba(76, 54, 30, 0.14)',
    borderColor: 'rgba(76, 54, 30, 0.22)',
    borderRadius: '10px',
    borderRadiusSmall: '8px',
    fontWeightStrong: '600',
    boxShadow1: '0 4px 14px rgba(90, 64, 30, 0.08)',
    boxShadow2: '0 8px 24px rgba(90, 64, 30, 0.12)',
    boxShadow3: '0 16px 40px rgba(90, 64, 30, 0.16)',
  },
  Card: {
    borderRadius: '14px',
    color: '#fbf5e9',
    colorEmbedded: '#f6eedf',
    titleFontWeightMedium: '600',
    titleFontSizeMedium: '17px',
    borderColor: 'rgba(76, 54, 30, 0.16)',
  },
  Button: {
    borderRadius: '9999px',
    borderRadiusSmall: '9999px',
    borderRadiusLarge: '9999px',
    fontWeight: '500',
  },
  Input: {
    borderRadius: '10px',
    color: '#fffdf7',
    colorDisabled: '#f0e7d6',
    border: '1px solid rgba(76, 54, 30, 0.22)',
    borderHover: '1px solid rgba(76, 54, 30, 0.36)',
    borderFocus: '1px solid #98461f',
    borderActive: '1px solid #98461f',
    borderSelected: '1px solid #98461f',
    boxShadowFocus: '0 0 0 3px rgba(152, 70, 31, 0.14)',
    placeholderColor: '#7a6852',
  },
  Select: {
    peers: {
      InternalSelection: {
        borderRadius: '10px',
        color: '#fffdf7',
        border: '1px solid rgba(76, 54, 30, 0.22)',
        borderHover: '1px solid rgba(76, 54, 30, 0.36)',
        borderActive: '1px solid #98461f',
        borderFocus: '1px solid #98461f',
      },
    },
  },
  DataTable: {
    thColor: '#f1e6d2',
    thTextColor: '#6f6050',
    thFontWeight: '600',
    tdColor: '#fbf5e9',
    tdColorHover: 'rgba(164, 85, 43, 0.06)',
    borderColor: 'rgba(76, 54, 30, 0.12)',
  },
  Tag: { borderRadius: '9999px' },
  Tabs: {
    barColor: '#a4552b',
    tabTextColorLine: '#6f6050',
    tabTextColorActiveLine: '#2c241b',
    tabTextColorHoverLine: '#2c241b',
    tabFontMedium: '15px',
    tabFontWeightActive: '600',
  },
  Form: {
    labelTextColor: '#2c241b',
    labelFontWeight: '500',
  },
  Switch: {
    railColorActive: '#a4552b',
  },
  Popover: { borderRadius: '14px' },
  Modal: { borderRadius: '16px' },
  Tooltip: { borderRadius: '8px' },
}

// v4.7.0：暖沙·夜（同色系低亮）——只覆盖颜色，圆角/字体沿用日间
const warmNightOverrides: GlobalThemeOverrides = {
  ...moonshotOverrides,
  common: {
    ...moonshotOverrides.common,
    bodyColor: 'transparent',
    cardColor: '#2e261d',
    modalColor: '#2e261d',
    popoverColor: '#3a3026',
    textColorBase: '#f4ead8',
    textColor1: '#f4ead8',
    textColor2: '#d6c6ad',
    textColor3: '#b7a58c',
    placeholderColor: '#9c8a72',
    dividerColor: 'rgba(255, 236, 210, 0.14)',
    borderColor: 'rgba(255, 236, 210, 0.22)',
    boxShadow1: '0 4px 14px rgba(0, 0, 0, 0.32)',
    boxShadow2: '0 8px 24px rgba(0, 0, 0, 0.42)',
    boxShadow3: '0 16px 40px rgba(0, 0, 0, 0.52)',
  },
  Card: {
    ...moonshotOverrides.Card,
    color: '#2e261d',
    colorEmbedded: '#3a3026',
    borderColor: 'rgba(255, 236, 210, 0.14)',
  },
  Input: {
    ...moonshotOverrides.Input,
    color: '#3a3026',
    colorDisabled: '#2a231b',
    border: '1px solid rgba(255, 236, 210, 0.2)',
    borderHover: '1px solid rgba(255, 236, 210, 0.34)',
    borderFocus: '1px solid #e0a06a',
    borderActive: '1px solid #e0a06a',
    borderSelected: '1px solid #e0a06a',
    boxShadowFocus: '0 0 0 3px rgba(224, 160, 106, 0.16)',
    placeholderColor: '#9c8a72',
  },
  DataTable: {
    ...moonshotOverrides.DataTable,
    thColor: '#3a3026',
    thTextColor: '#b7a58c',
    tdColor: '#2e261d',
    tdColorHover: 'rgba(224, 160, 106, 0.1)',
    borderColor: 'rgba(255, 236, 210, 0.12)',
  },
}

// v4.7.0：日间（暖沙）/ 夜间（暖沙·夜）切换，记忆在 localStorage
const THEME_KEY = 'humanizer-console-theme'
const themeMode = ref<'light' | 'night'>('light')
try {
  if (localStorage.getItem(THEME_KEY) === 'night') themeMode.value = 'night'
} catch {
  /* 隐私模式忽略 */
}
const activeOverrides = computed(() =>
  themeMode.value === 'night' ? warmNightOverrides : moonshotOverrides,
)

function applyTheme() {
  try {
    document.documentElement.dataset.theme = themeMode.value
  } catch {
    /* SSR/受限环境忽略 */
  }
}

function toggleTheme() {
  themeMode.value = themeMode.value === 'night' ? 'light' : 'night'
  try {
    localStorage.setItem(THEME_KEY, themeMode.value)
  } catch {
    /* 忽略 */
  }
  applyTheme()
}

onMounted(async () => {
  applyTheme()
  await init()
})
</script>

<style scoped>
/* ===== 顶部导航（Moonshot 式：黑底毛玻璃、纯文字、小字号） ===== */
.hz-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--hz-nav-bg);
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
  min-width: 0;
}
.hz-nav-inner > .brand,
.hz-nav-inner > .theme-toggle {
  flex: 0 0 auto;
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
  /* v4.8.1 自检：flex 子项默认 min-width:auto 会把整页撑宽，必须显式允许收缩 */
  min-width: 0;
  flex: 1 1 auto;
  -webkit-overflow-scrolling: touch;
}
.hz-menu::-webkit-scrollbar {
  display: none;
}

/* v4.8.0：任务分组导航（组名 + 细竖线分隔，窄屏隐藏组名） */
.nav-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}
.nav-group + .nav-group {
  margin-left: 4px;
  padding-left: 10px;
  border-left: 1px solid var(--hz-border);
}
.nav-group-label {
  margin-right: 2px;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: var(--hz-text-3);
}
@media (max-width: 1320px) {
  .nav-group-label {
    display: none;
  }
  .nav-group + .nav-group {
    margin-left: 0;
    padding-left: 0;
    border-left: 0;
  }
}
/* v4.8.1 自检：手机上让出导航空间，并用渐变提示「右侧还有页面可滑」 */
@media (max-width: 720px) {
  .brand-text {
    display: none;
  }
  .hz-nav-inner {
    padding: 0 14px;
    gap: 10px;
  }
  .hz-menu {
    mask-image: linear-gradient(to right, #000 calc(100% - 18px), transparent);
    -webkit-mask-image: linear-gradient(to right, #000 calc(100% - 18px), transparent);
  }
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
  background: var(--hz-nav-active);
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

/* v4.7.0：日间/夜间切换 */
.theme-toggle {
  margin-left: 4px;
  padding: 6px 13px;
  border-radius: var(--hz-radius-pill);
  border: 1px solid var(--hz-hairline);
  background: transparent;
  color: var(--hz-text-2);
  font-size: 12.5px;
  letter-spacing: 0.02em;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.2s var(--hz-ease), border-color 0.2s var(--hz-ease),
    background 0.2s var(--hz-ease);
}
.theme-toggle:hover {
  color: var(--hz-text);
  border-color: var(--hz-hairline-strong);
  background: var(--hz-pink-soft);
}

/* ===== 内容区：居中定宽 + 大留白 ===== */
.hz-main {
  max-width: var(--hz-content-w);
  margin: 0 auto;
  padding: 40px 24px 72px;
  min-height: calc(100vh - var(--hz-nav-h));
  display: flex;
  flex-direction: column;
  /* v4.8.1 自检：装饰性光晕不得把整页撑出横向滚动条 */
  overflow-x: clip;
  min-width: 0;
}

.page-head {
  margin-bottom: 32px;
}

.page-title {
  font-size: 34px;
  font-weight: 600;
  letter-spacing: -0.02em;
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
/* v4.8.0 审计修正：路由懒加载期间的悬浮提示（不参与页面布局，避免布局跳动） */
.route-loading {
  position: fixed;
  top: calc(var(--hz-nav-h) + 12px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 40;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: 999px;
  background: var(--hz-card);
  border: 1px solid var(--hz-hairline);
  box-shadow: 0 6px 20px rgba(60, 40, 20, 0.10);
  color: var(--hz-text-3);
  font-size: 12.5px;
  pointer-events: none;
}
.route-loading::before {
  content: '';
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--hz-hairline);
  border-top-color: var(--hz-pink);
  animation: route-spin 0.8s linear infinite;
}
@keyframes route-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
