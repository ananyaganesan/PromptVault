import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { workspaceService, promptStore, versionStore } from '../projects/workspace-data'
import { PlaygroundPage } from './playground-page'
import { runService } from '../runs/run-service'
import { ApiClientError } from '../../lib/api/client'
import { AuthProvider } from '../auth/auth-context'

const catalog = vi.hoisted(() => ({
  items: [{ provider: 'gemini', credential_available: true, quota_note: 'Free-tier account quotas apply.', models: [{ id: 'gemini-3.5-flash-lite', label: 'Gemini Flash-Lite', max_output_tokens: 4096, max_input_characters: 12000, free_access: true, available: true, unavailable_reason: null as string | null }] }],
  timeout_seconds: 30, max_concurrent_runs_per_user: 4, credential_ownership: 'shared_project',
}))
vi.mock('./provider-models', () => ({ useProviderModels: () => ({ data: catalog, error: '', refresh: vi.fn() }) }))
beforeEach(() => {
  catalog.items[0].models[0].unavailable_reason = null; vi.restoreAllMocks()
  vi.spyOn(runService, 'create').mockResolvedValue({
    id:'run-test', project_id:'checkout', prompt_id:'checkout-reply', prompt_key:'checkout-reply',
    version_id:'checkout-v3',version_number:3,user_id:'usr_demo_user',status:'completed',
    output:'Simulated Gemini response',input_variables:{},prompt_tokens:3,completion_tokens:6,
    latency_ms:25,cost:'0',model:'gemini-3.5-flash-lite',created_at:new Date().toISOString(),error_message:null,
  })
})

function setup(entry = '/playground') { return render(<AuthProvider><MemoryRouter initialEntries={[entry]}><PlaygroundPage /></MemoryRouter></AuthProvider>) }

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

  it('displays a successful free Gemini run without charging', async () => {
    const user = userEvent.setup(); setup()
    const before = Number((await runService.dashboard()).monthly_spend)
    await user.type(screen.getByRole('textbox', { name: /customer_message/ }), 'Please check my order')
    await user.click(screen.getByRole('button', { name: 'Run prompt' }))
    expect(await screen.findByText('completed')).toBeInTheDocument()
    expect(Number((await runService.dashboard()).monthly_spend)).toBe(before)
  })

  it('shows provider failure without charging', async () => {
    const user = userEvent.setup(); setup()
    const before = Number((await runService.dashboard()).monthly_spend)
    await user.type(screen.getByRole('textbox', { name: /customer_message/ }), 'Please check my order')
    vi.mocked(runService.create).mockRejectedValueOnce(new ApiClientError(502, { code: 'provider_error', message: 'Provider unavailable', request_id: 'test' }))
    await user.click(screen.getByRole('button', { name: 'Run prompt' }))
    expect(await screen.findByText('Run failed')).toBeInTheDocument()
    expect(Number((await runService.dashboard()).monthly_spend)).toBe(before)
  })

  it('shows budget limit without charging', async () => {
    const user = userEvent.setup(); setup()
    const before = Number((await runService.dashboard()).monthly_spend)
    await user.type(screen.getByRole('textbox', { name: /customer_message/ }), 'Please check my order')
    vi.mocked(runService.create).mockRejectedValueOnce(new ApiClientError(409, { code: 'budget_exceeded', message: 'Budget reached', request_id: 'test' }))
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
    await user.clear(screen.getByLabelText('Temperature'))
    await user.type(screen.getByLabelText('Temperature'), '0.7')
    expect(screen.getByRole('button', { name: 'Run prompt' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Save configuration' }))
    expect(save).toHaveBeenCalledWith(parent.prompt_id, expect.objectContaining({
      parent_version_id: parent.id, model_config: expect.objectContaining({ provider: 'gemini', model: 'gemini-3.5-flash-lite' }),
    }))
    expect(parent.model_config).toEqual(initialConfig)
    expect(screen.getByRole('button', { name: 'Run prompt' })).toBeEnabled()
    versionStore[parent.prompt_id] = versionStore[parent.prompt_id].filter((version) => version.id !== 'configured-version')
  })

  it('blocks execution and saving when the project key is missing', async () => {
    catalog.items[0].models[0].unavailable_reason = 'Provider key is not configured'
    const user = userEvent.setup(); setup()
    await user.clear(screen.getByLabelText('Temperature'))
    await user.type(screen.getByLabelText('Temperature'), '0.7')
    expect(screen.getByText('Provider key is not configured')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Run prompt' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save configuration' })).toBeDisabled()
  })
})


describe('Playground project selection', () => {
  beforeEach(() => {
    const parent = versionStore['checkout-reply'][0]
    promptStore.push({ ...promptStore[0], id: 'growth-demo', project_id: 'growth' })
    versionStore['growth-demo'] = [{ ...parent, id: 'growth-v1', prompt_id: 'growth-demo', version_number: 1 }]
  })

  afterEach(() => {
    promptStore.splice(promptStore.findIndex((prompt) => prompt.id === 'growth-demo'), 1)
    delete versionStore['growth-demo']
  })

  it('filters versions by project even when prompt keys match', async () => {
    const user = userEvent.setup(); setup()
    const versions = screen.getByLabelText('Prompt version')
    expect(screen.getByLabelText('Project')).toHaveValue('checkout')
    expect(within(versions).queryByRole('option', { name: /v1/ })).toHaveValue('checkout-v1')
    expect(Array.from((versions as HTMLSelectElement).options).map((option) => option.value)).not.toContain('growth-v1')
    await user.selectOptions(screen.getByLabelText('Project'), 'growth')
    expect(versions).toHaveValue('growth-v1')
    expect(within(versions).getAllByRole('option')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Run prompt' })).toBeEnabled()
  })

  it('opens a version deep link with its owning project selected', () => {
    setup('/playground?version=growth-v1')
    expect(screen.getByLabelText('Project')).toHaveValue('growth')
    expect(screen.getByLabelText('Prompt version')).toHaveValue('growth-v1')
  })

  it('clears inputs, results and configuration drafts when the project changes', async () => {
    const user = userEvent.setup(); setup()
    await user.type(screen.getByRole('textbox', { name: /customer_message/ }), 'Check my parcel')
    await user.click(screen.getByRole('button', { name: 'Run prompt' }))
    expect(await screen.findByText('completed')).toBeVisible()
    await user.clear(screen.getByLabelText('Temperature'))
    await user.type(screen.getByLabelText('Temperature'), '0.7')
    expect(screen.getByRole('button', { name: 'Save configuration' })).toBeVisible()
    await user.selectOptions(screen.getByLabelText('Project'), 'growth')
    expect(screen.getByRole('textbox', { name: /customer_message/ })).toHaveValue('')
    expect(screen.queryByRole('button', { name: 'Save configuration' })).not.toBeInTheDocument()
    expect(screen.queryByText('completed')).not.toBeInTheDocument()
    expect(screen.getByLabelText('LLM provider')).toHaveValue('gemini')
  })

  it('disables version selection and execution for an empty project', async () => {
    const user = userEvent.setup(); setup()
    await user.selectOptions(screen.getByLabelText('Project'), 'support')
    expect(screen.getByLabelText('Prompt version')).toBeDisabled()
    expect(screen.getByText('No prompt versions in this project')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run prompt' })).toBeDisabled()
    expect(screen.queryByLabelText('LLM provider')).not.toBeInTheDocument()
  })
})


it('offers only Gemini and no local mock provider', () => {
  setup()
  expect(screen.queryByRole('option', { name: 'Mock (local testing)' })).not.toBeInTheDocument()
  expect(Array.from((screen.getByLabelText('LLM provider') as HTMLSelectElement).options, option => option.value)).toEqual(['gemini'])
})
