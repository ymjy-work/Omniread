<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useAdminAuthStore } from '../stores/adminAuth'

const adminAuth = useAdminAuthStore()
const route = useRoute()
const router = useRouter()

const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入管理员账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const redirectTarget = computed(() => {
  const target = route.query.redirect
  return typeof target === 'string' && target.startsWith('/admin') && !target.startsWith('//')
    ? target
    : '/admin'
})

const errorText = computed(() => adminAuth.loginError)

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  try {
    await adminAuth.login(form.username.trim(), form.password)
    await router.replace(redirectTarget.value)
  } catch {
    // 错误信息由 adminAuth store 保存并在表单内展示
  }
}
</script>

<template>
  <main class="admin-login-page">
    <div class="admin-login-card">
      <header class="admin-login-head">
        <div class="brand-line">
          <span class="brand-mark">阅</span>
          <span class="brand-name">Omniread 管理后台</span>
        </div>
        <h1>管理员登录</h1>
        <p>管理控制台与用户体系相互独立。</p>
      </header>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="submit"
      >
        <el-form-item label="管理员账号" prop="username">
          <el-input
            v-model="form.username"
            name="username"
            autocomplete="username"
            placeholder="管理员账号"
            autofocus
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            name="password"
            type="password"
            autocomplete="current-password"
            placeholder="密码"
            show-password
          />
        </el-form-item>

        <p v-if="errorText" class="form-error" role="alert">{{ errorText }}</p>

        <el-button
          class="submit-btn"
          type="primary"
          native-type="submit"
          :loading="adminAuth.loggingIn"
        >
          {{ adminAuth.loggingIn ? '正在登录…' : '登录管理后台' }}
        </el-button>
      </el-form>

      <nav class="admin-login-links" aria-label="管理员登录页导航">
        <RouterLink to="/login">用户登录</RouterLink>
      </nav>
    </div>
  </main>
</template>

<style scoped>
.admin-login-page {
  display: grid;
  place-items: center;
  min-height: 100dvh;
  padding: var(--space-5);
  background:
    radial-gradient(circle at 50% 0%, rgba(47, 93, 138, 0.12), transparent 46%),
    #f3f5f8;
}

.admin-login-card {
  --el-color-primary: #2f5d8a;
  --el-color-primary-hover: #274d73;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: min(380px, 100%);
  padding: var(--space-6);
  border: 1px solid #e1e5eb;
  border-radius: var(--radius-lg);
  background: #fff;
  box-shadow: 0 18px 44px rgba(31, 38, 50, 0.14);
}

.admin-login-head {
  display: flex;
  flex-direction: column;
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
  background: #2f5d8a;
  color: #fff;
  font-family: var(--font-serif);
  font-size: 20px;
}

.brand-name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.admin-login-head h1 {
  font-size: 21px;
  font-weight: 600;
}

.admin-login-head p {
  color: #8b95a3;
  font-size: var(--text-sm);
}

.form-error {
  margin: 0 0 var(--space-2);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: rgba(163, 59, 59, 0.1);
  color: #a33b3b;
  font-size: var(--text-sm);
  line-height: 1.5;
}

.submit-btn {
  width: 100%;
  height: 40px;
}

.admin-login-links {
  display: flex;
  justify-content: center;
  padding-top: var(--space-3);
  border-top: 1px solid #e1e5eb;
  color: #5d6775;
  font-size: var(--text-xs);
}

.admin-login-links a:hover {
  color: #2f5d8a;
}
</style>
