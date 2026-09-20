// Vue 官方那套（flat config）：eslint-plugin-vue 的 essential 规则 + typescript-eslint recommended。
// 只保留查错规则，排版交给编辑器；type-aware 规则需要 project service，M0 不引入。
import pluginVue from 'eslint-plugin-vue'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'

export default defineConfigWithVueTs(
  {
    name: 'omniread/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}']
  },
  {
    name: 'omniread/files-to-ignore',
    ignores: ['dist/**', 'node_modules/**']
  },
  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended
)
