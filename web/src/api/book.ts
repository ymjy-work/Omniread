import { request } from './request'
import type { Book, Chapter, ChapterSummary } from '../types/api'

export function listBooks() {
  return request<Book[]>({ url: '/books', method: 'get' })
}

export function getBook(bookId: number) {
  return request<Book>({ url: `/books/${bookId}`, method: 'get' })
}

export function listChapters(bookId: number) {
  return request<ChapterSummary[]>({ url: `/books/${bookId}/chapters`, method: 'get' })
}

export function getChapter(bookId: number, chapterIndex: number) {
  return request<Chapter>({ url: `/books/${bookId}/chapters/${chapterIndex}`, method: 'get' })
}
