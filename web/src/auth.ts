/**
 * 登录态：当前账户，以及「探过没有」。
 *
 * 判定口径在**路由守卫一处**（`main.ts`）：进功能页之前 `await ensureLoaded()`，
 * 它只发一次 `GET /auth/me`，结果缓存在这里；此后每次导航读的是这个缓存，不再打接口。
 *
 * 不用 localStorage 记登录态：**真正的凭据是 HttpOnly 的会话 cookie，前端读不到**，
 * 记一个「我以为登录了」的布尔值只会与 cookie 的真实状态漂移——每次启动问一次服务端，
 * 是唯一不会说谎的判定。
 */
import { ref } from 'vue'
import * as api from './api'
import type { CurrentUser } from './types'

export const current = ref<CurrentUser | null>(null)

let probe: Promise<void> | null = null

/**
 * 启动时探一次登录态。并发导航共用同一个 Promise，不会打出两次 `/auth/me`；
 * 探测失败（未登录、网关不通）一律记成「没登录」——登录门按未登录放行到登录页，
 * 真正的失败原因会在登录尝试时以错误码显示出来。
 */
export function ensureLoaded(): Promise<void> {
  probe ??= api.me().then(
    (user) => {
      current.value = user
    },
    () => {
      current.value = null
    }
  )
  return probe
}

export function isAuthed(): boolean {
  return current.value !== null
}

export async function signIn(username: string, password: string): Promise<void> {
  current.value = await api.login(username, password)
}

/**
 * 退出。**即使请求失败也要本地清空**：服务端的会话行没删掉是它的事（下次 401 或到期后
 * 自然收敛），而把用户留在一个「点了退出却还在登录态」的界面上，是这边的事务。
 */
export async function signOut(): Promise<void> {
  try {
    await api.logout()
  } finally {
    current.value = null
  }
}

/** 401 出口用：会话没了，只清本地状态，跳转由调用方做 */
export function clear(): void {
  current.value = null
}
