<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import type { ChapterSummary } from '../types/api'

const props = defineProps<{
  chapters: ChapterSummary[]
  currentIndex: number | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  select: [chapterIndex: number]
  retry: []
}>()

const listRef = ref<HTMLElement | null>(null)

function formatNo(index: number) {
  return String(index + 1).padStart(2, '0')
}

async function revealActive() {
  await nextTick()
  const el = listRef.value?.querySelector<HTMLElement>('.chapter-link.active')
  el?.scrollIntoView({ block: 'center' })
}

watch(
  () => props.currentIndex,
  () => {
    void revealActive()
  },
)

onMounted(() => {
  void revealActive()
})
</script>

<template>
  <nav class="chapter-nav" aria-label="章节目录">
    <header class="chapter-head">
      <h2>目录</h2>
      <span class="chapter-count">{{ chapters.length }} 章</span>
    </header>

    <div ref="listRef" class="chapter-scroll">
      <div v-if="loading" class="nav-state">
        <span class="spinner"></span>
        <span>正在加载目录…</span>
      </div>

      <div v-else-if="error" class="nav-state">
        <p class="error-text">{{ error }}</p>
        <button class="btn" type="button" @click="emit('retry')">重试</button>
      </div>

      <p v-else-if="chapters.length === 0" class="nav-state">暂无章节目录</p>

      <ul v-else class="chapter-list">
        <li v-for="chapter in chapters" :key="chapter.id">
          <button
            class="chapter-link"
            :class="{ active: chapter.chapterIndex === currentIndex }"
            type="button"
            :aria-current="chapter.chapterIndex === currentIndex ? 'page' : undefined"
            @click="emit('select', chapter.chapterIndex)"
          >
            <span class="chapter-no">{{ formatNo(chapter.chapterIndex) }}</span>
            <span class="chapter-title">{{ chapter.title }}</span>
          </button>
        </li>
      </ul>
    </div>
  </nav>
</template>

<style scoped>
.chapter-nav {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
}

.chapter-head {
  flex: none;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--border);
}

.chapter-head h2 {
  font-size: 15px;
  font-weight: 600;
}

.chapter-count {
  font-size: 11.5px;
  color: var(--text-muted);
}

.chapter-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  overscroll-behavior: contain;
}

.chapter-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.chapter-list li + li {
  margin-top: 2px;
}

.chapter-link {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-left: 2px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
  font-size: 13.5px;
  line-height: 1.55;
  transition: background-color 0.14s ease, color 0.14s ease, border-color 0.14s ease;
}

.chapter-link:hover {
  background: var(--surface-2);
  color: var(--text);
}

.chapter-link.active {
  border-left-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
  font-weight: 600;
}

.chapter-no {
  flex: none;
  width: 22px;
  padding-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.chapter-link.active .chapter-no {
  color: var(--accent);
}

.chapter-title {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.nav-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 40px 16px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
</style>