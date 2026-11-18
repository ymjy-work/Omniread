# web

Vue 3 + TypeScript + Pinia + Vue Router 前端。

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

开发时 `/api` 由 Vite 代理到 `http://127.0.0.1:8080`（见 `vite.config.ts`）。

目录按 `src/api` / `src/stores` / `src/views` / `src/components` / `src/composables` / `src/types` 分层：
页面组件只负责渲染，状态放 store，请求放 api。
