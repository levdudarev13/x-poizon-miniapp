function parseVariantPairs(rawKey) {
  try {
    const parsed = JSON.parse(rawKey)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function toFiniteNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string') {
    const normalized = value.trim().replace(',', '.')
    if (!normalized) {
      return null
    }

    const parsed = Number.parseFloat(normalized)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }

  return null
}

export function variantKey(selectedVariants) {
  return JSON.stringify(
    Object.entries(selectedVariants || {})
      .map(([name, value]) => [String(name || '').trim(), String(value || '').trim()])
      .filter(([name, value]) => name && value)
      .sort((left, right) => {
        if (left[0] === right[0]) {
          return left[1].localeCompare(right[1])
        }
        return left[0].localeCompare(right[0])
      }),
  )
}

export function resolveProductPriceState(product, selectedVariants = {}, manualPrice = '') {
  if (!product) {
    return {
      calculationPrice: null,
      displayPrice: null,
      isStartingPrice: false,
      source: 'none',
    }
  }

  const map = product.variant_price_map || {}
  const groups = Array.isArray(product.variants) ? product.variants : []
  const selectedVariantCount = Object.keys(selectedVariants || {}).length

  if (map && Object.keys(map).length && selectedVariantCount) {
    const exactPrice = toFiniteNumber(map[variantKey(selectedVariants)])
    if (exactPrice != null) {
      return {
        calculationPrice: exactPrice,
        displayPrice: exactPrice,
        isStartingPrice: false,
        source: 'variant',
      }
    }

    const filtered = Object.entries(map).filter(([rawKey]) => {
      const pairs = parseVariantPairs(rawKey)
      if (!pairs.length) return false

      for (let index = 0; index < groups.length; index += 1) {
        const groupName = groups[index]?.name
        const selectedValue = groupName ? selectedVariants[groupName] : ''
        if (!selectedValue) continue

        const pair = pairs.find(([pairGroupName]) => pairGroupName === groupName)
        if (pair && pair[1] !== selectedValue) {
          return false
        }
      }

      return true
    })

    if (filtered.length) {
      let minPrice = Infinity
      for (const [, rawPrice] of filtered) {
        const parsedPrice = toFiniteNumber(rawPrice)
        if (parsedPrice != null) {
          minPrice = Math.min(minPrice, parsedPrice)
        }
      }
      if (minPrice < Infinity) {
        return {
          calculationPrice: minPrice,
          displayPrice: minPrice,
          isStartingPrice: false,
          source: 'variant',
        }
      }
    }
  }

  const normalizedManualPrice = typeof manualPrice === 'string' ? manualPrice.trim() : String(manualPrice || '').trim()
  if (normalizedManualPrice) {
    const parsedManualPrice = toFiniteNumber(normalizedManualPrice)
    if (parsedManualPrice != null && parsedManualPrice > 0) {
      return {
        calculationPrice: parsedManualPrice,
        displayPrice: parsedManualPrice,
        isStartingPrice: false,
        source: 'manual',
      }
    }
  }

  const basePrice = toFiniteNumber(product.price_cny)
  if (basePrice == null) {
    return {
      calculationPrice: null,
      displayPrice: null,
      isStartingPrice: false,
      source: 'none',
    }
  }

  if (product.price_is_starting) {
    return {
      calculationPrice: null,
      displayPrice: basePrice,
      isStartingPrice: true,
      source: 'starting',
    }
  }

  return {
    calculationPrice: basePrice,
    displayPrice: basePrice,
    isStartingPrice: false,
    source: 'base',
  }
}
