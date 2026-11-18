# web

Vue 3 + TypeScript + Pinia + Vue Router 前端，提供中文小说阅读与 RAG 对话界面。

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

开发时 `/api` 由 Vite 代理到 `http://127.0.0.1:8080`（见 `vite.config.ts`）。

## 页面

- `/login` 登录：用户名/密码登录，token 与用户信息写入 localStorage 和 auth store。
- `/` 书库：书籍卡片，点击进入阅读；入口带加载/错误/空状态。
- `/books/:bookId/chapters/:chapterIndex` 阅读页：章节目录、正文、上一章/下一章、滚动进度保存与恢复。
- `/books/:bookId` 阅读页入口：先读取进度，再跳到对应章节。
- `/settings` 设置：主题（明亮/护眼/夜间）、正文字号、账号退出。
- 阅读页移动端提供目录抽屉与对话抽屉；桌面端目录与对话常驻侧栏。

## 交互

- 对话面板支持 `past`（已读范围）/ `full`（全书）切换，Enter 发送、Shift+Enter 换行。
- 助手消息的引用显示为角标；点击后跳到对应章节，并用 `quote` 在正文中定位高亮，找不到时只跳章。
- 滚动停止 1 秒后保存进度（`scrollRatio`），切章、离开页面或隐藏标签页时立即补存。
- 401 统一清理登录态并跳转登录页。

## 接口

所有响应在 `src/api/request.ts` 统一解包 `Result { code, message, data }`（`code = 0` 成功），调用方直接拿 `data`。

- `POST /api/auth/login { username, password }`
- `GET /api/books`
- `GET /api/books/{id}`
- `GET /api/books/{id}/chapters`
- `GET /api/books/{id}/chapters/{chapterIndex}`
- `GET /api/books/{id}/progress`
- `PUT /api/books/{id}/progress { chapterIndex, scrollRatio }`
- `POST /api/chat/sessions { bookId }`
- `GET /api/chat/sessions?bookId={bookId}`
- `GET /api/chat/sessions/{id}/messages`
- `POST /api/chat/sessions/{id}/ask { question, level }`

## 目录

`src/api` 只发请求，`src/stores` 保存状态，`src/views` 与 `src/components` 负责渲染，`src/composables` 处理进度与聊天交互。主题和字号分别保存在 `omniread.theme`、`omniread.fontSize`；登录态在 `omniread.token`、`omniread.user`。