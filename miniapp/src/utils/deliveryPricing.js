export const STANDARD_DELIVERY_TYPE = 'standard'
export const EXPRESS_DELIVERY_TYPE = 'express'

export const DELIVERY_MODE_LABELS = {
  [STANDARD_DELIVERY_TYPE]: 'Обычная доставка',
  [EXPRESS_DELIVERY_TYPE]: 'Экспресс доставка',
}

export const DELIVERY_ROUTE_LABELS = {
  [STANDARD_DELIVERY_TYPE]: 'Обычная до Москвы',
  [EXPRESS_DELIVERY_TYPE]: 'Авиа до Москвы',
}

const DEFAULT_SETTINGS = {
  commission_pct: '10.0',
  min_commission_rub: '300.0',
  delivery_air_moscow_rub_500g: '1400.0',
  delivery_standard_moscow_rub_500g: '500.0',
  delivery_cdek_russia_rub_500g: '150.0',
  delivery_air_moscow_days: '5-10 дней',
  delivery_standard_moscow_days: '15-25 дней',
  delivery_cdek_russia_days: '2-5 дней',
}

function parseNumber(value, fallback = 0) {
  const normalized = String(value ?? '')
    .trim()
    .replace(',', '.')
    .replace(/\s+/g, '')

  const numericValue = Number(normalized)
  return Number.isFinite(numericValue) ? numericValue : fallback
}

export function normalizeDeliveryType(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'express' || normalized === 'fast' || normalized === 'air' || normalized === 'avia') {
    return EXPRESS_DELIVERY_TYPE
  }
  return STANDARD_DELIVERY_TYPE
}

export function isMoscowDeliveryCity(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) return true
  return normalized.includes('moscow') || normalized.includes('моск')
}

export function getDeliveryUnitsForWeight(weightKg) {
  const weightValue = parseNumber(weightKg, 0.5)
  const normalizedWeight = weightValue > 0 ? weightValue : 0.5
  return Math.max(1, Math.ceil(normalizedWeight / 0.5))
}

export function getDeliverySettings(settings = {}) {
  const merged = { ...DEFAULT_SETTINGS, ...(settings || {}) }
  return {
    commissionPct: parseNumber(merged.commission_pct, 10),
    minCommissionRub: parseNumber(merged.min_commission_rub, 300),
    standardToMoscowRub500g: parseNumber(merged.delivery_standard_moscow_rub_500g, 500),
    expressToMoscowRub500g: parseNumber(merged.delivery_air_moscow_rub_500g, 1400),
    cdekRussiaRub500g: parseNumber(merged.delivery_cdek_russia_rub_500g, 150),
    standardDays: String(merged.delivery_standard_moscow_days || '').trim(),
    expressDays: String(merged.delivery_air_moscow_days || '').trim(),
    cdekDays: String(merged.delivery_cdek_russia_days || '').trim(),
  }
}

export function calculateOrderItemPreview({
  priceCny,
  weightKg,
  weightEstimated = false,
  adminSettings = {},
  rate = 0,
  deliveryType = STANDARD_DELIVERY_TYPE,
  city = '',
} = {}) {
  const settings = getDeliverySettings(adminSettings)
  const normalizedDeliveryType = normalizeDeliveryType(deliveryType)
  const units500g = getDeliveryUnitsForWeight(weightKg)
  const routeRate = normalizedDeliveryType === EXPRESS_DELIVERY_TYPE
    ? settings.expressToMoscowRub500g
    : settings.standardToMoscowRub500g
  const goodsRub = parseNumber(priceCny, 0) * parseNumber(rate, 0)
  const commissionRub = Math.max(goodsRub * settings.commissionPct / 100, settings.minCommissionRub)
  const deliveryToMoscowRub = units500g * routeRate
  const addCdek = !isMoscowDeliveryCity(city)
  const cdekRub = addCdek ? units500g * settings.cdekRussiaRub500g : 0
  const subtotalRub = goodsRub + commissionRub + deliveryToMoscowRub + cdekRub
  const unitsNote = `${weightEstimated ? '~' : ''}${units500g} × 500 г`

  return {
    subtotalRub,
    goodsRub,
    commissionRub,
    deliveryToMoscowRub,
    cdekRub,
    units500g,
    unitsNote,
    addCdek,
    deliveryType: normalizedDeliveryType,
    modeLabel: DELIVERY_MODE_LABELS[normalizedDeliveryType],
    routeLabel: DELIVERY_ROUTE_LABELS[normalizedDeliveryType],
    routeDays: normalizedDeliveryType === EXPRESS_DELIVERY_TYPE ? settings.expressDays : settings.standardDays,
    cdekDays: settings.cdekDays,
  }
}
