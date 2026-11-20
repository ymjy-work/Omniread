<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useBookStore } from '../stores/book'
import type { Book } from '../types/api'

const bookStore = useBookStore()

const books = computed(() => bookStore.books)

onMounted(() => {
  void bookStore.fetchBooks()
})

function coverTone(index: number) {
  return `tone-${index % 5}`
}

function initial(book: Book) {
  return book.title.trim().charAt(0) || '书'
}
</script>

<template>
  <div class="library-page">
    <main class="library-main">
      <section class="hero">
        <div>
          <h1>书库</h1>
          <p class="hero-desc">从上次停下的那一页继续。</p>
        </div>
        <div v-if="!bookStore.booksLoading && !bookStore.booksError" class="hero-count">
          <strong>{{ books.length }}</strong>
          <span>本书</span>
        </div>
      </section>

      <div v-if="bookStore.booksLoading" class="book-grid" aria-busy="true" aria-label="正在加载书库">
        <div v-for="index in 8" :key="index" class="book-card skeleton-card">
          <div class="skeleton cover-skeleton"></div>
          <div class="skeleton line-skeleton wide"></div>
          <div class="skeleton line-skeleton"></div>
        </div>
      </div>

      <section v-else-if="bookStore.booksError" class="state-box">
        <p class="state-title">书库加载失败</p>
        <p class="state-desc">{{ bookStore.booksError }}</p>
        <button class="btn" type="button" @click="bookStore.fetchBooks()">重新加载</button>
      </section>

      <section v-else-if="books.length === 0" class="state-box">
        <span class="empty-glyph">空</span>
        <p class="state-title">书库还没有书</p>
        <p class="state-desc">书籍由管理员导入后会出现在这里。</p>
      </section>

      <div v-else class="book-grid">
        <RouterLink
          v-for="(book, index) in books"
          :key="book.id"
          class="book-card"
          :to="`/books/${book.id}`"
        >
          <div class="cover" :class="coverTone(index)">
            <img v-if="book.coverUrl" :src="book.coverUrl" :alt="`${book.title} 封面`" />
            <template v-else>
              <span class="cover-glyph">{{ initial(book) }}</span>
              <span class="cover-rule"></span>
            </template>
          </div>
          <div class="book-meta">
            <h2 class="book-title">{{ book.title }}</h2>
            <p class="book-author">{{ book.author || '佚名' }}</p>
            <p class="book-foot">
              <span v-if="book.chapterCount">{{ book.chapterCount }} 章</span>
              <span class="book-continue">
                继续阅读
                <span class="book-arrow" aria-hidden="true">→</span>
              </span>
            </p>
          </div>
        </RouterLink>
      </div>
    </main>
  </div>
</template>

<style scoped>
.library-page {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  background: var(--bg);
}

.library-main {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: clamp(24px, 4vw, 48px) clamp(18px, 3vw, 40px) 64px;
}

.hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: clamp(26px, 4vw, 40px);
}

.hero h1 {
  font-family: var(--font-serif);
  font-size: clamp(30px, 4vw, 42px);
  font-weight: 600;
  letter-spacing: 0.02em;
}

.hero-desc {
  margin-top: 10px;
  font-size: 14px;
  color: var(--text-secondary);
}

.hero-count {
  display: flex;
  align-items: baseline;
  gap: 6px;
  color: var(--text-muted);
  font-size: 13px;
  white-space: nowrap;
}

.hero-count strong {
  font-family: var(--font-serif);
  font-size: 30px;
  font-weight: 500;
  color: var(--text);
}

.book-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(178px, 1fr));
  gap: clamp(18px, 2.6vw, 30px);
}

.book-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  border-radius: var(--radius-md);
}

.cover {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 3 / 4.1;
  overflow: hidden;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  transition: transform 0.22s ease, box-shadow 0.22s ease;
}

.book-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 4px;
}

.book-card:hover .cover,
.book-card:focus-visible .cover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}

.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover::after {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 9px;
  border-right: 1px solid rgba(60, 45, 30, 0.12);
  background: linear-gradient(90deg, rgba(60, 45, 30, 0.14), rgba(60, 45, 30, 0));
}

.tone-0 {
  background: linear-gradient(150deg, var(--cover-a), var(--cover-b));
}

.tone-1 {
  background: linear-gradient(150deg, var(--surface-3), var(--cover-a));
}

.tone-2 {
  background: linear-gradient(150deg, var(--cover-b), var(--surface-3));
}

.tone-3 {
  background: linear-gradient(160deg, var(--surface-2), var(--cover-b));
}

.tone-4 {
  background: linear-gradient(140deg, var(--cover-a), var(--surface-2));
}

.cover-glyph {
  padding-left: 9px;
  font-family: var(--font-serif);
  font-size: clamp(42px, 5vw, 62px);
  color: color-mix(in srgb, var(--reader-text) 46%, transparent);
}

.cover-rule {
  position: absolute;
  bottom: 18%;
  left: 50%;
  width: 34px;
  height: 1px;
  transform: translateX(-50%);
  background: color-mix(in srgb, var(--reader-text) 24%, transparent);
}

.book-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.book-title {
  display: -webkit-box;
  overflow: hidden;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.book-author {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  color: var(--text-secondary);
}

.book-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.book-continue {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: var(--text-secondary);
}

.book-arrow {
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.book-card:hover .book-arrow,
.book-card:focus-visible .book-arrow {
  opacity: 1;
  transform: none;
}

.skeleton-card {
  pointer-events: none;
}

.cover-skeleton {
  aspect-ratio: 3 / 4.1;
  border-radius: var(--radius-md);
}

.line-skeleton {
  width: 62%;
  height: 12px;
}

.line-skeleton.wide {
  width: 86%;
  height: 15px;
}

.empty-glyph {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  border: 1px dashed var(--border-strong);
  border-radius: 50%;
  font-family: var(--font-serif);
  font-size: 26px;
  color: var(--text-muted);
}

@media (max-width: 720px) {
  .hero {
    align-items: flex-start;
  }

  .hero-count {
    display: none;
  }

  .book-grid {
    grid-template-columns: repeat(auto-fill, minmax(142px, 1fr));
    gap: 18px 14px;
  }
}
</style>
