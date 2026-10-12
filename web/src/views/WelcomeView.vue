<script setup lang="ts">
/**
 * 登录前的介绍 / 导航页（门厅）。回答三件事：这是什么、边界在哪儿、能做什么。
 *
 * **它不进三栏壳**（`main.ts` 里标了 `meta.shell = false`）：门厅里摆一组指向应用的按钮、
 * 却哪儿也去不了，比没有这组按钮更糟。
 *
 * **一条内容红线**：这页一个字的原著正文都不能有——「静态资源里不得含语料文本」是部署验收里
 * 要 grep 的项。所以只有章节编号、界面文案、以及 mock 面板里那些假的数据条。
 *
 * **使用须知不在这里**：它是登录进入功能页之后的弹窗（`NoticeGate`），不参与站点设计。
 *
 * 配色是这一页**自带的深墨青**，不跟随应用的深浅主题：门厅是一张画，画有它自己的颜色。
 * 应用内部的 `--accent`（蓝紫）没动。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createReveal, paintHero, type RevealController } from '../heroPainting'
import { store } from '../store'

const router = useRouter()

/** 第 1 卷 11 章（`deploy-plan` D8/D9，门禁 G1 核对的也是这一段），与 Java 侧阅读范围同一口径。 */
const READABLE_CHAPTERS = 11
/** 全书章数：优先取书库接口（已登录时 `store` 里就有），没有就用常量兜底——这页不登录也能看。 */
const FALLBACK_CHAPTERS = 193

const total = computed(() => store.books[0]?.chapter_count ?? FALLBACK_CHAPTERS)
const readRatio = computed(() => `${((READABLE_CHAPTERS / total.value) * 100).toFixed(1)}%`)
const rest = computed(() => Math.max(total.value - READABLE_CHAPTERS, 0))

const heroRef = ref<HTMLElement | null>(null)
const painting = ref<HTMLCanvasElement | null>(null)
const veil = ref<HTMLCanvasElement | null>(null)
/** 能不能拨雾：触屏没有 hover、减少动效时也不该动。false 时**整层遮罩不显示**。 */
const revealable = ref(false)
let revealCtl: RevealController | null = null
let observer: ResizeObserver | null = null

onMounted(() => {
  const canvas = painting.value
  const veilCanvas = veil.value
  if (!canvas || !veilCanvas) return

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
    // 画布坐标由 dpr 缩放接管，所以画的时候按 CSS 像素算
    paintHero(canvas, { width, height })
    revealCtl?.resize()
  }

  // **没有 hover、或者开了减少动效，就整层遮罩都不显示**：那种情况下指针不会生成墨点、
  // 循环也不跑，遮罩会被铺死在那儿——主视觉永久看不见。这是技能里记着的一个真实 blocking。
  // 遮罩层用 `v-show` 而不是 `v-if`：`v-if` 时它在 mount 这一刻还不在 DOM 里，
  // 上面那个 ref 就是 null，于是「要不要显示」永远算不出来（踩过）。
  revealable.value =
    window.matchMedia('(hover: hover)').matches &&
    !window.matchMedia('(prefers-reduced-motion: reduce)').matches

  draw()
  observer = new ResizeObserver(draw)
  observer.observe(canvas)

  if (!revealable.value) return
  revealCtl = createReveal(veilCanvas)
  // 等 DOM 把遮罩层显示出来再量尺寸——这一刻它还是 display:none，量到的是 0
  void nextTick(draw)

  // 指针事件挂在**整块首屏**上（那块画布是 `pointer-events: none`）：内容盖在画布之上，
  // 挂画布上的话指针一进标题就拨不动了——而人正是往中间划的。
  const hero = heroRef.value
  if (!hero) return
  const onMove = (event: PointerEvent): void => {
    const rect = veilCanvas.getBoundingClientRect()
    revealCtl?.move(event.clientX - rect.left, event.clientY - rect.top)
  }
  hero.addEventListener('pointermove', onMove)
  onBeforeUnmount(() => hero.removeEventListener('pointermove', onMove))
})

onBeforeUnmount(() => {
  observer?.disconnect()
  revealCtl?.stop()
})

function enter(): void {
  void router.push({ name: 'library' })
}

function toSection(id: string): void {
  // **这里要自己看媒体查询**：`scrollIntoView({behavior})` 的优先级高于 CSS 的
  // `scroll-behavior`，写死 'smooth' 会把 reduced-motion 那一段绕过去。
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document.getElementById(id)?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
}
</script>

<template>
  <div class="welcome">
    <!-- ── 顶栏：只有产品名与三个去向 ── -->
    <header class="topbar">
      <span class="mark">OMNIREAD</span>
      <nav>
        <button class="link" @click="toSection('boundary')">不剧透</button>
        <button class="link" @click="toSection('features')">会什么</button>
        <button class="link enter" @click="enter">开始阅读 ↗</button>
      </nav>
    </header>

    <!-- ── 一、首屏 ── -->
    <section ref="heroRef" class="hero">
      <canvas ref="painting" class="scene" aria-hidden="true"></canvas>
      <canvas v-show="revealable" ref="veil" class="scene veil" aria-hidden="true"></canvas>

      <div class="hero-inner">
        <p class="eyebrow">OMNIREAD · 陪你读，也陪你聊</p>
        <!-- 拆成两组：窄屏只允许在逗号之后断行。
             每个词各是一个 inline-block 遮罩，**词与词之间本来就能断**——不管的话
             手机上会断成「问 / 整本书」，把动词和它的宾语劈开。 -->
        <h1>
          <span class="line"
            ><span class="mask"><i class="word" style="--i: 0">读</i></span
            ><span class="mask"><i class="word em" style="--i: 1">第一卷</i></span
            ><span class="mask"><i class="word" style="--i: 2">，</i></span></span
          ><span class="line"
            ><span class="mask"><i class="word" style="--i: 3">问</i></span
            ><span class="mask"><i class="word em" style="--i: 4">整本书</i></span></span
          >
        </h1>
        <p class="roman">AN AI THAT READS ALONG</p>
        <p class="work">《不时轻声地以俄语遮羞的邻座艾莉同学》</p>
        <p class="sub">
          读到哪问到哪。它按你读到的位置作答、<b>不剧透</b>；
          答案里 <span class="cite">[C3]</span> 这样的角标点开就跳到那一章。
        </p>

        <!-- 三种读者处境排成一行标签：散文写进副文案会把三行标题下面压成一块砖 -->
        <p class="crowd">
          <span class="lead">如果你</span>
          <span class="pill">读不进去</span>
          <span class="pill">追到一半弃了</span>
          <span class="pill">只想看某个人的戏</span>
        </p>

        <!-- 输入框是个 mock：它展示这个站点做什么，点了会说明要登录（登录表单是 F1） -->
        <button class="askbox" @click="enter">
          <span class="caret">&gt;</span>
          <span class="placeholder">就这本书提问…</span>
          <span class="block"></span>
          <span class="go">登录后可用</span>
        </button>

        <div class="actions">
          <button class="cta" @click="enter">开始阅读</button>
          <button class="quiet" @click="toSection('features')">它能做什么</button>
        </div>
      </div>

      <div class="hero-foot">
        <span v-if="revealable" class="hint">移动指针可以拨开雾</span>
        <button class="down" @click="toSection('boundary')">向下 ↓</button>
      </div>
    </section>

    <!-- ── 二、补全前情 ── -->
    <section id="boundary" class="band">
      <div class="inner">
        <p class="eyebrow">补全前情</p>
        <h2>落下的，问回来</h2>
        <p class="sub">
          阅读页只放第 1 卷这 {{ READABLE_CHAPTERS }} 章；前情、人物关系、
          某件事发生在哪一章——直接问，它会告诉你出自哪一段。
        </p>

        <div class="spine" :style="{ '--read': readRatio, '--total': total }">
          <span class="spine-lit"></span>
          <span class="spine-edge"></span>
        </div>
        <div class="legend">
          <span class="k lit">第 1 卷 · {{ READABLE_CHAPTERS }} 章</span>
          <span class="dim">可以读</span>
          <span class="k rest">其余 {{ rest }} 章</span>
          <span class="dim">可以问</span>
        </div>

        <ul class="points">
          <!-- 这一段是对读者的承诺，**不是对实现的描述**：不许出现 403 / 装配集 / 检索增强这类词。
               里面的行为（按进度作答、角标跳章、多轮、切档位）后端都已实现（C2/C4/D1/D3b），
               但 E2（阅读范围）与 F2/F3（前端接线）**还没做**，部署前必须落地，否则这页在说假话。 -->
          <li><span class="n">01</span><b>读</b><span>第 1 卷的正文、插图、上下章。读到哪记到哪，换台设备接着读。</span></li>
          <li><span class="n">02</span><b>问</b><span>问整本书也行——想稳妥就切回顾档，它只按你读到的位置回答。</span></li>
          <li>
            <span class="n">03</span><b>核</b>
            <span>角标点开跳到那一章：第 1 卷里当场读原文，卷外也告诉你它出自哪。<b>不用信它，去看</b>。</span>
          </li>
        </ul>
      </div>
    </section>

    <!-- ── 三、功能：左文右图 / 左图右文交替 ── -->
    <section id="features" class="band features">
      <div class="inner">
        <p class="eyebrow">会什么</p>
        <h2>读小说时会想要的四件事</h2>

        <div class="feature">
          <div class="copy">
            <h3>读到哪，问到哪<span class="bar">|</span></h3>
            <p>阅读页右边常驻问答：不用离开正文、不用复制粘贴。接着问「她」「那件事」，它知道你在说谁。</p>
          </div>
          <div class="panel" aria-hidden="true">
            <div class="chrome"><i></i><i></i><i></i><span class="who">全书第 3 章 · 第 1 卷</span></div>
            <div class="doc">
              <span class="l w92"></span><span class="l w86"></span><span class="l w95"></span>
              <span class="l w70"></span>
              <span class="fig"></span>
              <span class="l w88"></span><span class="l w60"></span>
            </div>
            <div class="foot"><span>上一章</span><span class="prog"><i></i></span><span>下一章</span></div>
          </div>
        </div>

        <div class="feature flip">
          <div class="copy">
            <h3>前情，一句话问清<span class="bar">|</span></h3>
            <p>人物谁是谁、之前发生过什么——按原文答，每句都带角标；答不上来就直说，不编。</p>
          </div>
          <div class="panel" aria-hidden="true">
            <div class="chrome"><i></i><i></i><i></i><span class="who">剧情问答 · 全书</span></div>
            <div class="chat">
              <span class="bubble user">她后来怎么样了？</span>
              <span class="bubble ai">
                她回到了原来的地方，之后又离开了一次<span class="cite">[C17]</span>，
                同一条线在更早的一章里也提过一次<span class="cite">[C9]</span>。
              </span>
              <span class="meta">引用 2 处 · 都能点开</span>
            </div>
          </div>
        </div>

        <div class="feature">
          <div class="copy">
            <h3>只想看某个人<span class="bar">|</span></h3>
            <p>「她都在哪几章出场？」逐条指给你，每条都能点开原文——只挑她的部分看。</p>
          </div>
          <div class="panel" aria-hidden="true">
            <div class="chrome"><i></i><i></i><i></i><span class="who">她都在哪几章出场</span></div>
            <div class="rows">
              <span class="row on"><b>全书第 9 章</b><i>出场</i></span>
              <span class="row"><b>全书第 17 章</b><i>出场</i></span>
              <span class="row"><b>全书第 31 章</b><i>出场</i></span>
            </div>
          </div>
        </div>

        <div class="feature flip">
          <div class="copy">
            <h3>怕剧透，有档位<span class="bar">|</span></h3>
            <p><b>回顾档</b>只按你读到的位置答；想聊后面的剧情就换一档、另开一条线，原来那条不动。</p>
          </div>
          <div class="panel" aria-hidden="true">
            <div class="chrome"><i></i><i></i><i></i><span class="who">换个档位，另开一条</span></div>
            <div class="tree">
              <span class="node root">正在聊的这一条<span class="tag">回顾</span></span>
              <span class="branch"></span>
              <span class="node branched"><b>另开一条</b><span class="tag cy">剧透</span><i>从这里接着聊</i></span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── 四、收尾 ── -->
    <footer class="outro">
      <p class="eyebrow">开始</p>
      <h2>读一卷，问全书</h2>
      <p class="sub center">不要求你从头读完——想读就读，想问就问。</p>
      <div class="actions center">
        <button class="cta" @click="enter">开始阅读</button>
      </div>
      <p class="sign">Omniread · 个人学习与技术演示项目 · 第 1 卷可以读 · 整本书可以问</p>
    </footer>
  </div>
</template>

<style scoped>
/* ============================================================================
   门厅自己的配色：**深墨冷底 + 单一青色强调**。青色只用在「信号」上——
   强调词、刻度亮段、角标、边框高光。其余全是墨与灰。
   这一页不跟随应用的深浅主题：它是一张画，画有它自己的颜色。
   ========================================================================== */
.welcome {
  --cy: #34e0d0;
  --cy-dim: #5ed6ca; /* mono 那几行也是要读的，别用真·暗档 */
  --fg: #f2fbfa;
  /* 次级色比应用那套亮一点：这一页的底是**深雾 + 发光的夜空**，
     沿用 --ink-2 / --ink-3 那两档亮度，mono 小字在雾上读不出来。 */
  --fg-2: #c8dedc;
  --fg-3: #9fb7b7;
  --line: rgba(120, 200, 200, 0.14);
  --panel: rgba(8, 22, 26, 0.72);

  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
  background: #03090b;
  color: var(--fg);
}

h1, h2, h3 { margin: 0; font-weight: 800; }
b { color: var(--fg); }

/* ---------- 顶栏 ---------- */
.topbar {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 28px;
  backdrop-filter: blur(10px);
  background: linear-gradient(rgba(3, 9, 11, 0.72), rgba(3, 9, 11, 0));
}
.topbar .mark {
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.34em;
  color: var(--fg);
}
.topbar nav { display: flex; gap: 6px; align-items: center; }
.link {
  font: inherit;
  font-size: 13px;
  color: var(--fg-2);
  background: transparent;
  border: 0;
  padding: 7px 12px;
  border-radius: 9px;
  cursor: pointer;
  transition: color 0.18s, background 0.18s;
}
.link:hover { color: var(--fg); background: rgba(255, 255, 255, 0.05); }
.link.enter { color: var(--cy); border: 1px solid color-mix(in srgb, var(--cy) 34%, transparent); }

/* ---------- 首屏 ---------- */
.hero {
  position: relative;
  min-height: 100vh;
  min-height: 100svh;
  display: grid;
  place-items: center;
  padding: 96px 24px 96px;
  overflow: hidden;
}
.scene { position: absolute; inset: 0; width: 100%; height: 100%; }
/* 遮罩层不吃指针事件：指针事件挂在整块首屏上（见脚本里的注释）。
   v-show 藏起来时它是 display:none，量出来尺寸为 0，那一支自然什么都不画。 */
.veil { pointer-events: none; }
.hero-inner { position: relative; width: min(1000px, 100%); }

.eyebrow {
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.22em;
  color: var(--fg-3);
  margin: 0;
}
.hero h1 {
  margin: 20px 0 0;
  font-family: var(--serif);
  font-size: clamp(44px, 7.6vw, 108px);
  line-height: 1.06;
  letter-spacing: -0.01em;
  font-weight: 700;
  text-shadow: 0 3px 30px rgba(0, 0, 0, 0.75); /* 文字压在画上，没有这层投影会被亮部吃掉 */
}
.hero h1 .line { display: inline-block; white-space: nowrap; }
.hero h1 .mask { display: inline-block; overflow: hidden; padding-bottom: 0.1em; vertical-align: bottom; }
.hero h1 .word {
  display: inline-block;
  font-style: normal;
  animation: rise 1s cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: calc(var(--i) * 110ms);
}
.hero h1 .em { color: var(--cy); }
@keyframes rise {
  from { transform: translateY(110%); opacity: 0.15; }
  to { transform: none; opacity: 1; }
}
.roman {
  margin: 16px 0 0;
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.3em;
  color: var(--cy-dim);
}
.work {
  margin: 22px 0 0;
  font-family: var(--serif);
  font-size: 17px;
  color: var(--fg-2);
}
.sub {
  margin: 10px 0 0;
  max-width: 34em;
  font-size: 15px;
  line-height: 1.95;
  color: var(--fg-2);
  text-wrap: pretty;
}
.cite {
  font-family: var(--mono);
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 6px;
  color: var(--cy);
  background: color-mix(in srgb, var(--cy) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--cy) 32%, transparent);
}

/* 「如果你……」那一行：**不是按钮**，所以不做成 CTA 的样式，只做出一行的节奏 */
.crowd { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin-top: 20px; }
.crowd .lead { font-family: var(--mono); font-size: 11.5px; letter-spacing: 0.14em; color: var(--fg-3); }
.crowd .pill {
  font-size: 12.5px;
  padding: 3px 11px;
  border-radius: 999px;
  border: 1px solid var(--line);
  color: var(--fg-2);
  background: rgba(255, 255, 255, 0.035);
}

/* 输入框的 mock：它长得像这个站点真正的那一个（等登录后就是真的了） */
.askbox {
  margin-top: 30px;
  display: flex;
  align-items: center;
  gap: 10px;
  width: min(560px, 100%);
  padding: 13px 16px;
  font: inherit;
  font-family: var(--mono);
  font-size: 13px;
  text-align: left;
  color: var(--fg-3);
  background: rgba(8, 22, 26, 0.66);
  border: 1px solid var(--line);
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 0.18s, background 0.18s;
}
.askbox:hover { border-color: color-mix(in srgb, var(--cy) 40%, transparent); background: rgba(10, 28, 33, 0.8); }
.askbox .caret { color: var(--cy); }
.askbox .placeholder { flex: 1; }
.askbox .block { width: 7px; height: 15px; background: var(--cy); opacity: 0.75; animation: blink 1.1s steps(1) infinite; }
.askbox .go { color: var(--fg-3); font-size: 11px; }
@keyframes blink { 50% { opacity: 0; } }

.actions { display: flex; gap: 12px; align-items: center; margin-top: 26px; flex-wrap: wrap; }
.actions.center { justify-content: center; }
.cta, .quiet {
  font: inherit;
  font-size: 14px;
  padding: 12px 24px;
  border-radius: 999px;
  cursor: pointer;
  transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.18s, border-color 0.18s;
}
.cta {
  border: 1px solid color-mix(in srgb, var(--cy) 46%, transparent);
  color: #032023;
  background: linear-gradient(135deg, #5cf0e0, #2ec9be);
  box-shadow: 0 16px 40px -18px rgba(52, 224, 208, 0.8);
  font-weight: 600;
}
.quiet { border: 1px solid var(--line); background: rgba(255, 255, 255, 0.03); color: var(--fg-2); }
.cta:hover, .quiet:hover { transform: translateY(-2px); }
.quiet:hover { color: var(--fg); border-color: color-mix(in srgb, var(--cy) 34%, transparent); }

.hero-foot {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 26px;
  display: flex;
  justify-content: center;
  gap: 26px;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.2em;
  color: var(--fg-3);
}
.hero-foot .down { font: inherit; background: transparent; border: 0; color: inherit; cursor: pointer; }
.hero-foot .down:hover { color: var(--cy); }

/* ---------- 通用版心 ---------- */
.band { padding: 110px 28px; border-top: 1px solid var(--line); }
.inner { width: min(1080px, 100%); margin: 0 auto; }
.band h2 {
  margin-top: 14px;
  font-family: var(--serif);
  font-size: clamp(28px, 4.4vw, 56px);
  line-height: 1.14;
  letter-spacing: -0.01em;
}

/* ---------- 边界：书脊刻度（每一格真的是 `100% / --total`） ---------- */
.spine {
  position: relative;
  height: 76px;
  margin: 46px 0 16px;
  border-radius: 10px;
  overflow: hidden;
  color: rgba(160, 220, 220, 0.42);
  background-color: rgba(255, 255, 255, 0.03);
  background-image: linear-gradient(90deg, currentColor 0 1px, transparent 1px);
  background-repeat: repeat-x;
  background-size: calc(100% / var(--total, 193)) 100%;
}
.spine-lit {
  position: absolute;
  inset: 0 auto 0 0;
  width: var(--read, 6%);
  min-width: 8px;
  color: var(--cy);
  background-color: color-mix(in srgb, var(--cy) 16%, transparent);
  background-image: linear-gradient(90deg, currentColor 0 1px, transparent 1px);
  background-repeat: repeat-x;
  background-size: calc(100% / var(--total, 193)) 100%;
}
.spine-edge {
  position: absolute;
  inset: 0 auto 0 var(--read, 6%);
  width: 2px;
  background: var(--cy);
  box-shadow: 0 0 18px 2px color-mix(in srgb, var(--cy) 55%, transparent);
}
.legend { display: flex; gap: 10px; flex-wrap: wrap; align-items: baseline; font-size: 12px; }
.legend .k { font-family: var(--mono); letter-spacing: 0.04em; }
.legend .k.lit { color: var(--cy); }
.legend .k.rest { color: var(--fg-3); margin-left: 20px; }
.legend .dim { color: var(--fg-3); }

.points { list-style: none; margin: 46px 0 0; padding: 0; display: grid; gap: 2px; }
.points li {
  display: grid;
  grid-template-columns: 44px 28px 1fr;
  gap: 10px;
  align-items: baseline;
  padding: 16px 4px;
  border-top: 1px solid var(--line);
  font-size: 14px;
  line-height: 1.8;
  color: var(--fg-2);
}
.points li:last-child { border-bottom: 1px solid var(--line); }
.points .n { font-family: var(--mono); font-size: 11px; color: var(--fg-3); letter-spacing: 0.1em; }
.points b { font-size: 16px; color: var(--cy); }

/* ---------- 功能：左文右图 / 左图右文 ---------- */
.features h2 { margin-bottom: 56px; }
.feature {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
  gap: 38px;
  align-items: center;
  padding: 34px 0;
  border-top: 1px solid var(--line);
}
.feature.flip .copy { order: 2; }
.feature .copy h3 {
  font-family: var(--sans);
  font-size: 20px;
  letter-spacing: -0.01em;
  color: var(--fg);
}
.feature .copy h3 .bar { color: var(--cy); margin-left: 4px; font-weight: 400; }
.feature .copy p { margin: 12px 0 0; font-size: 14px; line-height: 1.9; color: var(--fg-2); text-wrap: pretty; }

/* 面板：界面是**画出来的**（没有图片素材），只用线、块与色 */
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 30px 70px -40px rgba(0, 0, 0, 0.9), inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.chrome { display: flex; align-items: center; gap: 6px; padding: 10px 13px; border-bottom: 1px solid var(--line); }
.chrome i { width: 8px; height: 8px; border-radius: 50%; background: rgba(160, 200, 200, 0.25); }
.chrome .who { margin-left: 10px; font-family: var(--mono); font-size: 11px; color: var(--fg-3); letter-spacing: 0.06em; }

.doc { display: grid; gap: 9px; padding: 18px 16px; }
.doc .l { height: 9px; border-radius: 5px; background: linear-gradient(90deg, rgba(190, 240, 235, 0.22), rgba(190, 240, 235, 0.08)); }
.doc .fig { height: 74px; border-radius: 8px; background: repeating-linear-gradient(135deg, rgba(52, 224, 208, 0.14) 0 8px, rgba(52, 224, 208, 0.04) 8px 16px); }
.doc .w60 { width: 60%; } .doc .w70 { width: 70%; } .doc .w86 { width: 86%; }
.doc .w88 { width: 88%; } .doc .w92 { width: 92%; } .doc .w95 { width: 95%; }
.panel .foot {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-top: 1px solid var(--line);
  font-size: 11px; color: var(--fg-3);
}
.panel .foot .prog { flex: 1; height: 3px; border-radius: 2px; background: rgba(255, 255, 255, 0.08); }
.panel .foot .prog i { display: block; width: 34%; height: 100%; border-radius: 2px; background: var(--cy); }

.chat { display: grid; gap: 10px; padding: 18px 16px; }
.chat .bubble { font-size: 13px; line-height: 1.75; padding: 9px 12px; border-radius: 12px; }
.chat .user { justify-self: end; max-width: 82%; background: rgba(52, 224, 208, 0.1); color: var(--fg); }
.chat .ai { background: rgba(255, 255, 255, 0.045); color: var(--fg-2); }
.chat .meta { font-family: var(--mono); font-size: 11px; color: var(--fg-3); }

.rows { display: grid; }
.rows .row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 16px; border-bottom: 1px solid var(--line);
  font-size: 13px; color: var(--fg-2);
}
.rows .row:last-child { border-bottom: 0; }
.rows .row b { font-weight: 500; }
.rows .row i { font-style: normal; font-family: var(--mono); font-size: 11px; color: var(--fg-3); }
.rows .row.on { color: var(--fg); background: rgba(52, 224, 208, 0.07); box-shadow: inset 2px 0 0 var(--cy); }

.tree { display: grid; gap: 0; padding: 18px 16px; }
.tree .node {
  display: flex; align-items: center; gap: 10px;
  padding: 11px 13px; border: 1px solid var(--line); border-radius: 10px;
  font-size: 13px; color: var(--fg-2); background: rgba(255, 255, 255, 0.03);
}
.tree .node.root { width: 74%; }
.tree .node b { color: var(--fg); font-weight: 500; }
.tree .node i { font-style: normal; font-family: var(--mono); font-size: 11px; color: var(--fg-3); }
.tree .branch { width: 1px; height: 26px; margin-left: 30px; background: color-mix(in srgb, var(--cy) 50%, transparent); }
.tree .node.branched { margin-left: 30px; }
.tag {
  font-family: var(--mono); font-size: 10px; letter-spacing: 0.08em;
  padding: 2px 6px; border-radius: 5px;
  color: var(--fg-3); border: 1px solid var(--line);
}
.tag.cy { color: var(--cy); border-color: color-mix(in srgb, var(--cy) 40%, transparent); }

/* ---------- 收尾 ---------- */
.outro { padding: 130px 28px 90px; text-align: center; border-top: 1px solid var(--line); }
.outro h2 { margin: 16px 0 0; font-family: var(--serif); font-size: clamp(30px, 5vw, 62px); letter-spacing: -0.01em; }
.outro .sub { color: var(--fg-2); }
.outro .center { margin-left: auto; margin-right: auto; text-align: center; }
.outro .sign {
  margin: 76px auto 0;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  color: var(--fg-3);
}

/* ---------- 窄屏 ---------- */
@media (max-width: 860px) {
  .feature { grid-template-columns: 1fr; gap: 20px; }
  .feature.flip .copy { order: 0; }
  .band { padding: 76px 20px; }
  .topbar { padding: 14px 18px; }
  .roman { font-size: 10.5px; letter-spacing: 0.18em; }
  .topbar nav .link:not(.enter) { display: none; }
  .points li { grid-template-columns: 30px 24px 1fr; }
}

/* 减少动效时停掉，不是减慢——入场、闪烁光标、拨雾都不是信息 */
@media (prefers-reduced-motion: reduce) {
  .hero h1 .word, .askbox .block { animation: none; }
  .welcome { scroll-behavior: auto; }
}
</style>
