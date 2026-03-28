import test from 'node:test'
import assert from 'node:assert/strict'

import { splitShowcaseRows } from './showcaseRows.js'

test('splitShowcaseRows keeps slots 1-5 in the first row and 6-10 in the second row', () => {
  const { firstRow, secondRow } = splitShowcaseRows([
    { slot: 7, id: 'slot-7' },
    { slot: 1, id: 'slot-1' },
    { slot: 6, id: 'slot-6' },
  ])

  assert.deepEqual(firstRow.map((item) => item.id), ['slot-1'])
  assert.deepEqual(secondRow.map((item) => item.id), ['slot-6', 'slot-7'])
})

test('splitShowcaseRows falls back to sequential slicing when items do not have explicit slots', () => {
  const items = Array.from({ length: 6 }, (_, index) => ({ id: `item-${index + 1}` }))
  const { firstRow, secondRow } = splitShowcaseRows(items)

  assert.deepEqual(firstRow.map((item) => item.id), ['item-1', 'item-2', 'item-3', 'item-4', 'item-5'])
  assert.deepEqual(secondRow.map((item) => item.id), ['item-6'])
})
