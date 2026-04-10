import bridge from '@vkontakte/vk-bridge'

function hasVkLaunchContext() {
  if (typeof window === 'undefined') {
    return false
  }

  try {
    const rawSearch = window.location.search.startsWith('?')
      ? window.location.search.slice(1)
      : window.location.search
    const params = new URLSearchParams(rawSearch)

    return (
      params.has('vk_platform') ||
      params.has('vk_user_id') ||
      params.has('sign')
    )
  } catch {
    return false
  }
}

let initPromise = null
let viewerProfilePromise = null

function toFiniteNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function normalizeVkViewerProfile(rawProfile) {
  if (!rawProfile || typeof rawProfile !== 'object') {
    return null
  }

  const userId = toFiniteNumber(
    rawProfile.id ??
    rawProfile.user_id ??
    rawProfile.vk_user_id,
  )
  if (userId <= 0) {
    return null
  }

  const photoUrl = String(
    rawProfile.photo_200 ||
    rawProfile.photo_100 ||
    rawProfile.photo_50 ||
    rawProfile.photo_url ||
    '',
  ).trim()

  return {
    id: userId,
    username: String(rawProfile.screen_name || rawProfile.username || '').trim(),
    first_name: String(rawProfile.first_name || '').trim(),
    last_name: String(rawProfile.last_name || '').trim(),
    photo_url: photoUrl || null,
  }
}

export function initVkMiniAppBridge() {
  if (!hasVkLaunchContext()) {
    return Promise.resolve(false)
  }

  if (initPromise) {
    return initPromise
  }

  initPromise = bridge.send('VKWebAppInit')
    .then(() => true)
    .catch((error) => {
      console.warn('VK Mini App bridge init failed:', error)
      return false
    })

  return initPromise
}

export function getVkViewerProfile() {
  if (!hasVkLaunchContext()) {
    return Promise.resolve(null)
  }

  if (viewerProfilePromise) {
    return viewerProfilePromise
  }

  viewerProfilePromise = initVkMiniAppBridge()
    .then((initialized) => {
      if (!initialized) {
        return null
      }

      return bridge.send('VKWebAppGetUserInfo')
    })
    .then((profile) => normalizeVkViewerProfile(profile))
    .catch((error) => {
      console.warn('VK Mini App viewer profile fetch failed:', error)
      return null
    })

  return viewerProfilePromise
}
