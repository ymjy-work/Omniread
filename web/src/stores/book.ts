import { ref } from 'vue'
import { defineStore } from 'pinia'
import { getBook, listBooks, listChapters } from '../api/book'
import { errorMessage } from '../api/request'
import type { Book, ChapterSummary } from '../types/api'

export const useBookStore = defineStore('book', () => {
  const books = ref<Book[]>([])
  const booksLoading = ref(false)
  const booksError = ref('')

  const currentBook = ref<Book | null>(null)
  const bookLoading = ref(false)
  const bookError = ref('')

  const chapters = ref<ChapterSummary[]>([])
  const chaptersLoading = ref(false)
  const chaptersError = ref('')

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
      currentBook.value = await getBook(bookId)
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
    currentBook,
    bookLoading,
    bookError,
    chapters,
    chaptersLoading,
    chaptersError,
    fetchBooks,
    fetchBook,
    fetchChapters,
    resetCurrent,
  }
})
