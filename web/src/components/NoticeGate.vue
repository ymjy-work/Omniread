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
 * 外壳与交互交给 `AppDialog`——遮罩、层级、Esc、焦点圈都在那儿，这里只放内容。
 */
import { onMounted, ref } from 'vue'
import AppDialog from './AppDialog.vue'

const STORAGE_KEY = 'omniread.notice.v1'

const open = ref(false)

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

onMounted(() => {
  open.value = !readAcknowledged()
})
</script>

<template>
  <AppDialog :open="open" title="使用须知" :width="680" @close="acknowledge">
    <h2>先花一分钟读完</h2>
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
    <template #actions>
      <span class="hint">按 Esc 也可以关掉</span>
      <button class="dlg-btn primary notice-ok" @click="acknowledge">我已知悉</button>
    </template>
  </AppDialog>
</template>

<style scoped>
h2 { margin: 0; font-size: 22px; letter-spacing: -0.01em; }
ol { margin: 18px 0 0; padding: 0; list-style: none; counter-reset: n; }
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
.hint { margin-right: auto; font-size: 12px; color: var(--ink-3); }
/* 须知是「读完点确认」，主操作比通用弹窗按钮大一档 */
.notice-ok { font-size: 14px; font-weight: 600; padding: 9px 20px; }
</style>
