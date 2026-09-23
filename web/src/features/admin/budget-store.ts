import type { Budget } from '../../types/admin'

const periodStart = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString()
const periodEnd = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 1).toISOString()
let budgets: Budget[] = [
  { id: 'budget-user-demo', target_type: 'user', target_id: 'usr_demo_user', target_name: 'Jamie Chen', monthly_limit: '0.0500', monthly_spend: '0.0140', period_start: periodStart, period_end: periodEnd },
  { id: 'budget-project-checkout', target_type: 'project', target_id: 'checkout', target_name: 'Checkout Assistant', monthly_limit: '0.1000', monthly_spend: '0.0140', period_start: periodStart, period_end: periodEnd },
]
let revision = 0
const listeners = new Set<() => void>()
export const budgetStore = {
  subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) },
  getSnapshot() { return revision },
  getBudgets() { return budgets },
  getLimit(targetType: Budget['target_type'], targetId: string) { return budgets.find((item) => item.target_type === targetType && item.target_id === targetId)?.monthly_limit ?? null },
  upsert(item: Budget) { budgets = [item, ...budgets.filter((entry) => !(entry.target_type === item.target_type && entry.target_id === item.target_id))]; revision += 1; listeners.forEach((listener) => listener()) },
}
