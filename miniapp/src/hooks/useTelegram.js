import { useEffect, useState } from 'react'

import { APP_AUTH_STATE_EVENT, readAppAuthState } from '../utils/appAuthState.js'
import { getVkViewerProfile } from '../utils/vkBridgeInit.js'

function getTelegramWebApp() {
  return window.Telegram?.WebApp ?? null
}

function readUserAgent() {
  return typeof navigator !== 'undefined' ? navigator.userAgent || '' : ''
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
    const entries = [...params.entries()]
    const hasVkLaunchParams = entries.some(([key]) => key.startsWith('vk_')) || Boolean(params.get('sign'))
    if (!hasVkLaunchParams) {
      return {
        raw: '',
        userId: 0,
        platform: '',
      }
    }

    const userId = toFiniteNumber(params.get('vk_user_id'))
    return {
      raw: rawSearch,
      userId: userId > 0 ? userId : 0,
      platform: String(params.get('vk_platform') || '').trim().toLowerCase(),
    }
  } catch {
    return {
      raw: '',
      userId: 0,
      platform: '',
    }
  }
}

function readCompatibilityOverride() {
  try {
    const params = new URLSearchParams(window.location.search)
    return params.get('tg_compat') === '1'
  } catch {
    return false
  }
}

function resolveTelegramPlatform(tg, userAgent = '') {
  const platform = typeof tg?.platform === 'string' ? tg.platform.trim().toLowerCase() : ''
  if (platform) {
    return platform
  }

  if (/iphone|ipad|ipod/i.test(userAgent)) {
    return 'ios'
  }

  if (/android/i.test(userAgent)) {
    return 'android'
  }

  return ''
}

function isTelegramUserAgent(userAgent = '') {
  return /telegram/i.test(userAgent)
}

function isTelegramCompatibilityPlatform(platform, userAgent = '') {
  return platform === 'ios' || /iphone|ipad|ipod/i.test(userAgent)
}

function readViewportValue(primaryValue, fallbackValue) {
  const primary = toFiniteNumber(primaryValue)
  if (primary > 0) return primary

  const fallback = toFiniteNumber(fallbackValue)
  if (fallback > 0) return fallback

  return 0
}

function readTelegramContext() {
  try {
    const tg = getTelegramWebApp()
    const launchParams = parseTelegramLaunchParams()
    const vkLaunchParams = parseVkLaunchParams()
    const authState = readAppAuthState()
    const userAgent = readUserAgent()
    const telegramPlatform = resolveTelegramPlatform(tg, userAgent)
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
    const isTelegramWebView = Boolean(
      tg ||
      initData ||
      user?.id ||
      isTelegramUserAgent(userAgent),
    )
    const compatibilityMode = readCompatibilityOverride() || (
      isTelegramWebView && isTelegramCompatibilityPlatform(telegramPlatform, userAgent)
    )
    const launchPlatform = isTelegramWebView ? 'telegram' : (vkLaunchParams.raw ? 'vk' : 'web')
    const platformUserId = isTelegramWebView
      ? toFiniteNumber(user?.id)
      : vkLaunchParams.userId
    const appUserId = authState.launchPlatform && authState.launchPlatform !== launchPlatform
      ? 0
      : toFiniteNumber(authState.userId)
    const resolvedUserId = launchPlatform === 'vk'
      ? appUserId
      : (appUserId || platformUserId)

    return {
      tg,
      initData,
      vkLaunchParams: vkLaunchParams.raw,
      vkPlatform: vkLaunchParams.platform,
      user,
      userAgent,
      telegramPlatform,
      platformUserId,
      appUserId,
      userId: resolvedUserId > 0 ? resolvedUserId : 0,
      launchPlatform,
      isTelegramWebView,
      compatibilityMode,
      safeAreaInset,
      contentSafeAreaInset,
      viewportHeight,
      viewportStableHeight,
    }
  } catch (error) {
    console.warn('Telegram context unavailable:', error)
    const fallbackViewportHeight = readViewportValue(window.visualViewport?.height, window.innerHeight)
    return {
      tg: null,
      initData: '',
      vkLaunchParams: '',
      vkPlatform: '',
      user: null,
      userAgent: readUserAgent(),
      telegramPlatform: '',
      platformUserId: 0,
      appUserId: 0,
      userId: 0,
      launchPlatform: 'web',
      isTelegramWebView: false,
      compatibilityMode: readCompatibilityOverride(),
      safeAreaInset: normalizeInset(),
      contentSafeAreaInset: normalizeInset(),
      viewportHeight: fallbackViewportHeight,
      viewportStableHeight: fallbackViewportHeight,
    }
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
    a.vkPlatform === b.vkPlatform &&
    a.userAgent === b.userAgent &&
    a.telegramPlatform === b.telegramPlatform &&
    a.platformUserId === b.platformUserId &&
    a.appUserId === b.appUserId &&
    a.userId === b.userId &&
    a.launchPlatform === b.launchPlatform &&
    a.isTelegramWebView === b.isTelegramWebView &&
    a.compatibilityMode === b.compatibilityMode &&
    (a.user?.id || 0) === (b.user?.id || 0) &&
    (a.user?.username || '') === (b.user?.username || '') &&
    (a.user?.photo_url || '') === (b.user?.photo_url || '') &&
    isSameInset(a.safeAreaInset, b.safeAreaInset) &&
    isSameInset(a.contentSafeAreaInset, b.contentSafeAreaInset) &&
    a.viewportHeight === b.viewportHeight &&
    a.viewportStableHeight === b.viewportStableHeight
  )
}

function isSameUserProfile(a, b) {
  return (
    (a?.id || 0) === (b?.id || 0) &&
    (a?.username || '') === (b?.username || '') &&
    (a?.first_name || '') === (b?.first_name || '') &&
    (a?.last_name || '') === (b?.last_name || '') &&
    (a?.photo_url || '') === (b?.photo_url || '')
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

function invokeTelegramMethod(tg, methodName, ...args) {
  try {
    const method = tg?.[methodName]
    if (typeof method !== 'function') {
      return undefined
    }

    return method.apply(tg, args)
  } catch (error) {
    console.warn(`Telegram WebApp method ${methodName} failed:`, error)
    return undefined
  }
}

export function useTelegram() {
  const [snapshot, setSnapshot] = useState(() => readTelegramContext())
  const [vkViewerProfile, setVkViewerProfile] = useState(null)

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

  useEffect(() => {
    if (snapshot.launchPlatform !== 'vk' || snapshot.platformUserId <= 0) {
      setVkViewerProfile(null)
      return undefined
    }

    let cancelled = false

    getVkViewerProfile()
      .then((profile) => {
        if (cancelled) {
          return
        }

        const normalizedProfile = profile && profile.id === snapshot.platformUserId
          ? profile
          : null

        setVkViewerProfile((currentProfile) => (
          isSameUserProfile(currentProfile, normalizedProfile)
            ? currentProfile
            : normalizedProfile
        ))
      })
      .catch(() => {
        if (!cancelled) {
          setVkViewerProfile(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [snapshot.launchPlatform, snapshot.platformUserId, snapshot.vkLaunchParams])

  const {
    tg,
    initData,
    vkLaunchParams,
    vkPlatform,
    user,
    userAgent,
    telegramPlatform,
    platformUserId,
    appUserId,
    userId,
    launchPlatform,
    isTelegramWebView,
    compatibilityMode,
    safeAreaInset,
    contentSafeAreaInset,
    viewportHeight,
    viewportStableHeight,
  } = snapshot

  const resolvedUser = user || (launchPlatform === 'vk' ? vkViewerProfile : null)

  const enableVerticalSwipes = () => {
    if (typeof tg?.enableVerticalSwipes === 'function') {
      invokeTelegramMethod(tg, 'enableVerticalSwipes')
      return
    }

    invokeTelegramMethod(tg, 'setSwipeBehavior', { allow_vertical_swipe: true })
  }

  const disableVerticalSwipes = () => {
    if (typeof tg?.disableVerticalSwipes === 'function') {
      invokeTelegramMethod(tg, 'disableVerticalSwipes')
      return
    }

    invokeTelegramMethod(tg, 'setSwipeBehavior', { allow_vertical_swipe: false })
  }

  return {
    tg,
    user: resolvedUser,
    userId,
    platformUserId,
    appUserId,
    launchPlatform,
    vkLaunchParams,
    vkPlatform,
    vkUserProfile: launchPlatform === 'vk' ? vkViewerProfile : null,
    firstName: resolvedUser?.first_name || 'Пользователь',
    lastName: resolvedUser?.last_name || '',
    username: resolvedUser?.username || '',
    photoUrl: resolvedUser?.photo_url || null,
    initData,
    userAgent,
    telegramPlatform,
    isTelegramWebView,
    isTelegramCompatibilityMode: compatibilityMode,
    safeAreaInset,
    contentSafeAreaInset,
    viewportHeight,
    viewportStableHeight,
    ready: () => invokeTelegramMethod(tg, 'ready'),
    expand: () => invokeTelegramMethod(tg, 'expand'),
    close: () => invokeTelegramMethod(tg, 'close'),
    hideKeyboard: () => invokeTelegramMethod(tg, 'hideKeyboard'),
    haptic: (type = 'light') => triggerHaptic(tg, type),
    enableVerticalSwipes,
    disableVerticalSwipes,
    enableVerticalSwipe: enableVerticalSwipes,
    disableVerticalSwipe: disableVerticalSwipes,
  }
}
