import { ref } from 'vue'
import { defineStore } from 'pinia'

export type ThemeName = 'light' | 'sepia' | 'dark'

const THEME_KEY = 'omniread.theme'
const FONT_KEY = 'omniread.fontSize'
const MIN_FONT = 16
const MAX_FONT = 26

function readTheme(): ThemeName {
  const saved = localStorage.getItem(THEME_KEY)
  return saved === 'sepia' || saved === 'dark' ? saved : 'light'
}

function readFontSize(): number {
  const saved = Number(localStorage.getItem(FONT_KEY))
  if (!Number.isFinite(saved)) return 18
  return Math.min(Math.max(saved, MIN_FONT), MAX_FONT)
}

export const useSettingsStore = defineStore('settings', () => {
  const theme = ref<ThemeName>(readTheme())
  const fontSize = ref(readFontSize())

  function apply() {
    document.documentElement.dataset.theme = theme.value
    document.documentElement.style.setProperty('--reader-font-size', `${fontSize.value}px`)
  }

  function setTheme(next: ThemeName) {
    theme.value = next
    localStorage.setItem(THEME_KEY, next)
    apply()
  }

  function setFontSize(next: number) {
    fontSize.value = Math.min(Math.max(Math.round(next), MIN_FONT), MAX_FONT)
    localStorage.setItem(FONT_KEY, String(fontSize.value))
    apply()
  }

  apply()

  return { theme, fontSize, setTheme, setFontSize, minFont: MIN_FONT, maxFont: MAX_FONT }
})
