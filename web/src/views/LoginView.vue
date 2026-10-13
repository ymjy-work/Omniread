<script setup lang="ts">
/**
 * 登录页（登录门）。背景与门厅同源——`HeroBackdrop` 的同一张画布，但**动态层不同**：
 * 这一页不要拨雾、不要指针交互（登录是个专注的动作，不是逛场景），改让画里的流星动起来
 * （`:veil="false" :meteors="true"`）。表单居中放在一块毛玻璃面板上。
 *
 * 两条口径：
 *
 * - 账户由开发者发放、**不开放注册**，所以这一页没有任何注册入口——放一个点了没用的
 *   链接比不放更糟。
 * - 登录成功后回跳到守卫拦下来时带的原地址（`?redirect=`）。回跳目标**必须收进站内**：
 *   只收「`/` 开头且不是 `//` 开头」的路径，否则 `redirect=//evil.example` 就是一个
 *   开放重定向——拿本站的登录页把人送去别处。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import HeroBackdrop from '../components/HeroBackdrop.vue'
import { ApiError } from '../api'
import { signIn } from '../auth'
import { describeErrorCode } from '../errors'

const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const busy = ref(false)
const failure = ref<{ code: string; text: string } | null>(null)
const usernameInput = ref<HTMLInputElement | null>(null)

const canSubmit = computed(
  () => username.value.trim() !== '' && password.value !== '' && !busy.value
)

onMounted(() => usernameInput.value?.focus())

function redirectTarget(): string {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')) {
    return redirect
  }
  return '/'
}

/**
 * 401 在这里的含义与别处不同：别处是「会话过期了」，这里是「这一对账户口令不对」。
 * 服务端刻意不区分「没这个账户」与「口令错」（区分开等于给了枚举账户名的接口，
 * 见 C2），所以文案也必须模糊。
 */
function describeLoginFailure(cause: unknown): { code: string; text: string } {
  if (cause instanceof ApiError) {
    if (cause.status === 401) return { code: cause.code, text: '账户或口令不正确' }
    return { code: cause.code, text: describeErrorCode(cause.code) }
  }
  return { code: 'UNKNOWN', text: '登录失败，请稍后重试' }
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  busy.value = true
  failure.value = null
  try {
    await signIn(username.value.trim(), password.value)
    await router.replace(redirectTarget())
  } catch (cause) {
    failure.value = describeLoginFailure(cause)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-page canvas-page">
    <HeroBackdrop class="stage" :veil="false" :meteors="true">
      <form class="panel" novalidate @submit.prevent="submit">
        <p class="eyebrow">OMNIREAD · 登录</p>
        <h1>欢迎回来。</h1>
        <!-- 断行是刻意的两行：交给浏览器自动折行时，尾行会剩一个「在。」孤字 -->
        <p class="lead">接着上次的故事继续。<br />读到哪儿、聊过什么，都还在。</p>

        <label class="field">
          <span>账户</span>
          <input
            ref="usernameInput"
            v-model="username"
            name="username"
            autocomplete="username"
            maxlength="64"
            spellcheck="false"
            :disabled="busy"
          />
        </label>

        <label class="field">
          <span>口令</span>
          <input
            v-model="password"
            type="password"
            name="password"
            autocomplete="current-password"
            maxlength="200"
            :disabled="busy"
          />
        </label>

        <!-- 失败行：文案按码给，错误码本身也摆在旁边——前端只按码分支，出问题时看这个 -->
        <p v-if="failure" class="err" role="alert">
          <b>{{ failure.text }}</b>
          <span class="code">{{ failure.code }}</span>
        </p>

        <button class="submit" type="submit" :disabled="!canSubmit">
          {{ busy ? '正在登录…' : '登录' }}
          <svg
            class="arw"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            aria-hidden="true"
          >
            <path d="M3 8h9M8.5 4.5L12 8l-3.5 3.5" />
          </svg>
        </button>

        <p class="hint">账户由开发者发放 · 不开放注册</p>
      </form>
    </HeroBackdrop>
  </div>
</template>

<style scoped>
/* 版式与门厅同一族：底部渐晕把视线压在面板上，其余交给画布与雾 */
.login-page {
  height: 100vh;
  overflow-y: auto;
  background-color: #05060c;
  background-image: radial-gradient(880px 560px at 50% 55%, rgba(139, 123, 255, 0.17), transparent 64%);
}
.stage {
  min-height: 100%;
  display: grid;
  place-items: center;
  padding: 48px 24px;
}

/* 毛玻璃面板：半透 + 大半径背景模糊，画布的星云会从玻璃里透出来。
   顶边一道细光 + 内高光是玻璃的「厚度」，缺了就是一块半透明色块。 */
.panel {
  position: relative;
  width: min(420px, 100%);
  padding: 42px 36px 30px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(14, 14, 26, 0.55);
  backdrop-filter: blur(28px) saturate(160%);
  -webkit-backdrop-filter: blur(28px) saturate(160%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    0 48px 110px -60px rgba(0, 0, 0, 0.95);
  animation: panel-in 0.6s cubic-bezier(0.22, 0.7, 0.3, 1) both;
}
.panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 14%;
  right: 14%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(139, 123, 255, 0.55), transparent);
}
@keyframes panel-in {
  from { opacity: 0; transform: translateY(14px); }
}

.eyebrow {
  margin: 0;
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.22em;
  color: var(--ac);
}
h1 {
  margin: 16px 0 0;
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 0.4px;
}
.lead {
  margin: 14px 0 6px;
  font-family: var(--serif);
  font-size: 15px;
  line-height: 1.9;
  color: var(--fg-2);
}

.field { display: grid; gap: 8px; margin-top: 18px; }
.field > span {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.18em;
  color: var(--fg-3);
}
.field input {
  height: 46px;
  padding: 0 14px;
  font: inherit;
  font-size: 15px;
  color: var(--fg);
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid var(--line);
  border-radius: 12px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}
.field input:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--ac) 30%, transparent);
}
.field input:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--ac) 62%, transparent);
  background: rgba(255, 255, 255, 0.06);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ac) 16%, transparent);
}
.field input:disabled { opacity: 0.6; }
/* 浏览器自动填充会盖上一层白底（深色玻璃上格外扎眼），用内阴影把它压回深色 */
.field input:-webkit-autofill,
.field input:-webkit-autofill:focus {
  -webkit-text-fill-color: var(--fg);
  -webkit-box-shadow: 0 0 0 1000px #131322 inset;
  caret-color: var(--fg);
}

.err {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin: 18px 0 0;
  padding: 10px 13px;
  border-radius: 11px;
  font-size: 13px;
  line-height: 1.6;
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent);
  color: color-mix(in srgb, var(--danger) 45%, #fff);
}
.err .code { flex: none; font-family: var(--mono); font-size: 11px; opacity: 0.72; }

/* 液态玻璃的登录键：与门厅那颗按钮同一配方（hover 不变色，只做位移与箭头滑入） */
.submit {
  font: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 46px;
  margin-top: 22px;
  padding: 0 26px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(18px) saturate(170%);
  -webkit-backdrop-filter: blur(18px) saturate(170%);
  color: var(--fg);
  font-size: 15px;
  font-weight: 500;
  letter-spacing: 0.24px;
  cursor: pointer;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.24),
    0 16px 36px -20px rgba(0, 0, 0, 0.85);
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.submit:disabled { opacity: 0.5; cursor: default; }
.submit:not(:disabled):hover { transform: translateY(-1px); }
.submit:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--ac) 70%, transparent);
  outline-offset: 2px;
}
.arw {
  width: 15px;
  height: 15px;
  flex: none;
  transition: opacity 0.2s ease, margin-left 0.2s ease;
}
.submit .arw { margin-left: -15px; opacity: 0; }
.submit:not(:disabled):hover .arw { margin-left: 9px; opacity: 1; }

.hint {
  margin: 16px 0 0;
  text-align: center;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--fg-3);
}

@media (max-width: 460px) {
  .panel { padding: 34px 22px 26px; }
}

/* 减少动效：入场与位移都停掉（拨雾在 HeroBackdrop 里本来就不挂） */
@media (prefers-reduced-motion: reduce) {
  .panel { animation: none; }
  .submit:not(:disabled):hover { transform: none; }
}
</style>
