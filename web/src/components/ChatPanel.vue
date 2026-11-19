<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import MessageList from './MessageList.vue'
import { useChat } from '../composables/useChat'
import { useAccountStore } from '../stores/account'
import { useReaderStore } from '../stores/reader'
import { errorMessage } from '../api/request'
import { BYOK_PROVIDERS, keyStatusLabel, planLabel, providerLabel } from '../utils/billing'
import type { ApiProvider } from '../types/account'
import type { ChatMode, Citation } from '../types/chat'

const props = defineProps<{ bookId: number }>()
const emit = defineEmits<{ cite: [citation: Citation] }>()

const reader = useReaderStore()
const account = useAccountStore()
const { question, sending, prepare, send } = useChat(() => props.bookId)

const inlineKey = ref('')
const savingKey = ref(false)
const keyError = ref('')

const activeKey = computed(() =>
  account.apiKeys.find((item) => item.provider === reader.provider),
)
const planReady = computed(() => Boolean(account.account))
const canPlatform = computed(() => planReady.value && account.plan !== 'free')
const insufficientCredits = computed(
  () => reader.mode !== 'byok' && planReady.value && account.credits < 1,
)

const modeHint = computed(() => {
  if (reader.mode === 'platform') return '使用平台模型回答，每次消耗 1 积分。'
  if (reader.mode === 'byok') return '使用你自己的 Key，不消耗积分。'
  return '自动选择可用渠道，每次消耗 1 积分。'
})

const configHint = computed(() => {
  if (reader.mode === 'platform') {
    if (!planReady.value) {
      return account.error ? '账户信息加载失败，请重试。' : '账户信息加载中，请稍后。'
    }
    if (account.plan === 'free') return 'free 档只能使用 auto 模式。'
    if (!reader.model) return '请选择一个平台模型。'
  }
  if (reader.mode === 'byok') {
    if (!activeKey.value) return '请先填写并保存该提供商的 API Key。'
    if (!reader.model.trim()) return '请填写 BYOK 模型 ID。'
  }
  if (insufficientCredits.value) return '积分不足，请购买套餐或改用 BYOK。'
  return ''
})

const chatErrorText = computed(() => {
  const message = reader.chatError
  if (!message) return ''
  if (reader.chatErrorCode === 40201) {
    return '积分不足，无法使用平台回答。请购买套餐或改用 BYOK。'
  }
  if (reader.chatErrorCode === 40202) return '余额不足，请联系管理员充值。'
  if (message.includes('API Key') || message.includes('Key')) {
    return '该提供商尚未配置 API Key，请先保存 Key。'
  }
  if (message.includes('free 档')) return 'free 档只能使用 auto 模式。'
  return message
})

const sendDisabled = computed(
  () => sending.value || !question.value.trim() || Boolean(configHint.value),
)

onMounted(() => {
  void prepare()
  void account.fetchAccount()
  void account.fetchApiKeys()
  if (reader.mode === 'platform' && canPlatform.value) void reader.loadPlatformModels()
})

watch(
  () => props.bookId,
  () => {
    void prepare()
  },
)

watch(
  () => reader.mode,
  (next) => {
    if (next === 'platform') {
      if (canPlatform.value) void reader.loadPlatformModels()
      else if (planReady.value) reader.setMode('auto')
    }
  },
)

watch(
  () => account.plan,
  (plan) => {
    if (plan === 'free' && reader.mode === 'platform') reader.setMode('auto')
    if (plan && plan !== 'free' && reader.mode === 'platform') {
      void reader.loadPlatformModels()
    }
  },
)

function handleCite(citation: Citation) {
  emit('cite', citation)
}

function chooseMode(next: ChatMode) {
  if (next === 'platform' && !canPlatform.value) return
  reader.setMode(next)
}

function onModelChange(event: Event) {
  reader.setModel((event.target as HTMLSelectElement).value)
}

function onModelInput(event: Event) {
  reader.setModel((event.target as HTMLInputElement).value)
}

function onProviderChange(event: Event) {
  reader.setProvider((event.target as HTMLSelectElement).value as ApiProvider)
  inlineKey.value = ''
  keyError.value = ''
}

async function saveInlineKey() {
  const value = inlineKey.value.trim()
  if (!value || savingKey.value) return
  savingKey.value = true
  keyError.value = ''
  try {
    await account.saveApiKey(reader.provider, value)
    inlineKey.value = ''
  } catch (error) {
    keyError.value = errorMessage(error, '保存 Key 失败')
  } finally {
    savingKey.value = false
  }
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
  <aside class="chat-panel">
    <header class="chat-head">
      <div class="chat-title-row">
        <h2>文中助手</h2>
        <div class="chat-meta">
          <span
            v-if="account.account"
            class="credit-tag"
            :class="{ empty: account.credits < 1 }"
            :title="`${planLabel(account.plan)} · 剩余积分`"
          >
            积分 {{ account.credits }}
          </span>
          <span v-else-if="account.loading" class="credit-tag">账户…</span>
          <RouterLink v-else class="credit-tag" to="/settings">配置账户</RouterLink>
          <span v-if="reader.session" class="session-tag">#{{ reader.session.id }}</span>
        </div>
      </div>

      <div class="control-row">
        <span class="control-label">范围</span>
        <div class="segmented" role="group" aria-label="回答范围">
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

      <div class="control-row">
        <span class="control-label">模式</span>
        <div class="segmented mode-switch" role="group" aria-label="回答模式">
          <button
            type="button"
            :class="{ active: reader.mode === 'auto' }"
            :aria-pressed="reader.mode === 'auto'"
            @click="chooseMode('auto')"
          >
            自动
          </button>
          <button
            type="button"
            :class="{ active: reader.mode === 'platform' }"
            :aria-pressed="reader.mode === 'platform'"
            :disabled="!canPlatform"
            :title="canPlatform ? '选择平台模型' : 'free 档或账户未加载时不可用'"
            @click="chooseMode('platform')"
          >
            平台
          </button>
          <button
            type="button"
            :class="{ active: reader.mode === 'byok' }"
            :aria-pressed="reader.mode === 'byok'"
            @click="chooseMode('byok')"
          >
            BYOK
          </button>
        </div>
      </div>

      <p class="mode-hint">{{ modeHint }}</p>

      <div v-if="reader.mode === 'platform'" class="config-box">
        <div v-if="reader.modelsLoading" class="config-state">
          <span class="spinner sm"></span>
          正在加载平台模型…
        </div>
        <div v-else-if="reader.modelsError" class="config-state error">
          <span>{{ reader.modelsError }}</span>
          <button class="btn btn-ghost" type="button" @click="reader.loadPlatformModels(true)">
            重试
          </button>
        </div>
        <select
          v-else-if="reader.platformModels.length > 0"
          class="select"
          :value="reader.model"
          aria-label="平台模型"
          @change="onModelChange"
        >
          <option value="">选择平台模型</option>
          <option v-for="item in reader.platformModels" :key="`${item.provider}-${item.model}`" :value="item.model">
            {{ item.displayName || item.model }}
          </option>
        </select>
        <p v-else class="config-state">当前套餐暂无可用平台模型。</p>
      </div>

      <div v-if="reader.mode === 'byok'" class="config-box">
        <div class="config-row">
          <select
            class="select"
            :value="reader.provider"
            aria-label="BYOK 提供商"
            @change="onProviderChange"
          >
            <option v-for="item in BYOK_PROVIDERS" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
          <span v-if="activeKey" class="key-ok">
            {{ activeKey.keyMask }} · {{ keyStatusLabel(activeKey.status) }}
          </span>
        </div>

        <div v-if="account.keysLoading && !activeKey" class="config-state">
          <span class="spinner sm"></span>
          正在读取 Key…
        </div>
        <div v-else-if="!activeKey" class="key-entry">
          <input
            v-model="inlineKey"
            class="input"
            type="password"
            autocomplete="off"
            :placeholder="`粘贴 ${providerLabel(reader.provider)} API Key`"
            aria-label="API Key"
            @keydown.enter.prevent="saveInlineKey"
          />
          <button
            class="btn"
            type="button"
            :disabled="!inlineKey.trim() || savingKey"
            @click="saveInlineKey"
          >
            <span v-if="savingKey" class="spinner sm"></span>
            保存 Key
          </button>
        </div>

        <p v-if="keyError" class="config-error">{{ keyError }}</p>

        <input
          class="input"
          :value="reader.model"
          placeholder="模型 ID，例如 gpt-4o-mini"
          aria-label="BYOK 模型 ID"
          @input="onModelInput"
        />
        <p class="config-sub">
          保存后只显示掩码，可在 <RouterLink to="/settings">设置</RouterLink> 中管理。
        </p>
      </div>

      <p v-if="configHint" class="config-hint">{{ configHint }}</p>
      <p v-if="account.error" class="config-hint">
        {{ account.error }}
        <button class="link-btn" type="button" @click="account.fetchAccount(true)">重试</button>
      </p>
      <p v-if="account.keysError" class="config-hint">
        {{ account.keysError }}
        <button class="link-btn" type="button" @click="account.fetchApiKeys(true)">重试</button>
      </p>
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
        placeholder="就这本书提问…"
        :disabled="reader.asking"
        @keydown="handleKeydown"
      ></textarea>
      <div class="composer-row">
        <span class="hint">Enter 发送 · Shift+Enter 换行</span>
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
    </footer>
  </aside>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--surface);
}

.chat-head {
  flex: none;
  max-height: 54%;
  overflow-y: auto;
  padding: 14px 16px 12px;
  border-bottom: 1px solid var(--border);
  overscroll-behavior: contain;
}

.chat-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.chat-head h2 {
  font-size: 15px;
  font-weight: 600;
}

.chat-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.credit-tag {
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}

.credit-tag.empty {
  border-color: color-mix(in srgb, var(--danger) 35%, var(--border));
  background: var(--danger-soft);
  color: var(--danger);
}

.session-tag {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 62px;
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

.segmented {
  display: flex;
  flex: 1;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
}

.segmented button {
  flex: 1;
  padding: 4px 8px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  transition: background-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.segmented button:hover:not(:disabled) {
  color: var(--text);
}

.segmented button.active {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: var(--shadow-sm);
}

.segmented button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.mode-hint {
  margin-top: 8px;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--text-muted);
}

.config-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-2);
}

.config-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.select {
  width: 100%;
  min-width: 0;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-size: 12.5px;
}

.select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.config-state {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.config-state.error {
  justify-content: space-between;
  color: var(--danger);
}

.config-state .btn {
  padding: 3px 8px;
  font-size: 11.5px;
  color: var(--danger);
}

.key-ok {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11.5px;
  color: var(--text-secondary);
}

.key-entry {
  display: flex;
  gap: 6px;
}

.key-entry .input {
  flex: 1;
  min-width: 0;
  padding: 7px 9px;
  font-size: 12px;
}

.key-entry .btn {
  flex: none;
  padding: 6px 10px;
  font-size: 11.5px;
}

.config-box .input {
  padding: 7px 9px;
  font-size: 12.5px;
}

.config-sub {
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-muted);
}

.config-sub a {
  color: var(--accent);
}

.config-error {
  font-size: 11.5px;
  color: var(--danger);
}

.config-hint {
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 7px;
  background: var(--accent-soft);
  color: var(--text-secondary);
  font-size: 11.5px;
  line-height: 1.5;
}

.link-btn {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--accent);
  font-size: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.session-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 14px 8px;
  padding: 8px 10px;
  border-radius: 9px;
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
  padding: 12px 14px 14px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}

.composer-input {
  display: block;
  width: 100%;
  min-height: 70px;
  max-height: 160px;
  padding: 10px 12px;
  resize: vertical;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-2);
  font-size: 14px;
  line-height: 1.65;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
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

.composer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 9px;
}

.hint {
  font-size: 11px;
  color: var(--text-muted);
}

.send-btn {
  min-width: 78px;
  padding: 8px 16px;
  font-size: 13.5px;
}

@media (max-width: 1000px) {
  .chat-head {
    max-height: 48%;
  }
}
</style>