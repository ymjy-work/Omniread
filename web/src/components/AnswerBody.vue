<script setup lang="ts">
/**
 * 回答正文：把 `buildAnswerView` 产出的块结构渲染成 DOM。
 *
 * 拆成独立组件是为了让块级排版（标题/列表/引用块/代码块的缩进与间距）
 * 与 `.ans-text` 上的流式光标（`::after`）互不牵连。
 *
 * 切分口径全在 `markdown.ts`，这里只排版；角标跳章上抛给 ChatPanel
 * （它才拿得到 `bookId` 与路由）。
 */
import { computed } from 'vue'
import InlineRuns from './InlineRuns.vue'
import { buildAnswerView } from '../markdown'
import type { MdViewBlock } from '../markdown'
import type { ContextChapter } from '../types'

const props = defineProps<{
  text: string
  citations: ContextChapter[]
  /** 引用集合是否已下发；未下发时角标只报章号，不做越界断言 */
  citationsReady: boolean
}>()

const emit = defineEmits<{ jump: [chapterIndex: number] }>()

/**
 * 每次正文变化重算一次（流式下每个 delta 一次）。
 *
 * 整段重算是刻意的：增量解析要额外维护「半个围栏 / 半条列表 / 未闭合 `**`」的
 * 跨帧状态，而这类状态机正是 bug 的来源。回答正文只有几百到几千字，
 * 整段重算的成本远低于维护它的风险。
 */
const blocks = computed<MdViewBlock[]>(() => buildAnswerView(props.text))

const titles = computed<ReadonlyMap<number, string>>(() => {
  const map = new Map<number, string>()
  for (const citation of props.citations) map.set(citation.chapter_index, citation.chapter_title)
  return map
})
</script>

<template>
  <template v-for="(block, blockIndex) in blocks" :key="blockIndex">
    <ul v-if="block.tag === 'ul'">
      <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
        <InlineRuns :runs="item" :titles="titles" :citations-ready="citationsReady" @jump="emit('jump', $event)" />
      </li>
    </ul>
    <ol v-else-if="block.tag === 'ol'">
      <!-- `value` 还原源编号：不挂它时 <ol> 一律从 1 重排，「3.」会显示成「1.」 -->
      <li v-for="(item, itemIndex) in block.items" :key="itemIndex" :value="block.numbers[itemIndex]">
        <InlineRuns :runs="item" :titles="titles" :citations-ready="citationsReady" @jump="emit('jump', $event)" />
      </li>
    </ol>
    <hr v-else-if="block.tag === 'hr'" />
    <!--
      代码块内部不再排版：围栏里的换行与缩进都是正文的一部分。
      仍走 InlineRuns 是为了角标逻辑只有一份——代码块里出现引用是违规写法，
      但按既定口径「只用于扫描与渲染，不是净化」，它照样显示、照样能点。
    -->
    <pre v-else-if="block.tag === 'pre'"><code><InlineRuns :runs="block.runs" :titles="titles" :citations-ready="citationsReady" @jump="emit('jump', $event)" /></code></pre>
    <component :is="block.tag" v-else>
      <InlineRuns :runs="block.runs" :titles="titles" :citations-ready="citationsReady" @jump="emit('jump', $event)" />
    </component>
  </template>
</template>
