import { useEffect, useState, useSyncExternalStore } from 'react'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Stat, Status } from '../../components/ui/prototype'
import { runService, runStore } from '../runs/run-service'
import type { PersonalDashboard } from '../../types/runs'
import { useAuth } from '../auth/auth-context'

export function CostsPage() {
  const { user } = useAuth()
  const revision = useSyncExternalStore(runStore.subscribe, runStore.getSnapshot)
  const [data, setData] = useState<PersonalDashboard | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => { let active = true; runService.dashboard(user?.id).then((result) => { if (active) { setData(result); setError('') } }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load costs.') }); return () => { active = false } }, [revision, retry, user?.id])
  const spend = Number(data?.monthly_spend ?? 0)
  const budget = data?.monthly_budget == null ? null : Number(data.monthly_budget)
  const utilization = budget && budget > 0 ? Math.min(100, Math.round(spend / budget * 100)) : null
  const points = data?.cost_trend ?? []
  const max = Math.max(...points.map((point) => Number(point.cost)), 0.001)
  const line = points.map((point, index) => `${points.length < 2 ? 0 : index / (points.length - 1) * 600},${160 - Number(point.cost) / max * 135}`).join(' ')
  return <><PageHeader title="Costs" description="Understand your spend and monthly budget utilization." />
    {error ? <section className="panel run-outcome" role="alert"><h2>Could not load costs</h2><p>{error}</p><Button secondary onClick={() => setRetry(retry + 1)}>Try again</Button></section> : !data ? <section className="panel empty-output">Loading costs…</section> : <><div className="stats-grid"><Stat label="THIS MONTH" value={`$${spend.toFixed(4)}`} note={utilization == null ? 'No budget set' : `${utilization}% of budget`} /><Stat label="BUDGET" value={budget == null ? 'No limit' : `$${budget.toFixed(4)}`} note="Monthly limit" /><Stat label="REMAINING" value={budget == null ? '—' : `$${Math.max(0, budget - spend).toFixed(4)}`} note={utilization != null && utilization >= 90 ? 'Near limit' : 'Available this month'} /><Stat label="RUNS" value={String(data.run_count)} note="All recorded runs" /></div><section className="panel budget-panel"><div className="panel-head"><div><h2>Budget utilization</h2><p>{budget == null ? 'No monthly budget configured.' : `$${spend.toFixed(4)} used of $${budget.toFixed(4)}`}</p></div>{utilization != null && <Status tone={utilization >= 90 ? 'warning' : 'success'}>{utilization}% used</Status>}</div><div className="budget-track" role="progressbar" aria-label="Monthly budget used" aria-valuenow={utilization ?? 0} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${utilization ?? 0}%` }} /></div></section><section className="panel chart-panel large"><div className="panel-head"><div><h2>Spend over time</h2><p>Last 14 days · USD</p></div></div><div className="chart"><svg viewBox="0 0 600 180" preserveAspectRatio="none" role="img" aria-label="Cost trend over the last 14 days"><line x1="0" y1="160" x2="600" y2="160" stroke="#eceae7" /><polyline points={line} fill="none" stroke="#17171c" strokeWidth="2" /></svg></div><div className="chart-axis"><span>{points[0]?.date}</span><span>{points[points.length - 1]?.date}</span></div></section><section className="panel cost-breakdown"><div className="panel-head"><div><h2>Daily breakdown</h2><p>Completed run charges only.</p></div></div><table><thead><tr><th>DATE</th><th>RUNS</th><th>COST</th></tr></thead><tbody>{points.filter((point) => point.run_count > 0).reverse().map((point) => <tr key={point.date}><td>{point.date}</td><td>{point.run_count}</td><td>${point.cost}</td></tr>)}</tbody></table></section></>}
  </>
}
export function ProfilePage() { const { user } = useAuth(); if (!user) return null; const initials = user.display_name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase(); return <><PageHeader title="Profile" description="Manage your identity and workspace access."/><section className="profile-card panel"><div className="profile-hero"><span className="large-avatar">{initials}</span><div><h2>{user.display_name}</h2><p>{user.email}</p></div><Status tone={user.is_active ? 'success' : 'warning'}>{user.is_active ? 'Active' : 'Inactive'}</Status></div><div className="profile-grid"><div><span>ROLE</span><b>{user.role === 'super_admin' ? 'Super Admin' : 'User'}</b></div><div><span>MEMBER SINCE</span><b>{new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric' }).format(new Date(user.created_at))}</b></div><div><span>WORKSPACE</span><b>PromptVault</b></div></div></section></> }
export { ApiTokensPage } from './api-tokens-page'
