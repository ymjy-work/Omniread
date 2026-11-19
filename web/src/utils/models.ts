import type { ApiProvider } from '../types/account'

export const SUGGESTED_MODELS: Record<ApiProvider, string[]> = {
  bailian: ['qwen3.8-max', 'qwen3.7-plus', 'qwen3.7-flash'],
  openai: ['gpt-6.2-sol', 'gpt-6.1-terra', 'gpt-6-luna'],
  deepseek: ['deepseek-flash', 'deepseek-v4-pro'],
  siliconflow: [
    'deepseek-ai/DeepSeek-V4.1-Flash',
    'deepseek-ai/DeepSeek-V4-Pro',
    'Qwen/Qwen3.8-27B',
    'zai-org/GLM-5.3',
  ],
}

export function suggestedModelsFor(provider: ApiProvider) {
  return SUGGESTED_MODELS[provider] ?? []
}