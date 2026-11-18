import { ref } from 'vue'
import type { ChatLevel } from '../types/chat'

export function useChat() {
  const asking = ref(false)

  async function send(_question: string, _level: ChatLevel) {
    // 接入 chat store 与 gateway 接口后补全
  }

  return { asking, send }
}
