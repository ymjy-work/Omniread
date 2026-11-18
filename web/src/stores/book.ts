import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Book, ChapterSummary } from '../types/api'

export const useBookStore = defineStore('book', () => {
  const books = ref<Book[]>([])
  const currentBook = ref<Book | null>(null)
  const chapters = ref<ChapterSummary[]>([])

  return { books, currentBook, chapters }
})
