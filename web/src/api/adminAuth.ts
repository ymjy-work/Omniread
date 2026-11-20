import { request } from './request'
import type { AuthResponse, LoginRequest } from '../types/api'

export function adminLogin(payload: LoginRequest) {
  return request<AuthResponse>({ url: '/admin/auth/login', method: 'post', data: payload })
}

export function adminLogout() {
  return request<void>({ url: '/admin/auth/logout', method: 'post' })
}
