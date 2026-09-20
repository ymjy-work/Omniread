<script setup lang="ts">
/**
 * 三栏骨架：活动栏 / 侧栏 / 主内容 + 右侧剧情问答。四个区块都在这里落位，
 * 主内容由路由决定（书库 / 阅读），侧栏与问答跨路由常驻。
 */
import ActivityRail from './components/ActivityRail.vue'
import ChatPanel from './components/ChatPanel.vue'
import SidePanel from './components/SidePanel.vue'
import StatusBar from './components/StatusBar.vue'
</script>

<template>
  <div class="root">
    <div class="app">
      <ActivityRail />
      <SidePanel />
      <router-view />
      <ChatPanel />
    </div>
    <StatusBar />
  </div>
</template>
