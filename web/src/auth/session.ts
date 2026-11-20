import { setHttpAuthHandler } from '../api/http'
import type { User } from '../types/api'

export const TOKEN_KEY = 'omniread.token'
export const USER_KEY = 'omniread.user'
export const ADMIN_TOKEN_KEY = 'omniread.admin.token'
export const ADMIN_USER_KEY = 'omniread.admin.user'

function isAdminApiPath(url?: string): boolean {
  return typeof url === 'string' && url.startsWith('/admin')
}

export function getUserToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getAdminToken(): string | null {
  return localStorage.getItem(ADMIN_TOKEN_KEY)
}

function readStoredJson(key: string): User | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<User>
    if (typeof parsed.username === 'string') return parsed as User
    return null
  } catch {
    return null
  }
}

export function readStoredUser(): User | null {
  return readStoredJson(USER_KEY)
}

export function readStoredAdmin(): User | null {
  return readStoredJson(ADMIN_USER_KEY)
}

export function saveUserSession(token: string, user: User): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function saveAdminSession(token: string, user: User): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token)
  localStorage.setItem(ADMIN_USER_KEY, JSON.stringify(user))
}

export function clearUserSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function clearAdminSession(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY)
  localStorage.removeItem(ADMIN_USER_KEY)
}

function redirectTo(path: string): void {
  if (window.location.pathname === path) return
  const redirect = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.assign(`${path}?redirect=${redirect}`)
}

export function redirectToLogin(): void {
  redirectTo('/login')
}

export function redirectToAdminLogin(): void {
  redirectTo('/admin/login')
}

export function installHttpAuth(): void {
  setHttpAuthHandler({
    getToken: (url) => (isAdminApiPath(url) ? getAdminToken() : getUserToken()),
    onUnauthorized: (url) => {
      if (isAdminApiPath(url)) {
        if (!getAdminToken()) return
        clearAdminSession()
        redirectToAdminLogin()
        return
      }
      if (!getUserToken()) return
      clearUserSession()
      redirectToLogin()
    },
  })
}
