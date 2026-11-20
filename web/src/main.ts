import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import { installHttpAuth } from './auth/session'
import './style.css'
import App from './App.vue'
import router from './router'

installHttpAuth()
createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
