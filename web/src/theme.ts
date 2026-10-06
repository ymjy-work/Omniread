/**
 * 深浅主题：documents 根节点的 data-theme 就是唯一切换点（style.css 只认这个属性），
 * 所以状态放在模块级 ref，不经过任何全局状态管理。
 *
 * **主题要记住**：它是用户的偏好，刷新后回到默认等于每次都要重设一次。
 *
 * `index.html` 里还有一段内联脚本做同一件事，**那不是重复**：模块要等 bundle 加载完才跑，
 * 而 CSS 解析完到那时之间浏览器已经画了一帧——暗色用户每次刷新都会看到一道亮色闪。
 * 内联脚本在样式之前把属性设好，那段闪就没有了。键名与取值集合的权威定义在本文件，
 * 内联那份是时序上不得不复制的。
 */
import { ref, watch, watchEffect } from 'vue'
import { readStored, writeStored } from './storage'

export type ThemeName = 'light' | 'deep'

/** 与 `index.html` 内联脚本里那一份必须一致。 */
export const THEME_STORAGE_KEY = 'omniread.theme'

/** 取值白名单；内联脚本里同样是硬编码的两个字面量。 */
export const THEME_NAMES: readonly ThemeName[] = ['light', 'deep']

export const theme = ref<ThemeName>(
  readStored(THEME_STORAGE_KEY, THEME_NAMES, 'light')
)

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value
})

watch(theme, (value) => {
  writeStored(THEME_STORAGE_KEY, value)
})

export function toggleTheme(): void {
  theme.value = theme.value === 'light' ? 'deep' : 'light'
}
