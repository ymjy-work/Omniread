import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatLevel, ChatMessage } from '../types/chat'
import type { ReadingProgress } from '../types/api'

export const useReaderStore = defineStore('reader', () => {
  const progress = ref<ReadingProgress | null>(null)
  const level = ref<ChatLevel>('past')
  const messages = ref<ChatMessage[]>([])
  const asking = ref(false)

  return { progress, level, messages, asking }
})
