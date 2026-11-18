import { request } from './request'
import type { AuthResponse, LoginRequest } from '../types/api'

export function login(payload: LoginRequest) {
  return request<AuthResponse>({ url: '/auth/login', method: 'post', data: payload })
}

export function logout() {
  return request<void>({ url: '/auth/logout', method: 'post' })
}
