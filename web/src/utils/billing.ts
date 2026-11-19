import type { ApiProvider, PlanCode, UserRole } from '../types/account'

export const BYOK_PROVIDERS: { value: ApiProvider; label: string }[] = [
  { value: 'bailian', label: '百炼' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'siliconflow', label: '硅基流动' },
]

export const PLAN_ORDER: PlanCode[] = ['free', 'plus', 'pro', 'ultra']

const PLAN_LABELS: Record<string, string> = {
  free: 'Free',
  plus: 'Plus',
  pro: 'Pro',
  ultra: 'Ultra',
}

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  user: '用户',
}

const MODE_LABELS: Record<string, string> = {
  auto: '自动',
  platform: '平台',
  byok: 'BYOK',
}

const KEY_STATUS_LABELS: Record<string, string> = {
  active: '可用',
  valid: '可用',
  invalid: '失效',
  error: '异常',
}

export function planLabel(code: string | null | undefined) {
  return PLAN_LABELS[code ?? ''] ?? (code || '—')
}

export function roleLabel(role: UserRole | string | null | undefined) {
  return ROLE_LABELS[role ?? ''] ?? (role || '—')
}

export function providerLabel(provider: string | null | undefined) {
  return BYOK_PROVIDERS.find((item) => item.value === provider)?.label ?? (provider || '—')
}

export function modeLabel(mode: string | null | undefined) {
  return MODE_LABELS[mode ?? ''] ?? (mode || '—')
}

export function keyStatusLabel(status: string | null | undefined) {
  return KEY_STATUS_LABELS[status ?? ''] ?? (status || '未知')
}

export function formatCredits(value: number | null | undefined) {
  return Number(value ?? 0).toLocaleString('zh-CN')
}

export function formatMoney(value: number | null | undefined) {
  return `¥${Number(value ?? 0).toFixed(2)}`
}

export function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}