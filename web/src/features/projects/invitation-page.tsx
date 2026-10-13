import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/auth-context'
import { Button } from '../../components/ui/prototype'
import { projectsApi } from './api'

export function ProjectInvitationPage() {
  const location = useLocation()
  const { user, logout } = useAuth()
  const token = new URLSearchParams(location.hash.slice(1)).get('token') ?? ''
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [projectId, setProjectId] = useState<string | null>(null)
  async function accept() {
    if (!token || busy || projectId) return
    setBusy(true)
    setError('')
    try {
      const project = await projectsApi.acceptInvitation(token)
      setProjectId(project.id)
      // Remove the consumed secret from this browser history entry.
      window.history.replaceState(window.history.state, '', location.pathname)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not accept invitation.') }
    finally { setBusy(false) }
  }
  return <main className="auth-main"><section className="auth-card">
    <h1>Project invitation</h1>
    {projectId ? <><p role="status">Invitation accepted. You now have project access.</p><Link to={`/projects/${projectId}`}>Open project</Link></> : <>
      <p>Signed in as {user?.email}. Accept using the account that received the invitation email.</p>
      <p>You will get access only after accepting this invitation.</p>
      {!token && <p role="alert">Open the invitation link from your email.</p>}
      {error && <p role="alert">{error}</p>}
      <Button type="button" disabled={!token || busy} onClick={accept}>{busy ? 'Accepting…' : 'Accept invitation'}</Button>
      <Button type="button" disabled={busy} onClick={logout}>Sign in with another account</Button>
      <p><Link to="/projects">Go to my projects</Link></p>
    </>}
  </section></main>
}
