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
