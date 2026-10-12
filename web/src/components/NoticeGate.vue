<script setup lang="ts">
/**
 * 使用须知：**进入功能页之后**弹一次，看完点掉就不再出现（记在 localStorage）。
 *
 * 它不在介绍页上——那页是给人看「这是什么」的，把八条须知压在那儿等于把门厅变成公告栏。
 * 须知要出现在**用户已经开始用**的时候，那时它才有对象。
 *
 * **一次就够**：同一台机器认过一次就不再弹。这是「看完即走」的提示，不是每次进来都要点的协议。
 * 键名带版本号（`.v1`）：将来须知真的改了，改版本号就能让它重新弹一次。
 *
 * 关于登录：现在还没有登录表单（F1 未做），所以触发点是「进入功能页」；
 * 等登录做完，触发点改成「刚登录成功」即可，这个组件不用动。
 */
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const STORAGE_KEY = 'omniread.notice.v1'

const open = ref(false)
const okButton = ref<HTMLButtonElement | null>(null)

/**
 * 权利人联系方式**只进配置，不入代码与仓库**（`deploy-plan` P4）。
 * 仓库里这一项是空的，部署构建时用 `VITE_RIGHTS_CONTACT` 注入。
 */
const contact = String(import.meta.env.VITE_RIGHTS_CONTACT ?? '').trim()

function readAcknowledged(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'ack'
  } catch {
    // 存储不可用（隐私模式）时**照样弹**：须知宁可多看一次，也不能因为存不下就不给人看
    return false
  }
}

function acknowledge(): void {
  try {
    localStorage.setItem(STORAGE_KEY, 'ack')
  } catch {
    // 记不住就下次再弹，不因此挡住入口
  }
  open.value = false
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    acknowledge()
    return
  }
  // 弹窗里只有一个可聚焦元素，Tab / Shift+Tab 一律留在它上面。
  // 不做这一步，焦点会走到被遮罩整个盖住的背景控件上——而 `aria-modal` 声明它是模态，
  // 那就成了一句谎话（键盘用户会对看不见的按钮操作）。
  if (event.key === 'Tab') {
    event.preventDefault()
    okButton.value?.focus()
  }
}

onMounted(() => {
  open.value = !readAcknowledged()
  if (!open.value) return
  window.addEventListener('keydown', onKeydown)
  // 显式 focus 而不是靠 `autofocus` 属性：元素是挂载之后才插进 DOM 的，
  // 部分浏览器（Safari）对这种情况不执行 autofocus。
  void nextTick(() => okButton.value?.focus())
})

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Transition name="fade">
    <div v-if="open" class="scrim" role="dialog" aria-modal="true" aria-labelledby="notice-title">
      <div class="card">
        <p class="eyebrow">使用须知</p>
        <h2 id="notice-title">先花一分钟读完</h2>
        <ol>
          <li>本站为个人学习与技术演示项目，仅供面试沟通与技术评估，不得用于商业用途。</li>
          <li>
            阅读页只提供《不时轻声地以俄语遮羞的邻座艾莉同学》第 1 卷的原文；
            问答基于全书语料作答，回答可能涉及阅读页未提供的章节内容。
          </li>
          <li>上述文本为已出版小说的原文，版权归原作者及出版方所有。</li>
          <li>访问账户由开发者发放，请勿转让或共享账户。</li>
          <li>请勿下载、转载、抓取或批量导出站内内容。</li>
          <li>站点记录登录与使用次数（<b>不记录口令</b>），用于安全与用量管理。</li>
          <li>回答由 AI 生成，可能存在错误，请以原文为准。</li>
          <li>
            权利人如认为本站侵犯其权益，请联系
            <template v-if="contact"><a :href="`mailto:${contact}`">{{ contact }}</a></template>
            <span v-else class="tbd">（联系方式见站点配置）</span>；
            收到通知后，站点将尽快停止相关内容的提供。
          </li>
        </ol>
        <div class="foot">
          <button ref="okButton" class="ok" @click="acknowledge">我已知悉</button>
          <span class="hint">按 Esc 也可以关掉</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.scrim {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(8, 12, 24, 0.5);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.card {
  width: min(680px, 100%);
  max-height: min(84vh, 100%);
  overflow-y: auto;
  padding: 30px 32px 24px;
  border-radius: 18px;
  background: var(--glass);
  backdrop-filter: blur(22px) saturate(150%);
  -webkit-backdrop-filter: blur(22px) saturate(150%);
  border: 1px solid var(--stroke);
  box-shadow: 0 40px 90px -40px rgba(10, 16, 40, 0.7);
}
.eyebrow {
  margin: 0;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.2em;
  color: var(--ink-3);
}
h2 { margin: 10px 0 0; font-size: 22px; letter-spacing: -0.01em; }
ol { margin: 20px 0 0; padding: 0; list-style: none; counter-reset: n; }
li {
  counter-increment: n;
  position: relative;
  padding: 11px 0 11px 38px;
  border-top: 1px solid var(--stroke-2);
  font-size: 13.5px;
  line-height: 1.85;
  color: var(--ink-2);
  text-wrap: pretty;
}
li::before {
  content: counter(n, decimal-leading-zero);
  position: absolute;
  left: 0;
  top: 12px;
  font-family: var(--mono);
  font-size: 12px;
  /* 序号是**导航**（第几条），不是装饰：--ink-3 的 11px 在浅玻璃上读不出来 */
  color: var(--ink-2);
}
li b { color: var(--ink); }
a { color: var(--accent); }
/* 这一行是**联系方式**的说明，不是装饰：--ink-3 在浅玻璃上约 2.2:1，够不上 AA。
   （同 ChatPanel 那条等待行的教训：信号类文字一律用 --ink-2。） */
.tbd { color: var(--ink-2); }
.foot { display: flex; align-items: center; gap: 14px; margin-top: 22px; }
.ok {
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  padding: 10px 22px;
  border-radius: 11px;
  border: 0;
  cursor: pointer;
  color: #fff;
  background: linear-gradient(135deg, #6d7bff, #b76bff);
  box-shadow: 0 14px 30px -16px rgba(90, 90, 255, 0.8);
}
.hint { font-size: 12px; color: var(--ink-3); }

.fade-enter-active, .fade-leave-active { transition: opacity 0.22s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) {
  .fade-enter-active, .fade-leave-active { transition: none; }
}
</style>
