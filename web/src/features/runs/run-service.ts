import { runsApi, type BackendPromptRun } from './api'
import { projectStore, promptStore, versionStore } from '../projects/workspace-data'
import type { CreateRunRequest, PersonalDashboard, PromptRun, RunListQuery } from '../../types/runs'
import type { Page } from '../../types/api'
import { budgetStore } from '../admin/budget-store'
import { useDemoData } from '../../lib/runtime'
import { ApiClientError } from '../../lib/api/client'
import { refreshLiveData } from '../../lib/live-refresh'

const useDemoRuns = useDemoData && import.meta.env.VITE_USE_MOCK_RUNS !== 'false'
const currentMonth = new Date().toISOString().slice(0, 7)
const daysAgo = (days: number) => new Date(Date.now() - days * 86400000).toISOString()
const seedRuns: PromptRun[] = [
  { id: 'demo-run-1', project_id: 'checkout', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v3', version_number: 3, user_id: 'usr_demo_user', status: 'completed', output: 'I can help review your checkout question. Please share the order number so I can check the payment details.', input_variables: { customer_message: 'Can you check my payment?', order_context: 'Order #10482' }, prompt_tokens: 184, completion_tokens: 42, latency_ms: 1240, cost: '0.0080', model: 'gpt-4o-mini', created_at: daysAgo(0) },
  { id: 'demo-run-2', project_id: 'checkout', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v2', version_number: 2, user_id: 'usr_demo_user', status: 'completed', output: 'Your order is being reviewed. We will update you shortly.', input_variables: { customer_message: 'What happened to my order?' }, prompt_tokens: 126, completion_tokens: 38, latency_ms: 980, cost: '0.0060', model: 'gpt-4o-mini', created_at: daysAgo(2) },
  { id: 'demo-run-3', project_id: 'checkout', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v3', version_number: 3, user_id: 'usr_demo_user', status: 'failed', output: null, input_variables: { customer_message: 'Please check my order' }, prompt_tokens: null, completion_tokens: null, latency_ms: null, cost: '0.0000', model: 'gpt-4o-mini', created_at: daysAgo(3), error_message: 'The model provider was unavailable. Try again.' },
  { id: 'demo-run-4', project_id: 'checkout', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v3', version_number: 3, user_id: 'usr_demo_user', status: 'blocked', output: null, input_variables: { customer_message: 'Please check my order' }, prompt_tokens: null, completion_tokens: null, latency_ms: null, cost: '0.0000', model: 'gpt-4o-mini', created_at: daysAgo(4), error_message: 'The monthly budget has been reached. No provider call was made.' },
]

let demoRuns = useDemoRuns ? seedRuns : []
let revision = 0
const listeners = new Set<() => void>()
function notify() { revision += 1; listeners.forEach((listener) => listener()); refreshLiveData() }
export const runStore = {
  subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) },
  getSnapshot() { return revision },
  getRuns() { return demoRuns },
}

function totalSpend(userId: string) { return demoRuns.filter((run) => run.user_id === userId && run.status === 'completed' && run.created_at.startsWith(currentMonth)).reduce((total, run) => total + Number(run.cost), 0) }
function money(amount: number) { return amount.toFixed(4) }
function spendFor(target: 'user' | 'project', id: string) { return demoRuns.filter((run) => run.status === 'completed' && run.created_at.startsWith(currentMonth) && (target === 'user' ? run.user_id : run.project_id) === id).reduce((total, run) => total + Number(run.cost), 0) }

export function adaptRun(run: BackendPromptRun): PromptRun {
  return {
    id: run.id,
    project_id: run.project_id,
    prompt_id: run.prompt_id,
    prompt_key: run.prompt_key,
    version_id: run.version_id,
    version_number: run.version_number,
    user_id: run.user_id,
    status: run.status,
    output: run.output_text,
    input_variables: run.input_variables,
    prompt_tokens: run.prompt_tokens,
    completion_tokens: run.completion_tokens,
    latency_ms: run.latency_ms,
    cost: run.cost,
    model: run.model,
    created_at: run.created_at,
    error_message: run.error_code ? run.error_code.replace(/_/g, ' ') : null,
  }
}

export const runService = {
  async create(request: CreateRunRequest, scenario: 'normal' | 'failed' | 'blocked' = 'normal', userId = 'usr_demo_user'): Promise<PromptRun> {
    if (!useDemoRuns) {
      try {
        const run = adaptRun(await runsApi.create(request))
        demoRuns = [run, ...demoRuns]
        notify()
        return run
      } catch (cause) {
        // These application errors are emitted only after ledger recording succeeds.
        // Other failures (including connection loss) do not confirm a recorded run.
        if (cause instanceof ApiClientError && (
          (cause.status === 502 && cause.code === 'provider_error') ||
          (cause.status === 504 && cause.code === 'provider_timeout') ||
          (cause.status === 409 && cause.code === 'budget_exceeded') ||
          (cause.status === 429 && cause.code === 'concurrency_limit') ||
          ([409, 503].includes(cause.status) && cause.code === 'execution_outcome_unknown')
        )) notify()
        throw cause
      }
    }
    const version = Object.values(versionStore).flat().find((item) => item.id === request.version_id)
    if (!version) throw new Error('Select a valid prompt version.')
    const prompt = promptStore.find((item) => item.id === version.prompt_id)
    if (!prompt) throw new Error('Prompt not found.')
    const missing = version.variables.find((variable) => variable.required && !request.variables[variable.name]?.trim())
    if (missing) throw new Error(`${missing.name} is required.`)
    const estimatedCost = Math.max(0.003, version.template.length / 30000 + Object.values(request.variables).join('').length / 50000)
    const userLimit = budgetStore.getLimit('user', userId)
    const projectLimit = budgetStore.getLimit('project', prompt.project_id)
    const overBudget = (userLimit !== null && spendFor('user', userId) + estimatedCost > Number(userLimit)) || (projectLimit !== null && spendFor('project', prompt.project_id) + estimatedCost > Number(projectLimit))
    const status = scenario === 'blocked' || overBudget ? 'blocked' : scenario === 'failed' ? 'failed' : 'completed'
    const rendered = version.template.replace(/{{\s*([a-zA-Z_][\w-]*)\s*}}/g, (_, name: string) => request.variables[name] || version.variables.find((variable) => variable.name === name)?.default_value || '')
    const run: PromptRun = {
      id: `run-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, project_id: prompt.project_id, prompt_id: prompt.id, prompt_key: prompt.key, version_id: version.id, version_number: version.version_number, user_id: userId, status,
      output: status === 'completed' ? `I can help with that. Based on the details you provided, here is a clear response:\n\n${rendered.slice(0, 500)}` : null,
      input_variables: { ...request.variables }, prompt_tokens: status === 'completed' ? Math.max(1, Math.ceil(rendered.length / 4)) : null, completion_tokens: status === 'completed' ? 42 : null, latency_ms: status === 'completed' ? 940 : null,
      cost: status === 'completed' ? money(estimatedCost) : '0.0000', model: version.model_config.model, created_at: new Date().toISOString(),
      error_message: status === 'blocked' ? 'The monthly budget has been reached. No provider call was made.' : status === 'failed' ? 'The model provider was unavailable. Try again.' : null,
    }
    demoRuns = [run, ...demoRuns]; notify(); return run
  },
  async list(query: RunListQuery = {}): Promise<Page<PromptRun>> {
    if (!useDemoRuns) {
      const page = await runsApi.list(query)
      return { ...page, items: page.items.map(adaptRun) }
    }
    const search = query.search?.trim().toLocaleLowerCase()
    const rows = demoRuns.filter((run) => (!search || `${run.prompt_key} ${run.id}`.toLocaleLowerCase().includes(search)) && (!query.project_id || run.project_id === query.project_id) && (!query.prompt_id || run.prompt_id === query.prompt_id) && (!query.version_id || run.version_id === query.version_id) && (!query.status || run.status === query.status) && (!query.model || run.model === query.model) && (!query.from || run.created_at >= query.from) && (!query.to || run.created_at < query.to))
    const page = query.page ?? 1; const pageSize = query.page_size ?? 20
    return { items: rows.slice((page - 1) * pageSize, page * pageSize), total: rows.length, page, page_size: pageSize }
  },
  async get(id: string): Promise<PromptRun | undefined> {
    if (useDemoRuns) return demoRuns.find((run) => run.id === id)
    return adaptRun(await runsApi.get(id))
  },
  async dashboard(userId = 'usr_demo_user'): Promise<PersonalDashboard> {
    if (!useDemoRuns) {
      const dashboard = await runsApi.personalDashboard()
      return {
        project_count: dashboard.project_count,
        prompt_count: dashboard.prompt_count,
        monthly_spend: dashboard.monthly_spend,
        monthly_budget: dashboard.monthly_budget,
        pending_approval_count: dashboard.pending_approval_count,
        run_count: dashboard.run_count,
        cost_trend: dashboard.cost_trend,
        recent_runs: dashboard.recent_runs.map(adaptRun),
      }
    }
    const buckets = new Map<string, { cost: number; run_count: number }>()
    for (let index = 13; index >= 0; index -= 1) buckets.set(daysAgo(index).slice(0, 10), { cost: 0, run_count: 0 })
    for (const run of demoRuns.filter((item) => item.user_id === userId)) { const bucket = buckets.get(run.created_at.slice(0, 10)); if (bucket) { bucket.cost += Number(run.cost); bucket.run_count += 1 } }
    return { recent_runs: demoRuns.filter((run) => run.user_id === userId).slice(0, 4), project_count: projectStore.length, prompt_count: promptStore.length, monthly_spend: money(totalSpend(userId)), monthly_budget: budgetStore.getLimit('user', userId), pending_approval_count: 0, run_count: demoRuns.filter((run) => run.user_id === userId).length, cost_trend: [...buckets].map(([date, value]) => ({ date, cost: money(value.cost), run_count: value.run_count })) }
  },
}
