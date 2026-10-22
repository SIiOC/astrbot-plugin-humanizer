import type { RouteRecordRaw } from 'vue-router'
import OverviewView from '@/views/OverviewView.vue'
import ConfigView from '@/views/ConfigView.vue'
import StylesView from '@/views/StylesView.vue'
import ProactiveView from '@/views/ProactiveView.vue'
import RecordsView from '@/views/RecordsView.vue'
import RulesView from '@/views/RulesView.vue'
import StatsView from '@/views/StatsView.vue'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'overview',
    component: OverviewView,
    meta: { title: '总览', icon: 'lucide:layout-dashboard', tone: 'pink' },
  },
  {
    path: '/config',
    name: 'config',
    component: ConfigView,
    meta: {
      title: '配置',
      subtitle: '风格、润色、感知、主动与发送六个分组的开关和参数',
      icon: 'lucide:settings',
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
      tone: 'amber',
    },
  },
]
