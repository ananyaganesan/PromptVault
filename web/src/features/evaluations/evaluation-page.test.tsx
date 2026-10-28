import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PromptVersion } from '../../types/versions'
import { workspaceService } from '../projects/workspace-data'
import { defaults, evaluationApi, type Evaluation, type Setup } from './evaluation-api'
import { EvaluationPage } from './evaluation-page'

const versions: PromptVersion[] = [2, 1].map((n) => ({
  id: `version-${n}`, prompt_id: 'prompt-1', version_number: n, parent_version_id: n === 2 ? 'version-1' : null,
  template: 'Answer {{topic}}', variables: [{ name: 'topic', required: true }],
  model_config: { provider: 'gemini', model: 'gemini-3.5-flash-lite', temperature: 0, max_output_tokens: 100 },
  commit_message: `Version ${n}`, created_by: 'owner', created_by_name: 'Owner', created_at: '2026-10-25T10:00:00Z',
}))
vi.mock('../projects/workspace-data', () => ({
  promptFor: () => ({ id: 'prompt-1', name: 'Support answer' }),
  versionsFor: () => versions,
  workspaceStore: { subscribe: () => () => {}, getSnapshot: () => 1 },
  workspaceService: { createVersion: vi.fn() },
}))
vi.mock('../../lib/live-refresh', () => ({ refreshLiveData: vi.fn() }))
const configuration: Setup = {
  version_ids: ['version-2', 'version-1'], goal: 'Answer clearly and include useful next steps.', preset: 'customer_support',
  cases: [{ name: 'Typical request', variables: { topic: 'Delivery issue' }, reference: '' }],
  weights: { ...defaults }, requirements: { valid_json: false, required_fields: [], max_words: null },
}
function completed(): Evaluation {
  return {
    id: 'evaluation-1', prompt_id: 'prompt-1', created_by: 'owner', configuration,
    version_snapshots: versions.map((v) => ({ ...v, template_body: v.template, variables: ['topic'], created_by: { id: 'owner', display_name: 'Owner' } })),
    status: 'completed', winner_version_id: 'version-2', error: null,
    created_at: '2026-10-25T10:00:00Z', updated_at: '2026-10-25T10:01:00Z', usage: { evaluator_calls: 2, evaluator_prompt_tokens: 50 },
    recommendation: 'Highest quality score among eligible versions.',
    ranking: [{ version_id: 'version-2', score: 90, eligible: true, passed_cases: 1, total_cases: 1, reason: 'Meets every mandatory check.' }],
    results: versions.map((v) => ({ version_id: v.id, case_index: 0, run_id: `run-${v.id}`, output: 'A useful answer.', checks: [],
      scores: { clarity: { score: 4.5, reason: 'Easy to read.', evidence: 'useful answer' } },
      weighted_score: v.version_number === 2 ? 90 : 70, summary: 'Includes next steps.', error: null,
      prompt_tokens: 10, completion_tokens: 20, latency_ms: 100,
    })),
  }
}
function renderPage(path = '/prompts/prompt-1/evaluate') {
  render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/prompts/:promptId/evaluate" element={<EvaluationPage />} /></Routes></MemoryRouter>)
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.mocked(workspaceService.createVersion).mockReset()
  vi.spyOn(evaluationApi, 'setup').mockResolvedValue({ configuration: null })
  vi.spyOn(evaluationApi, 'history').mockResolvedValue([])
  vi.spyOn(evaluationApi, 'get').mockResolvedValue(completed())
})

describe('Prompt version evaluations', () => {
  it('shows a plain-language workflow without developer format controls', async () => {
    renderPage()
    await screen.findByRole('button', { name: 'Compare versions' })
    expect(screen.getByText('1. Choose versions and your goal')).toBeInTheDocument()
    expect(screen.getByText('2. Try real examples')).toBeInTheDocument()
    expect(screen.getByText('3. Choose your answer preferences')).toBeInTheDocument()
    expect(screen.queryByText(/JSON|temperature|output limit|top-level/i)).not.toBeInTheDocument()
    expect(screen.getAllByRole('checkbox')).toHaveLength(2)
    expect(screen.getByText('Compare meaning with vector embeddings')).toBeInTheDocument()
  })

  it('keeps saved examples compact and preserves editing and removal', async () => {
    const user = userEvent.setup()
    vi.mocked(evaluationApi.setup).mockResolvedValue({ configuration: {
      ...configuration, cases: [configuration.cases[0], { name: 'Outage', variables: { topic: 'Checkout is unavailable.' }, reference: 'Escalate the incident.' }],
    } })
    const save = vi.spyOn(evaluationApi, 'saveSetup').mockResolvedValue({})
    renderPage()
    const input = await screen.findByLabelText('topic · example 1')
    expect(input).not.toBeVisible()
    await user.click(screen.getByText('Typical request'))
    expect(input).toBeVisible()
    await user.clear(input)
    await user.type(input, 'Updated delivery issue')
    await user.click(screen.getByRole('button', { name: 'Save setup' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith('prompt-1', expect.objectContaining({
      cases: [expect.objectContaining({ variables: { topic: 'Updated delivery issue' } }), expect.objectContaining({ reference: 'Escalate the incident.' })],
    })))
    await user.click(screen.getByRole('button', { name: 'Remove example 1' }))
    expect(screen.getByLabelText('topic · example 1')).toHaveValue('Checkout is unavailable.')
    expect(screen.getByRole('button', { name: 'Suggest examples for me' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Use previous examples' })).toBeVisible()
  })

  it('shows saved embedding similarity and the combined score', async () => {
    const item = completed()
    item.configuration = { ...item.configuration, use_embeddings: true }
    item.results[0].embedding = { model: 'gemini-embedding-2', cosine_similarity: 0.8, quality_score: 90, output_vector: [1, 0], reference_vector: [0.8, 0.6] }
    vi.mocked(evaluationApi.get).mockResolvedValue(item)
    renderPage('/prompts/prompt-1/evaluate?evaluation=evaluation-1')
    expect(await screen.findByText(/Cosine similarity: 0.8000/)).toBeInTheDocument()
    expect(screen.getByText('No trusted answer: quality-only score.')).toBeInTheDocument()
  })

  it('preserves saved format checks when a user changes the answer length', async () => {
    const user = userEvent.setup()
    const requirements = { valid_json: true, required_fields: ['category', 'priority'], max_words: 100 }
    vi.mocked(evaluationApi.setup).mockResolvedValue({ configuration: { ...configuration, requirements } })
    const save = vi.spyOn(evaluationApi, 'saveSetup').mockResolvedValue({})
    renderPage()
    const length = await screen.findByLabelText('Answer length limit (words, optional)')
    expect(screen.getByText(/and include: category, priority/)).toBeInTheDocument()
    await user.clear(length)
    await user.type(length, '80')
    await user.click(screen.getByRole('button', { name: 'Save setup' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith('prompt-1', expect.objectContaining({ requirements: { ...requirements, max_words: 80 } })))
  })

  it('describes format failures in the saved comparison without exposing JSON rules', async () => {
    const item = completed()
    item.results[0].checks = [
      { name: 'Valid JSON', passed: false, detail: 'Output must be JSON without Markdown fences.' },
      { name: 'Field: priority', passed: false, detail: 'Required top-level JSON field.' },
    ]
    vi.mocked(evaluationApi.get).mockResolvedValue(item)
    renderPage('/prompts/prompt-1/evaluate?evaluation=evaluation-1')
    expect(await screen.findByText(/Answer does not follow the expected format/)).toBeInTheDocument()
    expect(screen.getByText(/Missing: priority/)).toBeInTheDocument()
    expect(screen.queryByText(/Markdown fences|top-level JSON/)).not.toBeInTheDocument()
    expect(screen.getByText('Delivery issue')).toBeInTheDocument()
  })

  it('shows saved example inputs and reference after opening a history run', async () => {
    const user = userEvent.setup()
    const item = completed()
    item.configuration = { ...configuration, cases: [{ ...configuration.cases[0], reference: 'Offer a practical delivery update.' }] }
    vi.mocked(evaluationApi.get).mockResolvedValue(item)
    vi.mocked(evaluationApi.history).mockResolvedValue([{ id: item.id, status: 'completed', created_at: item.created_at, recommendation: item.recommendation, winner_version_id: item.winner_version_id, error: null, completed_cases: 2, total_cases: 2 }])
    renderPage()
    await user.click(await screen.findByRole('button', { name: item.recommendation }))
    const example = await screen.findByRole('group', { name: 'Saved example: Typical request' })
    expect(within(example).getByText('Delivery issue')).toBeVisible()
    expect(within(example).getByText('Offer a practical delivery update.')).toBeVisible()
  })

  it('reviews Gemini suggestions before running and sends the reviewed setup', async () => {
    const user = userEvent.setup()
    const suggest = vi.spyOn(evaluationApi, 'suggest').mockResolvedValue({
      cases: configuration.cases, weights: defaults, requirements: configuration.requirements, notes: 'Includes a typical customer request.',
    })
    const start = vi.spyOn(evaluationApi, 'start').mockResolvedValue(completed())
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Suggest examples for me' }))
    expect(suggest).toHaveBeenCalledOnce()
    expect(start).not.toHaveBeenCalled()
    const review = await screen.findByRole('region', { name: 'Suggested setup' })
    expect(within(review).getByText('Includes a typical customer request.')).toBeInTheDocument()
    await user.click(within(review).getByRole('button', { name: 'Use these examples and preferences' }))
    expect(screen.getByLabelText('Example name 1')).toHaveValue('Typical request')
    expect(screen.getByLabelText('topic · example 1')).toHaveValue('Delivery issue')
    await user.click(screen.getByRole('button', { name: 'Compare versions' }))
    await waitFor(() => expect(start).toHaveBeenCalledWith('prompt-1', expect.any(String), expect.objectContaining({ cases: configuration.cases })))
    expect(await screen.findByText('Recommended: v2')).toBeInTheDocument()
    expect(screen.getByText('No trusted answer was provided, so factual accuracy has not been verified.')).toBeInTheDocument()
  })

  it('requires valid weight totals before making model calls', async () => {
    const user = userEvent.setup()
    const start = vi.spyOn(evaluationApi, 'start')
    renderPage()
    await screen.findByRole('button', { name: 'Compare versions' })
    const weight = screen.getByLabelText('Clarity (%)')
    await user.clear(weight); await user.type(weight, '90')
    await user.click(screen.getByRole('button', { name: 'Compare versions' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('totaling 100%')
    expect(start).not.toHaveBeenCalled()
  })

  it('keeps improvement drafts editable and saves only on explicit request', async () => {
    const user = userEvent.setup()
    vi.spyOn(evaluationApi, 'improve').mockResolvedValue({ template: 'Improve {{topic}} with clear next steps.', explanation: 'Adds explicit structure.' })
    vi.mocked(workspaceService.createVersion).mockResolvedValue({ ...versions[0], id: 'version-3', version_number: 3 })
    renderPage('/prompts/prompt-1/evaluate?evaluation=evaluation-1')
    await user.click(await screen.findByRole('button', { name: 'Suggest an improvement' }))
    const draft = await screen.findByLabelText('Review and edit the suggested template')
    expect(draft).toHaveValue('Improve {{topic}} with clear next steps.')
    expect(workspaceService.createVersion).not.toHaveBeenCalled()
    await user.type(draft, ' Be concise.')
    await user.click(screen.getByRole('button', { name: 'Save as a new version' }))
    await waitFor(() => expect(workspaceService.createVersion).toHaveBeenCalledWith('prompt-1', expect.objectContaining({ parent_version_id: 'version-2', template: 'Improve {{topic}} with clear next steps. Be concise.' })))
    expect(await screen.findByText(/Saved v3/)).toBeInTheDocument()
  })

  it('displays incomplete comparisons without inventing a recommendation', async () => {
    const item = completed()
    item.status = 'failed'; item.winner_version_id = null; item.ranking = []; item.recommendation = ''; item.error = 'Gemini quota reached.'
    vi.spyOn(evaluationApi, 'get').mockResolvedValue(item)
    renderPage('/prompts/prompt-1/evaluate?evaluation=evaluation-1')
    expect(await screen.findByText('No winner selected')).toBeInTheDocument()
    expect(screen.getByText('Gemini quota reached.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Suggest an improvement' })).not.toBeInTheDocument()
  })
})
