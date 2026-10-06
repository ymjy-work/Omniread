/**
 * 全局阅读状态：当前书、章节列表、当前章、阅读进度、问答档位。
 *
 * 用 reactive 单例而不是 Pinia：M0 的状态只有这一份，装一个状态库
 * 换不来任何东西。store 只放状态，动作是同模块的具名导出函数。
 */
import { computed, reactive } from 'vue'
import * as api from './api'
import { ApiError } from './api'
import { describeErrorCode } from './errors'
import { readStored, writeStored } from './storage'
import type { Book, ChapterDetail, ChapterMeta, Progress, QueryLevel } from './types'

/** 问答档位的存储键；取值白名单与 `QueryLevel` 同源。 */
export const LEVEL_STORAGE_KEY = 'omniread.level'
const LEVELS: readonly QueryLevel[] = ['past', 'full']

export interface VolumeGroup {
  volume_index: number
  volume_title: string
  chapters: ChapterMeta[]
}

export const store = reactive({
  books: [] as Book[],
  bookId: null as number | null,
  chapters: [] as ChapterMeta[],
  chapter: null as ChapterDetail | null,
  progress: null as Progress | null,
  /**
   * 问答档位：回顾 / 剧透，状态栏与问答面板共用。
   *
   * 记住上次的选择——它和主题一样是偏好，刷新就忘等于每次都要重设。档位在界面上
   * 有四处在显示（问答面板的绿/黄点与分段控件、取证框的档位标签、状态栏的「档位：…」），
   * 所以「上次开过剧透、这次忘了」不至于悄无声息。
   */
  level: readStored(LEVEL_STORAGE_KEY, LEVELS, 'past'),
  loading: false,
  /** 最近一次失败的展示文案；null 表示无错误 */
  error: null as string | null
})

export const currentBook = computed<Book | null>(
  () => store.books.find((book) => book.book_id === store.bookId) ?? null
)

export const chapterCount = computed<number>(
  () => currentBook.value?.chapter_count ?? store.chapters.length
)

/** 章节列表按 volume_index 分组——接口给的是平铺数组，分组是前端的事 */
export const volumes = computed<VolumeGroup[]>(() => {
  const groups: VolumeGroup[] = []
  for (const chapter of store.chapters) {
    const last = groups[groups.length - 1]
    if (last && last.volume_index === chapter.volume_index) {
      last.chapters.push(chapter)
    } else {
      groups.push({
        volume_index: chapter.volume_index,
        volume_title: chapter.volume_title,
        chapters: [chapter]
      })
    }
  }
  return groups
})

export const readProgressRatio = computed<number>(() => {
  const total = chapterCount.value
  if (total <= 0 || store.progress === null) return 0
  return Math.min(1, Math.max(0, store.progress.max_seq / total))
})

function setError(cause: unknown): void {
  if (cause instanceof ApiError) {
    store.error = `${cause.code}（${describeErrorCode(cause.code)}）`
    return
  }
  store.error = cause instanceof Error ? cause.message : String(cause)
}

export async function loadBooks(): Promise<void> {
  store.loading = true
  try {
    const data = await api.listBooks()
    store.books = data.books
    store.error = null
  } catch (cause) {
    setError(cause)
  } finally {
    store.loading = false
  }
}

export async function selectBook(bookId: number): Promise<void> {
  if (store.bookId !== bookId) {
    store.bookId = bookId
    store.chapters = []
    store.chapter = null
    store.progress = null
  }
  await Promise.all([loadChapters(bookId), loadProgress(bookId)])
}

async function loadChapters(bookId: number): Promise<void> {
  try {
    const data = await api.listChapters(bookId)
    store.chapters = data.chapters
    store.error = null
  } catch (cause) {
    setError(cause)
  }
}

async function loadProgress(bookId: number): Promise<void> {
  try {
    store.progress = await api.getProgress(bookId)
  } catch (cause) {
    // 进度读不到不阻塞阅读，只在状态栏留一条错误
    setError(cause)
  }
}

export async function openChapter(chapterIndex: number): Promise<void> {
  const bookId = store.bookId
  if (bookId === null) return
  store.loading = true
  try {
    store.chapter = await api.getChapter(bookId, chapterIndex)
    store.error = null
  } catch (cause) {
    setError(cause)
  } finally {
    store.loading = false
  }
}

/** 把进度设为指定章；写成功后以服务端回值为准 */
export async function setProgress(maxSeq: number): Promise<boolean> {
  const bookId = store.bookId
  if (bookId === null) return false
  try {
    store.progress = await api.putProgress(bookId, maxSeq)
    store.error = null
    return true
  } catch (cause) {
    setError(cause)
    return false
  }
}

export function setLevel(level: QueryLevel): void {
  store.level = level
  writeStored(LEVEL_STORAGE_KEY, level)
}
