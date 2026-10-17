<script setup lang="ts">
/**
 * 三栏骨架：活动栏 / 侧栏 / 主内容 + 右侧剧情问答。四个区块都在这里落位，
 * 主内容由路由决定（书库 / 阅读），侧栏与问答跨路由常驻。
 *
 * 例外是标了 `meta.shell = false` 的路由（介绍页）：**整屏给它**，不套壳。
 * 门厅里出现一组指向应用的按钮、却哪儿也去不了，比没有这组按钮更糟。
 */
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { blockingError, dismissBlocking } from './blocking'
import ActivityRail from './components/ActivityRail.vue'
import AppDialog from './components/AppDialog.vue'
import ChatPanel from './components/ChatPanel.vue'
import NoticeGate from './components/NoticeGate.vue'
import SidePanel from './components/SidePanel.vue'
import StatusBar from './components/StatusBar.vue'

const route = useRoute()
const withShell = computed(() => route.meta.shell !== false)

/**
 * 窄屏下当前打开的那一栏。同一时刻只开一个——两个抽屉同时滑出来会互相盖住，
 * 而且屏幕本来就窄。宽屏下这个值不影响布局（抽屉规则都在媒体查询里）。
 */
const drawer = ref<'chapters' | 'chat' | null>(null)
const toggle = (which: 'chapters' | 'chat') => {
  drawer.value = drawer.value === which ? null : which
}

// 换了路由就收起来：点章节、切书都该立刻看到正文，而不是被抽屉挡着
watch(() => route.fullPath, () => {
  drawer.value = null
})
</script>

<template>
  <div class="root">
    <div v-if="withShell" class="app" :data-drawer="drawer ?? undefined">
      <ActivityRail />
      <SidePanel />
      <router-view />
      <ChatPanel />
      <!-- 窄屏顶栏：宽屏下 display:none（两栏都在位，没有可开合的抽屉） -->
      <div class="shellbar">
        <button
          class="sbtn"
          :class="{ on: drawer === 'chapters' }"
          :aria-expanded="drawer === 'chapters'"
          aria-label="章节"
          @click="toggle('chapters')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M4 6.5h16M4 12h16M4 17.5h16" />
          </svg>
        </button>
        <button
          class="sbtn"
          :class="{ on: drawer === 'chat' }"
          :aria-expanded="drawer === 'chat'"
          aria-label="剧情问答"
          @click="toggle('chat')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M21 11.5a7.5 7.5 0 01-10.9 6.7L5 20l1.6-4.4A7.5 7.5 0 1121 11.5z" />
          </svg>
        </button>
      </div>
      <!-- 点空白处收起：抽屉盖住正文时，正文本身收不到点击 -->
      <div v-if="drawer" class="scrim" @click="drawer = null"></div>
    </div>
    <router-view v-else />
    <StatusBar v-if="withShell" />
    <!-- 使用须知：进功能页之后弹一次（见组件注释）。门厅不弹——那儿还没到用它的时候 -->
    <NoticeGate v-if="withShell" />

    <!-- 403 的单一出口：问答流、会话接口、书目录与进度三条路都汇到这里。
         放在根级，所以设置页这类 `shell: false` 的页面也照样弹 -->
    <AppDialog
      :open="blockingError !== null"
      :title="blockingError?.title ?? ''"
      :width="400"
      @close="dismissBlocking"
    >
      <p v-if="blockingError?.detail">{{ blockingError.detail }}</p>
      <template #actions>
        <button class="dlg-btn primary" @click="dismissBlocking">知道了</button>
      </template>
    </AppDialog>
  </div>
</template>
