import { useLiveRefresh } from '../../lib/live-refresh'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Stat, Status } from '../../components/ui/prototype'
import { projectStore, workspaceStore } from '../projects/workspace-data'
import type { Page } from '../../types/api'
import { runService, runStore } from './run-service'
import type { PromptRun, RunStatus } from '../../types/runs'

function RunStatusBadge({ status }: { status: RunStatus }) { return <Status tone={status === 'completed' ? 'success' : 'warning'}>{status}</Status> }
function dateTime(value: string) { return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) }

export function RunsPage() {
  const refresh = useLiveRefresh()
  const revision = useSyncExternalStore(runStore.subscribe, runStore.getSnapshot)
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot)
  const [search, setSearch] = useState('')
  const [model, setModel] = useState('')
  const [status, setStatus] = useState<RunStatus | ''>('')
  const [projectId, setProjectId] = useState('')
  const [period, setPeriod] = useState('30')
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const requestKey = JSON.stringify([refresh, revision, page, search, status, projectId, period, model, retry])
  const [snapshot, setSnapshot] = useState<{ key: string; data?: Page<PromptRun>; error?: string } | null>(null)
  const loading = snapshot?.key !== requestKey
  const data = loading ? undefined : snapshot?.data
  const error = loading ? '' : snapshot?.error

  useEffect(() => {
    let active = true
    const from = period === 'all' ? undefined : new Date(Date.now() - Number(period) * 86400000).toISOString()
    runService.list({ page, page_size: 10, search: search.trim() || undefined, status: status || undefined, project_id: projectId || undefined, model: model.trim() || undefined, from })
      .then((result) => {
        if (!active) return
        const lastPage = Math.max(1, Math.ceil(result.total / result.page_size))
        if (page > lastPage) { setPage(lastPage); return }
        setSnapshot({ key: requestKey, data: result })
      })
      .catch((cause) => { if (active) setSnapshot({ key: requestKey, error: cause instanceof Error ? cause.message : 'Could not load runs.' }) })
    return () => { active = false }
  }, [requestKey, page, search, status, projectId, period, model])

  return <><PageHeader title="Runs" description="Inspect prompt executions, failures, and cost." />
    <div className="toolbar">
      <input value={search} maxLength={160} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Search prompt or run ID" aria-label="Search runs" />
      <input value={model} maxLength={160} onChange={(event) => { setModel(event.target.value); setPage(1) }} placeholder="Exact model ID" aria-label="Run model" />
      <select aria-label="Run status" value={status} onChange={(event) => { setStatus(event.target.value as RunStatus | ''); setPage(1) }}><option value="">All statuses</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="blocked">Blocked</option></select>
      <select aria-label="Run project" value={projectId} onChange={(event) => { setProjectId(event.target.value); setPage(1) }}><option value="">All projects</option>{projectStore.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select>
      <select aria-label="Run period" value={period} onChange={(event) => { setPeriod(event.target.value); setPage(1) }}><option value="30">Last 30 days</option><option value="7">Last 7 days</option><option value="all">All time</option></select>
    </div>
    {loading ? <section className="panel empty-output" role="status">Loading runs…</section> : error ? <section className="panel run-outcome" role="alert"><h2>Could not load runs</h2><p>{error}</p><Button secondary onClick={() => setRetry((value) => value + 1)}>Try again</Button></section> : data && <>
      <section className="panel table-panel" tabIndex={0} aria-label="Run history table"><table><thead><tr><th>PROMPT / VERSION</th><th>PROJECT</th><th>STATUS</th><th>TOKENS</th><th>COST</th><th>WHEN</th></tr></thead><tbody>{data.items.map((run) => <tr key={run.id}><td><Link to={`/runs/${run.id}`}>{run.prompt_key} · v{run.version_number}</Link></td><td>{projectStore.find((project) => project.id === run.project_id)?.name ?? run.project_id}</td><td><RunStatusBadge status={run.status} /></td><td>{run.prompt_tokens == null ? '—' : (run.prompt_tokens + (run.completion_tokens ?? 0)).toLocaleString()}</td><td>${run.cost}</td><td>{dateTime(run.created_at)}</td></tr>)}</tbody></table>{!data.items.length && <p className="no-results">No runs match these filters.</p>}</section>
      <div className="run-pagination"><span>{data.total} runs · page {page}</span><div><Button secondary disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><Button secondary disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</Button></div></div>
    </>}
  </>
}

export function RunDetailPage() {
  const refresh = useLiveRefresh()
  const { runId } = useParams()
  const revision = useSyncExternalStore(runStore.subscribe, runStore.getSnapshot)
  const [run, setRun] = useState<PromptRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => { let active = true; runService.get(runId ?? '').then((result) => { if (active) { setRun(result ?? null); setLoading(false); setError('') } }).catch((cause) => { if (active) { setLoading(false); setError(cause instanceof Error ? cause.message : 'Could not load this run.') } }); return () => { active = false } }, [refresh, runId, revision, retry])
  if (loading) return <><PageHeader title="Run details" /><section className="panel empty-output">Loading run…</section></>
  if (error) return <><PageHeader title="Run details" /><section className="panel run-outcome" role="alert"><h2>Could not load this run</h2><p>{error}</p><Button secondary onClick={() => { setLoading(true); setRetry(retry + 1) }}>Try again</Button></section></>
  if (!run) return <><PageHeader title="Run not found" /><section className="panel run-outcome"><p>This run is unavailable.</p><Link to="/runs">Back to runs</Link></section></>
  return <><PageHeader title={`${run.prompt_key} · v${run.version_number}`} eyebrow="RUN DETAILS" description={`Executed ${dateTime(run.created_at)}`} action={<Link to="/runs"><Button secondary>Back to runs</Button></Link>} /><div className="detail-stats"><Stat label="STATUS" value={run.status} note={run.model} /><Stat label="TOKENS" value={run.prompt_tokens == null ? '—' : String(run.prompt_tokens + (run.completion_tokens ?? 0))} note="Prompt + completion" /><Stat label="COST" value={`$${run.cost}`} note={run.status === 'completed' ? 'Charged for this run' : 'No charge'} /></div><div className="detail-layout"><section className="panel"><div className="panel-head"><div><h2>Input variables</h2><p>Values supplied for this execution.</p></div></div>{Object.entries(run.input_variables).map(([key, value]) => <div className="run-variable" key={key}><code>{key}</code><p>{value}</p></div>)}<div className="editor-meta"><span>Run ID: {run.id}</span><span>Model: {run.model}</span></div></section><section className="panel output"><div className="panel-head"><div><h2>Output</h2><p>Execution result</p></div><RunStatusBadge status={run.status} /></div>{run.status === 'completed' ? <div className="output-copy">{run.output}</div> : <div className="run-outcome" role="alert"><h3>{run.status === 'blocked' ? 'Budget limit reached' : 'Run failed'}</h3><p>{run.error_message ?? 'The run could not be completed.'}</p></div>}<div className="editor-meta"><span>Latency: {run.latency_ms == null ? '—' : `${run.latency_ms} ms`}</span><Link to={`/playground?version=${run.version_id}`}>Run this version again</Link></div></section></div></>
}
