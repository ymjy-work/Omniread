<script setup lang="ts">
/**
 * 剧情问答：会话（新建 / 切换 / 删除 / 切档位分叉）+ 提问 → SSE 流式回答。
 *
 * 数据路径固定为 /api/v1/query-stream（经 Java 网关），失败一律走 sse.ts 的 onError，
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
import AppDialog from './AppDialog.vue'
import { divertForbidden } from '../blocking'
import { noticeFor } from '../errors'
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
  rename as renameSession,
  sessions,
  sessionsError,
  shortTime
} from '../sessions'
import { readStoredList, writeStored } from '../storage'
import { setLevel, store } from '../store'
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
  /**
   * 这一轮的失败。**它不是模型说的话**，所以由模板渲染成独立提示，不套头像与气泡。
   * `code` 只作悬停时的排障信息——用户看到的只有 `text`。
   */
  error: { text: string; code: string } | null
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
const composerInput = ref<HTMLTextAreaElement | null>(null)
const scroller = ref<HTMLElement | null>(null)

/**
 * 输入框随内容长高：一行起，到 `max-height` 封顶，再多就框内滚动。
 *
 * 固定一行的话，**换行之后的内容立刻滚出视野**——用户看不见自己写了什么。业界（ChatGPT /
 * Claude / Slack）都是「先长高、到顶再滚」，所以那个高度是**下限**而不是定值。
 */
function autosize(): void {
  const el = composerInput.value
  if (el === null) return
  // 必须先归零：不清空的话，删字时算出的 scrollHeight 仍是上一次的高度，框只会变大不会变小
  el.style.height = 'auto'
  const max = Number.parseFloat(getComputedStyle(el).maxHeight) || 110
  el.style.height = `${Math.min(el.scrollHeight, max)}px`
  el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden'
}
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

/** 当前书的全部会话（列表接口不按书过滤——那是前端的事）。查找浮层读它 */
const bookSessions = computed(() => forBook(store.bookId))

/**
 * 被关掉的标签。**关闭不是删除**：会话还在，只是不再排在这一排里，
 * 从「查找全部会话」点开就会回到标签栏。
 *
 * **要跨刷新记住**（存 localStorage）：关掉的标签刷新后又冒出来，等于「关闭」这个动作没生效。
 * 同时得管住两件事——已删除的会话不会自己从表里消失（下面那个 watch 清理），
 * 以及表本身只涨不落（`persistClosed` 封顶）。
 */
const CLOSED_KEY = 'omniread.closedTabs'
const MAX_CLOSED = 100

const closedTabs = ref<Set<string>>(new Set(readStoredList(CLOSED_KEY)))
const openTabs = computed(() => bookSessions.value.filter((s) => !closedTabs.value.has(s.id)))

function persistClosed(next: Set<string>): void {
  closedTabs.value = next
  writeStored(CLOSED_KEY, JSON.stringify([...next].slice(-MAX_CLOSED)))
}

// 会话被删掉之后它的 id 会永远留在关闭表里。列表每次刷新顺手清一遍——
// **空列表时不清**：首帧的列表还没拉回来，那时清等于把用户关过的标签全抹掉。
watch(sessions, (list) => {
  if (list.length === 0 || closedTabs.value.size === 0) return
  const alive = new Set(list.map((session) => session.id))
  const kept = [...closedTabs.value].filter((id) => alive.has(id))
  if (kept.length !== closedTabs.value.size) persistClosed(new Set(kept))
})

/** 「查找全部会话」的浮层：搜索框 + 过滤后的列表 */
const finderOpen = ref(false)
const findQuery = ref('')
const foundSessions = computed(() => {
  const needle = findQuery.value.trim().toLowerCase()
  if (needle === '') return bookSessions.value
  return bookSessions.value.filter((session) => session.title.toLowerCase().includes(needle))
})

/** 待确认的切档位：会话内档位固定，改它等于分叉出一个新会话 */
const pending = ref<QueryLevel | null>(null)
const pendingBusy = ref(false)

/**
 * 模型**这一轮**的上下文占用，取自 `context_assembled.token_estimate`（装配完成后的结算值）。
 * 分母是服务端装配上下文的 token 预算，两个数要一起改。
 */
const CONTEXT_BUDGET = 6000
const contextTokens = ref<number | null>(null)
const contextRatio = computed(() => {
  const used = contextTokens.value
  return used === null ? 0 : Math.min(1, used / CONTEXT_BUDGET)
})
const contextLabel = computed(() => {
  const used = contextTokens.value
  if (used === null) return '上下文：0%'
  const percent = Math.round((used / CONTEXT_BUDGET) * 100)
  return `上下文：本轮 ${used} / ${CONTEXT_BUDGET} tokens（${percent}%）`
})
/** 圆环周长（r = 9）：stroke-dasharray 的第二个值就是它 */
const RING = (2 * Math.PI * 9).toFixed(2)

const pendingTitle = computed(() => (pending.value === null ? '' : '切档位要新建一个分叉会话'))
const pendingBody = computed(() => {
  const level = pending.value
  if (level === null) return ''
  return `会话的档位在建立时就定了。切到「${levelLabel(level)}」会从当前对话复制一份出来，原会话原样保留、随时切得回去。`
})

async function runPending(): Promise<void> {
  const level = pending.value
  if (level === null || pendingBusy.value) return
  pendingBusy.value = true
  try {
    const forked = await fork(level)
    // 分叉继承了截至当前点的对话——界面上的气泡就是那一份，不用重拉
    if (forked !== null) setLevel(level)
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
  if (connection.value !== null) return
  active.value = null
  messages.value = []
  // 档位**不重置**：它记的是用户上次的选择，新会话多半还要用同一个
}

/** 打开「全部会话」：每次进来清空搜索词，否则上次的词会挡住列表 */
function openFinder(): void {
  findQuery.value = ''
  finderOpen.value = true
}

/** 从查找里点开：顺手把它放回标签栏（关掉过的也能回来） */
function pickFromFinder(session: ChatSessionSummary): void {
  finderOpen.value = false
  reopenTab(session.id)
  void switchTo(session)
}

function reopenTab(id: string): void {
  if (!closedTabs.value.has(id)) return
  const next = new Set(closedTabs.value)
  next.delete(id)
  persistClosed(next)
}

/**
 * 关掉一个标签。**不删会话**——只是从这一排里挪走。
 * 关掉的若是当前会话，切到剩下最靠前的一个；一个都不剩就回到「新会话」的空态。
 * 正在回答时不关当前那个：半截回答切走就没地方落了。
 */
async function closeTab(session: ChatSessionSummary): Promise<void> {
  if (session.id === active.value?.id && connection.value !== null) return
  const next = new Set(closedTabs.value)
  next.add(session.id)
  persistClosed(next)
  if (session.id !== active.value?.id) return
  const fallback = openTabs.value[0]
  if (fallback !== undefined) await switchTo(fallback)
  else newSession()
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

/**
 * `/rename 新名字`：改当前会话的标题。
 *
 * 它是**本地命令**，不是提问——不建会话、不进消息流。没有当前会话时不给建一个空的：
 * 那会攒出一个问都没问过的壳，而改名除了「有个会话」之外不需要别的。
 */
const RENAME_COMMAND = '/rename'

async function runRename(name: string): Promise<void> {
  if (name === '') {
    sessionsError.value = '用法：/rename 新名字'
    return
  }
  const target = active.value
  if (target === null) {
    sessionsError.value = '还没有当前会话：先问一句，再用 /rename 改它的名字'
    return
  }
  await renameSession(target.id, name)
}

async function send(): Promise<void> {
  const question = draft.value.trim()
  const bookId = store.bookId
  if (question === '' || bookId === null || connection.value !== null || starting.value) return

  // 命令先拦下来：它不该触发懒建，也不该占一格消息
  if (question === RENAME_COMMAND || question.startsWith(`${RENAME_COMMAND} `)) {
    draft.value = ''
    void nextTick(autosize)
    await runRename(question.slice(RENAME_COMMAND.length).trim())
    return
  }

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
  // 发完把框缩回一行：v-model 改的是值，高度是内联样式，得自己收
  void nextTick(autosize)
  startTicker()

  connection.value = openQueryStream(
    {
      session_id: session.id,
      book_id: bookId,
      question,
      level,
      // level=past 时必填，由 Java 在 API 边界校验
      progress: level === 'past' ? store.reading?.progress ?? null : null
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
            // 圆环画的就是这个数：装配完成时预算已结算，是这一轮真正的上下文占用
            contextTokens.value = frame.data.token_estimate
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
          case 'query_error': {
            const code = frame.data.code
            const diverted = divertForbidden(code, frame.data.message)
            patch(aiId, {
              error: diverted ? null : { text: noticeFor(code, frame.data.message), code },
              streaming: false,
              phase: '',
              doneAt: Date.now()
            })
            stopTicker()
            break
          }
          case 'query_started':
            break
        }
      },
      onError: (error) => {
        const diverted = divertForbidden(error.code, error.message)
        patch(aiId, {
          error: diverted ? null : { text: noticeFor(error.code, error.message), code: error.code },
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
  pending.value = level
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
    <!-- 会话标签页在最上面：它表示「当前在看哪一段对话」，比标题更常点。
         每个标签带一个 ×——**关闭不是删除**，会话还在，从「查找全部会话」能打开回来 -->
    <div class="tabbar">
      <div class="tabs">
        <div
          v-for="session in openTabs"
          :key="session.id"
          class="tab"
          :class="{ on: session.id === active?.id }"
        >
          <button
            class="tab-open"
            :title="`${session.title}（${levelLabel(session.level)}）`"
            @click="switchTo(session)"
          >
            <span class="t-title">{{ session.title }}</span>
            <span v-if="session.forked_from" class="t-fork" aria-hidden="true">⑂</span>
          </button>
          <button
            class="tab-x"
            :aria-label="`关闭标签：${session.title}`"
            title="关闭标签（不会删除会话）"
            @click="closeTab(session)"
          >
            ×
          </button>
        </div>
        <span v-if="openTabs.length === 0" class="tab-none">还没有打开的会话</span>
      </div>
      <button class="tab-btn" title="新建会话" aria-label="新建会话" @click="newSession">＋</button>
      <button class="tab-btn" title="查找全部会话" aria-label="查找全部会话" @click="openFinder">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5" />
          <path d="M16 16l4 4" />
        </svg>
      </button>
    </div>

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
    <p v-if="sessionsError" class="sess-err">{{ sessionsError }}</p>

    <div ref="scroller" class="messages">
      <div v-if="messages.length === 0" class="blank">
        {{ active === null ? '开一段新对话：就这本书提问…（可粘贴选中的正文）' : '这个会话还没有消息' }}
      </div>

      <template v-for="message in messages" :key="message.id">
        <div v-if="message.role === 'user'" class="msg user">
          <div class="bubble">{{ message.text }}</div>
        </div>

        <!-- 只有真有正文（或这一轮没失败）才画 AI 气泡。失败且没有正文时不画——
             头像 + 空气泡 + 「0 条引用」会把一条系统提示伪装成模型说的话 -->
        <div v-else-if="!message.error || message.text" class="msg ai" :class="{ streaming: message.streaming }">
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
          </div>
        </div>

        <!-- 失败提示：**系统说的，不是模型说的**。有正文时它是气泡后面的一条，
             没有正文时它是这一轮唯一的内容。错误码只挂在 title 上，不摆在用户眼前。 -->
        <div
          v-if="message.role !== 'user' && message.error"
          class="notice"
          role="alert"
          :title="message.error.code"
        >
          <span class="n-ico" aria-hidden="true">!</span>
          <p class="n-text">{{ message.error.text }}</p>
        </div>
      </template>
    </div>

    <div class="composer">
      <div class="box">
        <textarea
          ref="composerInput"
          v-model="draft"
          rows="1"
          placeholder="Enter 发送 · Shift+Enter 换行"
          @input="autosize"
          @keydown="onKeydown"
        ></textarea>
        <!-- 上下文占用的圆环：画在发送键左边，不占输入区的行宽；悬停给出书名与章号 -->
        <span class="ctx" :aria-label="contextLabel" role="img" tabindex="0">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle class="ctx-track" cx="12" cy="12" r="9" />
            <circle
              class="ctx-fill"
              cx="12"
              cy="12"
              r="9"
              :stroke-dasharray="`${(contextRatio * Number(RING)).toFixed(2)} ${RING}`"
            />
          </svg>
          <!-- 还没有上下文时环是空的（0%），也不出提示文字 -->
          <span v-if="contextTokens !== null" class="ctx-tip" aria-hidden="true">{{ contextLabel }}</span>
        </span>
        <button class="send" :disabled="!canSend" aria-label="发送" @click="send">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 两个弹窗都走 AppDialog：遮罩、层级、Esc、焦点圈只写一份。
         分叉（旧会话还在）与删除（删了就没了）共用一个确认框，只是文案不同。 -->
    <AppDialog :open="pending !== null" :title="pendingTitle" @close="pending = null">
      <p>{{ pendingBody }}</p>
      <template #actions>
        <button class="dlg-btn" @click="pending = null">取消</button>
        <button class="dlg-btn primary" :disabled="pendingBusy" @click="runPending">分叉并切换</button>
      </template>
    </AppDialog>

    <!-- 查找全部会话：标签页只放得下几条，多了要能搜 -->
    <AppDialog :open="finderOpen" title="全部会话" :width="520" @close="finderOpen = false">
      <input
        v-model="findQuery"
        class="find-input"
        type="search"
        placeholder="按标题搜索…"
        aria-label="搜索会话"
      />
      <div class="find-list">
        <button
          v-for="session in foundSessions"
          :key="session.id"
          class="find-row"
          :class="{ on: session.id === active?.id }"
          @click="pickFromFinder(session)"
        >
          <span class="f-title">{{ session.title }}</span>
          <span class="f-meta">{{ levelLabel(session.level) }} · {{ shortTime(session.last_active_at) }}</span>
        </button>
        <p v-if="foundSessions.length === 0" class="find-none">没有匹配的会话</p>
      </div>
    </AppDialog>
  </section>
</template>
