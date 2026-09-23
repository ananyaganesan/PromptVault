import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PlaygroundPage } from './playground-page'
import { runService } from '../runs/run-service'
import { AuthProvider } from '../auth/auth-context'

function setup() { return render(<AuthProvider mode="demo"><MemoryRouter><PlaygroundPage /></MemoryRouter></AuthProvider>) }

describe('Playground run states', () => {
  it('requires the version input before execution', async () => {
    const user = userEvent.setup(); setup()
    await user.click(screen.getByRole('button', { name: 'Run prompt' }))
    expect(screen.getByRole('alert')).toHaveTextContent('customer_message is required.')
  })

  it('records a successful run and updates spend', async () => {
    const user = userEvent.setup(); setup()
    const before = Number((await runService.dashboard()).monthly_spend)
    await user.type(screen.getByRole('textbox', { name: /customer_message/ }), 'Please check my order')
    await user.click(screen.getByRole('button', { name: 'Run prompt' }))
    expect(await screen.findByText('View run details →')).toBeInTheDocument()
    expect(Number((await runService.dashboard()).monthly_spend)).toBeGreaterThan(before)
  })

  it('shows provider failure without charging', async () => {
    const user = userEvent.setup(); setup()
    const before = Number((await runService.dashboard()).monthly_spend)
    await user.type(screen.getByRole('textbox', { name: /customer_message/ }), 'Please check my order')
    await user.selectOptions(screen.getByLabelText('Test scenario'), 'failed')
    await user.click(screen.getByRole('button', { name: 'Run prompt' }))
    expect(await screen.findByText('Run failed')).toBeInTheDocument()
    expect(Number((await runService.dashboard()).monthly_spend)).toBe(before)
  })

  it('shows budget limit without charging', async () => {
    const user = userEvent.setup(); setup()
    const before = Number((await runService.dashboard()).monthly_spend)
    await user.type(screen.getByRole('textbox', { name: /customer_message/ }), 'Please check my order')
    await user.selectOptions(screen.getByLabelText('Test scenario'), 'blocked')
    await user.click(screen.getByRole('button', { name: 'Run prompt' }))
    expect(await screen.findByText('Budget limit reached')).toBeInTheDocument()
    expect(Number((await runService.dashboard()).monthly_spend)).toBe(before)
  })
})
