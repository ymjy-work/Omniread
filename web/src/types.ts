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
  max_seq: number
}

export interface ProgressWrite {
  max_seq: number
}

// ---------- rag ----------

/** past: chapter_index <= progress；full: 全部章节 */
export type QueryLevel = 'past' | 'full'

export interface QueryOptions {
  /** M0 不实现模型改写，字段保留但不接模型 */
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

export type ErrorCode =
  | 'RAG_INVALID_REALM'
  | 'RAG_PROVIDER_ERROR'
  | 'RAG_UNAVAILABLE'
  | 'RAG_TIMEOUT'

/** 只覆盖非 2xx；前端只按 code 分支，不得字符串匹配 message */
export interface ErrorBody {
  request_id: string
  code: ErrorCode
  message: string
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
