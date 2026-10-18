/**
 * 契约 contracts/openapi/frontend-api-v1.yaml 里八个路径的调用封装。
 *
 * base 用相对路径：前端与 Java 网关同源（开发期 Vite proxy 转发 /api，
 * 生产由 Java 托管 web/dist）。写死主机名会在生产形态下直接失效。
 */
import type {
  BookList,
  ChapterDetail,
  ChapterList,
  ChatSessionSummary,
  CurrentUser,
  ErrorBody,
  ErrorCode,
  Progress,
  ProgressWrite,
  QueryLevel,
  SessionDetail,
  SessionList
} from './types'

const BASE = '/api/v1'

/**
 * 写操作必须带的 CSRF 头（契约 `parameters.CsrfHeader`）。
 * **值不参与判断**——服务端只查「带了没有」，所以常量即可；真正拦住跨站请求的是
 * 浏览器对自定义头的同源限制。sse.ts 的流式 POST 也吃这一份。
 */
export const CSRF_HEADERS: Readonly<Record<string, string>> = { 'X-Omniread-Csrf': '1' }

/** 安全方法（不带 CSRF 头、也不改状态）；其余一律按写操作补头 */
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/** 本地产生的错误码：请求根本没拿到响应体，契约的 ErrorCode 覆盖不到 */
export type LocalErrorCode = 'NETWORK_ERROR' | 'MALFORMED_RESPONSE'

export class ApiError extends Error {
  readonly status: number
  readonly code: ErrorCode | LocalErrorCode
  readonly requestId: string | null

  constructor(
    code: ErrorCode | LocalErrorCode,
    message: string,
    status = 0,
    requestId: string | null = null
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.requestId = requestId
  }
}

function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== 'object' || value === null) return false
  const body = value as Record<string, unknown>
  return typeof body.code === 'string' && typeof body.message === 'string'
}

/**
 * 401 的唯一出口。会话过期或被停用之后，任何一个接口的 401 都由这个钩子
 * 统一清登录态并跳登录页（挂在 `main.ts` 一处）——调用方各自处理会有人漏。
 */
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

/** 供 sse.ts 用：流式请求的 401 走同一个出口 */
export function notifyUnauthorized(): void {
  onUnauthorized?.()
}

interface RequestOptions {
  /**
   * 跳过 401 出口。「本来就在探登录态」的两个调用（`me` 与 `login`）必须跳过：
   * 它们的 401 是**预期结果**（没登录 / 口令错），不是「会话中途失效」。
   */
  skipAuthRedirect?: boolean
}

async function request<T>(path: string, init?: RequestInit, options: RequestOptions = {}): Promise<T> {
  const method = (init?.method ?? 'GET').toUpperCase()
  let response: Response
  try {
    response = await fetch(BASE + path, {
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...(SAFE_METHODS.has(method) ? {} : CSRF_HEADERS)
      },
      ...init
    })
  } catch (cause) {
    // 网关没起来 / 断网：没有响应体，只能给本地错误码
    throw new ApiError('NETWORK_ERROR', cause instanceof Error ? cause.message : '请求失败')
  }

  if (!response.ok) {
    if (response.status === 401 && options.skipAuthRedirect !== true) notifyUnauthorized()
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    if (isErrorBody(body)) {
      throw new ApiError(body.code, body.message, response.status, body.request_id)
    }
    throw new ApiError('MALFORMED_RESPONSE', `HTTP ${response.status}`, response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function listBooks(): Promise<BookList> {
  return request<BookList>('/books')
}

export function listChapters(bookId: number): Promise<ChapterList> {
  return request<ChapterList>(`/books/${bookId}/chapters`)
}

export function getChapter(bookId: number, chapterIndex: number): Promise<ChapterDetail> {
  return request<ChapterDetail>(`/books/${bookId}/chapters/${chapterIndex}`)
}

export function getProgress(bookId: number): Promise<Progress> {
  return request<Progress>(`/books/${bookId}/progress`)
}

export function putProgress(bookId: number, progress: number): Promise<Progress> {
  const body: ProgressWrite = { progress }
  return request<Progress>(`/books/${bookId}/progress`, {
    method: 'PUT',
    body: JSON.stringify(body)
  })
}

// ---------- 会话 ----------

/** 我的会话列表（服务端已按最近活跃倒序）。**别人的会话不会出现在这里，也取不到** */
export function listSessions(): Promise<SessionList> {
  return request<SessionList>('/sessions')
}

export function createSession(bookId: number, level: QueryLevel): Promise<ChatSessionSummary> {
  return request<ChatSessionSummary>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ book_id: bookId, level })
  })
}

/** 会话详情（含消息）。消息**不带 meta**，所以恢复出来的气泡没有引用与耗时 */
export function getSession(sessionId: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${encodeURIComponent(sessionId)}`)
}

/** 删除会话（连同它的消息）。别人的会话删不掉，返回 403 */
export function deleteSession(sessionId: string): Promise<void> {
  return request<void>(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}

/**
 * 改会话标题。挂子资源上而不是 PATCH 整个会话：标题是唯一可改的字段。
 * 上限 20 码点由服务端判（`emoji` 占两个 char，前端不重复算一遍）。
 */
export function renameSession(sessionId: string, title: string): Promise<ChatSessionSummary> {
  return request<ChatSessionSummary>(`/sessions/${encodeURIComponent(sessionId)}/title`, {
    method: 'PUT',
    body: JSON.stringify({ title })
  })
}

/**
 * 切档位分叉：复制父会话截至 `at_seq` 的消息进新会话，父会话的档位与消息一律不动。
 *
 * `at_seq` 缺省 = 复制到当前最后一条（「继承到当前点」）。前端**不该自己算「完整轮」**
 * 再传进来——那是服务端的排版知识，算错了的表现是新会话凭空少一段上下文（见契约 ForkRequest）。
 */
export function forkSession(
  sessionId: string,
  level: QueryLevel,
  atSeq?: number
): Promise<ChatSessionSummary> {
  return request<ChatSessionSummary>(`/sessions/${encodeURIComponent(sessionId)}/fork`, {
    method: 'POST',
    body: JSON.stringify(atSeq === undefined ? { level } : { level, at_seq: atSeq })
  })
}

// ---------- 认证 ----------

/**
 * 登录。**不带 CSRF 头**（它是拿到 cookie 的那一步，本就不在登录门内，契约同此）。
 * 成功时会话 cookie 在响应头的 `Set-Cookie` 里，浏览器自己收下——前端不碰 token。
 */
export function login(username: string, password: string): Promise<CurrentUser> {
  return request<CurrentUser>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify({ username, password }) },
    { skipAuthRedirect: true }
  )
}

/** 退出：服务端删会话行并清 cookie。会话已过期时是 401，按「已经登出」处理即可。 */
export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' })
}

/** 当前账户。未登录是 401（不是 200 + null）——两种状态前端要分得开 */
export function me(): Promise<CurrentUser> {
  return request<CurrentUser>('/auth/me', undefined, { skipAuthRedirect: true })
}
