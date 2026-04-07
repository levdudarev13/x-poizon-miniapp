import { useCallback, useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import StateSurface from '../../components/ui/StateSurface'
import {
  IconArrowLeft,
  IconCheck,
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStatusArrived,
  IconStatusInOrder,
  IconStatusPaid,
  IconStatusPending,
  IconStatusShipped,
} from '../../components/ui/Icons'
import ProductThumb from '../../components/ui/ProductThumb'
import { BUYER_MOTION } from '../../constants/buyerMotion'
import { formatBuyerRub } from '../../constants/buyerNumbers'
import { BUYER_STATE_COPY } from '../../constants/buyerStateContent'
import { BUYER_STATUS_META } from '../../constants/buyerStatusMeta'
import { useTelegram } from '../../hooks/useTelegram'
import { parseRepairJson, repairMojibakeDeep } from '../../utils/text'
import './MyOrders.css'

const STATUS_KEYS = ['in_order', 'paid', 'shipped', 'arrived']
const MY_ORDERS_REFRESH_INTERVAL_MS = 15000

const MY_ORDER_ICONS = {
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStatusArrived,
  IconStatusInOrder,
  IconStatusPaid,
  IconStatusPending,
  IconStatusShipped,
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

async function copyText(value) {
  const normalizedValue = String(value || '').trim()
  if (!normalizedValue) return false

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(normalizedValue)
      return true
    } catch {
      // Fallback below.
    }
  }

  try {
    const textarea = document.createElement('textarea')
    textarea.value = normalizedValue
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    textarea.style.pointerEvents = 'none'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    textarea.setSelectionRange(0, normalizedValue.length)
    const copied = document.execCommand('copy')
    document.body.removeChild(textarea)
    return copied
  } catch {
    return false
  }
}

function getOrderStatus(item) {
  if (item.arrived) return 'arrived'
  if (item.shipped) return 'shipped'
  if (item.paid) return 'paid'
  return 'in_order'
}

function getMyOrdersIcon(iconName, size = 24) {
  const Icon = MY_ORDER_ICONS[iconName]
  return Icon ? <Icon size={size} /> : null
}

function formatDateTime(dateStr) {
  if (!dateStr) return ''

  try {
    const date = new Date(dateStr)
    const months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()} г. в ${hours}:${minutes}`
  } catch {
    return ''
  }
}

function getImageUrl(calcJson) {
  if (!calcJson) return ''

  const data = parseRepairJson(calcJson)
  return data?.product?.image_url || data?.image_url || ''
}

function getDescription(calcJson) {
  if (!calcJson) return ''

  const data = parseRepairJson(calcJson)
  const product = data?.product

  if (!product) {
    return ''
  }

  const parts = []
  if (product.size) parts.push(product.size)
  if (product.color) parts.push(product.color)

  if (product.specs) {
    const specValues = Object.entries(product.specs)
      .slice(0, 3)
      .map(([key, value]) => `${key}: ${value}`)
    parts.push(...specValues)
  }

  return parts.join(' / ')
}

function StatusTracker({ status }) {
  const currentStep = Math.max(STATUS_KEYS.indexOf(status), 0)

  return (
    <div className="myord-tracker">
      {STATUS_KEYS.map((key, index) => {
        const state = BUYER_STATUS_META[key]
        const done = index <= currentStep
        const current = index === currentStep
        const toneVars = done
          ? {
              '--myord-status-color': state.color,
              '--myord-status-glow': `${state.color}4d`,
              '--myord-status-ring': `${state.color}26`,
            }
          : undefined

        return (
          <div key={key} className="myord-tracker__step">
            <div
              className={`myord-tracker__dot${done ? ' myord-tracker__dot--done' : ''}${current ? ' myord-tracker__dot--current' : ''}`}
              style={toneVars}
            >
              {done ? <IconCheck size={10} /> : null}
            </div>

            <span
              className={`myord-tracker__label${done ? ' myord-tracker__label--done' : ''}`}
              style={done ? { color: state.color } : undefined}
            >
              {state.label}
            </span>

            {index < STATUS_KEYS.length - 1 ? (
              <div
                className={`myord-tracker__line${index < currentStep ? ' myord-tracker__line--done' : ''}`}
                style={index < currentStep ? { '--myord-status-color': BUYER_STATUS_META[STATUS_KEYS[index + 1]].color } : undefined}
              />
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function OrderCard({ item, prefersReducedMotion, copiedTracking, onCopyTracking }) {
  const status = getOrderStatus(item)
  const statusMeta = BUYER_STATUS_META[status] || BUYER_STATUS_META.pending
  const price = item.subtotal_rub || item.total_with_margin_rub || 0
  const imageUrl = getImageUrl(item.calc_json)
  const description = getDescription(item.calc_json)
  const itemNumber = String(item.item_number || item.id || '').trim().replace(/^#+/, '')
  const fallbackOrderId = String(item.id).padStart(6, '0')
  const displayOrderId = itemNumber || fallbackOrderId
  const trackingNumber = String(item.tracking_number || '').trim()

  return (
    <motion.article
      className="myord-card card"
      style={{ '--myord-status-color': statusMeta.color }}
      initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
    >
      <div className="myord-card__header">
        <div className="myord-card__header-copy">
          <span className="myord-card__order-id">Заказ #{displayOrderId}</span>
          <span className="myord-card__date">{formatDateTime(item.order_added_at)}</span>
        </div>
        <span className="myord-card__total">{formatBuyerRub(price)}</span>
      </div>

      <div className="myord-card__badge-row">
        <span className="ui-pill myord-card__badge" data-tone={statusMeta.tone}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            {getMyOrdersIcon(statusMeta.iconName, 14)}
            {statusMeta.label}
          </span>
        </span>
      </div>

      <div className="myord-card__product">
        <ProductThumb
          src={imageUrl}
          alt=""
          fallbackLabel={item.short_name || item.name || 'Товар'}
          className="myord-card__thumb"
          size="md"
        />

        <div className="myord-card__product-copy">
          <p className="myord-card__product-name">{item.short_name || item.name || 'Товар'}</p>
          {description ? <p className="myord-card__product-desc">{description}</p> : null}
          <span className="myord-card__product-price">{formatBuyerRub(price)}</span>
        </div>
      </div>

      <div className="myord-card__tracker">
        <StatusTracker status={status} />
        <p className="myord-card__tracker-msg">{BUYER_STATE_COPY.myOrders.statusMessages[status]}</p>
      </div>

      <div className="myord-card__tracking">
        <span className="myord-card__tracking-label">Трек-номер СДЭК</span>
        {trackingNumber ? (
          <button
            type="button"
            className="myord-card__tracking-value myord-card__tracking-value--button pressable"
            onClick={() => onCopyTracking(item.id, trackingNumber)}
          >
            <span className="myord-card__tracking-code">{trackingNumber}</span>
            <span className="myord-card__tracking-copy">
              {copiedTracking ? 'Скопировано' : 'Нажмите, чтобы скопировать'}
            </span>
          </button>
        ) : (
          <span className="myord-card__tracking-value">Не передан</span>
        )}
      </div>
    </motion.article>
  )
}

export default function MyOrders({ onBack, active }) {
  const { userId, haptic } = useTelegram()
  const prefersReducedMotion = useReducedMotion()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [copiedTrackingId, setCopiedTrackingId] = useState(0)

  const fetchOrders = useCallback(async () => {
    if (!userId) {
      setError(null)
      setLoading(false)
      setItems([])
      return
    }

    setLoading(true)
    setError(null)

    try {
      const data = await apiFetch(`/api/cart?user_id=${userId}`)
      const orders = (data || []).filter((item) => item.order_submitted || item.paid || item.shipped || item.arrived)

      orders.sort((left, right) => {
        const leftDate = new Date(right.order_added_at || 0)
        const rightDate = new Date(left.order_added_at || 0)
        return leftDate - rightDate
      })

      setItems(orders)
      setError(null)
    } catch (err) {
      setError(err)
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    fetchOrders()
  }, [fetchOrders])

  useEffect(() => {
    if (active) {
      fetchOrders()
    }
  }, [active, fetchOrders])

  useEffect(() => {
    if (!active || !userId) return undefined

    const intervalId = window.setInterval(() => {
      fetchOrders()
    }, MY_ORDERS_REFRESH_INTERVAL_MS)

    const handleVisibilityRefresh = () => {
      if (document.visibilityState === 'visible') {
        fetchOrders()
      }
    }

    window.addEventListener('focus', fetchOrders)
    document.addEventListener('visibilitychange', handleVisibilityRefresh)

    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener('focus', fetchOrders)
      document.removeEventListener('visibilitychange', handleVisibilityRefresh)
    }
  }, [active, fetchOrders, userId])

  useEffect(() => {
    if (!copiedTrackingId) return undefined

    const timeoutId = window.setTimeout(() => {
      setCopiedTrackingId((currentValue) => (
        currentValue === copiedTrackingId ? 0 : currentValue
      ))
    }, 1600)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [copiedTrackingId])

  const handleCopyTracking = useCallback(async (itemId, trackingNumber) => {
    const copied = await copyText(trackingNumber)

    if (!copied) {
      haptic?.('error')
      return
    }

    setCopiedTrackingId(itemId)
    haptic?.('success')
  }, [haptic])

  return (
    <div className="page myord-page buyer-page buyer-page--my-orders">
      <div className="myord-header">
        <button type="button" className="myord-header__back pressable" onClick={onBack}>
          <IconArrowLeft size={20} />
        </button>

        <div className="myord-header__copy">
          <h1 className="myord-header__title">Мои заказы</h1>
          <p className="myord-header__sub">История и статусы заказов</p>
        </div>
      </div>

      <div className="page-content">
        {loading ? (
          <StateSurface
            tone="progress"
            eyebrow={BUYER_STATE_COPY.myOrders.loading.eyebrow}
            title={BUYER_STATE_COPY.myOrders.loading.title}
            body={BUYER_STATE_COPY.myOrders.loading.body}
            compact
            icon={getMyOrdersIcon(BUYER_STATE_COPY.myOrders.loading.iconName)}
          />
        ) : error ? (
          <StateSurface
            tone="error"
            eyebrow={BUYER_STATE_COPY.myOrders.fetchError.eyebrow}
            title={BUYER_STATE_COPY.myOrders.fetchError.title}
            body={BUYER_STATE_COPY.myOrders.fetchError.body}
            actionLabel={BUYER_STATE_COPY.myOrders.fetchError.actionLabel}
            onAction={fetchOrders}
            icon={getMyOrdersIcon(BUYER_STATE_COPY.myOrders.fetchError.iconName)}
          />
        ) : !items.length ? (
          <StateSurface
            eyebrow={BUYER_STATE_COPY.myOrders.empty.eyebrow}
            title={BUYER_STATE_COPY.myOrders.empty.title}
            body={BUYER_STATE_COPY.myOrders.empty.body}
            icon={getMyOrdersIcon(BUYER_STATE_COPY.myOrders.empty.iconName)}
          />
        ) : (
          <div className="myord-list">
            {items.map((item) => (
              <OrderCard
                key={item.id}
                item={item}
                prefersReducedMotion={prefersReducedMotion}
                copiedTracking={copiedTrackingId === item.id}
                onCopyTracking={handleCopyTracking}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
