import type { Page } from '../../types/api'

export async function readAllPages<T>(read: (page: number) => Promise<Page<T>>): Promise<T[]> {
  const items: T[] = []
  for (let page = 1; ; page += 1) {
    const result = await read(page)
    items.push(...result.items)
    if (items.length >= result.total || result.items.length === 0) return items
  }
}
