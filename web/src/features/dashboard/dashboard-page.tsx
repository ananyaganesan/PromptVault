import { useEffect, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Stat, Status } from '../../components/ui/prototype'
import { ErrorState } from '../../components/ui/error-state'
import { LoadingState } from '../../components/ui/loading-state'
import { EmptyState } from '../../components/ui/empty-state'
import { useAuth } from '../auth/auth-context'
import { deploymentService, deploymentStore } from '../deployments/deployment-service'
import { projectStore, promptStore } from '../projects/workspace-data'
import { runService, runStore } from '../runs/run-service'
import type { PersonalDashboard, PromptRun } from '../../types/runs'

export function DashboardPage() {
  const { user } = useAuth()
  const runRevision = useSyncExternalStore(runStore.subscribe, runStore.getSnapshot)
  const deploymentRevision = useSyncExternalStore(deploymentStore.subscribe, deploymentStore.getSnapshot)
  const [data, setData] = useState<PersonalDashboard | null>(null)
  const [runs, setRuns] = useState<PromptRun[]>([])
  const [pending, setPending] = useState(0)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    Promise.all([runService.dashboard(user?.id), runService.list({ page_size: 100 }), deploymentService.list({ status: 'pending_approval' })]).then(([dashboard, history, approvals]) => {
      if (!active) return
      setData(dashboard); setRuns(history.items.filter((run) => run.user_id === user?.id).slice(0, 4)); setPending(approvals.total); setError('')
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load the dashboard.') })
    return () => { active = false }
  }, [runRevision, deploymentRevision, retry, user?.id])
  const points = data?.cost_trend ?? []
  const max = Math.max(0.001, ...points.map((point) => Number(point.cost)))
  const line = points.map((point, index) => `${points.length < 2 ? 0 : index / (points.length - 1) * 600},${160 - Number(point.cost) / max * 135}`).join(' ')
  const spend = Number(data?.monthly_spend ?? 0)
  return <><PageHeader title={`Good morning, ${user?.display_name.split(' ')[0] ?? 'there'}`} description="Here’s what’s happening across your workspace." action={<Link to="/projects/new"><Button>New project</Button></Link>} />
    {error ? <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} /> : !data ? <LoadingState label="Loading dashboard…" /> : <>
      <div className="stats-grid"><Stat label="PROJECTS" value={String(projectStore.length)} note="Workspace projects"/><Stat label="PROMPTS" value={String(promptStore.length)} note="Reusable templates"/><Stat label="MONTHLY SPEND" value={`$${spend.toFixed(4)}`} note={data.monthly_budget == null ? 'No personal limit' : `of $${Number(data.monthly_budget).toFixed(2)} budget`}/><Stat label="PENDING APPROVALS" value={String(pending)} note="Production requests"/></div>
      <div className="dashboard-grid"><section className="panel"><div className="panel-head"><div><h2>Recent activity</h2><p>Latest runs from your workspace.</p></div><Link to="/runs">View all</Link></div>{runs.length ? runs.map((run) => <Link className="activity" to={`/runs/${run.id}`} key={run.id}><span className="activity-icon">{run.status === 'completed' ? '✓' : '!'}</span><div><b>{run.prompt_key} · v{run.version_number}</b><small>{new Date(run.created_at).toLocaleString()}</small></div><Status tone={run.status === 'completed' ? 'success' : 'warning'}>{run.status}</Status></Link>) : <EmptyState title="No runs yet" description="Execute a prompt in the playground to see activity here." action={<Link to="/playground">Open playground</Link>} />}</section>
      <section className="panel chart-panel"><div className="panel-head"><div><h2>Cost trend</h2><p>Last 14 days</p></div><strong>${spend.toFixed(4)}</strong></div><div className="chart"><svg viewBox="0 0 600 180" preserveAspectRatio="none" role="img" aria-label="Daily cost trend"><line x1="0" y1="160" x2="600" y2="160" stroke="#eceae7"/><polyline points={line} fill="none" stroke="#17171c" strokeWidth="2"/></svg></div><div className="chart-axis"><span>{points[0]?.date}</span><span>{points[points.length - 1]?.date}</span></div></section></div>
    </>}</>
}
