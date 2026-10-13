<script setup lang="ts">
/**
 * 逐字打出来的标题（复刻官网 hero 副标题那个打字机）：
 * 一个字一个 `<span>`，打到的加 `is-typed`，后面跟一个闪烁光标，打完光标淡出。
 *
 * 两个刻意的取舍：
 *
 * - **触发是「滚进视口」，不是加载**。这些标题都在首屏下面，加载时就打完等于没打。
 * - **`prefers-reduced-motion` 下直接给全文**：打字是装饰不是内容，
 *   减少动效时不该让人等它一个字一个字出来（同应用里等待行的处理）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{ text: string; speed?: number }>(), { speed: 80 })

const chars = computed(() => [...props.text])
const typed = ref(0)
const root = ref<HTMLElement | null>(null)
let timer: number | undefined
let observer: IntersectionObserver | null = null

function clearTimers(): void {
  if (timer !== undefined) window.clearInterval(timer)
  timer = undefined
}

function type(): void {
  if (timer !== undefined) return
  timer = window.setInterval(() => {
    typed.value += 1
    if (typed.value >= chars.value.length) {
      window.clearInterval(timer)
      timer = undefined
    }
  }, props.speed)
}

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    typed.value = chars.value.length
    return
  }
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer?.disconnect()
        observer = null
        type()
      }
    },
    { threshold: 0.4 }
  )
  if (root.value) observer.observe(root.value)
})

onBeforeUnmount(() => {
  clearTimers()
  observer?.disconnect()
})
</script>

<template>
  <span ref="root" class="tw">
    <!-- 逐字：打到的显示，没打到的**不占位**（`display: none`）——这样光标才跟着字走。
         光标紧跟在最后一个打出的字后面，打完就留在末尾一直闪（同输入框那个）。 -->
    <span
      v-for="(char, i) in chars"
      :key="i"
      class="char"
      :class="{ 'is-typed': i < typed }"
      >{{ char }}</span
    ><span class="caret" aria-hidden="true"></span>
  </span>
</template>

<style scoped>
.tw { display: inline; }
/* 未打出的字**不占位**：占位的话光标一上来就贴在整行末尾，而不是跟着字走（踩过） */
.char { display: none; }
.char.is-typed { display: inline; }
/* 光标紧跟在最后一个打出的字后面；打完就留在末尾**一直闪**——
   节奏与 hero 输入框那个光标对齐（1.1s steps(1)） */
.caret {
  display: inline-block;
  width: 3px;
  height: 1.05em;
  margin-left: 3px;
  background: currentColor;
  vertical-align: -0.18em;
  animation: tw-caret 1.1s steps(1) infinite;
}
@keyframes tw-caret { 50% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) {
  /* 减少动效时整段直接给完（打字本身也停了，见脚本），光标也就不用闪了 */
  .caret { display: none; }
}
</style>
