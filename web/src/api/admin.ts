import { request } from './request'
import type { AdminUser, CreateUserRequest, GrantBalanceRequest } from '../types/account'

export function listUsers() {
  return request<AdminUser[]>({ url: '/admin/users', method: 'get' })
}

export function createUser(payload: CreateUserRequest) {
  return request<AdminUser>({ url: '/admin/users', method: 'post', data: payload })
}

export function grantBalance(userId: number, payload: GrantBalanceRequest) {
  return request<AdminUser>({
    url: `/admin/users/${userId}/balance`,
    method: 'post',
    data: payload,
  })
}