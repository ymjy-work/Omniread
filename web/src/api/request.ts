import axios from 'axios'

export const http = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 登录态清理与跳转在 auth store 接入后补全
    }
    return Promise.reject(error)
  },
)
