export const APP_AUTH_STATE_EVENT = 'buyer-miniapp-auth-state-change'

const APP_AUTH_STATE_KEY = '__BUYER_MINIAPP_AUTH_STATE__'

function normalizeUserId(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

function normalizeLaunchPlatform(value) {
  const normalized = String(value || '').trim().toLowerCase()
  return normalized === 'telegram' || normalized === 'vk' || normalized === 'query' || normalized === 'web'
    ? normalized
    : ''
}

function normalizeAuthState(rawState = {}) {
  return {
    userId: normalizeUserId(rawState.userId),
    launchPlatform: normalizeLaunchPlatform(rawState.launchPlatform),
  }
}

export function readAppAuthState() {
  if (typeof window === 'undefined') {
    return normalizeAuthState()
  }

  return normalizeAuthState(window[APP_AUTH_STATE_KEY])
}

export function writeAppAuthState(nextState = {}) {
  if (typeof window === 'undefined') {
    return normalizeAuthState(nextState)
  }

  const normalizedState = normalizeAuthState(nextState)
  window[APP_AUTH_STATE_KEY] = normalizedState
  window.dispatchEvent(new CustomEvent(APP_AUTH_STATE_EVENT, { detail: normalizedState }))
  return normalizedState
}

export function clearAppAuthState() {
  if (typeof window === 'undefined') {
    return normalizeAuthState()
  }

  delete window[APP_AUTH_STATE_KEY]
  const clearedState = normalizeAuthState()
  window.dispatchEvent(new CustomEvent(APP_AUTH_STATE_EVENT, { detail: clearedState }))
  return clearedState
}
