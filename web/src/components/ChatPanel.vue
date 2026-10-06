<script setup lang="ts">
/**
 * 剧情问答：提问 → SSE 流式回答。
 *
 * 数据路径固定为 /api/v1/query/stream（经 Java 网关），失败一律走 sse.ts 的 onError，
 * 这里只负责把事件翻译成界面上的一行行状态。
 */
import { computed, nextTick, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import AnswerBody from './AnswerBody.vue'
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
  /**
   * 引用集合是否已下发（citation_ready / query_done）。
   *
   * 服务端的顺序是「全部 answer_delta → citation_ready → query_done」，
   * 所以流式期间 `citations` 必然是空的。没有这个标记时，悬停角标会把
   * 「还没收到」断言成「本次上下文里没有这一章（越界引用）」——一个假指控。
   * 出错中断时它保持 false，角标就只报章号、不做断言。
   */
  citationsReady: boolean
  error: string | null
  /**
   * 当前阶段，等待期间显示在气泡里。
   *
   * 它不是锦上添花：回答模型是推理型的（`reasoning_effort=max`），**首字之前可能十几秒
   * 一个字都不输出**。此前这段时间界面上只有一个闪烁光标，读起来和卡死没有区别。
   * 阶段文案把「还在检索」与「模型正在想」分开——两件事的等待时间差一个数量级。
   */
  phase: string
  /** 本题发出时刻，用于算已等待多久 */
  startedAt: number
  /** 检索阶段结束（context_assembled）的时刻，用来算检索耗时 */
  retrievedAt: number | null
  /** 首个 answer_delta 的时刻，即首字延迟 */
  firstTokenAt: number | null
  /** 收尾时刻；有值即这题已结束 */
  doneAt: number | null
}

const messages = ref<ChatMessage[]>([])
const draft = ref('')
const scroller = ref<HTMLElement | null>(null)
const router = useRouter()
let seq = 0
/**
 * 当前连接。用 `shallowRef` 而不是普通变量：`sending` 是 computed，
 * 依赖一个普通 `let` 时它永远是首次求值的结果——按钮该禁时不禁、
 * 该恢复时不恢复。连接对象本身不需要深响应，`shallowRef` 足够。
 */
const connection = shallowRef<SseConnection | null>(null)

const sending = computed(() => connection.value !== null)

/** 每一秒推一下，让「已等待 N 秒」是活的——不动的东西看起来才像卡住。 */
const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | null = null

function startTicker(): void {
  if (ticker !== null) return
  ticker = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stopTicker(): void {
  if (ticker === null) return
  clearInterval(ticker)
  ticker = null
}
const canSend = computed(() => store.bookId !== null && draft.value.trim() !== '' && !sending.value)

/** 按 id 定位后原地改字段：数组元素读出来才是响应式代理，直接改局部变量不会触发更新 */
function patch(id: number, changes: Partial<ChatMessage>): void {
  const target = messages.value.find((message) => message.id === id)
  if (target !== undefined) Object.assign(target, changes)
}

function messageOf(id: number): ChatMessage | undefined {
  return messages.value.find((message) => message.id === id)
}

function recallOf(id: number): string {
  return messages.value.find((message) => message.id === id)?.recall ?? ''
}

function textOf(id: number): string {
  return messages.value.find((message) => message.id === id)?.text ?? ''
}

/** 已等待多少秒。收尾后冻结在总耗时上，不再跳动。 */
function elapsedSeconds(message: ChatMessage): number {
  const end = message.doneAt ?? now.value
  return Math.max(0, Math.round((end - message.startedAt) / 1000))
}

/** 首字延迟（秒，一位小数）；一个字都还没出来时返回空串。 */
function firstTokenSeconds(message: ChatMessage): string {
  if (message.firstTokenAt === null) return ''
  return ((message.firstTokenAt - message.startedAt) / 1000).toFixed(1)
}

/**
 * 三段耗时：检索（发出 → 装配完成）、首字（发出 → 第一个字）、共（发出 → 收尾）。
 *
 * 分开报是因为它们的量级差得远：检索通常 1–3 秒，而推理型回答模型的首字可能十几秒。
 * 合成一个「总耗时」就看不出该优化哪一段了。
 */
function timingOf(message: ChatMessage): string {
  if (message.doneAt === null) return ''
  const at = (moment: number | null): string =>
    moment === null ? '—' : `${((moment - message.startedAt) / 1000).toFixed(1)}s`
  return `检索 ${at(message.retrievedAt)} · 首字 ${at(message.firstTokenAt)} · 共 ${at(message.doneAt)}`
}

watch(messages, () => {
  void nextTick(() => {
    const element = scroller.value
    if (element !== null) element.scrollTop = element.scrollHeight
  })
}, { deep: true })

onUnmounted(() => {
  connection.value?.close()
  connection.value = null
  stopTicker()
})

function send(): void {
  const question = draft.value.trim()
  const bookId = store.bookId
  if (question === '' || bookId === null || connection.value !== null) return

  const level: QueryLevel = store.level
  const askedAt = Date.now()
  // `citations` 不放进 blank：blank 会被展开两次，数组是引用，两条消息会共用同一个实例。
  // 今天所有更新都是整体替换所以看不出来，但只要将来有人原地 push，就会同时改到另一条消息。
  const blank = {
    streaming: false,
    realm: null,
    recall: null,
    citationsReady: false,
    error: null,
    phase: '',
    startedAt: askedAt,
    retrievedAt: null,
    firstTokenAt: null,
    doneAt: null
  }
  messages.value.push({ ...blank, id: ++seq, role: 'user', text: question, citations: [] })

  const aiId = ++seq
  // 一发出就写「检索中」：这一段通常 1–3 秒，但空白与「在做事的空白」是两种感受
  messages.value.push({
    ...blank,
    id: aiId,
    role: 'ai',
    text: '',
    streaming: true,
    phase: '检索中',
    citations: []
  })
  draft.value = ''
  startTicker()

  connection.value = openQueryStream(
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
              recall: `召回：dense ${frame.data.dense_count} · BM25 ${frame.data.bm25_count} · fused ${frame.data.fused_count}`,
              phase: '重排与装配中'
            })
            break
          case 'rerank_completed':
            patch(aiId, { recall: `${recallOf(aiId)} · rerank ${frame.data.output_count}/${frame.data.input_count}` })
            break
          case 'context_assembled':
            patch(aiId, {
              recall: `${recallOf(aiId)} · 装配 ${frame.data.chunks.length} 片`,
              phase: '准备生成',
              retrievedAt: Date.now()
            })
            break
          case 'generation_started':
            // 从这里到第一个字之间是**最长的一段静默**：推理型模型先想再写，
            // 文案要说清是在思考，而不是把这段并进「生成中」让它看起来像卡住
            patch(aiId, {
              recall: `${recallOf(aiId)} · ${frame.data.answer_provider}/${frame.data.answer_model}`,
              phase: '模型思考中'
            })
            break
          case 'answer_delta':
            patch(aiId, {
              text: `${textOf(aiId)}${frame.data.text}`,
              phase: '生成中',
              firstTokenAt: messageOf(aiId)?.firstTokenAt ?? Date.now()
            })
            break
          case 'citation_ready':
            patch(aiId, { citations: frame.data.context_chapters, citationsReady: true })
            break
          case 'query_done':
            // 终止帧只带状态与引用；正文已经由 answer_delta 逐帧上屏，不在此覆盖
            patch(aiId, {
              citations: frame.data.context_chapters,
              citationsReady: true,
              streaming: false,
              phase: '',
              doneAt: Date.now()
            })
            stopTicker()
            break
          case 'query_error':
            patch(aiId, {
              error: formatErrorLine(frame.data.code, frame.data.message),
              streaming: false,
              phase: '',
              doneAt: Date.now()
            })
            stopTicker()
            break
          case 'query_started':
            break
        }
      },
      onError: (error) => {
        patch(aiId, {
          error: formatErrorLine(error.code, error.message),
          streaming: false,
          phase: '',
          doneAt: Date.now()
        })
        stopTicker()
        // 必须在这里断开：sse.ts 的失败路径只回调 onError、**从不回调 onDone**，
        // 而 `sending` 看的就是 connection 是否为 null。不置空的话，一次 SSE 失败
        // 会让发送框永久置灰、Enter 失效，只能刷新页面才能恢复。
        connection.value?.close()
        connection.value = null
      },
      onDone: () => {
        patch(aiId, { streaming: false, phase: '', doneAt: messageOf(aiId)?.doneAt ?? Date.now() })
        stopTicker()
        connection.value = null
      }
    }
  )
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
                <span v-if="timingOf(message)" class="tk-time">{{ timingOf(message) }}</span>
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

            <!--
              等待期间的进度行。没有它，这段时间界面上只剩一个闪烁光标——
              而回答模型是推理型的，首字之前可能十几秒不输出任何东西。
              转圈 + 阶段 + 已等待秒数三样一起给，才能回答「它还在动吗」。

              **活的只有 `w-phase` 那一个 span**：`role="status"` 隐含 `aria-live="polite"`
              与 `aria-atomic="true"`，把每秒跳动的秒数放进去，屏幕阅读器会**每秒把整行
              重念一遍**，真正的阶段变化反而被淹掉。所以秒数与首字延迟对辅助技术隐藏，
              它们是给眼睛看的时间感，阶段文案才是要播报的信息。
            -->
            <div v-if="message.streaming" class="waiter">
              <span class="spin" aria-hidden="true"></span>
              <span class="w-phase" role="status">{{ message.phase || '处理中' }}</span>
              <span class="w-time" aria-hidden="true">{{ elapsedSeconds(message) }}s</span>
              <span v-if="firstTokenSeconds(message)" class="w-note" aria-hidden="true">
                首字 {{ firstTokenSeconds(message) }}s
              </span>
            </div>

            <!-- 正文渲染交给 AnswerBody：模型输出是 Markdown，星号与井号不该裸露给用户 -->
            <div class="ans-text">
              <AnswerBody
                :text="message.text"
                :citations="message.citations"
                :citations-ready="message.citationsReady"
                @jump="jumpTo"
              />
            </div>
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
