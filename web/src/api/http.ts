import axios from 'axios'

export interface HttpAuthHandler {
  getToken(url?: string): string | null
  onUnauthorized(url?: string): void
}

let authHandler: HttpAuthHandler | null = null

export function setHttpAuthHandler(handler: HttpAuthHandler): void {
  authHandler = handler
}

export function notifyUnauthorized(url?: string): void {
  authHandler?.onUnauthorized(url)
}

export const http = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

http.interceptors.request.use((config) => {
  const token = authHandler?.getToken(config.url)
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  return config
})
