import type { Page } from '../../types/api'

export async function readAllPages<T>(read: (page: number) => Promise<Page<T>>): Promise<T[]> {
  // Offset pages are individual snapshots. Require two matching traversals for
  // multi-page lists; retry drifting totals, duplicate/missing rows and updates.
  // This is bounded eventual refresh, not a database snapshot across HTTP calls.
  let previous: string | undefined
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const items: T[] = []
    let total: number | undefined
    let valid = true
    const seen = new Set<unknown>()
    for (let page = 1; page <= 10_000; page += 1) {
      const result = await read(page)
      total ??= result.total
      if (result.page !== page || result.total !== total || result.page_size < 1 || result.items.length > result.page_size) {
        valid = false; break
      }
      for (const item of result.items) {
        const id = item && typeof item === 'object' && 'id' in item ? item.id : JSON.stringify(item)
        if (seen.has(id)) valid = false
        seen.add(id)
      }
      items.push(...result.items)
      if (items.length >= total || result.items.length < result.page_size) {
        valid &&= items.length === total
        if (valid && page === 1 && previous === undefined) return items
        break
      }
      if (page === 10_000) valid = false
    }
    if (!valid) { previous = undefined; continue }
    const fingerprint = JSON.stringify(items)
    if (previous === fingerprint) return items
    previous = fingerprint
  }
  throw new Error('Data changed while loading. Refresh data to try again.')
}
