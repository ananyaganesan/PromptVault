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
    Promise.all([runService.dashboard(user?.id), runService.list({ page_size: 4 }), deploymentService.list({ status: 'pending_approval' })]).then(([dashboard, history, approvals]) => {
      if (!active) return
      setData(dashboard); setRuns(history.items.filter((run) => run.user_id === user?.id).slice(0, 4)); setPending(approvals.total); setError('')
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load the dashboard.') })
    return () => { active = false }
  }, [runRevision, deploymentRevision, retry, user?.id])
  return <><PageHeader title={`Good morning, ${user?.display_name.split(' ')[0] ?? 'there'}`} description="Here’s what’s happening across your workspace." action={<Link to="/projects/new"><Button>New project</Button></Link>} />
    {error ? <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} /> : !data ? <LoadingState label="Loading dashboard…" /> : <>
      <div className="stats-grid"><Stat label="PROJECTS" value={String(projectStore.length)} note="Workspace projects"/><Stat label="PROMPTS" value={String(promptStore.length)} note="Reusable templates"/><Stat label="RUNS" value={String(data.run_count)} note="Recorded executions"/><Stat label="PENDING APPROVALS" value={String(pending)} note="Production requests"/></div>
      <section className="panel"><div className="panel-head"><div><h2>Recent activity</h2><p>Latest four runs from your workspace.</p></div><Link to="/runs">View all</Link></div>{runs.length ? runs.map((run) => <Link className="activity" to={`/runs/${run.id}`} key={run.id}><span className="activity-icon">{run.status === 'completed' ? '✓' : '!'}</span><div><b>{run.prompt_key} · v{run.version_number}</b><small>{new Date(run.created_at).toLocaleString()}</small></div><Status tone={run.status === 'completed' ? 'success' : 'warning'}>{run.status}</Status></Link>) : <EmptyState title="No runs yet" description="Execute a prompt in the playground to see activity here." action={<Link to="/playground">Open playground</Link>} />}</section>
    </>}</>
}
