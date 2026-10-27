import { useEffect, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/layout/page-header'
import { Stat, Status } from '../../components/ui/prototype'
import { LoadingState } from '../../components/ui/loading-state'
import { ErrorState } from '../../components/ui/error-state'
import { useLiveRefresh } from '../../lib/live-refresh'
import { useAuth } from '../auth/auth-context'
import { deploymentService, deploymentStore } from '../deployments/deployment-service'
import { adminStore, listAllAdminUsers } from './admin-service'
import type { AdminUser } from '../../types/admin'
import type { Deployment } from '../../types/deployments'

export function AdminWorkspaceDashboard() {
  const { user } = useAuth()
  const refresh = useLiveRefresh()
  const usersRevision = useSyncExternalStore(adminStore.subscribe, adminStore.getSnapshot)
  const deploymentsRevision = useSyncExternalStore(deploymentStore.subscribe, deploymentStore.getSnapshot)
  const [snapshot, setSnapshot] = useState<{ users: AdminUser[]; deployments: Deployment[] } | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    Promise.all([listAllAdminUsers(user), deploymentService.pending(user)])
      .then(([users, deployments]) => { if (active) { setSnapshot({ users, deployments }); setError('') } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load admin tasks.') })
    return () => { active = false }
  }, [user, refresh, usersRevision, deploymentsRevision, retry])
  const regularUsers = snapshot?.users.filter((account) => account.role === 'user') ?? []
  const pending = regularUsers.filter((account) => account.is_active && account.is_approved === false)
  return <div className="admin-workspace-dashboard">
    <PageHeader title="Admin dashboard" eyebrow="ADMIN" description={`Welcome, ${user?.display_name.split(' ')[0] ?? 'Admin'}. Review user access, deployment requests, and rollbacks.`} action={<Link className="button" to="/admin/users">Review users</Link>} />
    {error ? <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} /> : !snapshot ? <LoadingState label="Loading admin dashboard…" /> : <>
      <div className="stats-grid">
        <Stat label="USER APPROVALS" value={String(pending.length)} note="Accounts awaiting approval" />
        <Stat label="DEPLOYMENT APPROVALS" value={String(snapshot.deployments.length)} note="Requests awaiting review" />
        <Stat label="ACTIVE USERS" value={String(regularUsers.filter((account) => account.is_active && account.is_approved !== false).length)} note="Approved regular users" />
        <Stat label="INACTIVE USERS" value={String(regularUsers.filter((account) => !account.is_active).length)} note="Accounts with access disabled" />
      </div>
      <div className="dashboard-grid admin-approval-grid">
        <section className="panel admin-approval-panel"><div className="panel-head"><div><h2>User approvals</h2><p>Approve access after the account verifies its email.</p></div><Link className="button secondary" to="/admin/users">Manage users</Link></div>
          {pending.length ? pending.slice(0, 5).map((account) => <div className="health-row" key={account.id}><div><b>{account.display_name}</b><small className="user-email">{account.email}</small></div><Status tone="warning">Awaiting approval</Status></div>) : <p className="empty-evidence">No users are waiting for approval.</p>}
        </section>
        <section className="panel admin-approval-panel"><div className="panel-head"><div><h2>Deployment approvals</h2><p>Review prompt versions before activation.</p></div><Link className="button secondary" to="/admin/approvals">Review requests</Link></div>
          {snapshot.deployments.length ? snapshot.deployments.slice(0, 5).map((deployment) => <Link className="health-row" to={`/admin/approvals/${deployment.id}`} key={deployment.id}><span>{deployment.prompt_key} · v{deployment.version_number}</span><Status tone="warning">Pending review</Status></Link>) : <p className="empty-evidence">No deployment requests are waiting for review.</p>}
          <div className="admin-approval-footer"><Link to="/admin/rollback">Roll back a deployment</Link></div>
        </section>
      </div>
    </>}
  </div>
}
