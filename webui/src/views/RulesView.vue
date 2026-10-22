<template>
  <n-spin :show="loading">
    <template v-if="!loading">
      <section class="hz-section rules-head">
        <n-space align="center">
          <n-tag round type="primary">共 {{ rules.length }} 条</n-tag>
          <n-tag round>启用 {{ enabledCount }}</n-tag>
          <n-tag round type="info">注入型 {{ injectCount }}</n-tag>
          <n-tag round type="warning">质检型 {{ qcCount }}</n-tag>
          <n-tag v-if="builtinCount" round>内置 {{ builtinCount }}</n-tag>
          <span class="spacer" />
          <n-button size="small" @click="load">刷新</n-button>
          <n-button size="small" type="primary" @click="openAdd">新建规则</n-button>
        </n-space>
      </section>

      <section class="rules-filter">
        <n-radio-group v-model:value="filter" size="small">
          <n-radio-button value="all">全部</n-radio-button>
          <n-radio-button value="inject">注入型</n-radio-button>
          <n-radio-button value="qc">质检型</n-radio-button>
          <n-radio-button value="disabled">已停用</n-radio-button>
        </n-radio-group>
      </section>

      <n-input
        v-model:value="keyword"
        placeholder="搜索规则名 / 内容"
        clearable
        class="rules-search"
      />

      <n-alert v-if="loadError" type="error" :bordered="false" class="rules-empty">
        {{ loadError }}
      </n-alert>
      <n-empty v-else-if="!filtered.length" description="没有匹配的规则" class="rules-empty" />

      <n-grid v-else :cols="2" responsive="screen" item-responsive :x-gap="16" :y-gap="16">
        <n-grid-item v-for="rule in filtered" :key="rule.id" span="2 s:2 m:1">
        <n-card
          class="rule-card"
          :class="{ disabled: !rule.enabled }"
        >
          <div class="rule-top">
            <div class="rule-title">
              <n-tag size="small" round :type="rule.type === 'qc' ? 'warning' : 'info'">
                {{ rule.type === 'qc' ? '质检' : '注入' }}
              </n-tag>
              <span class="rule-name">{{ rule.name }}</span>
              <n-tag v-if="rule.severity" size="small" round>{{ rule.severity }}</n-tag>
              <n-tag v-if="rule.builtin" size="small" round type="default">内置</n-tag>
            </div>
            <n-space align="center" :size="8">
              <n-switch
                :value="!!rule.enabled"
                size="small"
                @update:value="(v: boolean) => toggle(rule, v)"
              />
              <n-button
                size="small"
                tertiary
                type="error"
                :disabled="rule.builtin"
                @click="remove(rule)"
              >
                删除
              </n-button>
            </n-space>
          </div>
          <p class="rule-content">{{ rule.content }}</p>
          <p v-if="rule.type === 'qc' && rule.qc_pattern" class="rule-pattern">
            <span class="lbl">质检正则关键词：</span>{{ rule.qc_pattern }}
          </p>
          <p class="rule-id">ID：{{ rule.id }}</p>
        </n-card>
        </n-grid-item>
      </n-grid>
    </template>
  </n-spin>

  <n-modal v-model:show="showAdd" preset="card" title="新建真人感规则" class="add-modal">
    <n-form label-placement="left" label-width="90">
      <n-form-item label="名称">
        <n-input v-model:value="draft.name" placeholder="例如：不主动提自己是 AI" />
      </n-form-item>
      <n-form-item label="类型">
        <n-select v-model:value="draft.type" :options="typeOptions" />
      </n-form-item>
      <n-form-item label="严重度">
        <n-select v-model:value="draft.severity" :options="severityOptions" />
      </n-form-item>
      <n-form-item label="规则内容">
        <n-input
          v-model:value="draft.content"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="注入型：告诉模型该怎么说话；质检型：描述要避免的表达"
        />
      </n-form-item>
      <n-form-item v-if="draft.type === 'qc'" label="质检关键词">
        <n-input
          v-model:value="draft.qc_pattern"
          placeholder="逗号分隔的触发词/正则关键词，留空则用规则内容"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showAdd = false">取消</n-button>
        <n-button type="primary" :loading="adding" @click="add">创建</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NForm,
  NFormItem,
  NGrid,
  NGridItem,
  NInput,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NSwitch,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import { useBridge } from '@/composables/useBridge'

const { apiGet, apiPost } = useBridge()
const message = useMessage()
const dialog = useDialog()

const loading = ref(true)
const adding = ref(false)
const showAdd = ref(false)
const loadError = ref('')
const keyword = ref('')
const filter = ref<'all' | 'inject' | 'qc' | 'disabled'>('all')
const rules = ref<any[]>([])

const draft = reactive({
  name: '',
  type: 'inject',
  severity: 'S2',
  content: '',
  qc_pattern: '',
})

const typeOptions = [
  { label: '注入型（约束生成）', value: 'inject' },
  { label: '质检型（事后检测）', value: 'qc' },
]
const severityOptions = [
  { label: 'S1 严格', value: 'S1' },
  { label: 'S2 标准', value: 'S2' },
  { label: 'S3 轻微', value: 'S3' },
]

const enabledCount = computed(() => rules.value.filter(r => r.enabled).length)
const injectCount = computed(() => rules.value.filter(r => r.type === 'inject').length)
const qcCount = computed(() => rules.value.filter(r => r.type === 'qc').length)
const builtinCount = computed(() => rules.value.filter(r => r.builtin).length)
const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  return rules.value.filter(r => {
    if (filter.value === 'inject' && r.type !== 'inject') return false
    if (filter.value === 'qc' && r.type !== 'qc') return false
    if (filter.value === 'disabled' && r.enabled) return false
    if (!k) return true
    return (
      String(r.name || '').toLowerCase().includes(k) ||
      String(r.content || '').toLowerCase().includes(k)
    )
  })
})

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res: any = await apiGet('rules')
    if (res && res.ok) rules.value = res.rules || []
    else {
      loadError.value = '规则读取失败：' + ((res && res.error) || '未知错误')
      message.error(loadError.value)
    }
  } catch (e: any) {
    loadError.value = '规则读取失败：' + (e?.message || e)
    message.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function apply(payload: Record<string, unknown>, okText: string) {
  const res: any = await apiPost('rules/save', payload)
  if (res && res.ok) {
    rules.value = res.rules || []
    message.success(okText)
    return true
  }
  message.error((res && res.error) || '操作失败')
  return false
}

async function toggle(rule: any, enabled: boolean) {
  await apply(
    { action: enabled ? 'enable' : 'disable', key: rule.id },
    `已${enabled ? '启用' : '停用'}「${rule.name}」`,
  )
}

function remove(rule: any) {
  dialog.warning({
    title: '删除规则',
    content: `确定删除「${rule.name}」吗？该操作可撤销（重新添加即可），内置规则不可删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await apply({ action: 'delete', key: rule.id }, `已删除「${rule.name}」`)
    },
  })
}

function openAdd() {
  draft.name = ''
  draft.type = 'inject'
  draft.severity = 'S2'
  draft.content = ''
  draft.qc_pattern = ''
  showAdd.value = true
}

async function add() {
  if (!draft.name.trim()) {
    message.warning('名称不能为空')
    return
  }
  if (!draft.content.trim()) {
    message.warning('规则内容不能为空')
    return
  }
  adding.value = true
  try {
    const ok = await apply(
      {
        action: 'add',
        name: draft.name.trim(),
        type: draft.type,
        severity: draft.severity,
        content: draft.content.trim(),
        qc_pattern: draft.qc_pattern.trim(),
      },
      `已创建「${draft.name.trim()}」`,
    )
    if (ok) showAdd.value = false
  } finally {
    adding.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.rules-head {
  margin-bottom: 12px;
}
.spacer {
  flex: 1;
}
.rules-search {
  max-width: 380px;
  margin-bottom: 12px;
}
.rules-filter {
  margin-bottom: 16px;
}
.rules-empty {
  padding: 60px 0;
}
.rules-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rule-card {
  transition: opacity 0.2s var(--hz-ease);
}
.rule-card.disabled {
  opacity: 0.55;
}
.rule-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.rule-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.rule-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--hz-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rule-content {
  margin: 12px 0 0;
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--hz-text-2);
  white-space: pre-wrap;
  word-break: break-word;
}
.rule-pattern {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: var(--hz-text-3);
  word-break: break-word;
}
.lbl {
  color: var(--hz-text-3);
}
.rule-id {
  margin: 8px 0 0;
  font-size: 11.5px;
  color: var(--hz-text-3);
  font-family: var(--hz-mono, monospace);
}
.add-modal {
  max-width: 640px;
}
</style>
