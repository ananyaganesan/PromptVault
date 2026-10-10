import { createContext, useContext, useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { ErrorState } from '../../components/ui/error-state'
import { LoadingState } from '../../components/ui/loading-state'
import { useAuth } from '../auth/auth-context'
import { workspaceService } from './workspace-data'
import { refreshLiveData, useLiveRefresh } from '../../lib/live-refresh'

const RefreshContext = createContext({ refreshing: false, error: '' })
export function WorkspaceRefreshControl() {
  const { refreshing, error } = useContext(RefreshContext)
  return <div className="data-refresh-toolbar">
    <button className="button secondary" onClick={refreshLiveData} disabled={refreshing}>
      {refreshing ? 'Refreshing…' : 'Refresh data'}
    </button>
    {error && <span role="alert">{error} <button className="text-button" onClick={refreshLiveData}>Try again</button></span>}
  </div>
}

export function WorkspaceBoundary() {
  const { user } = useAuth()
  const userId = user?.id
  const refresh = useLiveRefresh()
  const [readyUser, setReadyUser] = useState<string | null>(null)
  const [settledRefresh, setSettledRefresh] = useState(-1)
  const refreshing = settledRefresh !== refresh
  const [error, setError] = useState('')

  useEffect(() => {
    if (!userId) return
    let active = true
    workspaceService.load(userId)
      .then(() => { if (active) { setError(''); setReadyUser(userId) } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load your workspace.') })
      .finally(() => { if (active) setSettledRefresh(refresh) })
    return () => { active = false }
  }, [refresh, userId])

  if (readyUser !== user?.id && error) return <ErrorState message={error} onRetry={() => {
    setError('')
    refreshLiveData()
  }} />
  if (readyUser !== user?.id) return <LoadingState label="Loading workspace…" />
  return <RefreshContext.Provider value={{ refreshing, error }}><Outlet /></RefreshContext.Provider>
}
