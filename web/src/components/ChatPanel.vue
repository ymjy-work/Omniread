<script setup lang="ts">
/**
 * 剧情问答：提问 → SSE 流式回答。
 *
 * 数据路径固定为 /api/v1/query/stream（经 Java 网关），失败一律走 sse.ts 的 onError，
 * 这里只负责把事件翻译成界面上的一行行状态。
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { citationSegments } from '../citation'
import type { CitationSegment } from '../citation'
import { formatErrorLine } from '../errors'
import { openQueryStream } from '../sse'
import type { SseConnection } from '../sse'
import { chapterCount, currentBook, setLevel, store } from '../store'
import type { ContextChapter, QueryLevel } from '../types'

interface ChatMessage {
  id: number
  role: 'user' | 'ai'
  text: string
  streaming: boolean
  /** 检索域，来自 realm_resolved */
  realm: string | null
  /** 召回/重排计数，来自 retrieval_completed 与 rerank_completed */
  recall: string | null
  citations: ContextChapter[]
  error: string | null
}

const messages = ref<ChatMessage[]>([])
const draft = ref('')
const scroller = ref<HTMLElement | null>(null)
const router = useRouter()
let seq = 0
let connection: SseConnection | null = null

const sending = computed(() => connection !== null)
const canSend = computed(() => store.bookId !== null && draft.value.trim() !== '' && !sending.value)

/** 按 id 定位后原地改字段：数组元素读出来才是响应式代理，直接改局部变量不会触发更新 */
function patch(id: number, changes: Partial<ChatMessage>): void {
  const target = messages.value.find((message) => message.id === id)
  if (target !== undefined) Object.assign(target, changes)
}

function recallOf(id: number): string {
  return messages.value.find((message) => message.id === id)?.recall ?? ''
}

function textOf(id: number): string {
  return messages.value.find((message) => message.id === id)?.text ?? ''
}

watch(messages, () => {
  void nextTick(() => {
    const element = scroller.value
    if (element !== null) element.scrollTop = element.scrollHeight
  })
}, { deep: true })

onUnmounted(() => {
  connection?.close()
  connection = null
})

function send(): void {
  const question = draft.value.trim()
  const bookId = store.bookId
  if (question === '' || bookId === null || connection !== null) return

  const level: QueryLevel = store.level
  messages.value.push({ id: ++seq, role: 'user', text: question, streaming: false, realm: null, recall: null, citations: [], error: null })

  const aiId = ++seq
  messages.value.push({ id: aiId, role: 'ai', text: '', streaming: true, realm: null, recall: null, citations: [], error: null })
  draft.value = ''

  connection = openQueryStream(
    {
      book_id: bookId,
      question,
      level,
      // level=past 时必填，由 Java 在 API 边界校验
      progress: level === 'past' ? store.progress?.max_seq ?? null : null
    },
    {
      onEvent: (frame) => {
        switch (frame.event) {
          case 'realm_resolved':
            patch(aiId, { realm: `检索域 [${frame.data.lo}, ${frame.data.hi}]` })
            break
          case 'retrieval_completed':
            patch(aiId, {
              recall: `召回：dense ${frame.data.dense_count} · BM25 ${frame.data.bm25_count} · fused ${frame.data.fused_count}`
            })
            break
          case 'rerank_completed':
            patch(aiId, { recall: `${recallOf(aiId)} · rerank ${frame.data.output_count}/${frame.data.input_count}` })
            break
          case 'context_assembled':
            patch(aiId, { recall: `${recallOf(aiId)} · 装配 ${frame.data.chunks.length} 片` })
            break
          case 'generation_started':
            patch(aiId, { recall: `${recallOf(aiId)} · ${frame.data.answer_provider}/${frame.data.answer_model}` })
            break
          case 'answer_delta':
            patch(aiId, { text: `${textOf(aiId)}${frame.data.text}` })
            break
          case 'citation_ready':
            patch(aiId, { citations: frame.data.context_chapters })
            break
          case 'query_done':
            // 终止帧只带状态与引用；正文已经由 answer_delta 逐帧上屏，不在此覆盖
            patch(aiId, { citations: frame.data.context_chapters, streaming: false })
            break
          case 'query_error':
            patch(aiId, { error: formatErrorLine(frame.data.code, frame.data.message), streaming: false })
            break
          case 'query_started':
            break
        }
      },
      onError: (error) => {
        patch(aiId, { error: formatErrorLine(error.code, error.message), streaming: false })
      },
      onDone: () => {
        patch(aiId, { streaming: false })
        connection = null
      }
    }
  )
}

/** 正文按规范引用切段；非规范写法落在普通文本段里，原样显示 */
function segmentsOf(message: ChatMessage): CitationSegment[] {
  return citationSegments(message.text)
}

/** 角标提示文案：引用列表里有标题就用它，越界引用（不在本次允许集合里）只给章号 */
function citeTitle(message: ChatMessage, chapterIndex: number | null): string {
  if (chapterIndex === null) return ''
  const citation = message.citations.find((item) => item.chapter_index === chapterIndex)
  return citation === undefined
    ? `第 ${chapterIndex} 章`
    : `第 ${chapterIndex} 章 · ${citation.chapter_title}`
}

/** 跳章复用阅读路由；C0 不是合法章号，不跳 */
async function jumpTo(chapterIndex: number | null): Promise<void> {
  const bookId = store.bookId
  if (chapterIndex === null || chapterIndex < 1 || bookId === null) return
  await router.push({ name: 'reader', params: { bookId, chapterIndex } })
}

function pickLevel(level: QueryLevel): void {
  setLevel(level)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}
</script>

<template>
  <section class="chat glass">
    <div class="chead">
      <b>
        <span class="dot" :class="{ warn: store.level === 'full' }" title="回顾 = 绿色 · 剧透 = 黄色"></span>
        剧情问答 <span style="font-weight: 500; color: var(--ink-3); font-size: 11px">Omniread AI</span>
      </b>
      <div class="seg-ctl">
        <button :class="{ on: store.level === 'past' }" title="回顾：只答已读（1~进度），防剧透" @click="pickLevel('past')">
          回顾
        </button>
        <button :class="{ on: store.level === 'full' }" title="剧透：全书开放" @click="pickLevel('full')">剧透</button>
      </div>
    </div>

    <div ref="scroller" class="messages">
      <div v-if="messages.length === 0" class="blank">就这本书提问…（可粘贴选中的正文）</div>

      <template v-for="message in messages" :key="message.id">
        <div v-if="message.role === 'user'" class="msg user">
          <div class="bubble">{{ message.text }}</div>
        </div>

        <div v-else class="msg ai" :class="{ streaming: message.streaming }">
          <div class="av" style="background: linear-gradient(135deg, #6d7bff, #b76bff)">O</div>
          <div class="bubble">
            <details class="think">
              <summary>
                <span class="tk-ico">🧠</span>
                <span>思考 · 检索依据（{{ message.citations.length }} 条引用）</span>
                <span class="tk-chev">▾</span>
              </summary>
              <div class="think-body">
                <div class="tk-line">
                  <span class="tk-pill">{{ store.level === 'past' ? '已读回顾' : '全书剧透' }}</span>
                  <span class="tk-dim">{{ message.realm ?? '等待检索结果…' }}</span>
                </div>
                <div class="tk-line">
                  <span class="tk-dim">{{ message.recall ?? '' }}</span>
                </div>
                <div v-if="message.citations.length > 0" class="cite-row">
                  <span v-for="citation in message.citations" :key="citation.chapter_index" class="cite">
                    [{{ citation.chapter_index }}] {{ citation.chapter_title }} ↗
                  </span>
                </div>
              </div>
            </details>

            <div class="ans-text"><template v-for="(segment, index) in segmentsOf(message)" :key="index"><sup v-if="segment.kind === 'citation'" class="cite-an" :title="citeTitle(message, segment.chapterIndex)" @click="jumpTo(segment.chapterIndex)">{{ segment.chapterIndex }}</sup><template v-else>{{ segment.text }}</template></template></div>
            <div v-if="message.error" class="errline">{{ message.error }}</div>
          </div>
        </div>
      </template>
    </div>

    <div class="composer">
      <div class="box">
        <textarea
          v-model="draft"
          rows="1"
          placeholder="就这本书提问…（可粘贴选中的正文）"
          @keydown="onKeydown"
        ></textarea>
        <button class="send" :disabled="!canSend" @click="send">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </div>
      <div class="row">
        <span>上下文：{{ currentBook?.title ?? '未选书' }} · {{ store.progress?.max_seq ?? 0 }}/{{ chapterCount }}</span>
        <span>Enter 发送 · Shift+Enter 换行</span>
      </div>
    </div>
  </section>
</template>
