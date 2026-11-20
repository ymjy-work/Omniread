export interface ApiResult<T> {
  code: number
  message: string
  data: T
}

export interface User {
  id: number
  username: string
  displayName?: string
  role?: UserRole
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest extends LoginRequest {
  displayName?: string
}

export interface AuthResponse {
  token: string
  user: User
}

export interface Book {
  id: number
  title: string
  author?: string
  coverUrl?: string | null
  description?: string
  chapterCount?: number
}

export interface ChapterSummary {
  id: number
  chapterIndex: number
  title: string
}

export interface Chapter extends ChapterSummary {
  bookId: number
  text: string
}

export interface ReadingProgress {
  bookId: number
  chapterIndex: number
  scrollRatio: number
  updatedAt?: string
}
import type { UserRole } from './account'
