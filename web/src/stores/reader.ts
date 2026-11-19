import { ref } from 'vue'
import { defineStore } from 'pinia'
import { getChapter } from '../api/book'
import { ask as askApi, createSession, listMessages, listSessions } from '../api/chat'
import { listPlatformModels } from '../api/models'
import { saveProgress as saveProgressApi } from '../api/progress'
import { ApiError, errorMessage } from '../api/request'
import { useAccountStore } from './account'
import { BYOK_PROVIDERS } from '../utils/billing'
import type { Chapter } from '../types/api'
import type { ApiProvider, ModelOption } from '../types/account'
import type {
  AskRequest,
  ChatLevel,
  ChatMessage,
  ChatMode,
  ChatSession,
} from '../types/chat'

const LEVEL_KEY = 'omniread.chatLevel'
const MODE_KEY = 'omniread.chatMode'
const PROVIDER_KEY = 'omniread.byokProvider'
const MODEL_KEY = 'omniread.chatModel'

function readLevel(): ChatLevel {
  return localStorage.getItem(LEVEL_KEY) === 'full' ? 'full' : 'past'
}

function readMode(): ChatMode {
  const saved = localStorage.getItem(MODE_KEY)
  return saved === 'platform' || saved === 'byok' ? saved : 'auto'
}

function readProvider(): ApiProvider {
  const saved = localStorage.getItem(PROVIDER_KEY)
  return BYOK_PROVIDERS.some((item) => item.value === saved)
    ? (saved as ApiProvider)
    : 'bailian'
}

function normalizeMessages(list: ChatMessage[]): ChatMessage[] {
  return list.map((message) => ({
    ...message,
    citations: Array.isArray(message.citations) ? message.citations : [],
  }))
}

export const useReaderStore = defineStore('reader', () => {
  const account = useAccountStore()

  const currentChapter = ref<Chapter | null>(null)
  const chapterLoading = ref(false)
  const chapterError = ref('')

  const level = ref<ChatLevel>(readLevel())
  const mode = ref<ChatMode>(readMode())
  const provider = ref<ApiProvider>(readProvider())
  const model = ref(localStorage.getItem(MODEL_KEY) ?? '')
  const platformModels = ref<ModelOption[]>([])
  const modelsLoading = ref(false)
  const modelsError = ref('')

  const session = ref<ChatSession | null>(null)
  const sessionBookId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const messagesLoading = ref(false)
  const chatError = ref('')
  const chatErrorCode = ref<number | null>(null)
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

  function setMode(next: ChatMode) {
    mode.value = next
    localStorage.setItem(MODE_KEY, next)
  }

  function setProvider(next: ApiProvider) {
    if (provider.value !== next) {
      provider.value = next
      setModel('')
    }
    localStorage.setItem(PROVIDER_KEY, next)
  }

  function setModel(next: string) {
    model.value = next
    if (next) localStorage.setItem(MODEL_KEY, next)
    else localStorage.removeItem(MODEL_KEY)
  }

  async function loadPlatformModels(force = false) {
    if (modelsLoading.value) return
    if (!force && platformModels.value.length > 0) return
    modelsLoading.value = true
    modelsError.value = ''
    try {
      const list = await listPlatformModels('bailian')
      platformModels.value = Array.isArray(list) ? list : []
      if (model.value && !platformModels.value.some((item) => item.model === model.value)) {
        setModel('')
      }
    } catch (error) {
      platformModels.value = []
      modelsError.value = errorMessage(error, '平台模型加载失败')
    } finally {
      modelsLoading.value = false
    }
  }

  function failChat(message: string, code: number | null = null) {
    chatError.value = message
    chatErrorCode.value = code
  }

  async function loadMessages(sessionId: number, showLoading = true) {
    if (showLoading) messagesLoading.value = true
    chatError.value = ''
    chatErrorCode.value = null
    try {
      const list = await listMessages(sessionId)
      messages.value = normalizeMessages(Array.isArray(list) ? list : [])
    } catch (error) {
      chatError.value = errorMessage(error, '聊天记录加载失败')
      chatErrorCode.value = error instanceof ApiError ? error.code : null
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
    chatErrorCode.value = null
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
      chatErrorCode.value = error instanceof ApiError ? error.code : null
      throw error
    } finally {
      messagesLoading.value = false
    }
  }

  function validateAsk() {
    if (mode.value === 'platform') {
      if (!account.account) return '账户信息尚未加载，请稍后重试。'
      if (account.plan === 'free') return 'free 档只能使用 auto 模式。'
      if (!model.value) return '请选择平台模型。'
    }
    if (mode.value === 'byok') {
      if (!model.value.trim()) return '请填写 BYOK 模型 ID。'
      if (!account.hasKey(provider.value)) return '请先保存该提供商的 API Key。'
    }
    if (mode.value !== 'byok' && account.account && account.credits < 1) {
      return '积分不足，无法使用平台回答。请购买套餐或改用 BYOK。'
    }
    return ''
  }

  async function ask(question: string) {
    const text = question.trim()
    if (!text || asking.value || !session.value) return

    chatError.value = ''
    chatErrorCode.value = null
    const problem = validateAsk()
    if (problem) {
      failChat(problem, problem.includes('积分不足') ? 40201 : 40000)
      return
    }

    const active = session.value
    const activeMode = mode.value
    const payload: AskRequest = { question: text, level: level.value, mode: activeMode }
    if (activeMode === 'platform') {
      payload.provider = 'bailian'
      payload.model = model.value
    } else if (activeMode === 'byok') {
      payload.provider = provider.value
      payload.model = model.value.trim()
    }

    asking.value = true
    messages.value.push({ role: 'user', content: text })
    try {
      const response = await askApi(active.id, payload)
      messages.value.push({
        role: 'assistant',
        content: response.answer,
        citations: Array.isArray(response.citations) ? response.citations : [],
        usage: response.usage,
      })
      void account.fetchAccount(true)
    } catch (error) {
      chatError.value = errorMessage(error, '回答失败，请稍后重试')
      chatErrorCode.value = error instanceof ApiError ? error.code : null
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
    chatErrorCode.value = null
    messagesLoading.value = false
    asking.value = false
  }

  return {
    currentChapter,
    chapterLoading,
    chapterError,
    level,
    mode,
    provider,
    model,
    platformModels,
    modelsLoading,
    modelsError,
    session,
    sessionBookId,
    messages,
    messagesLoading,
    chatError,
    chatErrorCode,
    asking,
    loadChapter,
    saveProgress,
    setLevel,
    setMode,
    setProvider,
    setModel,
    loadPlatformModels,
    ensureSession,
    loadMessages,
    ask,
    resetChat,
  }
})