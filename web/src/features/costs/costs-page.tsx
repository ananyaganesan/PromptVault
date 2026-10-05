import { useEffect, useState, useSyncExternalStore } from 'react'
import { PageHeader } from '../../components/layout/page-header'
import { ErrorState } from '../../components/ui/error-state'
import { LoadingState } from '../../components/ui/loading-state'
import { Stat } from '../../components/ui/prototype'
import type { PersonalDashboard } from '../../types/runs'
import { useAuth } from '../auth/auth-context'
import { runService, runStore } from '../runs/run-service'

function currency(value: string | number) {
  return `$${Number(value).toFixed(4)}`
}

export function CostsPage() {
  const { user } = useAuth()
  const revision = useSyncExternalStore(runStore.subscribe, runStore.getSnapshot)
  const [data, setData] = useState<PersonalDashboard | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let active = true
    runService.dashboard(user?.id)
      .then((dashboard) => { if (active) { setData(dashboard); setError('') } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load cost data.') })
    return () => { active = false }
  }, [revision, retry, user?.id])

  const spend = Number(data?.monthly_spend ?? 0)
  const budget = data?.monthly_budget == null ? null : Number(data.monthly_budget)
  const remaining = budget == null ? null : Math.max(0, budget - spend)

  return <>
    <PageHeader title="Costs" description="Track personal usage and monthly budget consumption." />
    {error ? <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} /> : !data ? <LoadingState label="Loading costs…" /> : <>
      <div className="stats-grid">
        <Stat label="MONTHLY SPEND" value={currency(spend)} note="Completed runs this month" />
        <Stat label="MONTHLY BUDGET" value={budget == null ? 'Unlimited' : currency(budget)} note="Effective personal limit" />
        <Stat label="REMAINING" value={remaining == null ? 'Unlimited' : currency(remaining)} note="Before the next run is blocked" />
        <Stat label="TOTAL RUNS" value={String(data.run_count)} note="All recorded runs" />
      </div>
      <section className="panel table-panel">
        <div className="panel-head"><div><h2>Daily usage</h2><p>Authoritative run and cost totals for the last 14 days.</p></div></div>
        <table aria-label="Daily cost history">
          <thead><tr><th>DATE</th><th>RUNS</th><th>COST</th></tr></thead>
          <tbody>{data.cost_trend.map((point) => <tr key={point.date}><td>{new Date(`${point.date}T00:00:00`).toLocaleDateString()}</td><td>{point.run_count}</td><td>{currency(point.cost)}</td></tr>)}</tbody>
        </table>
      </section>
    </>}
  </>
}
