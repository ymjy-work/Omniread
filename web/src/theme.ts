/**
 * 深浅主题：documents 根节点的 data-theme 就是唯一切换点（style.css 只认这个属性），
 * 所以状态放在模块级 ref，不经过任何全局状态管理。
 */
import { ref, watchEffect } from 'vue'

export type ThemeName = 'light' | 'deep'

export const theme = ref<ThemeName>('light')

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value
})

export function toggleTheme(): void {
  theme.value = theme.value === 'light' ? 'deep' : 'light'
}
