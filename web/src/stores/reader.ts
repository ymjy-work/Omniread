import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { fetchProviderModels as fetchProviderModelsApi } from '../api/account'
import { getChapter } from '../api/book'
import { ask as askApi, createSession, listMessages, listSessions } from '../api/chat'
import { listPlatformModels } from '../api/models'
import { saveProgress as saveProgressApi } from '../api/progress'
import { ApiError, errorMessage } from '../api/errors'
import { useAccountStore } from './account'
import { BYOK_PROVIDERS } from '../utils/billing'
import { SUGGESTED_MODELS } from '../utils/models'
import type { Chapter } from '../types/api'
import type { ApiProvider, ModelOption } from '../types/account'
import type {
  AskRequest,
  ChatLevel,
  ChatMessage,
  ChatMode,
  ChatSession,
  ChatSurface,
} from '../types/chat'

const LEVEL_KEY = 'omniread.chatLevel'
const MODE_KEY = 'omniread.chatMode'
const PROVIDER_KEY = 'omniread.byokProvider'
const PLATFORM_MODEL_KEY = 'omniread.platformModel'
const BYOK_MODEL_KEY = 'omniread.byokModel'
const LEGACY_MODEL_KEY = 'omniread.chatModel'

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

function readPlatformModel() {
  return localStorage.getItem(PLATFORM_MODEL_KEY) ?? localStorage.getItem(LEGACY_MODEL_KEY) ?? ''
}

function readByokModel() {
  return localStorage.getItem(BYOK_MODEL_KEY) ?? ''
}

function normalizeProviderModels(raw: unknown): string[] {
  const list = Array.isArray(raw)
    ? raw
    : raw && typeof raw === 'object' && Array.isArray((raw as { models?: unknown }).models)
      ? (raw as { models: unknown[] }).models
      : []
  return list
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    .sort((a, b) => a.localeCompare(b))
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
  const platformModel = ref(readPlatformModel())
  const byokModel = ref(readByokModel())

  const platformModels = ref<ModelOption[]>([])
  const modelsLoading = ref(false)
  const modelsError = ref('')

  const pulledModels = ref<Partial<Record<ApiProvider, string[]>>>({})
  const providerModelsLoading = ref(false)
  const providerModelsError = ref('')
  let providerModelsRequest = 0

  const session = ref<ChatSession | null>(null)
  const sessionBookId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const messagesLoading = ref(false)
  const chatError = ref('')
  const chatErrorCode = ref<number | null>(null)
  const asking = ref(false)

  const surface = computed<ChatSurface>(() => (mode.value === 'byok' ? 'self' : 'official'))
  const suggestedModels = computed(() => SUGGESTED_MODELS[provider.value] ?? [])
  const availableModels = computed(() => {
    const pulled = account.hasKey(provider.value) ? pulledModels.value[provider.value] : undefined
    return pulled && pulled.length > 0 ? pulled : suggestedModels.value
  })
  const model = computed(() => (mode.value === 'byok' ? byokModel.value : platformModel.value))

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
    if (next === 'byok') ensureByokModel()
  }

  function setSurface(next: ChatSurface) {
    if (next === 'self') {
      setMode('byok')
      return
    }
    setMode(account.account && account.plan === 'free' ? 'auto' : 'platform')
  }

  function setPlatformModel(next: string) {
    platformModel.value = next
    if (next) localStorage.setItem(PLATFORM_MODEL_KEY, next)
    else localStorage.removeItem(PLATFORM_MODEL_KEY)
  }

  function setByokModel(next: string) {
    byokModel.value = next
    if (next) localStorage.setItem(BYOK_MODEL_KEY, next)
    else localStorage.removeItem(BYOK_MODEL_KEY)
  }

  function ensureByokModel() {
    const models = availableModels.value
    if (!models.includes(byokModel.value)) setByokModel(models[0] ?? '')
  }

  function setModel(next: string) {
    if (mode.value === 'byok') setByokModel(next)
    else setPlatformModel(next)
  }

  function setProvider(next: ApiProvider) {
    const changed = provider.value !== next
    provider.value = next
    localStorage.setItem(PROVIDER_KEY, next)
    if (!changed) return

    providerModelsRequest += 1
    providerModelsLoading.value = false
    providerModelsError.value = ''
    const pulled = account.hasKey(next) ? pulledModels.value[next] : undefined
    const nextModels = pulled && pulled.length > 0 ? pulled : SUGGESTED_MODELS[next]
    if (!nextModels.includes(byokModel.value)) {
      setByokModel(nextModels[0] ?? '')
    }
  }

  async function loadPlatformModels(force = false) {
    if (modelsLoading.value) return
    if (!force && platformModels.value.length > 0) return
    modelsLoading.value = true
    modelsError.value = ''
    try {
      const list = await listPlatformModels('bailian')
      platformModels.value = Array.isArray(list) ? list : []
      if (!platformModels.value.some((item) => item.model === platformModel.value)) {
        setPlatformModel('')
      }
    } catch (error) {
      platformModels.value = []
      modelsError.value = errorMessage(error, '平台模型加载失败')
    } finally {
      modelsLoading.value = false
    }
  }

  async function loadProviderModels(force = true) {
    const target = provider.value
    const cached = pulledModels.value[target]
    if (!force && cached && cached.length > 0) return
    if (providerModelsLoading.value) return

    const requestId = ++providerModelsRequest
    providerModelsLoading.value = true
    providerModelsError.value = ''
    try {
      const raw: unknown = await fetchProviderModelsApi(target)
      if (requestId !== providerModelsRequest) return
      const models = normalizeProviderModels(raw)
      if (models.length === 0) {
        providerModelsError.value = '该 Key 未返回模型，已保留建议列表'
        return
      }
      pulledModels.value = { ...pulledModels.value, [target]: models }
      if (provider.value === target) ensureByokModel()
    } catch {
      if (requestId !== providerModelsRequest) return
      providerModelsError.value = '拉取失败，仍显示建议模型'
    } finally {
      if (requestId === providerModelsRequest) providerModelsLoading.value = false
    }
  }

  watch(
    () => account.hasKey(provider.value),
    () => ensureByokModel(),
  )

  watch(
    () => account.plan,
    (plan) => {
      if (!plan) return
      if (plan === 'free' && mode.value === 'platform') setMode('auto')
      if (plan !== 'free' && mode.value === 'auto') setMode('platform')
    },
    { immediate: true },
  )

  const askProblem = computed(() => {
    if (mode.value === 'platform') {
      if (!account.account) {
        return account.error ? '账户信息加载失败，请重试。' : '账户信息加载中，请稍后。'
      }
      if (account.plan === 'free') return 'Free 档仅支持 auto 模式。'
      if (!platformModel.value) return '请选择平台模型。'
    }
    if (mode.value === 'byok') {
      if (account.keysLoading && !account.keysLoaded) return '正在读取 API Key…'
      if (!account.hasKey(provider.value)) return '请先在设置中保存该提供商的 API Key。'
      if (!byokModel.value) return '请选择模型。'
    }
    if (mode.value !== 'byok' && account.account && account.credits < 1) {
      return '积分不足，请购买套餐或改用自己。'
    }
    return ''
  })

  function validateAsk() {
    return askProblem.value
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
      payload.model = platformModel.value
    } else if (activeMode === 'byok') {
      payload.provider = provider.value
      payload.model = (byokModel.value || availableModels.value[0] || '').trim()
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

  ensureByokModel()

  return {
    currentChapter,
    chapterLoading,
    chapterError,
    level,
    mode,
    surface,
    provider,
    model,
    platformModels,
    modelsLoading,
    modelsError,
    pulledModels,
    suggestedModels,
    availableModels,
    providerModelsLoading,
    providerModelsError,
    session,
    sessionBookId,
    messages,
    messagesLoading,
    chatError,
    chatErrorCode,
    asking,
    askProblem,
    loadChapter,
    saveProgress,
    setLevel,
    setMode,
    setSurface,
    setProvider,
    setModel,
    loadPlatformModels,
    loadProviderModels,
    validateAsk,
    ensureSession,
    loadMessages,
    ask,
    resetChat,
  }
})
