<script setup lang="ts">
/**
 * 阅读：主内容区渲染当前章正文与插图，顶栏给导航与「读到这里」。
 * 章节树的分组与进度状态在 SidePanel，本章只负责正文本身。
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { chapterCount, currentBook, openChapter, selectBook, setProgress, store } from '../store'

const route = useRoute()
const router = useRouter()

const toast = ref('')
let toastTimer: ReturnType<typeof setTimeout> | null = null

const bookId = computed(() => Number(route.params.bookId))
const chapterIndex = computed(() => Number(route.params.chapterIndex))

watch(
  [bookId, chapterIndex],
  async ([nextBook, nextChapter]) => {
    if (!Number.isFinite(nextBook) || !Number.isFinite(nextChapter)) return
    if (store.bookId !== nextBook || store.chapters.length === 0) {
      await selectBook(nextBook)
    }
    await openChapter(nextChapter)
  },
  { immediate: true }
)

type Block = { kind: 'p'; text: string } | { kind: 'img'; marker: string; url: string; alt: string }

/** 独占一段的 `[插图NNN]` 标记；对不上图时为 skip，渲染时整块丢弃 */
type ScannedBlock = Block | { kind: 'skip' }

/**
 * 正文按空行切段。独占一段的 `[插图NNN]` 用 marker 查 images，
 * 查到就换成图；编号对不上图时直接丢弃，正文里不留任何痕迹。
 * 行内出现的 `[插图NNN]`（与其它文字同段）不是独占段，按普通文本原样输出。
 */
const blocks = computed<Block[]>(() => {
  const chapter = store.chapter
  if (chapter === null) return []
  const images = new Map(chapter.images.map((image) => [image.marker, image.url]))
  return chapter.text
    .split(/\n\s*\n/)
    .map((raw) => raw.trim())
    .filter((raw) => raw.length > 0)
    .map<ScannedBlock>((raw) => {
      const marker = /^\[插图(\d+)\]$/.exec(raw)
      if (marker === null) return { kind: 'p', text: raw }
      const url = images.get(marker[1])
      if (url === undefined) return { kind: 'skip' }
      return { kind: 'img', marker: marker[1], url, alt: `${chapter.chapter_title} 插图 ${marker[1]}` }
    })
    .filter((block): block is Block => block.kind !== 'skip')
})

function showToast(text: string): void {
  toast.value = text
  if (toastTimer !== null) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value = ''
  }, 2400)
}

async function go(target: number | null | undefined): Promise<void> {
  if (target === null || target === undefined) return
  await router.push({ name: 'reader', params: { bookId: bookId.value, chapterIndex: target } })
}

async function markRead(): Promise<void> {
  const chapter = store.chapter
  if (chapter === null) return
  if (await setProgress(chapter.chapter_index)) {
    showToast(`进度已设 → ${chapter.chapter_title}`)
  } else {
    showToast(store.error ?? '进度写入失败')
  }
}
</script>

<template>
  <main class="main glass">
    <div class="mbar">
      <div class="crumb">
        <b>{{ currentBook?.title ?? '未选书' }}</b>
        <template v-if="store.chapter"> › 卷 {{ store.chapter.volume_index }} › <span style="color: var(--ink)">{{ store.chapter.chapter_title }}</span></template>
      </div>
      <div class="title"><span>{{ store.chapter?.chapter_title ?? '' }}</span></div>
      <button class="gobtn" title="把进度设为本章起点" :disabled="store.chapter === null" @click="markRead">
        读到这里
      </button>
      <div class="navs">
        <button :disabled="!store.chapter?.prev_chapter_index" @click="go(store.chapter?.prev_chapter_index)">‹</button>
        <button :disabled="!store.chapter?.next_chapter_index" @click="go(store.chapter?.next_chapter_index)">›</button>
      </div>
    </div>

    <article class="read">
      <div v-if="store.chapter === null" class="placeholder">
        {{ store.loading ? '加载章节…' : '从左侧章节树选择一章' }}
      </div>
      <template v-else>
        <div class="chapter-head">
          <span class="vol-tag">卷 {{ store.chapter.volume_index }}</span>
          <!--
            把全书章序号摆到标题旁边，是为了让它与回答里的 `[C数字]` 对得上号。
            两者不同源：`[C数字]` 用全书连续序号，章节标题里的「第N话」按卷重新编号——
            全书第 7 章的标题恰恰写着「第6话」。不摆出来，用户按话数去找就会找错章。
          -->
          <span class="vol-tag">全书第 {{ store.chapter.chapter_index }} 章</span>
          <h1>{{ store.chapter.chapter_title }}</h1>
        </div>

        <div class="body-text">
          <template v-for="(block, index) in blocks" :key="index">
            <p v-if="block.kind === 'p'">{{ block.text }}</p>
            <img v-else class="illus" :src="block.url" :alt="block.alt" loading="lazy" />
          </template>
        </div>

        <div class="meta-note loc">
          卷 {{ store.chapter.volume_index }} · 全局 seq {{ store.chapter.chapter_index }}/{{ chapterCount }} ·
          ◎ 进度 {{ store.progress?.max_seq ?? 0 }}
        </div>
      </template>
    </article>

    <div class="toast" :class="{ show: toast !== '' }">{{ toast }}</div>
  </main>
</template>
