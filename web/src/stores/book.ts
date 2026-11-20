import { ref } from 'vue'
import { defineStore } from 'pinia'
import { getBook, listBooks, listChapters } from '../api/book'
import { errorMessage } from '../api/errors'
import type { Book, ChapterSummary } from '../types/api'

const RECENT_BOOK_KEY = 'omniread.recentBook'

interface RecentBook {
  id: number
  title: string
}

function readRecentBook(): RecentBook | null {
  try {
    const raw = localStorage.getItem(RECENT_BOOK_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<RecentBook>
    if (typeof parsed.id !== 'number' || typeof parsed.title !== 'string') return null
    return { id: parsed.id, title: parsed.title }
  } catch {
    return null
  }
}

export const useBookStore = defineStore('book', () => {
  const books = ref<Book[]>([])
  const booksLoading = ref(false)
  const booksError = ref('')

  const recentBook = ref<RecentBook | null>(readRecentBook())
  const currentBook = ref<Book | null>(null)
  const bookLoading = ref(false)
  const bookError = ref('')

  const chapters = ref<ChapterSummary[]>([])
  const chaptersLoading = ref(false)
  const chaptersError = ref('')

  function rememberRecent(book: Book) {
    recentBook.value = { id: book.id, title: book.title }
    localStorage.setItem(RECENT_BOOK_KEY, JSON.stringify(recentBook.value))
  }

  async function fetchBooks() {
    booksLoading.value = true
    booksError.value = ''
    try {
      const list = await listBooks()
      books.value = Array.isArray(list) ? list : []
    } catch (error) {
      booksError.value = errorMessage(error, '书库加载失败')
    } finally {
      booksLoading.value = false
    }
  }

  async function fetchBook(bookId: number) {
    bookLoading.value = true
    bookError.value = ''
    currentBook.value = null
    try {
      const book = await getBook(bookId)
      currentBook.value = book
      rememberRecent(book)
    } catch (error) {
      bookError.value = errorMessage(error, '书籍信息加载失败')
    } finally {
      bookLoading.value = false
    }
  }

  async function fetchChapters(bookId: number) {
    chaptersLoading.value = true
    chaptersError.value = ''
    try {
      const list = await listChapters(bookId)
      chapters.value = (Array.isArray(list) ? list : []).sort((a, b) => a.chapterIndex - b.chapterIndex)
    } catch (error) {
      chapters.value = []
      chaptersError.value = errorMessage(error, '目录加载失败')
    } finally {
      chaptersLoading.value = false
    }
  }

  function resetCurrent() {
    currentBook.value = null
    bookError.value = ''
    chapters.value = []
    chaptersError.value = ''
  }

  return {
    books,
    booksLoading,
    booksError,
    recentBook,
    currentBook,
    bookLoading,
    bookError,
    chapters,
    chaptersLoading,
    chaptersError,
    rememberRecent,
    fetchBooks,
    fetchBook,
    fetchChapters,
    resetCurrent,
  }
})
