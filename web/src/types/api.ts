export interface ApiResult<T> {
  code: number
  message: string
  data: T
}

export interface User {
  id: number
  username: string
  displayName?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface AuthResponse {
  token: string
  user: User
}

export interface Book {
  id: number
  title: string
  author?: string
  coverUrl?: string
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
}
