<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { errorMessage } from '../api/errors'
import { useAccountStore } from '../stores/account'
import { useReaderStore } from '../stores/reader'
import { keyStatusLabel, providerLabel } from '../utils/billing'

const account = useAccountStore()
const reader = useReaderStore()

const keyInput = ref('')
const savingKey = ref(false)
const deletingKey = ref(false)
const confirmDelete = ref(false)
const keyError = ref('')
const keyMessage = ref('')

const activeKey = computed(() =>
  account.apiKeys.find((item) => item.provider === reader.provider),
)
const keyLoading = computed(() => account.keysLoading && !account.keysLoaded)

watch(
  () => reader.provider,
  () => {
    keyInput.value = ''
    confirmDelete.value = false
    keyError.value = ''
    keyMessage.value = ''
  },
)

onMounted(() => {
  if (!account.keysLoaded && !account.keysLoading) void account.fetchApiKeys()
})

async function saveKey() {
  const value = keyInput.value.trim()
  if (!value || savingKey.value) return
  savingKey.value = true
  keyError.value = ''
  keyMessage.value = ''
  confirmDelete.value = false
  try {
    await account.saveApiKey(reader.provider, value)
    keyInput.value = ''
    keyMessage.value = `已保存 ${providerLabel(reader.provider)} Key。`
  } catch (error) {
    keyError.value = errorMessage(error, '保存 Key 失败')
  } finally {
    savingKey.value = false
  }
}

async function deleteKey() {
  if (deletingKey.value) return
  deletingKey.value = true
  keyError.value = ''
  keyMessage.value = ''
  try {
    await account.deleteApiKey(reader.provider)
    confirmDelete.value = false
    keyMessage.value = `已删除 ${providerLabel(reader.provider)} Key。`
  } catch (error) {
    keyError.value = errorMessage(error, '删除 Key 失败')
  } finally {
    deletingKey.value = false
  }
}
</script>

<template>
  <section class="byok-panel" aria-label="BYOK 凭据">
    <div class="key-summary">
      <div class="key-name">
        <span>{{ providerLabel(reader.provider) }}</span>
        <span v-if="keyLoading" class="key-state">读取中…</span>
        <code v-else-if="activeKey">{{ activeKey.keyMask }}</code>
        <span v-else class="key-state missing">未保存</span>
      </div>

      <div v-if="activeKey" class="key-actions">
        <span class="key-status">{{ keyStatusLabel(activeKey.status) }}</span>
        <template v-if="confirmDelete">
          <button class="danger-btn" type="button" :disabled="deletingKey" @click="deleteKey">
            {{ deletingKey ? '删除中…' : '确认删除' }}
          </button>
          <button type="button" @click="confirmDelete = false">取消</button>
        </template>
        <button v-else type="button" class="danger-link" @click="confirmDelete = true">删除</button>
      </div>
    </div>

    <div v-if="account.keysError && !keyLoading" class="key-problem" role="alert">
      <span>{{ account.keysError }}</span>
      <button type="button" @click="account.fetchApiKeys(true)">重试</button>
    </div>

    <form class="key-form" @submit.prevent="saveKey">
      <label class="sr-only" for="byok-key">API Key</label>
      <input
        id="byok-key"
        v-model="keyInput"
        class="key-input"
        type="password"
        autocomplete="off"
        placeholder="粘贴 API Key，保存后只显示掩码"
      />
      <button class="save-key" type="submit" :disabled="savingKey || !keyInput.trim()">
        {{ savingKey ? '保存中…' : '保存' }}
      </button>
    </form>

    <p v-if="keyError" class="key-message error" role="alert">{{ keyError }}</p>
    <p v-else-if="keyMessage" class="key-message success" role="status">{{ keyMessage }}</p>
    <p v-else class="key-note">Key 仅在请求时解密，页面只保留掩码。</p>
  </section>
</template>

<style scoped>
.byok-panel {
  width: 100%;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.key-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
  min-height: 22px;
}

.key-name,
.key-actions {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.key-name > span:first-child {
  flex: none;
  color: var(--text);
  font-size: 10.5px;
  font-weight: 600;
}

.key-name code,
.key-state {
  overflow: hidden;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 9.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.key-state.missing {
  color: var(--warning);
}

.key-status {
  color: var(--success);
  font-size: 9.5px;
}

.key-actions button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: 9.5px;
}

.key-actions .danger-link {
  color: var(--danger);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.key-actions .danger-btn {
  color: var(--danger);
}

.key-problem {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  color: var(--danger);
  font-size: 9.5px;
}

.key-problem button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: inherit;
  text-decoration: underline;
}

.key-form {
  display: flex;
  gap: 5px;
  margin-top: 6px;
}

.key-input {
  flex: 1;
  min-width: 0;
  height: 26px;
  padding: 2px 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: var(--surface);
  font-size: 10px;
}

.key-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.key-input::placeholder {
  color: var(--text-muted);
}

.save-key {
  flex: none;
  height: 26px;
  padding: 0 9px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-xs);
  background: var(--surface);
  color: var(--text);
  font-size: 10px;
}

.save-key:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.key-message,
.key-note {
  margin-top: 5px;
  font-size: 9.5px;
  line-height: 1.45;
}

.key-message.error {
  color: var(--danger);
}

.key-message.success {
  color: var(--success);
}

.key-note {
  color: var(--text-muted);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
