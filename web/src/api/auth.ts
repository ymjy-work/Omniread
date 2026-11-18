import { http } from './request'
import type { AuthResponse, LoginRequest } from '../types/api'

export function login(payload: LoginRequest) {
  return http.post<AuthResponse>('/auth/login', payload)
}

export function logout() {
  return http.post<void>('/auth/logout')
}
