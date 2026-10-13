<script setup lang="ts">
/**
 * 门厅那一屏的背景（介绍页与登录页**共用这一份**，别再抄第二遍）：程序化画布
 * （`heroPainting.ts`）+ 两种可选的动态层。
 *
 * 三个开关（默认值是介绍页那一套）：
 *
 * - `veil`（默认 true）：**拨雾**——一层可以用指针拨开的雾，介绍页的签名交互。
 * - `meteors`（默认 false）：**会动的流星**——独立的逐帧层，登录页用。
 *   开它的时候底画不再画静态流星（两套同时出现像在下雨）。
 * - `comet`（默认 false）：**指针流星**——鼠标自己拖一条会滑动、停手会散掉的星尾。
 *   与拨雾互不相干，两页各取一样。
 *
 * 三条不能省的（每一处配着 `heroPainting.ts` 里的说明看）：
 *
 * - **没有 hover、或开了减少动效，整层遮罩不显示**：那种情况下指针不生成墨点、循环也不跑，
 *   遮罩会铺死在那儿，主视觉永久看不见。
 * - **遮罩层用 `v-show` 不用 `v-if`**：`v-if` 时它在 mount 那一刻还不在 DOM 里，
 *   取到的 ref 是 null，「要不要显示」永远算不出来（踩过）。流星层反过来——它在模板里是
 *   静态的（`veil` / `meteors` / `comet` 三个 prop 各页固定），`v-if` 才安全。
 * - **指针事件挂在根元素上**（画布是 `pointer-events: none`）：内容由 slot 盖在画之上，
 *   挂画布上的话指针一进内容就拨不动了。
 *
 * 减少动效时的退路：流星不逐帧画，退回底画里那些静态流星——画面照样有流星，
 * 只是不动。这是「减少动效」该有的样子，不是把它删掉。
 *
 * 尺寸与留白（多高、怎么摆内容）是**页面自己的事**：本组件只管铺满宿主，
 * 所以外面用 class 传进来（`<HeroBackdrop class="hero">`）。
 */
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  createCometField,
  createMeteorField,
  createReveal,
  paintHero,
  type CometField,
  type MeteorField,
  type RevealController
} from '../heroPainting'

const props = withDefaults(
  defineProps<{ veil?: boolean; meteors?: boolean; comet?: boolean }>(),
  { veil: true, meteors: false, comet: false }
)

/** 减少动效：逐帧的东西一个都不起。触屏没有 hover，指针那两样也不起。 */
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const hoverable = window.matchMedia('(hover: hover)').matches
/** 各动态层要不要出现（模板里是静态判定，mount 时 ref 一定拿得到） */
const meteorLayer = props.meteors && !reducedMotion
const cometLayer = props.comet && hoverable && !reducedMotion

const host = ref<HTMLElement | null>(null)
const painting = ref<HTMLCanvasElement | null>(null)
// **ref 名不能与 prop 同名**（`veil` / `meteors` / `comet` 是 prop，这里是画布本身）：
// 同名时 `vue/no-dupe-keys` 报重名，而模板里 `ref="veil"` 指向的到底是哪一个也说不清
const veilCanvas = ref<HTMLCanvasElement | null>(null)
const meteorCanvas = ref<HTMLCanvasElement | null>(null)
const cometCanvas = ref<HTMLCanvasElement | null>(null)
const revealable = ref(false)
let revealCtl: RevealController | null = null
let meteorCtl: MeteorField | null = null
let cometCtl: CometField | null = null
let observer: ResizeObserver | null = null

onMounted(() => {
  const canvas = painting.value
  const veilEl = veilCanvas.value
  const meteorEl = meteorCanvas.value
  const cometEl = cometCanvas.value
  const el = host.value
  if (!canvas || !veilEl || !el) return

  const draw = (): void => {
    const width = canvas.clientWidth
    const height = canvas.clientHeight
    if (width <= 0 || height <= 0) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = Math.round(width * dpr)
    canvas.height = Math.round(height * dpr)
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    // 画布坐标由 dpr 缩放接管，所以画的时候按 CSS 像素算。
    // 有流星层时底画不画静态流星——会动的那些由 createMeteorField 负责
    paintHero(canvas, { width, height, meteors: !meteorLayer })
    revealCtl?.resize()
    meteorCtl?.resize()
    cometCtl?.resize()
  }

  if (meteorEl !== null && meteorLayer) {
    meteorCtl = createMeteorField(meteorEl)
    meteorCtl.start()
  }
  if (cometEl !== null && cometLayer) {
    cometCtl = createCometField(cometEl)
  }

  revealable.value = props.veil && hoverable && !reducedMotion

  draw()
  observer = new ResizeObserver(draw)
  observer.observe(canvas)

  if (revealable.value) {
    revealCtl = createReveal(veilEl)
    // 等 DOM 把遮罩层显示出来再量尺寸——这一刻它还是 display:none，量到的是 0
    void nextTick(draw)
  }

  // 指针事件挂在**根元素**上：内容（slot）盖在画之上，挂画布上的话指针一进内容就断了
  if (revealCtl === null && cometCtl === null) return
  const onMove = (event: PointerEvent): void => {
    const rect = el.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    revealCtl?.move(x, y)
    cometCtl?.move(x, y)
  }
  // 指针回到这一屏时忘掉上一个位置：不然从另一侧进来会拉一道横穿画面的长痕
  const onEnter = (): void => revealCtl?.enter()
  // 指针离开窗口：星尾原地散掉，别挂在边上
  const onLeave = (): void => cometCtl?.leave()
  el.addEventListener('pointermove', onMove)
  el.addEventListener('pointerenter', onEnter)
  el.addEventListener('pointerleave', onLeave)
  onBeforeUnmount(() => {
    el.removeEventListener('pointermove', onMove)
    el.removeEventListener('pointerenter', onEnter)
    el.removeEventListener('pointerleave', onLeave)
  })
})

onBeforeUnmount(() => {
  observer?.disconnect()
  revealCtl?.stop()
  meteorCtl?.stop()
  cometCtl?.stop()
})
</script>

<template>
  <div ref="host" class="backdrop">
    <canvas ref="painting" data-layer="painting" class="scene" aria-hidden="true"></canvas>
    <!-- 流星层与遮罩层在**内容之下**：它们是「画」的一部分，毛玻璃面板正是要透出它们 -->
    <canvas
      v-if="meteorLayer"
      ref="meteorCanvas"
      data-layer="meteor"
      class="scene"
      aria-hidden="true"
    ></canvas>
    <canvas
      v-show="veil && revealable"
      ref="veilCanvas"
      data-layer="veil"
      class="scene veil"
      aria-hidden="true"
    ></canvas>
    <slot />
    <!-- 指针星尾在**内容之上**：它是「光标效果」，跟着鼠标走。
         画在内容下面时，毛玻璃面板的半透底 + 背景模糊会把它糊成一团灰 —— 看起来就是
         「鼠标效果在表单上没了」。所以这一层要压过面板（z-index），并且不吃指针事件。 -->
    <canvas
      v-if="cometLayer"
      ref="cometCanvas"
      data-layer="comet"
      class="scene scene-top"
      aria-hidden="true"
    ></canvas>
  </div>
</template>

<style scoped>
.backdrop {
  position: relative;
  overflow: hidden;
  /* 隔离出一个层叠上下文：画布与雾的混合不外溢（官网也给 hero 加了 isolate） */
  isolation: isolate;
}
.scene { position: absolute; inset: 0; width: 100%; height: 100%; }
/* 遮罩层不吃指针事件：指针事件挂在根元素上（见脚本里的注释）。
   v-show 藏起来时它是 display:none，量出来尺寸为 0，那一支自然什么都不画。 */
.veil { pointer-events: none; }
/* 盖在内容之上的一层（指针星尾）：z-index 要压过内容里那些 relative 定位的面板。
   **必须 pointer-events: none** —— 否则表单、按钮全点不动。 */
.scene-top { z-index: 3; pointer-events: none; }
</style>
