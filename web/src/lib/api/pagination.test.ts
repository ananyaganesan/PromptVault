import { expect, it, vi } from 'vitest'
import { readAllPages } from './pagination'

const record = (id: string, name = id) => ({ id, name })
const page = (number: number, ids: string[], total = 3) => ({ page: number, page_size: 2, total, items: ids.map((id) => record(id)) })

it('returns empty and single-page snapshots without additional reads', async () => {
  const read = vi.fn(async () => page(1, [], 0))
  expect(await readAllPages(read)).toEqual([])
  expect(read).toHaveBeenCalledTimes(1)
})

it('requires two identical full traversals for multiple pages', async () => {
  const read = vi.fn(async (number: number) => number === 1 ? page(1, ['a', 'b']) : page(2, ['c']))
  expect(await readAllPages(read)).toEqual(['a', 'b', 'c'].map((id) => record(id)))
  expect(read.mock.calls.map(([number]) => number)).toEqual([1, 2, 1, 2])
})

it.each(['insert', 'delete', 'duplicate', 'missing'] as const)('restarts after a concurrent %s rather than publishing partial records', async (kind) => {
  const read = vi.fn().mockResolvedValueOnce(page(1, ['a', 'b']))
    .mockResolvedValueOnce(kind === 'insert' ? page(2, ['b', 'c'], 4) : kind === 'delete' ? page(2, [], 2) : kind === 'duplicate' ? page(2, ['b']) : page(2, []))
    .mockImplementation(async (number: number) => number === 1 ? page(1, ['a', 'b']) : page(2, ['c']))
  expect(await readAllPages(read)).toEqual(['a', 'b', 'c'].map((id) => record(id)))
  expect(read).toHaveBeenCalledTimes(6)
})

it('detects same-count replacement and changed fields between traversals', async () => {
  const read = vi.fn().mockResolvedValueOnce(page(1, ['a', 'b']))
    .mockResolvedValueOnce(page(2, ['c']))
    .mockImplementation(async (number: number) => ({ ...page(number, number === 1 ? ['a', 'b'] : ['d']), items: number === 1 ? [record('a', 'Updated'), record('b')] : [record('d')] }))
  expect(await readAllPages(read)).toEqual([record('a', 'Updated'), record('b'), record('d')])
  expect(read).toHaveBeenCalledTimes(6)
})

it('fails within a fixed number of requests when data keeps changing', async () => {
  let revision = 0
  const read = vi.fn(async (number: number) => {
    if (number === 1) revision += 1
    return page(number, number === 1 ? [`a${revision}`, 'b'] : ['c'])
  })
  await expect(readAllPages(read)).rejects.toThrow('Data changed while loading')
  expect(read).toHaveBeenCalledTimes(8)
})
