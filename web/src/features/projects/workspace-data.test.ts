import { beforeEach, describe, expect, it, vi } from 'vitest'
import { projectStore, promptStore, versionStore } from './workspace-data'

function json(payload: unknown) {
  return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('workspaceService', () => {
  beforeEach(() => {
    projectStore.splice(0)
    promptStore.splice(0)
    for (const key of Object.keys(versionStore)) delete versionStore[key]
    vi.unstubAllGlobals()
  })

  it('loads and adapts the permitted project, prompt, and immutable versions from the API', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ items: [{ id: 'project-1', name: 'Live Project', key: 'live-project', description: null, owner: { id: 'user-1', display_name: 'Owner' }, member_count: 1, prompt_count: 1, created_at: '2026-09-27T00:00:00Z', updated_at: '2026-09-27T00:00:00Z' }], page: 1, page_size: 100, total: 1 }))
      .mockResolvedValueOnce(json({ items: [{ id: 'prompt-1', project_id: 'project-1', key: 'live-prompt', name: 'Live Prompt', description: null, latest_version_number: 1, created_at: '2026-09-27T00:00:00Z', updated_at: '2026-09-27T00:00:00Z' }], page: 1, page_size: 100, total: 1 }))
      .mockResolvedValueOnce(json({ items: [{ id: 'version-1', prompt_id: 'prompt-1', version_number: 1, parent_version_id: null, template_body: 'Hello {{name}}', variables: ['name'], model_config: { provider: 'mock', model: 'deterministic', temperature: 0, max_output_tokens: 128 }, commit_message: 'Initial', created_by: { id: 'user-1', display_name: 'Owner' }, created_at: '2026-09-27T00:00:00Z' }], page: 1, page_size: 100, total: 1 }))
    vi.stubGlobal('fetch', fetcher)

    const module = await import('./workspace-data')
    expect('workspaceService' in module).toBe(true)
    if (!('workspaceService' in module)) return
    const service = module.workspaceService as { load: (userId: string) => Promise<void> }
    await service.load('user-1')

    expect(projectStore).toEqual([expect.objectContaining({ id: 'project-1', owner_id: 'user-1', is_owner: true })])
    expect(promptStore).toEqual([expect.objectContaining({ id: 'prompt-1', active_environment: 'draft' })])
    expect(versionStore['prompt-1']).toEqual([expect.objectContaining({ id: 'version-1', template: 'Hello {{name}}', created_by_name: 'Owner' })])
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      'http://localhost:8000/api/v1/projects?page=1&page_size=100',
      'http://localhost:8000/api/v1/projects/project-1/prompts?page=1&page_size=100',
      'http://localhost:8000/api/v1/prompts/prompt-1/versions?page=1&page_size=100',
    ])
  })
})
