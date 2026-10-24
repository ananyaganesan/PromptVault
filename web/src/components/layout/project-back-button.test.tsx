import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ProjectBackButton } from './project-back-button'

function Location() {
  const location = useLocation()
  return <output aria-label="Current location">{location.pathname}{location.search}</output>
}

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="*" element={<><ProjectBackButton /><Location /></>} />
  </Routes></MemoryRouter>)
}

beforeEach(() => window.history.replaceState({ idx: 0 }, '', '/'))
afterEach(cleanup)

describe('workspace back navigation', () => {
  it.each([
    '/projects',
    '/playground',
    '/deployments',
    '/api-tokens',
    '/profile',
    '/admin/approvals',
    '/admin/rollback',
    '/admin/users',
    '/admin/provider-keys',
    '/admin/audit',
  ])('hides the arrow on sidebar destination %s', (path) => {
    renderAt(path)
    expect(screen.queryByRole('button', { name: 'Go back' })).not.toBeInTheDocument()
  })

  it('keeps the arrow off the dashboard sidebar destination', () => {
    renderAt('/dashboard')
    expect(screen.queryByRole('button', { name: 'Go back' })).not.toBeInTheDocument()
  })

  it.each([
    '/prompts',
    '/projects/new',
    '/projects/project-1',
    '/prompts/new?project=project-1',
    '/prompts/prompt-1',
    '/versions/version-1',
    '/versions/version-1/compare',
    '/deployments/new',
    '/deployments/deployment-1',
    '/admin/approvals/approval-1',
  ])('shows the arrow on subpage %s', (path) => {
    renderAt(path)
    expect(screen.getByRole('button', { name: 'Go back' })).toBeInTheDocument()
  })

  it.each([
    ['/projects/new', '/projects'],
    ['/prompts/new?project=project-1', '/projects/project-1'],
    ['/versions/version-1/compare', '/versions/version-1'],
    ['/deployments/new', '/deployments'],
    ['/deployments/deployment-1', '/deployments'],
    ['/admin/approvals/approval-1', '/admin/approvals'],
  ])('uses the route hierarchy when %s is opened directly', async (path, parent) => {
    const user = userEvent.setup()
    renderAt(path)
    await user.click(screen.getByRole('button', { name: 'Go back' }))
    expect(screen.getByLabelText('Current location')).toHaveTextContent(parent)
  })

  it('returns to the actual previous page when browser history is available', async () => {
    window.history.replaceState({ idx: 1 }, '', '/')
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/api-tokens', '/deployments/new']} initialIndex={1}><Routes>
      <Route path="*" element={<><ProjectBackButton /><Location /></>} />
    </Routes></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Go back' }))
    expect(screen.getByLabelText('Current location')).toHaveTextContent('/api-tokens')
  })
})
