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
  ErrorBody,
  ErrorCode,
  Health,
  Progress,
  QueryRequest,
  QueryResponse
} from './types'

const BASE = '/api/v1'

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(BASE + path, {
      headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}) },
      ...init
    })
  } catch (cause) {
    // 网关没起来 / 断网：没有响应体，只能给本地错误码
    throw new ApiError('NETWORK_ERROR', cause instanceof Error ? cause.message : '请求失败')
  }

  if (!response.ok) {
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

/** 存活探针：只报 Java 自身存活 */
export function health(): Promise<Health> {
  return request<Health>('/health')
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

export function putProgress(bookId: number, maxSeq: number): Promise<Progress> {
  return request<Progress>(`/books/${bookId}/progress`, {
    method: 'PUT',
    body: JSON.stringify({ max_seq: maxSeq })
  })
}

/** 单轮问答（JSON 同步）。前端走 sse.ts 的流式路径，这个留给脚本与调试。 */
export function query(payload: QueryRequest): Promise<QueryResponse> {
  return request<QueryResponse>('/query', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}
