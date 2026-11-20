<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import ChatPanel from './ChatPanel.vue'
import UserMenu from './UserMenu.vue'
import { useBookStore } from '../stores/book'
import { useReaderStore } from '../stores/reader'
import type { Citation } from '../types/chat'

const route = useRoute()
const bookStore = useBookStore()
const reader = useReaderStore()

const chatCollapsed = ref(false)
const mobileChatOpen = ref(false)

const currentBookId = computed(() => {
  const value = route.params.bookId
  const id = typeof value === 'string' ? Number(value) : Number.NaN
  return Number.isFinite(id) && id > 0 ? id : 0
})

const currentBookTitle = computed(() => {
  const current = bookStore.currentBook
  if (current?.id === currentBookId.value) return current.title
  const recent = bookStore.recentBook
  return recent?.id === currentBookId.value ? recent.title : ''
})

const readingTarget = computed(() =>
  bookStore.recentBook ? `/books/${bookStore.recentBook.id}` : null,
)
const libraryActive = computed(() => route.name === 'library')
const readingActive = computed(() => currentBookId.value > 0)

function isCompactViewport() {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches
}

function collapseChat() {
  const compact = isCompactViewport()
  mobileChatOpen.value = false
  if (!compact) chatCollapsed.value = true
}

function openChat() {
  chatCollapsed.value = false
  if (isCompactViewport()) mobileChatOpen.value = true
}

function closeMobileChat() {
  mobileChatOpen.value = false
}

function handleCitation(citation: Citation) {
  mobileChatOpen.value = false
  reader.requestCitation(citation)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && mobileChatOpen.value) mobileChatOpen.value = false
}

watch(
  () => route.fullPath,
  () => {
    mobileChatOpen.value = false
  },
)

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="app-shell" :class="{ 'chat-collapsed': chatCollapsed && !mobileChatOpen }">
    <aside class="sidebar">
      <RouterLink class="sidebar-brand" to="/library" aria-label="Omniread 书库">
        <span class="brand-mark">阅</span>
        <span class="brand-copy">
          <strong>Omniread</strong>
          <small>读到哪里，聊到哪里</small>
        </span>
      </RouterLink>

      <nav class="sidebar-nav" aria-label="功能导航">
        <RouterLink
          class="side-link"
          :class="{ active: libraryActive }"
          to="/library"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H10v16H6.5A2.5 2.5 0 0 0 4 21.5z" />
            <path d="M10 3h3.5A2.5 2.5 0 0 1 16 5.5V19h-6z" />
            <path d="M16 8h1.5A2.5 2.5 0 0 1 20 10.5V21h-4z" />
          </svg>
          <span>书库</span>
        </RouterLink>

        <RouterLink
          v-if="readingTarget"
          class="side-link"
          :class="{ active: readingActive }"
          :to="readingTarget"
          :title="bookStore.recentBook ? `继续阅读《${bookStore.recentBook.title}》` : undefined"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M3.5 5.5A3.5 3.5 0 0 1 7 2h5v17H7a3.5 3.5 0 0 0-3.5 3z" />
            <path d="M20.5 5.5A3.5 3.5 0 0 0 17 2h-5v17h5a3.5 3.5 0 0 1 3.5 3z" />
          </svg>
          <span>阅读</span>
        </RouterLink>

        <span
          v-else
          class="side-link disabled"
          aria-disabled="true"
          title="打开一本书后会出现在这里"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M3.5 5.5A3.5 3.5 0 0 1 7 2h5v17H7a3.5 3.5 0 0 0-3.5 3z" />
            <path d="M20.5 5.5A3.5 3.5 0 0 0 17 2h-5v17h5a3.5 3.5 0 0 1 3.5 3z" />
          </svg>
          <span>阅读</span>
          <small>暂无</small>
        </span>
      </nav>

      <div class="sidebar-foot">
        <UserMenu />
      </div>
    </aside>

    <main class="app-main">
      <slot />
    </main>

    <aside
      class="chat-column"
      :class="{ collapsed: chatCollapsed && !mobileChatOpen, 'mobile-open': mobileChatOpen }"
      aria-label="阅读对话栏"
    >
      <ChatPanel
        v-if="currentBookId && (!chatCollapsed || mobileChatOpen)"
        :key="currentBookId"
        :book-id="currentBookId"
        :book-title="currentBookTitle"
        collapsible
        @cite="handleCitation"
        @collapse="collapseChat"
      />

      <button
        v-else-if="currentBookId"
        class="chat-rail"
        type="button"
        aria-label="展开对话面板"
        title="展开文中助手"
        @click="openChat"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 5.5h16v10H9l-5 4z" />
          <path d="M8 9h8M8 12h5" />
        </svg>
        <span>对话</span>
      </button>

      <div v-else-if="!chatCollapsed" class="chat-empty">
        <button
          class="empty-collapse"
          type="button"
          aria-label="收起对话面板"
          title="收起"
          @click="chatCollapsed = true"
        >
          ›
        </button>
        <span class="empty-mark">问</span>
        <h2>选一本书开始对话</h2>
        <p>打开书库中的任意一本书，文中助手会跟随当前书与阅读进度。</p>
      </div>

      <button
        v-else
        class="chat-rail"
        type="button"
        aria-label="展开对话面板"
        title="展开文中助手"
        @click="chatCollapsed = false"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 5.5h16v10H9l-5 4z" />
          <path d="M8 9h8M8 12h5" />
        </svg>
        <span>对话</span>
      </button>
    </aside>

    <button
      v-if="currentBookId && !mobileChatOpen"
      class="mobile-chat-button"
      type="button"
      @click="openChat"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 5.5h16v10H9l-5 4z" />
        <path d="M8 9h8M8 12h5" />
      </svg>
      文中助手
    </button>

    <nav class="mobile-nav" aria-label="功能导航">
      <RouterLink class="mobile-tab" :class="{ active: libraryActive }" to="/library">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H10v16H6.5A2.5 2.5 0 0 0 4 21.5z" />
          <path d="M10 3h3.5A2.5 2.5 0 0 1 16 5.5V19h-6z" />
          <path d="M16 8h1.5A2.5 2.5 0 0 1 20 10.5V21h-4z" />
        </svg>
        <span>书库</span>
      </RouterLink>
      <RouterLink
        v-if="readingTarget"
        class="mobile-tab"
        :class="{ active: readingActive }"
        :to="readingTarget"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3.5 5.5A3.5 3.5 0 0 1 7 2h5v17H7a3.5 3.5 0 0 0-3.5 3z" />
          <path d="M20.5 5.5A3.5 3.5 0 0 0 17 2h-5v17h5a3.5 3.5 0 0 1 3.5 3z" />
        </svg>
        <span>阅读</span>
      </RouterLink>
      <span v-else class="mobile-tab disabled" aria-disabled="true">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3.5 5.5A3.5 3.5 0 0 1 7 2h5v17H7a3.5 3.5 0 0 0-3.5 3z" />
          <path d="M20.5 5.5A3.5 3.5 0 0 0 17 2h-5v17h5a3.5 3.5 0 0 1 3.5 3z" />
        </svg>
        <span>阅读</span>
      </span>
    </nav>

    <div v-if="mobileChatOpen" class="mobile-scrim" @click="closeMobileChat"></div>
  </div>
</template>

<style scoped>
.app-shell {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr) 372px;
  width: 100%;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
}

.app-shell.chat-collapsed {
  grid-template-columns: 230px minmax(0, 1fr) 44px;
}

.sidebar {
  position: relative;
  z-index: 20;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 14px 12px 10px;
  border-right: 1px solid var(--border);
  background: var(--surface-2);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 2px 4px 16px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: var(--bg);
  font-family: var(--font-serif);
  font-size: 18px;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.brand-copy strong {
  font-size: 14px;
  letter-spacing: 0.04em;
}

.brand-copy small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 9.5px;
  letter-spacing: 0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.side-link {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  height: 38px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 13px;
  transition:
    background-color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.side-link svg,
.mobile-tab svg,
.chat-rail svg,
.mobile-chat-button svg {
  width: 17px;
  height: 17px;
  flex: none;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.side-link:hover:not(.disabled) {
  background: var(--surface);
  color: var(--text);
}

.side-link.active {
  border-color: var(--border);
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
}

.side-link.active::before {
  content: '';
  position: absolute;
  left: -1px;
  top: 9px;
  bottom: 9px;
  width: 2px;
  border-radius: 2px;
  background: var(--accent);
}

.side-link.disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

.side-link small {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 9.5px;
  font-weight: 400;
}

.sidebar-foot {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.app-main {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--bg);
}

.chat-column {
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border-left: 1px solid var(--border);
  background: var(--surface);
}

.chat-column > :deep(.chat-panel) {
  height: 100%;
}

.chat-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 100%;
  padding: 16px 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
}

.chat-rail:hover {
  background: var(--surface-2);
  color: var(--text);
}

.chat-rail span {
  writing-mode: vertical-rl;
  font-size: 10.5px;
  letter-spacing: 0.16em;
}

.chat-empty {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 100%;
  padding: 34px;
  text-align: center;
}

.empty-collapse {
  position: absolute;
  top: 12px;
  right: 12px;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 18px;
}

.empty-collapse:hover {
  border-color: var(--border);
  background: var(--surface-2);
  color: var(--text);
}

.empty-mark {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border: 1px dashed var(--border-strong);
  border-radius: 50%;
  color: var(--text-muted);
  font-family: var(--font-serif);
  font-size: 20px;
}

.chat-empty h2 {
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 600;
}

.chat-empty p {
  max-width: 230px;
  color: var(--text-muted);
  font-size: 11.5px;
  line-height: 1.7;
}

.mobile-nav,
.mobile-chat-button,
.mobile-scrim {
  display: none;
}

@media (max-width: 900px) {
  .app-shell,
  .app-shell.chat-collapsed {
    display: block;
    height: 100dvh;
  }

  .sidebar {
    position: fixed;
    inset: 0 0 auto;
    z-index: 70;
    flex-direction: row;
    align-items: center;
    height: 56px;
    padding: 0 14px;
    border-right: 0;
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--surface) 94%, transparent);
  }

  .sidebar-brand {
    padding: 0;
  }

  .brand-copy small {
    display: none;
  }

  .sidebar-nav {
    display: none;
  }

  .sidebar-foot {
    margin: 0 0 0 auto;
    padding: 0;
    border: 0;
  }

  .app-main {
    height: 100%;
    padding-top: 56px;
    padding-bottom: 56px;
  }

  .chat-column {
    position: fixed;
    inset: 0 0 0 auto;
    z-index: 90;
    width: min(94vw, 400px);
    border-left: 1px solid var(--border);
    box-shadow: var(--shadow-md);
    transform: translateX(102%);
    visibility: hidden;
    transition:
      transform var(--dur-slow) var(--ease-out),
      visibility var(--dur-slow) var(--ease-out);
  }

  .chat-column.mobile-open {
    transform: none;
    visibility: visible;
  }

  .chat-empty,
  .chat-rail {
    display: none;
  }

  .mobile-nav {
    position: fixed;
    inset: auto 0 0;
    z-index: 70;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    height: 56px;
    padding: 4px 10px;
    border-top: 1px solid var(--border);
    background: color-mix(in srgb, var(--surface) 96%, transparent);
  }

  .mobile-tab {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 11.5px;
  }

  .mobile-tab.active {
    background: var(--accent-soft);
    color: var(--text);
    font-weight: 600;
  }

  .mobile-tab.disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .mobile-chat-button {
    position: fixed;
    right: 14px;
    bottom: calc(56px + 12px);
    z-index: 60;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 36px;
    padding: 0 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-pill);
    background: var(--surface);
    color: var(--text-secondary);
    box-shadow: var(--shadow-sm);
    font-size: 11.5px;
  }

  .mobile-chat-button:hover {
    background: var(--surface-2);
    color: var(--text);
  }

  .mobile-scrim {
    position: fixed;
    inset: 0;
    z-index: 80;
    display: block;
    background: var(--scrim);
  }
}
</style>
