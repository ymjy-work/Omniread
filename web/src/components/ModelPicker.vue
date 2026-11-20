<script setup lang="ts">
import { computed, onMounted } from 'vue'
import ByokPanel from './ByokPanel.vue'
import { useAccountStore } from '../stores/account'
import { useReaderStore } from '../stores/reader'
import { BYOK_PROVIDERS } from '../utils/billing'
import type { ApiProvider } from '../types/account'
import type { ChatSurface } from '../types/chat'

const props = withDefaults(defineProps<{ wide?: boolean }>(), { wide: false })

const account = useAccountStore()
const reader = useReaderStore()

const planReady = computed(() => Boolean(account.account))
const canPlatform = computed(() => planReady.value && account.plan !== 'free')
const keyLoading = computed(() => account.keysLoading && !account.keysLoaded)
const activeKey = computed(() => account.apiKeys.find((item) => item.provider === reader.provider))
const pulledCount = computed(() => reader.pulledModels[reader.provider]?.length ?? 0)
const pullDisabled = computed(
  () =>
    !activeKey.value ||
    keyLoading.value ||
    reader.providerModelsLoading ||
    reader.asking,
)

onMounted(() => {
  if (!account.account && !account.loading) void account.fetchAccount()
  if (!account.keysLoaded && !account.keysLoading) void account.fetchApiKeys()
  if (reader.surface === 'official' && canPlatform.value) void reader.loadPlatformModels()
})

function chooseSurface(next: ChatSurface) {
  reader.setSurface(next)
  if (next === 'official' && canPlatform.value) void reader.loadPlatformModels()
}

function onPlatformChange(event: Event) {
  reader.setModel((event.target as HTMLSelectElement).value)
}

function onProviderChange(event: Event) {
  reader.setProvider((event.target as HTMLSelectElement).value as ApiProvider)
}

function onModelChange(event: Event) {
  reader.setModel((event.target as HTMLSelectElement).value)
}

function pullModels() {
  if (pullDisabled.value) return
  void reader.loadProviderModels()
}
</script>

<template>
  <div class="model-picker" :class="{ wide: props.wide }">
    <div class="surface-switch" role="group" aria-label="回答来源">
      <button
        type="button"
        :class="{ active: reader.surface === 'official' }"
        :aria-pressed="reader.surface === 'official'"
        :disabled="reader.asking"
        @click="chooseSurface('official')"
      >
        官方
      </button>
      <button
        type="button"
        :class="{ active: reader.surface === 'self' }"
        :aria-pressed="reader.surface === 'self'"
        :disabled="reader.asking"
        @click="chooseSurface('self')"
      >
        自己
      </button>
    </div>

    <template v-if="reader.surface === 'official'">
      <template v-if="!planReady">
        <span v-if="account.error" class="pick-note error">
          账户加载失败
          <button class="pick-link" type="button" @click="account.fetchAccount(true)">重试</button>
        </span>
        <span v-else class="pick-note">账户信息加载中…</span>
      </template>

      <span v-else-if="account.plan === 'free'" class="auto-pill" title="Free 档仅自动路由">
        auto
      </span>

      <template v-else-if="reader.modelsLoading">
        <span class="spinner sm"></span>
        <span class="pick-note">加载模型</span>
      </template>

      <template v-else-if="reader.modelsError">
        <span class="pick-note error">模型加载失败</span>
        <button class="pick-btn" type="button" @click="reader.loadPlatformModels(true)">
          重试
        </button>
      </template>

      <template v-else-if="reader.platformModels.length > 0">
        <select
          class="pick-select model-select"
          :value="reader.model"
          aria-label="平台模型"
          :disabled="reader.asking"
          @change="onPlatformChange"
        >
          <option value="">选择模型</option>
          <option
            v-for="item in reader.platformModels"
            :key="`${item.provider}-${item.model}`"
            :value="item.model"
          >
            {{ item.displayName || item.model }}
          </option>
        </select>
        <button
          class="pick-btn"
          type="button"
          :disabled="reader.modelsLoading || reader.asking"
          @click="reader.loadPlatformModels(true)"
        >
          刷新
        </button>
      </template>

      <button
        v-else
        class="pick-btn"
        type="button"
        :disabled="reader.asking"
        @click="reader.loadPlatformModels(true)"
      >
        加载模型
      </button>
    </template>

    <template v-else>
      <div class="self-panel">
        <div class="self-row">
          <span class="field-label">Key</span>
          <select
            class="pick-select provider-select"
            :value="reader.provider"
            aria-label="BYOK 提供商"
            :disabled="reader.asking"
            @change="onProviderChange"
          >
            <option v-for="item in BYOK_PROVIDERS" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
          <span v-if="keyLoading" class="key-pill">读取中…</span>
          <span v-else class="key-pill" :class="{ missing: !activeKey }">
            {{ activeKey?.keyMask || '未配置' }}
          </span>
        </div>

        <div class="self-row model-row">
          <span class="field-label">模型</span>
          <select
            class="pick-select model-select"
            :value="reader.model"
            aria-label="BYOK 模型"
            :disabled="reader.asking"
            @change="onModelChange"
          >
            <option v-for="item in reader.availableModels" :key="item" :value="item">
              {{ item }}
            </option>
          </select>
          <button
            class="pick-btn"
            type="button"
            :disabled="pullDisabled"
            :title="!activeKey ? '先保存 Key 再拉取' : undefined"
            @click="pullModels"
          >
            <span v-if="reader.providerModelsLoading" class="spinner sm"></span>
            {{
              reader.providerModelsLoading
                ? '拉取中…'
                : pulledCount > 0
                  ? '刷新'
                  : reader.providerModelsError
                    ? '重试'
                    : '拉取'
            }}
          </button>
        </div>

        <ByokPanel />

        <p
          v-if="reader.providerModelsError"
          class="pick-note error provider-status"
          role="status"
        >
          {{ reader.providerModelsError }}
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.model-picker {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-width: 0;
  max-width: 100%;
}

.surface-switch {
  display: flex;
  flex: none;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.surface-switch button {
  padding: 2px 7px;
  border: none;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1.4;
}

.surface-switch button.active {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: var(--shadow-sm);
}

.surface-switch button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.pick-select {
  min-width: 0;
  width: auto;
  height: 24px;
  padding: 1px 5px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 10.5px;
}

.pick-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.provider-select {
  max-width: 90px;
}

.model-select {
  max-width: 160px;
}

.self-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  min-width: 0;
  padding-top: 6px;
  border-top: 1px dashed var(--border);
}

.self-row {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.field-label {
  flex: none;
  width: 30px;
  color: var(--text-muted);
  font-size: 9.5px;
}

.model-row .model-select {
  flex: 1;
  max-width: none;
}

.key-pill {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 9.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.key-pill.missing {
  color: var(--warning);
}

.pick-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: none;
  height: 24px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: 10.5px;
  white-space: nowrap;
}

.pick-btn:hover:not(:disabled) {
  border-color: var(--border-strong);
  color: var(--text);
}

.pick-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pick-note {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pick-note.error {
  color: var(--danger);
}

.auto-pill {
  padding: 1px 7px;
  border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 10px;
}

.provider-status {
  width: 100%;
  white-space: normal;
}

.model-picker.wide {
  gap: var(--space-2);
}

.model-picker.wide .pick-select {
  height: 32px;
  padding: 4px 8px;
  font-size: var(--text-sm);
}

.model-picker.wide .provider-select {
  max-width: 130px;
}

.model-picker.wide .model-select {
  max-width: 230px;
}

.model-picker.wide .pick-btn {
  height: 32px;
  padding: 0 10px;
  font-size: var(--text-sm);
}

.model-picker.wide .surface-switch button {
  padding: 4px 12px;
  font-size: var(--text-sm);
}

.model-picker.wide .pick-note {
  font-size: var(--text-sm);
}

.model-picker.wide .self-panel {
  gap: var(--space-2);
  padding-top: var(--space-2);
}

.model-picker.wide .self-row {
  gap: var(--space-2);
}

.model-picker.wide .field-label,
.model-picker.wide .key-pill {
  font-size: var(--text-sm);
}
</style>
