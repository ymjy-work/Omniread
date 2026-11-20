<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { errorMessage } from '../api/errors'
import { useAdminAuthStore } from '../stores/adminAuth'
import { useAdminStore } from '../stores/admin'
import { formatCredits, formatDate, formatMoney, planLabel, roleLabel } from '../utils/billing'
import type { AdminUser } from '../types/account'

const router = useRouter()
const adminAuth = useAdminAuthStore()
const admin = useAdminStore()

const createFormRef = ref<FormInstance>()
const createForm = reactive({ username: '', password: '', displayName: '' })
const creating = ref(false)

const createRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入初始密码', trigger: 'blur' }],
}

const grantAmounts = reactive<Record<number, string>>({})
const grantingId = ref<number | null>(null)

const totalUsers = computed(() => admin.users.length)

onMounted(() => {
  void admin.fetchUsers()
})

function initial(user: AdminUser) {
  return (user.displayName || user.username).trim().charAt(0) || '用'
}

async function submitCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid || creating.value) return
  creating.value = true
  try {
    const user = await admin.createUser({
      username: createForm.username.trim(),
      password: createForm.password,
      displayName: createForm.displayName.trim() || undefined,
    })
    ElMessage.success(
      `已创建 @${user.username}：${planLabel(user.plan)} / ${formatCredits(user.credits)} 积分 / 余额 ${formatMoney(user.balance)}`,
    )
    createForm.username = ''
    createForm.password = ''
    createForm.displayName = ''
  } catch (error) {
    ElMessage.error(errorMessage(error, '创建用户失败'))
  } finally {
    creating.value = false
  }
}

async function grant(user: AdminUser) {
  if (grantingId.value !== null) return
  const raw = (grantAmounts[user.id] ?? '').trim()
  const amount = Number(raw)
  if (!raw || !Number.isFinite(amount) || amount <= 0) {
    ElMessage.warning('请输入大于 0 的发放金额')
    return
  }
  grantingId.value = user.id
  try {
    const updated = await admin.grantBalance(user.id, { amount, reason: '管理员发放' })
    grantAmounts[user.id] = ''
    ElMessage.success(`已向 @${updated.username} 发放 ${formatMoney(amount)}，当前余额 ${formatMoney(updated.balance)}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '发放余额失败'))
  } finally {
    grantingId.value = null
  }
}

async function handleLogout() {
  await adminAuth.logout()
  await router.replace({ name: 'admin-login' })
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
        <span class="operator">{{ adminAuth.displayName }}</span>
        <RouterLink class="quiet-link" to="/library">返回用户区</RouterLink>
        <el-button size="small" @click="handleLogout">退出</el-button>
      </div>
    </header>

    <main class="admin-main">
      <header class="admin-head">
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

        <el-form
          ref="createFormRef"
          :model="createForm"
          :rules="createRules"
          class="create-form"
          label-position="top"
          @submit.prevent="submitCreate"
        >
          <el-form-item label="用户名" prop="username">
            <el-input v-model="createForm.username" autocomplete="off" placeholder="登录用户名" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="createForm.password"
              type="password"
              autocomplete="new-password"
              placeholder="初始密码"
              show-password
            />
          </el-form-item>
          <el-form-item label="显示名称" prop="displayName">
            <el-input v-model="createForm.displayName" autocomplete="off" placeholder="可留空" />
          </el-form-item>
          <el-button
            class="create-submit"
            type="primary"
            native-type="submit"
            :loading="creating"
          >
            {{ creating ? '创建中…' : '创建用户' }}
          </el-button>
        </el-form>
      </section>

      <section class="admin-card">
        <div class="list-head">
          <div>
            <h2>用户列表</h2>
            <p>共 {{ totalUsers }} 位用户。</p>
          </div>
          <el-button :loading="admin.loading" @click="admin.fetchUsers()">刷新</el-button>
        </div>

        <div v-if="admin.error && admin.users.length === 0" class="inline-state">
          <span class="error-text">{{ admin.error }}</span>
          <el-button @click="admin.fetchUsers()">重试</el-button>
        </div>

        <el-table
          v-else
          v-loading="admin.loading"
          :data="admin.users"
          row-key="id"
          empty-text="还没有用户"
          class="user-table"
        >
          <el-table-column label="用户" min-width="240" fixed>
            <template #default="{ row }">
              <div class="user-ident">
                <span class="avatar">{{ initial(row) }}</span>
                <div>
                  <strong>{{ row.displayName || row.username }}</strong>
                  <span>@{{ row.username }} · {{ roleLabel(row.role) }} · {{ formatDate(row.createdAt) }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="档位" prop="plan" width="90">
            <template #default="{ row }">{{ planLabel(row.plan) }}</template>
          </el-table-column>
          <el-table-column label="积分" width="100" align="right">
            <template #default="{ row }">{{ formatCredits(row.credits) }}</template>
          </el-table-column>
          <el-table-column label="余额" width="110" align="right">
            <template #default="{ row }">{{ formatMoney(row.balance) }}</template>
          </el-table-column>
          <el-table-column label="到期" width="120" align="right">
            <template #default="{ row }">{{ formatDate(row.planExpiresAt) }}</template>
          </el-table-column>
          <el-table-column label="发放余额" min-width="210" fixed="right">
            <template #default="{ row }">
              <div class="grant-box">
                <el-input
                  v-model="grantAmounts[row.id]"
                  inputmode="decimal"
                  placeholder="金额"
                  :disabled="grantingId !== null"
                  class="grant-input"
                />
                <el-button
                  type="primary"
                  :loading="grantingId === row.id"
                  :disabled="grantingId !== null && grantingId !== row.id"
                  @click="grant(row)"
                >
                  发放
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
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
  --danger: #a33b3b;
  --danger-soft: rgba(163, 59, 59, 0.1);
  --el-color-primary: var(--accent);
  --el-color-primary-hover: var(--accent-hover);
  --el-border-color: var(--border);
  --el-border-color-light: var(--border);
  --el-fill-color-blank: #fff;
  --el-text-color-regular: var(--text-secondary);
  --el-text-color-primary: var(--text);
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

.admin-main {
  width: min(1180px, 100%);
  margin: 0 auto;
  padding: 26px clamp(18px, 3vw, 36px) 60px;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
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

.create-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.create-submit {
  min-width: 104px;
  height: 32px;
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

.user-table {
  --el-table-border-color: var(--border);
  --el-table-header-bg-color: var(--surface-2);
  --el-table-row-hover-bg-color: var(--surface-2);
  --el-table-text-color: var(--text-secondary);
  --el-table-header-text-color: var(--text-muted);
}

.user-table :deep(.el-table__cell) {
  padding: 7px 0;
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

.grant-box {
  display: flex;
  gap: 6px;
}

.grant-input {
  width: 96px;
}

.grant-box :deep(.el-input__wrapper),
.create-form :deep(.el-input__wrapper) {
  border-radius: var(--radius-sm);
}

@media (max-width: 900px) {
  .create-form {
    grid-template-columns: 1fr 1fr;
  }

  .create-submit {
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
