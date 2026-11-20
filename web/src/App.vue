<script setup lang="ts">
import { onMounted, watch } from 'vue'
import AppLayout from './components/AppLayout.vue'
import { useAccountStore } from './stores/account'
import { useAuthStore } from './stores/auth'
import { useSettingsStore } from './stores/settings'

const auth = useAuthStore()
const account = useAccountStore()

useSettingsStore()

onMounted(() => {
  if (auth.isAuthenticated) void account.fetchAccount()
})

watch(
  () => auth.token,
  (token) => {
    if (token) void account.fetchAccount(true)
    else account.clear()
  },
)
</script>

<template>
  <RouterView v-slot="{ Component, route }">
    <AppLayout v-if="route.meta.appShell">
      <component :is="Component" />
    </AppLayout>
    <component :is="Component" v-else />
  </RouterView>
</template>
