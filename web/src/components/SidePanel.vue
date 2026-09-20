<script setup lang="ts">
/**
 * 侧栏：书库板块列书，阅读板块列章节树（按卷分组）。
 * 底部的进度条与「调整进度」只在阅读板块出现——书库页没有可调整的进度。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { chapterCount, currentBook, readProgressRatio, selectBook, setProgress, store, volumes } from '../store'

const route = useRoute()
const router = useRouter()

const inReader = computed(() => route.name === 'reader')
const currentIndex = computed(() => store.chapter?.chapter_index ?? null)

/** 在书库板块点书 = 选中它（拉章节与进度），不跳转 */
function openBook(bookId: number): void {
  void selectBook(bookId)
}

function openChapter(chapterIndex: number): void {
  const bookId = store.bookId
  if (bookId === null) return
  void router.push({ name: 'reader', params: { bookId, chapterIndex } })
}

function chapterClass(chapterIndex: number): Record<string, boolean> {
  const maxSeq = store.progress?.max_seq ?? null
  return {
    active: chapterIndex === currentIndex.value,
    cur: maxSeq !== null && chapterIndex === maxSeq,
    done: maxSeq !== null && chapterIndex < maxSeq
  }
}

async function pickProgress(event: Event): Promise<void> {
  const value = Number((event.target as HTMLSelectElement).value)
  if (!Number.isFinite(value)) return
  await setProgress(value)
}
</script>

<template>
  <aside class="side glass">
    <div class="head">
      <b>{{ inReader ? '章节' : '书库' }}</b>
      <span class="k">{{ inReader ? `${chapterCount} 话 · 全局 seq` : 'TXT / EPUB / linovelib' }}</span>
    </div>

    <div class="tree">
      <!-- 阅读板块：章节树 -->
      <template v-if="inReader">
        <div
          v-for="volume in volumes"
          :key="volume.volume_index"
          class="vol open"
          :class="{ active: volume.chapters.some((c) => c.chapter_index === currentIndex) }"
        >
          <button class="vol-head">
            <span class="caret">▶</span>
            <span class="vol-badge">卷 {{ volume.volume_index }}</span>
            <span class="vol-count">
              {{ volume.chapters.length }} 话 · seq
              {{ volume.chapters[0]?.chapter_index }}–{{ volume.chapters[volume.chapters.length - 1]?.chapter_index }}
            </span>
          </button>
          <div
            v-for="chapter in volume.chapters"
            :key="chapter.chapter_index"
            class="chap"
            :class="chapterClass(chapter.chapter_index)"
          >
            <button @click="openChapter(chapter.chapter_index)">
              <span class="cno">{{ String(chapter.chapter_index).padStart(2, '0') }}</span>
              <span class="ct">{{ chapter.chapter_title }}</span>
              <span v-if="chapter.chapter_index === currentIndex" class="tag-cur">◉ 当前</span>
              <span
                v-else-if="store.progress && chapter.chapter_index === store.progress.max_seq"
                class="tag-cur cur"
                >读到</span
              >
            </button>
          </div>
        </div>
        <div v-if="volumes.length === 0" class="blank">
          {{ store.loading ? '加载中…' : '没有章节' }}
        </div>
      </template>

      <!-- 书库板块：书卡片 -->
      <template v-else>
        <div
          v-for="book in store.books"
          :key="book.book_id"
          class="bookcard"
          :class="{ active: book.book_id === store.bookId }"
          @click="openBook(book.book_id)"
        >
          <div class="cov">{{ book.title }}</div>
          <div>
            <h2>{{ book.title }}</h2>
            <p>{{ book.author }} · {{ book.volume_count }} 卷 · {{ book.chapter_count }} 话</p>
          </div>
          <span class="tag">{{ book.chapter_count }} 话</span>
        </div>
        <div v-if="store.books.length === 0" class="blank">
          {{ store.loading ? '加载中…' : '书库为空' }}
        </div>
      </template>
    </div>

    <div v-if="inReader" class="foot">
      <div class="progress-bar"><i :style="{ width: `${Math.round(readProgressRatio * 100)}%` }"></i></div>
      <div class="pg-line">
        阅读进度 <b style="font-family: var(--mono)">{{ store.progress?.max_seq ?? 0 }}/{{ chapterCount }}</b>
      </div>
      <label class="pg-pick">
        调整进度
        <select class="gobtn" :value="store.progress?.max_seq ?? 1" @change="pickProgress">
          <option v-for="chapter in store.chapters" :key="chapter.chapter_index" :value="chapter.chapter_index">
            第 {{ chapter.chapter_index }} 话 · {{ chapter.chapter_title }}
          </option>
        </select>
      </label>
    </div>

    <div v-else-if="currentBook" class="foot">
      <div class="pg-line">当前选中 <b style="font-family: var(--mono)">{{ currentBook.title }}</b></div>
    </div>
  </aside>
</template>
