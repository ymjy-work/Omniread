/**
 * 前端 ↔ Java 网关契约（contracts/openapi/frontend-api-v1.yaml）的 TypeScript 形状。
 *
 * 手写而非代码生成：契约只有 13 个 schema，生成器带来的构建期依赖与产物噪音
 * 大于它省下的维护量。字段名与契约逐字一致，改契约必须同步改本文件。
 * 所有时间相关的量都用契约里的原字段名，不做重命名。
 */

// ---------- meta ----------

/** 两个进程各有一个 health，service 用于自证来源 */
export type HealthService = 'omniread-rag' | 'omniread-backend'

export interface Health {
  status: 'ok'
  service: HealthService
}

// ---------- catalog ----------

export interface Book {
  book_id: number
  title: string
  author: string
  /** Java 用它校验 progress 上界 */
  chapter_count: number
  volume_count: number
}

export interface BookList {
  books: Book[]
}

export interface ChapterMeta {
  chapter_index: number
  chapter_title: string
  volume_index: number
  /** 取 index.jsonl[].vol 原值，不做归一化 */
  volume_title: string
}

export interface ChapterList {
  book_id: number
  /** 平铺、chapter_index 升序、不分页；按 volume_index 分组是前端的事 */
  chapters: ChapterMeta[]
}

export interface ChapterImage {
  /** 与正文里的 [插图NNN] 编号对齐；对不上就不渲染 */
  marker: string
  url: string
}

export interface ChapterDetail {
  chapter_index: number
  chapter_title: string
  volume_index: number
  volume_title: string
  /** 章节正文全文，[插图NNN] 占位符原样保留 */
  text: string
  images: ChapterImage[]
  /** 只回章序号，不回正文 */
  prev_chapter_index?: number | null
  next_chapter_index?: number | null
}

export interface Progress {
  book_id: number
  /** 已读到的章（= chapter_index），1..chapter_count */
  progress: number
}

export interface ProgressWrite {
  progress: number
}

// ---------- 认证 ----------

/**
 * 契约 CurrentUser：`login` 与 `auth/me` 的响应体。**刻意不含账户 id**
 * （前端用不到，发出去就成了事实上的契约）。`expires_at` 是登录会话的到期时刻。
 */
export interface CurrentUser {
  username: string
  expires_at: string
}

// ---------- rag ----------

/** past: chapter_index <= progress；full: 全部章节 */
export type QueryLevel = 'past' | 'full'

export interface QueryOptions {
  /**
   * 是否做查询改写（默认 true）。请求侧的开关，不是结果的回传位——
   * 改写的前后文走 `rewrite_completed` 事件。无历史时没有可消解的指代，Java 自己跳过。
   */
  rewrite?: boolean
  neighbor_expand?: boolean
}

export interface QueryRequest {
  book_id: number
  question: string
  level: QueryLevel
  /** level=past 时必填，由 Java 在 API 边界校验 */
  progress?: number | null
  options?: QueryOptions
}

export interface ContextChapter {
  chapter_index: number
  chapter_title: string
}

export interface Usage {
  answer_provider: string
  answer_model: string
  latency_ms: number
  /** 装配进 prompt 的材料 token 估算（本轮检索捞上来的那部分） */
  context_tokens: number
}

/** 拒答是正常业务结果，HTTP 仍为 200 */
export type QueryStatus = 'answered' | 'insufficient_evidence'

export interface QueryResponse {
  request_id: string
  status: QueryStatus
  /** 拒答时由服务端固定话术填充，不由模型生成 */
  answer: string
  /** 允许被引用的范围，不是模型实际引用了哪些章 */
  context_chapters: ContextChapter[]
  usage: Usage
}

/**
 * 契约 `ErrorBody.code` 的闭枚举——**13 个码的并集**（两份契约共用同一个 schema，
 * 所以两侧的码都列在这里）。运行时以数组存在：sse.ts 拿它判断一个码认不认识。
 * 表里的「谁产生 / HTTP」对照在 `contracts/openapi/frontend-api-v1.yaml` 的 ErrorBody。
 */
export const ERROR_CODES = [
  'RAG_INVALID_REALM',
  'RAG_INVALID_REQUEST',
  'RAG_UNAUTHENTICATED',
  'RAG_FORBIDDEN',
  'RAG_NOT_FOUND',
  'RAG_SESSION_MISMATCH',
  'RAG_RATE_LIMITED',
  'RAG_DAILY_QUOTA_EXCEEDED',
  'RAG_CONCURRENT_QUERY',
  'RAG_LOGIN_LOCKED',
  'RAG_PROVIDER_ERROR',
  'RAG_UNAVAILABLE',
  'RAG_TIMEOUT'
] as const

export type ErrorCode = (typeof ERROR_CODES)[number]

/** 只覆盖非 2xx；前端只按 code 分支，不得字符串匹配 message */
export interface ErrorBody {
  request_id: string
  code: ErrorCode
  message: string
}

/** 单轮问答（JSON 同步）。前端走 sse.ts 的流式路径，这个留给脚本与调试。 */
export interface SessionQueryRequest extends QueryRequest {
  /**
   * 本轮所属会话。**`book_id` 与 `level` 与会话冗余是刻意的**：它们是一致性断言，
   * 与会话不符时服务端返回 409，不静默采用会话的值（串味的症状只能是靠猜）。
   */
  session_id: string
}

// ---------- 会话 ----------

/** 契约 `ChatMessage`：会话里的一条消息。**不带 meta**（改写前后、模型与 prompt 版本是内部诊断列） */
export interface ChatMessage {
  id: number
  seq: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
  /**
   * 这一轮装配进上下文的章节号（只有 assistant 有）。
   * 刷新后靠它恢复「检索依据」的引用条——没有它历史就只剩正文。
   */
  context_chapters?: number[]
}

/** 契约 `ChatSessionSummary`：列表项，不含消息（列表不为每条会话搬运全文） */
export interface ChatSessionSummary {
  id: string
  book_id: number
  /** 首轮生成；还没问过时是占位标题 */
  title: string
  level: QueryLevel
  /** 分叉来源；不是分叉则为 null。列表里当普通会话显示并标注来源，不做树形 UI */
  forked_from: string | null
  created_at: string
  last_active_at: string
}

export interface SessionList {
  sessions: ChatSessionSummary[]
}

/** 契约 `SessionDetail`：列表项 + 消息 */
export interface SessionDetail extends ChatSessionSummary {
  messages: ChatMessage[]
}

// ---------- SSE ----------

export interface ScoredChunk {
  chunk_key: string
  chapter_index: number
  score: number
  rank: number
}

export interface ChunkRef {
  chunk_key: string
  chapter_index: number
  /** hit = 直接命中，neighbor = 邻接扩展带进来的 */
  source: 'hit' | 'neighbor'
}

export interface DroppedChunk {
  chunk_key: string
  reason: string
}

export interface QueryStartedPayload {
  request_id: string
  book_id: number
  level: QueryLevel
  progress: number | null
}

export interface RealmResolvedPayload {
  lo: number
  hi: number
}

export interface RetrievalCompletedPayload {
  dense_count: number
  bm25_count: number
  fused_count: number
  fused_top: ScoredChunk[]
}

export interface RerankCompletedPayload {
  input_count: number
  output_count: number
  ranked: ScoredChunk[]
}

export interface ContextAssembledPayload {
  /** 最终进入 prompt 的集合，realm re-check 与 token budget 均已结算 */
  chunks: ChunkRef[]
  token_estimate: number
  dropped: DroppedChunk[]
}

export interface GenerationStartedPayload {
  answer_provider: string
  answer_model: string
  prompt_version: string
}

export interface AnswerDeltaPayload {
  text: string
}

export interface CitationReadyPayload {
  context_chapters: ContextChapter[]
}

export interface QueryDonePayload {
  status: QueryStatus
  context_chapters: ContextChapter[]
  usage: Usage
  /** 网关补的：这一轮送进模型的会话内容（历史 + 问题 + 摘要 + 材料）token 估算 */
  prompt_tokens: number
  /** 网关补的：回答模型的上下文窗口，占比的分母 */
  context_window: number
}

export interface QueryErrorPayload {
  request_id: string
  code: ErrorCode
  message: string
}

/** 事件名即 dispatch 键，顺序与契约事件流顺序一致 */
export const SSE_EVENT_NAMES = [
  'query_started',
  'realm_resolved',
  'retrieval_completed',
  'rerank_completed',
  'context_assembled',
  'generation_started',
  'answer_delta',
  'citation_ready',
  'query_done',
  'query_error'
] as const

export type SseEventName = (typeof SSE_EVENT_NAMES)[number]

/** 事件名 → 负载。onEvent 的 event 与 data 由此约束成对出现 */
export interface SseEventMap {
  query_started: QueryStartedPayload
  realm_resolved: RealmResolvedPayload
  retrieval_completed: RetrievalCompletedPayload
  rerank_completed: RerankCompletedPayload
  context_assembled: ContextAssembledPayload
  generation_started: GenerationStartedPayload
  answer_delta: AnswerDeltaPayload
  citation_ready: CitationReadyPayload
  query_done: QueryDonePayload
  query_error: QueryErrorPayload
}

/**
 * 一个已解析的帧：event 与 data 成对。
 * 写成可辨识联合，消费方 `switch (frame.event)` 就能把 frame.data 收窄到对应负载类型。
 */
export type SseFrame = {
  [K in SseEventName]: { event: K; data: SseEventMap[K] }
}[SseEventName]
