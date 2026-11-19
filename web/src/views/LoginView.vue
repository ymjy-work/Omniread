<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const formError = ref('')

const redirectTarget = computed(() => {
  const target = route.query.redirect
  return typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')
    ? target
    : '/library'
})

const errorText = computed(() => formError.value || auth.loginError)

async function submit() {
  formError.value = ''
  if (!username.value.trim() || !password.value) {
    formError.value = '请输入用户名和密码'
    return
  }
  try {
    await auth.login(username.value.trim(), password.value)
    await router.replace(redirectTarget.value)
  } catch {
    // 错误信息由 auth store 保存并在表单内展示
  }
}
</script>

<template>
  <main class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <header class="login-head">
        <div class="brand-line">
          <span class="brand-mark">阅</span>
          <span class="brand-name">Omniread</span>
        </div>
        <h1>登录 Omniread</h1>
        <p>继续你的阅读进度。</p>
      </header>

      <label class="field">
        <span>用户名</span>
        <input
          v-model="username"
          class="input"
          type="text"
          name="username"
          autocomplete="username"
          autofocus
        />
      </label>

      <label class="field">
        <span>密码</span>
        <input
          v-model="password"
          class="input"
          type="password"
          name="password"
          autocomplete="current-password"
        />
      </label>

      <p v-if="errorText" class="form-error" role="alert">{{ errorText }}</p>

      <button class="btn btn-primary submit-btn" type="submit" :disabled="auth.loggingIn">
        <span v-if="auth.loggingIn" class="spinner sm"></span>
        {{ auth.loggingIn ? '正在登录…' : '登录' }}
      </button>

      <p class="account-hint">还没有账号？账号由管理员创建。</p>

      <nav class="login-links" aria-label="登录页导航">
        <RouterLink to="/">返回首页</RouterLink>
        <RouterLink to="/plans">查看套餐</RouterLink>
      </nav>
    </form>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  place-items: center;
  min-height: 100dvh;
  padding: var(--space-5);
  background:
    radial-gradient(circle at 50% 0%, var(--accent-soft), transparent 44%),
    var(--bg);
}

.login-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: min(360px, 100%);
  padding: var(--space-6);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.login-head {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.brand-line {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: var(--bg);
  font-family: var(--font-serif);
  font-size: 20px;
}

.brand-name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.login-head h1 {
  font-family: var(--font-serif);
  font-size: 21px;
  font-weight: 600;
}

.login-head p {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.field span {
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.form-error {
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--danger-soft);
  color: var(--danger);
  font-size: var(--text-sm);
  line-height: 1.5;
}

.submit-btn {
  height: 38px;
  margin-top: var(--space-1);
}

.account-hint {
  color: var(--text-muted);
  font-size: var(--text-xs);
  line-height: 1.6;
}

.login-links {
  display: flex;
  justify-content: space-between;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.login-links a:hover {
  color: var(--accent);
}
</style>