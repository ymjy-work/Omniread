<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const accountTarget = computed(() => (auth.isAuthenticated ? '/library' : '/login'))
const accountText = computed(() => (auth.isAuthenticated ? '进入书库' : '登录'))
</script>

<template>
  <header class="public-header">
    <RouterLink class="brand" to="/">
      <span class="brand-mark">阅</span>
      <span class="brand-name">Omniread</span>
    </RouterLink>

    <nav class="public-nav" aria-label="公开页导航">
      <RouterLink class="nav-link" to="/#capabilities">产品</RouterLink>
      <RouterLink class="nav-link" to="/plans">定价</RouterLink>
      <RouterLink class="nav-link login-link" :to="accountTarget">{{ accountText }}</RouterLink>
    </nav>
  </header>
</template>

<style scoped>
.public-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  height: var(--header-height);
  padding: 0 clamp(20px, 5vw, 64px);
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 92%, transparent);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
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

.public-nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.nav-link {
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
  transition: background-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.nav-link:hover {
  background: var(--surface-2);
  color: var(--text);
}

.login-link {
  margin-left: var(--space-2);
  border: 1px solid var(--border);
  color: var(--text);
}

@media (max-width: 640px) {
  .brand-name {
    display: none;
  }

  .public-header {
    gap: var(--space-2);
  }

  .nav-link {
    padding: 6px 8px;
  }
}
</style>