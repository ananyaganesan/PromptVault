import { useEffect, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Stat, Status } from '../../components/ui/prototype'
import { ErrorState } from '../../components/ui/error-state'
import { LoadingState } from '../../components/ui/loading-state'
import { EmptyState } from '../../components/ui/empty-state'
import { useAuth } from '../auth/auth-context'
import { runService, runStore } from '../runs/run-service'
import type { PersonalDashboard } from '../../types/runs'
import { useLiveRefresh } from '../../lib/live-refresh'

export function DashboardPage() {
  const { user } = useAuth()
  const refresh = useLiveRefresh()
  const runRevision = useSyncExternalStore(runStore.subscribe, runStore.getSnapshot)
  const [data, setData] = useState<PersonalDashboard | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    runService.dashboard(user?.id).then((dashboard) => {
      if (!active) return
      setData(dashboard); setError('')
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load the dashboard.') })
    return () => { active = false }
  }, [refresh, runRevision, retry, user?.id])
  const spend = Number(data?.monthly_spend ?? 0)
  const runs = data?.recent_runs.slice(0, 4) ?? []
  return <><PageHeader title={`Good morning, ${user?.display_name.split(' ')[0] ?? 'there'}`} description="Here’s what’s happening across your workspace." action={<Link to="/projects/new"><Button>New project</Button></Link>} />
    {error ? <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} /> : !data ? <LoadingState label="Loading dashboard…" /> : <>
      <div className="stats-grid"><Stat label="PROJECTS" value={String(data.project_count)} note="Workspace projects"/><Stat label="PROMPTS" value={String(data.prompt_count)} note="Reusable templates"/><Stat label="MONTHLY SPEND" value={`$${spend.toFixed(4)}`} note={data.monthly_budget == null ? 'No personal limit' : `of $${Number(data.monthly_budget).toFixed(2)} budget`}/><Stat label="YOUR RUNS" value={String(data.run_count)} note="Personal executions"/><Stat label="PENDING APPROVALS" value={String(data.pending_approval_count)} note="Production requests"/></div>
      <div className="dashboard-grid dashboard-grid-single"><section className="panel"><div className="panel-head"><div><h2>Recent activity</h2><p>Your four most recent runs.</p></div></div>{runs.length ? runs.map((run) => <div className="activity" key={run.id}><span className="activity-icon">{run.status === 'completed' ? '✓' : '!'}</span><div><b>{run.prompt_key} · v{run.version_number}</b><small>{new Date(run.created_at).toLocaleString()}</small></div><Status tone={run.status === 'completed' ? 'success' : 'warning'}>{run.status}</Status></div>) : <div className="recent-activity-empty"><EmptyState title="No personal runs yet" description="Execute a prompt in the playground to see activity here." action={<Link to="/playground">Open playground</Link>} /></div>}</section></div>
    </>}</>
}
