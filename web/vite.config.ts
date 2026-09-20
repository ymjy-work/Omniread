import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端与 Java 网关同源：开发期由下方 proxy 把 /api 转给网关，生产由 Java 托管 web/dist。
// 前端不直连 Python（M0-00 §4 冻结），因此这里只有网关一个 target。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': '/src' }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
})
