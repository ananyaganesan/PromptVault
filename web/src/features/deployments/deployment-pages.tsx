import { useLiveRefresh, refreshLiveData } from '../../lib/live-refresh'
import { useEffect, useState, useSyncExternalStore, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Status } from '../../components/ui/prototype'
import { ConfirmationDialog } from '../../components/ui/confirmation-dialog'
import { useAuth } from '../auth/auth-context'
import { projectStore, promptStore, versionStore, workspaceStore } from '../projects/workspace-data'
import { deploymentService, deploymentStore } from './deployment-service'
import type { Page } from '../../types/api'
import type { Deployment, DeploymentEnvironment, DeploymentStatus } from '../../types/deployments'

const dateTime = (value: string) => new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const label = (value: string) => value.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase())
const tone = (status: DeploymentStatus) => status === 'active' ? 'success' : status === 'pending_approval' ? 'warning' : 'neutral'

export function DeploymentListPage() {
  const refresh = useLiveRefresh()
  const revision = useSyncExternalStore(deploymentStore.subscribe, deploymentStore.getSnapshot)
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot)
  const [projectId, setProjectId] = useState('')
  const [status, setStatus] = useState<DeploymentStatus | ''>('')
  const [environment, setEnvironment] = useState<DeploymentEnvironment | ''>('')
  const [page, setPage] = useState(1)
  const requestKey = JSON.stringify([refresh, revision, page, projectId, status, environment])
  const [snapshot, setSnapshot] = useState<{ key: string; data?: Page<Deployment>; error?: string } | null>(null)
  const loading = snapshot?.key !== requestKey
  const data = loading ? undefined : snapshot?.data
  const error = loading ? '' : snapshot?.error
  const hasFilters = Boolean(projectId || status || environment)
  useEffect(() => {
    let active = true
    deploymentService.list({ page, page_size: 10, project_id: projectId || undefined, status: status || undefined, environment: environment || undefined })
      .then((result) => {
        if (!active) return
        const lastPage = Math.max(1, Math.ceil(result.total / result.page_size))
        if (page > lastPage) { setPage(lastPage); return }
        setSnapshot({ key: requestKey, data: result })
      })
      .catch((cause) => { if (active) setSnapshot({ key: requestKey, error: cause instanceof Error ? cause.message : 'Could not load deployments.' }) })
    return () => { active = false }
  }, [requestKey, page, projectId, status, environment])
  return <><PageHeader title="Deployments" description="Track prompt promotion across environments." action={<Link to="/deployments/new"><Button>New deployment</Button></Link>} />
    <div className="toolbar">
      <select aria-label="Deployment project" value={projectId} onChange={(event) => { setProjectId(event.target.value); setPage(1) }}><option value="">All projects</option>{projectStore.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select>
      <select aria-label="Deployment status" value={status} onChange={(event) => { setStatus(event.target.value as DeploymentStatus | ''); setPage(1) }}><option value="">All statuses</option>{(['active', 'pending_approval', 'rejected', 'cancelled', 'superseded', 'rolled_back'] as const).map((item) => <option value={item} key={item}>{label(item)}</option>)}</select>
      <select aria-label="Deployment environment" value={environment} onChange={(event) => { setEnvironment(event.target.value as DeploymentEnvironment | ''); setPage(1) }}><option value="">All environments</option><option value="development">Development</option><option value="staging">Staging</option><option value="production">Production</option></select>
    </div>
    {loading ? <section className="panel empty-output" role="status">Loading deployments…</section> : error ? <section className="panel" role="alert">{error} <Button secondary onClick={refreshLiveData}>Try again</Button></section> : data && <>
      <section className="panel table-panel deployment-table" tabIndex={0} aria-label="Deployment history table"><table><thead><tr><th>PROMPT / ENVIRONMENT</th><th>PROJECT</th><th>VERSION</th><th>STATUS</th><th>REQUESTED BY</th><th>CREATED</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id}><td><Link to={`/deployments/${item.id}`}>{item.prompt_key} → {label(item.environment)}</Link></td><td>{item.project_name}</td><td>v{item.version_number}</td><td><Status tone={tone(item.status)}>{label(item.status)}</Status></td><td>{item.requested_by_name}</td><td>{dateTime(item.created_at)}</td></tr>)}</tbody></table>{!data.items.length && <p className="no-results">{hasFilters ? 'No deployments match these filters.' : 'No deployments have been created yet.'}</p>}</section>
      <div className="run-pagination"><span>{data.total} deployments · page {page}</span><div><Button secondary disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><Button secondary disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</Button></div></div>
    </>}
  </>
}

export function NewDeploymentPage() {
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot)
  const { user } = useAuth(); const navigate = useNavigate(); const [params] = useSearchParams()
  const [versionId, setVersionId] = useState(params.get('version') ?? Object.values(versionStore).flat()[0]?.id ?? '')
  const [environment, setEnvironment] = useState<DeploymentEnvironment>('staging'); const [note, setNote] = useState(''); const [error, setError] = useState(''); const [pending, setPending] = useState(false)
  async function submit(event: FormEvent) { event.preventDefault(); setPending(true); setError(''); try { const item = await deploymentService.create({ version_id: versionId, environment, note }, user); navigate(`/deployments/${item.id}`) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create deployment.') } finally { setPending(false) } }
  return <><PageHeader title="Create deployment" eyebrow="DEPLOYMENTS" description="Promote an immutable prompt version to an environment." /><form className="form-panel" onSubmit={submit}>{error && <p className="form-error" role="alert">{error}</p>}<label className="field"><span>Prompt version</span><select value={versionId} onChange={(event) => setVersionId(event.target.value)}>{Object.values(versionStore).flat().map((version) => <option value={version.id} key={version.id}>{promptStore.find((prompt) => prompt.id === version.prompt_id)?.key ?? version.prompt_id} · v{version.version_number}</option>)}</select></label><label className="field"><span>Environment</span><select value={environment} onChange={(event) => setEnvironment(event.target.value as DeploymentEnvironment)}><option value="development">Development</option><option value="staging">Staging</option><option value="production">Production (requires approval)</option></select></label>{environment === 'production' && <p className="deployment-hint">Production requests enter the Super Admin approval queue. The current production version remains active until approval.</p>}<label className="field"><span>Deployment note</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="What changed in this deployment?" /></label><div className="form-actions"><Button secondary type="button" onClick={() => navigate('/deployments')}>Cancel</Button><Button type="submit" disabled={pending}>{pending ? 'Creating…' : environment === 'production' ? 'Request approval' : 'Create deployment'}</Button></div></form></>
}

export function DeploymentDetailPage() {
  const refresh = useLiveRefresh()
  const { deploymentId } = useParams(); const { user } = useAuth(); const revision = useSyncExternalStore(deploymentStore.subscribe, deploymentStore.getSnapshot)
  const key = JSON.stringify([refresh, deploymentId, revision])
  const [snapshot, setSnapshot] = useState<{ key: string; item?: Deployment; error?: string } | null>(null)
  const [error, setError] = useState(''); const [confirm, setConfirm] = useState(false)
  const loading = snapshot?.key !== key
  const item = loading ? undefined : snapshot?.item
  useEffect(() => { let active = true; deploymentService.get(deploymentId ?? '').then((result) => { if (active) setSnapshot({ key, item: result }) }).catch((cause) => { if (active) setSnapshot({ key, error: cause instanceof Error ? cause.message : 'Could not load deployment.' }) }); return () => { active = false } }, [key, deploymentId])
  async function cancel() { if (!item) return; try { await deploymentService.cancel(item.id, user); setConfirm(false); setError('') } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not cancel request.'); setConfirm(false); refreshLiveData() } }
  if (loading) return <><PageHeader title="Deployment" /><section className="panel empty-output">Loading deployment…</section></>
  if (!item) return <><PageHeader title="Deployment" /><section className="panel">{snapshot?.error || error || 'Deployment not found.'} <Button secondary onClick={refreshLiveData}>Try again</Button> <Link to="/deployments">Back to deployments</Link></section></>
  return <><PageHeader title={`${item.prompt_key} → ${label(item.environment)}`} eyebrow="DEPLOYMENT DETAIL" description={`Requested ${dateTime(item.created_at)} by ${item.requested_by_name}.`} action={<Status tone={tone(item.status)}>{label(item.status)}</Status>} />{error && <p className="form-error" role="alert">{error}</p>}<div className="detail-layout"><section className="panel"><div className="panel-head"><div><h2>Deployment</h2><p>Immutable version and requested environment.</p></div></div>{[['Project', item.project_name], ['Prompt', item.prompt_key], ['Version', `v${item.version_number}`], ['Environment', label(item.environment)], ['Status', label(item.status)], ['Requested by', item.requested_by_name], ['Note', item.note || '—'], ['Activated', item.activated_at ? dateTime(item.activated_at) : '—'], ['Rollback of', item.rollback_of_id || '—'], ['Rollback reason', item.rollback_reason || '—']].map(([name, value]) => <div className="health-row" key={name}><span>{name}</span><b>{value}</b></div>)}<div className="form-actions">{item.status === 'pending_approval' && item.requested_by === user?.id && <Button secondary onClick={() => setConfirm(true)}>Cancel request</Button>}</div></section><section className="panel"><div className="panel-head"><div><h2>Timeline</h2><p>Recent deployment history for this environment.</p></div></div><div className="version-row"><span className="timeline-dot current" /><div><b>Requested</b><small>{dateTime(item.created_at)} · {item.requested_by_name}</small></div></div>{item.reviewed_at && <div className="version-row"><span className="timeline-dot current" /><div><b>{label(item.status)}</b><small>{dateTime(item.reviewed_at)} · {item.review_note || 'No review note'}</small></div></div>}{item.status === 'pending_approval' && <div className="version-row"><span className="timeline-dot" /><div><b>Awaiting Super Admin review</b><small>Production stays on its current active version.</small></div></div>}{item.status === 'cancelled' && <div className="version-row"><span className="timeline-dot" /><div><b>Cancelled</b><small>The request was withdrawn before review.</small></div></div>}{item.timeline?.map((event) => <div className="version-row" key={event.id}><span className="timeline-dot" /><div><Link to={`/deployments/${event.id}`}>v{event.version_number} · {label(event.status)}</Link><small>Requested {dateTime(event.requested_at)}{event.reviewed_at ? ` · Reviewed ${dateTime(event.reviewed_at)}` : ''}{event.activated_at ? ` · Activated ${dateTime(event.activated_at)}` : ''}</small></div></div>)}{user?.role === 'super_admin' && item.status === 'pending_approval' && <Link to={`/admin/approvals/${item.id}`}>Review request →</Link>}</section></div><ConfirmationDialog open={confirm} title="Cancel deployment request" message="Withdraw this pending production request?" onConfirm={cancel} onCancel={() => setConfirm(false)} /></>
}
