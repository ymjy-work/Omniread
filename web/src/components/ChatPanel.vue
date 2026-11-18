<script setup lang="ts">
import { onMounted, watch } from 'vue'
import MessageList from './MessageList.vue'
import { useChat } from '../composables/useChat'
import { useReaderStore } from '../stores/reader'
import type { Citation } from '../types/chat'

const props = defineProps<{ bookId: number }>()
const emit = defineEmits<{ cite: [citation: Citation] }>()

const reader = useReaderStore()
const { question, sending, prepare, send } = useChat(() => props.bookId)

onMounted(() => {
  void prepare()
})

watch(
  () => props.bookId,
  () => {
    void prepare()
  },
)

function handleCite(citation: Citation) {
  emit('cite', citation)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void send()
  }
}
</script>

<template>
  <aside class="chat-panel">
    <header class="chat-head">
      <div class="chat-title-row">
        <h2>文中助手</h2>
        <span v-if="reader.session" class="session-tag">会话 #{{ reader.session.id }}</span>
      </div>

      <div class="level-switch" role="group" aria-label="回答范围">
        <button
          type="button"
          :class="{ active: reader.level === 'past' }"
          :aria-pressed="reader.level === 'past'"
          @click="reader.setLevel('past')"
        >
          已读
        </button>
        <button
          type="button"
          :class="{ active: reader.level === 'full' }"
          :aria-pressed="reader.level === 'full'"
          @click="reader.setLevel('full')"
        >
          全书
        </button>
      </div>

      <p class="level-hint">
        {{
          reader.level === 'past'
            ? '只依据已读章节回答，避免剧透。'
            : '可检索全书范围，可能包含后续情节。'
        }}
      </p>
    </header>

    <MessageList
      :messages="reader.messages"
      :loading="reader.messagesLoading"
      :error="reader.chatError"
      :asking="reader.asking"
      @cite="handleCite"
    />

    <div v-if="reader.chatError && !reader.session" class="session-error">
      <span>会话未能建立。</span>
      <button class="btn btn-ghost" type="button" @click="prepare()">重试</button>
    </div>

    <footer class="composer">
      <textarea
        v-model="question"
        class="composer-input"
        rows="3"
        placeholder="就这本书提问…"
        :disabled="reader.asking"
        @keydown="handleKeydown"
      ></textarea>
      <div class="composer-row">
        <span class="hint">Enter 发送 · Shift+Enter 换行</span>
        <button
          class="btn btn-primary send-btn"
          type="button"
          :disabled="sending || !question.trim()"
          @click="send()"
        >
          <span v-if="sending" class="spinner sm"></span>
          {{ sending ? '回答中' : '发送' }}
        </button>
      </div>
    </footer>
  </aside>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--surface);
}

.chat-head {
  flex: none;
  padding: 16px 16px 14px;
  border-bottom: 1px solid var(--border);
}

.chat-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.chat-head h2 {
  font-size: 15px;
  font-weight: 600;
}

.session-tag {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--text-muted);
}

.level-switch {
  display: flex;
  gap: 3px;
  margin-top: 12px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
}

.level-switch button {
  flex: 1;
  padding: 5px 10px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12.5px;
  transition: background-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.level-switch button:hover {
  color: var(--text);
}

.level-switch button.active {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: var(--shadow-sm);
}

.level-hint {
  margin-top: 9px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-muted);
}

.session-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 14px 8px;
  padding: 8px 10px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.session-error .btn {
  color: var(--danger);
  font-size: 12.5px;
  padding: 4px 8px;
}

.composer {
  flex: none;
  padding: 12px 14px 14px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}

.composer-input {
  display: block;
  width: 100%;
  min-height: 76px;
  max-height: 180px;
  padding: 10px 12px;
  resize: vertical;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-2);
  font-size: 14px;
  line-height: 1.65;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.composer-input::placeholder {
  color: var(--text-muted);
}

.composer-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
  background: var(--surface);
}

.composer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 9px;
}

.hint {
  font-size: 11px;
  color: var(--text-muted);
}

.send-btn {
  min-width: 78px;
  padding: 8px 16px;
  font-size: 13.5px;
}
</style>