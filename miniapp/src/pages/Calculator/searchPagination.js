function toFiniteNumber(value, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function toExplicitTrue(value) {
  return value === true || value === 1 || value === '1' || value === 'true'
}

export function resolveSearchPagination(payload, platform, { startId = 0, count = 20 } = {}) {
  const normalizedPlatform = String(platform || payload?.platform || '').trim().toLowerCase()
  const safeStartId = Math.max(0, toFiniteNumber(startId, 0))
  const safeCount = Math.max(1, toFiniteNumber(count, 20))
  const loadedCount = Array.isArray(payload?.products) ? payload.products.length : 0
  const responseNextStartId = toFiniteNumber(payload?.next_start_id, NaN)
  const nextStartId = Number.isFinite(responseNextStartId)
    ? Math.max(safeStartId, responseNextStartId)
    : (loadedCount > 0 ? safeStartId + safeCount : safeStartId)

  const totalCount = toFiniteNumber(payload?.total, 0)
  const explicitHasMore = toExplicitTrue(payload?.has_more)

  let inferredHasMore = false
  if (normalizedPlatform === 'poizon') {
    inferredHasMore = loadedCount >= safeCount && nextStartId > safeStartId
  } else if (normalizedPlatform === 'taobao') {
    inferredHasMore = totalCount > 0
      ? safeStartId + loadedCount < totalCount
      : loadedCount >= safeCount
  } else {
    inferredHasMore = loadedCount >= safeCount
  }

  return {
    nextStartId,
    hasMore: explicitHasMore || inferredHasMore,
  }
}

export function getSearchUnavailablePlatform(error) {
  const code = String(error?.code || '').trim().toLowerCase()
  if (code === 'taobao_search_unavailable') return 'taobao'
  if (code === '1688_search_unavailable') return '1688'
  return ''
}
