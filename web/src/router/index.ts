import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
    { path: '/', name: 'library', component: () => import('../views/LibraryView.vue') },
    {
      path: '/books/:bookId/chapters/:chapterIndex',
      name: 'reader',
      component: () => import('../views/ReaderView.vue'),
    },
    { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
  ],
})

router.beforeEach(() => {
  // 登录守卫在 auth store 接入后补全
  return true
})

export default router
