<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage } from '../api/request'
import { useAdminStore } from '../stores/admin'
import { useAuthStore } from '../stores/auth'
import { formatCredits, formatDate, formatMoney, planLabel, roleLabel } from '../utils/billing'
import type { AdminUser } from '../types/account'

const router = useRouter()
const auth = useAuthStore()
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
    createMessage.value = `已创建 @${user.username}：${planLabel(user.plan)} / ${formatCredits(user.credits)} 积分 / 余额 ${formatMoney(user.balance)}。`
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
    grantMessage.value = `已向 @${updated.username} 发放 ${formatMoney(amount)}，当前余额 ${formatMoney(updated.balance)}。`
  } catch (error) {
    grantError.value = errorMessage(error, '发放余额失败')
  } finally {
    grantingId.value = null
  }
}

async function handleLogout() {
  await auth.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="admin-shell">
    <header class="admin-topbar">
      <div class="admin-brand">
        <span class="brand-mark">阅</span>
        <div class="brand-text">
          <strong>Omniread</strong>
          <span>管理控制台</span>
        </div>
      </div>

      <nav class="admin-nav" aria-label="管理员导航">
        <RouterLink class="admin-nav-link active" to="/admin">用户管理</RouterLink>
      </nav>

      <div class="admin-side">
        <span class="operator">{{ auth.displayName }}</span>
        <RouterLink class="quiet-link" to="/library">返回用户区</RouterLink>
        <button class="btn" type="button" @click="handleLogout">退出</button>
      </div>
    </header>

    <main class="admin-main">
      <header class="admin-head">
        <p class="eyebrow">ADMIN CONSOLE</p>
        <h1>用户管理</h1>
        <p class="head-desc">创建账号、查看额度并发放余额。</p>
      </header>

      <section class="admin-card">
        <div class="card-head">
          <div>
            <h2>新建用户</h2>
            <p>用户名与密码由管理员设置，角色固定为普通用户。</p>
          </div>
          <span class="meta-tag">默认 Free · 100 积分 · ¥20.00</span>
        </div>

        <form class="create-form" @submit.prevent="submitCreate">
          <label class="field">
            <span>用户名</span>
            <input
              v-model="form.username"
              class="input"
              type="text"
              autocomplete="off"
              placeholder="登录用户名"
            />
          </label>
          <label class="field">
            <span>密码</span>
            <input
              v-model="form.password"
              class="input"
              type="password"
              autocomplete="new-password"
              placeholder="初始密码"
            />
          </label>
          <label class="field">
            <span>显示名称</span>
            <input
              v-model="form.displayName"
              class="input"
              type="text"
              autocomplete="off"
              placeholder="可留空"
            />
          </label>
          <button class="btn btn-primary" type="submit" :disabled="creating">
            <span v-if="creating" class="spinner sm"></span>
            {{ creating ? '创建中…' : '创建用户' }}
          </button>
        </form>

        <p v-if="createError" class="notice error" role="alert">{{ createError }}</p>
        <p v-if="createMessage" class="notice success" role="status">{{ createMessage }}</p>
      </section>

      <section class="admin-card">
        <div class="list-head">
          <div>
            <h2>用户列表</h2>
            <p>共 {{ totalUsers }} 位用户。</p>
          </div>
          <button class="btn" type="button" :disabled="admin.loading" @click="admin.fetchUsers()">
            <span v-if="admin.loading" class="spinner sm"></span>
            {{ admin.loading ? '刷新中…' : '刷新' }}
          </button>
        </div>

        <div v-if="admin.loading && admin.users.length === 0" class="inline-state">
          <span class="spinner"></span>
          正在加载用户…
        </div>

        <div v-else-if="admin.error && admin.users.length === 0" class="inline-state">
          <span class="error-text">{{ admin.error }}</span>
          <button class="btn" type="button" @click="admin.fetchUsers()">重试</button>
        </div>

        <p v-else-if="admin.users.length === 0" class="inline-state">还没有用户。</p>

        <div v-else class="table-wrap">
          <div class="user-table">
            <div class="table-head">
              <span>用户</span>
              <span>档位</span>
              <span>积分</span>
              <span>余额</span>
              <span>到期</span>
              <span>发放余额</span>
            </div>
            <div v-for="user in admin.users" :key="user.id" class="table-row">
              <div class="user-ident">
                <span class="avatar">{{ initial(user) }}</span>
                <div>
                  <strong>{{ user.displayName || user.username }}</strong>
                  <span>
                    @{{ user.username }} · {{ roleLabel(user.role) }} ·
                    {{ formatDate(user.createdAt) }}
                  </span>
                </div>
              </div>
              <div class="cell">
                <strong>{{ planLabel(user.plan) }}</strong>
              </div>
              <div class="cell numeric">
                <strong>{{ formatCredits(user.credits) }}</strong>
              </div>
              <div class="cell numeric">
                <strong>{{ formatMoney(user.balance) }}</strong>
              </div>
              <div class="cell numeric">
                <strong>{{ formatDate(user.planExpiresAt) }}</strong>
              </div>
              <div class="grant-box">
                <input
                  class="input"
                  type="text"
                  inputmode="decimal"
                  placeholder="金额"
                  :value="grantAmounts[user.id] ?? ''"
                  :disabled="grantingId !== null"
                  @input="onGrantInput(user.id, $event)"
                />
                <button
                  class="btn btn-primary"
                  type="button"
                  :disabled="grantingId !== null"
                  @click="grant(user)"
                >
                  <span v-if="grantingId === user.id" class="spinner sm"></span>
                  {{ grantingId === user.id ? '发放中' : '发放' }}
                </button>
              </div>
            </div>
          </div>

          <p v-if="grantError" class="notice error" role="alert">{{ grantError }}</p>
          <p v-if="grantMessage" class="notice success" role="status">{{ grantMessage }}</p>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.admin-shell {
  --bg: #f3f5f8;
  --surface: #ffffff;
  --surface-2: #f7f8fa;
  --surface-3: #eef1f5;
  --text: #1f2632;
  --text-secondary: #5d6775;
  --text-muted: #8b95a3;
  --border: #e1e5eb;
  --border-strong: #cdd4de;
  --accent: #2f5d8a;
  --accent-hover: #274d73;
  --accent-soft: rgba(47, 93, 138, 0.1);
  --success: #3e6b4c;
  --success-soft: rgba(62, 107, 76, 0.12);
  --warning: #8f691d;
  --warning-soft: rgba(143, 105, 29, 0.12);
  --danger: #a33b3b;
  --danger-soft: rgba(163, 59, 59, 0.1);
  min-height: 100dvh;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
}

.admin-topbar {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  height: 56px;
  padding: 0 clamp(18px, 3vw, 36px);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.admin-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  font-family: var(--font-serif);
  font-size: 16px;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.brand-text strong {
  font-size: 13.5px;
  letter-spacing: 0.03em;
}

.brand-text span {
  color: var(--text-muted);
  font-size: 10px;
}

.admin-nav {
  display: flex;
  align-items: center;
  flex: 1;
}

.admin-nav-link {
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-secondary);
}

.admin-nav-link.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.admin-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}

.operator {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  font-size: 12px;
}

.quiet-link {
  color: var(--text-muted);
  font-size: 12px;
}

.quiet-link:hover {
  color: var(--accent);
}

.admin-side .btn {
  padding: 6px 11px;
  font-size: 12px;
}

.admin-main {
  width: min(1180px, 100%);
  margin: 0 auto;
  padding: 26px clamp(18px, 3vw, 36px) 60px;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.admin-head {
  margin-bottom: 2px;
}

.eyebrow {
  margin-bottom: 6px;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.22em;
}

.admin-head h1 {
  font-size: clamp(24px, 3vw, 30px);
  font-weight: 700;
  letter-spacing: -0.01em;
}

.head-desc {
  margin-top: 5px;
  color: var(--text-secondary);
  font-size: 12.5px;
}

.admin-card {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.card-head,
.list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: 14px;
}

.list-head {
  align-items: center;
}

.card-head h2,
.list-head h2 {
  font-size: 14px;
  font-weight: 650;
}

.card-head p,
.list-head p {
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 11.5px;
}

.meta-tag {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 10.5px;
  white-space: nowrap;
}

.create-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  align-items: end;
  gap: 9px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.field span {
  color: var(--text-muted);
  font-size: 10.5px;
}

.field .input {
  padding: 7px 9px;
  font-size: 12.5px;
}

.create-form > .btn {
  padding: 8px 14px;
  font-size: 12.5px;
}

.inline-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 22px 12px;
  color: var(--text-secondary);
  font-size: 12.5px;
}

.notice {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-size: 11.5px;
  line-height: 1.5;
}

.notice.error {
  background: var(--danger-soft);
  color: var(--danger);
}

.notice.success {
  background: var(--success-soft);
  color: var(--success);
}

.table-wrap {
  overflow-x: auto;
}

.user-table {
  min-width: 860px;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns: minmax(220px, 1.6fr) 72px 72px 96px 104px minmax(190px, 1fr);
  align-items: center;
  gap: var(--space-3);
}

.table-head {
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 10.5px;
  letter-spacing: 0.04em;
}

.table-row {
  min-height: 40px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
}

.table-row:last-child {
  border-bottom: none;
}

.table-row:hover {
  background: var(--surface-2);
}

.user-ident {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.avatar {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 13px;
}

.user-ident div {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.user-ident strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
}

.user-ident span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-muted);
  font-size: 10px;
}

.cell {
  min-width: 0;
}

.cell strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11.5px;
  font-weight: 600;
}

.cell.numeric strong {
  font-variant-numeric: tabular-nums;
}

.grant-box {
  display: flex;
  gap: 6px;
}

.grant-box .input {
  width: 76px;
  min-width: 0;
  padding: 5px 7px;
  font-size: 11.5px;
}

.grant-box .btn {
  padding: 5px 9px;
  font-size: 11px;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .create-form {
    grid-template-columns: 1fr 1fr;
  }

  .create-form > .btn {
    grid-column: 1 / -1;
  }
}

@media (max-width: 640px) {
  .admin-topbar {
    height: auto;
    min-height: 56px;
    flex-wrap: wrap;
    padding-top: 8px;
    padding-bottom: 8px;
  }

  .admin-nav {
    order: 3;
    width: 100%;
    flex-basis: 100%;
  }

  .admin-side {
    margin-left: auto;
  }

  .operator {
    display: none;
  }

  .create-form {
    grid-template-columns: 1fr;
  }

  .card-head,
  .list-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>