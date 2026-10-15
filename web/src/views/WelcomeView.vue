<script setup lang="ts">
/**
 * 登录前的介绍 / 导航页（门厅）。结构对着设计稿（hero / mid / tail 三张）排：
 * 卡片式首屏 → `WHY OMNIREAD` 三张卡 → 四个编号功能块 → 收尾。**文案逐句照设计稿。**
 *
 * **它不进三栏壳**（`main.ts` 里标了 `meta.shell = false`）：门厅里摆一组指向应用的按钮、
 * 却哪儿也去不了，比没有这组按钮更糟。
 *
 * **一条内容红线**：这页一个字的原著正文都不能有——「静态资源里不得含语料文本」是部署验收里
 * 要 grep 的项。所以只有章节编号、界面文案、以及 mock 面板里那些假的数据条。
 *
 * **使用须知不在这里**：它是登录进入功能页之后的弹窗（`NoticeGate`），不参与站点设计。
 *
 * 背景是程序化画布 + 一层可以用指针拨开的雾——那一段抽在 `components/HeroBackdrop.vue`，
 * **登录页共用同一个组件**（改效果只改一处）。首屏内容居中是刻意的：画面与雾在文字后面，
 * 「拨开」才有地方发生。
 */
import { useRouter } from 'vue-router'
import HeroBackdrop from '../components/HeroBackdrop.vue'
import TypewriterText from '../components/TypewriterText.vue'

const router = useRouter()

function enter(): void {
  void router.push({ name: 'library' })
}
</script>

<template>
  <div class="welcome canvas-page">
    <!-- 顶栏只剩品牌：导航项全砍了，页面内的去向交给首屏那颗按钮与页脚 -->
    <header class="topbar">
      <span class="mark">OMNIREAD</span>
    </header>

    <!-- ── 一、首屏：内容居中压在画上，画与雾在它后面（共用组件） ── -->
    <HeroBackdrop class="hero">
      <!-- 结构照官网 hero —— 标题组 → 输入框 → 按钮，三者都是居中列 -->
      <div class="hero-content">
        <div class="hero-head">
          <p class="eyebrow">OMNIREAD · READ BEYOND</p>
          <h1>故事未完，随时重逢。</h1>
          <p class="lead">
            那些读到一半的故事，那些念念不忘的角色，都值得再次相遇。Omniread 陪你找回剧情、解开疑问，让每一次重逢都自然发生。
          </p>
        </div>

        <button class="askbox" @click="enter">
          <span class="caret">&gt;</span>
          <span class="placeholder">就这本书提问…</span>
          <span class="block"></span>
          <span class="go">登录后可用</span>
        </button>

        <div class="btns">
          <!-- 这一颗进功能页（`enter`），不是往下滚。未登录时由**路由守卫**统一拦到 /login
               （一处收口，页面上不逐颗按钮判断）。 -->
          <button class="btn" @click="enter">
            探索故事
            <svg class="arw" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
              <path d="M3 8h9M8.5 4.5L12 8l-3.5 3.5" />
            </svg>
          </button>
        </div>
      </div>

    </HeroBackdrop>

    <!-- ── 二、为什么 ── -->
    <section id="why" class="band why">
      <div class="inner">
        <p class="eyebrow">WHY OMNIREAD</p>
        <h2>阅读不该是一场与遗忘的赛跑。</h2>
        <p class="lead">
          我们不想让你追赶阅读进度。无论是暂时搁置的故事、难以理解的剧情，
          还是让你念念不忘的角色，都应该有重新走近它们的方式。
        </p>

        <ul class="cards">
          <li>
            <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
              <path d="M4 5.5A2.5 2.5 0 016.5 3H20v15H6.5A2.5 2.5 0 004 20.5zM4 5.5v15M9 3v15" />
            </svg>
            <b>随时接续</b>
            <span>忘记剧情，也能快速找回阅读脉络。</span>
          </li>
          <li>
            <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
              <path d="M21 11.5a7.5 7.5 0 01-10.9 6.7L5 20l1.6-4.4A7.5 7.5 0 1121 11.5z" />
              <path d="M9.5 9.5h5M9.5 12.5h3" />
            </svg>
            <b>随时讨论</b>
            <span>围绕小说内容提问，不必离开阅读界面。</span>
          </li>
          <li>
            <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
              <path d="M12 3l7.5 3v5.5c0 4.6-3.1 8-7.5 9.5-4.4-1.5-7.5-4.9-7.5-9.5V6z" />
              <path d="M8.8 12.2l2.2 2.2 4.2-4.4" />
            </svg>
            <b>自由探索</b>
            <span>自主选择无剧透或完整剧透的讨论方式。</span>
          </li>
        </ul>

        <p class="why-foot">让故事按照你的节奏继续，而不是让你追赶故事。</p>
      </div>
    </section>

    <!-- ── 三、四个编号功能块（界面都是画出来的 mock，没有图片素材） ── -->
    <section id="features" class="band features">
      <div class="inner">
        <article class="step">
          <p class="tag">01 · 阅读工作台</p>
          <div class="step-grid">
            <div class="mock" aria-hidden="true">
              <div class="chrome"><i></i><i></i><i></i><span class="who">全书第 3 章 · 第 1 卷</span></div>
              <div class="doc">
                <span class="l w92"></span><span class="l w86"></span><span class="l w95"></span>
                <span class="l w70"></span>
                <span class="fig"></span>
                <span class="l w88"></span><span class="l w60"></span>
              </div>
              <div class="foot"><span>上一章</span><span class="prog"><i></i></span><span>下一章</span></div>
            </div>
            <div class="step-copy">
              <h3><TypewriterText text="把阅读与理解，放在同一个空间。" /></h3>
              <p>小说、章节导航与 AI 助手并行工作。阅读时随时提问，无需切换应用或丢失上下文。</p>
            </div>
          </div>
        </article>

        <article class="step flip">
          <p class="tag">02 · 剧情回顾</p>
          <div class="step-grid">
            <div class="mock" aria-hidden="true">
              <div class="chrome"><i></i><i></i><i></i><span class="who">剧情回顾 · 第 24 章以前</span></div>
              <div class="doc">
                <span class="l w88"></span><span class="l w95"></span>
                <span class="l on w78"></span>
                <span class="l w70"></span><span class="l w60"></span>
              </div>
            </div>
            <div class="step-copy">
              <h3><TypewriterText text="忘记了前面的剧情？随时接着读。" /></h3>
              <p>快速梳理人物关系、关键事件与伏笔。读过的内容重新建立联系，不必从头翻找。</p>
            </div>
          </div>
        </article>

        <article class="step">
          <p class="tag">03 · 双档 AI 对话</p>
          <div class="step-grid">
            <div class="mock" aria-hidden="true">
              <div class="seg">
                <span class="on">无剧透</span>
                <span>完整剧透</span>
              </div>
              <div class="chat">
                <span class="bubble user">这个角色为什么突然改变立场？</span>
                <span class="bubble ai">
                  结合当前章节的线索，可以从他的对话和先前行为理解这一变化……
                </span>
              </div>
            </div>
            <div class="step-copy">
              <h3><TypewriterText text="想知道多少，由你决定。" /></h3>
              <p>无剧透模式严格限定在当前阅读进度；完整剧透模式允许深入讨论后续发展、隐藏伏笔与人物结局。</p>
            </div>
          </div>
        </article>

        <article class="step flip">
          <p class="tag">04 · 角色与故事探索</p>
          <div class="step-grid">
            <div class="mock" aria-hidden="true">
              <div class="cast">
                <span class="avatar">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                    <circle cx="12" cy="9" r="3.4" />
                    <path d="M5.5 20a6.5 6.5 0 0113 0" />
                  </svg>
                </span>
                <span class="lines"><i class="ac"></i><i></i></span>
              </div>
              <div class="cast-relations">
                <span class="rel-label">角色关系</span>
                <div class="rel-row">
                  <span class="chip">角色 A</span>
                  <span class="arrow">⇄</span>
                  <span class="chip">角色 B</span>
                </div>
              </div>
            </div>
            <div class="step-copy">
              <h3><TypewriterText text="从一个喜欢的角色，认识整个故事。" /></h3>
              <p>探索角色经历、关系变化与关键章节。即使暂时没有时间读完整本小说，也能从感兴趣的地方开始。</p>
            </div>
          </div>
        </article>
      </div>
    </section>

    <!-- ── 四、页脚：网站信息与版权 ── -->
    <footer class="foot">
      <div class="inner foot-top">
        <div class="foot-brand">
          <p class="mark">OMNIREAD</p>
          <p class="tagline">故事未完，随时重逢。</p>
        </div>
      </div>
      <div class="inner foot-legal">
        <p>© 2026 Omniread · 个人学习与技术演示项目，仅供面试沟通与技术评估</p>
        <p>阅读页只放第 1 卷 · 问答覆盖整本书 · 回答由 AI 生成，请以原文为准</p>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* ============================================================================
   门厅的版式。配色令牌（--ac / --fg / --line …）在 style.css 的 `.canvas-page` 里——
   登录页是同一族的另一张画，两份共用同一套色。
   强调色只用在「信号」上——眉标、按钮、图标、mock 里的高亮行。
   ========================================================================== */
.welcome {
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
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
  background: linear-gradient(rgba(5, 6, 12, 0.72), rgba(5, 6, 12, 0));
}
.topbar .mark {
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.34em;
  color: var(--fg);
}

/* ---------- 首屏 ---------- */
/* 画布、雾、层叠隔离都在 HeroBackdrop 里，这里只管这一屏多高、内容怎么摆 */
.hero {
  /* 高度封顶 700：满屏那一版太空，内容只占中间一段；矮屏仍按 100svh 兜底 */
  min-height: min(100vh, 700px);
  min-height: min(100svh, 700px);
  display: grid;
  align-items: center;
  justify-items: center;
  padding: 96px 28px 76px;
  /* 一抹紫罗兰的底光，把视线压到中间那一段文字上；其余交给画布 */
  background: radial-gradient(880px 560px at 50% 62%, rgba(139, 123, 255, 0.17), transparent 64%);
}

/* 居中内容列：宽 809 / 列内间距 40 / 标题组内间距 30 —— 三个数都取自官网 hero */
.hero-content {
  position: relative;
  width: min(809px, 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 40px;
}
.hero-head { display: flex; flex-direction: column; align-items: center; gap: 30px; text-align: center; }

.eyebrow {
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.22em;
  color: var(--ac);
  margin: 0;
}
.hero h1 {
  margin: 20px 0 0;
  font-size: clamp(31px, 4.6vw, 52px);
  line-height: 1.25;
  /* 正字距、760 的字重：官网标题是 400 + 0.4px（那是拉丁展示体，中文照搬会太细） */
  letter-spacing: 0.4px;
  font-weight: 700;
  /* 字直接压在画上，没有这层投影，亮部（星云、圆相）会把笔画吃掉 */
  text-shadow: 0 2px 26px rgba(0, 0, 0, 0.62);
}
h2 {
  margin: 14px 0 0;
  font-family: var(--serif);
  font-size: clamp(28px, 4.2vw, 52px);
  line-height: 1.24;
  letter-spacing: -0.01em;
}
h3 { font-size: 22px; line-height: 1.4; letter-spacing: -0.01em; }
.lead {
  margin: 22px 0 0;
  font-size: 16px;
  line-height: 2;
  color: var(--fg-2);
  text-wrap: pretty;
}
/* 正文一行别太长：中文长行读起来会丢行 */
.lead { max-width: 34em; }

/* 首屏那段说明用**明朝体衬线**：官网的排版是「标题无衬线 + 副标题衬线」，
   这一对调过来之后，标题的力气和正文的呼吸分得开。段落只有下面两节用无衬线。 */
.hero .lead {
  font-family: var(--serif);
  font-size: clamp(17px, 1.7vw, 21px);
  font-weight: 500;
  line-height: 1.65;
  letter-spacing: 0.4px;
  color: var(--fg);
  max-width: min(760px, 100%);
  margin-inline: auto;
  text-shadow: 0 2px 22px rgba(0, 0, 0, 0.6);
}

/* 输入框的 mock：它长得像这个站点真正的那一个（等登录后就是真的了）。
   600 × 55、10px 圆角是官网终端那一块的数；它也是这一屏的第三块，居中排在标题与按钮之间。 */
.askbox {
  display: flex;
  align-items: center;
  gap: 10px;
  width: min(600px, 100%);
  height: 55px;
  padding: 0 18px;
  font: inherit;
  font-family: var(--mono);
  font-size: 13.5px;
  text-align: left;
  color: var(--fg-3);
  background: rgba(14, 14, 26, 0.7);
  border: 1px solid var(--line);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
}
.askbox:hover { border-color: color-mix(in srgb, var(--ac) 42%, transparent); background: rgba(18, 18, 34, 0.86); }
/* 环境反馈：鼠标在 hero 里任何地方，输入框自己亮一点（官网是 hero:hover 时终端底色变白） */
.hero:hover .askbox { background: rgba(18, 18, 34, 0.74); border-color: color-mix(in srgb, var(--ac) 30%, transparent); }
.askbox .caret { color: var(--ac); }
.askbox .placeholder { flex: 1; }
.askbox .block { width: 7px; height: 15px; background: var(--ac); opacity: 0.75; animation: blink 1.1s steps(1) infinite; }
.askbox .go { color: var(--fg-3); font-size: 11px; }
@keyframes blink { 50% { opacity: 0; } }

.btns { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; justify-content: center; }
.btns.center { justify-content: center; }
/* 首屏那颗按钮：**液态玻璃**（半透 + 背景模糊 + 一道内高光）。
   背景模糊真的吃到后面的画布，所以星云会从那块玻璃里透出来。
   hover **不变色**——只做位移与箭头滑入，颜色一动不动。 */
.btn {
  font: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 44px;
  padding: 0 30px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(18px) saturate(170%);
  -webkit-backdrop-filter: blur(18px) saturate(170%);
  color: var(--fg);
  font-size: 15px;
  font-weight: 500;
  letter-spacing: 0.24px;
  cursor: pointer;
  /* 顶边一道内高光 + 底部一点落影：玻璃的「厚度」全靠这两笔 */
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.24), 0 16px 36px -20px rgba(0, 0, 0, 0.85);
  transition: transform 0.2s ease;
}
.btn:hover { transform: translateY(-1px); }

/* 箭头默认**藏在文字里**（负外边距），hover 才滑出来。
   这套「箭头滑入」是官网按钮的招牌，靠 margin 与 opacity 两个属性做，不用 transform。 */
.arw {
  width: 15px;
  height: 15px;
  flex: none;
  transition: opacity 0.2s ease, margin-left 0.2s ease;
}
.btn .arw { margin-left: -15px; opacity: 0; }
.btn:hover .arw { margin-left: 9px; opacity: 1; }

/* ---------- 通用版心 ---------- */
.band { padding: 110px 28px; border-top: 1px solid var(--line); }
.inner { width: min(1080px, 100%); margin: 0 auto; }

/* ---------- 为什么：三张卡 ---------- */
.why .lead { margin-top: 24px; }
.cards {
  list-style: none;
  margin: 46px 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.cards li {
  padding: 24px 22px 26px;
  border-radius: 18px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.035);
  display: grid;
  gap: 10px;
}
.cards .ic { width: 26px; height: 26px; color: var(--ac); }
.cards b { font-size: 18px; }
.cards span:last-child { font-size: 14px; line-height: 1.85; color: var(--fg-2); text-wrap: pretty; }
.why-foot {
  margin: 34px 0 0;
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.06em;
  color: var(--fg-3);
}

/* ---------- 功能：四个编号块 ---------- */
.step { padding: 54px 0 10px; border-top: 1px solid var(--line); }
.step:first-child { border-top: 0; padding-top: 0; }
.tag {
  display: inline-block;
  margin: 0 0 26px;
  padding: 5px 13px;
  border-radius: 999px;
  border: 1px solid var(--line);
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.06em;
  color: var(--fg-2);
}
.step-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 40px;
  align-items: center;
}
.step.flip .step-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr); }
.step.flip .mock { order: 2; }
.step-copy p { margin: 14px 0 0; font-size: 15px; line-height: 1.95; color: var(--fg-2); text-wrap: pretty; }

/* 面板：界面是**画出来的**（没有图片素材），只用线、块与色 */
.mock {
  border-radius: 16px;
  border: 1px solid var(--line);
  background: var(--panel);
  overflow: hidden;
  box-shadow: 0 34px 80px -46px rgba(0, 0, 0, 0.95), inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.chrome { display: flex; align-items: center; gap: 6px; padding: 11px 14px; border-bottom: 1px solid var(--line); }
.chrome i { width: 8px; height: 8px; border-radius: 50%; background: rgba(190, 185, 255, 0.22); }
.chrome .who { margin-left: 10px; font-family: var(--mono); font-size: 11px; color: var(--fg-3); letter-spacing: 0.05em; }

.doc { display: grid; gap: 10px; padding: 20px 18px; }
.doc .l {
  height: 10px; border-radius: 6px;
  background: linear-gradient(90deg, rgba(214, 210, 255, 0.2), rgba(214, 210, 255, 0.07));
}
.doc .l.on { background: linear-gradient(90deg, color-mix(in srgb, var(--ac) 55%, transparent), color-mix(in srgb, var(--ac) 22%, transparent)); }
.doc .fig {
  height: 84px; border-radius: 10px;
  background: repeating-linear-gradient(135deg, rgba(139, 123, 255, 0.16) 0 8px, rgba(139, 123, 255, 0.04) 8px 16px);
}
.doc .w60 { width: 60%; } .doc .w70 { width: 70%; } .doc .w78 { width: 78%; }
.doc .w88 { width: 88%; } .doc .w92 { width: 92%; } .doc .w95 { width: 95%; }
.mock .foot {
  display: flex; align-items: center; gap: 12px;
  padding: 13px 18px; border-top: 1px solid var(--line);
  font-size: 11px; color: var(--fg-3);
}
.mock .foot .prog { flex: 1; height: 3px; border-radius: 2px; background: rgba(255, 255, 255, 0.08); }
.mock .foot .prog i { display: block; width: 34%; height: 100%; border-radius: 2px; background: var(--ac); }

/* 双档对话的 mock：先一个档位开关，再一问一答 */
.seg { display: flex; gap: 6px; padding: 16px 18px 0; }
.seg span {
  font-size: 13px;
  padding: 6px 15px;
  border-radius: 10px;
  color: var(--fg-3);
  background: rgba(255, 255, 255, 0.04);
}
.seg .on { color: #fff; background: linear-gradient(135deg, var(--ac), var(--ac-2)); font-weight: 500; }
.chat { display: grid; gap: 10px; padding: 16px 18px 20px; }
.chat .bubble { font-size: 13.5px; line-height: 1.8; padding: 11px 14px; border-radius: 13px; }
.chat .user { justify-self: end; max-width: 86%; background: rgba(139, 123, 255, 0.12); color: var(--fg); }
.chat .ai { background: rgba(255, 255, 255, 0.05); color: var(--fg-2); }

/* 角色探索的 mock：头像 + 名字 + 角色关系 */
.cast { display: flex; align-items: center; gap: 14px; padding: 20px 18px 16px; }
.cast .avatar {
  width: 42px; height: 42px; flex: none; display: grid; place-items: center;
  border-radius: 13px; color: var(--ac);
  background: rgba(139, 123, 255, 0.12);
  border: 1px solid color-mix(in srgb, var(--ac) 26%, transparent);
}
.cast .avatar svg { width: 24px; height: 24px; }
.cast .lines { flex: 1; display: grid; gap: 8px; }
.cast .lines i { height: 10px; border-radius: 6px; background: rgba(214, 210, 255, 0.14); }
.cast .lines i.ac { background: linear-gradient(90deg, var(--ac), color-mix(in srgb, var(--ac) 30%, transparent)); }
.cast-relations { padding: 0 18px 20px; border-top: 1px solid var(--line); margin-top: 4px; }
.rel-label { display: block; padding: 14px 0 10px; font-family: var(--mono); font-size: 11px; color: var(--fg-3); letter-spacing: 0.08em; }
.rel-row { display: flex; align-items: center; gap: 12px; }
.chip {
  flex: 1;
  text-align: center;
  padding: 12px 10px;
  border-radius: 12px;
  font-size: 13px;
  color: var(--fg-2);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--line);
}
.arrow { color: var(--ac); font-size: 15px; }

/* ---------- 页脚：两段，上品牌与去向、下版权与免责 ---------- */
.foot { padding: 72px 28px 44px; border-top: 1px solid var(--line); }
.foot-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 28px;
  flex-wrap: wrap;
}
.foot .mark { margin: 0; font-family: var(--mono); font-size: 12px; letter-spacing: 0.34em; color: var(--fg); }
.foot .tagline { margin: 12px 0 0; font-family: var(--serif); font-size: 17px; color: var(--fg-2); }
.foot-legal { margin-top: 46px; padding-top: 20px; border-top: 1px solid var(--line); }
.foot-legal p {
  margin: 0;
  font-size: 12px;
  line-height: 2;
  color: var(--fg-3);
  letter-spacing: 0.02em;
}

/* ---------- 窄屏 ---------- */
@media (max-width: 900px) {
  .hero { padding: 92px 20px 64px; }
  .hero-content { gap: 30px; }
  .band { padding: 76px 20px; }
  .cards { grid-template-columns: 1fr; }
  .step-grid, .step.flip .step-grid { grid-template-columns: 1fr; gap: 22px; }
  .step.flip .mock { order: 0; }
  .topbar { padding: 14px 18px; }
}

/* 减少动效时停掉，不是减慢——拨雾在脚本里就没挂，这里只管过渡 */
@media (prefers-reduced-motion: reduce) {
  .welcome { scroll-behavior: auto; }
  .askbox .block { animation: none; }
  .btn:hover { transform: none; }
}
</style>
