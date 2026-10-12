import { useState, type FormEvent } from 'react'
import { PageHeader } from '../../components/layout/page-header'
import { Button, Status } from '../../components/ui/prototype'
import { useAuth } from '../auth/auth-context'
import type { UserSummary } from '../../types/auth'

export function ProfilePage() {
  const { user } = useAuth()
  return user ? <ProfileContent key={user.id} user={user} /> : null
}

function ProfileContent({ user }: { user: UserSummary }) {
  const { updateProfile } = useAuth()
  const [draft, setDraft] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const name = draft ?? user.display_name
  const initials = user.display_name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase()
  async function save(event: FormEvent) {
    event.preventDefault()
    const normalized = name.trim()
    if (!normalized || normalized.length > 120) return setError('Display name must contain 1–120 characters.')
    setPending(true); setError(''); setNotice('')
    try { await updateProfile(normalized); setDraft(null); setNotice('Display name saved.') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save your display name.') }
    finally { setPending(false) }
  }
  return <><PageHeader title="Profile" description="Manage your identity and workspace access." />
    <section className="profile-card panel">
      <div className="profile-hero"><span className="large-avatar">{initials}</span><div><h2>{user.display_name}</h2><p>{user.email}</p></div><Status tone={user.is_active ? 'success' : 'warning'}>{user.is_active ? 'Active' : 'Inactive'}</Status></div>
      <form onSubmit={save}>
        <label className="field"><span>Display name</span><input value={name} maxLength={120} required disabled={pending} onChange={(event) => { setDraft(event.target.value); setError(''); setNotice('') }} /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        {notice && <p className="profile-notice" role="status">{notice}</p>}
        <Button type="submit" disabled={pending || name.trim() === user.display_name}>{pending ? 'Saving…' : 'Save display name'}</Button>
      </form>
      <div className="profile-grid"><div><span>ROLE</span><b>{user.role === 'super_admin' ? 'Super Admin' : 'User'}</b></div><div><span>MEMBER SINCE</span><b>{new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric' }).format(new Date(user.created_at))}</b></div><div><span>WORKSPACE</span><b>PromptVault</b></div></div>
    </section></>
}
export { ApiTokensPage } from './api-tokens-page'
