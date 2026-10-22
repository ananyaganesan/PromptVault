import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { workspaceService, versionStore } from '../projects/workspace-data'
import { PlaygroundPage } from './playground-page'
import { runService } from '../runs/run-service'
import { AuthProvider } from '../auth/auth-context'

const catalog = vi.hoisted(() => ({
  items: [{ provider: 'groq', credential_available: true, quota_note: 'Free-tier account quotas apply.', models: [{ id: 'qwen/qwen3.8-27b', label: 'Qwen 3.8 27B', max_output_tokens: 4096, max_input_characters: 12000, free_access: true, available: true, unavailable_reason: null as string | null }] }],
  timeout_seconds: 30, max_concurrent_runs_per_user: 4, credential_ownership: 'shared_project',
}))
vi.mock('./provider-models', () => ({ useProviderModels: () => ({ data: catalog, error: '', refresh: vi.fn() }) }))
beforeEach(() => { catalog.items[0].models[0].unavailable_reason = null; vi.restoreAllMocks() })

function setup() { return render(<AuthProvider><MemoryRouter><PlaygroundPage /></MemoryRouter></AuthProvider>) }

describe('Playground run states', () => {
  it('loads editable sample values for a demo run', async () => {
    const user = userEvent.setup(); setup()
    await user.click(screen.getByRole('button', { name: 'Load demo inputs' }))
    expect(screen.getByRole('textbox', { name: /customer_message/ })).toHaveValue('My order is delayed and tracking has not changed since yesterday. Can you tell me what happens next?')
    expect(screen.getByRole('textbox', { name: /order_context/ })).toHaveValue('Order PV-2026-1042 is in transit at the Bengaluru regional sorting center. Estimated delivery is October 17, 2026.')
  })

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
    expect(await screen.findByText('completed')).toBeInTheDocument()
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


describe('Playground provider configuration', () => {
  it('saves a new immutable version before allowing a changed model to run', async () => {
    const user = userEvent.setup(); setup()
    const parent = Object.values(versionStore).flat()[0]
    const initialConfig = { ...parent.model_config }
    const save = vi.spyOn(workspaceService, 'createVersion').mockImplementationOnce(async (promptId, request) => {
      const version = { ...parent, id: 'configured-version', version_number: parent.version_number + 1, parent_version_id: parent.id, model_config: request.model_config }
      versionStore[promptId].unshift(version)
      return version
    })
    await user.selectOptions(screen.getByLabelText('LLM provider'), 'groq')
    expect(screen.getByRole('button', { name: 'Run prompt' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Save configuration' }))
    expect(save).toHaveBeenCalledWith(parent.prompt_id, expect.objectContaining({
      parent_version_id: parent.id, model_config: expect.objectContaining({ provider: 'groq', model: 'qwen/qwen3.8-27b' }),
    }))
    expect(parent.model_config).toEqual(initialConfig)
    expect(screen.getByRole('button', { name: 'Run prompt' })).toBeEnabled()
    versionStore[parent.prompt_id] = versionStore[parent.prompt_id].filter((version) => version.id !== 'configured-version')
  })

  it('blocks execution and saving when the project key is missing', async () => {
    catalog.items[0].models[0].unavailable_reason = 'Provider key is not configured'
    const user = userEvent.setup(); setup()
    await user.selectOptions(screen.getByLabelText('LLM provider'), 'groq')
    expect(screen.getByText('Provider key is not configured')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Run prompt' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save configuration' })).toBeDisabled()
  })
})
