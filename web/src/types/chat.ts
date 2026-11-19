export type ChatSurface = 'official' | 'self'

export type ChatLevel = 'past' | 'full'
export type ChatMode = 'auto' | 'platform' | 'byok'

export interface Citation {
  chapterId: string
  chapterIndex: number
  title: string
  quote: string
}

export interface AskUsage {
  mode: string
  provider: string
  model: string
  promptTokens: number
  completionTokens: number
}

export interface ChatMessage {
  id?: number
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  usage?: AskUsage
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
  mode: ChatMode
  provider?: string
  model?: string
}

export interface AskResponse {
  answer: string
  citations: Citation[]
  usage?: AskUsage
}