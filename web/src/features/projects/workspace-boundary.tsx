import { useEffect, useState, useSyncExternalStore } from 'react'
import { Outlet } from 'react-router-dom'
import { ErrorState } from '../../components/ui/error-state'
import { LoadingState } from '../../components/ui/loading-state'
import { useAuth } from '../auth/auth-context'
import { workspaceService, workspaceStore } from './workspace-data'

export function WorkspaceBoundary() {
  const { user } = useAuth()
  useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!user) return
    let active = true
    workspaceService.load(user.id)
      .then(() => { if (active) { setError(''); setReady(true) } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load your workspace.') })
    return () => { active = false }
  }, [retry, user])

  if (error) return <ErrorState message={error} onRetry={() => {
    setError('')
    setReady(false)
    setRetry((value) => value + 1)
  }} />
  if (!ready) return <LoadingState label="Loading workspace…" />
  return <Outlet />
}
