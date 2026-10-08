/**
 * 让 Node 直接跑 `web/src` 下的 `.ts`：给**无扩展名的相对导入**补上 `.ts`。
 *
 * 为什么需要它：`src/` 里的相对导入沿用打包器的写法（`from './citation'`，不带扩展名），
 * 而 Node 的 ESM 解析要求显式扩展名。`check:citations` 不需要这个钩子，是因为
 * `citation.ts` 没有任何本地导入；`markdown.ts` 有一个，不补就跑不起来。
 * 另一条路是把 `src/` 里那行改成 `./citation.ts` 并开 `allowImportingTsExtensions`，
 * 那会让它成为 src 下**唯一**带扩展名导入的文件——为测试改产品代码的写法，不划算。
 *
 * **只在 dev 脚本里生效**（由 `node --import` 显式加载），不进构建、不影响产品代码。
 * 只有当同名 `.ts` 确实存在时才改写——否则会把真正的解析错误一起吞掉。
 */
import { existsSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { fileURLToPath } from 'node:url'

const HAS_EXTENSION = /\.[cm]?[jt]sx?$/i

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith('.') && !HAS_EXTENSION.test(specifier) && context.parentURL) {
      const candidate = fileURLToPath(new URL(`${specifier}.ts`, context.parentURL))
      if (existsSync(candidate)) return nextResolve(`${specifier}.ts`, context)
    }
    return nextResolve(specifier, context)
  },
})
