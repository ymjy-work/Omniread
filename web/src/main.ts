import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import LibraryView from './views/LibraryView.vue'
import ReaderView from './views/ReaderView.vue'

// 阅读路由带 bookId 与 chapterIndex：两者都在 URL 里，刷新与直接分享链接都能还原视图
const router = createRouter({
  history: createWebHistory(),
  routes: [
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
