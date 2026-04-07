export function hasSelectableVariantGroups(product) {
  return Array.isArray(product?.variants)
    && product.variants.some((group) => (group?.options || []).length >= 2)
}

export function shouldAllowFallbackVariantSelection(product) {
  if (!product) {
    return false
  }

  const map = product.variant_price_map
  if (map && Object.keys(map).length) {
    return false
  }

  if (!hasSelectableVariantGroups(product)) {
    return false
  }

  const platform = String(product.platform || '').trim().toLowerCase()
  if (platform !== 'poizon') {
    return false
  }

  const hasExactBasePrice = typeof product.price_cny === 'number'
    && Number.isFinite(product.price_cny)
    && !product.price_is_starting

  return !hasExactBasePrice
}
