<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChapterNav from '../components/ChapterNav.vue'
import ChatPanel from '../components/ChatPanel.vue'
import { getProgress } from '../api/progress'
import { useReadingProgress } from '../composables/useReadingProgress'
import { useAccountStore } from '../stores/account'
import { useBookStore } from '../stores/book'
import { useReaderStore } from '../stores/reader'
import { useSettingsStore } from '../stores/settings'
import type { ThemeName } from '../stores/settings'
import { formatCredits } from '../utils/billing'
import type { ChapterSummary, ReadingProgress } from '../types/api'
import type { Citation } from '../types/chat'

interface Segment {
  text: string
  mark: boolean
}

interface Paragraph {
  segments: Segment[]
}

interface ShowChapterOptions {
  restore?: boolean
  replace?: boolean
  quote?: string
  updateUrl?: boolean
}

const route = useRoute()
const router = useRouter()
const account = useAccountStore()
const bookStore = useBookStore()
const reader = useReaderStore()
const settings = useSettingsStore()

const bookId = computed(() => Number(route.params.bookId))
const scrollEl = ref<HTMLElement | null>(null)
const articleEl = ref<HTMLElement | null>(null)
const loadedIndex = ref<number | null>(null)
const requestedIndex = ref<number | null>(null)
const progress = ref<ReadingProgress | null>(null)
const initializing = ref(true)
const tocOpen = ref(false)
const chatOpen = ref(false)
const highlight = ref<{ start: number; end: number } | null>(null)

const { saving, ratio, saveError, schedule, flush, sync } = useReadingProgress({
  getScrollEl: () => scrollEl.value,
  getBookId: () => bookId.value,
  getChapterIndex: () => (reader.chapterLoading || reader.chapterError ? null : loadedIndex.value),
  delay: 1000,
})

const themeOrder: ThemeName[] = ['light', 'sepia', 'dark']
const themeLabels: Record<ThemeName, string> = { light: '明亮', sepia: '护眼', dark: '夜间' }
const themeLabel = computed(() => themeLabels[settings.theme])

const bookTitle = computed(
  () => bookStore.currentBook?.title || (bookStore.bookLoading ? '加载中…' : '阅读'),
)

const tocPosition = computed(() => {
  if (loadedIndex.value === null) return -1
  return bookStore.chapters.findIndex((item) => item.chapterIndex === loadedIndex.value)
})

const prevChapter = computed<ChapterSummary | null>(() => neighbor(-1))
const nextChapter = computed<ChapterSummary | null>(() => neighbor(1))

const footPosition = computed(() => {
  if (tocPosition.value >= 0) return `${tocPosition.value + 1} / ${bookStore.chapters.length}`
  if (loadedIndex.value === null) return ''
  return `第 ${loadedIndex.value + 1} 章`
})

const paragraphs = computed<Paragraph[]>(() => {
  const chapter = reader.currentChapter
  if (!chapter) return []
  const text = normalizeText(chapter.text)
  const range = highlight.value
  const lines = text.split('\n')
  const result: Paragraph[] = []
  let offset = 0

  for (const line of lines) {
    const lineStart = offset
    const lineEnd = offset + line.length
    offset = lineEnd + 1
    if (!line.trim()) continue

    if (!range || range.end <= lineStart || range.start >= lineEnd) {
      result.push({ segments: [{ text: line, mark: false }] })
      continue
    }

    const localStart = Math.max(range.start - lineStart, 0)
    const localEnd = Math.min(range.end - lineStart, line.length)
    const segments: Segment[] = []
    if (localStart > 0) segments.push({ text: line.slice(0, localStart), mark: false })
    segments.push({ text: line.slice(localStart, localEnd), mark: true })
    if (localEnd < line.length) segments.push({ text: line.slice(localEnd), mark: false })
    result.push({ segments })
  }

  return result
})

function normalizeText(text: string) {
  return text.replace(/\r\n?/g, '\n')
}

function findQuote(text: string, quote: string) {
  const needle = quote.replace(/\s+/g, '')
  if (!needle) return null

  let normalized = ''
  const map: number[] = []
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (/\s/.test(char)) continue
    normalized += char
    map.push(index)
  }

  const position = normalized.indexOf(needle)
  if (position < 0) return null
  return {
    start: map[position],
    end: map[position + needle.length - 1] + 1,
  }
}

function neighbor(offset: number): ChapterSummary | null {
  const current = loadedIndex.value
  if (current === null) return null
  const list = bookStore.chapters
  const position = list.findIndex((item) => item.chapterIndex === current)
  if (position >= 0) return list[position + offset] ?? null

  const target = current + offset
  if (target < 0) return null
  const count = bookStore.currentBook?.chapterCount
  if (count && target >= count) return null
  return { id: -1, chapterIndex: target, title: offset < 0 ? '上一章' : '下一章' }
}

function applyRatio(value: number) {
  const el = scrollEl.value
  if (!el) return
  const max = el.scrollHeight - el.clientHeight
  el.scrollTop = max > 0 ? max * Math.min(Math.max(value, 0), 1) : 0
}

async function revealHighlight() {
  await nextTick()
  const mark = articleEl.value?.querySelector<HTMLElement>('mark.quote-mark')
  mark?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

async function showChapter(index: number, options: ShowChapterOptions = {}) {
  if (!Number.isFinite(index) || index < 0) return
  requestedIndex.value = index

  if (loadedIndex.value !== null && loadedIndex.value !== index) {
    await flush()
  }
  highlight.value = null

  const restoreRatio =
    options.restore && progress.value?.chapterIndex === index ? progress.value.scrollRatio : 0

  try {
    const chapter = await reader.loadChapter(bookId.value, index)
    loadedIndex.value = index

    const routeIndex =
      typeof route.params.chapterIndex === 'string' ? Number(route.params.chapterIndex) : null
    if (options.updateUrl !== false && routeIndex !== index) {
      const location = `/books/${bookId.value}/chapters/${index}`
      const navigation = options.replace ? router.replace(location) : router.push(location)
      await navigation.catch(() => undefined)
    }

    const range = options.quote ? findQuote(normalizeText(chapter.text), options.quote) : null
    highlight.value = range
    await nextTick()
    if (range) {
      await revealHighlight()
    } else {
      applyRatio(restoreRatio)
    }
    sync(range ? 0 : restoreRatio)
  } catch {
    // reader store 已保存章节错误信息
  } finally {
    tocOpen.value = false
  }
}

function selectChapter(index: number) {
  if (index === loadedIndex.value) {
    tocOpen.value = false
    return
  }
  void showChapter(index)
}

async function handleCitation(citation: Citation) {
  chatOpen.value = false
  const targetIndex = Number(citation.chapterIndex)
  if (!Number.isFinite(targetIndex)) return
  if (loadedIndex.value === targetIndex && reader.currentChapter) {
    const range = findQuote(normalizeText(reader.currentChapter.text), citation.quote)
    if (range) {
      highlight.value = range
      await revealHighlight()
    }
    return
  }
  await showChapter(targetIndex, { quote: citation.quote })
}

function goPrev() {
  const target = prevChapter.value
  if (target) void showChapter(target.chapterIndex)
}

function goNext() {
  const target = nextChapter.value
  if (target) void showChapter(target.chapterIndex)
}

function retryChapter() {
  void showChapter(requestedIndex.value ?? progress.value?.chapterIndex ?? 0)
}

function retryChapters() {
  void bookStore.fetchChapters(bookId.value)
}

function cycleTheme() {
  const index = themeOrder.indexOf(settings.theme)
  settings.setTheme(themeOrder[(index + 1) % themeOrder.length] ?? 'light')
}

function closeDrawers() {
  tocOpen.value = false
  chatOpen.value = false
}

async function loadProgress() {
  try {
    progress.value = await getProgress(bookId.value)
  } catch {
    progress.value = null
  }
}

function onScroll() {
  if (!reader.chapterLoading && !reader.chapterError) schedule()
}

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') void flush()
}

onMounted(async () => {
  if (!Number.isFinite(bookId.value)) {
    await router.replace('/')
    return
  }

  document.addEventListener('visibilitychange', onVisibilityChange)
  void account.fetchAccount()
  await Promise.all([
    bookStore.fetchBook(bookId.value),
    bookStore.fetchChapters(bookId.value),
    loadProgress(),
  ])

  const raw = route.params.chapterIndex
  const initial = typeof raw === 'string' ? Number(raw) : null
  if (initial !== null && Number.isFinite(initial)) {
    await showChapter(initial, { restore: route.query.restore === '1' })
  } else {
    await showChapter(progress.value?.chapterIndex ?? 0, { restore: true, replace: true })
  }
  initializing.value = false
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  void flush()
})

watch(
  () => route.params.chapterIndex,
  (value) => {
    if (!initializing.value) {
      const index = typeof value === 'string' ? Number(value) : null
      if (index === null || !Number.isFinite(index) || index === loadedIndex.value) return
      void showChapter(index, { updateUrl: false })
    }
  },
)
</script>

<template>
  <div class="reader-shell">
    <header class="reader-header">
      <div class="header-left">
        <RouterLink class="btn btn-ghost btn-icon" to="/" aria-label="返回书库">←</RouterLink>
        <button
          class="btn btn-ghost btn-icon mobile-only"
          type="button"
          :aria-expanded="tocOpen"
          aria-label="打开章节目录"
          @click="tocOpen = !tocOpen"
        >
          ☰
        </button>
        <div class="header-titles">
          <span class="book-title">{{ bookTitle }}</span>
          <span class="chapter-title">{{ reader.currentChapter?.title || ' ' }}</span>
        </div>
      </div>

      <div class="header-right">
        <RouterLink
          v-if="account.account"
          class="credit-chip"
          to="/settings"
          :title="`剩余积分 ${account.credits}`"
        >
          {{ formatCredits(account.credits) }} 积分
        </RouterLink>
        <span class="save-state" :title="saveError || '阅读进度自动保存'">
          <template v-if="saving">保存中…</template>
          <template v-else-if="saveError">未保存</template>
          <template v-else>{{ Math.round(ratio * 100) }}%</template>
        </span>
        <button class="btn btn-ghost theme-btn" type="button" @click="cycleTheme">
          主题 · {{ themeLabel }}
        </button>
        <RouterLink class="btn btn-ghost optional" to="/settings">设置</RouterLink>
        <button
          class="btn btn-ghost mobile-only"
          type="button"
          :aria-expanded="chatOpen"
          @click="chatOpen = !chatOpen"
        >
          对话
        </button>
      </div>
    </header>

    <div class="progress-rail" aria-hidden="true">
      <span :style="{ width: `${ratio * 100}%` }"></span>
    </div>

    <div v-if="bookStore.bookError && !bookStore.bookLoading" class="reader-alert" role="status">
      {{ bookStore.bookError }}，章节内容仍可阅读。
    </div>

    <div class="reader-body">
      <aside class="reader-sidebar" :class="{ open: tocOpen }">
        <ChapterNav
          :chapters="bookStore.chapters"
          :current-index="loadedIndex"
          :loading="bookStore.chaptersLoading"
          :error="bookStore.chaptersError"
          @select="selectChapter"
          @retry="retryChapters"
        />
      </aside>

      <main class="reader-main">
        <div ref="scrollEl" class="reader-scroll" @scroll.passive="onScroll">
          <div v-if="initializing || reader.chapterLoading" class="reader-loading">
            <span class="spinner"></span>
            <span>正在加载章节…</span>
          </div>

          <section v-else-if="reader.chapterError" class="state-box reader-error">
            <p class="state-title">章节加载失败</p>
            <p class="state-desc">{{ reader.chapterError }}</p>
            <div class="error-actions">
              <button class="btn btn-primary" type="button" @click="retryChapter">重新加载</button>
              <RouterLink class="btn" to="/">返回书库</RouterLink>
            </div>
          </section>

          <template v-else-if="reader.currentChapter">
            <article ref="articleEl" class="article-wrap">
              <header class="article-head">
                <p class="article-kicker">第 {{ loadedIndex !== null ? loadedIndex + 1 : 1 }} 章</p>
                <h1>{{ reader.currentChapter.title }}</h1>
              </header>
              <p v-if="paragraphs.length === 0" class="article-empty">本章暂无正文。</p>
              <div v-else class="article-body">
                <p v-for="(paragraph, index) in paragraphs" :key="index">
                  <template v-for="(segment, segmentIndex) in paragraph.segments" :key="segmentIndex">
                    <mark v-if="segment.mark" class="quote-mark">{{ segment.text }}</mark>
                    <template v-else>{{ segment.text }}</template>
                  </template>
                </p>
              </div>
            </article>

            <footer class="chapter-foot">
              <button class="btn" type="button" :disabled="!prevChapter" @click="goPrev">
                ← 上一章
              </button>
              <span class="foot-position">{{ footPosition }}</span>
              <button class="btn" type="button" :disabled="!nextChapter" @click="goNext">
                下一章 →
              </button>
            </footer>
          </template>

          <section v-else class="state-box">
            <p class="state-title">这一章还没有内容</p>
            <p class="state-desc">可以从目录选择其他章节。</p>
          </section>
        </div>
      </main>

      <aside class="reader-chat" :class="{ open: chatOpen }">
        <ChatPanel :book-id="bookId" @cite="handleCitation" />
      </aside>
    </div>

    <div v-if="tocOpen || chatOpen" class="scrim" @click="closeDrawers"></div>
  </div>
</template>

<style scoped>
.reader-shell {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
}

.reader-header {
  position: relative;
  z-index: 50;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 56px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 92%, transparent);
  backdrop-filter: blur(10px);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.header-titles {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding-left: 4px;
  line-height: 1.3;
}

.book-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
  font-size: 13.5px;
  font-weight: 600;
}

.chapter-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
  font-size: 11.5px;
  color: var(--text-muted);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 2px;
}

.credit-chip {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}

.save-state {
  padding: 0 8px;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
  white-space: nowrap;
}

.theme-btn {
  font-size: 12.5px;
}

.progress-rail {
  flex: none;
  height: 2px;
  background: var(--border);
}

.progress-rail span {
  display: block;
  height: 100%;
  max-width: 100%;
  background: var(--accent);
  transition: width 0.12s linear;
}

.reader-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 272px minmax(0, 1fr) 372px;
}

.reader-sidebar,
.reader-chat {
  min-height: 0;
  overflow: hidden;
}

.reader-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--reader-bg);
}

.reader-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.reader-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 58vh;
  font-size: 13px;
  color: var(--text-secondary);
}

.article-wrap {
  width: min(100%, 760px);
  margin: 0 auto;
  padding: 44px clamp(20px, 5vw, 64px) 28px;
}

.article-head {
  margin-bottom: 30px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}

.article-kicker {
  margin-bottom: 8px;
  font-size: 11px;
  letter-spacing: 0.2em;
  color: var(--text-muted);
}

.article-head h1 {
  font-family: var(--font-serif);
  font-size: clamp(23px, 3vw, 31px);
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0.02em;
  color: var(--reader-text);
}

.article-body {
  font-family: var(--font-serif);
  font-size: var(--reader-font-size);
  line-height: 1.95;
  color: var(--reader-text);
  text-align: justify;
  overflow-wrap: break-word;
}

.article-body p {
  margin: 0 0 0.9em;
  text-indent: 2em;
}

.quote-mark {
  padding: 0 2px;
  border-radius: 2px;
  background: var(--quote-bg);
  color: inherit;
  scroll-margin: 40vh 0;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}

.chapter-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  width: min(100%, 760px);
  margin: 0 auto;
  padding: 8px clamp(20px, 5vw, 64px) 72px;
}

.chapter-foot .btn {
  flex: 1;
  max-width: 200px;
}

.foot-position {
  min-width: 74px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.reader-error {
  min-height: 58vh;
}

.error-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.reader-alert {
  flex: none;
  padding: 7px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 12px;
  text-align: center;
}

.article-empty {
  padding: 36px 0;
  text-align: center;
  font-size: 14px;
  color: var(--text-secondary);
}

.scrim {
  position: fixed;
  inset: 0;
  z-index: 45;
  background: var(--scrim);
}

.mobile-only {
  display: none;
}

@media (max-width: 1180px) {
  .reader-body {
    grid-template-columns: 240px minmax(0, 1fr) 336px;
  }
}

@media (max-width: 1000px) {
  .reader-body {
    display: block;
    position: relative;
  }

  .reader-main {
    height: 100%;
  }

  .reader-sidebar,
  .reader-chat {
    position: fixed;
    top: 0;
    bottom: 0;
    z-index: 60;
    display: flex;
    flex-direction: column;
    width: min(86vw, 340px);
    box-shadow: var(--shadow-md);
    transition: transform 0.24s ease;
  }

  .reader-sidebar {
    left: 0;
    transform: translateX(-102%);
  }

  .reader-chat {
    right: 0;
    width: min(94vw, 400px);
    transform: translateX(102%);
  }

  .reader-sidebar.open,
  .reader-chat.open {
    transform: none;
  }

  .mobile-only {
    display: inline-flex;
  }
}

@media (min-width: 1001px) {
  .scrim {
    display: none;
  }

  .reader-sidebar,
  .reader-chat {
    display: flex;
    flex-direction: column;
  }
}

@media (max-width: 640px) {
  .optional,
  .save-state {
    display: none;
  }

  .book-title {
    max-width: 130px;
  }

  .chapter-title {
    max-width: 130px;
  }

  .article-wrap {
    padding-top: 34px;
  }

  .chapter-foot .btn {
    max-width: none;
  }
}

@media (max-width: 420px) {
  .theme-btn {
    display: none;
  }

  .book-title,
  .chapter-title {
    max-width: 96px;
  }
}
</style>