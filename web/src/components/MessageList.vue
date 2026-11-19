<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import CitationBadge from './CitationBadge.vue'
import { modeLabel, providerLabel } from '../utils/billing'
import type { ChatMessage, Citation } from '../types/chat'

const props = defineProps<{
  messages: ChatMessage[]
  loading: boolean
  error: string
  asking: boolean
}>()

const emit = defineEmits<{ cite: [citation: Citation] }>()

const scrollBox = ref<HTMLElement | null>(null)

async function scrollToBottom() {
  await nextTick()
  const el = scrollBox.value
  if (el) el.scrollTop = el.scrollHeight
}

function handleCite(citation: Citation) {
  emit('cite', citation)
}

watch(
  () => [props.messages.length, props.asking, props.loading],
  () => {
    void scrollToBottom()
  },
)

onMounted(() => {
  void scrollToBottom()
})
</script>

<template>
  <div ref="scrollBox" class="message-list">
    <div v-if="loading && messages.length === 0" class="list-state">
      <span class="spinner"></span>
      <span>正在载入对话…</span>
    </div>

    <div v-else-if="messages.length === 0" class="list-state empty">
      <span class="empty-mark">问</span>
      <p>可以向文中助手提问，例如“这一章里谁出现了？”</p>
      <p class="empty-sub">回答会附上引用，点引用即可回到原文。</p>
    </div>

    <template v-else>
      <article
        v-for="(message, index) in messages"
        :key="message.id ?? index"
        class="message"
        :class="message.role"
      >
        <div class="bubble">
          <p class="message-text">{{ message.content }}</p>
          <div v-if="message.citations && message.citations.length > 0" class="citations">
            <CitationBadge
              v-for="(citation, citationIndex) in message.citations"
              :key="citationIndex"
              :citation="citation"
              :index="citationIndex"
              @select="handleCite"
            />
          </div>
          <p v-if="message.usage" class="usage-line">
            <span>{{ modeLabel(message.usage.mode) }}</span>
            <span class="usage-sep">·</span>
            <span>{{ providerLabel(message.usage.provider) }} / {{ message.usage.model }}</span>
            <span
              v-if="message.usage.promptTokens || message.usage.completionTokens"
              class="usage-tokens"
            >
              {{ message.usage.promptTokens }} + {{ message.usage.completionTokens }} tokens
            </span>
          </p>
        </div>
      </article>

      <article v-if="asking" class="message assistant">
        <div class="bubble typing" aria-label="正在思考">
          <span></span><span></span><span></span>
        </div>
      </article>
    </template>

    <p v-if="error" class="list-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 16px 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overscroll-behavior: contain;
}

.list-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 220px;
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.8;
}

.list-state.empty {
  justify-content: flex-start;
  padding-top: 48px;
}

.empty-mark {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  margin-bottom: 4px;
  border: 1px dashed var(--border-strong);
  border-radius: 50%;
  font-family: var(--font-serif);
  font-size: 20px;
  color: var(--text-muted);
}

.empty-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.message {
  display: flex;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 92%;
  padding: 11px 13px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.75;
}

.message.user .bubble {
  background: var(--accent-soft);
  border: 1px solid color-mix(in srgb, var(--accent) 22%, transparent);
  border-bottom-right-radius: 5px;
}

.message.assistant .bubble {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-bottom-left-radius: 5px;
}

.message-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.citations {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px dashed var(--border);
}

.usage-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px dashed var(--border);
  font-size: 10.5px;
  line-height: 1.5;
  color: var(--text-muted);
}

.usage-sep {
  opacity: 0.6;
}

.usage-tokens {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 14px 16px;
}

.typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: blink 1.2s infinite ease-in-out;
}

.typing span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes blink {
  0%,
  60%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

.list-error {
  padding: 9px 11px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}
</style>