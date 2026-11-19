import { createRouter, createWebHistory } from 'vue-router'
import { TOKEN_KEY } from '../api/request'
import { useAccountStore } from '../stores/account'

function safeInternalRedirect(value: unknown): string | null {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//')
    ? value
    : null
}

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, top: 76, behavior: 'smooth' }
    return { top: 0 }
  },
  routes: [
    {
      path: '/',
      name: 'landing',
      component: () => import('../views/LandingView.vue'),
    },
    {
      path: '/plans',
      name: 'plans',
      component: () => import('../views/PlanView.vue'),
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
    },
    {
      path: '/library',
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
    {
      path: '/plan',
      name: 'legacy-plan',
      redirect: '/plans',
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const hasToken = Boolean(localStorage.getItem(TOKEN_KEY))

  if (to.name === 'login' && hasToken) {
    const target = safeInternalRedirect(to.query.redirect)
    return target ?? { name: 'library' }
  }

  if (to.meta.requiresAuth && !hasToken) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresAdmin) {
    const account = await useAccountStore().fetchAccount(true)
    if (!account) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (account.role !== 'admin') return { name: 'library' }
  }

  return true
})

export default router