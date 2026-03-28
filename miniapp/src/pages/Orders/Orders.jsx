import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { fetchDeliveryProfile } from '../../api/delivery'
import {
  IconExternalLink,
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStateSuccess,
  IconTrash,
} from '../../components/ui/Icons'
import StateSurface from '../../components/ui/StateSurface'
import { BUYER_MOTION, BUYER_PRESS_SCALE } from '../../constants/buyerMotion'
import { formatBuyerRub } from '../../constants/buyerNumbers'
import ProductThumb from '../../components/ui/ProductThumb'
import { BUYER_STATE_COPY } from '../../constants/buyerStateContent'
import { PLATFORM_COLORS, PLATFORM_NAMES } from '../../constants/platformMeta'
import { useTelegram } from '../../hooks/useTelegram'
import { parseRepairJson, repairMojibakeDeep } from '../../utils/text'
import './Orders.css'

const ORDER_STATE_ICONS = {
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStateSuccess,
}

function createInitialDeliveryStatus() {
  return {
    isComplete: null,
    deliveryData: null,
    updatedAt: '',
  }
}

function normalizeDeliveryStatus(payload = {}) {
  return {
    isComplete:
      typeof payload?.isComplete === 'boolean'
        ? payload.isComplete
        : typeof payload?.is_complete === 'boolean'
          ? payload.is_complete
          : null,
    deliveryData: payload?.delivery_data || null,
    updatedAt: String(payload?.updated_at || ''),
  }
}

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = repairMojibakeDeep(await response.json())

  if (!response.ok || data.error) {
    throw new Error(data.error || `HTTP ${response.status}`)
  }

  return data
}

function formatDate(dateStr) {
  if (!dateStr) return ''

  try {
    const date = new Date(dateStr)
    const months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
    return `${date.getDate()} ${months[date.getMonth()]}`
  } catch {
    return ''
  }
}

function pluralItems(count) {
  const last = count % 10
  const lastHundred = count % 100

  if (lastHundred >= 11 && lastHundred <= 19) return `${count} товаров`
  if (last === 1) return `${count} товар`
  if (last >= 2 && last <= 4) return `${count} товара`
  return `${count} товаров`
}

function getOrdersIcon(iconName, size = 24) {
  const Icon = ORDER_STATE_ICONS[iconName]
  return Icon ? <Icon size={size} /> : null
}

function getImageUrl(calcJson) {
  if (!calcJson) return ''

  const data = parseRepairJson(calcJson)
  return data?.product?.image_url || data?.image_url || ''
}

function ConfirmModal({ onConfirm, onCancel, loading }) {
  const prefersReducedMotion = useReducedMotion()

  return (
    <motion.div
      className="ord-modal-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={BUYER_MOTION.quick}
      onClick={onCancel}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        className="ord-modal ui-surface-panel"
        data-shell-swipe-block="true"
        initial={{ opacity: 0, scale: prefersReducedMotion ? 1 : BUYER_PRESS_SCALE, y: prefersReducedMotion ? 0 : 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: prefersReducedMotion ? 1 : BUYER_PRESS_SCALE, y: prefersReducedMotion ? 0 : 20 }}
        transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="ord-modal__icon" aria-hidden="true">
          <IconExternalLink size={30} />
        </div>

        <h2 className="ord-modal__title">Оформить заказ?</h2>
        <p className="ord-modal__text">
          После оформления с вами свяжется администратор для уточнения деталей и оплаты.
        </p>
        <p className="ord-modal__text ord-modal__text--hint">
          Статус оформленных товаров вы можете отслеживать в Профиле → Мои заказы.
        </p>

        <div className="ord-modal__actions">
          <button type="button" className="ord-modal__btn ord-modal__btn--cancel pressable" onClick={onCancel} disabled={loading}>
            Отмена
          </button>
          <button type="button" className="ord-modal__btn ord-modal__btn--confirm pressable" onClick={onConfirm} disabled={loading}>
            {loading ? <span className="ord-modal__spinner" /> : 'Оформить заказ'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}

function DeliveryBlockerModal({ onClose, onOpenDelivery }) {
  const prefersReducedMotion = useReducedMotion()

  return (
    <motion.div
      className="ord-modal-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={BUYER_MOTION.quick}
      onClick={onClose}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        className="ord-modal ord-modal--blocker ui-surface-panel"
        data-shell-swipe-block="true"
        initial={{ opacity: 0, scale: prefersReducedMotion ? 1 : BUYER_PRESS_SCALE, y: prefersReducedMotion ? 0 : 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: prefersReducedMotion ? 1 : BUYER_PRESS_SCALE, y: prefersReducedMotion ? 0 : 20 }}
        transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="ord-modal__icon ord-modal__icon--blocker" aria-hidden="true">
          <IconStateAlert size={30} />
        </div>

        <h2 className="ord-modal__title">Заполните данные для доставки</h2>
        <p className="ord-modal__text">
          Перед оформлением заказа сохраните данные для доставки в профиле.
        </p>
        <p className="ord-modal__text ord-modal__text--hint">
          Откройте Профиль → Данные для доставки. После сохранения вернитесь к заявке и нажмите кнопку ещё раз.
        </p>

        <div className="ord-modal__actions ord-modal__actions--stacked">
          <button type="button" className="ord-modal__btn ord-modal__btn--confirm pressable" onClick={onOpenDelivery}>
            Перейти
          </button>
          <button type="button" className="ord-modal__btn ord-modal__btn--cancel pressable" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}

function OrdersModalPortal({ children }) {
  if (typeof document === 'undefined') {
    return children
  }

  return createPortal(children, document.body)
}

export default function Orders({ active, onRequestOpenProfileDelivery }) {
  const { userId, haptic } = useTelegram()
  const prefersReducedMotion = useReducedMotion()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState({})
  const [showConfirm, setShowConfirm] = useState(false)
  const [showDeliveryBlocker, setShowDeliveryBlocker] = useState(false)
  const [submitSuccess, setSubmitSuccess] = useState(false)
  const [submitLoading, setSubmitLoading] = useState(false)
  const [deliveryStatus, setDeliveryStatus] = useState(() => createInitialDeliveryStatus())

  const fetchOrders = useCallback(async () => {
    if (!userId) {
      setError(null)
      setSubmitSuccess(false)
      setLoading(false)
      setItems([])
      return
    }

    setLoading(true)
    setError(null)
    setSubmitSuccess(false)

    try {
      const data = await apiFetch(`/api/cart?user_id=${userId}`)
      const orders = (data || []).filter((item) => item.in_order && !item.order_submitted && !item.paid && !item.shipped && !item.arrived)
      setItems(orders)
    } catch (err) {
      setItems([])
      setError(err.message || 'fetch-error')
    } finally {
      setLoading(false)
    }
  }, [userId])

  const refreshDeliveryStatus = useCallback(async () => {
    if (!userId) {
      const emptyStatus = createInitialDeliveryStatus()
      setDeliveryStatus(emptyStatus)
      return emptyStatus
    }

    try {
      const payload = await fetchDeliveryProfile({ userId })
      const nextStatus = normalizeDeliveryStatus(payload)
      setDeliveryStatus(nextStatus)
      return nextStatus
    } catch {
      return null
    }
  }, [userId])

  useEffect(() => {
    fetchOrders()
  }, [fetchOrders])

  useEffect(() => {
    if (active) {
      fetchOrders()
      refreshDeliveryStatus()
    }
  }, [active, fetchOrders, refreshDeliveryStatus])

  useEffect(() => {
    const blockShellSwipe = active && (showConfirm || showDeliveryBlocker)
    document.body.dataset.shellSwipeRootOrders = blockShellSwipe ? '0' : '1'

    return () => {
      document.body.dataset.shellSwipeRootOrders = '1'
    }
  }, [active, showConfirm, showDeliveryBlocker])

  useEffect(() => {
    if (!showConfirm || deliveryStatus.isComplete !== false) {
      return
    }

    setShowConfirm(false)
    setShowDeliveryBlocker(true)
  }, [deliveryStatus.isComplete, showConfirm])

  const handleDelete = async (calcId) => {
    haptic?.('medium')
    setDeleteLoading((current) => ({ ...current, [calcId]: true }))

    try {
      await apiFetch('/api/cart/set-order', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, calc_id: calcId, value: false }),
      })
      setItems((current) => current.filter((item) => item.id !== calcId))
      haptic?.('success')
    } catch {
      haptic?.('error')
    } finally {
      setDeleteLoading((current) => ({ ...current, [calcId]: false }))
    }
  }

  const handleSubmitClick = useCallback(() => {
    if (!items.length) {
      return
    }

    haptic?.('medium')
    setSubmitSuccess(false)

    if (deliveryStatus.isComplete === false) {
      setShowConfirm(false)
      setShowDeliveryBlocker(true)
      return
    }

    if (deliveryStatus.isComplete === null) {
      void refreshDeliveryStatus()
    }

    setShowDeliveryBlocker(false)
    setShowConfirm(true)
  }, [deliveryStatus, haptic, items.length, refreshDeliveryStatus])

  const handleOpenDelivery = useCallback(() => {
    setShowDeliveryBlocker(false)
    setShowConfirm(false)
    haptic?.('light')
    onRequestOpenProfileDelivery?.()
  }, [haptic, onRequestOpenProfileDelivery])

  const handleConfirmSubmit = async () => {
    setSubmitLoading(true)

    try {
      await apiFetch('/api/cart/submit-order', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId }),
      })
      setSubmitSuccess(true)
      setItems([])
      setError(null)
      setShowDeliveryBlocker(false)
      haptic?.('success')
    } catch (err) {
      if ((err.message || '') === 'delivery_data_incomplete') {
        setShowConfirm(false)
        await refreshDeliveryStatus()
        setShowDeliveryBlocker(true)
        haptic?.('error')
      } else {
        haptic?.('error')
      }
    } finally {
      setSubmitLoading(false)
      setShowConfirm(false)
    }
  }

  const total = items.reduce((sum, item) => sum + (item.subtotal_rub || item.total_with_margin_rub || 0), 0)
  const deliveryCueVisible = deliveryStatus.isComplete === false

  return (
    <div className="page orders-page buyer-page buyer-page--orders">
      <div className="page-header">
        <h1>Заявки</h1>
        <p className="ord-overview text-secondary">{pluralItems(items.length)}</p>
      </div>

      {loading ? (
        <div className="page-content ord-page__state">
          <StateSurface
            tone="progress"
            eyebrow={BUYER_STATE_COPY.orders.loading.eyebrow}
            title={BUYER_STATE_COPY.orders.loading.title}
            body={BUYER_STATE_COPY.orders.loading.body}
            compact
            icon={getOrdersIcon(BUYER_STATE_COPY.orders.loading.iconName)}
          />
        </div>
      ) : error ? (
        <div className="page-content ord-page__state">
          <StateSurface
            tone="error"
            eyebrow={BUYER_STATE_COPY.orders.fetchError.eyebrow}
            title={BUYER_STATE_COPY.orders.fetchError.title}
            body={BUYER_STATE_COPY.orders.fetchError.body}
            actionLabel={BUYER_STATE_COPY.orders.fetchError.actionLabel}
            onAction={fetchOrders}
            icon={getOrdersIcon(BUYER_STATE_COPY.orders.fetchError.iconName)}
          />
        </div>
      ) : submitSuccess ? (
        <div className="page-content ord-page__state">
          <StateSurface
            tone="complete"
            eyebrow={BUYER_STATE_COPY.orders.submitSuccess.eyebrow}
            title={BUYER_STATE_COPY.orders.submitSuccess.title}
            body={BUYER_STATE_COPY.orders.submitSuccess.body}
            icon={getOrdersIcon(BUYER_STATE_COPY.orders.submitSuccess.iconName)}
          />
        </div>
      ) : !items.length ? (
        <div className="page-content ord-page__state">
          <StateSurface
            eyebrow={BUYER_STATE_COPY.orders.empty.eyebrow}
            title={BUYER_STATE_COPY.orders.empty.title}
            body={BUYER_STATE_COPY.orders.empty.body}
            icon={getOrdersIcon(BUYER_STATE_COPY.orders.empty.iconName)}
          />
        </div>
      ) : (
        <>
          <div className="page-content">
            <div className="orders-list">
              <AnimatePresence initial={false}>
                {items.map((item, index) => {
                  const platformColor = PLATFORM_COLORS[item.platform] || '#555555'
                  const platformLabel = PLATFORM_NAMES[item.platform] || item.platform || 'Товар'
                  const price = item.subtotal_rub || item.total_with_margin_rub || 0
                  const date = formatDate(item.order_added_at)
                  const imageUrl = getImageUrl(item.calc_json)
                  const isDeleting = Boolean(deleteLoading[item.id])

                  return (
                    <motion.article
                      key={item.id}
                      layout
                      className="ord-card card"
                      style={{ '--ord-platform-color': platformColor }}
                      initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, x: prefersReducedMotion ? 0 : -48 }}
                      transition={{
                        ...(prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard),
                        delay: prefersReducedMotion ? 0 : Math.min(index * 0.04, 0.2),
                      }}
                    >
                      <div className="ord-card__media">
                        <ProductThumb
                          src={imageUrl}
                          alt=""
                          fallbackLabel={platformLabel}
                          className="ord-card__thumb"
                          size="sm"
                        />
                      </div>

                      <div className="ord-card__body">
                        <p className="ord-card__name">{item.short_name || item.name || 'Товар'}</p>
                        <p className="ord-card__price">{formatBuyerRub(price)}</p>

                        <div className="ord-card__meta">
                          <span className="ui-pill ord-card__platform">{platformLabel}</span>
                          {date ? <span className="ui-pill ord-card__date">{date}</span> : null}
                        </div>
                      </div>

                      <button
                        type="button"
                        className="ord-card__delete ui-icon-button"
                        aria-label="Убрать из заявки"
                        onClick={() => handleDelete(item.id)}
                        disabled={isDeleting}
                      >
                        {isDeleting ? (
                          <span className="ord-card__delete-spinner" />
                        ) : (
                          <IconTrash size={18} />
                        )}
                      </button>
                    </motion.article>
                  )
                })}
              </AnimatePresence>
            </div>

            <div className="ord-footer-shell">
              <div className="ord-footer ui-surface-panel">
                <div className="ord-footer__info">
                  <span className="ord-footer__label">Итого</span>
                  <span className="ord-footer__sum">{formatBuyerRub(total)}</span>
                </div>

                <button
                  type="button"
                  className="ord-footer__submit pressable"
                  onClick={handleSubmitClick}
                  disabled={!items.length}
                >
                  <span className="ord-footer__submit-content">
                    <span
                      className={`ord-footer__submit-icon${deliveryCueVisible ? ' ord-footer__submit-icon--alert' : ''}`}
                      aria-hidden="true"
                    >
                      {deliveryCueVisible ? <IconStateAlert size={18} /> : <IconExternalLink size={18} />}
                    </span>
                    <span>Оформить заказ</span>
                  </span>
                </button>
              </div>
            </div>
          </div>

          <OrdersModalPortal>
            <AnimatePresence>
              {showDeliveryBlocker ? (
                <DeliveryBlockerModal
                  onClose={() => setShowDeliveryBlocker(false)}
                  onOpenDelivery={handleOpenDelivery}
                />
              ) : null}
              {showConfirm ? (
                <ConfirmModal
                  onConfirm={handleConfirmSubmit}
                  onCancel={() => setShowConfirm(false)}
                  loading={submitLoading}
                />
              ) : null}
            </AnimatePresence>
          </OrdersModalPortal>
        </>
      )}
    </div>
  )
}
