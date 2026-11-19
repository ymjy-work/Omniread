import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  deleteApiKey as deleteApiKeyApi,
  getAccount,
  listApiKeys,
  listPlans,
  purchasePlan as purchasePlanApi,
  saveApiKey as saveApiKeyApi,
} from '../api/account'
import { errorMessage } from '../api/request'
import type {
  Account,
  ApiKeyRecord,
  ApiProvider,
  PlanCatalog,
  PlanCode,
} from '../types/account'

function normalizeAccount(value: Account): Account {
  return {
    role: value.role ?? 'user',
    plan: value.plan ?? 'free',
    credits: Number(value.credits ?? 0),
    balance: Number(value.balance ?? 0),
    planExpiresAt: value.planExpiresAt ?? null,
  }
}

export const useAccountStore = defineStore('account', () => {
  const account = ref<Account | null>(null)
  const loading = ref(false)
  const error = ref('')

  const plans = ref<PlanCatalog[]>([])
  const plansLoading = ref(false)
  const plansError = ref('')
  const plansLoaded = ref(false)

  const apiKeys = ref<ApiKeyRecord[]>([])
  const keysLoading = ref(false)
  const keysError = ref('')
  const keysLoaded = ref(false)

  let accountPromise: Promise<Account | null> | null = null
  let plansPromise: Promise<PlanCatalog[]> | null = null
  let keysPromise: Promise<ApiKeyRecord[]> | null = null

  const isAdmin = computed(() => account.value?.role === 'admin')
  const plan = computed(() => account.value?.plan ?? '')
  const credits = computed(() => account.value?.credits ?? 0)
  const balance = computed(() => account.value?.balance ?? 0)
  const planExpiresAt = computed(() => account.value?.planExpiresAt ?? null)

  function hasKey(provider: string) {
    return apiKeys.value.some((item) => item.provider === provider)
  }

  async function fetchAccount(force = false) {
    if (!force && account.value) return account.value
    if (accountPromise) {
      const current = await accountPromise
      if (!force) return current
    }
    loading.value = true
    error.value = ''
    accountPromise = (async () => {
      try {
        const data = await getAccount()
        account.value = data ? normalizeAccount(data) : null
        return account.value
      } catch (err) {
        error.value = errorMessage(err, '账户信息加载失败')
        return null
      } finally {
        loading.value = false
        accountPromise = null
      }
    })()
    return accountPromise
  }

  async function fetchPlans(force = false) {
    if (!force && plansLoaded.value) return plans.value
    if (plansPromise) return plansPromise
    plansLoading.value = true
    plansError.value = ''
    plansPromise = (async () => {
      try {
        const list = await listPlans()
        plans.value = Array.isArray(list) ? list : []
        plansLoaded.value = true
        return plans.value
      } catch (err) {
        plansError.value = errorMessage(err, '套餐列表加载失败')
        return plans.value
      } finally {
        plansLoading.value = false
        plansPromise = null
      }
    })()
    return plansPromise
  }

  async function fetchApiKeys(force = false) {
    if (!force && keysLoaded.value) return apiKeys.value
    if (keysPromise) return keysPromise
    keysLoading.value = true
    keysError.value = ''
    keysPromise = (async () => {
      try {
        const list = await listApiKeys()
        apiKeys.value = Array.isArray(list) ? list : []
        keysLoaded.value = true
        return apiKeys.value
      } catch (err) {
        keysError.value = errorMessage(err, 'API Key 列表加载失败')
        return apiKeys.value
      } finally {
        keysLoading.value = false
        keysPromise = null
      }
    })()
    return keysPromise
  }

  async function purchasePlan(planCode: PlanCode) {
    const next = await purchasePlanApi(planCode)
    account.value = normalizeAccount(next)
    return account.value
  }

  async function saveApiKey(provider: ApiProvider, key: string) {
    const record = await saveApiKeyApi(provider, key)
    const index = apiKeys.value.findIndex((item) => item.provider === provider)
    if (index >= 0) apiKeys.value.splice(index, 1, record)
    else apiKeys.value.push(record)
    keysLoaded.value = true
    return record
  }

  async function deleteApiKey(provider: ApiProvider) {
    await deleteApiKeyApi(provider)
    apiKeys.value = apiKeys.value.filter((item) => item.provider !== provider)
    keysLoaded.value = true
  }

  function clear() {
    account.value = null
    error.value = ''
    apiKeys.value = []
    keysError.value = ''
    keysLoaded.value = false
  }

  return {
    account,
    loading,
    error,
    plans,
    plansLoading,
    plansError,
    plansLoaded,
    apiKeys,
    keysLoading,
    keysError,
    keysLoaded,
    isAdmin,
    plan,
    credits,
    balance,
    planExpiresAt,
    hasKey,
    fetchAccount,
    fetchPlans,
    fetchApiKeys,
    purchasePlan,
    saveApiKey,
    deleteApiKey,
    clear,
  }
})