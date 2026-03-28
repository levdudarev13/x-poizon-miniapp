import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldAllowFallbackVariantSelection } from './productVariants.js'

const variantGroups = [
  { name: 'Color', options: ['Yellow', 'Apricot'] },
  { name: 'Size', options: ['S', 'M'] },
]

test('taobao keeps variant chips selectable without variant prices', () => {
  assert.equal(
    shouldAllowFallbackVariantSelection({
      platform: 'taobao',
      price_cny: 42.49,
      price_is_starting: false,
      variants: variantGroups,
      variant_price_map: {},
    }),
    true,
  )
})

test('1688 keeps variant chips selectable without variant prices', () => {
  assert.equal(
    shouldAllowFallbackVariantSelection({
      platform: '1688',
      price_cny: 6.78,
      price_is_starting: false,
      variants: variantGroups,
      variant_price_map: {},
    }),
    true,
  )
})

test('poizon exact-price products still disable fallback variant selection', () => {
  assert.equal(
    shouldAllowFallbackVariantSelection({
      platform: 'poizon',
      price_cny: 888,
      price_is_starting: false,
      variants: variantGroups,
      variant_price_map: {},
    }),
    false,
  )
})
