import { useLiveRefresh, refreshLiveData } from '../../lib/live-refresh'
import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Stat, Status } from '../../components/ui/prototype'
import { ConfirmationDialog } from '../../components/ui/confirmation-dialog'
import { useAuth } from '../auth/auth-context'
import { deploymentService, deploymentStore } from '../deployments/deployment-service'
import { versionStore, workspaceStore } from '../projects/workspace-data'
import { ApiClientError } from '../../lib/api/client'
import type { Deployment } from '../../types/deployments'

const statusLabel = (status: string) => status.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase())

export function DeploymentApprovalQueuePage() {
  const refresh = useLiveRefresh()
  const { user } = useAuth()
  const revision = useSyncExternalStore(deploymentStore.subscribe, deploymentStore.getSnapshot)
  const key = JSON.stringify([refresh, revision, user?.id])
  const [snapshot, setSnapshot] = useState<{ key: string; items?: Deployment[]; error?: string } | null>(null)
  useEffect(() => {
    let active = true
    deploymentService.pending(user).then((items) => { if (active) setSnapshot({ key, items }) })
      .catch((cause) => { if (active) setSnapshot({ key, error: cause instanceof Error ? cause.message : 'Could not load approvals.' }) })
    return () => { active = false }
  }, [key, user])
  const ready = snapshot?.key === key
  return <><PageHeader title="Approvals" eyebrow="ADMINISTRATION" description="Review production deployment requests." />{!ready ? <p role="status">Loading approvals…</p> : snapshot.error ? <section className="panel" role="alert">{snapshot.error} <Button secondary onClick={refreshLiveData}>Try again</Button></section> : <section className="panel table-panel" tabIndex={0} aria-label="Pending deployment approvals"><table><thead><tr><th>REQUEST</th><th>PROJECT</th><th>REQUESTED BY</th><th>STATUS</th></tr></thead><tbody>{snapshot.items?.map((item) => <tr key={item.id}><td><Link to={`/admin/approvals/${item.id}`}>{item.prompt_key} v{item.version_number} → Production</Link></td><td>{item.project_name}</td><td>{item.requested_by_name}</td><td><Status tone="warning">Pending review</Status></td></tr>)}</tbody></table>{!snapshot.items?.length && <p className="no-results">No production requests are waiting for review.</p>}</section>}</>
}

export function DeploymentApprovalReviewPage() {
  const { approvalId } = useParams()
  return <ApprovalReviewContent key={approvalId} approvalId={approvalId ?? ''} />
}
function ApprovalReviewContent({ approvalId }: { approvalId: string }) {
  const refresh = useLiveRefresh()
  const { user } = useAuth()
  const revision = useSyncExternalStore(deploymentStore.subscribe, deploymentStore.getSnapshot)
  const key = JSON.stringify([refresh, revision, approvalId, user?.id])
  type Detail = Awaited<ReturnType<typeof deploymentService.reviewDetail>>
  const [snapshot, setSnapshot] = useState<{ key: string; detail?: Detail; error?: string } | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState<'approve' | 'reject' | null>(null)
  const [pending, setPending] = useState(false)
  const pendingRef = useRef(false)
  useEffect(() => {
    const controller = new AbortController()
    deploymentService.reviewDetail(approvalId, user, controller.signal)
      .then((detail) => { if (!controller.signal.aborted) setSnapshot({ key, detail }) })
      .catch((cause) => { if (!controller.signal.aborted) setSnapshot({ key, error: cause instanceof Error ? cause.message : 'Could not load request.' }) })
    return () => controller.abort()
  }, [key, approvalId, user])
  const ready = snapshot?.key === key
  const detail = ready ? snapshot.detail : undefined
  const item = detail?.deployment
  const candidate = detail?.requested_version
  const base = detail?.active_version
  const recentRuns = detail?.recent_runs ?? []
  const baseLines = base?.template.split('\n') ?? []
  const candidateLines = candidate?.template.split('\n') ?? []
  const addedLines = candidateLines.filter((line) => !baseLines.includes(line)).length
  const removedLines = baseLines.filter((line) => !candidateLines.includes(line)).length
  async function decide() {
    if (!item || item.status !== 'pending_approval' || !confirmation || pendingRef.current) return
    pendingRef.current = true
    setPending(true)
    setError('')
    try {
      await deploymentService.review(item.id, confirmation, { note }, user)
      // The service notifies both the queue and review through the shared refresh signal.
    } catch (cause) {
      setError(cause instanceof ApiClientError && cause.status === 409 ? `${cause.message}. The latest decision is being loaded; your note is preserved.` : cause instanceof Error ? cause.message : 'Could not complete review.')
      refreshLiveData()
    } finally {
      pendingRef.current = false
      setPending(false)
      setConfirmation(null)
    }
  }
  if (!ready) return <><PageHeader title="Review deployment" /><p role="status">Loading request…</p></>
  if (!item) return <><PageHeader title="Review deployment" /><section className="panel" role="alert">{snapshot.error || 'Request not found.'} <Button secondary onClick={refreshLiveData}>Try again</Button></section></>
  return <><PageHeader title={`${item.prompt_key} v${item.version_number} → Production`} eyebrow="APPROVALS / REVIEW" description={`Requested by ${item.requested_by_name}.`} action={<Status tone={item.status === 'pending_approval' ? 'warning' : item.status === 'active' ? 'success' : 'neutral'}>{statusLabel(item.status)}</Status>} />{error && <p className="form-error" role="alert">{error} <Button secondary onClick={refreshLiveData}>Try again</Button></p>}<div className="detail-stats"><Stat label="PROJECT" value={item.project_name} note="Production request" /><Stat label="VERSION" value={`v${item.version_number}`} note="Immutable snapshot" /><Stat label="RECENT RUNS" value={String(recentRuns.length)} note={`${recentRuns.filter((run) => run.status === 'completed').length} completed`} /></div><div className="detail-layout"><section className="panel editor"><div className="panel-head"><div><h2>Version evidence</h2><p>{base ? `v${base.version_number} currently active → v${candidate?.version_number ?? item.version_number} candidate` : 'Production candidate snapshot.'}</p></div></div>{base && <div className="diff-summary"><Status>v{base.version_number} current</Status><span>→</span><Status tone="success">v{candidate?.version_number} candidate</Status><span>+{addedLines} / −{removedLines} lines</span></div>}<label className="field"><span>Production candidate</span><textarea readOnly value={candidate?.template ?? 'Version unavailable'} /></label><div className="editor-meta"><span>{candidate?.variables.length ?? 0} variables · {candidate?.model_config.model ?? '—'}</span><span>{candidate?.commit_message ?? ''}</span></div>{base && <details className="review-base"><summary>View current production v{base.version_number}</summary><pre>{base.template}</pre></details>}</section><section className="panel"><div className="panel-head"><div><h2>Run evidence</h2><p>Latest runs of this exact version.</p></div></div>{recentRuns.length ? recentRuns.map((run) => <Link className="health-row" to={`/runs/${run.id}`} key={run.id}><span>{run.status} · {new Date(run.created_at).toLocaleDateString()}</span><b>{run.prompt_key} · v{run.version_number}</b></Link>) : <p className="empty-evidence">No runs recorded for this version yet.</p>}{item.status === 'pending_approval' && <><label className="field"><span>Review note</span><textarea disabled={pending} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add context for this decision…" /></label><div className="review-actions"><Button secondary disabled={pending} onClick={() => { if (!note.trim()) return setError('Add a reason before rejecting.'); setConfirmation('reject') }}>Reject request</Button><Button disabled={pending} onClick={() => setConfirmation('approve')}>Approve production</Button></div></>}{item.status !== 'pending_approval' && note && <p>Your draft note: {note}</p>}{item.status !== 'pending_approval' && <div className="inline-notice"><Status tone={item.status === 'active' ? 'success' : 'neutral'}>{statusLabel(item.status)}</Status><p>{item.review_note || 'This request has been reviewed.'}</p></div>}</section></div><ConfirmationDialog open={confirmation !== null} title={confirmation === 'approve' ? 'Approve production deployment' : 'Reject deployment request'} message={confirmation === 'approve' ? `Activate ${item.prompt_key} v${item.version_number} in production?` : 'Reject this production request with the entered reason?'} pending={pending} onConfirm={decide} onCancel={() => setConfirmation(null)} /></>
}

export function DeploymentRollbackPage() {
  const refresh = useLiveRefresh()
  const { user } = useAuth()
  const navigate = useNavigate()
  const revision = useSyncExternalStore(deploymentStore.subscribe, deploymentStore.getSnapshot)
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot)
  const key = JSON.stringify([refresh, revision, user?.id])
  const [snapshot, setSnapshot] = useState<{ key: string; items?: Deployment[]; error?: string } | null>(null)
  const [activeId, setActiveId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState<{ activeId: string; targetId: string } | null>(null)
  const [pending, setPending] = useState(false)
  const pendingRef = useRef(false)
  useEffect(() => {
    let active = true
    deploymentService.activeProduction().then((items) => {
      if (!active) return
      setSnapshot({ key, items })
      setActiveId((current) => current || items[0]?.id || '')
    }).catch((cause) => { if (active) setSnapshot({ key, error: cause instanceof Error ? cause.message : 'Could not load active deployments.' }) })
    return () => { active = false }
  }, [key])
  const ready = snapshot?.key === key
  const activeItems = ready ? snapshot.items ?? [] : []
  const selected = activeItems.find((item) => item.id === activeId)
  const options = selected ? (versionStore[selected.prompt_id] ?? []).filter((version) => version.version_number < selected.version_number) : []
  const chosen = targetId ? options.find((version) => version.id === targetId) : options[0]
  const loadError = ready ? snapshot.error : undefined
  async function rollback() {
    if (pendingRef.current) return
    if (!selected || !chosen || confirmation?.activeId !== selected.id || confirmation.targetId !== chosen.id) {
      setError('The active deployment or target changed. Review the current selection again.')
      setConfirmation(null)
      return
    }
    pendingRef.current = true
    setPending(true)
    try {
      const item = await deploymentService.rollback(selected.id, chosen.id, note, user)
      navigate(`/deployments/${item.id}`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create rollback.')
      setConfirmation(null)
      refreshLiveData()
    } finally { pendingRef.current = false; setPending(false) }
  }
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!note.trim()) return setError('A rollback reason is required.')
    if (!selected || !chosen) return setError('Select an active production deployment and an earlier version.')
    setError('')
    setConfirmation({ activeId: selected.id, targetId: chosen.id })
  }
  return <><PageHeader title="Rollback deployment" eyebrow="ADMINISTRATION" description="Restore an earlier immutable version in production." />
    {(error || loadError) && <p className="form-error" role="alert">{error || loadError} <Button secondary onClick={refreshLiveData}>Try again</Button></p>}
    {!ready && <p role="status">Loading active production deployments…</p>}
    {ready && !loadError && !activeItems.length && <p>No active production deployments are available.</p>}
    {ready && activeId && !selected && <p role="alert">The selected deployment is no longer active. Select the current production deployment.</p>}
    <div className="detail-layout deployment-impact-layout"><form className="form-panel" onSubmit={submit}>
      <label className="field"><span>Active deployment</span><select disabled={!ready || pending} value={selected?.id ?? ''} onChange={(event) => { setActiveId(event.target.value); setTargetId(''); setConfirmation(null) }}>
        <option value="" disabled>Select active production deployment</option>
        {activeItems.map((item) => <option value={item.id} key={item.id}>{item.project_name} · {item.prompt_key} · production v{item.version_number}</option>)}
      </select></label>
      <label className="field"><span>Restore version</span><select disabled={!selected || pending} value={chosen?.id ?? ''} onChange={(event) => { setTargetId(event.target.value); setConfirmation(null) }}>{options.map((version) => <option value={version.id} key={version.id}>v{version.version_number} · {version.commit_message}</option>)}</select></label>
      {selected && !options.length && <p className="deployment-hint">This deployment has no earlier version to restore.</p>}
      <label className="field"><span>Rollback reason</span><textarea disabled={pending} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Why is this rollback required?" /></label>
      <div className="form-actions"><Button secondary type="button" disabled={pending} onClick={() => navigate('/deployments')}>Cancel</Button><Button type="submit" disabled={!selected || !chosen || pending}>Review rollback</Button></div>
    </form><section className="panel"><div className="panel-head"><div><h2>Deployment impact</h2><p>Review the current production state before proceeding.</p></div></div>
      {[['Project', selected?.project_name ?? '—'], ['Prompt', selected?.prompt_key ?? '—'], ['Environment', 'production'], ['Current version', selected ? `v${selected.version_number}` : '—'], ['Rollback target', chosen ? `v${chosen.version_number}` : '—'], ['History', 'Preserved']].map(([name, value]) => <div className="health-row" key={name}><span>{name}</span><b>{value}</b></div>)}
      {selected && <Link className="deployment-impact-link" to={`/deployments/${selected.id}`}>View active deployment →</Link>}
    </section></div>
    <ConfirmationDialog open={confirmation !== null} title="Confirm rollback" message={`Restore ${selected?.prompt_key ?? 'prompt'} to v${chosen?.version_number ?? '—'} in production? This creates a new deployment record.`} pending={pending} onConfirm={rollback} onCancel={() => setConfirmation(null)} />
  </>
}
