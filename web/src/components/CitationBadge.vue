<script setup lang="ts">
import { computed } from 'vue'
import type { Citation } from '../types/chat'

const props = defineProps<{ citation: Citation; index: number }>()
const emit = defineEmits<{ select: [citation: Citation] }>()

const label = computed(
  () => `第 ${props.citation.chapterIndex + 1} 章 ${props.citation.title}：${props.citation.quote}`,
)
</script>

<template>
  <button
    class="citation-badge"
    type="button"
    :title="label"
    :aria-label="`跳到${label}`"
    @click="emit('select', citation)"
  >
    <span class="badge-index">{{ index + 1 }}</span>
    <span class="badge-chapter">第 {{ citation.chapterIndex + 1 }} 章</span>
  </button>
</template>

<style scoped>
.citation-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 2px 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--text-secondary);
  font-size: 11.5px;
  line-height: 1.5;
  transition: background-color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.citation-badge:hover,
.citation-badge:focus-visible {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
}

.badge-index {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  flex: none;
  border-radius: var(--radius-xs);
  background: var(--accent);
  color: #fffdf8;
  font-size: 10px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.badge-chapter {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
}
</style>