import { useState, type ReactNode } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Logo } from './brand'
import { ProjectBackButton } from './project-back-button'
import { useAuth } from '../../features/auth/auth-context'

const workspace = [['Dashboard', '/dashboard'], ['Projects', '/projects'], ['Playground', '/playground'], ['Deployments', '/deployments'], ['API tokens', '/api-tokens'], ['Profile', '/profile']]
const admin = [['Approvals', '/admin/approvals'], ['Rollback', '/admin/rollback'], ['Users', '/admin/users'], ['Provider keys', '/admin/provider-keys'], ['Audit log', '/admin/audit'], ['Database maintenance', '/admin/maintenance']]

function NavIcon({ label }: { label: string }) {
  const icons: Record<string, ReactNode> = { Dashboard: <><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></>, Projects: <path d="M3 6.5A2.5 2.5 0 0 1 5.5 4H10l2 2h6.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5Z"/>, Playground: <path d="M9 3v6.5L4.7 17A3 3 0 0 0 7.3 21h9.4a3 3 0 0 0 2.6-4L15 9.5V3M8 3h8M8 15h8"/>, Runs: <><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5M12 7v5l3 2"/></>, Costs: <><circle cx="12" cy="12" r="9"/><path d="M15 8.5c-.7-.5-1.7-.8-3-.8-1.8 0-3 .9-3 2.2 0 3.2 6 1.4 6 4.3 0 1.3-1.2 2.2-3 2.2-1.2 0-2.4-.3-3.2-1M12 6v12"/></>, Deployments: <><path d="m14 4 6 6-5 1-4 4-1-1 4-4 1-5Z"/><path d="M10 14 5 19M5 14l-1 5 5-1"/></>, 'API tokens': <><circle cx="8" cy="15" r="3"/><path d="m10.2 12.8 7.3-7.3 2 2-1.7 1.7 1.5 1.5-2 2-1.5-1.5-3.4 3.4"/></>, Profile: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>, Approvals: <><path d="M7 3h10l3 3v15H4V6l3-3Z"/><path d="m8 13 2.5 2.5L16 10"/></>, Users: <><circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0M16 4.5a3 3 0 0 1 0 5.7M17 14a5 5 0 0 1 4 4.9"/></>, 'Provider keys': <><circle cx="8" cy="15" r="3"/><path d="m10.2 12.8 7.3-7.3 2 2-1.7 1.7 1.5 1.5-2 2-1.5-1.5-3.4 3.4"/></> }
  const governanceIcons: Record<string, ReactNode> = { Rollback: <><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></>, 'Admin runs': <><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5M12 7v5l3 2"/></>, 'Audit log': <><path d="M6 3h12v18H6z"/><path d="M9 8h6M9 12h6M9 16h4"/></> }
  return <svg className="side-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icons[label] ?? governanceIcons[label] ?? icons.Dashboard}</svg>
}

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false); const [mobileOpen, setMobileOpen] = useState(false); const [sidebarTooltip, setSidebarTooltip] = useState<{ label: string; left: number; top: number } | null>(null); const navigate = useNavigate(); const { user, logout } = useAuth(); const name = user?.display_name ?? 'PromptVault User'; const canAdminister = user?.role === 'super_admin' || user?.role === 'admin'; const workspaceLinks = user?.role === 'admin' ? workspace.map(([label, to]) => [to === '/dashboard' ? 'Admin dashboard' : label, to]) : workspace; const adminHeading = user?.role === 'admin' ? 'ADMIN' : 'SUPER ADMIN'; const adminLinks = user?.role === 'admin' ? admin.filter(([, to]) => ['/admin/users', '/admin/approvals', '/admin/rollback'].includes(to)) : admin
  const showSidebarTooltip = (label: string, target: HTMLElement) => {
    if (!collapsed) return
    const bounds = target.getBoundingClientRect()
    setSidebarTooltip({ label, left: bounds.right + 10, top: bounds.top + bounds.height / 2 })
  }
  const links = (items: string[][]) => items.map(([label, to], index) => <span key={to}><NavLink to={to} end={to === '/admin'} className={({ isActive }) => isActive ? 'side-link active' : 'side-link'} aria-label={label} onMouseEnter={(event) => showSidebarTooltip(label, event.currentTarget)} onMouseLeave={() => setSidebarTooltip(null)} onFocus={(event) => showSidebarTooltip(label, event.currentTarget)} onBlur={() => setSidebarTooltip(null)}><NavIcon label={label}/><span className="side-link-label">{label}</span></NavLink>{items === workspaceLinks && index === 2 && <span className="side-separator" />}</span>)
  const initials = name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase()
  return <div className={collapsed ? 'app-shell sidebar-is-collapsed' : 'app-shell'}>
    <aside className={collapsed ? 'sidebar collapsed' : 'sidebar'}>
      <Logo />
      <div className="side-label">WORKSPACE</div>{links(workspaceLinks)}
      {canAdminister && <><div className="side-label admin-label">{adminHeading}</div>{links(adminLinks)}</>}
      <div className="sidebar-bottom"><button className="mini-user" aria-label="Open profile" onClick={() => navigate('/profile')}><span className="avatar">{initials}</span><div><b>{name}</b><small>{user?.role === 'super_admin' ? 'Super Admin' : user?.role === 'admin' ? 'Admin' : 'User'}</small></div></button><button className="signout" onClick={() => { logout(); navigate('/login') }}>Sign out</button></div>
    </aside>
    <button className="sidebar-toggle" onClick={() => { setSidebarTooltip(null); setCollapsed(!collapsed) }} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed}>{collapsed ? '›' : '‹'}</button>
    <div className="app-content"><div className="mobile-bar"><Logo /><div className="mobile-actions"><button className="mobile-menu-button" aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileOpen} aria-controls="mobile-navigation" onClick={() => setMobileOpen(!mobileOpen)}>{mobileOpen ? '×' : '☰'}</button><button className="mobile-avatar" aria-label="Open profile" onClick={() => { setMobileOpen(false); navigate('/profile') }}>{initials}</button></div></div>{mobileOpen && <nav className="mobile-navigation" id="mobile-navigation" aria-label="Mobile navigation"><div className="side-label">WORKSPACE</div>{workspaceLinks.map(([label, to]) => <NavLink key={to} to={to} onClick={() => setMobileOpen(false)} className={({ isActive }) => isActive ? 'side-link active' : 'side-link'}>{label}</NavLink>)}{canAdminister && <><div className="side-label admin-label">{adminHeading}</div>{adminLinks.map(([label, to]) => <NavLink key={to} to={to} end={to === '/admin'} onClick={() => setMobileOpen(false)} className={({ isActive }) => isActive ? 'side-link active' : 'side-link'}>{label}</NavLink>)}</>}<button className="signout" onClick={() => { setMobileOpen(false); logout(); navigate('/login') }}>Sign out</button></nav>}<main id="main-content"><ProjectBackButton /><Outlet /></main></div>
    {sidebarTooltip && <div className="sidebar-page-tooltip" role="tooltip" style={{ left: sidebarTooltip.left, top: sidebarTooltip.top }}>{sidebarTooltip.label}</div>}
  </div>
}
