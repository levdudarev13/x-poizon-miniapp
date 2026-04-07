import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveSearchPagination } from './searchPagination.js'

test('resolveSearchPagination keeps load more when backend returns a full page and next cursor', () => {
  const result = resolveSearchPagination(
    {
      next_start_id: 20,
      products: Array.from({ length: 20 }, (_, index) => ({ id: index + 1 })),
    },
    'poizon',
    { startId: 0, count: 20 },
  )

  assert.equal(result.nextStartId, 20)
  assert.equal(result.hasMore, true)
})

test('resolveSearchPagination stops when returned page is shorter than requested', () => {
  const result = resolveSearchPagination(
    {
      next_start_id: 35,
      products: Array.from({ length: 15 }, (_, index) => ({ id: index + 1 })),
    },
    'poizon',
    { startId: 20, count: 20 },
  )

  assert.equal(result.nextStartId, 35)
  assert.equal(result.hasMore, false)
})

test('resolveSearchPagination stops when total count is exhausted', () => {
  const result = resolveSearchPagination(
    {
      total: 55,
      next_start_id: 60,
      products: Array.from({ length: 15 }, (_, index) => ({ id: index + 1 })),
    },
    'poizon',
    { startId: 40, count: 20 },
  )

  assert.equal(result.nextStartId, 60)
  assert.equal(result.hasMore, false)
})
