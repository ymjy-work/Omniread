<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const formError = ref('')

const redirectTarget = computed(() => {
  const target = route.query.redirect
  return typeof target === 'string' && target.startsWith('/') ? target : '/'
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
    <section class="brand-panel">
      <div class="brand-top">
        <span class="brand-mark">阅</span>
        <span class="brand-name">Omniread</span>
      </div>

      <div class="brand-copy">
        <p class="brand-eyebrow">中文长文阅读 · 文中问答</p>
        <h1>在字里行间停留，<br />让问题回到原文。</h1>
        <p class="brand-desc">
          分章阅读、进度同步，随时向文章提问。每个回答都带引用，点一下就能回到对应段落。
        </p>
      </div>

      <ul class="feature-list">
        <li><span class="dot"></span>沉浸式中文排版</li>
        <li><span class="dot"></span>已读范围防剧透</li>
        <li><span class="dot"></span>引用原文定位高亮</li>
      </ul>
    </section>

    <section class="form-panel">
      <div class="form-card">
        <header class="form-head">
          <p class="form-eyebrow">WELCOME BACK</p>
          <h2>登录 Omniread</h2>
          <p class="form-sub">继续上次的阅读进度</p>
        </header>

        <form class="form" @submit.prevent="submit">
          <label class="field">
            <span class="field-label">用户名</span>
            <input
              v-model="username"
              class="input"
              type="text"
              name="username"
              autocomplete="username"
              placeholder="请输入用户名"
              autofocus
            />
          </label>

          <label class="field">
            <span class="field-label">密码</span>
            <span class="password-wrap">
              <input
                v-model="password"
                class="input"
                :type="showPassword ? 'text' : 'password'"
                name="password"
                autocomplete="current-password"
                placeholder="请输入密码"
              />
              <button
                class="password-toggle"
                type="button"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                @click="showPassword = !showPassword"
              >
                {{ showPassword ? '隐藏' : '显示' }}
              </button>
            </span>
          </label>

          <p v-if="errorText" class="form-error" role="alert">{{ errorText }}</p>

          <button class="btn btn-primary submit-btn" type="submit" :disabled="auth.loggingIn">
            <span v-if="auth.loggingIn" class="spinner sm"></span>
            {{ auth.loggingIn ? '正在登录…' : '登录' }}
          </button>
        </form>

        <p class="form-foot">账号由 Omniread 网关统一管理。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  min-height: 100dvh;
}

.brand-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 32px;
  padding: clamp(28px, 5vw, 64px);
  overflow: hidden;
  color: #f6efe4;
  background:
    radial-gradient(circle at 82% 18%, rgba(214, 154, 92, 0.24), transparent 42%),
    radial-gradient(circle at 12% 88%, rgba(120, 68, 40, 0.34), transparent 46%),
    linear-gradient(155deg, #33261d 0%, #241b15 48%, #1b1511 100%);
}

.brand-panel::after {
  content: '读';
  position: absolute;
  right: -4vw;
  bottom: -10vh;
  font-family: var(--font-serif);
  font-size: clamp(240px, 34vw, 520px);
  line-height: 1;
  color: rgba(255, 244, 226, 0.045);
  pointer-events: none;
}

.brand-top {
  display: flex;
  align-items: center;
  gap: 12px;
  position: relative;
  z-index: 1;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid rgba(246, 239, 228, 0.32);
  border-radius: 12px;
  font-family: var(--font-serif);
  font-size: 20px;
}

.brand-name {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.brand-copy {
  position: relative;
  z-index: 1;
  max-width: 520px;
}

.brand-eyebrow {
  margin-bottom: 18px;
  font-size: 12px;
  letter-spacing: 0.22em;
  color: rgba(246, 239, 228, 0.6);
}

.brand-copy h1 {
  font-family: var(--font-serif);
  font-size: clamp(30px, 3.4vw, 50px);
  font-weight: 600;
  line-height: 1.42;
  letter-spacing: 0.02em;
}

.brand-desc {
  margin-top: 22px;
  max-width: 420px;
  font-size: 14px;
  line-height: 1.9;
  color: rgba(246, 239, 228, 0.66);
}

.feature-list {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 24px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
  color: rgba(246, 239, 228, 0.58);
}

.feature-list li {
  display: flex;
  align-items: center;
  gap: 9px;
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #d69a5c;
}

.form-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px clamp(20px, 5vw, 72px);
  background: var(--bg);
}

.form-card {
  width: min(100%, 390px);
}

.form-head {
  margin-bottom: 30px;
}

.form-eyebrow {
  margin-bottom: 10px;
  font-size: 11px;
  letter-spacing: 0.24em;
  color: var(--text-muted);
}

.form-head h2 {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.form-sub {
  margin-top: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.password-wrap {
  position: relative;
  display: block;
}

.password-wrap .input {
  padding-right: 62px;
}

.password-toggle {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  padding: 4px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
}

.password-toggle:hover {
  color: var(--text);
  background: var(--surface-2);
}

.form-error {
  padding: 10px 12px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 13px;
}

.submit-btn {
  height: 44px;
  margin-top: 4px;
  font-size: 15px;
}

.form-foot {
  margin-top: 22px;
  font-size: 12px;
  color: var(--text-muted);
}

@media (max-width: 880px) {
  .login-page {
    grid-template-columns: 1fr;
  }

  .brand-panel {
    min-height: 240px;
    gap: 20px;
    padding: 28px 24px 32px;
  }

  .brand-copy h1 {
    font-size: 28px;
  }

  .brand-desc {
    margin-top: 14px;
    font-size: 13px;
  }

  .feature-list {
    display: none;
  }

  .form-panel {
    align-items: flex-start;
    padding: 36px 24px 56px;
  }
}
</style>