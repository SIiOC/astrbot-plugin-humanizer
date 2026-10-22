<template>
  <div>
    <n-space align="center" class="mb-4">
      <n-select
        v-model:value="selectedUmo"
        :options="sessionOptions"
        placeholder="选择会话"
        clearable
        style="width: 380px"
        @update:value="onSelect"
      />
      <n-button @click="loadSessions">刷新会话</n-button>
    </n-space>

    <n-alert v-if="sessionsError" type="error" class="mb-4">
      会话列表读取失败：{{ sessionsError }}
    </n-alert>
    <n-alert v-else-if="loaded && !sessions.length" type="info" class="mb-4">
      还没有找到任何会话。先和机器人聊几句，再回来查看记录。
    </n-alert>

    <n-alert v-if="historyError" type="error" class="mb-4">
      消息记录读取失败：{{ historyError }}
    </n-alert>

    <n-card>
      <n-spin :show="historyLoading">
        <n-empty v-if="!selectedUmo" description="选择会话查看消息记录" size="small" class="py-8" />
        <n-empty v-else-if="!historyLoading && !messages.length" description="该会话暂无消息" size="small" class="py-8" />
        <n-space v-else vertical size="small">
          <div
            v-for="(m, i) in messages"
            :key="i"
            class="bubble-row"
            :class="m.role === 'user' ? 'row-user' : 'row-ai'"
          >
            <div class="bubble" :class="m.role === 'user' ? 'bubble-user' : 'bubble-ai'">
              <div class="bubble-head">
                <span class="bubble-who">{{ m.role === 'user' ? '用户' : 'AI' }}</span>
                <n-tag v-if="m.proactive" type="warning" size="tiny">主动</n-tag>
              </div>
              <div class="msg-text">{{ m.text }}</div>
              <n-collapse v-if="m.thinking">
                <n-collapse-item title="当时的思考过程" name="thinking">
                  <div class="thinking-text">{{ m.thinking }}</div>
                </n-collapse-item>
              </n-collapse>
            </div>
          </div>
        </n-space>
      </n-spin>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NEmpty, NSelect, NSpace, NSpin, NTag } from 'naive-ui'
import { useBridge } from '@/composables/useBridge'

const { apiGet } = useBridge()
const sessions = ref<any[]>([])
const loaded = ref(false)
const selectedUmo = ref<string | null>(null)
const messages = ref<any[]>([])
const historyLoading = ref(false)
const sessionsError = ref('')
const historyError = ref('')
// v4.1.9：请求序号——快速切换会话时丢弃过期响应，避免旧会话消息显示在新选择下
let historySeq = 0

const sessionOptions = computed(() =>
  sessions.value.map(s => ({ label: s.label, value: s.umo })),
)

async function loadSessions() {
  sessionsError.value = ''
  try {
    const res: any = await apiGet('sessions')
    if (res && res.ok) sessions.value = res.sessions || []
    else sessionsError.value = (res && res.error) || '后端未返回有效数据'
  } catch (e: any) {
    sessionsError.value = e?.message || String(e)
    console.error('会话加载失败:', e)
  } finally {
    loaded.value = true
  }
}

function onSelect(umo: string | null) {
  if (!umo) {
    historySeq += 1
    messages.value = []
    historyError.value = ''
    return
  }
  loadHistory(umo)
}

async function loadHistory(umo: string) {
  const seq = ++historySeq
  historyLoading.value = true
  historyError.value = ''
  try {
    const res: any = await apiGet('sessions/history', { umo })
    if (seq !== historySeq) return
    if (res && res.ok) {
      messages.value = res.messages || []
    } else {
      messages.value = []
      historyError.value = (res && res.error) || '后端未返回有效数据'
    }
  } catch (e: any) {
    if (seq !== historySeq) return
    messages.value = []
    historyError.value = e?.message || String(e)
    console.error('历史读取失败:', e)
  } finally {
    if (seq === historySeq) historyLoading.value = false
  }
}

onMounted(loadSessions)
</script>

<style scoped>
.mb-4 {
  margin-bottom: 20px;
}
.py-8 {
  padding: 40px 0;
}
.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13.5px;
  line-height: 1.65;
}
.thinking-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  color: var(--hz-text-2);
  padding: 10px 12px;
  background: #202020;
  border-radius: 10px;
}

/* v3.1 Moonshot 式暗色气泡：用户左·深灰面板 / AI 右·品牌粉暗底 */
.bubble-row {
  display: flex;
}
.row-user {
  justify-content: flex-start;
}
.row-ai {
  justify-content: flex-end;
}
.bubble {
  max-width: 76%;
  padding: 12px 16px;
  border-radius: 18px;
  font-size: 13.5px;
  transition: transform 0.2s var(--hz-ease), background 0.2s var(--hz-ease);
}
.bubble:hover {
  transform: translateY(-1px);
}
.bubble-user {
  background: #202020;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-bottom-left-radius: 6px;
}
.bubble-ai {
  background: rgba(255, 110, 199, 0.13);
  border: 1px solid rgba(255, 110, 199, 0.26);
  border-bottom-right-radius: 6px;
}
.bubble-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.bubble-who {
  font-size: 11px;
  font-weight: 600;
  color: var(--hz-text-3);
}
</style>
