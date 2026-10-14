import { beforeEach, describe, expect, it, vi } from 'vitest'
import { activeVersionsStore, collectPages, memberStore, projectStore, promptStore, versionEnvironments, versionStore, workspaceService } from './workspace-data'

vi.mock('../../lib/runtime', () => ({ useDemoData: false }))

function json(payload: unknown) {
  const response = payload && typeof payload === 'object' && 'items' in payload ? { page: 1, page_size: 100, ...payload } : payload
  return new Response(JSON.stringify(response), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('collectPages', () => {
  it('loads every API page instead of truncating workspace data at 100 rows', async () => {
    const first = Array.from({ length: 100 }, (_, index) => ({ id: `item-${index}` }))
    const loadPage = vi.fn()
      .mockResolvedValueOnce({ items: first, total: 101, page: 1, page_size: 100 })
      .mockResolvedValueOnce({ items: [{ id: 'item-100' }], total: 101, page: 2, page_size: 100 })
      .mockResolvedValueOnce({ items: first, total: 101, page: 1, page_size: 100 })
      .mockResolvedValueOnce({ items: [{ id: 'item-100' }], total: 101, page: 2, page_size: 100 })

    await expect(collectPages(loadPage)).resolves.toHaveLength(101)
    expect(loadPage).toHaveBeenNthCalledWith(1, 1, 100)
    expect(loadPage).toHaveBeenNthCalledWith(2, 2, 100)
  })

  it('rejects incomplete pages instead of publishing a truncated workspace', async () => {
    const loadPage = vi.fn()
      .mockResolvedValueOnce({ items: [{ id: 'item-0' }], total: 2, page: 1, page_size: 100 })
      .mockResolvedValue({ items: [], total: 2, page: 2, page_size: 100 })

    await expect(collectPages(loadPage)).rejects.toThrow('Data changed while loading')
    expect(loadPage).toHaveBeenCalledTimes(4)
  })
})

describe('workspaceService', () => {
  beforeEach(() => {
    projectStore.splice(0)
    promptStore.splice(0)
    for (const key of Object.keys(versionStore)) delete versionStore[key]
    for (const key of Object.keys(memberStore)) delete memberStore[key]
    for (const key of Object.keys(activeVersionsStore)) delete activeVersionsStore[key]
    vi.unstubAllGlobals()
  })

  it('keeps the previous workspace snapshot when concurrent paging cannot settle', async () => {
    projectStore.push({ id: 'saved', name: 'Existing workspace', key: 'saved', description: null, owner_id: 'owner', is_owner: true, member_count: 1, prompt_count: 0, monthly_spend: '0', created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z' })
    let generation = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const number = Number(new URL(url).searchParams.get('page'))
      if (number === 1) generation += 1
      return json({ page: number, page_size: 100, total: 101, items: number === 1 ? Array.from({ length: 100 }, (_, index) => ({ id: `${generation}-${index}` })) : [] })
    }))
    await expect(workspaceService.load('owner')).rejects.toThrow('Data changed while loading')
    expect(projectStore).toHaveLength(1)
    expect(projectStore[0].name).toBe('Existing workspace')
  })

  it('loads active deployment pages beyond 100 and replaces the active version on refresh', async () => {
    let currentVersion = 'v3'
    const fetcher = vi.fn(async (url: string) => {
      const parsed = new URL(url)
      const base = { created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z' }
      if (parsed.pathname.endsWith('/projects')) return json({ items: [{ ...base, id: 'project', name: 'Project', key: 'project', description: null, owner: { id: 'owner', display_name: 'Owner' }, member_count: 1, prompt_count: 1 }], total: 1 })
      if (parsed.pathname.endsWith('/prompts')) return json({ items: [{ ...base, id: 'prompt', project_id: 'project', name: 'Prompt', key: 'prompt', description: null, latest_version_number: 3 }], total: 1 })
      if (parsed.pathname.endsWith('/versions')) return json({ items: [], total: 0 })
      if (parsed.pathname.endsWith('/deployments')) return json({ page: Number(parsed.searchParams.get('page')), items: parsed.searchParams.get('page') === '1' ? Array.from({ length: 100 }, (_, n) => ({ prompt_id: `other-${n}`, version_id: 'unrelated', environment: 'prod' })) : [{ prompt_id: 'prompt', version_id: currentVersion, environment: 'prod' }, { prompt_id: 'prompt', version_id: 'v2', environment: 'staging' }], total: 102 })
      throw new Error('Unexpected API read')
    })
    vi.stubGlobal('fetch', fetcher)
    await workspaceService.load('owner')
    expect(versionEnvironments('prompt', 'v3')).toEqual(['production'])
    expect(versionEnvironments('prompt', 'v2')).toEqual(['staging'])
    currentVersion = 'v1'
    await workspaceService.load('owner')
    expect(versionEnvironments('prompt', 'v3')).toEqual([])
    expect(versionEnvironments('prompt', 'v1')).toEqual(['production'])
    expect(versionEnvironments('prompt', 'v2')).toEqual(['staging'])
    expect(fetcher.mock.calls.filter(([url]) => new URL(url).pathname.endsWith('/deployments') && new URL(url).searchParams.get('page') === '2')).toHaveLength(4)
  })

  it('does not let a membership read invalidate an overlapping workspace load', async () => {
    let resolveProjects!: (response: Response) => void
    const projects = new Promise<Response>((resolve) => { resolveProjects = resolve })
    const owner = { id: 'owner', display_name: 'Owner' }
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (new URL(url).pathname.endsWith('/projects')) return projects
      return Promise.resolve(json({ items: [], total: 0, page: 1, page_size: 100 }))
    }))
    const loading = workspaceService.load(owner.id)
    await workspaceService.loadMembers('project')
    resolveProjects(json({ items: [{ id: 'project', name: 'Refreshed', key: 'project', description: null, owner, member_count: 1, prompt_count: 0, created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z' }], total: 1, page: 1, page_size: 100 }))
    await loading
    expect(projectStore[0].name).toBe('Refreshed')
  })

  it('does not grant membership for a pending invitation and reconciles counts from a fresh read', async () => {
    const owner = { id: 'owner', email: 'owner@example.com', display_name: 'Owner', role: 'user', is_active: true, created_at: '2026-10-10T00:00:00Z', is_owner: true }
    const member = { ...owner, id: 'member', email: 'member@example.com', is_owner: false }
    let resolveOld!: (response: Response) => void
    const fetcher = vi.fn().mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce(json(member))
      .mockResolvedValueOnce(json({ items: [owner, member], total: 2, page: 1, page_size: 100 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    const old = workspaceService.loadMembers('project')
    await workspaceService.addMember('project', { email: member.email })
    resolveOld(json({ items: [], total: 0, page: 1, page_size: 100 }))
    await old
    expect(memberStore.project ?? []).not.toContainEqual(expect.objectContaining({ user_id: 'member' }))
    projectStore.push({ id: 'project', name: 'Project', key: 'project', description: null, owner_id: 'owner', is_owner: true, member_count: 99, prompt_count: 0, monthly_spend: '0', created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z' })
    await workspaceService.loadMembers('project')
    expect(projectStore[0].member_count).toBe(2)
    await workspaceService.removeMember('project', 'member')
    expect(projectStore[0].member_count).toBe(1)
    expect(memberStore.project).toHaveLength(1)
  })

  it('distinguishes active environments for each immutable version', () => {
    activeVersionsStore.prompt = { prod: 'v1', staging: 'v2', dev: 'v2' }
    expect(versionEnvironments('prompt', 'v1')).toEqual(['production'])
    expect(versionEnvironments('prompt', 'v2')).toEqual(['staging', 'development'])
    expect(versionEnvironments('prompt', 'v3')).toEqual([])
    expect(versionEnvironments('unknown', 'v1')).toBeUndefined()
  })

  it('does not downgrade latest-version metadata when a create response arrives late', async () => {
    const newest = { id: 'v3', prompt_id: 'prompt', version_number: 3, parent_version_id: 'v2', template: 'Newest', variables: [], model_config: { provider: 'mock', model: 'deterministic', temperature: 0, max_output_tokens: 100 }, commit_message: 'Newest', created_by: 'owner', created_by_name: 'Owner', created_at: '2026-10-10T00:00:00Z' }
    versionStore.prompt = [newest]
    promptStore.push({ id: 'prompt', project_id: 'project', key: 'prompt', name: 'Prompt', description: null, latest_version_number: 3, active_environment: 'draft', created_at: newest.created_at, updated_at: newest.created_at })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ...newest, id: 'v2', version_number: 2, parent_version_id: 'v1', template_body: 'Late response', variables: [], created_by: { id: 'owner', display_name: 'Owner' }, created_at: '2026-10-09T00:00:00Z' })))
    await workspaceService.createVersion('prompt', { parent_version_id: 'v1', template: 'Late response', model_config: newest.model_config, commit_message: 'Late' })
    expect(versionStore.prompt.map((version) => version.id)).toEqual(['v3', 'v2'])
    expect(promptStore[0].latest_version_number).toBe(3)
    expect(promptStore[0].updated_at).toBe(newest.created_at)
  })

  it('loads and adapts the permitted project, prompt, and immutable versions from the API', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ items: [{ id: 'project-1', name: 'Live Project', key: 'live-project', description: null, owner: { id: 'user-1', display_name: 'Owner' }, member_count: 1, prompt_count: 1, created_at: '2026-09-27T00:00:00Z', updated_at: '2026-09-27T00:00:00Z' }], page: 1, page_size: 100, total: 1 }))
      .mockResolvedValueOnce(json({ items: [{ id: 'prompt-1', project_id: 'project-1', key: 'live-prompt', name: 'Live Prompt', description: null, latest_version_number: 1, created_at: '2026-09-27T00:00:00Z', updated_at: '2026-09-27T00:00:00Z' }], page: 1, page_size: 100, total: 1 }))
      .mockResolvedValueOnce(json({ items: [{ id: 'version-1', prompt_id: 'prompt-1', version_number: 1, parent_version_id: null, template_body: 'Hello {{name}}', variables: ['name'], model_config: { provider: 'mock', model: 'deterministic', temperature: 0, max_output_tokens: 128 }, commit_message: 'Initial', created_by: { id: 'user-1', display_name: 'Owner' }, created_at: '2026-09-27T00:00:00Z' }], page: 1, page_size: 100, total: 1 }))
    fetcher.mockResolvedValueOnce(json({ items: [], page: 1, page_size: 100, total: 0 }))
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
      'http://localhost:8000/api/v1/deployments?status=active&page=1&page_size=100',
    ])
  })

  it('loads projects and immutable versions beyond the first API page', async () => {
    const owner = { id: 'user-1', display_name: 'Owner' }
    const project = (index: number) => ({
      id: `project-${index}`, name: `Project ${index}`, key: `project-${index}`,
      description: null, owner, member_count: 1, prompt_count: index === 0 ? 1 : 0,
      created_at: '2026-09-27T00:00:00Z', updated_at: '2026-09-27T00:00:00Z',
    })
    const version = (index: number) => ({
      id: `version-${index}`, prompt_id: 'prompt-0', version_number: index + 1,
      parent_version_id: index ? `version-${index - 1}` : null,
      template_body: `Version ${index}`, variables: [],
      model_config: { provider: 'mock', model: 'deterministic', temperature: 0, max_output_tokens: 128 },
      commit_message: `Save ${index}`, created_by: owner, created_at: '2026-09-27T00:00:00Z',
    })
    const fetcher = vi.fn().mockImplementation((url: string) => {
      const request = new URL(url)
      const page = Number(request.searchParams.get('page'))
      if (request.pathname.endsWith('/projects')) {
        return Promise.resolve(json({ items: page === 1 ? Array.from({ length: 100 }, (_, index) => project(index)) : [project(100)], page, page_size: 100, total: 101 }))
      }
      if (request.pathname.endsWith('/project-0/prompts')) {
        return Promise.resolve(json({ items: [{ id: 'prompt-0', project_id: 'project-0', key: 'prompt-0', name: 'Prompt', description: null, latest_version_number: 101, created_at: '2026-09-27T00:00:00Z', updated_at: '2026-09-27T00:00:00Z' }], page, page_size: 100, total: 1 }))
      }
      if (request.pathname.endsWith('/prompt-0/versions')) {
        return Promise.resolve(json({ items: page === 1 ? Array.from({ length: 100 }, (_, index) => version(index)) : [version(100)], page, page_size: 100, total: 101 }))
      }
      return Promise.resolve(json({ items: [], page, page_size: 100, total: 0 }))
    })
    vi.stubGlobal('fetch', fetcher)

    await workspaceService.load(owner.id)

    expect(projectStore).toHaveLength(101)
    expect(versionStore['prompt-0']).toHaveLength(101)
    expect(fetcher.mock.calls.map(([url]) => url)).toContain('http://localhost:8000/api/v1/projects?page=2&page_size=100')
    expect(fetcher.mock.calls.map(([url]) => url)).toContain('http://localhost:8000/api/v1/prompts/prompt-0/versions?page=2&page_size=100')
  })

  it('creates, updates, and deletes a project through the API even with demo-shaped IDs', async () => {
    const owner = { id: 'usr_demo_owner', display_name: 'Owner' }
    const base = { id: 'project-123', key: 'live-project', description: null, owner, member_count: 1, prompt_count: 0, created_at: '2026-09-27T00:00:00Z', updated_at: '2026-09-27T00:00:00Z' }
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ ...base, name: 'Live Project' }))
      .mockResolvedValueOnce(json({ ...base, name: 'Renamed Project', description: 'Saved in PostgreSQL' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)

    const created = await workspaceService.createProject({ name: 'Live Project', key: 'live-project' }, owner.id)
    const updated = await workspaceService.updateProject(created.id, { name: 'Renamed Project', description: 'Saved in PostgreSQL' }, owner.id)

    expect(updated.name).toBe('Renamed Project')
    expect(projectStore).toEqual([expect.objectContaining({ id: 'project-123', name: 'Renamed Project', description: 'Saved in PostgreSQL' })])
    await workspaceService.deleteProject(created.id)
    expect(projectStore).toEqual([])
    expect(fetcher.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
      ['http://localhost:8000/api/v1/projects', 'POST'],
      ['http://localhost:8000/api/v1/projects/project-123', 'PATCH'],
      ['http://localhost:8000/api/v1/projects/project-123', 'DELETE'],
    ])
  })

  it('reloads members from the API even when a demo-shaped project has cached members', async () => {
    const projectId = 'project-123'
    memberStore[projectId] = [{ user_id: 'stale-user', display_name: 'Stale User', email: 'stale@example.com', role: 'member', joined_at: '2026-09-27T00:00:00Z' }]
    const owner = { id: 'usr_demo_owner', email: 'owner@example.com', display_name: 'Owner', role: 'user', is_active: true, created_at: '2026-09-27T00:00:00Z', is_owner: true }
    const added = { ...owner, id: 'usr_demo_member', email: 'member@example.com', display_name: 'Member', is_owner: false }
    const fetcher = vi.fn()
      .mockResolvedValueOnce(json({ items: [owner], page: 1, page_size: 100, total: 1 }))
      .mockResolvedValueOnce(json(added))
      .mockResolvedValueOnce(json({ items: [owner, added], page: 1, page_size: 100, total: 2 }))
    vi.stubGlobal('fetch', fetcher)

    expect(await workspaceService.loadMembers(projectId)).toEqual([expect.objectContaining({ user_id: owner.id, role: 'owner' })])
    await workspaceService.addMember(projectId, { email: added.email })
    expect(await workspaceService.loadMembers(projectId)).toEqual([
      expect.objectContaining({ user_id: owner.id }),
      expect.objectContaining({ user_id: added.id, role: 'member' }),
    ])
    expect(fetcher.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
      ['http://localhost:8000/api/v1/projects/project-123/members?page=1&page_size=100', 'GET'],
      ['http://localhost:8000/api/v1/projects/project-123/members', 'POST'],
      ['http://localhost:8000/api/v1/projects/project-123/members?page=1&page_size=100', 'GET'],
    ])
  })
})
