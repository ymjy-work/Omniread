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
}

export interface AskRequest {
  question: string
  level: ChatLevel
}

export interface AskResponse {
  answer: string
  citations: Citation[]
}
