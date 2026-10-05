import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/auth-context'
import { CostsPage } from './costs-page'

describe('Costs page', () => {
  it('shows reconciled spend, budget, run count, and daily usage', async () => {
    render(<AuthProvider><MemoryRouter><CostsPage /></MemoryRouter></AuthProvider>)

    expect(await screen.findByRole('heading', { name: 'Costs' })).toBeInTheDocument()
    expect(screen.getByText('All recorded runs')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Daily cost history' })).toBeInTheDocument()
    expect(screen.getByText('MONTHLY SPEND')).toBeInTheDocument()
  })
})
