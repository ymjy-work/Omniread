<script setup lang="ts">
/**
 * 三栏骨架：活动栏 / 侧栏 / 主内容 + 右侧剧情问答。四个区块都在这里落位，
 * 主内容由路由决定（书库 / 阅读），侧栏与问答跨路由常驻。
 *
 * 例外是标了 `meta.shell = false` 的路由（介绍页）：**整屏给它**，不套壳。
 * 门厅里出现一组指向应用的按钮、却哪儿也去不了，比没有这组按钮更糟。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ActivityRail from './components/ActivityRail.vue'
import ChatPanel from './components/ChatPanel.vue'
import NoticeGate from './components/NoticeGate.vue'
import SidePanel from './components/SidePanel.vue'
import StatusBar from './components/StatusBar.vue'

const route = useRoute()
const withShell = computed(() => route.meta.shell !== false)
</script>

<template>
  <div class="root">
    <div v-if="withShell" class="app">
      <ActivityRail />
      <SidePanel />
      <router-view />
      <ChatPanel />
    </div>
    <router-view v-else />
    <StatusBar v-if="withShell" />
    <!-- 使用须知：进功能页之后弹一次（见组件注释）。门厅不弹——那儿还没到用它的时候 -->
    <NoticeGate v-if="withShell" />
  </div>
</template>
