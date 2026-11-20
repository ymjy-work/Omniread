<script setup lang="ts">
import { computed } from 'vue'
import PublicHeader from '../components/PublicHeader.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const primaryTarget = computed(() => (auth.isAuthenticated ? '/library' : '/login?redirect=/library'))
const primaryText = computed(() => (auth.isAuthenticated ? '进入书库' : '开始阅读'))

const features = [
  {
    title: '读到哪，问到哪',
    body: '正文与问答同屏，停在任意一章直接提问。',
  },
  {
    title: '只答已读，不剧透',
    body: '检索范围按你的阅读进度截断，未读章节不进入答案。',
  },
  {
    title: '句句有出处',
    body: '回答附章节引用，一键跳回原文并高亮。',
  },
]
</script>

<template>
  <div class="landing-page">
    <PublicHeader />

    <main>
      <section class="hero-section">
        <div class="hero-copy">
          <h1>读到哪，聊到哪。</h1>
          <p class="hero-lead">
            问答就在正文旁边，只检索你读过的章节，每一句回答都能回到原文。
          </p>
          <div class="hero-actions">
            <RouterLink class="btn btn-primary hero-cta" :to="primaryTarget">{{ primaryText }}</RouterLink>
            <RouterLink class="btn hero-cta" to="/plans">看看套餐</RouterLink>
          </div>
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

      <section id="capabilities" class="features-section">
        <article v-for="feature in features" :key="feature.title" class="feature">
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.body }}</p>
        </article>
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

.hero-section {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  align-items: center;
  gap: clamp(28px, 5vw, 64px);
  min-height: calc(100dvh - var(--header-height) - 200px);
  padding: clamp(48px, 8vw, 96px) 0 clamp(48px, 7vw, 80px);
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
  max-width: 30rem;
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

.features-section {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-7);
  padding: var(--space-7) 0;
  border-top: 1px solid var(--border);
  scroll-margin-top: calc(var(--header-height) + var(--space-4));
}

.feature {
  padding-left: var(--space-4);
  border-left: 2px solid var(--border-strong);
}

.feature h3 {
  margin-bottom: var(--space-2);
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 600;
}

.feature p {
  color: var(--text-secondary);
  font-size: 13.5px;
  line-height: 1.8;
}

.landing-footer {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: var(--space-6) clamp(20px, 5vw, 64px);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
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

  .features-section {
    grid-template-columns: 1fr;
    gap: var(--space-5);
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

  .landing-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .footer-nav {
    flex-wrap: wrap;
  }
}
</style>
