import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import LibraryView from './views/LibraryView.vue'
import ReaderView from './views/ReaderView.vue'
import WelcomeView from './views/WelcomeView.vue'

// 阅读路由带 bookId 与 chapterIndex：两者都在 URL 里，刷新与直接分享链接都能还原视图
const router = createRouter({
  history: createWebHistory(),
  routes: [
    // 介绍 / 导航页是「门厅」，**不进三栏壳**：它自带整屏滚动，
    // 而壳（活动栏 / 侧栏 / 常驻问答）对还没进来的人没有意义。见 App.vue 的判断。
    { path: '/welcome', name: 'welcome', component: WelcomeView, meta: { shell: false } },
    { path: '/', name: 'library', component: LibraryView },
    {
      path: '/books/:bookId(\\d+)/chapters/:chapterIndex(\\d+)',
      name: 'reader',
      component: ReaderView
    },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})

createApp(App).use(router).mount('#app')
