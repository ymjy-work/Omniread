<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ModelPicker from '../components/ModelPicker.vue'
import UserTopbar from '../components/UserTopbar.vue'
import { errorMessage } from '../api/request'
import { useAccountStore } from '../stores/account'
import { useAuthStore } from '../stores/auth'
import { useReaderStore } from '../stores/reader'
import { useSettingsStore } from '../stores/settings'
import {
  BYOK_PROVIDERS,
  formatCredits,
  formatDate,
  formatMoney,
  keyStatusLabel,
  planLabel,
  providerLabel,
} from '../utils/billing'
import type { ApiProvider } from '../types/account'
import type { ThemeName } from '../stores/settings'

const account = useAccountStore()
const auth = useAuthStore()
const reader = useReaderStore()
const settings = useSettingsStore()

const themes: { value: ThemeName; label: string; desc: string }[] = [
  { value: 'light', label: '明亮', desc: '纸白' },
  { value: 'sepia', label: '护眼', desc: '暖黄' },
  { value: 'dark', label: '夜间', desc: '低亮墨色' },
]

const keyProvider = ref<ApiProvider>(reader.provider)
const keyInput = ref('')
const savingKey = ref(false)
const keyError = ref('')
const keyMessage = ref('')
const pendingDelete = ref<ApiProvider | null>(null)
const deletingKey = ref<ApiProvider | ''>('')

const isFree = computed(() => account.plan === 'free')
const hasProviderKey = computed(() => account.hasKey(reader.provider))
const selectedKey = computed(() =>
  account.apiKeys.find((item) => item.provider === keyProvider.value),
)

const preferenceHint = computed(() => {
  if (reader.surface === 'official') {
    if (!account.account) {
      return account.error ? '账户信息加载失败。' : '正在读取账户…'
    }
    if (isFree.value) return 'Free 档自动路由，无需选择模型。'
    if (reader.modelsLoading) return '正在加载平台模型…'
    if (reader.modelsError) return reader.modelsError
    if (reader.platformModels.length === 0) return '当前套餐暂无可用平台模型。'
    if (!reader.model) return '请选择默认平台模型。'
    return '当前配置可用。'
  }

  if (account.keysLoading && !account.keysLoaded) return '正在读取 API Key…'
  if (!hasProviderKey.value) return '请先保存该提供商的 Key。'
  if (reader.providerModelsLoading) return '正在拉取模型…'
  if (reader.providerModelsError) return reader.providerModelsError
  return '当前配置可用。'
})



const preferenceTone = computed(() => {
  if (
    preferenceHint.value === '当前配置可用。' ||
    preferenceHint.value === 'Free 档自动路由，无需选择模型。'
  ) {
    return 'ok'
  }
  return preferenceHint.value.includes('正在') ? 'info' : 'warning'
})

onMounted(async () => {
  await Promise.all([account.fetchAccount(), account.fetchApiKeys()])
  if (reader.surface === 'official' && account.plan && account.plan !== 'free') {
    void reader.loadPlatformModels(true)
  }
})

watch(
  () => account.plan,
  (plan) => {
    if (plan && plan !== 'free' && reader.surface === 'official') {
      void reader.loadPlatformModels(true)
    }
  },
)

function onFontInput(event: Event) {
  const target = event.target as HTMLInputElement
  settings.setFontSize(Number(target.value))
}

function onKeyProviderChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value as ApiProvider
  keyProvider.value = value
  reader.setProvider(value)
  keyError.value = ''
  keyMessage.value = ''
}

async function saveKey() {
  const value = keyInput.value.trim()
  if (!value || savingKey.value) return
  savingKey.value = true
  keyError.value = ''
  keyMessage.value = ''
  try {
    await account.saveApiKey(keyProvider.value, value)
    keyInput.value = ''
    keyMessage.value = `已保存 ${providerLabel(keyProvider.value)} Key，仅显示掩码。`
  } catch (error) {
    keyError.value = errorMessage(error, '保存 Key 失败')
  } finally {
    savingKey.value = false
  }
}

function requestDelete(provider: ApiProvider) {
  pendingDelete.value = provider
  keyError.value = ''
  keyMessage.value = ''
}

async function confirmDelete(provider: ApiProvider) {
  if (deletingKey.value) return
  deletingKey.value = provider
  keyError.value = ''
  keyMessage.value = ''
  try {
    await account.deleteApiKey(provider)
    pendingDelete.value = null
    keyMessage.value = `已删除 ${providerLabel(provider)} Key。`
  } catch (error) {
    keyError.value = errorMessage(error, '删除 Key 失败')
  } finally {
    deletingKey.value = ''
  }
}
</script>

<template>
  <div class="settings-page">
    <UserTopbar active="settings" />

    <main class="settings-main">
      <header class="page-head">
        <p class="eyebrow">SETTINGS</p>
        <h1>设置</h1>
        <p class="page-desc">阅读偏好、账户与模型。</p>
      </header>

      <section class="panel">
        <div class="panel-head">
          <h2>网页设置</h2>
          <p>调整页面底色与正文大小，选择后立即生效。</p>
        </div>

        <div class="theme-options">
          <button
            v-for="item in themes"
            :key="item.value"
            class="theme-option"
            :class="[`swatch-${item.value}`, { active: settings.theme === item.value }]"
            type="button"
            :aria-pressed="settings.theme === item.value"
            @click="settings.setTheme(item.value)"
          >
            <span class="swatch" aria-hidden="true"></span>
            <span class="theme-label">{{ item.label }}</span>
            <span class="theme-desc">{{ item.desc }}</span>
          </button>
        </div>

        <div class="font-block">
          <div class="font-head">
            <h3>正文字号</h3>
            <span>{{ settings.fontSize }}px</span>
          </div>
          <div class="font-row">
            <span class="font-edge" aria-hidden="true">A</span>
            <input
              class="font-slider"
              type="range"
              :min="settings.minFont"
              :max="settings.maxFont"
              step="1"
              :value="settings.fontSize"
              aria-label="正文字号"
              @input="onFontInput"
            />
            <span class="font-edge large" aria-hidden="true">A</span>
          </div>
          <div class="preview">
            <p class="preview-text">
              夜色从窗沿退去，书页上的字仍停在原处。读到一半的句子，会在下一次打开时继续。
            </p>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head panel-head-inline">
          <div>
            <h2>用户信息</h2>
            <p>账号资料与当前套餐摘要。购买与续费在套餐页完成。</p>
          </div>
          <RouterLink class="btn" to="/plans">查看套餐</RouterLink>
        </div>

        <div v-if="account.loading && !account.account" class="inline-state">
          <span class="spinner"></span>
          正在读取账户…
        </div>

        <div v-else-if="account.account" class="info-grid">
          <div class="info-item">
            <span>用户名</span>
            <strong>{{ auth.user?.username || '—' }}</strong>
          </div>
          <div class="info-item">
            <span>展示名</span>
            <strong>{{ auth.user?.displayName || '未设置' }}</strong>
          </div>
          <div class="info-item">
            <span>当前档位</span>
            <strong>{{ planLabel(account.plan) }}</strong>
          </div>
          <div class="info-item">
            <span>剩余积分</span>
            <strong :class="{ danger: account.credits < 1 }">{{ formatCredits(account.credits) }}</strong>
          </div>
          <div class="info-item">
            <span>余额</span>
            <strong>{{ formatMoney(account.balance) }}</strong>
          </div>
          <div class="info-item">
            <span>到期时间</span>
            <strong>{{ formatDate(account.planExpiresAt) }}</strong>
          </div>
        </div>

        <div v-else class="inline-state">
          <span class="error-text">{{ account.error || '账户信息不可用' }}</span>
          <button class="btn" type="button" @click="account.fetchAccount(true)">重试</button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>模型配置</h2>
          <p>BYOK Key 只显示掩码；默认模型偏好会用于阅读器对话。</p>
        </div>

        <div v-if="account.keysLoading && account.apiKeys.length === 0" class="inline-state">
          <span class="spinner"></span>
          正在读取 Key…
        </div>

        <div v-else-if="account.keysError" class="inline-state">
          <span class="error-text">{{ account.keysError }}</span>
          <button class="btn" type="button" @click="account.fetchApiKeys(true)">重试</button>
        </div>

        <div v-else class="key-list">
          <div v-for="key in account.apiKeys" :key="key.provider" class="key-row">
            <div class="key-main">
              <strong>{{ providerLabel(key.provider) }}</strong>
              <code>{{ key.keyMask }}</code>
              <span class="key-status">{{ keyStatusLabel(key.status) }}</span>
            </div>
            <div v-if="pendingDelete === key.provider" class="key-actions">
              <span class="confirm-text">确认删除？</span>
              <button
                class="btn danger-btn"
                type="button"
                :disabled="deletingKey === key.provider"
                @click="confirmDelete(key.provider)"
              >
                {{ deletingKey === key.provider ? '删除中…' : '删除' }}
              </button>
              <button class="btn btn-ghost" type="button" @click="pendingDelete = null">取消</button>
            </div>
            <button v-else class="btn" type="button" @click="requestDelete(key.provider)">删除</button>
          </div>
          <p v-if="account.apiKeys.length === 0" class="inline-state">还没有保存的 Key。</p>
        </div>

        <form class="key-form" @submit.prevent="saveKey">
          <label class="key-field">
            <span>提供商</span>
            <select class="select" :value="keyProvider" @change="onKeyProviderChange">
              <option v-for="item in BYOK_PROVIDERS" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <label class="key-field key-field-main">
            <span>API Key</span>
            <input
              v-model="keyInput"
              class="input"
              type="password"
              autocomplete="off"
              placeholder="粘贴新的 Key，保存后只显示掩码"
            />
          </label>
          <button class="btn btn-primary" type="submit" :disabled="savingKey || !keyInput.trim()">
            <span v-if="savingKey" class="spinner sm"></span>
            保存 Key
          </button>
        </form>

        <p v-if="selectedKey" class="key-note">
          {{ providerLabel(keyProvider) }} 已保存 {{ selectedKey.keyMask }}，再次保存会覆盖。
        </p>
        <p class="key-note">Key 只在请求时解密传给模型服务，页面只显示掩码。</p>

        <div class="preference-block">
          <div class="preference-head">
            <div>
              <h3>默认模型偏好</h3>
              <p>阅读页与设置页共用同一份选择。</p>
            </div>
          </div>

          <ModelPicker wide />

          <p
            class="preference-hint"
            :class="preferenceTone"
            role="status"
          >
            {{ preferenceHint }}
          </p>
        </div>

        <p v-if="keyError" class="notice error" role="alert">{{ keyError }}</p>
        <p v-if="keyMessage" class="notice success" role="status">{{ keyMessage }}</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.settings-page {
  min-height: 100dvh;
  background: var(--bg);
}

.settings-main {
  width: min(1000px, 100%);
  margin: 0 auto;
  padding: clamp(28px, 5vw, 56px) clamp(18px, 4vw, 48px) 80px;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.page-head {
  margin-bottom: var(--space-2);
}

.eyebrow {
  margin-bottom: 10px;
  color: var(--text-muted);
  font-size: var(--text-xs);
  letter-spacing: 0.26em;
}

.page-head h1 {
  font-family: var(--font-serif);
  font-size: var(--text-xl);
  font-weight: 600;
}

.page-desc {
  margin-top: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--text-base);
}

.panel {
  padding: clamp(20px, 3vw, 28px);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.panel-head {
  margin-bottom: var(--space-4);
}

.panel-head-inline {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
}

.panel-head h2 {
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 600;
}

.panel-head p {
  margin-top: var(--space-1);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.inline-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: var(--space-5) var(--space-3);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.theme-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3);
}

.theme-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
  text-align: left;
  transition: border-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}

.theme-option:hover {
  border-color: var(--border-strong);
}

.theme-option.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.swatch {
  display: block;
  width: 100%;
  height: 46px;
  margin-bottom: var(--space-2);
  border: 1px solid color-mix(in srgb, var(--text) 10%, transparent);
  border-radius: var(--radius-sm);
}

.swatch-light .swatch {
  background: linear-gradient(
    135deg,
    var(--swatch-light-bg) 48%,
    var(--swatch-light-surface) 52%
  );
}

.swatch-sepia .swatch {
  background: linear-gradient(
    135deg,
    var(--swatch-sepia-bg) 48%,
    var(--swatch-sepia-surface) 52%
  );
}

.swatch-dark .swatch {
  background: linear-gradient(
    135deg,
    var(--swatch-dark-bg) 48%,
    var(--swatch-dark-surface) 52%
  );
}

.theme-label {
  font-size: var(--text-base);
  font-weight: 600;
}

.theme-desc {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.font-block {
  margin-top: var(--space-5);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border);
}

.font-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.font-head h3 {
  font-size: var(--text-base);
  font-weight: 600;
}

.font-head span {
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}

.font-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.font-edge {
  color: var(--text-muted);
  font-size: 13px;
}

.font-edge.large {
  font-size: 21px;
}

.font-slider {
  flex: 1;
  accent-color: var(--accent);
  cursor: pointer;
}

.preview {
  margin-top: var(--space-4);
  padding: var(--space-4) var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--reader-bg);
}

.preview-text {
  color: var(--reader-text);
  font-family: var(--font-serif);
  font-size: var(--reader-font-size);
  line-height: var(--reading-leading);
  letter-spacing: 0.012em;
  text-align: justify;
  text-indent: 2em;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
}

.info-item span {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.info-item strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.info-item strong.danger {
  color: var(--danger);
}

.key-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.key-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 10px var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
}

.key-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  min-width: 0;
}

.key-main strong {
  font-size: 13px;
}

.key-main code {
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 11.5px;
}

.key-status {
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  color: var(--text-muted);
  font-size: 10px;
}

.key-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.confirm-text {
  color: var(--danger);
  font-size: 11px;
}

.key-actions .btn,
.key-row .btn {
  padding: 4px 9px;
  font-size: 11.5px;
}

.danger-btn {
  border-color: color-mix(in srgb, var(--danger) 40%, var(--border));
  color: var(--danger);
}

.key-form {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.key-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 130px;
}

.key-field span {
  color: var(--text-muted);
  font-size: 11.5px;
}

.key-field-main {
  flex: 1;
  min-width: 180px;
}

.key-form > .btn {
  height: 34px;
  font-size: var(--text-sm);
}

.key-note {
  margin-top: 10px;
  color: var(--text-muted);
  font-size: 11.5px;
}

.preference-block {
  margin-top: var(--space-5);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border);
}

.preference-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-3);
}

.preference-head h3 {
  font-size: 13.5px;
  font-weight: 600;
}

.preference-head p {
  margin-top: var(--space-1);
  color: var(--text-muted);
  font-size: 11.5px;
}

.preference-hint {
  margin-top: var(--space-3);
  color: var(--text-muted);
  font-size: var(--text-sm);
  line-height: 1.5;
}

.preference-hint.ok {
  color: var(--success);
}

.preference-hint.info {
  color: var(--text-muted);
}

.preference-hint.warning {
  color: var(--warning);
}

.notice {
  margin-top: var(--space-3);
  padding: 9px 11px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  line-height: 1.55;
}

.notice.error {
  background: var(--danger-soft);
  color: var(--danger);
}

.notice.success {
  background: var(--success-soft);
  color: var(--success);
}

@media (max-width: 820px) {
  .info-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .theme-options,
  .info-grid {
    grid-template-columns: 1fr;
  }

  .theme-option {
    flex-direction: row;
    align-items: center;
    gap: var(--space-3);
  }

  .swatch {
    width: 54px;
    height: 36px;
    margin: 0;
    flex: none;
  }

  .theme-desc {
    margin-left: auto;
  }

  .panel-head-inline,
  .preference-head {
    flex-direction: column;
  }

  .key-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>