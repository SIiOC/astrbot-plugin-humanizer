<template>
  <n-spin :show="loading">
    <template v-if="!loading">
      <!-- ① 语料：统计 + 导入（风格由「有效语料」提炼而来） -->
      <n-card title="语料" embedded>
        <template #header-extra>
          <span class="step-hint">第一步 · 说话风格由「有效语料」提炼而来，先在这里积累对话语料</span>
        </template>

        <div class="mini-stats">
          <StatCard class="mini" icon="lucide:user" tone="pink" label="用户语料" :value="`${corpus.user?.pairs ?? 0} 对`" :delay="0" />
          <StatCard class="mini" icon="lucide:package" tone="cyan" label="内置语料" :value="`${corpus.builtin?.pairs ?? 0} 对`" :delay="60" />
          <StatCard class="mini" icon="lucide:layers" tone="violet" label="有效语料（合并）" :value="`${corpus.effective?.pairs ?? 0} 对`" :delay="120" />
        </div>

        <n-alert v-if="loadError" type="error" :bordered="false" style="margin-top: 12px">
          {{ loadError }}（上方语料计数按 0 显示，不代表真实值）
        </n-alert>

          <n-upload
            ref="uploadRef"
            accept=".txt,.json,.jsonl,.csv"
            :max="1"
            :default-upload="false"
            :show-file-list="false"
            @change="onFileChange"
          >
          <n-upload-dragger>
            <div class="upload-inner">
              <Icon icon="lucide:upload-cloud" style="font-size: 30px; color: var(--hz-pink)" />
              <p class="upload-title">拖拽语料文件到这里，或点击选择</p>
              <p class="upload-sub">支持 .txt / .json / .jsonl / .csv，10MB 以内，自动识别格式并去重</p>
            </div>
          </n-upload-dragger>
        </n-upload>

        <div v-if="uploadFile" class="file-chip">
          <Icon icon="lucide:file-text" class="file-chip-icon" />
          <span class="file-chip-name">{{ uploadFile.name }}</span>
          <span class="file-chip-size">{{ fmtSize(uploadFile.size) }}</span>
          <n-button size="tiny" quaternary circle title="移除" @click="clearFile">
            <Icon icon="lucide:x" style="font-size: 14px" />
          </n-button>
        </div>
        <div style="margin-top: 10px">
          <n-button type="primary" :loading="uploading" :disabled="!uploadFile" @click="doUpload">
            上传并导入
          </n-button>
        </div>

        <n-divider style="margin: 12px 0 8px">
          <span class="divider-text">或粘贴文本</span>
        </n-divider>

        <n-input
          v-model:value="corpusText"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="粘贴对话语料：每行一句（txt 格式），或 JSON/JSONL/CSV。内容仅用于本地提炼说话风格，提炼时采样片段会发送给 LLM。"
        />
        <div style="margin-top: 10px">
          <n-button type="primary" ghost :loading="importing" :disabled="!corpusText.trim()" @click="doImport">
            导入文本
          </n-button>
        </div>

        <n-alert v-if="lastImport" :type="lastImport.ok ? 'success' : 'error'" :bordered="false" style="margin-top: 12px">
          {{ lastImport.text }}
        </n-alert>
      </n-card>

      <!-- ② 生成风格档案 -->
      <n-card title="生成风格档案" embedded class="mt-4">
        <template #header-extra>
          <span class="step-hint">第二步 · 语料够了就可以提炼说话风格</span>
        </template>
        <n-space vertical>
          <n-space align="center">
            <n-input v-model:value="genName" placeholder="风格名（如：我的风格）" style="width: 220px" />
            <n-radio-group v-model:value="genSource">
              <n-radio value="corpus">从语料提炼</n-radio>
              <n-radio value="colleague">从人格文本导入</n-radio>
            </n-radio-group>
          </n-space>

          <n-input
            v-if="genSource === 'colleague'"
            v-model:value="genBody"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 8 }"
            placeholder="粘贴 persona.md 全文（或 meta.json），或填写插件数据目录内文件/目录路径"
          />
          <n-text v-else depth="3" style="font-size: 12px">
            从上方「有效语料」采样提炼说话风格，生成后自动启用。
          </n-text>

          <div>
            <n-button type="primary" :loading="generating" :disabled="!genName.trim()" @click="doGenerate">
              生成并启用
            </n-button>
            <n-text v-if="genSource === 'colleague'" depth="3" style="font-size: 12px; margin-left: 10px">
              文件输入限插件数据目录内（安全策略）。生成会调用一次 LLM。
            </n-text>
          </div>
        </n-space>
      </n-card>

      <!-- ③ 风格档案列表 -->
      <n-card title="风格档案" embedded class="mt-4">
        <template #header-extra>
          <span class="step-hint">第三步 · 查看与切换已生成的档案</span>
        </template>
        <n-data-table
          :columns="columns"
          :data="styles"
          :pagination="{ pageSize: 10 }"
          :bordered="false"
          size="small"
        />
      </n-card>

      <!-- ④ 记录纠错 -->
      <n-card title="记录纠错" embedded class="mt-4">
        <template #header-extra>
          <span class="step-hint">持续调教：「TA 绝不会这样说」</span>
        </template>
        <n-space vertical>
          <n-input v-model:value="correctName" placeholder="风格名" style="width: 220px" />
          <n-input
            v-model:value="correctBody"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="格式：场景：错误说法 → 正确说法（如：打招呼：在吗 → 直接说事）"
          />
          <n-button :loading="correcting" :disabled="!correctName.trim() || !correctBody.trim()" @click="doCorrect">
            追加纠错记录
          </n-button>
        </n-space>
      </n-card>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import type { DataTableColumns } from 'naive-ui'
import {
  NAlert, NButton, NCard, NDataTable, NDivider, NInput, NRadio, NRadioGroup,
  NSpace, NSpin, NTag, NText, NUpload, NUploadDragger, useMessage,
} from 'naive-ui'
import { Icon } from '@iconify/vue'
import StatCard from '@/components/StatCard.vue'
import { useBridge } from '@/composables/useBridge'

const { apiGet, apiPost, upload } = useBridge()
const message = useMessage()

const loading = ref(true)
const styles = ref<any[]>([])
const current = ref('')
const corpus = ref<any>({})
// v4.1.9：读取失败时显示错误条——此前只弹 toast，语料计数会伪装成 0 对
const loadError = ref('')

// —— 语料导入状态 ——
const corpusText = ref('')
const importing = ref(false)
const uploading = ref(false)
const uploadFile = ref<File | null>(null)
const uploadRef = ref<any>(null)
const lastImport = ref<{ ok: boolean; text: string } | null>(null)

// —— 生成 / 纠错状态 ——
const genName = ref('')
const genSource = ref('corpus')
const genBody = ref('')
const generating = ref(false)
const correctName = ref('')
const correctBody = ref('')
const correcting = ref(false)

function clearFile() {
  uploadFile.value = null
  // n-upload 内部 fileList 不受控——不显式清空，max=1 会让第二次选文件被静默丢弃
  uploadRef.value?.clear()
}

function fmtSize(bytes: number): string {
  if (!bytes) return ''
  const units = ['B', 'KB', 'MB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`
}

const columns: DataTableColumns<any> = [
  { title: '名称', key: 'name' },
  {
    title: '当前',
    key: 'current',
    width: 80,
    render: row => (row.name === current.value ? h(NTag, { type: 'primary', size: 'small' }, { default: () => '启用' }) : null),
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    render: row =>
      h(
        NButton,
        {
          size: 'small',
          quaternary: true,
          type: 'primary',
          disabled: row.name === current.value,
          onClick: () => useStyle(row.name),
        },
        { default: () => '切换' },
      ),
  },
]

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    // 两路数据独立成败：一路失败不应丢掉另一路（Promise.all 会一损俱损）
    const [stylesRes, corpusRes] = await Promise.allSettled([
      apiGet('styles'),
      apiGet('corpus'),
    ])
    if (stylesRes.status === 'fulfilled') {
      const res: any = stylesRes.value
      if (res && res.ok) {
        styles.value = res.styles || []
        current.value = res.current || ''
      } else {
        message.error('风格读取失败: ' + ((res && res.error) || '未知错误'))
        loadError.value = '风格列表读取失败'
      }
    } else {
      message.error('风格读取失败: ' + (stylesRes.reason?.message || String(stylesRes.reason)))
      loadError.value = '风格列表读取失败'
    }
    if (corpusRes.status === 'fulfilled') {
      const res: any = corpusRes.value
      if (res && res.ok) {
        corpus.value = res
      } else {
        message.error('语料读取失败: ' + ((res && res.error) || '未知错误'))
        loadError.value = '语料统计读取失败'
      }
    } else {
      message.error('语料读取失败: ' + (corpusRes.reason?.message || String(corpusRes.reason)))
      loadError.value = '语料统计读取失败'
    }
  } finally {
    loading.value = false
  }
}

async function useStyle(name: string) {
  try {
    const res: any = await apiPost('styles/use', { name })
    if (res && res.ok) {
      message.success('已切换风格: ' + name)
      current.value = name
    } else {
      message.error('切换失败: ' + ((res && res.error) || '未知错误'))
    }
  } catch (e: any) {
    message.error('切换失败: ' + e.message)
  }
}

async function doGenerate() {
  generating.value = true
  try {
    const payload: Record<string, any> = { name: genName.value.trim(), source: genSource.value }
    if (genSource.value === 'colleague') payload.body = genBody.value.trim()
    const res: any = await apiPost('styles/generate', payload)
    if (res && res.ok) {
      message.success('风格档案已生成并启用: ' + genName.value.trim())
      genName.value = ''
      genBody.value = ''
      await load()
    } else {
      message.error('生成失败: ' + ((res && res.error) || '未知错误'))
    }
  } catch (e: any) {
    message.error('生成失败: ' + e.message)
  } finally {
    generating.value = false
  }
}

async function doCorrect() {
  correcting.value = true
  try {
    const res: any = await apiPost('styles/correct', {
      name: correctName.value.trim(),
      body: correctBody.value.trim(),
    })
    if (res && res.ok) {
      message.success('纠错记录已追加')
      correctBody.value = ''
    } else {
      message.error('纠错失败: ' + ((res && res.error) || '未知错误'))
    }
  } catch (e: any) {
    message.error('纠错失败: ' + e.message)
  } finally {
    correcting.value = false
  }
}

function onFileChange(options: { fileList?: Array<{ file?: File | null; status?: string }> }) {
  const list = options.fileList || []
  const last = [...list].reverse().find(it => it.status !== 'removed')
  const f = last?.file ?? null
  if (f && f.size > 10 * 1024 * 1024) {
    message.error('文件超过 10MB 上限')
    uploadFile.value = null
    // 超限文件必须从内部列表清掉：max=1 下残留会让上传区永久禁用（死锁）
    uploadRef.value?.clear()
    return
  }
  uploadFile.value = f
}

async function doUpload() {
  if (!uploadFile.value) return
  uploading.value = true
  try {
    const res: any = await upload('corpus/upload', uploadFile.value)
    if (res && res.ok) {
      lastImport.value = {
        ok: true,
        text: `已从「${res.filename || uploadFile.value.name}」导入 ${res.inserted} 对对话。`,
      }
      uploadFile.value = null
      uploadRef.value?.clear()
      await load()
    } else {
      lastImport.value = { ok: false, text: '上传导入失败：' + ((res && res.error) || '未知错误') }
      message.error('上传导入失败: ' + ((res && res.error) || '未知错误'))
    }
  } catch (e: any) {
    lastImport.value = { ok: false, text: '上传导入失败：' + e.message }
    message.error('上传导入失败: ' + e.message)
  } finally {
    uploading.value = false
  }
}

async function doImport() {
  importing.value = true
  try {
    const res: any = await apiPost('corpus/import', { text: corpusText.value })
    if (res && res.ok) {
      lastImport.value = { ok: true, text: `已从粘贴文本导入 ${res.inserted} 对对话。` }
      corpusText.value = ''
      await load()
    } else {
      lastImport.value = { ok: false, text: '文本导入失败：' + ((res && res.error) || '未知错误') }
      message.error('导入失败: ' + ((res && res.error) || '未知错误'))
    }
  } catch (e: any) {
    lastImport.value = { ok: false, text: '文本导入失败：' + e.message }
    message.error('导入失败: ' + e.message)
  } finally {
    importing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.mt-4 {
  margin-top: 20px;
}
.step-hint {
  font-size: 12px;
  color: var(--hz-text-3);
}
/* 三枚语料统计瓷贴（共享 StatCard，紧凑档） */
.mini-stats {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.mini-stats .mini {
  flex: 1;
  min-width: 160px;
}
:deep(.mini .stat-v) {
  font-size: 24px;
  margin-top: 10px;
}
/* 上传拖拽区：深灰虚线，hover 品牌粉 */
:deep(.n-upload-dragger) {
  border-radius: var(--hz-radius-card);
  background: #141414;
  border: 1.5px dashed rgba(255, 255, 255, 0.16);
  transition: border-color 0.2s var(--hz-ease), background 0.2s var(--hz-ease);
}
:deep(.n-upload-dragger:hover) {
  border-color: var(--hz-pink);
  background: rgba(255, 110, 199, 0.05);
}
.upload-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 12px;
}
.upload-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--hz-text);
}
.upload-sub {
  font-size: 12px;
  color: var(--hz-text-3);
}
.divider-text {
  font-size: 12px;
  color: var(--hz-text-3);
}
/* 待上传文件条：粉调软底 */
.file-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--hz-radius-ctl);
  background: var(--hz-pink-soft);
  border: 1px solid rgba(255, 110, 199, 0.24);
  margin-top: 10px;
}
.file-chip-icon {
  font-size: 18px;
  color: var(--hz-pink);
  flex-shrink: 0;
}
.file-chip-name {
  font-size: 13px;
  font-weight: 600;
  color: #ffb1de;
  word-break: break-all;
  flex: 1;
}
.file-chip-size {
  font-size: 11px;
  color: var(--hz-text-2);
  flex-shrink: 0;
}
</style>
