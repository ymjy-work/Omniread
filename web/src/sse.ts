/**
 * 契约 `POST /api/v1/query/stream` 的 SSE 客户端，手写。
 *
 * 用 fetch + ReadableStream 而不是 EventSource：EventSource 只能 GET，
 * 而问答请求体是 JSON。代价是帧解析要自己做，好处是能带请求体、能主动 abort。
 *
 * 两条硬约束：
 * 1. 本模块**不向调用方抛异常** —— 网络错误、非 2xx、非法帧全部走 onError；
 * 2. 出错后不再回调 onEvent，也不重复回调 onError。
 */
import type { ErrorBody, ErrorCode, QueryRequest, SseFrame } from './types'
import { ERROR_CODES, SSE_EVENT_NAMES } from './types'
import { CSRF_HEADERS, notifyUnauthorized } from './api'

/** 本地错误码：流本身断了，契约的 ErrorCode 覆盖不到 */
export type SseLocalErrorCode = 'SSE_STREAM_ERROR'

export interface SseError {
  code: ErrorCode | SseLocalErrorCode
  message: string
  request_id: string | null
}

export interface SseHandlers {
  /** 十个契约事件逐个回调；帧里 event 与 data 成对，switch 后 data 自动收窄 */
  onEvent?: (frame: SseFrame) => void
  /** 唯一失败出口：网络错误、非 2xx、`event: error` 帧 */
  onError?: (error: SseError) => void
  /** 只有收到 `data: [DONE]` 或连接正常结束时回调 */
  onDone?: () => void
}

export interface SseConnection {
  close(): void
  readonly closed: boolean
}

const KNOWN_EVENTS = new Set<string>(SSE_EVENT_NAMES)

export function openQueryStream(
  payload: QueryRequest,
  handlers: SseHandlers = {}
): SseConnection {
  const controller = new AbortController()
  let closed = false
  let failed = false

  const fail = (error: SseError) => {
    if (closed || failed) return
    failed = true
    handlers.onError?.(error)
  }

  const finish = () => {
    if (closed) return
    closed = true
    controller.abort()
    handlers.onDone?.()
  }

  const close = () => {
    if (closed) return
    closed = true
    failed = true // 主动关闭后到达的帧与错误都不再回调
    controller.abort()
  }

  const emit = (name: string, raw: string) => {
    if (raw === '' ) return
    if (raw === '[DONE]') {
      finish()
      return
    }
    if (name === 'error') {
      const body = parseJson(raw)
      fail({
        code: readCode(body),
        message: readString(body, 'message') ?? 'SSE 流返回错误帧',
        request_id: readString(body, 'request_id')
      })
      close()
      return
    }
    if (name === 'message' || name === '') return // 无事件名的裸消息：契约里不存在，忽略
    if (!KNOWN_EVENTS.has(name)) return // 未知事件名不当作错误，向前兼容
    const data = parseJson(raw)
    if (data === null) {
      fail({ code: 'SSE_STREAM_ERROR', message: `事件 ${name} 的负载不是合法 JSON`, request_id: null })
      close()
      return
    }
    handlers.onEvent?.({ event: name, data } as SseFrame)
  }

  void (async () => {
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
    try {
      const response = await fetch('/api/v1/query/stream', {
        method: 'POST',
        // 写操作要带 CSRF 头，流式这一条也不例外（契约对 queryStream 同样声明了它）
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...CSRF_HEADERS },
        body: JSON.stringify(payload),
        signal: controller.signal
      })

      if (!response.ok) {
        // 帧还没开始发时失败会走这里；帧已开始发时 HTTP 状态无法再改，失败只能用终止帧表达
        // 会话中途过期：走 api.ts 那个 401 出口统一跳登录页，别在这儿各显各的
        if (response.status === 401) notifyUnauthorized()
        const text = await response.text().catch(() => '')
        const body = parseJson(text)
        fail({
          code: readCode(body),
          message: readString(body, 'message') ?? `SSE 连接失败：HTTP ${response.status}`,
          request_id: readString(body, 'request_id')
        })
        return
      }
      if (response.body === null) {
        fail({ code: 'SSE_STREAM_ERROR', message: '响应没有可读的流', request_id: null })
        return
      }

      reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      let eventName = ''
      let dataLines: string[] = []

      const dispatch = () => {
        const name = eventName
        const raw = dataLines.join('\n')
        eventName = ''
        dataLines = []
        emit(name, raw)
      }

      // 帧以空行结束；字段行形如 `event: x` / `data: y`，冒号后可有一个空格
      const handleLine = (line: string) => {
        if (line.startsWith(':')) return // 注释行（心跳）
        if (line === '') {
          dispatch()
          return
        }
        const colon = line.indexOf(':')
        const field = colon === -1 ? line : line.slice(0, colon)
        let value = colon === -1 ? '' : line.slice(colon + 1)
        if (value.startsWith(' ')) value = value.slice(1)
        if (field === 'event') eventName = value
        else if (field === 'data') dataLines.push(value)
        // id / retry 前端用不上，显式忽略
      }

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        if (value === undefined) continue
        buffer += decoder.decode(value, { stream: true })
        for (;;) {
          const nl = buffer.indexOf('\n')
          if (nl === -1) break
          let line = buffer.slice(0, nl)
          buffer = buffer.slice(nl + 1)
          if (line.endsWith('\r')) line = line.slice(0, -1)
          handleLine(line)
          if (closed) break
        }
        if (closed) break
      }

      // 连接正常结束：补一个未以空行收尾的尾帧，然后按成功终止处理
      if (!closed) {
        buffer += decoder.decode()
        if (buffer.length > 0) {
          const line = buffer.endsWith('\r') ? buffer.slice(0, -1) : buffer
          handleLine(line)
        }
        if (!closed) dispatch()
        if (!closed) finish()
      }
    } catch (cause) {
      if (!closed) {
        fail({
          code: 'SSE_STREAM_ERROR',
          message: cause instanceof Error ? cause.message : 'SSE 流读取失败',
          request_id: null
        })
        close()
      }
    } finally {
      // 无论怎么退出都要释放读锁，否则连接不会真正断开
      if (reader !== null) {
        try {
          await reader.cancel()
        } catch {
          // 已经取消或已关闭，无需处理
        }
      }
      controller.abort()
    }
  })()

  return {
    close,
    get closed() {
      return closed
    }
  }
}

function parseJson(text: string): unknown {
  if (text.trim() === '') return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

function readString(source: unknown, key: string): string | null {
  if (typeof source !== 'object' || source === null) return null
  const value = (source as Record<string, unknown>)[key]
  return typeof value === 'string' ? value : null
}

function readCode(source: unknown): ErrorCode | SseLocalErrorCode {
  const code = readString(source, 'code')
  // 认不认识这个码查契表的闭枚举（types.ts 的 ERROR_CODES）——
  // 原先按四个码白名单，别的契约码会被错标成「流断了」，而它其实好好地送来了一个业务错误
  return ERROR_CODES.includes(code as ErrorCode) ? (code as ErrorCode) : 'SSE_STREAM_ERROR'
}

/** 供调用方按契约字段判断错误体形状（与 api.ts 的 ApiError 同源语义） */
export function isErrorBody(value: unknown): value is ErrorBody {
  return typeof value === 'object' && value !== null && 'code' in value && 'message' in value
}
