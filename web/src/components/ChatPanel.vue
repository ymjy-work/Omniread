<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import MessageList from './MessageList.vue'
import ModelPicker from './ModelPicker.vue'
import { useChat } from '../composables/useChat'
import { useAccountStore } from '../stores/account'
import { useReaderStore } from '../stores/reader'
import { formatCredits } from '../utils/billing'
import type { Citation } from '../types/chat'

const props = withDefaults(
  defineProps<{
    bookId: number
    bookTitle?: string
    collapsible?: boolean
  }>(),
  {
    bookTitle: '',
    collapsible: false,
  },
)
const emit = defineEmits<{ cite: [citation: Citation]; collapse: [] }>()

const reader = useReaderStore()
const account = useAccountStore()
const { question, sending, prepare, send } = useChat(() => props.bookId)

const planReady = computed(() => Boolean(account.account))
const canPlatform = computed(() => planReady.value && account.plan !== 'free')
const activeKey = computed(() => account.apiKeys.find((item) => item.provider === reader.provider))

const blockingMessage = computed(() => {
  if (reader.surface === 'self' && account.keysLoading && !account.keysLoaded) {
    return '正在读取 API Key…'
  }
  return reader.askProblem
})

const statusText = computed(() => {
  if (account.error && !planReady.value) return account.error
  if (reader.surface === 'self' && account.keysError && !activeKey.value) {
    return account.keysError
  }
  if (reader.surface === 'self' && !activeKey.value && !account.keysLoading) {
    return '请在自己面板保存该提供商的 API Key。'
  }
  if (blockingMessage.value) return blockingMessage.value
  if (reader.surface === 'self' && reader.providerModelsError) {
    return reader.providerModelsError
  }
  if (reader.surface === 'official') {
    return reader.mode === 'auto'
      ? 'Free 档 auto 自动路由 · 每次 1 积分'
      : '官方模型 · 每次 1 积分'
  }
  return '自己的 Key · 不扣积分'
})

const chatErrorText = computed(() => {
  const message = reader.chatError
  if (!message) return ''
  if (reader.chatErrorCode === 40201) {
    return '积分不足，无法使用官方回答。请改用自己。'
  }
  if (reader.chatErrorCode === 40202) return '余额不足，当前无法使用官方回答。'
  if (message.includes('API Key') || message.includes('Key')) {
    return '该提供商尚未配置 API Key，请先保存 Key。'
  }
  if (message.includes('free 档')) return 'Free 档只能使用 auto 模式。'
  return message
})

const sendDisabled = computed(
  () => sending.value || !question.value.trim() || Boolean(blockingMessage.value),
)

onMounted(() => {
  void prepare()
  void account.fetchAccount()
  void account.fetchApiKeys()
  if (reader.surface === 'official' && canPlatform.value) void reader.loadPlatformModels(true)
})

watch(
  () => props.bookId,
  () => {
    void prepare()
  },
)

watch(
  () => account.plan,
  (plan) => {
    if (plan && plan !== 'free' && reader.surface === 'official') {
      void reader.loadPlatformModels(true)
    }
  },
)

function handleCite(citation: Citation) {
  emit('cite', citation)
}

function submit() {
  if (sendDisabled.value) return
  void send()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="chat-panel">
    <header class="chat-head">
      <div class="chat-title-row">
        <div class="chat-identity">
          <h2>文中助手</h2>
          <p class="book-context">{{ bookTitle || '当前书' }}</p>
        </div>
        <div class="chat-head-actions">
          <span v-if="reader.session" class="session-tag">#{{ reader.session.id }}</span>
          <button
            v-if="collapsible"
            class="collapse-btn"
            type="button"
            aria-label="收起对话面板"
            title="收起对话"
            @click="emit('collapse')"
          >
            ›
          </button>
        </div>
      </div>

      <div class="control-row">
        <span class="control-label">范围</span>
        <div class="range-switch" role="group" aria-label="回答范围">
          <button
            type="button"
            :class="{ active: reader.level === 'past' }"
            :aria-pressed="reader.level === 'past'"
            @click="reader.setLevel('past')"
          >
            已读
          </button>
          <button
            type="button"
            :class="{ active: reader.level === 'full' }"
            :aria-pressed="reader.level === 'full'"
            @click="reader.setLevel('full')"
          >
            全书
          </button>
        </div>
      </div>
    </header>

    <MessageList
      :messages="reader.messages"
      :loading="reader.messagesLoading"
      :error="chatErrorText"
      :asking="reader.asking"
      @cite="handleCite"
    />

    <div v-if="reader.chatError && !reader.session" class="session-error">
      <span>会话未能建立。</span>
      <button class="btn btn-ghost" type="button" @click="prepare()">重试</button>
    </div>

    <footer class="composer">
      <textarea
        v-model="question"
        class="composer-input"
        rows="3"
        placeholder="就这一章提问…"
        :disabled="reader.asking"
        @keydown="handleKeydown"
      ></textarea>

      <div class="composer-status" :class="{ warning: Boolean(blockingMessage) }">
        <span
          v-if="account.account"
          class="credit-tag"
          :class="{ empty: account.credits < 1 }"
          :title="`剩余积分 ${account.credits}`"
        >
          积分 {{ formatCredits(account.credits) }}
        </span>
        <span class="status-text" role="status">{{ statusText }}</span>
        <button
          v-if="account.error && !planReady"
          class="link-btn"
          type="button"
          @click="account.fetchAccount(true)"
        >
          重试
        </button>
      </div>

      <div class="composer-controls">
        <ModelPicker />
        <button
          class="btn btn-primary send-btn"
          type="button"
          :disabled="sendDisabled"
          @click="submit"
        >
          <span v-if="sending" class="spinner sm"></span>
          {{ sending ? '回答中' : '发送' }}
        </button>
      </div>

      <p class="hint">Enter 发送 · Shift+Enter 换行</p>
    </footer>
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--surface);
  border-left: 1px solid var(--border);
}

.chat-head {
  flex: none;
  padding: 14px 16px 11px;
  border-bottom: 1px solid var(--border);
}

.chat-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.chat-identity {
  min-width: 0;
}

.chat-head h2 {
  font-size: 15px;
  font-weight: 600;
}

.book-context {
  overflow: hidden;
  max-width: 230px;
  color: var(--text-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}

.collapse-btn {
  display: grid;
  place-items: center;
  width: 25px;
  height: 25px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1;
}

.collapse-btn:hover {
  border-color: var(--border);
  background: var(--surface-2);
  color: var(--text);
}

.session-tag {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 72px;
  font-size: 11px;
  color: var(--text-muted);
}

.control-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.control-label {
  flex: none;
  width: 30px;
  font-size: 11.5px;
  color: var(--text-muted);
}

.range-switch {
  display: flex;
  flex: 1;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.range-switch button {
  flex: 1;
  padding: 4px 8px;
  border: none;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  transition: background-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}

.range-switch button:hover:not(:disabled) {
  color: var(--text);
}

.range-switch button.active {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: var(--shadow-sm);
}

.session-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 14px 8px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.session-error .btn {
  color: var(--danger);
  font-size: 12.5px;
  padding: 4px 8px;
}

.composer {
  flex: none;
  padding: 10px 12px 12px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}

.composer-input {
  display: block;
  width: 100%;
  min-height: 70px;
  max-height: 150px;
  padding: 9px 11px;
  resize: vertical;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  font-size: 14px;
  line-height: 1.65;
  transition: border-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}

.composer-input::placeholder {
  color: var(--text-muted);
}

.composer-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
  background: var(--surface);
}

.composer-status {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-height: 20px;
  margin-top: 7px;
  font-size: 10.5px;
  line-height: 1.45;
  color: var(--text-muted);
}

.composer-status.warning {
  color: var(--danger);
}

.credit-tag {
  flex: none;
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.credit-tag.empty {
  border-color: color-mix(in srgb, var(--danger) 35%, var(--border));
  background: var(--danger-soft);
  color: var(--danger);
}

.status-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.link-btn {
  flex: none;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--accent);
  font-size: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.composer-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 7px;
}

.send-btn {
  flex: none;
  min-width: 64px;
  height: 32px;
  padding: 0 13px;
  font-size: 12.5px;
}

.hint {
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-muted);
}

@media (max-width: 380px) {
  .composer-controls {
    justify-content: flex-start;
  }

  .send-btn {
    margin-left: auto;
  }
}
</style>
