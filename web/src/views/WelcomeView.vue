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
          忘记了前面的剧情，不必反复翻找；遇到陌生的人物与复杂的关系，不必在章节间来回跳转。
          Omniread 将 AI 融入阅读过程，让你随时找回故事脉络、理解人物与情节，也能自由决定探索故事的深度。
        </p>

        <ul class="cards">
          <li>
            <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
              <path d="M4 5.5A2.5 2.5 0 016.5 3H20v15H6.5A2.5 2.5 0 004 20.5zM4 5.5v15M9 3v15" />
            </svg>
            <b>随时接续</b>
            <span>忘记了人物是谁，或记不清之前发生了什么？通过 AI 回顾关键剧情与人物信息，快速找回上下文，不必重新翻阅整段故事。</span>
          </li>
          <li>
            <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
              <path d="M3 6.5A2.5 2.5 0 015.5 4h7A2.5 2.5 0 0115 6.5v4a2.5 2.5 0 01-2.5 2.5H8l-3.5 3v-3.2A2.5 2.5 0 013 10.5z" />
              <path d="M18 9h.5A2.5 2.5 0 0121 11.5v3.6a2.5 2.5 0 01-1.6 2.3V21l-3.4-3H12" />
            </svg>
            <b>随时探讨</b>
            <span>一个称呼、一段对话，也可能藏着复杂的人物关系。直接向 AI 提问，结合小说原文理解指代、梳理线索，让难懂的剧情有迹可循。</span>
          </li>
          <li>
            <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
              <circle cx="12" cy="12" r="8.6" />
              <path d="M15 9l-1.7 4.3L9 15l1.7-4.3z" />
            </svg>
            <b>自由探索</b>
            <span>想重温已经读过的情节，还是提前了解后续发展？自由选择回顾或剧透模式，让 AI 按照你的阅读需求展开讨论。</span>
          </li>
        </ul>

        <p class="why-foot">不必追赶故事的进度，让故事按照你的节奏继续。</p>
      </div>
    </section>

    <!-- ── 三、四个编号功能块（界面都是画出来的 mock，没有图片素材） ── -->
    <section id="features" class="band features">
      <div class="inner">
        <article class="step">
          <div class="step-grid">
            <div class="mock mk-work" aria-hidden="true">
              <div class="mk-chrome">
                <i></i><i></i><i></i>
                <span class="mk-who">阅读工作台 · 全书第 3 章</span>
                <span class="mk-who-r">第 1 卷</span>
              </div>
              <div class="mk-work-body">
                <div class="mk-pane mk-tree">
                  <span class="mk-pane-h">目录</span>
                  <span class="mk-ch"><i class="mk-ch-num">01</i><i class="mk-ch-label">第 1 章</i></span>
                  <span class="mk-ch"><i class="mk-ch-num">02</i><i class="mk-ch-label">第 2 章</i></span>
                  <span class="mk-ch on"><i class="mk-ch-num">03</i><i class="mk-ch-label">第 3 章</i></span>
                  <span class="mk-ch"><i class="mk-ch-num">04</i><i class="mk-ch-label">第 4 章</i></span>
                  <span class="mk-ch"><i class="mk-ch-num">05</i><i class="mk-ch-label">第 5 章</i></span>
                  <span class="mk-ch"><i class="mk-ch-num">06</i><i class="mk-ch-label">第 6 章</i></span>
                  <span class="mk-ch"><i class="mk-ch-num">07</i><i class="mk-ch-label">第 7 章</i></span>
                  <span class="mk-ch"><i class="mk-ch-num">08</i><i class="mk-ch-label">第 8 章</i></span>
                  <span class="mk-ch"><i class="mk-ch-num">09</i><i class="mk-ch-label">第 9 章</i></span>
                </div>
                <div class="mk-pane mk-doc">
                  <span class="mk-kicker">第 1 卷 · 全书第 3 章</span>
                  <span class="mk-title"></span>
                  <span class="mk-l mk-w95"></span>
                  <span class="mk-l mk-w88"></span>
                  <span class="mk-l mk-w92"></span>
                  <span class="mk-l mk-w70"></span>
                  <span class="mk-l on mk-w84"></span>
                  <span class="mk-l mk-w90"></span>
                  <span class="mk-l mk-w62"></span>
                  <span class="mk-l mk-w95"></span>
                  <span class="mk-l mk-w74"></span>
                  <span class="mk-l mk-w86"></span>
                </div>
                <div class="mk-pane mk-chat">
                  <span class="mk-pane-h">问答</span>
                  <span class="mk-bubble user">这一章讲了什么？</span>
                  <span class="mk-bubble ai">
                    <i class="mk-l mk-w90"></i>
                    <i class="mk-l mk-w74"></i>
                    <i class="mk-l mk-w86"></i>
                    <i class="mk-l mk-w64"></i>
                  </span>
                  <span class="mk-input"><i>&gt;</i>就本章提问…</span>
                </div>
              </div>
              <div class="mk-nav">
                <span>上一章</span>
                <span class="mk-prog"><i></i></span>
                <span>下一章</span>
              </div>
            </div>
            <div class="step-copy">
              <h3><TypewriterText text="阅读与 AI 对话，无缝衔接。" /></h3>
              <p>随时阅读，随时提问。不用切换页面，也不用打断阅读节奏，让 AI 成为你的专属阅读搭档。</p>
            </div>
          </div>
        </article>

        <article class="step flip">
          <div class="step-grid">
            <div class="mock mk-panel mk-recall" aria-hidden="true">
              <div class="mk-head">
                <span class="mk-ai-mark"></span>
                <b class="mk-head-title">剧情问答</b>
                <span class="mk-head-meta">全书第 24 章</span>
                <span class="mk-head-badge">回顾模式</span>
              </div>
              <div class="mk-body">
                <div class="mk-mode">
                  <span class="mk-mode-thumb"></span>
                  <span class="mk-mode-opt on">回顾<small>不剧透</small></span>
                  <span class="mk-mode-opt">剧透<small>全知</small></span>
                </div>
                <span class="mk-mode-note">只依据已读章节回答</span>
                <div class="mk-recall-card">
                  <span class="mk-q">她后来答应了没有？</span>
                  <span class="mk-a">在已读内容里，这件事还没有结果。<sup class="mk-cite">12</sup></span>
                </div>
                <div class="mk-cutoff"><span>第 24 章 · 阅读进度</span></div>
                <div class="mk-future">
                  <span class="mk-future-h">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                      <rect x="5" y="10.5" width="14" height="10" rx="2.5" />
                      <path d="M8.5 10.5V8a3.5 3.5 0 017 0v2.5" />
                    </svg>
                    后续剧情已隐藏
                  </span>
                  <i class="mk-l mk-w86"></i>
                  <i class="mk-l mk-w64"></i>
                  <i class="mk-l mk-w92"></i>
                  <i class="mk-l mk-w70"></i>
                </div>
                <span class="mk-input"><i>&gt;</i>就这本书提问…</span>
              </div>
            </div>
            <div class="step-copy">
              <h3><TypewriterText text="想知道多少，由你决定。" /></h3>
              <p>想重温已读剧情，还是提前探索后续发展？自由切换回顾与剧透模式，按自己的阅读节奏获取信息，既能守住惊喜，也能满足好奇。</p>
            </div>
          </div>
        </article>

        <article class="step">
          <div class="step-grid">
            <div class="mock mk-panel mk-coref" aria-hidden="true">
              <div class="mk-head">
                <span class="mk-ai-mark"></span>
                <b class="mk-head-title">剧情问答</b>
                <span class="mk-head-meta">全书第 3 章</span>
                <span class="mk-head-badge">指代理解</span>
              </div>
              <div class="mk-body mk-thread">
                <span class="mk-bubble user">艾莉的姐姐叫什么？</span>
                <span class="mk-bubble ai brief">玛夏。</span>
                <span class="mk-bubble user">她和她姐姐在学生会分别担任什么职务？</span>
                <div class="mk-ai-card">
                  <ol class="mk-flow">
                    <li class="k-retrieval">
                      <div class="mk-row">
                        <span class="mk-ico">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <circle cx="10.5" cy="10.5" r="6" />
                            <path d="M15 15l4.5 4.5" />
                          </svg>
                        </span>
                        <b class="mk-name">检索</b>
                        <span class="mk-sum">4 条线索</span>
                        <span class="mk-time">0.6s</span>
                        <span class="mk-mark">✓</span>
                      </div>
                    </li>
                    <li class="k-thinking">
                      <div class="mk-row">
                        <span class="mk-ico">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path d="M12 3.5a5.5 5.5 0 00-3.2 9.9V16h6.4v-2.6A5.5 5.5 0 0012 3.5z" />
                            <path d="M10 19h4" />
                          </svg>
                        </span>
                        <b class="mk-name">思考</b>
                        <span class="mk-sum">「她」→ 艾莉</span>
                        <span class="mk-time">1.1s</span>
                        <span class="mk-mark">✓</span>
                      </div>
                    </li>
                    <li class="k-generating">
                      <div class="mk-row">
                        <span class="mk-ico">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path d="M20 12a7.5 7.5 0 01-10.6 6.7L5 20l1.4-4.2A7.5 7.5 0 1120 12z" />
                          </svg>
                        </span>
                        <b class="mk-name">生成</b>
                        <span class="mk-sum">引用 2 处</span>
                        <span class="mk-time">2.3s</span>
                        <span class="mk-mark">✓</span>
                      </div>
                    </li>
                  </ol>
                  <p class="mk-answer">
                    艾莉是学生会会计，玛夏在二年级担任学生会书记<sup class="mk-cite">9</sup>。
                  </p>
                </div>
                <span class="mk-input"><i>&gt;</i>就本章提问…</span>
              </div>
            </div>
            <div class="step-copy">
              <h3><TypewriterText text="告别剧情遗忘与指代混淆。" /></h3>
              <p>无需反复翻阅前文，即使只记得一个模糊的称呼、一段零散的情节，也能直接提问。AI 结合小说内容理解上下文，消除指代歧义，帮你理清人物关系、回顾关键剧情，让每一次阅读都能自然接续。</p>
            </div>
          </div>
        </article>

        <article class="step flip">
          <div class="step-grid">
            <div class="mock mk-panel mk-sources" aria-hidden="true">
              <div class="mk-head">
                <span class="mk-ai-mark"></span>
                <b class="mk-head-title">剧情问答</b>
                <span class="mk-head-meta">全书第 9 章</span>
                <span class="mk-head-badge">2 条依据</span>
              </div>
              <div class="mk-body mk-thread">
                <span class="mk-bubble user">艾莉为什么不喜欢被叫「公主大人」？</span>
                <div class="mk-ai-card">
                  <ol class="mk-flow">
                    <li class="k-retrieval open">
                      <div class="mk-row">
                        <span class="mk-ico">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <circle cx="10.5" cy="10.5" r="6" />
                            <path d="M15 15l4.5 4.5" />
                          </svg>
                        </span>
                        <b class="mk-name">检索</b>
                        <span class="mk-sum">2 条依据</span>
                        <span class="mk-time">0.7s</span>
                        <span class="mk-chev">▾</span>
                      </div>
                      <div class="mk-src-list">
                        <span class="mk-src"><i class="mk-src-n">[5]</i>第 5 章 · 称呼的由来<i class="mk-src-v">第 1 卷</i></span>
                        <span class="mk-src"><i class="mk-src-n">[9]</i>第 9 章 · 当面解释<i class="mk-src-v">第 1 卷</i></span>
                      </div>
                    </li>
                    <li class="k-generating">
                      <div class="mk-row">
                        <span class="mk-ico">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path d="M20 12a7.5 7.5 0 01-10.6 6.7L5 20l1.4-4.2A7.5 7.5 0 1120 12z" />
                          </svg>
                        </span>
                        <b class="mk-name">生成</b>
                        <span class="mk-sum">引用 2 处</span>
                        <span class="mk-time">2.1s</span>
                        <span class="mk-mark">✓</span>
                      </div>
                    </li>
                  </ol>
                  <p class="mk-answer">
                    她介意的不是被夸漂亮，而是这个称呼把她的努力抹成了天分<sup class="mk-cite">5</sup>；这一点她后来当面解释过<sup class="mk-cite">9</sup>。
                  </p>
                </div>
                <span class="mk-input"><i>&gt;</i>就这本书提问…</span>
              </div>
            </div>
            <div class="step-copy">
              <h3><TypewriterText text="不止回答问题，更能找到原文依据。" /></h3>
              <p>想知道的剧情、人物与细节，都可以直接提问。AI 结合小说内容检索相关线索，并展示引用依据，让每一次解答都有迹可循。</p>
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
  margin: 20px 0 0;
  font-size: clamp(26px, 3.1vw, 36px);
  line-height: 1.3;
  font-weight: 800;
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

/* ---------- 为什么：一整块面板 + 三张流光卡 ---------- */
.why .inner {
  padding: 44px 44px 40px;
  border-radius: 28px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.022);
}
.why .lead { margin-top: 26px; max-width: none; font-size: 17px; line-height: 2.05; }
.cards {
  list-style: none;
  margin: 40px 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 26px;
}
.cards li {
  position: relative;
  padding: 26px 24px 28px;
  border-radius: 18px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  display: grid;
  gap: 14px;
  align-content: start;
}
.cards .ic { width: 30px; height: 30px; color: var(--ac); }
.cards b { font-size: 20px; letter-spacing: -0.01em; }
.cards span:last-child { font-size: 15px; line-height: 2.05; color: var(--fg-2); text-wrap: pretty; }

/* 流光环绕：一段彗尾沿描边跑圈。
   环是 conic-gradient 画的，再用两层 mask 的 xor 把中间掏空 —— 卡片底是半透明的，
   不能靠「盖一块不透明内芯」那种做法（会把面板底也盖掉）。
   @property 让角度真的能补间；不认识它的浏览器只是停在起始角度，环还在。 */
@property --why-angle {
  syntax: "<angle>";
  initial-value: 0deg;
  inherits: false;
}
.cards li::before {
  content: "";
  position: absolute;
  inset: -1px;
  padding: 1px;
  border-radius: inherit;
  pointer-events: none;
  background: conic-gradient(
    from var(--why-angle),
    transparent 0deg 226deg,
    color-mix(in srgb, var(--ac) 22%, transparent) 286deg,
    color-mix(in srgb, var(--ac) 72%, transparent) 330deg,
    var(--ac) 348deg,
    color-mix(in srgb, var(--ac-2) 96%, transparent) 357deg,
    transparent 360deg
  );
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask-composite: exclude;
  /* 不加 filter: blur/drop-shadow —— CSS 里 filter 先于 mask 生效，
     模糊会被随后的镂空裁掉，写了也看不见。光晕要靠另一层画。 */
  animation: why-flow 7s linear infinite;
}
/* 三张错开，免得三个光点同时出现 */
.cards li:nth-child(2)::before { animation-delay: -2.4s; }
.cards li:nth-child(3)::before { animation-delay: -4.8s; }
@keyframes why-flow { to { --why-angle: 360deg; } }

.why-foot {
  margin: 40px 0 0;
  padding-top: 22px;
  border-top: 1px solid var(--line);
  font-size: 14px;
  color: var(--fg-3);
}

/* ---------- 功能：四张卡 ----------
   四块各自包一张卡（圆角 + 描边 + 一点点底），靠**间距**分开而不是一条贯穿细线——
   细线只有 1px、颜色又淡，四块会糊成一片。 */
.features .inner { display: flex; flex-direction: column; gap: 28px; }
.step {
  padding: 10px 15px;
  border-radius: 26px;
  border: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.042), rgba(255, 255, 255, 0.012));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
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

/* ---------- 四块界面 mock ----------
   界面**画出来的**，不用图片素材：产品截图与页面同是深色底，贴上去会糊成一块，
   而四张截图的画幅横竖混排（1.83 / 2.86 / 0.85 / 0.51），统一不了。
   画出来的好处是四块**严格等高**（--mock-h），不依赖内容也不依赖断点。
   **类名必须带 .mk- 前缀**：全局有一条裸的 `.chat`（<=1199px 会设成 position: fixed
   并移出屏幕）和一条裸的 `.tree`，撞上就是静默错位。 */
.features { --mock-h: 360px; }
#features { scroll-margin-top: 72px; }

.mock {
  /* 三个阶段色：取值与主应用的 --warn / --ok 一致，但写成字面量——
     门厅是一张画，不跟随主应用主题。 */
  --mk-ref: var(--ac);
  --mk-think: #ffb020;
  --mk-gen: #1fbf7f;
  --mk-on-ac: #14101f;

  height: var(--mock-h);
  display: grid;
  grid-template-rows: 38px minmax(0, 1fr);
  min-width: 0;
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid color-mix(in srgb, var(--ac) 18%, var(--line));
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.012)),
    var(--panel);
  box-shadow: 0 34px 80px -46px rgba(0, 0, 0, 0.95), inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.mock.mk-work { grid-template-rows: 38px minmax(0, 1fr) 30px; }

/* ① 顶部条：01 是窗口三点，02–04 是对话面板的头 */
.mk-chrome { display: flex; align-items: center; gap: 6px; padding: 0 14px; border-bottom: 1px solid var(--line); }
.mk-chrome i { width: 8px; height: 8px; border-radius: 50%; background: rgba(190, 185, 255, 0.22); }
.mk-who { margin-left: 10px; font-family: var(--mono); font-size: 10px; color: var(--fg-3); letter-spacing: 0.05em; }
.mk-who-r { margin-left: auto; font-family: var(--mono); font-size: 10px; color: var(--fg-3); }

.mk-head { display: flex; align-items: center; gap: 7px; padding: 0 12px; border-bottom: 1px solid var(--line); }
.mk-ai-mark { width: 12px; height: 12px; flex: none; border-radius: 4px; background: linear-gradient(135deg, var(--ac), var(--ac-2)); }
.mk-head-title { flex: 1; min-width: 0; font-size: 12px; font-weight: 650; color: var(--fg); }
.mk-head-meta { flex: none; font-family: var(--mono); font-size: 10px; color: var(--fg-3); }
.mk-head-badge {
  flex: none; padding: 2px 7px; border-radius: 999px; font-size: 10px;
  color: var(--ac);
  border: 1px solid color-mix(in srgb, var(--ac) 30%, transparent);
  background: color-mix(in srgb, var(--ac) 10%, transparent);
}

/* ② 文本条与宽度档 */
.mk-body { display: flex; flex-direction: column; gap: 9px; padding: 11px 12px; min-width: 0; min-height: 0; overflow: hidden; }
.mk-l {
  display: block; height: 7px; border-radius: 4px; font-style: normal;
  background: linear-gradient(90deg, rgba(214, 210, 255, 0.2), rgba(214, 210, 255, 0.07));
}
.mk-l.on { background: linear-gradient(90deg, color-mix(in srgb, var(--ac) 55%, transparent), color-mix(in srgb, var(--ac) 22%, transparent)); }
.mk-w62 { width: 62%; } .mk-w64 { width: 64%; } .mk-w70 { width: 70%; } .mk-w74 { width: 74%; }
.mk-w84 { width: 84%; } .mk-w86 { width: 86%; } .mk-w88 { width: 88%; } .mk-w90 { width: 90%; }
.mk-w92 { width: 92%; } .mk-w95 { width: 95%; }

/* ③ 01：三栏工作台 */
.mk-work-body { display: grid; grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.5fr) minmax(0, 1fr); min-height: 0; }
.mk-pane { display: flex; flex-direction: column; gap: 6px; padding: 10px; min-width: 0; min-height: 0; overflow: hidden; }
.mk-pane + .mk-pane { border-left: 1px solid var(--line); }
.mk-pane-h { font-family: var(--mono); font-size: 9px; letter-spacing: 0.1em; color: var(--fg-3); }
.mk-tree { background: rgba(255, 255, 255, 0.02); }
.mk-doc { align-items: flex-start; gap: 7px; }
.mk-chat { gap: 6px; background: color-mix(in srgb, var(--ac) 5%, transparent); }
.mk-kicker { font-family: var(--mono); font-size: 9px; color: var(--fg-3); }
.mk-title { display: block; width: 72%; height: 12px; border-radius: 4px; background: linear-gradient(90deg, var(--ac), color-mix(in srgb, var(--ac-2) 70%, transparent)); }
.mk-ch { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 3px 5px; border-radius: 6px; }
.mk-ch-num { flex: none; font-family: var(--mono); font-size: 9px; font-style: normal; color: var(--fg-3); }
.mk-ch-label { font-size: 10px; font-style: normal; color: var(--fg-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mk-ch.on { background: color-mix(in srgb, var(--ac) 16%, transparent); }
.mk-ch.on .mk-ch-num, .mk-ch.on .mk-ch-label { color: var(--fg); }
.mk-nav { display: flex; align-items: center; gap: 10px; padding: 0 14px; border-top: 1px solid var(--line); font-size: 9px; color: var(--fg-3); }
.mk-prog { flex: 1; height: 3px; border-radius: 2px; background: rgba(255, 255, 255, 0.08); }
.mk-prog i { display: block; width: 34%; height: 100%; border-radius: 2px; background: var(--ac); }

/* ④ 气泡与输入条 */
.mk-bubble { font-size: 11px; line-height: 1.65; padding: 6px 9px; border-radius: 9px; }
.mk-bubble.user { align-self: flex-end; max-width: 92%; color: var(--fg); background: color-mix(in srgb, var(--ac) 18%, transparent); }
.mk-bubble.ai { display: grid; gap: 5px; background: rgba(255, 255, 255, 0.05); }
/* 只有一句话的回应用 fit-content，否则会被 flex 拉成一整条 */
.mk-bubble.ai.brief { align-self: flex-start; width: fit-content; }
.mk-input {
  margin-top: auto;
  display: flex; align-items: center; gap: 4px;
  padding: 5px 8px; border-radius: 8px;
  border: 1px solid var(--line); background: rgba(255, 255, 255, 0.03);
  font-size: 9px; color: var(--fg-3);
}
.mk-input i { font-style: normal; color: var(--ac); }

/* ⑤ 02：档位开关 + 切断线 + 隐藏区 */
.mk-mode {
  position: relative;
  display: grid; grid-template-columns: 1fr 1fr;
  padding: 3px; border-radius: 11px;
  border: 1px solid var(--line); background: rgba(255, 255, 255, 0.05);
}
.mk-mode-thumb {
  position: absolute; top: 3px; bottom: 3px; left: 3px; width: calc(50% - 3px);
  border-radius: 8px; background: linear-gradient(135deg, var(--ac), var(--ac-2));
}
/* 滑块是浅紫，激活档的文字必须用深色 —— 白字压在 #8b7bff 上只有 3.3:1 */
.mk-mode-opt { position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; gap: 4px; padding: 5px 0; font-size: 11px; color: var(--fg-2); }
.mk-mode-opt small { font-size: 9px; opacity: 0.72; }
.mk-mode-opt.on { color: var(--mk-on-ac); font-weight: 650; }
.mk-mode-note { font-size: 9px; color: var(--fg-3); }
.mk-recall-card { display: grid; gap: 5px; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); background: rgba(255, 255, 255, 0.045); }
.mk-q { font-size: 11px; color: var(--fg); }
.mk-a { font-size: 10.5px; line-height: 1.6; color: var(--fg-2); }
.mk-cutoff { display: flex; align-items: center; gap: 8px; font-family: var(--mono); font-size: 9px; color: var(--fg-3); }
.mk-cutoff::before, .mk-cutoff::after { content: ""; flex: 1; height: 1px; background: var(--line); }
/* 隐藏区吃掉剩余高度：它就是这个面板还没展示的那部分 */
.mk-future { flex: 1; display: grid; align-content: start; gap: 6px; padding: 8px 10px; border-radius: 10px; border: 1px dashed color-mix(in srgb, var(--ac) 26%, transparent); background: color-mix(in srgb, var(--ac) 4%, transparent); }
.mk-future-h { display: flex; align-items: center; gap: 5px; font-size: 9px; color: var(--fg-3); }
.mk-future-h svg { width: 11px; height: 11px; }
.mk-future .mk-l { opacity: 0.5; }

/* ⑥ 03 / 04：阶段时间线（主应用 .stages 的简化重画，不复用它的类名）。
   竖线必须**分段**画（图标上方一段、下方一段）：再细的线也压不住图标。
   ol 上不能加 gap —— 线会断，行距放进 li 的 padding。 */
.mk-thread { gap: 8px; }
.mk-ai-card { display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.mk-flow { --flow-row: 32px; list-style: none; margin: 0; padding: 0; }
.mk-flow li { position: relative; padding-bottom: 4px; }
.mk-flow li::before, .mk-flow li::after { content: ""; position: absolute; left: 9.25px; width: 1.5px; background: var(--line); }
.mk-flow li::before { top: 0; height: calc(var(--flow-row) / 2 - 10px); }
.mk-flow li::after { top: calc(var(--flow-row) / 2 + 10px); bottom: 0; }
.mk-flow li:first-child::before { display: none; }
.mk-flow li:last-child::after { display: none; }
.mk-row { position: relative; display: flex; align-items: center; gap: 7px; height: var(--flow-row); }
.mk-ico {
  flex: none; width: 20px; height: 20px; display: grid; place-items: center;
  border-radius: 50%; border: 1.25px solid currentColor;
  background: color-mix(in srgb, currentColor 10%, transparent);
}
.mk-ico svg { width: 11px; height: 11px; }
.k-retrieval .mk-ico { color: var(--mk-ref); }
.k-thinking .mk-ico { color: var(--mk-think); }
.k-generating .mk-ico { color: var(--mk-gen); }
.k-retrieval.open .mk-ico { box-shadow: 0 0 0 3px color-mix(in srgb, var(--ac) 16%, transparent); }
.mk-name { flex: none; font-size: 11px; font-weight: 650; color: var(--fg); }
.mk-sum { min-width: 0; font-size: 9px; color: var(--fg-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mk-time { margin-left: auto; flex: none; font-family: var(--mono); font-size: 9px; color: var(--fg-3); font-variant-numeric: tabular-nums; }
.mk-mark { flex: none; font-size: 10px; color: var(--mk-gen); }
.mk-chev { flex: none; font-size: 9px; color: var(--fg-3); }
.mk-src-list {
  margin: 2px 0 2px 30px; padding-left: 8px;
  display: grid; gap: 5px;
  border-left: 2px solid color-mix(in srgb, var(--ac) 45%, transparent);
}
.mk-src {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 7px; border-radius: 7px;
  font-size: 9px; color: var(--fg-2);
  background: color-mix(in srgb, var(--ac) 8%, transparent);
  white-space: nowrap; overflow: hidden;
}
.mk-src-n { flex: none; font-family: var(--mono); font-size: 9px; font-style: normal; color: var(--ac); }
.mk-src-v { margin-left: auto; flex: none; font-family: var(--mono); font-size: 8px; font-style: normal; color: var(--fg-3); }
.mk-answer { font-size: 11px; line-height: 1.75; color: var(--fg-2); }
.mk-cite {
  font-family: var(--mono); font-size: 8px; line-height: 1; vertical-align: super;
  color: var(--ac); background: color-mix(in srgb, var(--ac) 14%, transparent);
  border-radius: 3px; padding: 0 3px; margin: 0 2px;
}

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
  .step { padding: 8px; border-radius: 20px; }
  .features .inner { gap: 14px; }
  .why .inner { padding: 26px 20px 28px; border-radius: 22px; }
  .why .lead { font-size: 15px; }
  .cards { gap: 14px; }
  .why-foot { margin-top: 28px; }
  /* 单栏时列宽会掉到视口宽：封顶 640 并居中，否则四块会拉成扁条 */
  .mock { width: 100%; max-width: 640px; justify-self: center; }
  .topbar { padding: 14px 18px; }
}

/* 手机竖屏：mock 只有 311–341px 宽，三栏与时间线的字要跟着缩一档，
   否则气泡会把一句话折断成两行、时间线摘要被省略号吃光 */
@media (max-width: 420px) {
  /* 三栏在 341px 上，问答栏只剩 83px —— 气泡会被折断成两行，把宽度让给它 */
  .mk-work-body { grid-template-columns: minmax(0, 0.7fr) minmax(0, 1.4fr) minmax(0, 1.1fr); }
  .mk-bubble { font-size: 10px; padding: 5px 7px; }
  .mk-bubble.user { max-width: 100%; }
  .mk-ch { gap: 4px; padding: 2px 4px; }
  .mk-ch-label { font-size: 9px; }
  .mk-ch-num { font-size: 8px; }
  .mk-name { font-size: 10px; }
  .mk-sum, .mk-time { font-size: 8px; }
  .mk-answer { font-size: 10px; }
  .mk-src { font-size: 8px; }
}

/* 减少动效时停掉，不是减慢——拨雾在脚本里就没挂，这里只管过渡 */
@media (prefers-reduced-motion: reduce) {
  .welcome { scroll-behavior: auto; }
  .askbox .block { animation: none; }
  .btn:hover { transform: none; }
  /* 流光停在起始角度，环还在，只是不跑 */
  .cards li::before { animation: none; }
}
</style>
