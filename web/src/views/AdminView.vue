<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { errorMessage } from '../api/request'
import { useAccountStore } from '../stores/account'
import { useAdminStore } from '../stores/admin'
import { formatCredits, formatDate, formatMoney, planLabel, roleLabel } from '../utils/billing'
import type { AdminUser } from '../types/account'

const account = useAccountStore()
const admin = useAdminStore()

const form = reactive({ username: '', password: '', displayName: '' })
const creating = ref(false)
const createError = ref('')
const createMessage = ref('')

const grantAmounts = reactive<Record<number, string>>({})
const grantingId = ref<number | null>(null)
const grantError = ref('')
const grantMessage = ref('')

const totalUsers = computed(() => admin.users.length)

onMounted(() => {
  void account.fetchAccount()
  void admin.fetchUsers()
})

function initial(user: AdminUser) {
  return (user.displayName || user.username).trim().charAt(0) || '用'
}

function onGrantInput(userId: number, event: Event) {
  grantAmounts[userId] = (event.target as HTMLInputElement).value
}

async function submitCreate() {
  if (creating.value) return
  const username = form.username.trim()
  if (!username || !form.password) {
    createError.value = '请输入用户名和密码。'
    return
  }
  creating.value = true
  createError.value = ''
  createMessage.value = ''
  try {
    const user = await admin.createUser({
      username,
      password: form.password,
      displayName: form.displayName.trim() || undefined,
    })
    createMessage.value = `已创建 ${user.username}：${planLabel(user.plan)} / ${formatCredits(user.credits)} 积分 / 余额 ${formatMoney(user.balance)}。`
    form.username = ''
    form.password = ''
    form.displayName = ''
  } catch (error) {
    createError.value = errorMessage(error, '创建用户失败')
  } finally {
    creating.value = false
  }
}

async function grant(user: AdminUser) {
  if (grantingId.value !== null) return
  const raw = (grantAmounts[user.id] ?? '').trim()
  const amount = Number(raw)
  if (!raw || !Number.isFinite(amount) || amount <= 0) {
    grantError.value = '请输入大于 0 的发放金额。'
    return
  }
  grantingId.value = user.id
  grantError.value = ''
  grantMessage.value = ''
  try {
    const updated = await admin.grantBalance(user.id, { amount, reason: '管理员发放' })
    grantAmounts[user.id] = ''
    grantMessage.value = `已向 ${updated.username} 发放 ${formatMoney(amount)}，当前余额 ${formatMoney(updated.balance)}。`
  } catch (error) {
    grantError.value = errorMessage(error, '发放余额失败')
  } finally {
    grantingId.value = null
  }
}
</script>

<template>
  <div class="admin-page">
    <header class="topbar">
      <RouterLink class="brand" to="/">
        <span class="brand-mark">阅</span>
        <span class="brand-name">Omniread</span>
      </RouterLink>
      <div class="topbar-actions">
        <span v-if="account.account" class="quota-chip">
          {{ planLabel(account.plan) }} · 积分 {{ formatCredits(account.credits) }}
        </span>
        <RouterLink class="btn btn-ghost" to="/settings">设置</RouterLink>
        <RouterLink class="btn btn-ghost" to="/">书库</RouterLink>
      </div>
    </header>

    <main class="admin-main">
      <header class="page-head">
        <p class="eyebrow">ADMIN</p>
        <h1>用户管理</h1>
        <p class="page-desc">新建账号默认 Free / 100 积分 / 余额 ¥20.00。</p>
      </header>

      <section class="panel">
        <div class="panel-head">
          <h2>新建用户</h2>
          <p>用户名与密码由管理员设置，角色固定为普通用户。</p>
        </div>

        <form class="create-form" @submit.prevent="submitCreate">
          <label class="field">
            <span>用户名</span>
            <input v-model="form.username" class="input" type="text" autocomplete="off" placeholder="登录用户名" />
          </label>
          <label class="field">
            <span>密码</span>
            <input v-model="form.password" class="input" type="password" autocomplete="new-password" placeholder="初始密码" />
          </label>
          <label class="field">
            <span>显示名称</span>
            <input v-model="form.displayName" class="input" type="text" autocomplete="off" placeholder="可留空" />
          </label>
          <button class="btn btn-primary" type="submit" :disabled="creating">
            <span v-if="creating" class="spinner sm"></span>
            {{ creating ? '创建中…' : '创建用户' }}
          </button>
        </form>

        <p v-if="createError" class="notice error" role="alert">{{ createError }}</p>
        <p v-if="createMessage" class="notice success" role="status">{{ createMessage }}</p>
      </section>

      <section class="panel">
        <div class="panel-head panel-head-inline">
          <div>
            <h2>用户列表</h2>
            <p>共 {{ totalUsers }} 个账号。</p>
          </div>
          <button class="btn" type="button" :disabled="admin.loading" @click="admin.fetchUsers()">
            刷新
          </button>
        </div>

        <div v-if="admin.loading" class="inline-state">
          <span class="spinner"></span>
          正在加载用户…
        </div>

        <div v-else-if="admin.error" class="inline-state">
          <span class="error-text">{{ admin.error }}</span>
          <button class="btn" type="button" @click="admin.fetchUsers()">重试</button>
        </div>

        <p v-else-if="admin.users.length === 0" class="inline-state">还没有用户。</p>

        <div v-else class="user-list">
          <article v-for="user in admin.users" :key="user.id" class="user-row">
            <div class="user-ident">
              <span class="avatar">{{ initial(user) }}</span>
              <div>
                <strong>{{ user.displayName || user.username }}</strong>
                <span>@{{ user.username }} · {{ roleLabel(user.role) }}</span>
              </div>
            </div>
            <div class="user-metric">
              <span>档位</span>
              <strong>{{ planLabel(user.plan) }}</strong>
            </div>
            <div class="user-metric">
              <span>积分</span>
              <strong>{{ formatCredits(user.credits) }}</strong>
            </div>
            <div class="user-metric">
              <span>余额</span>
              <strong>{{ formatMoney(user.balance) }}</strong>
            </div>
            <div class="user-metric">
              <span>到期</span>
              <strong>{{ formatDate(user.planExpiresAt) }}</strong>
            </div>
            <div class="grant-box">
              <input
                class="input"
                inputmode="decimal"
                :value="grantAmounts[user.id] ?? ''"
                placeholder="金额"
                :aria-label="`向 ${user.username} 发放余额`"
                @input="onGrantInput(user.id, $event)"
              />
              <button
                class="btn"
                type="button"
                :disabled="grantingId === user.id"
                @click="grant(user)"
              >
                {{ grantingId === user.id ? '发放中…' : '发放余额' }}
              </button>
            </div>
          </article>
        </div>

        <p v-if="grantError" class="notice error" role="alert">{{ grantError }}</p>
        <p v-if="grantMessage" class="notice success" role="status">{{ grantMessage }}</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.admin-page {
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
  gap: 6px;
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

.admin-main {
  width: min(1120px, 100%);
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
  margin-bottom: 18px;
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

.create-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  align-items: end;
  gap: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.field span {
  font-size: 11.5px;
  color: var(--text-muted);
}

.field .input {
  padding: 9px 11px;
  font-size: 13px;
}

.create-form > .btn {
  padding: 9px 16px;
  font-size: 13px;
}

.inline-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 24px 12px;
  font-size: 13px;
  color: var(--text-secondary);
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

.user-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-row {
  display: grid;
  grid-template-columns: minmax(190px, 1.5fr) repeat(3, minmax(70px, 0.55fr)) minmax(90px, 0.7fr) minmax(180px, 1fr);
  align-items: center;
  gap: 12px;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
}

.user-ident {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: none;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--border);
  font-family: var(--font-serif);
  font-size: 15px;
  color: var(--text-secondary);
}

.user-ident div {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-ident strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.user-ident span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10.5px;
  color: var(--text-muted);
}

.user-metric {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.user-metric span {
  font-size: 10.5px;
  color: var(--text-muted);
}

.user-metric strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
}

.grant-box {
  display: flex;
  gap: 6px;
}

.grant-box .input {
  width: 72px;
  min-width: 0;
  padding: 6px 8px;
  font-size: 12px;
}

.grant-box .btn {
  padding: 6px 10px;
  font-size: 11.5px;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .create-form {
    grid-template-columns: 1fr 1fr;
  }

  .create-form > .btn {
    grid-column: 1 / -1;
  }

  .user-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .user-ident {
    grid-column: 1 / -1;
  }

  .grant-box {
    grid-column: 1 / -1;
  }
}

@media (max-width: 560px) {
  .quota-chip {
    display: none;
  }

  .create-form {
    grid-template-columns: 1fr;
  }

  .user-row {
    grid-template-columns: 1fr 1fr;
  }
}
</style>