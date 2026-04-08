export function hasSelectableVariantGroups(product) {
  return Array.isArray(product?.variants)
    && product.variants.some((group) => (group?.options || []).length >= 2)
}

const SIZE_GROUP_NAMES = ['size', 'размер', 'sz', 'taille', '尺码', '尺寸']
export const POIZON_MANUAL_VARIANT_SELECTIONS = {
  left: 'Вариант по кнопке 05 (Poizon)',
  right: 'Вариант по кнопке 06 (Poizon)',
}
export const POIZON_MANUAL_VARIANT_HINT_TEXT = 'Нажмите на кнопку если нужный вам размер\nнаходится не в Китае или если вы хотите заказать товар с 95'
export const POIZON_MANUAL_PRICE_HELPER_TEXT = 'Соответствующую выбранному размеру, как на Poizon, так как товар находится не в Китае.'

function normalizeOptionValue(value) {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function getSavedSelectionParts(product) {
  return String(product?.size || '')
    .split(' / ')
    .map((part) => part.trim())
    .filter(Boolean)
}

export function shouldAllowFallbackVariantSelection(product) {
  if (!product) {
    return false
  }

  const map = product.variant_price_map
  if (map && Object.keys(map).length) {
    return false
  }

  if (!hasSelectableVariantGroups(product) && !(Array.isArray(product?.available_sizes) && product.available_sizes.length >= 2)) {
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

export function derivePersistedVariantSelection(product) {
  const savedParts = getSavedSelectionParts(product)
  const groups = Array.isArray(product?.variants)
    ? product.variants.filter((group) => (group?.options || []).length >= 2)
    : []
  const selectedVariants = {}

  for (const group of groups) {
    const options = (group.options || [])
      .map((option) => normalizeOptionValue(typeof option === 'string' ? option : option?.name))
      .filter(Boolean)
    const match = savedParts.find((part) => options.includes(part))
    if (match) {
      selectedVariants[group.name] = match
    }
  }

  const hasVariantSizeGroup = groups.some((group) => SIZE_GROUP_NAMES.includes(normalizeOptionValue(group.name).toLowerCase()))
  let selectedSize = ''
  if (!hasVariantSizeGroup && Array.isArray(product?.available_sizes) && product.available_sizes.length >= 2) {
    const sizeOptions = product.available_sizes
      .map((option) => normalizeOptionValue(typeof option === 'string' ? option : option?.name))
      .filter(Boolean)
    selectedSize = sizeOptions.find((size) => savedParts.includes(size) || String(product?.size || '').includes(size)) || ''
  }

  return {
    selectedVariants,
    selectedSize,
  }
}

export function shouldRequireManualPriceForSelection(product, selectionText = '') {
  if (!shouldAllowFallbackVariantSelection(product)) {
    return false
  }

  const savedSelection = normalizeOptionValue(product?.size)
  const currentSelection = normalizeOptionValue(selectionText)
  if (!savedSelection || !currentSelection) {
    return false
  }

  return savedSelection !== currentSelection
}
