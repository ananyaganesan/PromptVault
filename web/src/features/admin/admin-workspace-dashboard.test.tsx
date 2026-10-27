import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AppLayout } from '../../components/layout/app-layout'
import { DashboardPage } from '../dashboard/dashboard-page'
import { deploymentService } from '../deployments/deployment-service'
import { runService } from '../runs/run-service'
import { adminService } from './admin-service'
import type { AdminUser } from '../../types/admin'

const auth = vi.hoisted(() => ({ user: { id: 'admin-id', display_name: 'Ananya', email: 'admin@example.com', role: 'admin', is_active: true, created_at: '2026-10-25T10:00:00Z' }, logout: vi.fn() }))
vi.mock('../auth/auth-context', () => ({ useAuth: () => auth }))
vi.mock('../../components/layout/project-back-button', () => ({ ProjectBackButton: () => null }))
function account(id: string, active: boolean, approved: boolean, role: AdminUser['role'] = 'user'): AdminUser {
  return { id, display_name: id, email: `${id}@example.com`, role, is_active: active, is_approved: approved, created_at: '2026-10-25T10:00:00Z', project_count: 0, last_active_at: null }
}
beforeEach(() => { auth.user.role = 'admin' })
afterEach(() => vi.restoreAllMocks())

it('gives admins an approval-focused dashboard using only their allowed APIs', async () => {
  const users = [account('Pending person', true, false), account('Active person', true, true), account('Disabled person', false, true), account('Software owner', true, true, 'super_admin')]
  vi.spyOn(adminService, 'listUsers').mockResolvedValue({ items: users, total: users.length, page: 1, page_size: 100 })
  vi.spyOn(deploymentService, 'pending').mockResolvedValue([])
  const personalDashboard = vi.spyOn(runService, 'dashboard')
  const systemDashboard = vi.spyOn(adminService, 'dashboard')
  render(<MemoryRouter><DashboardPage /></MemoryRouter>)
  expect(screen.getByRole('heading', { name: 'Admin dashboard' })).toBeInTheDocument()
  expect(await screen.findByText('Pending person')).toBeInTheDocument()
  expect(screen.queryByText('Software owner')).not.toBeInTheDocument()
  for (const label of ['USER APPROVALS', 'ACTIVE USERS', 'INACTIVE USERS']) {
    const stat = screen.getByText(label).closest<HTMLElement>('.stat')
    expect(stat).not.toBeNull()
    expect(within(stat!).getByText('1')).toBeInTheDocument()
  }
  expect(screen.getByRole('link', { name: 'Review requests' })).toHaveAttribute('href', '/admin/approvals')
  expect(personalDashboard).not.toHaveBeenCalled()
  expect(systemDashboard).not.toHaveBeenCalled()
})

it('shows admin navigation and hides software/database controls on desktop and mobile', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter><AppLayout /></MemoryRouter>)
  expect(screen.getByRole('link', { name: 'Admin dashboard' })).toHaveAttribute('href', '/dashboard')
  expect(screen.getByRole('link', { name: 'Rollback' })).toHaveAttribute('href', '/admin/rollback')
  expect(screen.getByText('ADMIN', { exact: true })).toBeInTheDocument()
  expect(screen.getByText('Admin', { exact: true })).toBeInTheDocument()
  for (const label of ['Provider keys', 'Database maintenance', 'Audit log']) expect(screen.queryByRole('link', { name: label })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Open navigation' }))
  const mobile = screen.getByRole('navigation', { name: 'Mobile navigation' })
  expect(within(mobile).getByRole('link', { name: 'Admin dashboard' })).toBeInTheDocument()
  expect(within(mobile).getByRole('link', { name: 'Users' })).toBeInTheDocument()
  expect(within(mobile).queryByRole('link', { name: 'Database maintenance' })).not.toBeInTheDocument()
})

it('keeps superadmin controls and labels separate', () => {
  auth.user.role = 'super_admin'
  render(<MemoryRouter><AppLayout /></MemoryRouter>)
  expect(screen.getByText('SUPER ADMIN', { exact: true })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Database maintenance' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Admin dashboard' })).not.toBeInTheDocument()
})

it('offers a retry when admin task loading fails', async () => {
  vi.spyOn(adminService, 'listUsers').mockRejectedValueOnce(new Error('Could not load user approvals.')).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 })
  vi.spyOn(deploymentService, 'pending').mockResolvedValue([])
  render(<MemoryRouter><DashboardPage /></MemoryRouter>)
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load user approvals.')
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await waitFor(() => expect(screen.getByText('No users are waiting for approval.')).toBeInTheDocument())
})
