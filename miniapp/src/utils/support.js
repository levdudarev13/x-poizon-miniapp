export const DEFAULT_ADMIN_SUPPORT = {
  url: 'https://t.me/LogisticsXSupport',
  username: 'LogisticsXSupport',
  userId: 0,
}

export function normalizeAdminSupport(value) {
  if (typeof value === 'string') {
    const text = String(value || '').trim()
    if (!text) {
      return { ...DEFAULT_ADMIN_SUPPORT }
    }

    return {
      ...DEFAULT_ADMIN_SUPPORT,
      url: /^(https?:\/\/|tg:\/\/)/i.test(text)
        ? text
        : `https://t.me/${text.replace(/^@+/, '')}`,
    }
  }

  const candidate = value && typeof value === 'object' ? value : {}
  const rawUsername = typeof candidate.username === 'string' ? candidate.username : ''
  const username = rawUsername.trim().replace(/^@+/, '')
  const rawUrl = String(candidate.url || '').trim()
  const numericUserId = Number(candidate.userId || candidate.user_id || 0)
  const resolvedUserId = Number.isFinite(numericUserId) && numericUserId > 0
    ? numericUserId
    : DEFAULT_ADMIN_SUPPORT.userId
  const normalizedUrl = rawUrl
    ? (/^(https?:\/\/|tg:\/\/)/i.test(rawUrl) ? rawUrl : `https://t.me/${rawUrl.replace(/^@+/, '')}`)
    : (username ? `https://t.me/${username}` : (resolvedUserId > 0 ? `tg://user?id=${resolvedUserId}` : DEFAULT_ADMIN_SUPPORT.url))

  return {
    url: normalizedUrl,
    username,
    userId: resolvedUserId,
  }
}

export function openAdminSupportChat(support, { tg, haptic } = {}) {
  const target = normalizeAdminSupport(support)
  const telegramUrl = target.username
    ? `https://t.me/${target.username}`
    : (/^(https?:\/\/t\.me\/|tg:\/\/)/i.test(target.url) ? target.url : '')
  const userDeepLink = target.userId > 0 ? `tg://user?id=${target.userId}` : ''

  try {
    if (telegramUrl && typeof tg?.openTelegramLink === 'function') {
      tg.openTelegramLink(telegramUrl)
    } else if (telegramUrl && typeof tg?.openLink === 'function') {
      tg.openLink(telegramUrl)
    } else if (telegramUrl && typeof window.open === 'function') {
      window.open(telegramUrl, '_blank', 'noopener,noreferrer')
    } else if (userDeepLink) {
      window.location.href = userDeepLink
    } else if (typeof tg?.openLink === 'function') {
      tg.openLink(target.url)
    } else if (typeof window.open === 'function') {
      window.open(target.url, '_blank', 'noopener,noreferrer')
    } else {
      window.location.href = target.url
    }

    haptic?.('light')
    return true
  } catch {
    haptic?.('error')
    return false
  }
}
