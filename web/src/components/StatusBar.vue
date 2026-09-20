<script setup lang="ts">
/** 底部状态栏：当前书、问答档位、阅读进度，以及最近一次错误的错误码 */
import { chapterCount, currentBook, store } from '../store'
</script>

<template>
  <div class="statusbar">
    <span>Omniread · Web</span>
    <span>{{ currentBook?.title ?? '未选书' }}</span>
    <span>档位：{{ store.level === 'past' ? '回顾' : '剧透' }}</span>
    <span v-if="store.error" style="color: var(--danger)">{{ store.error }}</span>
    <span class="r">进度 {{ store.progress?.max_seq ?? 0 }}/{{ chapterCount }}</span>
  </div>
</template>
