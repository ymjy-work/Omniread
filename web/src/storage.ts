/**
 * 前端偏好的本地持久化：读回上次选的档位，刷新后不用重设。
 *
 * 两件事集中在这么小的一个文件里，是因为它们都不显然：
 *
 * - **`localStorage` 会抛**。隐私模式或禁用存储时 `getItem` / `setItem` 直接抛异常，
 *   而这些调用发生在模块顶层——不兜住的话，「一个偏好记不住」会升级成「页面打不开」。
 * - **读回来必须校验取值**。存储是用户可改的：一个手写的 `omniread.theme=whatever`
 *   会让 `data-theme` 静默失效、样式悄悄退回默认，从界面上看不出来。
 *
 * 键名统一 `omniread.` 前缀，避免与同源下的别的东西撞名。
 */

/** 写入失败不抛：存不下只是这次会话结束后记不住，不该影响当前这一会话。 */
export function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // 见上
  }
}

/**
 * 读回一组字符串（记「关掉的标签」这类 id 集合用）。
 *
 * 同样不信任存储：不是数组、或者元素不是字符串，一律当没存过——
 * 一份手改过的 `["a", 1, null]` 让某个 id 变成数字，后面 `has()` 就永远不命中。
 */
export function readStoredList(key: string): string[] {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

/** 读回一个受白名单约束的偏好；没存过、存坏了、或存储不可用都回落到 `fallback`。 */
export function readStored<T extends string>(
  key: string,
  allowed: readonly T[],
  fallback: T
): T {
  try {
    const raw = localStorage.getItem(key)
    if (raw !== null && (allowed as readonly string[]).includes(raw)) return raw as T
  } catch {
    // 读不到就当没存过
  }
  return fallback
}

/**
 * 读回一段自由文本（会话 id 这类没有白名单可枚举的值）；读不到或存储不可用回 `null`。
 *
 * 这类值没法在这里校验——校验交给消费方（比如「这个 id 在服务端列表里有没有」）。
 */
export function readStoredText(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
