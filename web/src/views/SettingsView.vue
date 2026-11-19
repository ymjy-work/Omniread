<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage } from '../api/request'
import { useAccountStore } from '../stores/account'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import {
  BYOK_PROVIDERS,
  PLAN_ORDER,
  formatCredits,
  formatDate,
  formatMoney,
  keyStatusLabel,
  planLabel,
  providerLabel,
} from '../utils/billing'
import type { ApiProvider, PlanCatalog, PlanCode } from '../types/account'
import type { ThemeName } from '../stores/settings'

const account = useAccountStore()
const auth = useAuthStore()
const settings = useSettingsStore()
const router = useRouter()

const themes: { value: ThemeName; label: string; desc: string }[] = [
  { value: 'light', label: '明亮', desc: '清爽纸白' },
  { value: 'sepia', label: '护眼', desc: '暖黄纸页' },
  { value: 'dark', label: '夜间', desc: '低亮墨色' },
]

const purchasing = ref<PlanCode | ''>('')
const purchaseError = ref('')
const purchaseMessage = ref('')

const keyProvider = ref<ApiProvider>('bailian')
const keyInput = ref('')
const savingKey = ref(false)
const keyError = ref('')
const keyMessage = ref('')
const pendingDelete = ref<ApiProvider | null>(null)
const deletingKey = ref<ApiProvider | ''>('')

const plans = computed(() =>
  [...account.plans].sort(
    (a, b) => PLAN_ORDER.indexOf(a.code) - PLAN_ORDER.indexOf(b.code),
  ),
)

const selectedKey = computed(() =>
  account.apiKeys.find((item) => item.provider === keyProvider.value),
)

onMounted(() => {
  void account.fetchAccount()
  void account.fetchPlans()
  void account.fetchApiKeys()
})

function onFontInput(event: Event) {
  const target = event.target as HTMLInputElement
  settings.setFontSize(Number(target.value))
}

function onKeyProviderChange(event: Event) {
  keyProvider.value = (event.target as HTMLSelectElement).value as ApiProvider
  keyError.value = ''
}

async function buyPlan(plan: PlanCatalog) {
  if (plan.code === 'free' || purchasing.value) return
  purchaseError.value = ''
  purchaseMessage.value = ''

  if (!account.account) await account.fetchAccount(true)
  if (!account.account) {
    purchaseError.value = '账户信息尚未加载，请稍后重试。'
    return
  }
  if (account.balance < plan.price) {
    purchaseError.value = `余额不足：当前余额 ${formatMoney(account.balance)}，购买 ${planLabel(plan.code)} 需要 ${formatMoney(plan.price)}。请联系管理员充值。`
    return
  }

  purchasing.value = plan.code
  try {
    await account.purchasePlan(plan.code)
    purchaseMessage.value = `已开通 ${planLabel(plan.code)}，积分已重置为 ${formatCredits(plan.credits)}。`
  } catch (error) {
    purchaseError.value = errorMessage(error, '套餐购买失败')
  } finally {
    purchasing.value = ''
  }
}

function planButtonText(plan: PlanCatalog) {
  if (plan.code === 'free') return '默认档位'
  if (account.plan === plan.code) return '续费'
  return '购买'
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

async function handleLogout() {
  await auth.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="settings-page">
    <header class="topbar">
      <RouterLink class="brand" to="/">
        <span class="brand-mark">阅</span>
        <span class="brand-name">Omniread</span>
      </RouterLink>
      <div class="topbar-actions">
        <span v-if="account.account" class="quota-chip">
          {{ planLabel(account.plan) }} · 积分 {{ formatCredits(account.credits) }}
        </span>
        <RouterLink class="btn btn-ghost" to="/">返回书库</RouterLink>
      </div>
    </header>

    <main class="settings-main">
      <header class="page-head">
        <p class="eyebrow">ACCOUNT &amp; PREFERENCES</p>
        <h1>账户与设置</h1>
        <p class="page-desc">套餐、积分、BYOK 与阅读偏好。</p>
      </header>

      <section class="panel">
        <div class="panel-head panel-head-inline">
          <div>
            <h2>我的账户</h2>
            <p>余额只用于购买套餐，积分用于平台回答。</p>
          </div>
          <RouterLink v-if="account.isAdmin" class="btn" to="/admin">用户管理</RouterLink>
        </div>

        <div v-if="account.loading && !account.account" class="inline-state">
          <span class="spinner"></span>
          正在读取账户…
        </div>

        <div v-else-if="account.account" class="account-grid">
          <div class="account-item">
            <span>当前档位</span>
            <strong>{{ planLabel(account.plan) }}</strong>
          </div>
          <div class="account-item">
            <span>剩余积分</span>
            <strong :class="{ danger: account.credits < 1 }">{{ formatCredits(account.credits) }}</strong>
          </div>
          <div class="account-item">
            <span>余额</span>
            <strong>{{ formatMoney(account.balance) }}</strong>
          </div>
          <div class="account-item">
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
          <h2>套餐购买</h2>
          <p>使用余额购买，立即开启 1 个月新周期，积分按档位重置。</p>
        </div>

        <div v-if="account.plansLoading" class="inline-state">
          <span class="spinner"></span>
          正在加载套餐…
        </div>

        <div v-else-if="account.plansError" class="inline-state">
          <span class="error-text">{{ account.plansError }}</span>
          <button class="btn" type="button" @click="account.fetchPlans(true)">重试</button>
        </div>

        <p v-else-if="plans.length === 0" class="inline-state">暂无套餐信息。</p>

        <div v-else class="plan-grid">
          <article
            v-for="plan in plans"
            :key="plan.code"
            class="plan-card"
            :class="{ current: account.plan === plan.code }"
          >
            <header class="plan-head">
              <div>
                <h3>{{ planLabel(plan.code) }}<span v-if="account.plan === plan.code" class="plan-current">当前</span></h3>
                <p>{{ formatCredits(plan.credits) }} 积分 / {{ plan.durationDays }} 天</p>
              </div>
              <p class="plan-price">
                {{ plan.price === 0 ? '免费' : formatMoney(plan.price) }}
                <span v-if="plan.price > 0">/月</span>
              </p>
            </header>
            <ul class="plan-perks">
              <li>周期内 {{ formatCredits(plan.credits) }} 积分</li>
              <li>{{ plan.code === 'free' ? '到期自动续 Free' : '到期未续回落 Free' }}</li>
              <li>{{ plan.code === 'free' ? '仅自动模式' : '可选平台模型' }}</li>
            </ul>
            <p
              v-if="plan.code !== 'free' && account.account && account.balance < plan.price"
              class="plan-shortage"
            >
              余额不足
            </p>
            <button
              class="btn plan-buy"
              :class="{ 'btn-primary': account.plan !== plan.code && plan.code !== 'free' }"
              type="button"
              :disabled="plan.code === 'free' || purchasing === plan.code"
              @click="buyPlan(plan)"
            >
              <span v-if="purchasing === plan.code" class="spinner sm"></span>
              {{ purchasing === plan.code ? '处理中…' : planButtonText(plan) }}
            </button>
          </article>
        </div>

        <p v-if="purchaseError" class="notice error" role="alert">{{ purchaseError }}</p>
        <p v-if="purchaseMessage" class="notice success" role="status">{{ purchaseMessage }}</p>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>BYOK API Key</h2>
          <p>使用自己的 Key 回答不消耗积分；保存后只显示掩码。</p>
        </div>

        <div v-if="account.keysLoading" class="inline-state">
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
              placeholder="粘贴新的 Key，保存后不回显"
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
        <p v-if="keyError" class="notice error" role="alert">{{ keyError }}</p>
        <p v-if="keyMessage" class="notice success" role="status">{{ keyMessage }}</p>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>主题</h2>
          <p>调整页面与正文的底色。</p>
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
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>正文字号</h2>
          <p>当前 {{ settings.fontSize }}px，保存后立即生效。</p>
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
      </section>

      <section class="panel account-panel">
        <div>
          <h2>账号</h2>
          <p class="account-name">{{ auth.displayName }}</p>
        </div>
        <button class="btn" type="button" @click="handleLogout">退出登录</button>
      </section>
    </main>
  </div>
</template>

<style scoped>
.settings-page {
  min-height: 100dvh;
  background: var(--bg);
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: var(--header-height);
  padding: 0 clamp(18px, 4vw, 48px);
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: blur(12px);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--text);
  color: var(--bg);
  font-family: var(--font-serif);
  font-size: 18px;
}

.brand-name {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.quota-chip {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 11.5px;
  white-space: nowrap;
}

.settings-main {
  width: min(820px, 100%);
  margin: 0 auto;
  padding: clamp(28px, 5vw, 56px) clamp(18px, 4vw, 48px) 80px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.page-head {
  margin-bottom: 8px;
}

.eyebrow {
  margin-bottom: 10px;
  font-size: 11px;
  letter-spacing: 0.26em;
  color: var(--text-muted);
}

.page-head h1 {
  font-family: var(--font-serif);
  font-size: clamp(30px, 4vw, 40px);
  font-weight: 600;
}

.page-desc {
  margin-top: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.panel {
  padding: clamp(20px, 3vw, 28px);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.panel-head {
  margin-bottom: 20px;
}

.panel-head-inline {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel h2 {
  font-size: 16px;
  font-weight: 600;
}

.panel-head p {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.account-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.account-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
}

.account-item span {
  font-size: 11.5px;
  color: var(--text-muted);
}

.account-item strong {
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 600;
}

.account-item strong.danger {
  color: var(--danger);
}

.inline-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 22px 12px;
  font-size: 13px;
  color: var(--text-secondary);
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.plan-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
}

.plan-card.current {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.plan-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.plan-head h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
}

.plan-current {
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--accent);
  color: #fff;
  font-size: 9px;
  font-weight: 500;
}

.plan-head p {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-muted);
}

.plan-price {
  font-family: var(--font-serif);
  font-size: 18px;
  white-space: nowrap;
}

.plan-price span {
  font-family: var(--font-sans);
  font-size: 10px;
  color: var(--text-muted);
}

.plan-perks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.plan-perks li::before {
  content: '·';
  margin-right: 5px;
  color: var(--accent);
}

.plan-shortage {
  font-size: 11px;
  color: var(--danger);
}

.plan-buy {
  margin-top: auto;
  padding: 7px 10px;
  font-size: 12px;
}

.notice {
  margin-top: 12px;
  padding: 9px 11px;
  border-radius: 9px;
  font-size: 12.5px;
  line-height: 1.55;
}

.notice.error {
  background: var(--danger-soft);
  color: var(--danger);
}

.notice.success {
  background: var(--accent-soft);
  color: var(--text-secondary);
}

.key-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.key-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
}

.key-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.key-main strong {
  font-size: 13px;
}

.key-main code {
  padding: 2px 6px;
  border-radius: 5px;
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 11.5px;
}

.key-status {
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
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
  font-size: 11px;
  color: var(--danger);
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
  gap: 8px;
  flex-wrap: wrap;
}

.key-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 130px;
}

.key-field span {
  font-size: 11.5px;
  color: var(--text-muted);
}

.key-field-main {
  flex: 1;
  min-width: 180px;
}

.select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
}

.select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.key-form .input {
  padding: 8px 10px;
  font-size: 13px;
}

.key-form > .btn {
  padding: 9px 14px;
  font-size: 12.5px;
}

.key-note {
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--text-muted);
}

.theme-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.theme-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
  text-align: left;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
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
  margin-bottom: 8px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.08);
}

.swatch-light .swatch {
  background: linear-gradient(135deg, #f3f1ec 48%, #ffffff 52%);
}

.swatch-sepia .swatch {
  background: linear-gradient(135deg, #ece2cd 48%, #f8f1e0 52%);
}

.swatch-dark .swatch {
  background: linear-gradient(135deg, #141619 48%, #2b3036 52%);
}

.theme-label {
  font-size: 14px;
  font-weight: 600;
}

.theme-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.font-row {
  display: flex;
  align-items: center;
  gap: 14px;
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
  margin-top: 20px;
  padding: 20px 22px;
  border-radius: var(--radius-md);
  background: var(--reader-bg);
  border: 1px solid var(--border);
}

.preview-text {
  font-family: var(--font-serif);
  font-size: var(--reader-font-size);
  line-height: 1.9;
  color: var(--reader-text);
  text-align: justify;
  text-indent: 2em;
}

.account-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.account-name {
  margin-top: 6px;
  font-size: 14px;
  color: var(--text-secondary);
}

@media (max-width: 820px) {
  .account-grid,
  .plan-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .quota-chip {
    display: none;
  }

  .account-grid,
  .plan-grid {
    grid-template-columns: 1fr;
  }

  .theme-options {
    grid-template-columns: 1fr;
  }

  .theme-option {
    flex-direction: row;
    align-items: center;
    gap: 12px;
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

  .key-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>