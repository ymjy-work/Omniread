<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PublicHeader from '../components/PublicHeader.vue'
import UserTopbar from '../components/UserTopbar.vue'
import { errorMessage, TOKEN_KEY } from '../api/request'
import { useAccountStore } from '../stores/account'
import { useAuthStore } from '../stores/auth'
import { PLAN_ORDER, formatCredits, formatDate, formatMoney, planLabel } from '../utils/billing'
import type { PlanCatalog, PlanCode } from '../types/account'

const FALLBACK_PLANS: PlanCatalog[] = [
  { code: 'free', price: 0, credits: 100, durationDays: 30 },
  { code: 'plus', price: 20, credits: 500, durationDays: 30 },
  { code: 'pro', price: 60, credits: 2000, durationDays: 30 },
  { code: 'ultra', price: 100, credits: 4000, durationDays: 30 },
]

const PERKS: Record<PlanCode, string[]> = {
  free: ['auto 自动路由', '每月补 100 积分', '引用与进度完整可用', 'BYOK 不扣积分'],
  plus: ['平台模型可选', '约 500 次平台回答', 'BYOK 不扣积分', '到期未续回落 Free'],
  pro: ['平台模型可选', '约 2,000 次平台回答', 'BYOK 不扣积分', '到期未续回落 Free'],
  ultra: ['平台模型可选', '约 4,000 次平台回答', 'BYOK 不扣积分', '到期未续回落 Free'],
}

const account = useAccountStore()
const auth = useAuthStore()

const purchasing = ref<PlanCode | ''>('')
const purchaseError = ref('')
const purchaseMessage = ref('')

const hasToken = computed(() => auth.isAuthenticated || Boolean(localStorage.getItem(TOKEN_KEY)))

const displayPlans = computed<PlanCatalog[]>(() => {
  const list = account.plans.length > 0 ? account.plans : []
  const source = !hasToken.value && account.plansError && list.length === 0 ? FALLBACK_PLANS : list
  return [...source].sort((a, b) => PLAN_ORDER.indexOf(a.code) - PLAN_ORDER.indexOf(b.code))
})

const usingFallback = computed(
  () => !hasToken.value && account.plansError !== '' && account.plans.length === 0,
)

const plansLoading = computed(
  () => account.plansLoading && displayPlans.value.length === 0 && !usingFallback.value,
)

const plansProblem = computed(() => {
  if (usingFallback.value) return ''
  if (hasToken.value && account.plansError) return account.plansError
  return ''
})

onMounted(() => {
  if (hasToken.value) void account.fetchAccount(true)
  void account.fetchPlans()
})

function priceText(plan: PlanCatalog) {
  return plan.price === 0 ? '免费' : `¥${plan.price} / 月`
}

function creditsText(plan: PlanCatalog) {
  return `每月 ${formatCredits(plan.credits)} 积分`
}

function isCurrent(plan: PlanCatalog) {
  return Boolean(account.account) && account.plan === plan.code
}

function ctaText(plan: PlanCatalog) {
  if (!hasToken.value) return plan.code === 'free' ? '登录后开始' : '登录后购买'
  if (plan.code === 'free') return isCurrent(plan) ? '当前档位' : '默认档位'
  if (isCurrent(plan)) return '续费'
  return '购买'
}

function ctaDisabled(plan: PlanCatalog) {
  if (!hasToken.value) return false
  if (Boolean(purchasing.value)) return true
  return plan.code === 'free'
}

function ctaTarget(plan: PlanCatalog) {
  if (hasToken.value) return null
  return plan.code === 'free' ? '/login?redirect=/library' : '/login?redirect=/plans'
}

async function buyPlan(plan: PlanCatalog) {
  if (!hasToken.value) return
  if (plan.code === 'free' || purchasing.value) return
  purchaseError.value = ''
  purchaseMessage.value = ''

  if (!account.account) await account.fetchAccount(true)
  if (!account.account) {
    purchaseError.value = '账户信息尚未加载，请稍后重试。'
    return
  }
  if (account.balance < plan.price) {
    purchaseError.value = `余额不足：当前 ${formatMoney(account.balance)}，购买 ${planLabel(plan.code)} 需要 ${formatMoney(plan.price)}。请联系管理员充值。`
    return
  }

  purchasing.value = plan.code
  try {
    await account.purchasePlan(plan.code)
    purchaseMessage.value = `已开通 ${planLabel(plan.code)}，积分已重置为 ${formatCredits(plan.credits)}。`
  } catch (error) {
    purchaseError.value = errorMessage(error, '套餐购买失败')
  } finally {
    purchasing.value = ''
  }
}

function retryPlans() {
  void account.fetchPlans(true)
}
</script>

<template>
  <div class="plan-page">
    <PublicHeader v-if="!hasToken" />
    <UserTopbar v-else active="plans" />

    <main class="plan-main">
      <header class="page-head">
        <p class="eyebrow">PLAN</p>
        <h1>套餐</h1>
        <p class="page-desc">按阅读量选择。所有档位都能使用自己的 API Key，BYOK 不扣积分。</p>
      </header>

      <section v-if="hasToken" class="panel summary-panel">
        <div v-if="account.loading && !account.account" class="inline-state">
          <span class="spinner"></span>
          正在读取账户…
        </div>

        <div v-else-if="account.account" class="summary-grid">
          <div class="summary-item">
            <span>当前档位</span>
            <strong>{{ planLabel(account.plan) }}</strong>
          </div>
          <div class="summary-item">
            <span>剩余积分</span>
            <strong :class="{ danger: account.credits < 1 }">{{ formatCredits(account.credits) }}</strong>
          </div>
          <div class="summary-item">
            <span>余额</span>
            <strong>{{ formatMoney(account.balance) }}</strong>
          </div>
          <div class="summary-item">
            <span>到期时间</span>
            <strong>{{ formatDate(account.planExpiresAt) }}</strong>
          </div>
        </div>

        <div v-else class="inline-state">
          <span class="error-text">{{ account.error || '账户信息不可用' }}</span>
          <button class="btn" type="button" @click="account.fetchAccount(true)">重试</button>
        </div>
      </section>

      <section class="panel plan-panel">
        <div class="panel-head">
          <h2>{{ hasToken ? '选择套餐' : '四档套餐' }}</h2>
          <p>周期内积分用完不补；续费会开启新周期并重置积分。</p>
        </div>

        <div v-if="plansLoading" class="inline-state">
          <span class="spinner"></span>
          正在加载套餐…
        </div>

        <div v-else-if="plansProblem" class="inline-state">
          <span class="error-text">{{ plansProblem }}</span>
          <button class="btn" type="button" @click="retryPlans">重试</button>
        </div>

        <p v-else-if="displayPlans.length === 0" class="inline-state">暂无套餐信息。</p>

        <div v-else class="plan-grid">
          <article
            v-for="plan in displayPlans"
            :key="plan.code"
            class="plan-card"
            :class="{ current: isCurrent(plan), featured: plan.code === 'pro' }"
          >
            <span v-if="plan.code === 'pro'" class="featured-tag">常用</span>
            <header class="plan-head">
              <div>
                <h3>
                  {{ planLabel(plan.code) }}
                  <span v-if="isCurrent(plan)" class="plan-current">当前</span>
                </h3>
                <p>{{ creditsText(plan) }}</p>
              </div>
              <p class="plan-price">{{ priceText(plan) }}</p>
            </header>

            <ul class="plan-perks">
              <li v-for="perk in PERKS[plan.code]" :key="perk">{{ perk }}</li>
            </ul>

            <p
              v-if="hasToken && account.account && plan.price > 0 && account.balance < plan.price"
              class="plan-shortage"
            >
              余额不足
            </p>

            <RouterLink
              v-if="!hasToken"
              class="btn plan-buy"
              :class="{ 'btn-primary': plan.code !== 'free' }"
              :to="ctaTarget(plan) || '/plans'"
            >
              {{ ctaText(plan) }}
            </RouterLink>
            <button
              v-else
              class="btn plan-buy"
              :class="{ 'btn-primary': plan.code !== 'free' }"
              type="button"
              :disabled="ctaDisabled(plan)"
              @click="buyPlan(plan)"
            >
              <span v-if="purchasing === plan.code" class="spinner sm"></span>
              {{ purchasing === plan.code ? '处理中…' : ctaText(plan) }}
            </button>
          </article>
        </div>

        <p v-if="purchaseError" class="notice error" role="alert">{{ purchaseError }}</p>
        <p v-if="purchaseMessage" class="notice success" role="status">{{ purchaseMessage }}</p>
      </section>

      <section class="rules">
        <p>平台回答每次扣 1 积分；BYOK 与失败的回答不扣。</p>
        <p>周期内积分用完不补。续费开启新周期，积分重置为该档额度，未用完不结转。</p>
        <p>余额仅用于购买套餐，由管理员发放；不开放真实支付，也不做余额兑积分。</p>
        <p v-if="usingFallback" class="fallback-note">套餐目录暂时无法读取，当前展示为固定价格。</p>
      </section>

      <footer v-if="!hasToken" class="plan-footer">
        <span>阅 Omniread</span>
        <nav aria-label="定价页页脚">
          <RouterLink to="/">产品</RouterLink>
          <RouterLink to="/login">登录</RouterLink>
        </nav>
      </footer>
    </main>
  </div>
</template>

<style scoped>
.plan-page {
  min-height: 100dvh;
  background: var(--bg);
}

.plan-main {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: clamp(28px, 5vw, 56px) clamp(18px, 4vw, 48px) 72px;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.page-head {
  margin-bottom: var(--space-2);
}

.eyebrow {
  margin-bottom: 10px;
  font-size: var(--text-xs);
  letter-spacing: 0.26em;
  color: var(--text-muted);
}

.page-head h1 {
  font-family: var(--font-serif);
  font-size: var(--text-xl);
  font-weight: 600;
}

.page-desc {
  max-width: 640px;
  margin-top: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--text-base);
  line-height: 1.7;
}

.panel {
  padding: clamp(20px, 3vw, 28px);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.summary-panel {
  padding-top: var(--space-5);
  padding-bottom: var(--space-5);
}

.panel-head {
  margin-bottom: var(--space-4);
}

.panel-head h2 {
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 600;
}

.panel-head p {
  margin-top: var(--space-1);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.summary-item span {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.summary-item strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 17px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.summary-item strong.danger {
  color: var(--danger);
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
}

.plan-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-height: 280px;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-2);
}

.plan-card.current {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.featured-tag {
  position: absolute;
  top: -9px;
  right: 10px;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  background: var(--accent);
  color: #fffdf8;
  font-size: 9.5px;
}

.plan-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.plan-head h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 600;
}

.plan-head p {
  margin-top: var(--space-1);
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.plan-current {
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-family: var(--font-sans);
  font-size: 10px;
  font-weight: 500;
}

.plan-price {
  margin: 0 !important;
  color: var(--text) !important;
  font-family: var(--font-serif);
  font-size: 28px !important;
  font-weight: 600;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.plan-perks {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
  color: var(--text-secondary);
  font-size: var(--text-xs);
  line-height: 1.6;
}

.plan-perks li::before {
  content: '·';
  margin-right: 5px;
  color: var(--accent);
}

.plan-shortage {
  color: var(--danger);
  font-size: 11.5px;
}

.plan-buy {
  margin-top: auto;
  height: 34px;
  padding: 0 var(--space-3);
  font-size: var(--text-sm);
}

.notice {
  margin-top: var(--space-3);
  padding: 9px 11px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  line-height: 1.6;
}

.notice.error {
  background: var(--danger-soft);
  color: var(--danger);
}

.notice.success {
  background: var(--success-soft);
  color: var(--success);
}

.rules {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: 0 var(--space-1);
  color: var(--text-muted);
  font-size: var(--text-xs);
  line-height: 1.7;
}

.fallback-note {
  color: var(--warning);
}

.plan-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin-top: var(--space-5);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.plan-footer nav {
  display: flex;
  gap: var(--space-4);
}

.plan-footer a:hover {
  color: var(--accent);
}

.inline-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: var(--space-5) var(--space-3);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

@media (max-width: 900px) {
  .plan-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .summary-grid,
  .plan-grid {
    grid-template-columns: 1fr;
  }

  .plan-footer {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>