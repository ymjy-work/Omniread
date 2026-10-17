/**
 * 需要用户明确确认的错误。**当前只有 `RAG_FORBIDDEN` 走这里**。
 *
 * 它表示「这次操作根本不被允许」——状态栏里的一行文字很容易被当成噪音划过去，
 * 而用户需要知道刚才那一下为什么没成。所以它走弹窗。
 *
 * 状态放在模块级 ref 而不是某个组件里：403 能从**三条路**进来（问答流、会话接口、
 * 书目录与进度）。只在其中一条路上弹窗，另外两条就只剩一行字——同一个错误码有两种表现，
 * 用户看到的就是「有时弹有时不弹」。
 */
import { ref } from 'vue'
import { describeErrorCode } from './errors'
import type { AnyErrorCode } from './errors'

export interface BlockingError {
  /** 人类可读的标题（错误码对应的那句话），用户看到的不是码本身 */
  title: string
  /** 服务端那句更具体的原因；可能为空 */
  detail: string
}

export const blockingError = ref<BlockingError | null>(null)

export function raiseBlocking(code: AnyErrorCode, message: string): void {
  blockingError.value = { title: describeErrorCode(code), detail: message.trim() }
}

export function dismissBlocking(): void {
  blockingError.value = null
}
