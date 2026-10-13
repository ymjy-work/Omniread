/**
 * 会话：列表 / 当前会话 / 新建 / 打开 / 删除 / 分叉。
 *
 * **消息不在这个模块里**——消息是 `ChatPanel` 的渲染状态（气泡、流式、耗时都在那儿）；
 * 这里只管「有哪些会话、当前是哪一个」。
 *
 * 两条口径：
 *
 * - **档位固定在会话上**（契约）：切档位不是改当前会话，而是分叉出一个新的（见 `fork`）。
 * - **新建是懒的**：没有当前会话时，第一句提问才建——这样每个会话都有内容，
 *   列表里不会攒一堆问都没问过的空壳。
 */
import { ref } from 'vue'
import * as api from './api'
import { ApiError } from './api'
import { formatErrorLine } from './errors'
import type { ChatSessionSummary, QueryLevel, SessionDetail } from './types'

export const sessions = ref<ChatSessionSummary[]>([])
/** 当前会话；null = 还没开始（第一句提问时新建） */
export const active = ref<ChatSessionSummary | null>(null)
export const sessionsError = ref<string | null>(null)

function noteError(cause: unknown): void {
  sessionsError.value =
    cause instanceof ApiError ? formatErrorLine(cause.code, cause.message) : String(cause)
}

/** 拉一次列表（服务端已按最近活跃倒序），并顺手把 `active` 同步成最新的一份 */
export async function refresh(): Promise<void> {
  try {
    const data = await api.listSessions()
    sessions.value = data.sessions
    const current = active.value
    if (current !== null) {
      // 对不上说明它在别处被删了（或这是分叉前的旧对象）：以服务端为准
      active.value = data.sessions.find((s) => s.id === current.id) ?? null
    }
    sessionsError.value = null
  } catch (cause) {
    noteError(cause)
  }
}

/** 打开会话（取详情，含消息）并设为当前。返回 null = 失败，错误已记在 `sessionsError` */
export async function open(sessionId: string): Promise<SessionDetail | null> {
  try {
    const detail = await api.getSession(sessionId)
    active.value = detail
    sessionsError.value = null
    return detail
  } catch (cause) {
    noteError(cause)
    return null
  }
}

export async function create(bookId: number, level: QueryLevel): Promise<ChatSessionSummary | null> {
  try {
    const created = await api.createSession(bookId, level)
    sessions.value = [created, ...sessions.value]
    active.value = created
    sessionsError.value = null
    return created
  } catch (cause) {
    noteError(cause)
    return null
  }
}

export async function remove(sessionId: string): Promise<boolean> {
  try {
    await api.deleteSession(sessionId)
    sessions.value = sessions.value.filter((s) => s.id !== sessionId)
    if (active.value?.id === sessionId) active.value = null
    sessionsError.value = null
    return true
  } catch (cause) {
    noteError(cause)
    return false
  }
}

/**
 * 切档位分叉：复制父会话截至当前点的消息进新会话（父会话一律不动），新会话成为当前。
 * 调用方**必须先让用户确认**——既然叫分叉，就得让人知道旧会话还在。
 *
 * 不传 `at_seq`：缺省就是「复制到当前最后一条」，而「完整轮」怎么算是服务端的排版知识。
 */
export async function fork(level: QueryLevel): Promise<ChatSessionSummary | null> {
  const parent = active.value
  if (parent === null) return null
  try {
    const forked = await api.forkSession(parent.id, level)
    sessions.value = [forked, ...sessions.value]
    active.value = forked
    sessionsError.value = null
    return forked
  } catch (cause) {
    noteError(cause)
    return null
  }
}

export function levelLabel(level: QueryLevel): string {
  return level === 'past' ? '回顾' : '剧透'
}

/** 某本书下的会话（列表接口不按书过滤——那是前端的事） */
export function forBook(bookId: number | null): ChatSessionSummary[] {
  if (bookId === null) return []
  return sessions.value.filter((session) => session.book_id === bookId)
}
