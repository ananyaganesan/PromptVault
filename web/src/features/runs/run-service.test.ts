import { describe, expect, it } from 'vitest'
import { runService } from './run-service'

describe('run service summaries', () => {
  it('filters the full run ledger before applying pagination', async () => {
    const firstPage = await runService.list({
      search: 'demo-run-4',
      page: 1,
      page_size: 1,
    } as Parameters<typeof runService.list>[0])

    expect(firstPage.total).toBe(1)
    expect(firstPage.items.map((run) => run.id)).toEqual(['demo-run-4'])
  })

  it('uses the dashboard response as the source of recent activity', async () => {
    const dashboard = await runService.dashboard()

    expect(dashboard.recent_runs.map((run) => run.id)).toEqual([
      'demo-run-1',
      'demo-run-2',
      'demo-run-3',
      'demo-run-4',
    ])
  })
})
