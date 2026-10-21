<script setup lang="ts">
/**
 * 侧栏：书库板块列书，阅读板块列章节树（按卷分组）。
 * 底部的进度条与「调整进度」只在阅读板块出现——书库页没有可调整的进度。
 */
import { computed, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { chapterCount, currentBook, readProgressRatio, selectBook, setProgress, store, volumes } from '../store'

const route = useRoute()
const router = useRouter()

const inReader = computed(() => route.name === 'reader')
const currentIndex = computed(() => store.chapter?.chapter_index ?? null)

/**
 * 展开着的卷。**默认只开当前章节所在的那一卷**：全书 15 卷 193 章全平铺是一整片，
 * 找一章要滚很久。
 *
 * 手动收起当前卷也允许，所以不强制它一直开着——只在**换章**时把它所在的卷补进来。
 * 一次都没开过时给个落脚点（第一卷），否则初次进阅读页会是一片全是收起的标题。
 */
const expanded = reactive(new Set<number>())

function volumeOf(chapterIndex: number | null): number | null {
  if (chapterIndex === null) return null
  return store.chapters.find((c) => c.chapter_index === chapterIndex)?.volume_index ?? null
}

const currentVolume = computed(() => volumeOf(currentIndex.value))

function toggleVolume(volumeIndex: number): void {
  if (expanded.has(volumeIndex)) expanded.delete(volumeIndex)
  else expanded.add(volumeIndex)
}

watch(
  [currentVolume, () => volumes.value.length],
  () => {
    const target = currentVolume.value ?? (expanded.size === 0 ? (volumes.value[0]?.volume_index ?? null) : null)
    if (target !== null) expanded.add(target)
  },
  { immediate: true }
)

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
  const readUpTo = store.reading?.progress ?? null
  return {
    active: chapterIndex === currentIndex.value,
    cur: readUpTo !== null && chapterIndex === readUpTo,
    done: readUpTo !== null && chapterIndex < readUpTo
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
          class="vol"
          :class="{
            open: expanded.has(volume.volume_index),
            active: volume.chapters.some((c) => c.chapter_index === currentIndex)
          }"
        >
          <button
            class="vol-head"
            :aria-expanded="expanded.has(volume.volume_index)"
            @click="toggleVolume(volume.volume_index)"
          >
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
                v-else-if="store.reading && chapter.chapter_index === store.reading.progress"
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
          <div class="cov"><span>{{ book.title }}</span></div>
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
        阅读进度 <b style="font-family: var(--mono)">{{ store.reading?.progress ?? 0 }}/{{ chapterCount }}</b>
      </div>
      <label class="pg-pick">
        调整进度
        <select class="gobtn" :value="store.reading?.progress ?? 1" @change="pickProgress">
          <option v-for="chapter in store.chapters" :key="chapter.chapter_index" :value="chapter.chapter_index">
            <!--
              这个数字是 `chapter_index`（全书连续序号），**不是话数**——两者不同源，
              写成「第 N 话」会渲染出「第 7 话 · 第6话」这种同一行两个打架的号码。
            -->
            全书第 {{ chapter.chapter_index }} 章 · {{ chapter.chapter_title }}
          </option>
        </select>
      </label>
    </div>

    <div v-else-if="currentBook" class="foot">
      <div class="pg-line">当前选中 <b style="font-family: var(--mono)">{{ currentBook.title }}</b></div>
    </div>
  </aside>
</template>
