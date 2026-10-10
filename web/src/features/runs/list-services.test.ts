import { afterEach, expect, it, vi } from 'vitest'
import { deploymentsApi } from '../deployments/api'
import { deploymentService } from '../deployments/deployment-service'
import { runsApi } from './api'
import { runService } from './run-service'

vi.mock('../../lib/runtime', () => ({ useDemoData: false }))
afterEach(() => vi.restoreAllMocks())

it('forwards supported run filters and server pagination without a text-search parameter', async () => {
  const query = {
    project_id: 'project-1', prompt_id: 'prompt-1', version_id: 'version-1',
    model: 'rare-model', status: 'failed' as const, page: 2, page_size: 10,
    from: '2026-10-01T00:00:00Z', to: '2026-11-01T00:00:00Z',
  }
  const response = { items: [], total: 11, page: 2, page_size: 10 }
  const list = vi.spyOn(runsApi, 'list').mockResolvedValue(response)

  expect(await runService.list(query)).toEqual(response)
  expect(list).toHaveBeenCalledWith(query)
})

it('maps deployment filters to backend values and preserves page metadata', async () => {
  const response = { items: [], total: 21, page: 3, page_size: 10 }
  const list = vi.spyOn(deploymentsApi, 'list').mockResolvedValue(response)

  expect(await deploymentService.list({
    project_id: 'project-1', status: 'pending_approval', environment: 'production', page: 3, page_size: 10,
  })).toEqual(response)
  expect(list).toHaveBeenCalledWith({
    project_id: 'project-1', status: 'pending', environment: 'prod', page: 3, page_size: 10,
  })
})
