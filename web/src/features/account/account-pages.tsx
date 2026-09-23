import { PageHeader } from '../../components/layout/page-header'
import { Status } from '../../components/ui/prototype'
import { useAuth } from '../auth/auth-context'

export function ProfilePage() { const { user } = useAuth(); if (!user) return null; const initials = user.display_name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase(); return <><PageHeader title="Profile" description="Manage your identity and workspace access."/><section className="profile-card panel"><div className="profile-hero"><span className="large-avatar">{initials}</span><div><h2>{user.display_name}</h2><p>{user.email}</p></div><Status tone={user.is_active ? 'success' : 'warning'}>{user.is_active ? 'Active' : 'Inactive'}</Status></div><div className="profile-grid"><div><span>ROLE</span><b>{user.role === 'super_admin' ? 'Super Admin' : 'User'}</b></div><div><span>MEMBER SINCE</span><b>{new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric' }).format(new Date(user.created_at))}</b></div><div><span>WORKSPACE</span><b>PromptVault</b></div></div></section></> }
export { ApiTokensPage } from './api-tokens-page'
