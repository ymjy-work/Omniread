<script setup lang="ts">
import { computed } from 'vue'
import PublicHeader from '../components/PublicHeader.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const primaryTarget = computed(() => (auth.isAuthenticated ? '/library' : '/login?redirect=/library'))
const primaryText = computed(() => (auth.isAuthenticated ? '进入书库' : '开始阅读'))

const capabilities = [
  {
    no: '01',
    title: '读到哪，问到哪',
    body: '正文在左，对话在右。停在任意一章，直接问这一章，不用离开页面，也不用把整本书复制给谁。',
  },
  {
    no: '02',
    title: '只答已读，不剧透',
    body: '已读模式按你的阅读进度截断检索范围。没读到的章节不会成为答案，也不会出现在引用里。',
  },
  {
    no: '03',
    title: '每一句，都能回到原文',
    body: '回答附章节引用与原文片段。点一下跳到那一章并高亮；找不到依据时，它会直接说不知道。',
  },
]

const steps = ['打开一本书', '停在读到的地方', '就这一章提问', '点引用回到原文']

const teaserPlans = [
  { name: 'Free', price: '¥0', credits: '100 积分', featured: false },
  { name: 'Plus', price: '¥20', credits: '500 积分', featured: false },
  { name: 'Pro', price: '¥60', credits: '2,000 积分', featured: true },
  { name: 'Ultra', price: '¥100', credits: '4,000 积分', featured: false },
]
</script>

<template>
  <div class="landing-page">
    <PublicHeader />

    <main>
      <section class="hero-section">
        <div class="hero-copy">
          <p class="eyebrow">轻小说 · 沉浸阅读 · 文中问答</p>
          <h1>读到哪，聊到哪。</h1>
          <p class="hero-lead">
            一本长篇，读到一半总会卡住：这个人是谁、前面提过什么、她为什么这样回答。Omniread
            把问答放在正文旁边，只在你读过的章节里找答案，每一句回答都能回到原文。
          </p>
          <div class="hero-actions">
            <RouterLink class="btn btn-primary hero-cta" :to="primaryTarget">{{ primaryText }}</RouterLink>
            <RouterLink class="btn hero-cta" to="/plans">看看套餐</RouterLink>
          </div>
          <p class="hero-note">不剧透 · 引用可回原文 · 支持自己的模型</p>
        </div>

        <div class="reading-scene" aria-label="阅读与文中问答示意">
          <div class="paper" aria-hidden="true">
            <span class="paper-rule"></span>
            <p>雨停以后，旧书店的灯还亮着。她把伞收在门边，听见楼上有人轻轻翻书。</p>
            <p>
              “你来得正好。”店主没有抬头，只把一只信封推到桌沿。信封上没有署名，只有一枚已经褪色的
              <mark>朱砂印</mark>。
            </p>
            <p class="paper-short">她忽然想起，自己似乎在哪里见过这枚印记。</p>
          </div>

          <div class="qa-card">
            <div class="qa-head">
              <strong>文中助手</strong>
              <span class="read-pill">已读</span>
            </div>
            <div class="qa-user">这一章里，谁第一次出现？</div>
            <div class="qa-answer">
              这一章里，新转来的同学第一次出场；前文只提过她的名字，没有正面描写。
            </div>
            <div class="qa-citations">
              <button class="citation-chip" type="button" tabindex="-1">
                <span class="citation-square">1</span>
                <span>第 2 章</span>
              </button>
              <button class="citation-chip" type="button" tabindex="-1">
                <span class="citation-square">2</span>
                <span>第 5 章</span>
              </button>
            </div>
            <div class="fake-composer">
              <span>就这一章提问…</span>
              <span class="fake-send" aria-hidden="true">
                <svg viewBox="0 0 20 20" width="13" height="13" fill="none">
                  <path d="M3.5 10h11M10 5.5l4.5 4.5-4.5 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </span>
            </div>
          </div>
        </div>
      </section>

      <section id="capabilities" class="capabilities-section">
        <header class="section-head">
          <p class="eyebrow">为什么是 Omniread</p>
          <h2>把阅读留在正文里</h2>
        </header>
        <div class="capability-grid">
          <article v-for="item in capabilities" :key="item.no" class="capability">
            <span class="capability-no">{{ item.no }}</span>
            <h3>{{ item.title }}</h3>
            <p>{{ item.body }}</p>
          </article>
        </div>
      </section>

      <section class="steps-section">
        <header class="section-head">
          <p class="eyebrow">怎么用</p>
          <h2>四步，不打断阅读</h2>
        </header>
        <ol class="step-list">
          <li v-for="(step, index) in steps" :key="step">
            <span class="step-no">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="step-text">{{ step }}</span>
          </li>
        </ol>
      </section>

      <section class="pricing-section">
        <div class="pricing-copy">
          <p class="eyebrow">定价</p>
          <h2>从 Free 开始</h2>
          <p>每月 100 积分，够读几十次。需要更多，再换 Plus 或 Pro。</p>
        </div>
        <div class="pricing-teaser">
          <div
            v-for="plan in teaserPlans"
            :key="plan.name"
            class="teaser-item"
            :class="{ featured: plan.featured }"
          >
            <span v-if="plan.featured" class="featured-tag">常用</span>
            <strong>{{ plan.name }}</strong>
            <span class="teaser-price">{{ plan.price }}</span>
            <span class="teaser-credits">{{ plan.credits }}</span>
          </div>
        </div>
        <RouterLink class="pricing-link" to="/plans">查看完整套餐 →</RouterLink>
      </section>
    </main>

    <footer class="landing-footer">
      <div class="footer-brand">
        <span class="brand-mark">阅</span>
        <div>
          <strong>Omniread</strong>
          <p>读到哪，聊到哪。</p>
        </div>
      </div>
      <nav class="footer-nav" aria-label="页脚导航">
        <RouterLink to="/#capabilities">产品</RouterLink>
        <RouterLink to="/plans">定价</RouterLink>
        <RouterLink to="/login">登录</RouterLink>
      </nav>
      <p class="footer-note">仅用于个人阅读与学习；语料版权归原作者与出版方所有。</p>
    </footer>
  </div>
</template>

<style scoped>
.landing-page {
  min-height: 100dvh;
  background:
    radial-gradient(circle at 78% 8%, var(--accent-soft), transparent 34%),
    var(--bg);
}

main {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: 0 clamp(20px, 5vw, 64px);
}

.eyebrow {
  margin-bottom: var(--space-3);
  font-size: var(--text-xs);
  letter-spacing: 0.2em;
  color: var(--text-muted);
}

.hero-section {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  align-items: center;
  gap: clamp(28px, 5vw, 64px);
  min-height: calc(100dvh - var(--header-height));
  padding: clamp(48px, 8vw, 96px) 0;
}

.hero-copy h1 {
  font-family: var(--font-serif);
  font-size: var(--text-display);
  font-weight: 600;
  line-height: 1.18;
  letter-spacing: 0.01em;
  text-wrap: balance;
}

.hero-lead {
  max-width: 34rem;
  margin-top: var(--space-5);
  color: var(--text-secondary);
  font-family: var(--font-serif);
  font-size: 17px;
  line-height: 1.9;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-6);
}

.hero-cta {
  min-width: 112px;
  height: 42px;
  padding: 0 var(--space-5);
  font-size: 14px;
}

.hero-note {
  margin-top: var(--space-4);
  color: var(--text-muted);
  font-size: var(--text-sm);
  letter-spacing: 0.02em;
}

.reading-scene {
  position: relative;
  min-height: 460px;
  padding: 28px 0 0;
}

.paper {
  position: relative;
  width: min(100%, 370px);
  aspect-ratio: 3 / 4;
  padding: var(--space-6);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-md);
  transform: rotate(-0.6deg);
}

.paper-rule {
  display: block;
  width: 36px;
  height: 2px;
  margin-bottom: var(--space-5);
  background: var(--accent);
}

.paper p {
  margin-bottom: 0.9em;
  color: var(--reader-text);
  font-family: var(--font-serif);
  font-size: 15px;
  line-height: 1.9;
  text-align: justify;
  text-indent: 2em;
}

.paper mark {
  padding: 0 2px;
  border-radius: 2px;
  background: var(--quote-bg);
  color: inherit;
}

.paper-short {
  opacity: 0.72;
}

.qa-card {
  position: absolute;
  top: 150px;
  right: 0;
  z-index: 2;
  width: min(300px, 78%);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-md);
  transform: rotate(0.4deg);
  transition: transform var(--dur) var(--ease-out);
}

.qa-card:hover {
  transform: translateY(-2px) rotate(0.4deg);
}

.qa-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.qa-head strong {
  font-size: 14px;
}

.read-pill {
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 10px;
}

.qa-user {
  margin-left: auto;
  max-width: 92%;
  padding: 8px 10px;
  border-radius: var(--radius-md) var(--radius-md) var(--radius-xs) var(--radius-md);
  background: var(--accent-soft);
  color: var(--text);
  font-size: 12.5px;
  line-height: 1.65;
}

.qa-answer {
  margin-top: var(--space-2);
  max-width: 96%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md) var(--radius-md) var(--radius-md) var(--radius-xs);
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 12.5px;
  line-height: 1.7;
}

.qa-citations {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px dashed var(--border);
}

.citation-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11.5px;
}

.citation-square {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: var(--radius-xs);
  background: var(--accent);
  color: #fffdf8;
  font-size: 10px;
  font-weight: 600;
}

.fake-composer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: var(--space-3);
  padding: 7px 8px 7px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  color: var(--text-muted);
  font-size: 11.5px;
}

.fake-send {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-xs);
  background: var(--accent);
  color: #fffdf8;
}

.capabilities-section,
.steps-section {
  padding: var(--space-8) 0;
  border-top: 1px solid var(--border);
  scroll-margin-top: calc(var(--header-height) + var(--space-4));
}

.section-head {
  margin-bottom: var(--space-6);
}

.section-head h2 {
  font-family: var(--font-serif);
  font-size: var(--text-xl);
  font-weight: 600;
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-6);
}

.capability-no {
  display: block;
  margin-bottom: var(--space-3);
  color: var(--accent);
  font-family: var(--font-serif);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.capability h3 {
  margin-bottom: var(--space-2);
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 600;
}

.capability p {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.8;
}

.step-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.step-list li {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-strong);
}

.step-no {
  color: var(--accent);
  font-size: var(--text-xs);
  font-variant-numeric: tabular-nums;
}

.step-text {
  font-size: 14px;
}

.pricing-section {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: var(--space-6) var(--space-8);
  align-items: center;
  margin: var(--space-6) 0 var(--space-8);
  padding: var(--space-6);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-2);
  scroll-margin-top: calc(var(--header-height) + var(--space-4));
}

.pricing-copy h2 {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 600;
}

.pricing-copy > p:last-child {
  margin-top: var(--space-3);
  color: var(--text-secondary);
  font-size: 13.5px;
  line-height: 1.8;
}

.pricing-teaser {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-2);
}

.teaser-item {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.teaser-item.featured {
  border-color: var(--accent);
}

.featured-tag {
  position: absolute;
  top: -9px;
  right: 8px;
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: var(--accent);
  color: #fffdf8;
  font-size: 9.5px;
}

.teaser-item strong {
  font-size: 13px;
}

.teaser-price {
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 600;
}

.teaser-credits {
  color: var(--text-muted);
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}

.pricing-link {
  grid-column: 2;
  justify-self: start;
  color: var(--accent);
  font-size: 13px;
}

.landing-footer {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: var(--space-7) clamp(20px, 5vw, 64px) var(--space-6);
  border-top: 1px solid var(--border);
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--space-4) var(--space-6);
}

.footer-brand {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: var(--bg);
  font-family: var(--font-serif);
  font-size: 17px;
}

.footer-brand strong {
  font-size: 14px;
}

.footer-brand p {
  margin-top: 2px;
  color: var(--text-muted);
  font-family: var(--font-serif);
  font-size: 12.5px;
}

.footer-nav {
  display: flex;
  gap: var(--space-4);
  color: var(--text-secondary);
  font-size: 12.5px;
}

.footer-nav a:hover {
  color: var(--accent);
}

.footer-note {
  grid-column: 1 / -1;
  color: var(--text-muted);
  font-size: var(--text-xs);
}

@media (max-width: 900px) {
  .hero-section {
    grid-template-columns: 1fr;
    min-height: 0;
    padding-top: var(--space-8);
  }

  .reading-scene {
    min-height: 0;
    padding-top: 0;
  }

  .paper {
    width: min(100%, 400px);
  }

  .qa-card {
    position: relative;
    top: auto;
    right: auto;
    width: min(100%, 400px);
    margin: -36px auto 0 auto;
    transform: rotate(0.4deg);
  }

  .capability-grid {
    grid-template-columns: 1fr;
    gap: var(--space-5);
  }

  .step-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pricing-section {
    grid-template-columns: 1fr;
  }

  .pricing-link {
    grid-column: 1;
  }
}

@media (max-width: 620px) {
  .hero-copy h1 {
    font-size: clamp(34px, 11vw, 48px);
  }

  .hero-lead {
    font-size: 15.5px;
  }

  .paper {
    padding: var(--space-5);
  }

  .paper p:nth-child(3) {
    display: none;
  }

  .pricing-teaser {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .step-list {
    grid-template-columns: 1fr;
  }

  .landing-footer {
    grid-template-columns: 1fr;
  }

  .footer-nav {
    flex-wrap: wrap;
  }
}
</style>