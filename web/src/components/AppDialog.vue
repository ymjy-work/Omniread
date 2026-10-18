<script setup lang="ts">
/**
 * 通用弹窗。**所有模态都走它**——遮罩、层级、Esc、焦点这四件事只写一份。
 *
 * 三件必须做对的：
 * - **Teleport 到 body**：面板带 `backdrop-filter`，会给 fixed 后代另立包含块，
 *   留在面板里的「全屏」遮罩其实只盖住面板那一块。
 * - **Esc 与点遮罩关闭**；`dismissible=false` 时两者都不响应（必须明确选一个的场合）。
 * - **焦点进弹窗、Tab 不出圈**：`aria-modal` 声明它是模态，焦点就该留在里面——
 *   否则键盘用户会操作到被遮罩盖住的背景控件上。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{ open: boolean; title?: string; width?: number; dismissible?: boolean }>(),
  { title: '', width: 380, dismissible: true }
)
const emit = defineEmits<{ close: [] }>()

const card = ref<HTMLElement | null>(null)

function requestClose(): void {
  if (props.dismissible) emit('close')
}

function focusables(): HTMLElement[] {
  if (card.value === null) return []
  return [...card.value.querySelectorAll<HTMLElement>(
    'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])'
  )].filter((el) => !el.hasAttribute('disabled'))
}

function onKey(event: KeyboardEvent): void {
  if (!props.open) return
  if (event.key === 'Escape') {
    requestClose()
    return
  }
  if (event.key !== 'Tab') return
  const list = focusables()
  if (list.length === 0) {
    event.preventDefault()
    card.value?.focus()
    return
  }
  const first = list[0]
  const last = list[list.length - 1]
  const active = document.activeElement
  if (event.shiftKey && (active === first || active === card.value)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    await nextTick()
    // 打开时把焦点送进弹窗；一个可聚焦元素都没有就落在卡片本身（`tabindex="-1"`）
    ;(focusables()[0] ?? card.value)?.focus()
  },
  { immediate: true }
)
</script>

<template>
  <Teleport to="body">
    <Transition name="dlg-fade">
      <div v-if="open" class="dlg-mask" @click.self="requestClose">
        <div
          ref="card"
          class="dlg-card"
          role="dialog"
          aria-modal="true"
          :aria-label="title || undefined"
          tabindex="-1"
          :style="{ width: `min(${width}px, 100%)` }"
        >
          <p v-if="title" class="dlg-title">{{ title }}</p>
          <div class="dlg-body"><slot /></div>
          <div v-if="$slots.actions" class="dlg-actions"><slot name="actions" /></div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
