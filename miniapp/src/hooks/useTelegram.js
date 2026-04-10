import { useEffect, useState } from 'react'

import { APP_AUTH_STATE_EVENT, readAppAuthState } from '../utils/appAuthState.js'

function getTelegramWebApp() {
  return window.Telegram?.WebApp ?? null
}

function toFiniteNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function normalizeInset(source = {}) {
  return {
    top: toFiniteNumber(source.top),
    right: toFiniteNumber(source.right),
    bottom: toFiniteNumber(source.bottom),
    left: toFiniteNumber(source.left),
  }
}

function parseUserFromInitData(initData = '') {
  if (!initData) return null

  try {
    const params = new URLSearchParams(initData)
    const rawUser = params.get('user')
    return rawUser ? JSON.parse(rawUser) : null
  } catch {
    return null
  }
}

function parseTelegramLaunchParams() {
  const rawHash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash

  if (!rawHash) {
    return { initData: '', user: null }
  }

  try {
    const params = new URLSearchParams(rawHash)
    const initData = params.get('tgWebAppData') || ''
    return {
      initData,
      user: parseUserFromInitData(initData),
    }
  } catch {
    return { initData: '', user: null }
  }
}

function parseVkLaunchParams() {
  try {
    const rawSearch = window.location.search.startsWith('?')
      ? window.location.search.slice(1)
      : window.location.search
    const params = new URLSearchParams(rawSearch)
    const hasVkLaunchParams = [...params.keys()].some((key) => key.startsWith('vk_')) || Boolean(params.get('sign'))
    if (!hasVkLaunchParams) {
      return { raw: '', userId: 0 }
    }

    const userId = toFiniteNumber(params.get('vk_user_id'))
    return {
      raw: rawSearch,
      userId: userId > 0 ? userId : 0,
    }
  } catch {
    return { raw: '', userId: 0 }
  }
}

function readViewportValue(primaryValue, fallbackValue) {
  const primary = toFiniteNumber(primaryValue)
  if (primary > 0) return primary

  const fallback = toFiniteNumber(fallbackValue)
  if (fallback > 0) return fallback

  return 0
}

function readTelegramContext() {
  const tg = getTelegramWebApp()
  const launchParams = parseTelegramLaunchParams()
  const vkLaunchParams = parseVkLaunchParams()
  const initData = tg?.initData || launchParams.initData || ''
  const user = tg?.initDataUnsafe?.user || parseUserFromInitData(initData) || launchParams.user
  const safeAreaInset = normalizeInset(
    tg?.safeAreaInset ?? tg?.safeAreaInsets ?? tg?.safe_area_inset,
  )
  const contentSafeAreaInset = normalizeInset(
    tg?.contentSafeAreaInset ?? tg?.contentSafeAreaInsets ?? tg?.content_safe_area_inset ?? safeAreaInset,
  )
  const fallbackViewportHeight = readViewportValue(window.visualViewport?.height, window.innerHeight)
  const viewportHeight = readViewportValue(
    tg?.viewportHeight ?? tg?.viewport_height,
    fallbackViewportHeight,
  )
  const viewportStableHeight = readViewportValue(
    tg?.viewportStableHeight ?? tg?.viewport_stable_height,
    viewportHeight,
  )
  const authState = readAppAuthState()
  const isTelegramWebView = Boolean(tg || initData || user?.id)
  const launchPlatform = isTelegramWebView ? 'telegram' : (vkLaunchParams.raw ? 'vk' : 'web')
  const platformUserId = isTelegramWebView ? toFiniteNumber(user?.id) : vkLaunchParams.userId
  const appUserId = authState.launchPlatform && authState.launchPlatform !== launchPlatform
    ? 0
    : toFiniteNumber(authState.userId)
  const resolvedUserId = launchPlatform === 'vk'
    ? appUserId
    : (platformUserId || appUserId)

  return {
    tg,
    initData,
    vkLaunchParams: vkLaunchParams.raw,
    user,
    safeAreaInset,
    contentSafeAreaInset,
    viewportHeight,
    viewportStableHeight,
    platformUserId,
    appUserId,
    userId: resolvedUserId > 0 ? resolvedUserId : 0,
    launchPlatform,
    isTelegramWebView,
    isTelegramCompatibilityMode: false,
  }
}

function isSameInset(a, b) {
  return (
    a.top === b.top &&
    a.right === b.right &&
    a.bottom === b.bottom &&
    a.left === b.left
  )
}

function isSameSnapshot(a, b) {
  return (
    a.tg === b.tg &&
    a.initData === b.initData &&
    a.vkLaunchParams === b.vkLaunchParams &&
    (a.user?.id || 0) === (b.user?.id || 0) &&
    (a.user?.username || '') === (b.user?.username || '') &&
    (a.user?.photo_url || '') === (b.user?.photo_url || '') &&
    a.platformUserId === b.platformUserId &&
    a.appUserId === b.appUserId &&
    a.userId === b.userId &&
    a.launchPlatform === b.launchPlatform &&
    isSameInset(a.safeAreaInset, b.safeAreaInset) &&
    isSameInset(a.contentSafeAreaInset, b.contentSafeAreaInset) &&
    a.viewportHeight === b.viewportHeight &&
    a.viewportStableHeight === b.viewportStableHeight
  )
}

const HAPTIC_IMPACT_TYPES = new Set(['light', 'medium', 'heavy', 'rigid', 'soft'])
const HAPTIC_NOTIFICATION_TYPES = new Set(['success', 'error', 'warning'])

function triggerHaptic(tg, type = 'light') {
  const feedback = tg?.HapticFeedback
  if (!feedback) return

  try {
    if (HAPTIC_NOTIFICATION_TYPES.has(type)) {
      feedback.notificationOccurred?.(type)
      return
    }

    if (type === 'selection') {
      feedback.selectionChanged?.()
      return
    }

    feedback.impactOccurred?.(HAPTIC_IMPACT_TYPES.has(type) ? type : 'light')
  } catch {
    // Haptics must never break the main UI flow.
  }
}

export function useTelegram() {
  const [snapshot, setSnapshot] = useState(() => readTelegramContext())

  useEffect(() => {
    const syncContext = () => {
      const nextSnapshot = readTelegramContext()
      setSnapshot((currentSnapshot) => (
        isSameSnapshot(currentSnapshot, nextSnapshot) ? currentSnapshot : nextSnapshot
      ))
    }

    syncContext()

    const intervalId = window.setInterval(syncContext, 250)
    window.addEventListener(APP_AUTH_STATE_EVENT, syncContext)
    window.addEventListener('hashchange', syncContext)
    window.addEventListener('popstate', syncContext)

    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener(APP_AUTH_STATE_EVENT, syncContext)
      window.removeEventListener('hashchange', syncContext)
      window.removeEventListener('popstate', syncContext)
    }
  }, [])

  const {
    tg,
    initData,
    vkLaunchParams,
    user,
    safeAreaInset,
    contentSafeAreaInset,
    viewportHeight,
    viewportStableHeight,
    platformUserId,
    appUserId,
    userId,
    launchPlatform,
    isTelegramWebView,
    isTelegramCompatibilityMode,
  } = snapshot

  const enableVerticalSwipes = () => {
    if (typeof tg?.enableVerticalSwipes === 'function') {
      tg.enableVerticalSwipes()
      return
    }

    tg?.setSwipeBehavior?.({ allow_vertical_swipe: true })
  }

  const disableVerticalSwipes = () => {
    if (typeof tg?.disableVerticalSwipes === 'function') {
      tg.disableVerticalSwipes()
      return
    }

    tg?.setSwipeBehavior?.({ allow_vertical_swipe: false })
  }

  return {
    tg,
    user,
    userId,
    platformUserId,
    appUserId,
    launchPlatform,
    vkLaunchParams,
    isTelegramWebView,
    isTelegramCompatibilityMode,
    firstName: user?.first_name || 'Пользователь',
    lastName: user?.last_name || '',
    username: user?.username || '',
    photoUrl: user?.photo_url || null,
    initData,
    safeAreaInset,
    contentSafeAreaInset,
    viewportHeight,
    viewportStableHeight,
    ready: () => tg?.ready(),
    expand: () => tg?.expand(),
    close: () => tg?.close(),
    hideKeyboard: () => tg?.hideKeyboard?.(),
    haptic: (type = 'light') => triggerHaptic(tg, type),
    enableVerticalSwipes,
    disableVerticalSwipes,
    enableVerticalSwipe: enableVerticalSwipes,
    disableVerticalSwipe: disableVerticalSwipes,
  }
}
