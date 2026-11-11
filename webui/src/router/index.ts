import type { RouteRecordRaw } from 'vue-router'

// v4.8.2：路由级懒加载——首屏只加载总览，其余页面按需拉取 chunk，
// 降低首次打开控制台的 JS 体积（构建产物会按路由拆分）。
const OverviewView = () => import('@/views/OverviewView.vue')
const ConfigView = () => import('@/views/ConfigView.vue')
const StylesView = () => import('@/views/StylesView.vue')
const ProactiveView = () => import('@/views/ProactiveView.vue')
const RecordsView = () => import('@/views/RecordsView.vue')
const RulesView = () => import('@/views/RulesView.vue')
const StatsView = () => import('@/views/StatsView.vue')
const GrowthView = () => import('@/views/GrowthView.vue')

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'overview',
    component: OverviewView,
    meta: { title: '总览', icon: 'lucide:layout-dashboard', tone: 'pink', group: '像个人' },
  },
  {
    path: '/config',
    name: 'config',
    component: ConfigView,
    meta: {
      title: '配置',
      subtitle: '表达基调、细分配置与成长档案的开关和参数',
      icon: 'lucide:settings',
      group: '调校排障',
      tone: 'blue',
    },
  },
  {
    path: '/styles',
    name: 'styles',
    component: StylesView,
    meta: {
      title: '语料与风格',
      subtitle: '积累语料、提炼说话风格、切换档案与记录纠错',
      icon: 'lucide:sparkles',
      group: '像个人',
      tone: 'violet',
    },
  },
  {
    path: '/proactive',
    name: 'proactive',
    component: ProactiveView,
    meta: {
      title: '主动聊天',
      subtitle: '各会话的主动消息触发状态与策略',
      icon: 'lucide:message-circle',
      group: '主动找人',
      tone: 'cyan',
    },
  },
  {
    path: '/records',
    name: 'records',
    component: RecordsView,
    meta: {
      title: '记录回看',
      subtitle: '查看会话消息记录与当时的思考过程',
      icon: 'lucide:history',
      group: '别被识破',
      tone: 'indigo',
    },
  },
  {
    path: '/rules',
    name: 'rules',
    component: RulesView,
    meta: {
      title: '真人感规则',
      subtitle: '自定义表达规则库：注入型约束生成、质检型事后检测，逐条开关',
      icon: 'lucide:scroll-text',
      group: '别被识破',
      tone: 'green',
    },
  },
  {
    path: '/stats',
    name: 'stats',
    component: StatsView,
    meta: {
      title: '统计',
      subtitle: '规则清理、主动发送、分段、质检与打字延迟等累计次数',
      icon: 'lucide:bar-chart-3',
      group: '调校排障',
      tone: 'amber',
    },
  },
  {
    path: '/growth',
    name: 'growth',
    component: GrowthView,
    meta: {
      title: '成长档案',
      subtitle: '按会话查看只读成长状态与元数据事件',
      icon: 'lucide:clipboard-check',
      group: '像个人',
      tone: 'green',
    },
  },
]
