import { ref } from 'vue'
import { saveProgress } from '../api/progress'
import { errorMessage } from '../api/errors'

interface ProgressOptions {
  getScrollEl: () => HTMLElement | null
  getBookId: () => number
  getChapterIndex: () => number | null
  delay?: number
}

export function useReadingProgress(options: ProgressOptions) {
  const saving = ref(false)
  const ratio = ref(0)
  const saveError = ref('')

  let timer: number | null = null
  let lastSent = -1

  function clearTimer() {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  function measure() {
    const el = options.getScrollEl()
    if (!el) return ratio.value
    const max = el.scrollHeight - el.clientHeight
    const next = max > 0 ? Math.min(Math.max(el.scrollTop / max, 0), 1) : 0
    ratio.value = next
    return next
  }

  function schedule() {
    measure()
    clearTimer()
    timer = window.setTimeout(() => {
      timer = null
      void flush()
    }, options.delay ?? 1000)
  }

  async function flush() {
    clearTimer()
    const index = options.getChapterIndex()
    const bookId = options.getBookId()
    if (index === null || !Number.isFinite(bookId)) return
    const current = measure()
    if (lastSent >= 0 && Math.abs(current - lastSent) < 0.005) return

    saving.value = true
    saveError.value = ''
    try {
      await saveProgress(bookId, {
        chapterIndex: index,
        scrollRatio: Number(current.toFixed(4)),
      })
      lastSent = current
    } catch (error) {
      saveError.value = errorMessage(error, '进度保存失败')
    } finally {
      saving.value = false
    }
  }

  function sync(value = 0) {
    clearTimer()
    ratio.value = value
    lastSent = value
    saveError.value = ''
  }

  return { saving, ratio, saveError, measure, schedule, flush, sync }
}
