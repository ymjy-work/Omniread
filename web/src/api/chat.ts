import { request } from './request'
import type { AskRequest, AskResponse, ChatMessage, ChatSession } from '../types/chat'

export function createSession(bookId: number) {
  return request<ChatSession>({ url: '/chat/sessions', method: 'post', data: { bookId } })
}

export function listSessions(bookId: number) {
  return request<ChatSession[]>({ url: '/chat/sessions', method: 'get', params: { bookId } })
}

export function listMessages(sessionId: number) {
  return request<ChatMessage[]>({ url: `/chat/sessions/${sessionId}/messages`, method: 'get' })
}

export function ask(sessionId: number, payload: AskRequest) {
  return request<AskResponse>({ url: `/chat/sessions/${sessionId}/ask`, method: 'post', data: payload })
}
