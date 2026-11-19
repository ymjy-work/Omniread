import { request } from './request'
import type { Account, ApiKeyRecord, ApiProvider, PlanCatalog, PlanCode } from '../types/account'

export function getAccount() {
  return request<Account>({ url: '/me/account', method: 'get' })
}

export function listPlans() {
  return request<PlanCatalog[]>({ url: '/plans', method: 'get' })
}

export function purchasePlan(plan: PlanCode) {
  return request<Account>({ url: '/me/plan', method: 'post', data: { plan } })
}

export function listApiKeys() {
  return request<ApiKeyRecord[]>({ url: '/me/api-keys', method: 'get' })
}

export function saveApiKey(provider: ApiProvider, key: string) {
  return request<ApiKeyRecord>({
    url: '/me/api-keys',
    method: 'post',
    data: { provider, key },
  })
}

export function deleteApiKey(provider: ApiProvider) {
  return request<void>({
    url: '/me/api-keys',
    method: 'delete',
    params: { provider },
  })
}
export function fetchProviderModels(provider: ApiProvider) {
  return request<string[]>({
    url: `/me/api-keys/${provider}/models`,
    method: 'get',
  })
}