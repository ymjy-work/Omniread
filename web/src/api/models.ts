import { request } from './request'
import type { ByokProviderOption, ApiProvider, ModelOption } from '../types/account'

export function listPlatformModels(provider = 'bailian') {
  return request<ModelOption[]>({
    url: '/models',
    method: 'get',
    params: { mode: 'platform', provider },
  })
}

export function listByokProviders(provider?: ApiProvider) {
  return request<ByokProviderOption[]>({
    url: '/models',
    method: 'get',
    params: { mode: 'byok', provider },
  })
}