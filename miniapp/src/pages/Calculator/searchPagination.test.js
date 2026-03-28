import assert from 'node:assert/strict'
import test from 'node:test'

import { getSearchUnavailablePlatform, resolveSearchPagination } from './searchPagination.js'

test('resolveSearchPagination keeps load more when backend omits has_more for taobao', () => {
  const result = resolveSearchPagination(
    {
      total: 55,
      next_start_id: 20,
      products: Array.from({ length: 20 }, (_, index) => ({ id: index + 1 })),
    },
    'taobao',
    { startId: 0, count: 20 },
  )

  assert.equal(result.nextStartId, 20)
  assert.equal(result.hasMore, true)
})

test('resolveSearchPagination keeps load more for 1688 full pages even on falsey responses', () => {
  const result = resolveSearchPagination(
    {
      has_more: false,
      next_start_id: 20,
      products: Array.from({ length: 20 }, (_, index) => ({ id: index + 1 })),
    },
    '1688',
    { startId: 0, count: 20 },
  )

  assert.equal(result.nextStartId, 20)
  assert.equal(result.hasMore, true)
})

test('resolveSearchPagination stops when taobao total is exhausted', () => {
  const result = resolveSearchPagination(
    {
      total: 55,
      next_start_id: 60,
      products: Array.from({ length: 15 }, (_, index) => ({ id: index + 1 })),
    },
    'taobao',
    { startId: 40, count: 20 },
  )

  assert.equal(result.nextStartId, 60)
  assert.equal(result.hasMore, false)
})

test('resolveSearchPagination trusts poizon cursor when it advances', () => {
  const result = resolveSearchPagination(
    {
      next_start_id: 77,
      products: Array.from({ length: 20 }, (_, index) => ({ id: index + 1 })),
    },
    'poizon',
    { startId: 0, count: 20 },
  )

  assert.equal(result.nextStartId, 77)
  assert.equal(result.hasMore, true)
})

test('getSearchUnavailablePlatform maps provider-specific error codes', () => {
  assert.equal(getSearchUnavailablePlatform({ code: 'taobao_search_unavailable' }), 'taobao')
  assert.equal(getSearchUnavailablePlatform({ code: '1688_search_unavailable' }), '1688')
  assert.equal(getSearchUnavailablePlatform({ code: 'other_error' }), '')
})
