<script setup lang="ts">
/**
 * 账户菜单：活动栏底部那颗头像。点开是账户摘要 + 设置 / 退出。
 *
 * 头像用用户名首字符——没有头像素材，名字的首字是最短的识别方式。
 *
 * 浮层 **Teleport 到 body**：活动栏是 z-index 30 的层叠上下文，留在里面会被别的
 * fixed 层（抽屉、遮罩）压住。位置按头像的**视口矩形现算**，所以滚不滚都一样贴边。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { current, expiryLabel, signOut } from '../auth'

const router = useRouter()

const open = ref(false)
const anchor = ref<HTMLButtonElement | null>(null)
const pos = ref({ left: 0, bottom: 0 })

const initial = computed(() => (current.value?.username ?? '?').slice(0, 1).toUpperCase())
const username = computed(() => current.value?.username ?? '未登录')
const expiry = computed(() => expiryLabel())

function toggle(): void {
  if (!open.value && anchor.value) {
    const r = anchor.value.getBoundingClientRect()
    pos.value = {
      left: Math.round(r.right + 10),
      bottom: Math.round(window.innerHeight - r.bottom)
    }
  }
  open.value = !open.value
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) open.value = false
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

/** 设置是独立路由页（`/settings`），不是弹窗 */
function openSettings(): void {
  open.value = false
  void router.push({ name: 'settings' })
}

async function doLogout(): Promise<void> {
  open.value = false
  await signOut()
  void router.replace({ name: 'login' })
}
</script>

<template>
  <div class="acct">
    <button
      ref="anchor"
      class="acct-btn"
      :class="{ on: open }"
      :aria-expanded="open"
      aria-haspopup="menu"
      :title="username"
      @click="toggle"
    >
      <span class="tip">账户</span>
      <span class="acct-av">{{ initial }}</span>
    </button>

    <Teleport to="body">
      <div v-if="open" class="acct-scrim" @click="open = false"></div>
      <div
        v-if="open"
        class="acct-menu"
        role="menu"
        :style="{ left: pos.left + 'px', bottom: pos.bottom + 'px' }"
      >
        <div class="am-head">
          <span class="am-av">{{ initial }}</span>
          <div class="am-id">
            <p class="am-name">{{ username }}</p>
            <p class="am-sub">有效期至 {{ expiry }}</p>
          </div>
        </div>

        <button class="am-item" role="menuitem" @click="openSettings">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <path d="M4 7h9M18.5 7H20M4 17h3M12.5 17H20" />
            <circle cx="15.5" cy="7" r="2" />
            <circle cx="9.5" cy="17" r="2" />
          </svg>
          设置
        </button>

        <button class="am-item danger" role="menuitem" @click="doLogout">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <path d="M10 4H6.5A2.5 2.5 0 004 6.5v11A2.5 2.5 0 006.5 20H10" />
            <path d="M15.5 8l4 4-4 4M9.5 12h9.5" />
          </svg>
          退出登录
        </button>
      </div>
    </Teleport>
  </div>
</template>
