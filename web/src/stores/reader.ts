import { ref } from 'vue'
import { defineStore } from 'pinia'
import { getChapter } from '../api/book'
import { ask as askApi, createSession, listMessages, listSessions } from '../api/chat'
import { saveProgress as saveProgressApi } from '../api/progress'
import { errorMessage } from '../api/request'
import type { Chapter } from '../types/api'
import type { ChatLevel, ChatMessage, ChatSession } from '../types/chat'

const LEVEL_KEY = 'omniread.chatLevel'

function readLevel(): ChatLevel {
  return localStorage.getItem(LEVEL_KEY) === 'full' ? 'full' : 'past'
}

function normalizeMessages(list: ChatMessage[]): ChatMessage[] {
  return list.map((message) => ({
    ...message,
    citations: Array.isArray(message.citations) ? message.citations : [],
  }))
}

export const useReaderStore = defineStore('reader', () => {
  const currentChapter = ref<Chapter | null>(null)
  const chapterLoading = ref(false)
  const chapterError = ref('')

  const level = ref<ChatLevel>(readLevel())
  const session = ref<ChatSession | null>(null)
  const sessionBookId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const messagesLoading = ref(false)
  const chatError = ref('')
  const asking = ref(false)

  let chapterRequestId = 0

  async function loadChapter(bookId: number, chapterIndex: number) {
    const requestId = ++chapterRequestId
    chapterLoading.value = true
    chapterError.value = ''
    try {
      const chapter = await getChapter(bookId, chapterIndex)
      if (requestId === chapterRequestId) currentChapter.value = chapter
      return chapter
    } catch (error) {
      if (requestId === chapterRequestId) {
        currentChapter.value = null
        chapterError.value = errorMessage(error, '章节加载失败')
      }
      throw error
    } finally {
      if (requestId === chapterRequestId) chapterLoading.value = false
    }
  }

  async function saveProgress(bookId: number, chapterIndex: number, scrollRatio: number) {
    await saveProgressApi(bookId, { chapterIndex, scrollRatio })
  }

  function setLevel(next: ChatLevel) {
    level.value = next
    localStorage.setItem(LEVEL_KEY, next)
  }

  async function loadMessages(sessionId: number, showLoading = true) {
    if (showLoading) messagesLoading.value = true
    chatError.value = ''
    try {
      const list = await listMessages(sessionId)
      messages.value = normalizeMessages(Array.isArray(list) ? list : [])
    } catch (error) {
      chatError.value = errorMessage(error, '聊天记录加载失败')
    } finally {
      if (showLoading) messagesLoading.value = false
    }
  }

  async function ensureSession(bookId: number) {
    if (session.value && sessionBookId.value === bookId) {
      if (!messages.value.length && !messagesLoading.value) await loadMessages(session.value.id)
      return session.value
    }
    session.value = null
    sessionBookId.value = null
    messages.value = []
    chatError.value = ''
    messagesLoading.value = true
    try {
      let next: ChatSession | undefined
      try {
        const sessions = await listSessions(bookId)
        next = [...sessions].sort((a, b) => b.id - a.id)[0]
      } catch {
        // 会话列表不可用时直接尝试新建会话
      }
      if (!next) next = await createSession(bookId)
      session.value = next
      sessionBookId.value = bookId
      await loadMessages(next.id, false)
      return next
    } catch (error) {
      chatError.value = errorMessage(error, '会话初始化失败')
      throw error
    } finally {
      messagesLoading.value = false
    }
  }

  async function ask(question: string) {
    const text = question.trim()
    if (!text || asking.value || !session.value) return
    const active = session.value
    chatError.value = ''
    asking.value = true
    messages.value.push({ role: 'user', content: text })
    try {
      const response = await askApi(active.id, { question: text, level: level.value })
      messages.value.push({
        role: 'assistant',
        content: response.answer,
        citations: Array.isArray(response.citations) ? response.citations : [],
      })
    } catch (error) {
      chatError.value = errorMessage(error, '回答失败，请稍后重试')
      throw error
    } finally {
      asking.value = false
    }
  }

  function resetChat() {
    session.value = null
    sessionBookId.value = null
    messages.value = []
    chatError.value = ''
    messagesLoading.value = false
    asking.value = false
  }

  return {
    currentChapter,
    chapterLoading,
    chapterError,
    level,
    session,
    sessionBookId,
    messages,
    messagesLoading,
    chatError,
    asking,
    loadChapter,
    saveProgress,
    setLevel,
    ensureSession,
    loadMessages,
    ask,
    resetChat,
  }
})
