<script setup lang="ts">
/**
 * 设置页：独立路由（`/settings`），不进三栏壳——设置与「读哪本书、问到哪」无关，
 * 套着章节栏与问答面板只会让人以为它们跟着一起变。
 *
 * 排版是「页头 + 左栏导航卡 + 右栏内容卡」：三块各自有边界，左侧导航与右侧内容是两张卡，
 * 不是一个大盒子里切一刀。栏目只有**已经存在的**三块功能，不为了凑满导航而加空壳。
 *
 * **这一页必须自己当滚动容器**：`body` 是 `overflow: hidden`（三栏壳自己滚），
 * 独立路由页只写 `min-height` 的话，会话一多下半截既看不见也滚不到。
 *
 * 账户信息只读：账户由开发者发放，前端没有改昵称/头像的接口，所以不摆看起来能编辑的控件。
 * 删除这类不可逆的动作放在这里，而不是日常切换会话的标签页上。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppDialog from '../components/AppDialog.vue'
import { expiryFull, username } from '../auth'
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

const NAV = [
  { key: 'account', label: '账户信息', title: '账户信息', sub: '查看账户身份与当前登录状态。', icon: 'user' },
  { key: 'sessions', label: '会话管理', title: '会话管理', sub: '重命名或删除对话记录。删除不可逆。', icon: 'chat' },
  { key: 'web', label: '网页设置', title: '网页设置', sub: '只影响功能页面的外观，不改动内容。', icon: 'sliders' }
] as const

type TabKey = (typeof NAV)[number]['key']
const tab = ref<TabKey>('account')
const activeNav = computed(() => NAV.find((item) => item.key === tab.value) ?? NAV[0])

/** 头像里那个字母。账户名取不到时用问号，不编一个假名字出来 */
const initial = computed(() => (username.value || '?').slice(0, 1).toUpperCase())

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
    <div class="pc">
      <header class="sp-head">
        <span class="pc-mark">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <circle cx="12" cy="8.5" r="3.8" />
            <path d="M4.8 20.2a7.2 7.2 0 0114.4 0" />
          </svg>
        </span>
        <div class="pc-title">
          <b>个人中心</b>
          <span>PERSONAL CENTER</span>
        </div>
        <button class="sp-back" aria-label="返回" @click="back">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
          </svg>
        </button>
      </header>

      <div class="set-card">
        <aside class="set-tabs">
          <div class="pc-user">
            <span class="pc-avatar">{{ initial }}</span>
            <span class="pc-user-t">
              <b>{{ username }}</b>
              <i>个人账户</i>
            </span>
          </div>

          <nav class="pc-nav" aria-label="设置栏目">
            <button
              v-for="item in NAV"
              :key="item.key"
              :class="{ on: tab === item.key }"
              :aria-current="tab === item.key ? 'page' : undefined"
              @click="tab = item.key"
            >
              <svg v-if="item.icon === 'user'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <circle cx="12" cy="8.5" r="3.6" />
                <path d="M5.2 20a6.8 6.8 0 0113.6 0" />
              </svg>
              <svg v-else-if="item.icon === 'chat'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <path d="M3 6.5A2.5 2.5 0 015.5 4h7A2.5 2.5 0 0115 6.5v4a2.5 2.5 0 01-2.5 2.5H8l-3.5 3v-3.2A2.5 2.5 0 013 10.5z" />
                <path d="M18 9h.5A2.5 2.5 0 0121 11.5v3.6a2.5 2.5 0 01-1.6 2.3V21l-3.4-3H12" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <path d="M4 7.5h8M16.5 7.5H20M4 16.5h4M12.5 16.5H20" />
                <circle cx="14" cy="7.5" r="2.2" />
                <circle cx="10" cy="16.5" r="2.2" />
              </svg>
              <span>{{ item.label }}</span>
            </button>
          </nav>
        </aside>

        <main class="pc-main">
          <h1 class="pc-h">{{ activeNav.title }}</h1>
          <p class="pc-sub">{{ activeNav.sub }}</p>

          <section v-if="tab === 'account'" class="pc-card">
            <div class="pc-hero">
              <span class="pc-avatar big">{{ initial }}</span>
              <span class="pc-hero-t">
                <b>{{ username }}</b>
                <i>个人账户</i>
              </span>
              <span class="pc-user-time"><i>账户有效期</i>{{ expiryFull }}</span>
            </div>

            <dl class="set-kv">
              <dt>用户名</dt>
              <dd>{{ username }}</dd>
            </dl>

            <p class="pc-note">
              账户由开发者发放，不开放注册。停用账户会一并清除它的登录会话、对话与阅读进度。
            </p>
          </section>

          <section v-else-if="tab === 'sessions'" class="pc-card">
            <p class="pc-card-t">全部会话</p>
            <p class="pc-card-d">
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
                  <button class="dlg-btn danger" @click="pendingDelete = session">删除</button>
                </template>
              </div>
              <p v-if="sessions.length === 0" class="find-none">还没有会话</p>
            </div>
            <p v-if="sessionsError" class="ss-err">{{ sessionsError }}</p>
          </section>

          <section v-else class="pc-card">
            <p class="pc-card-t">主题</p>
            <p class="pc-card-d">只影响功能页面；介绍页与登录页不跟随——它们是画，有自己的颜色。</p>

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
          </section>
        </main>
      </div>
    </div>

    <AppDialog :open="pendingDelete !== null" title="是否删除该会话？" @close="pendingDelete = null">
      <p>「{{ pendingDelete?.title }}」连同它的全部消息会一起删掉，删了就没了。</p>
      <template #actions>
        <button class="dlg-btn" @click="pendingDelete = null">取消</button>
        <button class="dlg-btn danger" :disabled="deleting" @click="confirmDelete">删除</button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
/* 这一页是独立路由（不进三栏壳），样式跟着组件走——与 LibraryView / LoginView / WelcomeView 一致。
   这些规则只命中本组件模板里的元素（含传给 AppDialog 的插槽内容，插槽在父作用域里编译）。
   窄屏那条必须排在基础规则**之后**：同优先级时后写的赢。

   类名沿用旧的 `.set-*` / `.sp-*` / `.ss-*`：`temp/` 下四个 CDP 核对脚本按这些选择器取元素，
   换成一套新名字等于让它们全部静默失效。 */
.set-page {
  /* body 是 overflow:hidden，这一页必须自己滚 */
  height: 100vh;
  overflow-y: auto;
  padding: 28px 24px 56px;
}
.pc { width: min(1080px, 100%); margin: 0 auto; }

/* ---------- 页头：图标 + 中英标题 + 右侧关闭 ---------- */
.sp-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--stroke-2);
}
.pc-mark {
  width: 46px;
  height: 46px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 13px;
  background: var(--accent);
  color: var(--on-accent);
}
.pc-mark svg { width: 24px; height: 24px; }
.pc-title b { display: block; font-size: 20px; letter-spacing: 0.01em; }
.pc-title span {
  display: block;
  margin-top: 3px;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.16em;
  color: var(--ink-3);
}
.sp-back {
  margin-left: auto;
  width: 34px;
  height: 34px;
  flex: none;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
}
.sp-back:hover { color: var(--ink); border-color: var(--stroke-2); background: var(--glass-2); }
.sp-back svg { width: 17px; height: 17px; }

/* ---------- 两栏：左导航卡 + 右内容 ---------- */
.set-card {
  margin-top: 22px;
  display: grid;
  grid-template-columns: 268px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}
.set-tabs {
  padding: 14px;
  border-radius: 18px;
  border: 1px solid var(--stroke-2);
  background: var(--glass);
  backdrop-filter: blur(22px) saturate(150%);
  -webkit-backdrop-filter: blur(22px) saturate(150%);
}
.pc-user {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 6px 16px;
  border-bottom: 1px solid var(--stroke-2);
}
.pc-avatar {
  width: 42px;
  height: 42px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--accent);
  color: var(--on-accent);
  font-size: 16px;
  font-weight: 700;
}
.pc-avatar.big { width: 54px; height: 54px; font-size: 20px; }
/* 名字过长时省略，别把右边那列时间挤出去 */
.pc-user-t { flex: 1; min-width: 0; }
.pc-user-t b {
  display: block;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pc-user-t i {
  display: block;
  margin-top: 3px;
  font-style: normal;
  font-size: 11.5px;
  color: var(--ink-3);
}
/* 账户有效期：贴住头像行的右下角。前面那句说明不能省——
   单独一串数字放在这儿，看不出它是到期时间还是上次登录时间。 */
.pc-user-time {
  flex: none;
  margin-left: auto;
  align-self: flex-end;
  padding-bottom: 1px;
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  white-space: nowrap;
}
.pc-user-time i {
  font-style: normal;
  font-family: var(--sans);
  font-size: 11.5px;
  color: var(--ink-2);
}

.pc-nav { display: flex; flex-direction: column; gap: 2px; padding-top: 12px; }
.pc-nav button {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 11px 12px;
  border: 0;
  border-radius: 11px;
  background: transparent;
  font: inherit;
  font-size: 13.5px;
  color: var(--ink-2);
  text-align: left;
  cursor: pointer;
}
.pc-nav button svg { width: 17px; height: 17px; flex: none; opacity: 0.85; }
.pc-nav button:hover { background: var(--glass-2); color: var(--ink); }
.pc-nav button.on {
  color: var(--accent);
  font-weight: 600;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.pc-nav button.on svg { opacity: 1; }

/* ---------- 右栏内容 ---------- */
.pc-main { min-height: 360px; }
.pc-h { margin: 2px 0 0; font-size: 22px; font-weight: 700; }
.pc-sub { margin: 8px 0 18px; font-size: 13px; color: var(--ink-3); }
.pc-card {
  padding: 18px 20px 20px;
  border-radius: 16px;
  border: 1px solid var(--stroke-2);
  background: var(--glass-2);
}
.pc-hero {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--stroke-2);
}
.pc-hero-t b { display: block; font-size: 16px; }
.pc-hero-t i {
  display: block;
  margin-top: 4px;
  font-style: normal;
  font-size: 12px;
  color: var(--ink-3);
}
.set-kv { margin: 16px 0 0; display: grid; gap: 7px; }
.set-kv dt { margin-top: 9px; font-size: 12.5px; color: var(--ink-2); }
.set-kv dt:first-child { margin-top: 0; }
.set-kv dd {
  margin: 0;
  padding: 11px 13px;
  border-radius: 11px;
  border: 1px solid var(--stroke-2);
  background: var(--glass);
  font-size: 13px;
  color: var(--ink-2);
}
.pc-note { margin: 16px 0 0; font-size: 11.5px; line-height: 1.7; color: var(--ink-3); }
.pc-card-t { margin: 0; font-size: 13.5px; font-weight: 600; }
.pc-card-d { margin: 6px 0 0; font-size: 11.5px; line-height: 1.7; color: var(--ink-3); }

/* 会话管理 */
.ss-list { margin-top: 14px; display: grid; gap: 4px; }
.ss-row {
  display: flex; align-items: center; gap: 10px; padding: 7px 10px;
  border: 1px solid var(--stroke-2); border-radius: 10px; background: var(--glass);
}
.ss-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; }
.ss-meta { flex: none; font-size: 10.5px; color: var(--ink-3); font-family: var(--mono); }
.ss-row .dlg-btn { padding: 4px 10px; font-size: 11.5px; }
.ss-input {
  flex: 1; min-width: 0; font: inherit; font-size: 12.5px; padding: 5px 9px; outline: 0;
  border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent); border-radius: 8px;
  background: var(--glass-2); color: var(--ink);
}
.ss-err { margin: 8px 0 0; font-size: 11.5px; color: var(--danger); }

/* 网页设置 */
.theme-pick {
  display: inline-flex; gap: 4px; margin-top: 14px; padding: 3px; border-radius: 10px;
  background: var(--glass); border: 1px solid var(--stroke-2);
}
.theme-pick button {
  border: 0; background: transparent; font: inherit; font-size: 12px; color: var(--ink-2);
  padding: 6px 14px; border-radius: 7px; cursor: pointer; white-space: nowrap;
}
.theme-pick button.on { background: var(--accent); color: var(--on-accent); }

/* 窄屏：左导航卡塌到上面，导航项改横排 */
@media (max-width: 860px) {
  .set-page { padding: 20px 16px 40px; }
  .set-card { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .pc-user { padding-bottom: 12px; }
  .pc-nav { flex-direction: row; gap: 4px; padding-top: 10px; overflow-x: auto; }
  .pc-nav button { width: auto; flex: none; padding: 9px 12px; }
  .pc-main { min-height: 0; }
}
</style>
