<script setup lang="ts">
/**
 * 剧情问答：会话（新建 / 切换 / 删除 / 切档位分叉）+ 提问 → SSE 流式回答。
 *
 * 数据路径固定为 /api/v1/query/stream（经 Java 网关），失败一律走 sse.ts 的 onError，
 * 这里只负责把事件翻译成界面上的一行行状态。
 *
 * 三条口径：
 *
 * - **会话是懒建的**：没有当前会话时，第一句提问才新建（档位用界面上选的那个）。
 *   这样每个会话都有内容，列表里不攒问都没问过的空壳。
 * - **档位固定在会话上**（契约）：看着对话切档位不是改会话，而是**分叉**——
 *   先确认（「既然叫分叉，就得让人知道旧会话还在」），再复制一份换档位。
 * - **历史消息没有 meta**（契约刻意不下发）：恢复出来的气泡不带引用与耗时，
 *   角标因此只报章号、不断言它在不在本次上下文里。
 */
import { computed, nextTick, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import AnswerBody from './AnswerBody.vue'
import { formatErrorLine } from '../errors'
import { openQueryStream } from '../sse'
import type { SseConnection } from '../sse'
import {
  active,
  create as createSession,
  fork,
  forBook,
  levelLabel,
  open as openSession,
  refresh as refreshSessions,
  remove as removeSession,
  sessionsError
} from '../sessions'
import { chapterCount, currentBook, setLevel, store } from '../store'
import type { ChatMessage, ChatSessionSummary, ContextChapter, QueryLevel } from '../types'

interface Bubble {
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
  /**
   * 从服务端恢复出来的历史消息（切会话时）。它们**没有 meta**——
   * 引用、耗时、检索依据一概没有，所以「思考 · 检索依据」那一块整块不显示，
   * 而不是显示一堆「等待检索结果…」。
   */
  restored: boolean
}

const messages = ref<Bubble[]>([])
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
/** 正在建会话（懒建那一刻，还没有连接可看） */
const starting = ref(false)

const sending = computed(() => connection.value !== null || starting.value)

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

// ---------- 会话 ----------

const menuOpen = ref(false)
/** 当前书的会话（列表接口不按书过滤——那是前端的事） */
const bookSessions = computed(() => forBook(store.bookId))
const activeTitle = computed(() => active.value?.title ?? '新会话')

/** 待确认的动作。分叉与删除共用一个对话框——都是「做之前先说清后果」 */
type Pending = { kind: 'fork'; level: QueryLevel } | { kind: 'delete'; session: ChatSessionSummary }
const pending = ref<Pending | null>(null)
const pendingBusy = ref(false)

const pendingTitle = computed(() => {
  const action = pending.value
  if (action === null) return ''
  return action.kind === 'fork' ? '切档位要新建一个分叉会话' : '删除这个会话？'
})
const pendingBody = computed(() => {
  const action = pending.value
  if (action === null) return ''
  if (action.kind === 'fork') {
    return `会话的档位在建立时就定了。切到「${levelLabel(action.level)}」会从当前对话复制一份出来，原会话原样保留、随时切得回去。`
  }
  return `「${action.session.title}」连同它的全部消息会一起删掉，删了就没了。`
})
const pendingAction = computed(() => (pending.value?.kind === 'fork' ? '分叉并切换' : '删除'))

async function runPending(): Promise<void> {
  const action = pending.value
  if (action === null || pendingBusy.value) return
  pendingBusy.value = true
  try {
    if (action.kind === 'fork') {
      const forked = await fork(action.level)
      // 分叉继承了截至当前点的对话——界面上的气泡就是那一份，不用重拉
      if (forked !== null) setLevel(action.level)
    } else {
      const wasShown = active.value?.id === action.session.id
      if ((await removeSession(action.session.id)) && wasShown) {
        // 删的正是屏上这个：连着半截回答一起清掉
        connection.value?.close()
        connection.value = null
        messages.value = []
        stopTicker()
      }
    }
  } finally {
    pendingBusy.value = false
    pending.value = null
  }
}

/** 服务端的历史消息 → 界面气泡 */
function toBubbles(history: readonly ChatMessage[]): Bubble[] {
  return history.map((message) => ({
    id: ++seq,
    role: message.role === 'user' ? 'user' : 'ai',
    text: message.content,
    streaming: false,
    realm: null,
    recall: null,
    citations: [],
    citationsReady: false,
    error: null,
    phase: '',
    startedAt: 0,
    retrievedAt: null,
    firstTokenAt: null,
    doneAt: null,
    restored: true
  }))
}

async function switchTo(session: ChatSessionSummary): Promise<void> {
  menuOpen.value = false
  if (session.id === active.value?.id) return
  // 正在回答时不切：半截对话切走，攒了一半的正文就没地方落了
  if (connection.value !== null) return
  const detail = await openSession(session.id)
  if (detail === null) return
  messages.value = toBubbles(detail.messages)
  // 档位跟着会话走——分段控件与状态栏读的都是 store.level
  setLevel(detail.level)
}

function newSession(): void {
  menuOpen.value = false
  if (connection.value !== null) return
  active.value = null
  messages.value = []
  // 档位**不重置**：它记的是用户上次的选择，新会话多半还要用同一个
}

/** 列表行里的时间：今天只给时分，更早给月-日 */
function shortTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value: number): string => String(value).padStart(2, '0')
  if (date.toDateString() === new Date().toDateString()) {
    return `${pad(date.getHours())}:${pad(date.getMinutes())}`
  }
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

// 换书 = 换一整个会话空间：当前会话属于上一本书，屏上的气泡也不再相关。
// immediate：首次挂载就拉一次列表（那时 bookId 可能还是 null，列表为空是对的）
watch(
  () => store.bookId,
  () => {
    connection.value?.close()
    connection.value = null
    active.value = null
    messages.value = []
    stopTicker()
    void refreshSessions()
  },
  { immediate: true }
)

// ---------- 消息 ----------

/** 按 id 定位后原地改字段：数组元素读出来才是响应式代理，直接改局部变量不会触发更新 */
function patch(id: number, changes: Partial<Bubble>): void {
  const target = messages.value.find((message) => message.id === id)
  if (target !== undefined) Object.assign(target, changes)
}

function messageOf(id: number): Bubble | undefined {
  return messages.value.find((message) => message.id === id)
}

function recallOf(id: number): string {
  return messages.value.find((message) => message.id === id)?.recall ?? ''
}

function textOf(id: number): string {
  return messages.value.find((message) => message.id === id)?.text ?? ''
}

/** 已等待多少秒。收尾后冻结在总耗时上，不再跳动。 */
function elapsedSeconds(message: Bubble): number {
  const end = message.doneAt ?? now.value
  return Math.max(0, Math.round((end - message.startedAt) / 1000))
}

/** 首字延迟（秒，一位小数）；一个字都还没出来时返回空串。 */
function firstTokenSeconds(message: Bubble): string {
  if (message.firstTokenAt === null) return ''
  return ((message.firstTokenAt - message.startedAt) / 1000).toFixed(1)
}

/**
 * 三段耗时：检索（发出 → 装配完成）、首字（发出 → 第一个字）、共（发出 → 收尾）。
 *
 * 分开报是因为它们的量级差得远：检索通常 1–3 秒，而推理型回答模型的首字可能十几秒。
 * 合成一个「总耗时」就看不出该优化哪一段了。
 */
function timingOf(message: Bubble): string {
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

async function send(): Promise<void> {
  const question = draft.value.trim()
  const bookId = store.bookId
  if (question === '' || bookId === null || connection.value !== null || starting.value) return

  // 懒建会话：没有当前会话就先建一个（档位就是界面上选的那个）
  let session = active.value
  if (session === null) {
    starting.value = true
    try {
      session = await createSession(bookId, store.level)
    } finally {
      starting.value = false
    }
    // 建不出来（错误已经显示在会话栏下）：草稿留着，用户可以直接重试
    if (session === null) return
  }

  const level: QueryLevel = session.level
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
    doneAt: null,
    restored: false
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
      session_id: session.id,
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
            // 首轮回答之后服务端才把标题从占位符改成那句话：拉一次，列表与栏上都跟着变
            void refreshSessions()
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

/**
 * 切档位：**没在对话里**时改的是下一场的默认档位；看着对话时走分叉
 * （会话内档位固定，见契约与方案 §四）。
 */
function pickLevel(level: QueryLevel): void {
  if (level === store.level) return
  if (active.value === null || messages.value.length === 0) {
    setLevel(level)
    return
  }
  pending.value = { kind: 'fork', level }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
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
        <button :class="{ on: store.level === 'full' }" title="剧透：全书开放；正在对话时会分叉出一个新会话" @click="pickLevel('full')">剧透</button>
      </div>
    </div>

    <!-- 会话栏：当前会话 → 下拉切换 / 删除，右边是新建 -->
    <div class="sessbar">
      <button class="sess-pick" :class="{ on: menuOpen }" @click="menuOpen = !menuOpen">
        <svg class="s-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
          <path d="M21 11.5a7.5 7.5 0 01-10.9 6.7L5 20l1.6-4.4A7.5 7.5 0 1121 11.5z" />
        </svg>
        <span class="s-title">{{ activeTitle }}</span>
        <span class="s-chev" aria-hidden="true">▾</span>
      </button>
      <button class="sess-new" title="新建会话" @click="newSession">＋</button>

      <div v-if="menuOpen" class="sess-scrim" @click="menuOpen = false"></div>
      <div v-if="menuOpen" class="sess-menu">
        <p v-if="bookSessions.length === 0" class="sess-none">这本书还没有会话，问一句就会开始记录</p>
        <div
          v-for="session in bookSessions"
          :key="session.id"
          class="sess-row"
          :class="{ on: session.id === active?.id }"
        >
          <button class="sess-open" @click="switchTo(session)">
            <span class="t">{{ session.title }}</span>
            <span class="meta">
              <span class="lv" :class="session.level">{{ levelLabel(session.level) }}</span>
              <span v-if="session.forked_from" class="fork" title="切档位时分叉出来的会话">⑂</span>
              <span class="when">{{ shortTime(session.last_active_at) }}</span>
            </span>
          </button>
          <button class="sess-del" title="删除这个会话" @click="pending = { kind: 'delete', session }">×</button>
        </div>
      </div>
    </div>
    <p v-if="sessionsError" class="sess-err">{{ sessionsError }}</p>

    <div ref="scroller" class="messages">
      <div v-if="messages.length === 0" class="blank">
        {{ active === null ? '开一段新对话：就这本书提问…（可粘贴选中的正文）' : '这个会话还没有消息' }}
      </div>

      <template v-for="message in messages" :key="message.id">
        <div v-if="message.role === 'user'" class="msg user">
          <div class="bubble">{{ message.text }}</div>
        </div>

        <div v-else class="msg ai" :class="{ streaming: message.streaming }">
          <div class="av" style="background: linear-gradient(135deg, var(--accent), var(--accent-2))">O</div>
          <div class="bubble">
            <!-- 历史消息没有 meta（契约刻意不下发），检索依据那一块整块不显示——
                 显示一堆「等待检索结果…」比不显示更糟 -->
            <details v-if="!message.restored" class="think">
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

    <!-- 做之前先说清后果：分叉（旧会话还在）与删除（删了就没了）共用这一个框。
         **Teleport 到 body**：面板带 backdrop-filter，它会给 fixed 后代另立一个包含块——
         留在面板里的话，这层「全屏」遮罩其实只盖住面板那一块（截图核对时看出来的）。 -->
    <Teleport to="body">
      <div v-if="pending !== null" class="sess-modal" @click.self="pending = null">
        <div class="sess-card" role="dialog" aria-modal="true">
          <p class="m-title">{{ pendingTitle }}</p>
          <p class="m-body">{{ pendingBody }}</p>
          <div class="m-actions">
            <button class="m-quiet" @click="pending = null">取消</button>
            <button class="m-go" :disabled="pendingBusy" @click="runPending">{{ pendingAction }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>
