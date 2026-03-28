import { useCallback, useEffect, useState } from 'react'
import { fetchViewerAvatar } from '../../api/admin.js'
import { fetchDeliveryProfile } from '../../api/delivery'
import {
  IconCheck,
  IconChevronRight,
  IconGift,
  IconPackage,
  IconShield,
  IconStatusShipped,
} from '../../components/ui/Icons'
import { useTelegram } from '../../hooks/useTelegram'
import DeliveryProfile from './DeliveryProfile'
import MyOrders from './MyOrders'
import './Profile.css'

const DEFAULT_ADMIN_SUPPORT = {
  url: 'https://t.me/getsuga0',
  username: 'getsuga0',
  userId: 1096995802,
}

const MENU_ITEMS = [
  {
    id: 'orders',
    icon: <IconPackage size={19} />,
    label: 'Мои заказы',
    sub: 'Отслеживайте статус заказа и посылки',
    action: 'openOrders',
  },
  {
    id: 'delivery',
    icon: <IconStatusShipped size={19} />,
    label: 'Данные для доставки',
    sub: 'Сохраните получателя и адрес для следующих отправок',
    action: 'openDelivery',
  },
  {
    id: 'rate',
    icon: <IconGift size={19} />,
    label: 'Курс юаня',
    sub: 'Актуальный курс CNY / RUB',
    value: '13.24 ₽',
  },
  {
    id: 'support',
    icon: <IconShield size={19} />,
    label: 'Написать админу',
    sub: 'Вопросы, предложения, помощь и поддержка',
    action: 'openAdminChat',
  },
]

function normalizeAdminSupport(value) {
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
  const username = String(candidate.username || DEFAULT_ADMIN_SUPPORT.username).trim().replace(/^@+/, '')
  const rawUrl = String(candidate.url || '').trim()
  const normalizedUrl = rawUrl
    ? (/^(https?:\/\/|tg:\/\/)/i.test(rawUrl) ? rawUrl : `https://t.me/${rawUrl.replace(/^@+/, '')}`)
    : `https://t.me/${username}`
  const numericUserId = Number(candidate.userId || candidate.user_id || DEFAULT_ADMIN_SUPPORT.userId)

  return {
    url: normalizedUrl,
    username,
    userId: Number.isFinite(numericUserId) && numericUserId > 0
      ? numericUserId
      : DEFAULT_ADMIN_SUPPORT.userId,
  }
}

function openAdminChat(support, { tg, haptic }) {
  const target = normalizeAdminSupport(support)
  const telegramUrl = target.username
    ? `https://t.me/${target.username}`
    : (/^https?:\/\/t\.me\//i.test(target.url) ? target.url : '')
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

function readDeliveryCompletion(value) {
  if (typeof value === 'boolean') {
    return value
  }

  if (value && typeof value === 'object' && typeof value.isComplete === 'boolean') {
    return value.isComplete
  }

  if (value && typeof value === 'object' && typeof value.is_complete === 'boolean') {
    return value.is_complete
  }

  return null
}

function ProfileAvatar({ initData, userId, photoUrl, displayName }) {
  const [avatarUrl, setAvatarUrl] = useState('')
  const [hasError, setHasError] = useState(false)
  const fallbackInitial = (displayName || '?').charAt(0).toUpperCase() || '?'

  useEffect(() => {
    let isMounted = true
    let objectUrl = ''

    setAvatarUrl('')
    setHasError(false)

    const loadAvatar = async () => {
      if (!initData || !userId) {
        return
      }

      try {
        const blob = await fetchViewerAvatar({ initData })

        if (!isMounted || !blob || !blob.size) {
          return
        }

        objectUrl = URL.createObjectURL(blob)
        if (isMounted) {
          setAvatarUrl(objectUrl)
        }
      } catch {
        if (isMounted) {
          setAvatarUrl('')
        }
      }
    }

    loadAvatar()

    return () => {
      isMounted = false
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [initData, userId])

  const resolvedAvatarUrl = avatarUrl || photoUrl || ''

  return (
    <div className="profile-avatar">
      {resolvedAvatarUrl && !hasError ? (
        <img
          src={resolvedAvatarUrl}
          alt=""
          className="profile-avatar__img"
          onError={() => setHasError(true)}
          referrerPolicy="no-referrer"
        />
      ) : (
        fallbackInitial
      )}
    </div>
  )
}

export default function Profile({
  active,
  supportLink = DEFAULT_ADMIN_SUPPORT,
  requestedView = null,
  onRequestedViewConsumed,
}) {
  const { firstName, lastName, username, photoUrl, userId, initData, haptic, tg } = useTelegram()
  const displayName = [firstName, lastName].filter(Boolean).join(' ')
  const [view, setView] = useState('main')
  const [deliveryComplete, setDeliveryComplete] = useState(null)
  const adminSupport = normalizeAdminSupport(supportLink)

  const handleBackToMain = () => {
    haptic?.('light')
    setView('main')
  }

  // Keep the seam tolerant while DeliveryProfile lands in parallel.
  // Either `onCompletionChange(boolean)` or `onCompletionChange({ isComplete })` is accepted.
  const handleDeliveryCompletionChange = useCallback((nextValue) => {
    const nextComplete = readDeliveryCompletion(nextValue)

    if (nextComplete === null) {
      return
    }

    setDeliveryComplete(nextComplete)
  }, [])

  useEffect(() => {
    const blockShellSwipe = active && (view === 'orders' || view === 'delivery')
    document.body.dataset.shellSwipeRootProfile = blockShellSwipe ? '0' : '1'

    return () => {
      document.body.dataset.shellSwipeRootProfile = '1'
    }
  }, [active, view])

  useEffect(() => {
    if (requestedView === 'delivery') {
      setView('delivery')
      onRequestedViewConsumed?.()
    }
  }, [onRequestedViewConsumed, requestedView])

  useEffect(() => {
    if (!active) {
      return undefined
    }

    if (!userId) {
      setDeliveryComplete(null)
      return undefined
    }

    if (view === 'delivery') {
      return undefined
    }

    let cancelled = false

    const syncDeliveryStatus = async () => {
      try {
        const payload = await fetchDeliveryProfile({ userId })
        const nextComplete = readDeliveryCompletion(payload)

        if (!cancelled && nextComplete !== null) {
          setDeliveryComplete(nextComplete)
        }
      } catch {
        // Keep the current cue state if the sync fails.
      }
    }

    syncDeliveryStatus()

    return () => {
      cancelled = true
    }
  }, [active, userId, view])

  const handleMenuClick = (item) => {
    if (item.action === 'openOrders') {
      haptic?.('light')
      setView('orders')
      return
    }

    if (item.action === 'openDelivery') {
      haptic?.('light')
      setView('delivery')
      return
    }

    if (item.action === 'openAdminChat') {
      openAdminChat(adminSupport, { tg, haptic })
    }
  }

  if (view === 'orders') {
    return <MyOrders onBack={handleBackToMain} active={active} />
  }

  if (view === 'delivery') {
    return (
      <DeliveryProfile
        active={active}
        onBack={handleBackToMain}
        onCompletionChange={handleDeliveryCompletionChange}
      />
    )
  }

  const deliveryCompletionState = deliveryComplete === true
    ? 'complete'
    : deliveryComplete === false
      ? 'pending'
      : 'idle'
  const deliveryCompletionLabel = deliveryCompletionState === 'complete'
    ? 'Данные для доставки заполнены'
    : deliveryCompletionState === 'pending'
      ? 'Данные для доставки требуют заполнения'
      : 'Данные для доставки можно добавить'

  return (
    <div className="page profile-page buyer-page buyer-page--profile">
      <div className="page-content profile-scroll">
        <div className="profile-banner ui-surface-panel">
          <div className="profile-banner__glow" />
          <div className="profile-banner__halo" />

          <div className="profile-banner__content">
            <div className="profile-banner__header">
              <span className="profile-banner__eyebrow">Профиль</span>
              <p className="profile-banner__copy">Заказы и поддержка в одном месте.</p>
            </div>

            <div className="profile-banner__sticky">
              <div className="profile-banner__inner">
                <ProfileAvatar
                  initData={initData}
                  userId={userId}
                  photoUrl={photoUrl}
                  displayName={displayName || 'Пользователь'}
                />

                <div className="profile-info">
                  <span className="profile-info__name">{displayName || 'Пользователь'}</span>
                  {username ? <span className="profile-info__username">@{username}</span> : null}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="profile-main">
          <p className="section-label">Главное</p>

          <div className="profile-menu">
            {MENU_ITEMS.filter((item) => item.id !== 'rate').map((item) => {
              const isPrimaryAction = item.id === 'orders' || item.id === 'delivery'
              const isDeliveryItem = item.id === 'delivery'

              return (
                <button
                  key={item.id}
                  type="button"
                  className={[
                    'profile-menu-item card pressable',
                    isPrimaryAction ? 'profile-menu-item--primary' : '',
                    isDeliveryItem ? 'profile-menu-item--delivery' : '',
                  ].filter(Boolean).join(' ')}
                  data-completion-state={isDeliveryItem ? deliveryCompletionState : undefined}
                  onClick={() => handleMenuClick(item)}
                >
                  <div className={`profile-menu-item__icon${isDeliveryItem ? ' profile-menu-item__icon--delivery' : ''}`}>
                    {item.icon}
                    {isDeliveryItem ? (
                      <span
                        className="profile-menu-item__icon-badge"
                        data-state={deliveryCompletionState}
                        role="img"
                        aria-label={deliveryCompletionLabel}
                      >
                        <span className="profile-menu-item__icon-badge-ring" />
                        <span className="profile-menu-item__icon-badge-core">
                          {deliveryCompletionState === 'complete' ? (
                            <IconCheck size={10} />
                          ) : (
                            <span className="profile-menu-item__icon-badge-dot" />
                          )}
                        </span>
                      </span>
                    ) : null}
                  </div>

                  <div className="profile-menu-item__text">
                    <span className="profile-menu-item__label">{item.label}</span>
                    <span className="profile-menu-item__sub">{item.sub}</span>
                  </div>

                  <span className="profile-menu-item__arrow" aria-hidden="true"><IconChevronRight /></span>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
