import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { ApiError } from './errors'
import { http, notifyUnauthorized } from './http'
import type { ApiResult } from '../types/api'

interface ParsedApiMessage {
  code: number | undefined
  message: string | undefined
}

function parseApiMessage(payload: unknown): ParsedApiMessage {
  if (!payload || typeof payload !== 'object') return { code: undefined, message: undefined }
  const result = payload as Partial<ApiResult<unknown>>
  return {
    code: typeof result.code === 'number' ? result.code : undefined,
    message: typeof result.message === 'string' && result.message ? result.message : undefined,
  }
}

function unwrap<T>(payload: unknown): T {
  if (payload && typeof payload === 'object' && 'code' in payload) {
    const result = payload as ApiResult<T>
    if (result.code === 0) return result.data
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
      const { code, message } = parseApiMessage(error.response?.data)

      if (status === 401) {
        notifyUnauthorized(config.url)
        throw new ApiError(code ?? 401, message ?? '登录已过期，请重新登录')
      }
      if (message) throw new ApiError(code ?? status ?? -1, message)
      if (!error.response) throw new ApiError(-1, '网络连接失败，请检查后端服务是否启动')
      throw new ApiError(status ?? -1, error.message || '请求失败')
    }
    throw error
  }
}
