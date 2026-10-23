import { afterEach, describe, expect, it, vi } from 'vitest'
import { sampleUserProfiles } from '../../mocks/users'
import { adminApi } from './api'
import { adminService } from './admin-service'

vi.mock('../../lib/runtime', () => ({ useDemoData: false }))

afterEach(() => vi.restoreAllMocks())

describe('live model pricing', () => {
  it('loads later pricing pages', async () => {
    const price = {
      id: 'price-1', provider: 'gemini', model: 'test-model',
      input_price_per_million: '1.000000', output_price_per_million: '2.000000',
      effective_from: '2026-10-07T00:00:00Z', effective_to: null,
      created_by: null, created_at: '2026-10-07T00:00:00Z',
    }
    const list = vi.spyOn(adminApi, 'listModelPrices').mockImplementation(async ({ page } = {}) => ({
      items: page === 1 ? Array.from({ length: 100 }, (_, index) => ({ ...price, id: `price-${index}` })) : [{ ...price, id: 'price-100' }],
      total: 101, page: page ?? 1, page_size: 100,
    }))

    const rows = await adminService.listModelPrices(sampleUserProfiles[1])

    expect(list).toHaveBeenCalledTimes(2)
    expect(rows).toHaveLength(202)
    expect(rows.some((row) => row.id.startsWith('price-100:'))).toBe(true)
  })

  it('sends both entered prices without silently setting either one to zero', async () => {
    const create = vi.spyOn(adminApi, 'createModelPrice').mockResolvedValue({
      id: 'new-price', provider: 'gemini', model: 'test-model',
      input_price_per_million: '1.250000', output_price_per_million: '2.500000',
      effective_from: '2026-10-07T00:00:00Z', effective_to: null,
      created_by: null, created_at: '2026-10-07T00:00:00Z',
    })

    const rows = await adminService.addModelPrice({
      provider: 'gemini', model: 'test-model', input_price_per_million: '1.250000',
      output_price_per_million: '2.500000', effective_from: '2026-10-07T00:00:00Z',
    }, sampleUserProfiles[1])

    expect(create).toHaveBeenCalledWith({
      provider: 'gemini', model: 'test-model', input_price_per_million: '1.250000',
      output_price_per_million: '2.500000', effective_from: '2026-10-07T00:00:00Z',
    })
    expect(rows.map((row) => row.price_per_million_tokens)).toEqual(['1.250000', '2.500000'])
  })
})
