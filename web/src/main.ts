import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import LibraryView from './views/LibraryView.vue'
import LoginView from './views/LoginView.vue'
import ReaderView from './views/ReaderView.vue'
import SettingsView from './views/SettingsView.vue'
import WelcomeView from './views/WelcomeView.vue'
import { setUnauthorizedHandler } from './api'
import { clear as clearAuth, ensureLoaded, isAuthed } from './auth'

// 阅读路由带 bookId 与 chapterIndex：两者都在 URL 里，刷新与直接分享链接都能还原视图
const router = createRouter({
  history: createWebHistory(),
  routes: [
    // 两张「画布页」（门厅与登录页）**不进三栏壳**：它们自带整屏构图，
    // 而壳（活动栏 / 侧栏 / 常驻问答）对还没进来的人没有意义。见 App.vue 的判断。
    // `public` 是登录门的豁免标记——只有这两条不需要登录态。
    //
    // 门厅占 `/`：进站先看到「这是什么、边界在哪儿」，比一上来就撞登录框说得通。
    // 它不要登录态；点「探索故事」时未登录的人由守卫拦到 /login（见下方 beforeEach）。
    { path: '/', name: 'welcome', component: WelcomeView, meta: { shell: false, public: true } },
    // 旧地址留着：文档与外部链接都指向过 /welcome
    { path: '/welcome', redirect: '/' },
    { path: '/login', name: 'login', component: LoginView, meta: { shell: false, public: true } },
    { path: '/library', name: 'library', component: LibraryView },
    // 设置是整页而不是弹窗，也不进三栏壳：它跟「在读哪本书」无关，套着章节栏会让人误会
    { path: '/settings', name: 'settings', component: SettingsView, meta: { shell: false } },
    {
      path: '/books/:bookId(\\d+)/chapters/:chapterIndex(\\d+)',
      name: 'reader',
      component: ReaderView
    },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})

/**
 * 登录门：**就这么一处**。未登录访问功能页一律去 `/login`，并带上原地址供回跳；
 * 页面上不逐颗按钮判断「登没登录」——那样迟早漏掉一个入口。
 *
 * 登录态问一次服务端（`ensureLoaded` 内部缓存，多个导航不会重复打接口）；
 * 已登录的人到 `/login` 直接送回书库。
 */
router.beforeEach(async (to) => {
  if (to.meta.public !== true) {
    await ensureLoaded()
    if (!isAuthed()) return { name: 'login', query: { redirect: to.fullPath } }
    return true
  }
  if (to.name === 'login') {
    await ensureLoaded()
    if (isAuthed()) return { name: 'library' }
  }
  return true
})

/**
 * 401 的唯一出口：会话过期 / 被停用之后，任何一个接口的 401 都在这里收口——
 * 清本地登录态并跳登录页。收口在 `api.ts` 一处触发（sse.ts 的流式 401 也走它）。
 */
setUnauthorizedHandler(() => {
  clearAuth()
  const current = router.currentRoute.value
  // 公开页（门厅 / 登录页）与「路由还没匹配上」都不踢：它们本来就不需要登录态，
  // 在这些地方出现的 401 是「还没登录」，不是「会话失效」。
  if (current.matched.length === 0 || current.meta.public === true) return
  void router.replace({ name: 'login', query: { redirect: current.fullPath } })
})

createApp(App).use(router).mount('#app')
