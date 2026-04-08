import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldAllowFallbackVariantSelection } from './productVariants.js'

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

test('poizon starting-price products with standalone available sizes keep fallback size selection enabled', () => {
  assert.equal(
    shouldAllowFallbackVariantSelection({
      platform: 'poizon',
      price_cny: 888,
      price_is_starting: true,
      variants: [],
      available_sizes: ['40', '40.5', '41'],
      variant_price_map: {},
    }),
    true,
  )
})

test('poizon exact-price products with standalone available sizes keep size selection locked', () => {
  assert.equal(
    shouldAllowFallbackVariantSelection({
      platform: 'poizon',
      price_cny: 888,
      price_is_starting: false,
      variants: [],
      available_sizes: ['40', '40.5', '41'],
      variant_price_map: {},
    }),
    false,
  )
})
