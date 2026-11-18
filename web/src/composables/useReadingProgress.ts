import { ref } from 'vue'

export function useReadingProgress() {
  const saving = ref(false)

  async function save() {
    // 接入 progress store 与 gateway 接口后补全
  }

  return { saving, save }
}
