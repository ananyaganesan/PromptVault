import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/auth-context'

export function AdminOnly({ superOnly = true }: { superOnly?: boolean }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'super_admin' && (superOnly || user.role !== 'admin')) return <Navigate to="/403" replace />
  return <Outlet />
}
