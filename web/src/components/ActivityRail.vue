<script setup lang="ts">
/** 活动栏：书库 / 章节两个板块入口 + 深浅切换。图标为内联 SVG，不引图标库。 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { store } from '../store'
import { theme, toggleTheme } from '../theme'

const route = useRoute()
const router = useRouter()

const onLibrary = computed(() => route.name !== 'reader')

function openLibrary(): void {
  void router.push({ name: 'library' })
}

/** 没有选中的书时章节入口不可用——它没有可去的地方 */
function openReader(): void {
  const bookId = store.bookId
  if (bookId === null) return
  const chapter = store.chapter?.chapter_index ?? store.progress?.max_seq ?? 1
  void router.push({ name: 'reader', params: { bookId, chapterIndex: chapter } })
}
</script>

<template>
  <nav class="rail glass">
    <div class="logo">O</div>
    <button class="ic" :class="{ on: onLibrary }" @click="openLibrary">
      <span class="tip">书库 Library</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
        <path d="M4 5.5A2.5 2.5 0 016.5 3H20v15H6.5A2.5 2.5 0 004 20.5zM4 5.5v15M9 3v15" />
      </svg>
    </button>
    <button
      class="ic"
      :class="{ on: !onLibrary, 'is-disabled': store.bookId === null }"
      :disabled="store.bookId === null"
      @click="openReader"
    >
      <span class="tip">章节 Chapters</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
        <path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" />
      </svg>
    </button>
    <div class="sp"></div>
    <button class="ic" :title="theme === 'light' ? '切换到深色' : '切换到浅色'" @click="toggleTheme">
      <span class="tip">切换深浅</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
        <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />
      </svg>
    </button>
  </nav>
</template>
