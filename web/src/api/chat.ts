import { http } from './request'
import type { AskRequest, AskResponse } from '../types/chat'

export function ask(sessionId: number, payload: AskRequest) {
  return http.post<AskResponse>(`/chat/sessions/${sessionId}/ask`, payload)
}
