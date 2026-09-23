import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './auth-context'

export function RequireAuth() {
  const { user, restoring } = useAuth()
  const location = useLocation()
  if (restoring) return <p role="status">Restoring session…</p>
  return user ? <Outlet /> : <Navigate to="/login" state={{ from: location.pathname }} replace />
}
