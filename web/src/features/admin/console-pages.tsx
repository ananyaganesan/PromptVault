import { LLM_PROVIDERS } from "../../lib/providers"
import { useCallback, useEffect, useState, useSyncExternalStore, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Stat, Status } from '../../components/ui/prototype'
import { Modal } from '../../components/ui/modal'
import { ConfirmationDialog } from '../../components/ui/confirmation-dialog'
import { useAuth } from '../auth/auth-context'
import { deploymentStore } from '../deployments/deployment-service'
import { projectStore } from '../projects/workspace-data'
import { runStore } from '../runs/run-service'
import { adminService, adminStore, isDemoAdmin, listAllAdminUsers } from './admin-service'
import type { AdminUser, OrganizationDashboard, ProviderKeyMetadata } from '../../types/admin'
import type { PromptRun, RunStatus } from '../../types/runs'
import type { Page } from '../../types/api'

export function useAdminData<T>(load: () => Promise<T>, revisionKey = '') {
  const [data, setData] = useState<T | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [retry, setRetry] = useState(0)
  useEffect(() => { let active = true; load().then((value) => { if (active) { setData(value); setError(''); setLoading(false) } }).catch((cause) => { if (active) { setError(cause instanceof Error ? cause.message : 'Could not load data.'); setLoading(false) } }); return () => { active = false } }, [load, retry, revisionKey])
  return { data, loading, error, reload: () => { setLoading(true); setRetry((value) => value + 1) } }
}

export function AdminDataState({ loading, error, onRetry }: { loading: boolean; error: string; onRetry: () => void }) {
  if (error) return <section className="panel admin-state" role="alert"><p>{error}</p><Button secondary onClick={onRetry}>Try again</Button></section>
  if (loading) return <section className="panel admin-state">Loading…</section>
  return null
}

export function AdminDashboardPage() {
  const { user } = useAuth(); const revision = useSyncExternalStore(adminStore.subscribe, adminStore.getSnapshot); const runRevision = useSyncExternalStore(runStore.subscribe, runStore.getSnapshot); const deploymentRevision = useSyncExternalStore(deploymentStore.subscribe, deploymentStore.getSnapshot)
  const load = useCallback(() => adminService.dashboard(user), [user])
  const { data, loading, error, reload } = useAdminData<OrganizationDashboard>(load, `${revision}:${runRevision}:${deploymentRevision}`)
  return <><PageHeader title="Administration" eyebrow="ADMINISTRATION" description="Organization-wide visibility, governance, and controls." />{isDemoAdmin && <p className="deployment-hint">Prototype data · live organization APIs are not connected.</p>}{!data ? <AdminDataState loading={loading} error={error} onRetry={reload} /> : <><div className="stats-grid"><Stat label="ORGANIZATION SPEND" value={`$${data.monthly_spend}`} note="This month" /><Stat label="TOTAL RUNS" value={String(data.run_count)} note="All recorded runs" /><Stat label="ACTIVE USERS" value={String(data.active_user_count)} note="Enabled accounts" /><Stat label="PENDING APPROVALS" value={String(data.pending_approval_count)} note="Requires review" /></div><div className="dashboard-grid"><section className="panel"><div className="panel-head"><div><h2>Spend by model</h2><p>Completed run charges.</p></div></div>{data.spend_by_model.length ? data.spend_by_model.map((item) => <div className="bar-item" key={item.model}><div><span>{item.model}</span><b>${item.cost}</b></div><div className="bar"><i style={{ width: `${item.percentage}%` }} /></div></div>) : <p className="empty-evidence">No chargeable runs yet.</p>}</section><section className="panel"><div className="panel-head"><div><h2>Governance health</h2><p>Review queue and operational checks.</p></div></div><div className="health-row"><span>Approval queue</span><Link to="/admin/approvals">{data.pending_approval_count} pending</Link></div><div className="health-row"><span>Users</span><Link to="/admin/users">{data.active_user_count} active</Link></div><div className="health-row"><span>Maintenance</span><Link to="/admin/maintenance">View health</Link></div></section></div></>}{error && <p className="form-error" role="alert">{error}</p>}</>
}

export function AdminRunsExplorerPage() {
  const { user } = useAuth(); const runRevision = useSyncExternalStore(runStore.subscribe, runStore.getSnapshot); const [status, setStatus] = useState<RunStatus | ''>(''); const [projectId, setProjectId] = useState(''); const [userId, setUserId] = useState(''); const [search, setSearch] = useState(''); const [page, setPage] = useState(1); const [userOptions, setUserOptions] = useState<AdminUser[]>([])
  useEffect(() => { let active = true; listAllAdminUsers(user).then((result) => { if (active) setUserOptions(result) }).catch(() => undefined); return () => { active = false } }, [user])
  const load = useCallback(() => adminService.listRuns({ page, page_size: 20, search: search.trim() || undefined, status: status || undefined, project_id: projectId || undefined, user_id: userId || undefined }, user), [user, search, status, projectId, userId, page])
  const { data, loading, error, reload } = useAdminData<Page<PromptRun>>(load, String(runRevision))
  const visible = data?.items ?? []
  const hasFilters = Boolean(search.trim() || status || projectId || userId)
  return <><PageHeader title="Organization runs" eyebrow="ADMINISTRATION" description="Inspect model activity across projects and users." /><div className="toolbar"><input aria-label="Search runs" placeholder="Search prompt or run ID" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} /><select aria-label="Run status" value={status} onChange={(event) => { setStatus(event.target.value as RunStatus | ''); setPage(1) }}><option value="">All statuses</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="blocked">Blocked</option></select><select aria-label="Run project" value={projectId} onChange={(event) => { setProjectId(event.target.value); setPage(1) }}><option value="">All projects</option>{projectStore.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><select aria-label="Run user" value={userId} onChange={(event) => { setUserId(event.target.value); setPage(1) }}><option value="">All users</option>{userOptions.map((item) => <option value={item.id} key={item.id}>{item.display_name}</option>)}</select></div>{!data ? <AdminDataState loading={loading} error={error} onRetry={reload} /> : <><section className="panel table-panel" tabIndex={0} aria-label="Organization runs table"><table><thead><tr><th>RUN</th><th>PROMPT</th><th>PROJECT</th><th>USER</th><th>STATUS</th><th>TOKENS</th><th>COST</th></tr></thead><tbody>{visible.map((run) => <tr key={run.id}><td><Link to={`/runs/${run.id}`}><code>{run.id}</code></Link></td><td>{run.prompt_key} v{run.version_number}</td><td>{projectStore.find((item) => item.id === run.project_id)?.name ?? run.project_id}</td><td>{userOptions.find((item) => item.id === run.user_id)?.display_name ?? run.user_id}</td><td><Status tone={run.status === 'completed' ? 'success' : 'warning'}>{run.status}</Status></td><td>{run.prompt_tokens == null ? '—' : run.prompt_tokens + (run.completion_tokens ?? 0)}</td><td>${run.cost}</td></tr>)}</tbody></table>{!visible.length && <p className="no-results">{hasFilters ? 'No runs match these filters.' : 'No organization runs have been recorded yet.'}</p>}</section><div className="run-pagination"><span>{data.total} runs · page {page}</span><div><Button secondary disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><Button secondary disabled={page * 20 >= data.total} onClick={() => setPage(page + 1)}>Next</Button></div></div></>}{error && <p className="form-error" role="alert">{error}</p>}</>
}

export function UserManagementPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const revision = useSyncExternalStore(adminStore.subscribe, adminStore.getSnapshot)
  const [search, setSearch] = useState('')
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [pending, setPending] = useState<{ target: AdminUser; role?: 'user' | 'admin' | 'super_admin'; is_active?: boolean; is_approved?: boolean } | null>(null)
  const [saving, setSaving] = useState(false)
  const [mutationError, setMutationError] = useState('')
  const load = useCallback(() => adminService.listUsers({ page, page_size: 25, search, role: role || undefined, is_active: status === '' ? undefined : status === 'active' }, user), [user, page, search, role, status])
  const { data, loading, error, reload } = useAdminData<Page<AdminUser>>(load, String(revision))
  const hasFilters = Boolean(search || role || status)
  async function save() {
    if (!pending || saving) return
    setSaving(true)
    try {
      const request = { ...(pending.role !== undefined ? { role: pending.role } : {}), ...(pending.is_active !== undefined ? { is_active: pending.is_active } : {}), ...(pending.is_approved !== undefined ? { is_approved: pending.is_approved } : {}) }
      await adminService.updateUser(pending.target.id, request, user)
      setMutationError('')
      if (pending.target.id === user?.id) { logout(); navigate('/login'); return }
      setPending(null)
    } catch (cause) { setMutationError(cause instanceof Error ? cause.message : 'Could not update user.'); setPending(null) }
    finally { setSaving(false) }
  }
  return <>
    <PageHeader title={user?.role === 'admin' ? 'User approvals' : 'Users'} eyebrow={user?.role === 'admin' ? 'ADMIN' : 'SUPER ADMIN'} description={user?.role === 'admin' ? 'Approve verified accounts and manage regular user access.' : 'Approve verified accounts, assign roles, and manage user access.'} />
    <div className="toolbar">
      <input aria-label="Search users" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Search users" />
      <select aria-label="Role filter" value={role} onChange={(event) => { setRole(event.target.value); setPage(1) }}><option value="">All roles</option><option value="super_admin">Super Admin</option><option value="admin">Admin</option><option value="user">User</option></select>
      <select aria-label="Status filter" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select>
    </div>
    {mutationError && <p className="form-error" role="alert">{mutationError}</p>}
    {!data ? <AdminDataState loading={loading} error={error} onRetry={reload} /> : <section className="panel table-panel" tabIndex={0} aria-label="Users table"><table><thead><tr><th>USER</th><th>ROLE</th><th>PROJECTS</th><th>LAST ACTIVE</th><th>STATUS</th><th>ACTIONS</th></tr></thead><tbody>{data.items.map((item) => {
      const peerDemotion = item.role === 'super_admin' && item.id !== user?.id
      const canManage = user?.role === 'super_admin' || item.role === 'user'
      const roleLabel = item.role === 'super_admin' ? 'Super Admin' : item.role === 'admin' ? 'Admin' : 'User'
      return <tr key={item.id}>
        <td><b>{item.display_name}</b><small className="user-email">{item.email}</small></td><td>{roleLabel}</td><td>{item.project_count}</td><td>{item.last_active_at ? new Date(item.last_active_at).toLocaleDateString() : 'Never'}</td>
        <td><Status tone={!item.is_active ? 'neutral' : item.is_approved === false ? 'warning' : 'success'}>{!item.is_active ? 'Inactive' : item.is_approved === false ? 'Awaiting approval' : 'Active'}</Status></td>
        <td className="admin-actions">
          {user?.role === 'super_admin' && <>
            <button className="text-button" disabled={peerDemotion || saving} title={peerDemotion ? 'Super Admins cannot demote another Super Admin' : undefined} onClick={() => setPending({ target: item, role: item.role === 'user' ? 'admin' : 'user' })}>{item.role === 'user' ? 'Make admin' : 'Make user'}</button>
            {item.role !== 'super_admin' && <button className="text-button" disabled={saving} onClick={() => setPending({ target: item, role: 'super_admin' })}>Make Super Admin</button>}
          </>}
          {canManage && <>
            {item.is_approved === false && <button className="text-button" disabled={saving} onClick={() => setPending({ target: item, is_approved: true })}>Approve user</button>}
            <button className="text-button" disabled={saving} onClick={() => setPending({ target: item, is_active: !item.is_active })}>{item.is_active ? 'Deactivate' : 'Activate'}</button>
          </>}
        </td>
      </tr>
    })}</tbody></table>{!data.items.length && <p className="no-results">{hasFilters ? 'No users match these filters.' : 'No users are available.'}</p>}</section>}
    {data && <div className="run-pagination"><span>{data.total} users · page {page}</span><div><Button secondary disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><Button secondary disabled={page * 25 >= data.total} onClick={() => setPage(page + 1)}>Next</Button></div></div>}
    {error && data && <p className="form-error" role="alert">{error}</p>}
    <ConfirmationDialog open={pending !== null} pending={saving} title="Confirm user change" message={pending ? pending.is_approved ? `Approve access for ${pending.target.display_name}?` : pending.role ? `Change ${pending.target.display_name} to ${pending.role === 'super_admin' ? 'Super Admin' : pending.role === 'admin' ? 'Admin' : 'User'}?` : `${pending.is_active ? 'Activate' : 'Deactivate'} ${pending.target.display_name}?` : ''} onConfirm={save} onCancel={() => setPending(null)} />
  </>
}

export function ProviderKeyManagementPage() {
  const { user } = useAuth(); const revision = useSyncExternalStore(adminStore.subscribe, adminStore.getSnapshot); const [open, setOpen] = useState(false); const [provider, setProvider] = useState('gemini'); const [label, setLabel] = useState(''); const [secret, setSecret] = useState(''); const [deactivateId, setDeactivateId] = useState<string | null>(null); const [mutationError, setMutationError] = useState('')
  const load = useCallback(() => adminService.listProviderKeys(user), [user])
  const { data, loading, error, reload } = useAdminData<ProviderKeyMetadata[]>(load, String(revision))
  async function create(event: FormEvent) { event.preventDefault(); try { await adminService.addProviderKey({ provider, label, secret }, user); setOpen(false); setSecret(''); setLabel(''); setMutationError('') } catch (cause) { setMutationError(cause instanceof Error ? cause.message : 'Could not add provider key.') } }
  async function deactivate() { if (!deactivateId) return; try { await adminService.deactivateProviderKey(deactivateId, user); setDeactivateId(null); setMutationError('') } catch (cause) { setMutationError(cause instanceof Error ? cause.message : 'Could not deactivate key.'); setDeactivateId(null) } }
  return <><PageHeader title="Provider keys" eyebrow="ADMINISTRATION" description="Manage provider credentials without exposing saved values." action={<Button onClick={() => setOpen(true)}>Add provider key</Button>} />{mutationError && <p className="form-error" role="alert">{mutationError}</p>}{!data ? <AdminDataState loading={loading} error={error} onRetry={reload} /> : <section className="panel table-panel" tabIndex={0} aria-label="Provider keys table"><table><thead><tr><th>PROVIDER</th><th>LABEL</th><th>CREATED</th><th>STATUS</th><th></th></tr></thead><tbody>{data.map((item) => <tr key={item.id}><td>{item.provider}</td><td>{item.label}</td><td>{new Date(item.created_at).toLocaleDateString()}</td><td><Status tone={item.deactivated_at ? 'neutral' : 'success'}>{item.deactivated_at ? 'Inactive' : 'Active'}</Status></td><td>{!item.deactivated_at && <button className="text-button danger" onClick={() => setDeactivateId(item.id)}>Deactivate</button>}</td></tr>)}</tbody></table>{!data.length && <p className="no-results">No provider keys configured.</p>}</section>}<Modal open={open} title="Add provider key" onClose={() => { setOpen(false); setSecret('') }}><form onSubmit={create}><label className="field"><span>Provider</span><select value={provider} onChange={(event) => setProvider(event.target.value)}>{LLM_PROVIDERS.map((name) => <option key={name} value={name}>{name}</option>)}</select></label><label className="field"><span>Label</span><input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Sandbox key" required /></label><label className="field"><span>Secret key</span><input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} autoComplete="off" required /></label><p className="deployment-hint">Use a key from a free-tier project account. Saved keys are encrypted and never shown again.</p><div className="form-actions"><Button secondary type="button" onClick={() => { setOpen(false); setSecret('') }}>Cancel</Button><Button type="submit">Save key</Button></div></form></Modal><ConfirmationDialog open={deactivateId !== null} title="Deactivate provider key" message="Deactivate this provider key? New runs cannot use it." onConfirm={deactivate} onCancel={() => setDeactivateId(null)} /></>
}
