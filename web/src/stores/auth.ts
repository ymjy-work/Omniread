import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { login as loginApi, logout as logoutApi, register as registerApi } from '../api/auth'
import { errorMessage } from '../api/errors'
import {
  clearUserSession,
  getUserToken,
  readStoredUser,
  saveUserSession,
} from '../auth/session'
import type { User } from '../types/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getUserToken())
  const user = ref<User | null>(readStoredUser())
  const loggingIn = ref(false)
  const registering = ref(false)
  const loginError = ref('')
  const registerError = ref('')

  const isAuthenticated = computed(() => Boolean(token.value))
  const displayName = computed(() => user.value?.displayName || user.value?.username || '读者')

  function setSession(nextToken: string, nextUser: User) {
    token.value = nextToken
    user.value = nextUser
    saveUserSession(nextToken, nextUser)
  }

  function clear() {
    token.value = null
    user.value = null
    clearUserSession()
  }

  async function login(username: string, password: string) {
    loggingIn.value = true
    loginError.value = ''
    registerError.value = ''
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

  async function register(username: string, password: string, displayName?: string) {
    registering.value = true
    loginError.value = ''
    registerError.value = ''
    try {
      const response = await registerApi({ username, password, displayName })
      setSession(response.token, response.user)
      return response
    } catch (error) {
      registerError.value = errorMessage(error, '注册失败')
      throw error
    } finally {
      registering.value = false
    }
  }

  function clearErrors() {
    loginError.value = ''
    registerError.value = ''
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
    registering,
    loginError,
    registerError,
    isAuthenticated,
    displayName,
    setSession,
    clearErrors,
    clear,
    login,
    register,
    logout,
  }
})
