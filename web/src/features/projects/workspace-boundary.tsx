import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { ErrorState } from '../../components/ui/error-state'
import { LoadingState } from '../../components/ui/loading-state'
import { useAuth } from '../auth/auth-context'
import { workspaceService } from './workspace-data'
import { refreshLiveData, useLiveRefresh } from '../../lib/live-refresh'

export function WorkspaceBoundary() {
  const { user } = useAuth()
  const userId = user?.id
  const refresh = useLiveRefresh()
  const [readyUser, setReadyUser] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!userId) return
    let active = true
    workspaceService.load(userId)
      .then(() => { if (active) { setError(''); setReadyUser(userId) } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load your workspace.') })
    return () => { active = false }
  }, [refresh, userId])

  if (readyUser !== user?.id && error) return <ErrorState message={error} onRetry={() => {
    setError('')
    refreshLiveData()
  }} />
  if (readyUser !== user?.id) return <LoadingState label="Loading workspace…" />
  return <Outlet />
}
