import assert from 'node:assert/strict'
import test from 'node:test'

import {
  shouldAllowFallbackVariantSelection,
  shouldAllowVariantSelectionWithoutPriceMap,
} from './productVariants.js'

const variantGroups = [
  { name: 'Color', options: ['Yellow', 'Apricot'] },
  { name: 'Size', options: ['S', 'M'] },
]

test('poizon starting-price products keep variant chips selectable without variant prices', () => {
  assert.equal(
    shouldAllowFallbackVariantSelection({
      platform: 'poizon',
      price_cny: 42.49,
      price_is_starting: true,
      variants: variantGroups,
      variant_price_map: {},
    }),
    true,
  )
})

test('poizon exact-price products still keep variant chips selectable without price map', () => {
  assert.equal(
    shouldAllowVariantSelectionWithoutPriceMap({
      platform: 'poizon',
      price_cny: 888,
      price_is_starting: false,
      variants: variantGroups,
      variant_price_map: {},
    }),
    true,
  )
})

test('non-poizon products do not enable fallback variant selection', () => {
  assert.equal(
    shouldAllowFallbackVariantSelection({
      platform: 'other',
      price_cny: 6.78,
      price_is_starting: false,
      variants: variantGroups,
      variant_price_map: {},
    }),
    false,
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
