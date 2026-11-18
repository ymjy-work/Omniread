import { http } from './request'
import type { Book, Chapter, ChapterSummary } from '../types/api'

export function listBooks() {
  return http.get<Book[]>('/books')
}

export function getBook(bookId: number) {
  return http.get<Book>(`/books/${bookId}`)
}

export function listChapters(bookId: number) {
  return http.get<ChapterSummary[]>(`/books/${bookId}/chapters`)
}

export function getChapter(bookId: number, chapterIndex: number) {
  return http.get<Chapter>(`/books/${bookId}/chapters/${chapterIndex}`)
}
