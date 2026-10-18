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

export type ThemeName = 'light' | 'deep' | 'violet'

/** 与 `index.html` 内联脚本里那一份必须一致。 */
export const THEME_STORAGE_KEY = 'omniread.theme'

/** 取值白名单；内联脚本里同样是硬编码的那几个字面量。 */
export const THEME_NAMES: readonly ThemeName[] = ['light', 'deep', 'violet']

/** 按钮点一下换到哪个、以及按钮上怎么称呼它。加主题只改这一张表。 */
const THEME_LABELS: Record<ThemeName, string> = {
  light: '浅色',
  deep: '深色',
  violet: '深紫'
}

/**
 * **功能页面（主界面）的默认主题**：介绍页那套深墨 + 紫罗兰。
 * 门厅自己不看这个——它自带配色，不跟随主题（见 WelcomeView 的注释）。
 */
export const DEFAULT_THEME: ThemeName = 'violet'

/**
 * 深色底的几个主题。**样式里那批「深色底要换底色 / 描边」的规则只认 `data-dark`**，
 * 不逐个主题名去写——否则每加一个深色主题，那十几条规则就要复制一遍。
 */
export const DARK_THEMES: readonly ThemeName[] = ['deep', 'violet']

export function themeLabel(name: ThemeName): string {
  return THEME_LABELS[name]
}

export const theme = ref<ThemeName>(
  readStored(THEME_STORAGE_KEY, THEME_NAMES, DEFAULT_THEME)
)

watchEffect(() => {
  const root = document.documentElement
  root.dataset.theme = theme.value
  root.toggleAttribute('data-dark', DARK_THEMES.includes(theme.value))
})

watch(theme, (value) => {
  writeStored(THEME_STORAGE_KEY, value)
})
