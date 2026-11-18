export type ChatLevel = 'past' | 'full'

export interface Citation {
  chapterId: string
  chapterIndex: number
  title: string
  quote: string
}

export interface ChatMessage {
  id?: number
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  createdAt?: string
}

export interface ChatSession {
  id: number
  bookId: number
  title?: string
  createdAt?: string
  updatedAt?: string
}

export interface AskRequest {
  question: string
  level: ChatLevel
}

export interface AskResponse {
  answer: string
  citations: Citation[]
}
