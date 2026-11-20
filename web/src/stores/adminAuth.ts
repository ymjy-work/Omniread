import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { adminLogin as adminLoginApi, adminLogout as adminLogoutApi } from '../api/adminAuth'
import { errorMessage } from '../api/errors'
import {
  clearAdminSession,
  getAdminToken,
  readStoredAdmin,
  saveAdminSession,
} from '../auth/session'
import type { User } from '../types/api'

export const useAdminAuthStore = defineStore('adminAuth', () => {
  const token = ref<string | null>(getAdminToken())
  const admin = ref<User | null>(readStoredAdmin())
  const loggingIn = ref(false)
  const loginError = ref('')

  const isAuthenticated = computed(() => Boolean(token.value))
  const displayName = computed(() => admin.value?.displayName || admin.value?.username || '管理员')

  function setSession(nextToken: string, nextUser: User) {
    token.value = nextToken
    admin.value = nextUser
    saveAdminSession(nextToken, nextUser)
  }

  function clear() {
    token.value = null
    admin.value = null
    clearAdminSession()
  }

  async function login(username: string, password: string) {
    loggingIn.value = true
    loginError.value = ''
    try {
      const response = await adminLoginApi({ username, password })
      setSession(response.token, response.user)
      return response
    } catch (error) {
      loginError.value = errorMessage(error, '管理员登录失败')
      throw error
    } finally {
      loggingIn.value = false
    }
  }

  async function logout() {
    try {
      await adminLogoutApi()
    } catch {
      // 管理员会话失效时仍然清理本地登录态
    } finally {
      clear()
    }
  }

  return {
    token,
    admin,
    loggingIn,
    loginError,
    isAuthenticated,
    displayName,
    setSession,
    clear,
    login,
    logout,
  }
})
