<script setup lang="ts">
/**
 * 设置页：独立路由（`/settings`），不进三栏壳——设置与「读哪本书、问到哪」无关，
 * 套着章节栏与问答面板只会让人以为它们跟着一起变。
 *
 * 两个 tab：账户信息（只读账户 + **会话管理**）/ 网页设置（跨会话记住的偏好，当前是主题）。
 * 删除这类不可逆的动作放在这里，而不是日常切换会话的标签页上。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppDialog from '../components/AppDialog.vue'
import { current, expiryLabel } from '../auth'
import {
  levelLabel,
  refresh as refreshSessions,
  remove as removeSession,
  rename as renameSession,
  sessions,
  sessionsError,
  shortTime
} from '../sessions'
import { THEME_NAMES, theme, themeLabel } from '../theme'
import type { ChatSessionSummary } from '../types'

const router = useRouter()
const tab = ref<'account' | 'web'>('account')
const username = computed(() => current.value?.username ?? '—')
const expiry = computed(() => expiryLabel())

/** 待确认删除的会话。删了就没了，所以先问一句 */
const pendingDelete = ref<ChatSessionSummary | null>(null)
const deleting = ref(false)

/** 行内改名：同一时刻只改一行，换一行就等于放弃上一次编辑 */
const editingId = ref<string | null>(null)
const editTitle = ref('')
const saving = ref(false)

function startEdit(session: ChatSessionSummary): void {
  editingId.value = session.id
  editTitle.value = session.title
}

function cancelEdit(): void {
  editingId.value = null
  editTitle.value = ''
}

/** 失败不关编辑器：服务端那句原因（超长 / 空）要留在眼前，否则用户不知道为什么没改上 */
async function saveRename(): Promise<void> {
  const id = editingId.value
  const title = editTitle.value.trim()
  if (id === null || saving.value || title === '') return
  saving.value = true
  try {
    if (await renameSession(id, title)) cancelEdit()
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void refreshSessions()
})

async function confirmDelete(): Promise<void> {
  const target = pendingDelete.value
  if (target === null || deleting.value) return
  deleting.value = true
  try {
    await removeSession(target.id)
  } finally {
    deleting.value = false
    pendingDelete.value = null
  }
}

/** 从哪儿来回哪儿去；直接打开这个地址时没有上一页，退回书库。 */
function back(): void {
  const prev = (window.history.state as { back?: string } | null)?.back
  if (prev) router.back()
  else void router.push({ name: 'library' })
}
</script>

<template>
  <div class="set-page">
    <header class="sp-head">
      <button class="sp-back" @click="back">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
          <path d="M13 8H3M7 4L3 8l4 4" />
        </svg>
        返回
      </button>
      <b>设置</b>
    </header>

    <div class="set-card">
      <div class="set-tabs" role="tablist">
        <button
          role="tab"
          :aria-selected="tab === 'account'"
          :class="{ on: tab === 'account' }"
          @click="tab = 'account'"
        >
          账户信息
        </button>
        <button
          role="tab"
          :aria-selected="tab === 'web'"
          :class="{ on: tab === 'web' }"
          @click="tab = 'web'"
        >
          网页设置
        </button>
      </div>

      <div v-if="tab === 'account'" class="set-body" role="tabpanel">
        <dl class="set-kv">
          <dt>用户名</dt>
          <dd>{{ username }}</dd>
          <dt>登录有效期</dt>
          <dd>{{ expiry }}</dd>
        </dl>
        <p class="set-note">
          账户由开发者发放，不开放注册。停用账户会一并清除它的登录会话、对话与阅读进度。
        </p>

        <section class="set-sessions">
          <p class="sr-t">会话</p>
          <p class="sr-d">
            切换会话在问答面板顶部的标签页里；这里改名与删除——删除不可逆，所以不放在日常路径上。
          </p>
          <div class="ss-list">
            <div v-for="session in sessions" :key="session.id" class="ss-row">
              <template v-if="editingId === session.id">
                <input
                  v-model="editTitle"
                  class="ss-input"
                  maxlength="20"
                  aria-label="新标题"
                  @keydown.enter.prevent="saveRename"
                  @keydown.esc="cancelEdit"
                />
                <button
                  class="dlg-btn primary"
                  :disabled="saving || editTitle.trim() === ''"
                  @click="saveRename"
                >
                  保存
                </button>
                <button class="dlg-btn" @click="cancelEdit">取消</button>
              </template>
              <template v-else>
                <span class="ss-title">{{ session.title }}</span>
                <span class="ss-meta">{{ levelLabel(session.level) }} · {{ shortTime(session.last_active_at) }}</span>
                <button class="dlg-btn" @click="startEdit(session)">改名</button>
                <button class="dlg-btn" @click="pendingDelete = session">删除</button>
              </template>
            </div>
            <p v-if="sessions.length === 0" class="find-none">还没有会话</p>
          </div>
          <p v-if="sessionsError" class="ss-err">{{ sessionsError }}</p>
        </section>
      </div>

      <div v-else class="set-body" role="tabpanel">
        <div class="set-row">
          <div class="sr-copy">
            <p class="sr-t">主题</p>
            <p class="sr-d">只影响功能页面；介绍页与登录页不跟随——它们是画，有自己的颜色。</p>
          </div>
          <div class="theme-pick" role="radiogroup" aria-label="主题">
            <button
              v-for="name in THEME_NAMES"
              :key="name"
              role="radio"
              :aria-checked="theme === name"
              :class="{ on: theme === name }"
              @click="theme = name"
            >
              {{ themeLabel(name) }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <AppDialog :open="pendingDelete !== null" title="删除这个会话？" @close="pendingDelete = null">
      <p>「{{ pendingDelete?.title }}」连同它的全部消息会一起删掉，删了就没了。</p>
      <template #actions>
        <button class="dlg-btn" @click="pendingDelete = null">取消</button>
        <button class="dlg-btn primary" :disabled="deleting" @click="confirmDelete">删除</button>
      </template>
    </AppDialog>
  </div>
</template>
