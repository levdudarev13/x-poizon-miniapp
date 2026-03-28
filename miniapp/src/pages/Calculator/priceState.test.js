import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveProductPriceState, variantKey } from './priceState.js'

test('starting price stays display-only until exact price is known', () => {
  const result = resolveProductPriceState({
    price_cny: 888,
    price_is_starting: true,
    variants: [],
    variant_price_map: {},
  })

  assert.equal(result.calculationPrice, null)
  assert.equal(result.displayPrice, 888)
  assert.equal(result.isStartingPrice, true)
  assert.equal(result.source, 'starting')
})

test('manual price overrides starting price and becomes exact', () => {
  const result = resolveProductPriceState(
    {
      price_cny: 888,
      price_is_starting: true,
      variants: [],
      variant_price_map: {},
    },
    {},
    '1500',
  )

  assert.equal(result.calculationPrice, 1500)
  assert.equal(result.displayPrice, 1500)
  assert.equal(result.isStartingPrice, false)
  assert.equal(result.source, 'manual')
})

test('exact variant price wins over starting base price', () => {
  const selectedVariants = { Color: 'Black', Size: '42' }
  const result = resolveProductPriceState(
    {
      price_cny: 888,
      price_is_starting: true,
      variants: [
        { name: 'Color', options: ['Black', 'White'] },
        { name: 'Size', options: ['41', '42'] },
      ],
      variant_price_map: {
        [variantKey(selectedVariants)]: 1288,
      },
    },
    selectedVariants,
  )

  assert.equal(result.calculationPrice, 1288)
  assert.equal(result.displayPrice, 1288)
  assert.equal(result.isStartingPrice, false)
  assert.equal(result.source, 'variant')
})

test('variant price map accepts numeric strings from API payloads', () => {
  const selectedVariants = { Color: 'Apricot', Size: 'M' }
  const result = resolveProductPriceState(
    {
      price_cny: 42.49,
      price_is_starting: false,
      variants: [
        { name: 'Color', options: ['Yellow', 'Apricot'] },
        { name: 'Size', options: ['S', 'M'] },
      ],
      variant_price_map: {
        [variantKey(selectedVariants)]: '48.03',
      },
    },
    selectedVariants,
  )

  assert.equal(result.calculationPrice, 48.03)
  assert.equal(result.displayPrice, 48.03)
  assert.equal(result.isStartingPrice, false)
  assert.equal(result.source, 'variant')
})
