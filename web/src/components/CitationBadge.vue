<script setup lang="ts">
import type { Citation } from '../types/chat'

defineProps<{ citation: Citation; index: number }>()
const emit = defineEmits<{ select: [citation: Citation] }>()
</script>

<template>
  <button
    class="citation-badge"
    type="button"
    :title="`${citation.title}：${citation.quote}`"
    @click="emit('select', citation)"
  >
    <span class="badge-index">{{ index + 1 }}</span>
    <span class="badge-title">{{ citation.title }}</span>
  </button>
</template>

<style scoped>
.citation-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 3px 8px 3px 3px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 11.5px;
  line-height: 1.4;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.citation-badge:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
}

.badge-index {
  display: grid;
  place-items: center;
  width: 17px;
  height: 17px;
  flex: none;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
}

.badge-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
}
</style>