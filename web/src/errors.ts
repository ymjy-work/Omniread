/**
 * 错误码 → 人类可读文案。
 *
 * 前端只按 code 分支（契约 ErrorBody 的约定），message 只作辅助信息展示，
 * 不做字符串匹配。NETWORK_ERROR / MALFORMED_RESPONSE / SSE_STREAM_ERROR
 * 是本地产生的码（没有响应体可读），语义见 api.ts 与 sse.ts。
 */
import type { ErrorCode } from './types'
import type { LocalErrorCode } from './api'
import type { SseLocalErrorCode } from './sse'

export type AnyErrorCode = ErrorCode | LocalErrorCode | SseLocalErrorCode

const TEXT: Record<AnyErrorCode, string> = {
  RAG_INVALID_REALM: '提问超出了可回答的章节范围',
  RAG_PROVIDER_ERROR: '模型服务异常，请稍后重试',
  RAG_UNAVAILABLE: '问答服务暂不可用',
  RAG_TIMEOUT: '回答超时',
  NETWORK_ERROR: '连不上 Java 网关',
  MALFORMED_RESPONSE: '服务返回了无法识别的响应',
  SSE_STREAM_ERROR: '事件流中断'
}

export function describeErrorCode(code: AnyErrorCode): string {
  return TEXT[code] ?? code
}

/** 错误行文案：错误码在前，具体 message 收在括号里，便于定位又不喧宾夺主 */
export function formatErrorLine(code: AnyErrorCode, message: string): string {
  return `⚠ ${code}（${describeErrorCode(code)}${message ? ` · ${message}` : ''}）`
}
