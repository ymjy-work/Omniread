<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

type AuthMode = 'login' | 'register'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const mode = ref<AuthMode>('login')
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '', displayName: '' })

const rules = computed<FormRules>(() => ({
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}))

const redirectTarget = computed(() => {
  const target = route.query.redirect
  return typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')
    ? target
    : '/library'
})

const isRegister = computed(() => mode.value === 'register')
const submitting = computed(() => (isRegister.value ? auth.registering : auth.loggingIn))
const errorText = computed(() => (isRegister.value ? auth.registerError : auth.loginError))
const heading = computed(() => (isRegister.value ? '创建 Omniread 账号' : '登录 Omniread'))
const subtitle = computed(() =>
  isRegister.value ? '注册后即可开始阅读，并获赠 100 积分。' : '继续你的阅读进度。',
)
const submitLabel = computed(() => {
  if (submitting.value) return isRegister.value ? '正在注册…' : '正在登录…'
  return isRegister.value ? '注册' : '登录'
})
const accountPrompt = computed(() => (isRegister.value ? '已有账号？' : '还没有账号？'))
const switchLabel = computed(() => (isRegister.value ? '返回登录' : '立即注册'))

function switchMode(nextMode: AuthMode) {
  if (mode.value === nextMode || submitting.value) return
  mode.value = nextMode
  form.password = ''
  auth.clearErrors()
  void formRef.value?.clearValidate()
}

async function submit() {
  if (submitting.value) return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  try {
    if (isRegister.value) {
      await auth.register(
        form.username.trim(),
        form.password,
        form.displayName.trim() || undefined,
      )
    } else {
      await auth.login(form.username.trim(), form.password)
    }
    await router.replace(redirectTarget.value)
  } catch {
    // 错误信息由 auth store 保存并在表单内展示
  }
}
</script>

<template>
  <main class="login-page">
    <div class="login-card">
      <header class="login-head">
        <div class="brand-line">
          <span class="brand-mark">阅</span>
          <span class="brand-name">Omniread</span>
        </div>
        <div class="mode-switch" role="group" aria-label="登录或注册">
          <button
            type="button"
            class="mode-tab"
            :class="{ 'is-active': mode === 'login' }"
            :aria-pressed="mode === 'login'"
            :disabled="submitting"
            @click="switchMode('login')"
          >
            登录
          </button>
          <button
            type="button"
            class="mode-tab"
            :class="{ 'is-active': mode === 'register' }"
            :aria-pressed="mode === 'register'"
            :disabled="submitting"
            @click="switchMode('register')"
          >
            注册
          </button>
        </div>
        <h1>{{ heading }}</h1>
        <p>{{ subtitle }}</p>
      </header>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="submit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            name="username"
            autocomplete="username"
            placeholder="用户名"
            autofocus
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            name="password"
            type="password"
            :autocomplete="isRegister ? 'new-password' : 'current-password'"
            placeholder="密码"
            show-password
          />
        </el-form-item>
        <el-form-item v-if="isRegister" label="展示名（选填）" prop="displayName">
          <el-input
            v-model="form.displayName"
            name="displayName"
            autocomplete="nickname"
            placeholder="缺省使用用户名"
          />
        </el-form-item>

        <p v-if="errorText" class="form-error" role="alert">{{ errorText }}</p>

        <el-button
          class="submit-btn"
          type="primary"
          native-type="submit"
          :loading="submitting"
          :disabled="submitting"
        >
          {{ submitLabel }}
        </el-button>
      </el-form>

      <p class="account-hint">
        {{ accountPrompt }}
        <button
          type="button"
          class="mode-link"
          :disabled="submitting"
          @click="switchMode(isRegister ? 'login' : 'register')"
        >
          {{ switchLabel }}
        </button>
      </p>

      <nav class="login-links" aria-label="登录页导航">
        <RouterLink to="/">返回首页</RouterLink>
        <RouterLink to="/plans">查看套餐</RouterLink>
      </nav>
    </div>
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
  --el-input-bg-color: var(--surface-2);
  --el-input-border-color: var(--border);
  --el-input-hover-border-color: var(--border-strong);
  --el-input-focus-border-color: var(--accent);
  --el-input-text-color: var(--text);
  --el-fill-color-blank: var(--surface-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: min(380px, 100%);
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

.mode-switch {
  display: flex;
  gap: var(--space-4);
  width: 100%;
  margin-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}

.mode-tab {
  padding: 0 0 var(--space-2);
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: var(--text-sm);
  letter-spacing: 0.08em;
  cursor: pointer;
  transition:
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}

.mode-tab:hover:not(:disabled) {
  color: var(--text);
}

.mode-tab.is-active {
  border-bottom-color: var(--accent);
  color: var(--text);
}

.mode-tab:disabled,
.mode-link:disabled {
  cursor: wait;
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

.form-error {
  margin: 0 0 var(--space-2);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--danger-soft);
  color: var(--danger);
  font-size: var(--text-sm);
  line-height: 1.5;
}

.submit-btn {
  width: 100%;
  height: 40px;
  margin-top: var(--space-1);
  letter-spacing: 0.05em;
}

.account-hint {
  color: var(--text-muted);
  font-size: var(--text-xs);
  line-height: 1.6;
}

.mode-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font: inherit;
  cursor: pointer;
}

.mode-link:hover:not(:disabled) {
  color: var(--accent-hover);
}

.mode-tab:focus-visible,
.mode-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
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
