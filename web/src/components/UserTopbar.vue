<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAccountStore } from '../stores/account'
import { useAuthStore } from '../stores/auth'
import { formatCredits, planLabel } from '../utils/billing'

defineProps<{ active?: 'library' | 'plans' | 'settings' }>()

const router = useRouter()
const auth = useAuthStore()
const account = useAccountStore()

onMounted(() => {
  if (!account.account) void account.fetchAccount()
})

async function handleLogout() {
  await auth.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <header class="topbar">
    <RouterLink class="brand" to="/library">
      <span class="brand-mark">阅</span>
      <span class="brand-name">Omniread</span>
    </RouterLink>

    <nav class="topnav" aria-label="用户区导航">
      <RouterLink class="nav-link" :class="{ active: active === 'library' }" to="/library">书库</RouterLink>
      <RouterLink class="nav-link" :class="{ active: active === 'plans' }" to="/plans">套餐</RouterLink>
      <RouterLink class="nav-link" :class="{ active: active === 'settings' }" to="/settings">
        设置
      </RouterLink>
      <RouterLink v-if="account.isAdmin" class="nav-link admin-link" to="/admin">管理</RouterLink>
    </nav>

    <div class="topbar-side">
      <span v-if="account.account" class="quota-chip">
        {{ planLabel(account.plan) }} · {{ formatCredits(account.credits) }} 积分
      </span>
      <span class="user-chip" :title="auth.user?.username || '读者'">{{ auth.displayName }}</span>
      <button class="btn btn-ghost" type="button" @click="handleLogout">退出</button>
    </div>
  </header>
</template>

<style scoped>
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
  background: color-mix(in srgb, var(--bg) 92%, transparent);
  backdrop-filter: saturate(1.25) blur(10px);
  -webkit-backdrop-filter: saturate(1.25) blur(10px);
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
  width: 34px;
  height: 34px;
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

.topnav {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.nav-link {
  padding: 6px 10px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.nav-link:hover {
  background: var(--surface-2);
  color: var(--text);
}

.nav-link.active {
  background: var(--surface-2);
  color: var(--text);
  font-weight: 600;
}

.admin-link {
  margin-left: 4px;
  border: 1px solid var(--border);
}

.topbar-side {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}

.quota-chip {
  margin-right: 4px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 11.5px;
  white-space: nowrap;
}

.user-chip {
  max-width: 150px;
  margin: 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-secondary);
}

@media (max-width: 820px) {
  .quota-chip,
  .user-chip {
    display: none;
  }
}

@media (max-width: 560px) {
  .brand-name {
    display: none;
  }

  .topbar {
    gap: 8px;
  }

  .nav-link {
    padding: 6px 8px;
  }
}
</style>
