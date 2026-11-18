<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import type { ThemeName } from '../stores/settings'

const auth = useAuthStore()
const settings = useSettingsStore()
const router = useRouter()

const themes: { value: ThemeName; label: string; desc: string }[] = [
  { value: 'light', label: '明亮', desc: '清爽纸白' },
  { value: 'sepia', label: '护眼', desc: '暖黄纸页' },
  { value: 'dark', label: '夜间', desc: '低亮墨色' },
]

function onFontInput(event: Event) {
  const target = event.target as HTMLInputElement
  settings.setFontSize(Number(target.value))
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
      <RouterLink class="btn btn-ghost" to="/">返回书库</RouterLink>
    </header>

    <main class="settings-main">
      <header class="page-head">
        <p class="eyebrow">PREFERENCES</p>
        <h1>阅读设置</h1>
        <p class="page-desc">设置保存在当前浏览器，立即生效。</p>
      </header>

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

.settings-main {
  width: min(760px, 100%);
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

.panel h2 {
  font-size: 16px;
  font-weight: 600;
}

.panel-head p {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
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

@media (max-width: 640px) {
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
}
</style>