<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAccountStore } from '../stores/account'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import type { ThemeName } from '../stores/settings'
import { formatCredits, formatDate, formatMoney, planLabel } from '../utils/billing'

const themes: { value: ThemeName; label: string }[] = [
  { value: 'light', label: '明亮' },
  { value: 'sepia', label: '护眼' },
  { value: 'dark', label: '夜间' },
]

const router = useRouter()
const account = useAccountStore()
const auth = useAuthStore()
const settings = useSettingsStore()

const root = ref<HTMLElement | null>(null)
const open = ref(false)
const loggingOut = ref(false)

const initial = computed(() => auth.displayName.trim().charAt(0) || '阅')

function close() {
  open.value = false
}

function toggle() {
  open.value = !open.value
}

function onDocumentPointerDown(event: PointerEvent) {
  if (!open.value) return
  const target = event.target
  if (target instanceof Node && root.value?.contains(target)) return
  close()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}

function onFontInput(event: Event) {
  settings.setFontSize(Number((event.target as HTMLInputElement).value))
}

async function logout() {
  if (loggingOut.value) return
  loggingOut.value = true
  close()
  await auth.logout()
  await router.replace({ name: 'login' })
  loggingOut.value = false
}

watch(open, (value) => {
  if (value) {
    document.addEventListener('pointerdown', onDocumentPointerDown)
    document.addEventListener('keydown', onKeydown)
    return
  }
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onKeydown)
})

onMounted(() => {
  if (!account.account && !account.loading) void account.fetchAccount()
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="user-menu">
    <button
      class="user-trigger"
      type="button"
      aria-haspopup="dialog"
      :aria-expanded="open"
      aria-label="账户与网页设置"
      @click="toggle"
    >
      <span class="user-avatar" aria-hidden="true">{{ initial }}</span>
      <span class="user-copy">
        <strong>{{ auth.displayName }}</strong>
        <small>{{ planLabel(account.plan) }}</small>
      </span>
      <span class="user-chevron" aria-hidden="true">{{ open ? '⌄' : '⌃' }}</span>
    </button>

    <section v-if="open" class="user-popover" role="dialog" aria-label="账户与网页设置">
      <header class="popover-head">
        <div>
          <p class="eyebrow">当前读者</p>
          <h2>{{ auth.displayName }}</h2>
        </div>
        <button class="popover-close" type="button" aria-label="关闭账户弹层" @click="close">
          ×
        </button>
      </header>

      <section class="popover-block account-block" aria-labelledby="account-title">
        <h3 id="account-title">账户与额度</h3>
        <div v-if="account.loading && !account.account" class="popover-state">
          <span class="spinner sm"></span>
          正在读取账户…
        </div>
        <template v-else-if="account.account">
          <dl class="account-grid">
            <div>
              <dt>用户名</dt>
              <dd>@{{ auth.user?.username || '—' }}</dd>
            </div>
            <div>
              <dt>展示名</dt>
              <dd>{{ auth.user?.displayName || '未设置' }}</dd>
            </div>
            <div>
              <dt>当前档位</dt>
              <dd>{{ planLabel(account.plan) }}</dd>
            </div>
            <div>
              <dt>到期时间</dt>
              <dd>{{ formatDate(account.planExpiresAt) }}</dd>
            </div>
            <div>
              <dt>剩余积分</dt>
              <dd :class="{ danger: account.credits < 1 }">{{ formatCredits(account.credits) }}</dd>
            </div>
            <div>
              <dt>余额</dt>
              <dd>{{ formatMoney(account.balance) }}</dd>
            </div>
          </dl>
        </template>
        <div v-else class="popover-state error">
          <span>{{ account.error || '账户信息不可用' }}</span>
          <button class="text-btn" type="button" @click="account.fetchAccount(true)">重试</button>
        </div>
      </section>

      <section class="popover-block settings-block" aria-labelledby="preferences-title">
        <div class="block-head">
          <h3 id="preferences-title">网页设置</h3>
          <span>即时生效</span>
        </div>

        <div class="theme-options" role="group" aria-label="网页主题">
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
            <span>{{ item.label }}</span>
          </button>
        </div>

        <div class="font-block">
          <div class="font-head">
            <label for="user-font-size">正文字号</label>
            <span>{{ settings.fontSize }}px</span>
          </div>
          <div class="font-row">
            <span aria-hidden="true">A</span>
            <input
              id="user-font-size"
              type="range"
              :min="settings.minFont"
              :max="settings.maxFont"
              step="1"
              :value="settings.fontSize"
              aria-label="正文字号"
              @input="onFontInput"
            />
            <span class="font-large" aria-hidden="true">A</span>
          </div>
        </div>
      </section>

      <footer class="popover-foot">
        <button class="btn logout-btn" type="button" :disabled="loggingOut" @click="logout">
          {{ loggingOut ? '正在退出…' : '退出登录' }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.user-menu {
  position: relative;
  width: 100%;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-width: 0;
  padding: 7px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  text-align: left;
  transition:
    background-color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}

.user-trigger:hover,
.user-trigger[aria-expanded='true'] {
  border-color: var(--border);
  background: var(--surface);
}

.user-avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: var(--bg);
  font-family: var(--font-serif);
  font-size: 15px;
}

.user-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.user-copy strong,
.user-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-copy strong {
  font-size: 12.5px;
  font-weight: 600;
}

.user-copy small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.user-chevron {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 12px;
}

.user-popover {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 100;
  width: min(340px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
  overflow-y: auto;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.popover-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding-bottom: 12px;
}

.eyebrow {
  margin-bottom: 2px;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.16em;
}

.popover-head h2 {
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 600;
}

.popover-close {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1;
}

.popover-close:hover {
  background: var(--surface-2);
  color: var(--text);
}

.popover-block {
  padding: 12px 0;
  border-top: 1px solid var(--border);
}

.popover-block h3 {
  font-size: 12.5px;
  font-weight: 600;
}

.block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: 10px;
}

.block-head span {
  color: var(--text-muted);
  font-size: 10px;
}

.account-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 10px 0 0;
}

.account-grid > div {
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.account-grid dt {
  color: var(--text-muted);
  font-size: 9.5px;
}

.account-grid dd {
  margin: 1px 0 0;
  overflow: hidden;
  color: var(--text);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-grid dd.danger {
  color: var(--danger);
}

.popover-state {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  color: var(--text-secondary);
  font-size: 11.5px;
}

.popover-state.error {
  flex-wrap: wrap;
  color: var(--danger);
}

.text-btn {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.theme-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.theme-option {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 5px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 10.5px;
  text-align: left;
}

.theme-option.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
  color: var(--text);
}

.swatch {
  display: block;
  width: 100%;
  height: 22px;
  border: 1px solid color-mix(in srgb, var(--text) 10%, transparent);
  border-radius: 3px;
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

.font-block {
  margin-top: 12px;
}

.font-head,
.font-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.font-head {
  color: var(--text-secondary);
  font-size: 10.5px;
}

.font-head span {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.font-row span {
  color: var(--text-muted);
  font-size: 11px;
}

.font-row .font-large {
  font-size: 18px;
}

.font-row input {
  flex: 1;
  min-width: 0;
  accent-color: var(--accent);
}

.popover-foot {
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.logout-btn {
  width: 100%;
  height: 34px;
  padding: 0 12px;
  color: var(--danger);
  font-size: 12.5px;
}

@media (max-width: 900px) {
  .user-menu {
    width: auto;
  }

  .user-trigger {
    width: auto;
    padding: 4px;
    border-color: transparent;
  }

  .user-copy,
  .user-chevron {
    display: none;
  }

  .user-popover {
    position: fixed;
    top: calc(56px + 8px);
    right: 12px;
    bottom: auto;
    left: auto;
    width: min(360px, calc(100vw - 24px));
    max-height: calc(100dvh - 72px);
  }
}
</style>
