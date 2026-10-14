import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ProjectDetailPage, ProjectsPage } from './project-pages'
import { projectsApi } from './api'

const auth = vi.hoisted(() => ({
  user: {
    id: 'user-1',
    email: 'user@example.com',
    display_name: 'Regular User',
    role: 'user' as 'user' | 'super_admin',
    is_active: true,
    created_at: '2026-10-14T00:00:00Z',
  },
}))

vi.mock('../auth/auth-context', () => ({ useAuth: () => auth }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  auth.user.role = 'user'
})

describe('project creation policy', () => {
  it('does not offer project creation to regular users', () => {
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    expect(screen.queryByRole('button', { name: 'New project' })).not.toBeInTheDocument()
  })

  it('offers project creation to administrators', () => {
    auth.user.role = 'super_admin'
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'New project' })).toBeInTheDocument()
  })
})

describe('project deletion policy', () => {
  async function renderSettings() {
    vi.spyOn(projectsApi, 'listInvitations').mockResolvedValue([])
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/projects/checkout']}><Routes>
      <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
    </Routes></MemoryRouter>)
    await user.click(screen.getByRole('button', { name: 'Settings' }))
  }

  it('does not offer project deletion to regular users', async () => {
    await renderSettings()
    expect(screen.queryByRole('button', { name: 'Delete project' })).not.toBeInTheDocument()
  })

  it('offers project deletion to administrators', async () => {
    auth.user.role = 'super_admin'
    await renderSettings()
    expect(screen.getByRole('button', { name: 'Delete project' })).toBeInTheDocument()
  })
})
