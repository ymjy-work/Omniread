export type UserRole = 'admin' | 'user'
export type PlanCode = 'free' | 'plus' | 'pro' | 'ultra'
export type ApiProvider = 'bailian' | 'openai' | 'deepseek' | 'siliconflow'

export interface Account {
  role: UserRole
  plan: PlanCode
  credits: number
  balance: number
  planExpiresAt?: string | null
}

export interface PlanCatalog {
  code: PlanCode
  price: number
  credits: number
  durationDays: number
}

export interface ApiKeyRecord {
  provider: ApiProvider
  keyMask: string
  status?: string | null
  createdAt?: string | null
  lastCheckedAt?: string | null
}

export interface ModelOption {
  provider: string
  model: string
  displayName?: string
}

export interface ByokProviderOption {
  provider: ApiProvider
  models: string[]
}

export interface AdminUser {
  id: number
  username: string
  displayName?: string | null
  role: UserRole | string
  plan: PlanCode | string
  credits: number
  balance: number
  planExpiresAt?: string | null
  createdAt?: string | null
}

export interface CreateUserRequest {
  username: string
  password: string
  displayName?: string
}

export interface GrantBalanceRequest {
  amount: number
  reason?: string
}