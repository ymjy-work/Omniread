import { request } from './request'
import type { ReadingProgress } from '../types/api'

export type ProgressPayload = Pick<ReadingProgress, 'chapterIndex' | 'scrollRatio'>

export function getProgress(bookId: number) {
  return request<ReadingProgress>({ url: `/books/${bookId}/progress`, method: 'get' })
}

export function saveProgress(bookId: number, progress: ProgressPayload) {
  return request<void>({ url: `/books/${bookId}/progress`, method: 'put', data: progress })
}
