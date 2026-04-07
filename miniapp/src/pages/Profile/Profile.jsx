import { useCallback, useEffect, useState } from 'react'
import { fetchViewerAvatar } from '../../api/admin.js'
import { fetchDeliveryProfile } from '../../api/delivery'
import {
  IconCheck,
  IconChevronRight,
  IconGift,
  IconStatusShipped,
  IconSupport,
} from '../../components/ui/Icons'
import BrandGemIcon from '../../components/ui/BrandGemIcon'
import { useTelegram } from '../../hooks/useTelegram'
import { DEFAULT_ADMIN_SUPPORT, normalizeAdminSupport } from '../../utils/support'
import DeliveryProfile from './DeliveryProfile'
import FaqSupport from './FaqSupport'
import MyOrders from './MyOrders'
import './Profile.css'

const MENU_ITEMS = [
  {
    id: 'orders',
    icon: <BrandGemIcon size={19} colors={['currentColor', 'currentColor', 'currentColor']} />,
    label: 'Мои заказы',
    sub: 'Отслеживайте статус заказа и посылки',
    action: 'openOrders',
  },
  {
    id: 'delivery',
    icon: <IconStatusShipped size={19} />,
    label: 'Данные для доставки',
    sub: 'Заполните и сохраните\nнеобходимые данные',
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
    icon: <IconSupport size={19} />,
    label: 'FAQ и поддержка',
    sub: 'Ответы на часто\nзадаваемые вопросы',
    action: 'openFaq',
  },
]

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
  onRequestOpenOrderGuide,
  guidePreview = null,
  guideHighlightTarget = null,
}) {
  const {
    firstName,
    lastName,
    username: viewerUsername,
    photoUrl: viewerPhotoUrl,
    userId: viewerUserId,
    initData: viewerInitData,
    haptic,
  } = useTelegram()
  const isGuidePreview = Boolean(guidePreview)
  const previewDisplayName = typeof guidePreview?.displayName === 'string'
    ? guidePreview.displayName.trim()
    : ''
  const previewUsername = typeof guidePreview?.username === 'string'
    ? guidePreview.username.replace(/^@+/, '').trim()
    : ''
  const previewPhotoUrl = typeof guidePreview?.photoUrl === 'string'
    ? guidePreview.photoUrl.trim()
    : ''
  const resolvedGuideHighlightTarget = isGuidePreview ? (guideHighlightTarget || 'delivery') : null
  const displayName = isGuidePreview
    ? (previewDisplayName || 'Buyer 101')
    : [firstName, lastName].filter(Boolean).join(' ')
  const resolvedDisplayName = displayName
  const resolvedUsername = isGuidePreview ? previewUsername : viewerUsername
  const resolvedPhotoUrl = isGuidePreview ? previewPhotoUrl : viewerPhotoUrl
  const resolvedUserId = isGuidePreview ? null : viewerUserId
  const resolvedInitData = isGuidePreview ? '' : viewerInitData
  const username = resolvedUsername
  const [view, setView] = useState('main')
  const [deliveryComplete, setDeliveryComplete] = useState(() => {
    const previewCompletion = readDeliveryCompletion(guidePreview?.deliveryComplete)
    return previewCompletion === null ? null : previewCompletion
  })
  const adminSupport = normalizeAdminSupport(supportLink)

  const handleBackToMain = () => {
    haptic?.('light')
    setView('main')
  }

  const handleDeliveryCompletionChange = useCallback((nextValue) => {
    const nextComplete = readDeliveryCompletion(nextValue)

    if (nextComplete === null) {
      return
    }

    setDeliveryComplete(nextComplete)
  }, [])

  useEffect(() => {
    if (!isGuidePreview) {
      return undefined
    }

    const previewCompletion = readDeliveryCompletion(guidePreview?.deliveryComplete)
    setDeliveryComplete(previewCompletion === null ? null : previewCompletion)
    setView('main')

    return undefined
  }, [guidePreview, isGuidePreview])

  useEffect(() => {
    const blockShellSwipe = active && (view === 'orders' || view === 'delivery' || view === 'faq')
    document.body.dataset.shellSwipeRootProfile = blockShellSwipe ? '0' : '1'

    return () => {
      document.body.dataset.shellSwipeRootProfile = '1'
    }
  }, [active, view])

  useEffect(() => {
    if (isGuidePreview) {
      return undefined
    }

    if (requestedView === 'delivery' || requestedView === 'faq') {
      setView(requestedView)
      onRequestedViewConsumed?.()
    }
  }, [isGuidePreview, onRequestedViewConsumed, requestedView])

  useEffect(() => {
    if (isGuidePreview || !active) {
      return undefined
    }

    if (!resolvedUserId) {
      setDeliveryComplete(null)
      return undefined
    }

    if (view === 'delivery') {
      return undefined
    }

    let cancelled = false

    const syncDeliveryStatus = async () => {
      try {
        const payload = await fetchDeliveryProfile({ userId: resolvedUserId })
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
  }, [active, isGuidePreview, resolvedUserId, view])

  const handleMenuClick = (item) => {
    if (isGuidePreview) {
      return
    }

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

    if (item.action === 'openFaq') {
      haptic?.('light')
      setView('faq')
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

  if (view === 'faq') {
    return (
      <FaqSupport
        active={active}
        supportLink={adminSupport}
        onBack={handleBackToMain}
        onRequestOpenOrderGuide={onRequestOpenOrderGuide}
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
                  initData={resolvedInitData}
                  userId={resolvedUserId}
                  photoUrl={resolvedPhotoUrl}
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
              const isOrdersItem = item.id === 'orders'
              const isDeliveryItem = item.id === 'delivery'
              const isSupportItem = item.id === 'support'

              return (
                <button
                  key={item.id}
                  type="button"
                  className={[
                    'profile-menu-item card pressable',
                    isPrimaryAction ? 'profile-menu-item--primary' : '',
                    isDeliveryItem ? 'profile-menu-item--delivery' : '',
                    isSupportItem ? 'profile-menu-item--support' : '',
                  ].filter(Boolean).join(' ')}
                  data-completion-state={isDeliveryItem ? deliveryCompletionState : undefined}
                  data-order-guide-step-seven-target={isGuidePreview && isDeliveryItem && resolvedGuideHighlightTarget === 'delivery' ? 'card' : undefined}
                  data-order-guide-step-nine-target={isGuidePreview && isOrdersItem && resolvedGuideHighlightTarget === 'orders' ? 'card' : undefined}
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
