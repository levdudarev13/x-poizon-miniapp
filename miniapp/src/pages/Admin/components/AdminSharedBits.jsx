import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import {
  IconAdmin,
  IconArrowLeft,
  IconCalculator,
  IconCart,
  IconExternalLink,
  IconInfo,
  IconOrders,
} from '../../../components/ui/Icons.jsx'
import { fetchAdminAvatar } from '../../../api/admin.js'
import { proxyImageUrl } from '../../../utils/media'
import {
  ADMIN_MOTION,
  DELIVERY_FIELDS,
  getAdminUserAvatarInitial,
  getCartPlatformColor,
  getDeliveryFieldRawValue,
} from '../adminShared.js'

export function AdminCartsOverview({
  items,
  actions = null,
  collapsible = false,
  defaultExpanded = true,
  showHeader = true,
  className = '',
  cardless = false,
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  useEffect(() => {
    setExpanded(defaultExpanded)
  }, [defaultExpanded])

  const isExpanded = collapsible ? expanded : true
  const overviewClassName = [
    'admin-carts__overview',
    collapsible ? 'admin-carts__overview--collapsible' : '',
    cardless ? 'admin-carts__overview--cardless' : 'card',
    className,
  ].filter(Boolean).join(' ')

  return (
    <section className={overviewClassName}>
      {showHeader && (
        <div className="admin-carts__overview-head">
          <div className="admin-carts__overview-head-row">
            <h2 className="admin-carts__overview-title">Краткая сводка</h2>
            <div className="admin-carts__overview-actions">
              {actions}
              {collapsible && (
                <button
                  type="button"
                  className="admin-carts__overview-toggle pressable"
                  onClick={() => setExpanded((current) => !current)}
                  aria-expanded={isExpanded}
                >
                  <span>{isExpanded ? 'Свернуть' : 'Развернуть'}</span>
                  <span className="admin-carts__overview-toggle-icon" aria-hidden="true">v</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      {isExpanded && (
        <div className="admin-carts__overview-grid">
          {items.map((item) => (
            <div key={item.label} className="admin-carts__overview-item">
              <span className="admin-carts__overview-label">{item.label}</span>
              <strong className="admin-carts__overview-value">{item.value}</strong>
              <span className="admin-carts__overview-sub">{item.sub}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export function AdminUserAvatar({ user, initData }) {
  const [imageSrc, setImageSrc] = useState('')

  useEffect(() => {
    if (!initData || !user?.user_id) {
      setImageSrc('')
      return
    }

    let active = true
    let objectUrl = ''

    fetchAdminAvatar({ initData, userId: user.user_id })
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setImageSrc(objectUrl)
      })
      .catch(() => {
        if (active) setImageSrc('')
      })

    return () => {
      active = false
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [initData, user?.user_id])

  if (imageSrc) {
    return (
      <span className="admin-user-avatar" aria-hidden="true">
        <img src={imageSrc} alt="" className="admin-user-avatar__img" />
      </span>
    )
  }

  return (
    <span className="admin-user-avatar admin-user-avatar--fallback" aria-hidden="true">
      {getAdminUserAvatarInitial(user)}
    </span>
  )
}

export function AdminCartThumb({ imageUrl, platform, title }) {
  const [resolvedSrc, setResolvedSrc] = useState(() => proxyImageUrl(imageUrl || ''))

  useEffect(() => {
    setResolvedSrc(proxyImageUrl(imageUrl || ''))
  }, [imageUrl])

  if (resolvedSrc) {
    return (
      <div className="admin-cart-item__thumb">
        <img
          src={resolvedSrc}
          alt={title || ''}
          className="admin-cart-item__thumb-img"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setResolvedSrc('')}
        />
      </div>
    )
  }

  return (
    <div
      className="admin-cart-item__thumb admin-cart-item__thumb--fallback"
      style={{ color: getCartPlatformColor(platform) }}
    >
      {String(title || platform || '?').slice(0, 2).toUpperCase()}
    </div>
  )
}

export function AdminSectionIcon({ type }) {
  if (type === 'orders') return <IconOrders size={22} />
  if (type === 'pricing') return <IconCalculator size={22} />
  if (type === 'carts') return <IconCart size={22} />
  return <IconAdmin size={22} />
}

export function AdminBackIcon() {
  return <IconArrowLeft size={20} />
}

export function AdminDeliveryIcon() {
  return <IconInfo size={18} />
}

export function AdminExternalLinkIcon() {
  return <IconExternalLink size={18} />
}

export function AdminCopyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="9" width="10" height="10" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M7 15H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function useAdminModalBodyLock() {
  useEffect(() => {
    if (typeof document === 'undefined') return undefined

    const { body } = document
    const previousOverflow = body.style.overflow
    const previousOverscrollBehavior = body.style.overscrollBehavior

    body.style.overflow = 'hidden'
    body.style.overscrollBehavior = 'contain'

    return () => {
      body.style.overflow = previousOverflow
      body.style.overscrollBehavior = previousOverscrollBehavior
    }
  }, [])
}

function scrollAdminInputIntoView(inputElement, behavior = 'smooth') {
  if (!(inputElement instanceof HTMLElement)) return

  const card = inputElement.closest('.admin-modal__card')
  if (!(card instanceof HTMLElement)) {
    inputElement.scrollIntoView({ block: 'center', inline: 'nearest', behavior })
    return
  }

  const cardRect = card.getBoundingClientRect()
  const inputRect = inputElement.getBoundingClientRect()
  const inputOffsetWithinCard = inputRect.top - cardRect.top + card.scrollTop
  const targetTop = Math.max(0, inputOffsetWithinCard - Math.max(96, Math.round(card.clientHeight * 0.32)))

  card.scrollTo({ top: targetTop, behavior })
  inputElement.scrollIntoView({ block: 'center', inline: 'nearest', behavior })
}

export function AdminValueDialog({
  eyebrow,
  title,
  item,
  currentLabel = 'Товар',
  fieldLabel,
  placeholder,
  submitLabel = 'Сохранить',
  value,
  error,
  saving,
  onChange,
  onClose,
  onSubmit,
}) {
  useAdminModalBodyLock()
  const focusTimeoutsRef = useRef([])

  const clearFocusTimers = useCallback(() => {
    focusTimeoutsRef.current.forEach((timerId) => window.clearTimeout(timerId))
    focusTimeoutsRef.current = []
  }, [])

  const scheduleInputVisibilitySync = useCallback((inputElement) => {
    if (!(inputElement instanceof HTMLElement)) return

    clearFocusTimers()
    scrollAdminInputIntoView(inputElement, 'auto')

    if (typeof window === 'undefined') return

    window.requestAnimationFrame(() => {
      scrollAdminInputIntoView(inputElement)
    })

    ;[90, 220].forEach((delay) => {
      const timeoutId = window.setTimeout(() => {
        scrollAdminInputIntoView(inputElement)
      }, delay)
      focusTimeoutsRef.current.push(timeoutId)
    })
  }, [clearFocusTimers])

  useEffect(() => clearFocusTimers, [clearFocusTimers])

  return (
    <motion.div
      className="admin-modal"
      data-shell-swipe-block="true"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={ADMIN_MOTION.quick}
      onClick={() => onClose()}
    >
      <motion.div
        className="admin-modal__card"
        role="dialog"
        aria-modal="true"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 18 }}
        transition={ADMIN_MOTION.standard}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="admin-modal__copy">
          <span className="admin-shell__eyebrow">{eyebrow}</span>
          <h3 className="admin-modal__title">{title}</h3>
        </div>
        <form className="admin-modal__body admin-modal__body--form" onSubmit={onSubmit}>
          <div className="admin-modal__current">
            <span className="admin-modal__current-label">{currentLabel}</span>
            <strong className="admin-modal__current-value">
              {item?.short_name || item?.name || `Товар #${item?.calc_id || '—'}`}
            </strong>
          </div>
          <label className="admin-modal__field">
            <span className="admin-modal__field-label">{fieldLabel}</span>
            <div className="admin-modal__input-wrap">
              <input
                className="admin-modal__input"
                type="text"
                value={value}
                placeholder={placeholder}
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
                enterKeyHint="done"
                onChange={(event) => onChange(event.target.value)}
                onFocus={(event) => scheduleInputVisibilitySync(event.currentTarget)}
              />
            </div>
          </label>
          {error && <span className="admin-modal__error">{error}</span>}
          <div className="admin-modal__actions">
            <button type="button" className="admin-pricing__ghost pressable" onClick={() => onClose()}>
              Отмена
            </button>
            <button type="submit" className="admin-modal__submit pressable" disabled={saving}>
              {saving ? 'Сохраняем...' : submitLabel}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  )
}

export function AdminDeliveryDialog({ user, batch, onClose, onCopyField }) {
  useAdminModalBodyLock()

  return (
    <motion.div
      className="admin-modal"
      data-shell-swipe-block="true"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={ADMIN_MOTION.quick}
      onClick={onClose}
    >
      <motion.div
        className="admin-modal__card admin-delivery__dialog"
        role="dialog"
        aria-modal="true"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 18 }}
        transition={ADMIN_MOTION.standard}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="admin-delivery__head">
          <div className="admin-modal__copy">
            <span className="admin-shell__eyebrow">Доставка</span>
            <h3 className="admin-modal__title">Адрес и контакты</h3>
          </div>
          <button type="button" className="admin-delivery__close pressable" onClick={onClose} aria-label="Закрыть">
            ×
          </button>
        </div>
        <p className="admin-delivery__intro">
          {user?.display_name || 'Клиент'} отправил эти данные вместе с заявкой. Базовый пакет доставки остается
          компактным и открывается только по запросу.
        </p>
        <div className="admin-delivery__summary">
          <div className="admin-delivery__summary-item">
            <span className="admin-modal__current-label">Статус</span>
            <strong className={batch?.deliveryComplete ? 'admin-delivery__summary-value' : 'admin-delivery__summary-value admin-delivery__summary-value--muted'}>
              {batch?.deliveryComplete ? 'Данные заполнены' : 'Нужно уточнение'}
            </strong>
          </div>
          <div className="admin-delivery__summary-item">
            <span className="admin-modal__current-label">Отправлено</span>
            <strong className="admin-delivery__summary-value">{batch?.submittedAtLabel || '—'}</strong>
          </div>
        </div>
        <div className="admin-delivery__fields">
          {DELIVERY_FIELDS.map((field) => {
            const rawValue = getDeliveryFieldRawValue(batch?.deliveryData, field.key)
            const displayValue = rawValue || 'Не заполнено'

            return (
              <div key={field.key} className="admin-delivery__field">
                <div className="admin-delivery__field-head">
                  <span className="admin-modal__field-label">{field.label}</span>
                  <button
                    type="button"
                    className="admin-delivery__field-copy pressable"
                    onClick={() => onCopyField(field)}
                    disabled={!rawValue}
                    aria-label={`Скопировать поле ${field.label}`}
                  >
                    <AdminCopyIcon />
                  </button>
                </div>
                <strong className={`admin-delivery__field-value ${rawValue ? '' : 'admin-delivery__field-value--missing'}`}>
                  {displayValue}
                </strong>
              </div>
            )
          })}
        </div>
      </motion.div>
    </motion.div>
  )
}

export function AdminModalPortal({ children }) {
  if (typeof document === 'undefined') {
    return children
  }

  return createPortal(children, document.body)
}
