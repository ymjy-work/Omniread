/**
 * 等价性测试的 TS 侧入口：按 `web/src/citation.ts` 跑一遍权威定义里的样本，把结果打成 JSON。
 *
 * Python 侧 `services/rag/tests/test_citation_equivalence.py` 以子进程调用本脚本，
 * 用同一批样本比对两侧的引用集合与违规集合，并核对两侧声明的正则源码。
 *
 * 用法（Node ≥ 23.6 原生剥离类型，可直接跑 .ts）：
 *   node web/scripts/citation-samples.ts citation-format.json
 *
 * 本文件是开发期脚本，不在 `tsconfig.json` 的 include 里（用到 node:fs / process，
 * 前端工程没有装 @types/node），因此不参与 vue-tsc 的类型检查。
 */
import { readFileSync } from 'node:fs'
import { CANDIDATE_PATTERN, CITATION_PATTERN, findCitations, findViolations } from '../src/citation.ts'

interface Sample {
  name: string
  text: string
}

const definitionPath = process.argv[2]
if (definitionPath === undefined) {
  console.error('用法：node web/scripts/citation-samples.ts <citation-format.json>')
  process.exit(2)
}

const definition = JSON.parse(readFileSync(definitionPath, 'utf8')) as { samples: Sample[] }

const output = {
  pattern: CITATION_PATTERN,
  candidate_pattern: CANDIDATE_PATTERN,
  samples: definition.samples.map((sample) => ({
    name: sample.name,
    citations: findCitations(sample.text).map((hit) => ({
      chapter_index: hit.chapterIndex,
      text: hit.text
    })),
    violations: findViolations(sample.text)
  }))
}

console.log(JSON.stringify(output))
