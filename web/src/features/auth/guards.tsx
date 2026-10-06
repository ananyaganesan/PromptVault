import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './auth-context'
import { LoadingState } from '../../components/ui/loading-state'

export function RequireAuth() {
  const { user, restoring } = useAuth()
  const location = useLocation()
  if (restoring) return <LoadingState label="Restoring session…" />
  return user ? <Outlet /> : <Navigate to="/login" state={{ from: `${location.pathname}${location.search}${location.hash}` }} replace />
}
