const ALIBABA_IMAGE_HOST_SUFFIXES = ['alicdn.com', 'alicdn.com.cn']

function normalizeRemoteUrl(url) {
  if (typeof url !== 'string') return ''
  const trimmed = url.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('//')) return `https:${trimmed}`
  return trimmed
}

export function shouldProxyImageUrl(url) {
  const normalized = normalizeRemoteUrl(url)
  if (!normalized || normalized.startsWith('/api/image-proxy?')) return false
  if (!/^https?:/i.test(normalized)) return false

  try {
    const parsed = new URL(normalized)
    const host = (parsed.hostname || '').toLowerCase()
    return ALIBABA_IMAGE_HOST_SUFFIXES.some((suffix) => host === suffix || host.endsWith(`.${suffix}`))
  } catch {
    return false
  }
}

export function proxyImageUrl(url) {
  const normalized = normalizeRemoteUrl(url)
  if (!normalized) return ''
  if (!shouldProxyImageUrl(normalized)) return normalized
  return `/api/image-proxy?url=${encodeURIComponent(normalized)}`
}

export function getImageSourceCandidates(url, { preferProxy = true } = {}) {
  const normalized = normalizeRemoteUrl(url)
  if (!normalized) return []

  const proxied = proxyImageUrl(normalized)
  if (proxied === normalized) return [normalized]
  return preferProxy ? [proxied, normalized] : [normalized, proxied]
}
