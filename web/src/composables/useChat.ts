import { computed, ref, unref } from 'vue'
import type { Ref } from 'vue'
import { useReaderStore } from '../stores/reader'

type BookIdSource = number | Ref<number> | (() => number)

export function useChat(bookId: BookIdSource) {
  const reader = useReaderStore()
  const question = ref('')
  const sending = computed(() => reader.asking)
  const error = computed(() => reader.chatError)

  function resolveBookId() {
    return typeof bookId === 'function' ? bookId() : unref(bookId)
  }

  async function prepare() {
    const id = resolveBookId()
    if (!Number.isFinite(id)) return
    try {
      await reader.ensureSession(id)
    } catch {
      // 错误已写入 reader store
    }
  }

  async function send() {
    const text = question.value.trim()
    if (!text || reader.asking) return
    const id = resolveBookId()
    if (!Number.isFinite(id)) return
    question.value = ''
    try {
      await reader.ensureSession(id)
      await reader.ask(text)
    } catch {
      // 错误已写入 reader store
    }
  }

  return { question, sending, error, prepare, send }
}