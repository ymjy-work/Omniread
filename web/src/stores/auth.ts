import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { login as loginApi, logout as logoutApi } from '../api/auth'
import { errorMessage, TOKEN_KEY, USER_KEY } from '../api/request'
import type { User } from '../types/api'

function readStoredUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<User>
    if (typeof parsed.username === 'string') return parsed as User
    return null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<User | null>(readStoredUser())
  const loggingIn = ref(false)
  const loginError = ref('')

  const isAuthenticated = computed(() => Boolean(token.value))
  const displayName = computed(() => user.value?.displayName || user.value?.username || '读者')

  function setSession(nextToken: string, nextUser: User) {
    token.value = nextToken
    user.value = nextUser
    localStorage.setItem(TOKEN_KEY, nextToken)
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
  }

  function clear() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  async function login(username: string, password: string) {
    loggingIn.value = true
    loginError.value = ''
    try {
      const response = await loginApi({ username, password })
      setSession(response.token, response.user)
      return response
    } catch (error) {
      loginError.value = errorMessage(error, '登录失败')
      throw error
    } finally {
      loggingIn.value = false
    }
  }

  async function logout() {
    try {
      await logoutApi()
    } catch {
      // 退出接口失败时仍然清理本地登录态
    } finally {
      clear()
    }
  }

  return {
    token,
    user,
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
