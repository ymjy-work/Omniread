<script setup lang="ts">
/**
 * 一段行内内容：粗体 / 行内代码 / 引用角标。
 *
 * 三种标签用同一个循环渲染，不拆三份——拆了就要同步维护三遍角标逻辑，
 * 而角标逻辑恰恰是最不该有分歧的地方（点击、悬停文案、越界提示）。
 *
 * 引用标记不在这层切：`segments` 已由 `markdown.ts` 过 `citationSegments` 切好，
 * 与阅读页共用同一份口径。跳章由父级接手——它才拿得到 `bookId` 与路由。
 */
import type { MdRun } from '../markdown'

const props = defineProps<{
  runs: MdRun[]
  /** 角标编号 → 章节标题，用于拼悬停文案 */
  titles: ReadonlyMap<number, string>
  /** 引用集合是否已下发；未下发时只报章号，不做越界断言 */
  citationsReady: boolean
}>()

const emit = defineEmits<{ jump: [chapterIndex: number] }>()

/**
 * 悬停文案。
 *
 * 「全书第 N 章」这几个字不能省：`[C数字]` 用全书连续序号（1..193），
 * 而章节标题里的「第N话」按卷重新编号——全书第 7 章的标题恰好写着「第6话」。
 * 只说「第 7 章」会被读成「第七话」，点过去看到的是另一段剧情。
 *
 * 引用集合未下发前（流式进行中）**不做越界断言**：服务端顺序是
 * 「全部 answer_delta → citation_ready」，此刻 citations 必然是空的，
 * 断言「本次上下文里没有这一章」就是把还没收到说成不存在。
 */
function titleOf(chapterIndex: number | null): string {
  if (chapterIndex === null) return ''
  const title = props.titles.get(chapterIndex)
  if (title !== undefined) return `全书第 ${chapterIndex} 章 · ${title}`
  if (!props.citationsReady) return `全书第 ${chapterIndex} 章`
  return `全书第 ${chapterIndex} 章 · 本次上下文里没有这一章（越界引用）`
}
</script>

<template>
  <template v-for="(run, runIndex) in runs" :key="runIndex">
    <component :is="run.tag">
      <template v-for="(segment, segmentIndex) in run.segments" :key="segmentIndex">
        <sup
          v-if="segment.kind === 'citation'"
          class="cite-an"
          :title="titleOf(segment.chapterIndex)"
          @click="emit('jump', segment.chapterIndex ?? 0)"
          >{{ segment.chapterIndex }}</sup
        ><template v-else>{{ segment.text }}</template>
      </template>
    </component>
  </template>
</template>
