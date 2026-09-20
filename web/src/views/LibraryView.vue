<script setup lang="ts">
/** 书库：列出 /api/v1/books 的书，选中后进入阅读。导入入口置灰：M0 不做文件导入。 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { loadBooks, selectBook, store } from '../store'
import type { Book } from '../types'

const router = useRouter()

onMounted(() => {
  if (store.books.length === 0) void loadBooks()
})

async function enter(book: Book): Promise<void> {
  await selectBook(book.book_id)
  const chapterIndex = store.progress?.max_seq ?? 1
  void router.push({ name: 'reader', params: { bookId: book.book_id, chapterIndex } })
}
</script>

<template>
  <main class="main glass">
    <div class="mbar">
      <div class="crumb">书库</div>
      <div class="title"><span>我的书库</span></div>
      <!-- M0 不做文件导入：TXT / EPUB 上传未实现，按钮先置灰 -->
      <button class="gobtn" disabled title="TXT / EPUB 上传未实现">导入 TXT / EPUB</button>
    </div>

    <div class="libgrid fade-in">
      <div v-for="book in store.books" :key="book.book_id" class="bookcard">
        <div class="cov">{{ book.title }}</div>
        <div>
          <h2>{{ book.title }}</h2>
          <p>{{ book.author }} · {{ book.volume_count }} 卷 · {{ book.chapter_count }} 话</p>
        </div>
        <button class="gobtn" style="margin-left: auto" @click="enter(book)">进入阅读</button>
      </div>

      <div class="import is-disabled" aria-disabled="true">＋ 拖入文件 / 目录导入（文件导入未实现）</div>
    </div>
  </main>
</template>

<style scoped>
/* 设计稿的 .import 是可点态；这里明确置灰，避免被误当成可用入口 */
.import.is-disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
