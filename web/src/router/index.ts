import { createRouter, createWebHistory } from 'vue-router'
import { TOKEN_KEY } from '../api/request'
import { useAccountStore } from '../stores/account'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
    },
    {
      path: '/',
      name: 'library',
      component: () => import('../views/LibraryView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/books/:bookId',
      name: 'reader-root',
      component: () => import('../views/ReaderView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/books/:bookId/chapters/:chapterIndex',
      name: 'reader',
      component: () => import('../views/ReaderView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/AdminView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const hasToken = Boolean(localStorage.getItem(TOKEN_KEY))
  if (to.meta.requiresAuth && !hasToken) {
    return {
      name: 'login',
      query: to.fullPath === '/' ? {} : { redirect: to.fullPath },
    }
  }
  if (to.name === 'login' && hasToken) {
    return { name: 'library' }
  }
  if (to.meta.requiresAdmin) {
    const accountStore = useAccountStore()
    const current = accountStore.account ?? (await accountStore.fetchAccount())
    if (!current || current.role !== 'admin') {
      return { name: 'library' }
    }
  }
  return true
})

export default router