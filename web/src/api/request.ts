import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import type { ApiResult } from '../types/api'

export const TOKEN_KEY = 'omniread.token'
export const USER_KEY = 'omniread.user'

export const http = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  return config
})

export class ApiError extends Error {
  code: number

  constructor(code: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

function redirectToLogin() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  if (window.location.pathname !== '/login') {
    const redirect = encodeURIComponent(window.location.pathname + window.location.search)
    window.location.assign(`/login?redirect=${redirect}`)
  }
}

function unwrap<T>(payload: unknown): T {
  if (payload && typeof payload === 'object' && 'code' in payload) {
    const result = payload as ApiResult<T>
    if (result.code === 0) return result.data
    if (result.code === 401) redirectToLogin()
    throw new ApiError(result.code, result.message || '请求失败')
  }
  return payload as T
}

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  try {
    const response = await http.request<ApiResult<T>>(config)
    return unwrap<T>(response.data)
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (axios.isAxiosError(error)) {
      const status = error.response?.status
      if (status === 401) {
        redirectToLogin()
        throw new ApiError(401, '登录已过期，请重新登录')
      }
      const body = error.response?.data
      if (body && typeof body === 'object') {
        const result = body as Partial<ApiResult<unknown>>
        if (typeof result.message === 'string' && result.message) {
          throw new ApiError(typeof result.code === 'number' ? result.code : (status ?? -1), result.message)
        }
      }
      if (!error.response) throw new ApiError(-1, '网络连接失败，请检查后端服务是否启动')
      throw new ApiError(status ?? -1, error.message || '请求失败')
    }
    throw error
  }
}

export function errorMessage(error: unknown, fallback = '请求失败'): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return fallback
}
