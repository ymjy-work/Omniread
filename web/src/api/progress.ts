import { http } from './request'
import type { ReadingProgress } from '../types/api'

export function getProgress(bookId: number) {
  return http.get<ReadingProgress>(`/books/${bookId}/progress`)
}

export function saveProgress(bookId: number, progress: ReadingProgress) {
  return http.put<void>(`/books/${bookId}/progress`, progress)
}
