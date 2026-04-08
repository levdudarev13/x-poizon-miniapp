import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { bootstrapWithInitData } from '../../api/admin.js'
import { fetchDeliveryProfile } from '../../api/delivery'
import {
  IconExternalLink,
  IconPackage,
  IconQuestion,
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
import { useTelegram } from '../../hooks/useTelegram'
import {
  EXPRESS_DELIVERY_TYPE,
  STANDARD_DELIVERY_TYPE,
  calculateOrderItemPreview,
  getDeliverySettings,
  isMoscowDeliveryCity,
  normalizeDeliveryType,
} from '../../utils/deliveryPricing'
import { parseRepairJson, repairMojibakeDeep } from '../../utils/text'
import './Orders.css'

const ORDER_STATE_ICONS = {
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStateSuccess,
}
const ORDER_GUIDE_SEQUENCE_STAGE = {
  intro: 0,
  delivery: 1,
  deliveryCopy: 2,
  footer: 3,
  popover: 4,
}

function createInitialDeliveryStatus() {
  return {
    isComplete: null,
    deliveryData: null,
    updatedAt: '',
  }
}

function createInitialPricingState() {
  return {
    adminSettings: {},
    deliveryInfo: null,
    rateRubPerCny: 0,
  }
}

function normalizeGuidePreviewDeliveryStatus(payload = {}) {
  return {
    isComplete: typeof payload?.isComplete === 'boolean' ? payload.isComplete : true,
    deliveryData: payload?.deliveryData && typeof payload.deliveryData === 'object'
      ? payload.deliveryData
      : null,
    updatedAt: String(payload?.updatedAt || ''),
  }
}

function normalizeGuidePreviewPricingState(payload = {}) {
  return {
    adminSettings: payload?.adminSettings && typeof payload.adminSettings === 'object'
      ? payload.adminSettings
      : {},
    deliveryInfo: payload?.deliveryInfo && typeof payload.deliveryInfo === 'object'
      ? payload.deliveryInfo
      : null,
    rateRubPerCny: Number(payload?.rateRubPerCny || 0),
  }
}

function getOrderGuideFocusKind(stage = 0) {
  if (stage >= ORDER_GUIDE_SEQUENCE_STAGE.popover) return 'popover'
  if (stage >= ORDER_GUIDE_SEQUENCE_STAGE.footer) return 'footer'
  if (stage >= ORDER_GUIDE_SEQUENCE_STAGE.delivery) return 'delivery'
  return ''
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

function normalizePricingState(payload = {}) {
  return {
    adminSettings: payload?.admin_settings || {},
    deliveryInfo: payload?.delivery_info || null,
    rateRubPerCny: Number(payload?.rate?.cny_rub || 0),
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

function getOrderPreviewSeed(item) {
  const calcPayload = parseRepairJson(item?.calc_json)
  const product = calcPayload?.product || {}

  return {
    priceCny: item?.price_cny ?? product?.price_cny ?? 0,
    weightKg: item?.weight_kg ?? product?.weight_kg ?? null,
    weightEstimated: Boolean(item?.weight_estimated ?? product?.weight_estimated),
  }
}

function formatMetricValue(value, { maxFractionDigits = 2 } = {}) {
  const numeric = Number(value || 0)
  if (!Number.isFinite(numeric)) return '0'

  const hasFraction = Math.abs(numeric - Math.trunc(numeric)) > 0.001
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: hasFraction ? Math.min(2, maxFractionDigits) : 0,
    maximumFractionDigits: maxFractionDigits,
  }).format(numeric)
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

export default function Orders({
  active,
  onRequestOpenProfileDelivery,
  guidePreview = null,
  guidePreviewSequenceStage = ORDER_GUIDE_SEQUENCE_STAGE.intro,
}) {
  const { userId, initData, haptic } = useTelegram()
  const prefersReducedMotion = useReducedMotion()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState({})
  const [showConfirm, setShowConfirm] = useState(false)
  const [showDeliveryBlocker, setShowDeliveryBlocker] = useState(false)
  const [submitSuccess, setSubmitSuccess] = useState(false)
  const [submitLoading, setSubmitLoading] = useState(false)
  const [deliveryInfoOpen, setDeliveryInfoOpen] = useState(false)
  const [priceInfoOpen, setPriceInfoOpen] = useState(false)
  const [deliveryStatus, setDeliveryStatus] = useState(() => createInitialDeliveryStatus())
  const [pricingState, setPricingState] = useState(() => createInitialPricingState())
  const [deliveryType, setDeliveryType] = useState(STANDARD_DELIVERY_TYPE)
  const deliveryInfoRef = useRef(null)
  const priceInfoRef = useRef(null)
  const isGuidePreview = Boolean(guidePreview)
  const guidePreviewItems = useMemo(() => (
    isGuidePreview && Array.isArray(guidePreview?.items)
      ? guidePreview.items.slice(0, 1)
      : []
  ), [guidePreview?.items, isGuidePreview])
  const previewDeliveryStatus = useMemo(() => (
    isGuidePreview
      ? normalizeGuidePreviewDeliveryStatus(guidePreview?.deliveryStatus)
      : null
  ), [guidePreview?.deliveryStatus, isGuidePreview])
  const previewPricingState = useMemo(() => (
    isGuidePreview
      ? normalizeGuidePreviewPricingState(guidePreview?.pricingState)
      : null
  ), [guidePreview?.pricingState, isGuidePreview])
  const guidePreviewFocusKind = isGuidePreview ? getOrderGuideFocusKind(guidePreviewSequenceStage) : ''
  const resolvedItems = isGuidePreview ? guidePreviewItems : items
  const resolvedLoading = isGuidePreview ? false : loading
  const resolvedError = isGuidePreview ? null : error
  const resolvedSubmitSuccess = isGuidePreview ? false : submitSuccess
  const resolvedDeliveryStatus = isGuidePreview ? previewDeliveryStatus : deliveryStatus
  const resolvedPricingState = isGuidePreview ? previewPricingState : pricingState
  const resolvedDeliveryInfoOpen = isGuidePreview ? false : deliveryInfoOpen
  const resolvedPriceInfoOpen = isGuidePreview ? false : priceInfoOpen
  const resolvedDeliveryType = isGuidePreview
    ? (
      guidePreviewSequenceStage >= ORDER_GUIDE_SEQUENCE_STAGE.delivery
        ? EXPRESS_DELIVERY_TYPE
        : normalizeDeliveryType(guidePreview?.deliveryType)
    )
    : normalizeDeliveryType(deliveryType)

  const fetchOrders = useCallback(async () => {
    if (isGuidePreview) {
      setItems(guidePreviewItems)
      setLoading(false)
      setError(null)
      setSubmitSuccess(false)
      return guidePreviewItems
    }

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
  }, [guidePreviewItems, isGuidePreview, userId])

  const refreshDeliveryStatus = useCallback(async () => {
    if (isGuidePreview) {
      return previewDeliveryStatus
    }

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
  }, [isGuidePreview, previewDeliveryStatus, userId])

  const refreshPricingState = useCallback(async () => {
    if (isGuidePreview) {
      return previewPricingState
    }

    if (!userId) {
      const emptyState = createInitialPricingState()
      setPricingState(emptyState)
      return emptyState
    }

    try {
      const payload = await bootstrapWithInitData({ userId, initData })
      const nextState = normalizePricingState(payload)
      setPricingState(nextState)
      return nextState
    } catch {
      return null
    }
  }, [initData, isGuidePreview, previewPricingState, userId])

  useEffect(() => {
    if (!active && !isGuidePreview) {
      return
    }

    fetchOrders()
  }, [active, fetchOrders, isGuidePreview])

  useEffect(() => {
    if (active) {
      fetchOrders()
      refreshDeliveryStatus()
      refreshPricingState()
    }
  }, [active, fetchOrders, refreshDeliveryStatus, refreshPricingState])

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

  useEffect(() => {
    if (isGuidePreview) {
      return
    }

    if (active) {
      return
    }

    setDeliveryInfoOpen(false)
    setPriceInfoOpen(false)
  }, [active, isGuidePreview])

  useEffect(() => {
    if (!deliveryInfoOpen && !priceInfoOpen) {
      return undefined
    }

    const handlePointerDown = (event) => {
      if (deliveryInfoRef.current?.contains(event.target) || priceInfoRef.current?.contains(event.target)) {
        return
      }

      setDeliveryInfoOpen(false)
      setPriceInfoOpen(false)
    }

    document.addEventListener('pointerdown', handlePointerDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [deliveryInfoOpen, priceInfoOpen])

  const handleDelete = async (calcId) => {
    if (isGuidePreview) {
      return
    }

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
    if (isGuidePreview || !resolvedItems.length) {
      return
    }

    haptic?.('medium')
    setSubmitSuccess(false)

    if (resolvedDeliveryStatus.isComplete === false) {
      setShowConfirm(false)
      setShowDeliveryBlocker(true)
      return
    }

    if (resolvedDeliveryStatus.isComplete === null) {
      void refreshDeliveryStatus()
    }

    setShowDeliveryBlocker(false)
    setShowConfirm(true)
  }, [haptic, isGuidePreview, refreshDeliveryStatus, resolvedDeliveryStatus, resolvedItems.length])

  const handleOpenDelivery = useCallback(() => {
    if (isGuidePreview) {
      return
    }

    setShowDeliveryBlocker(false)
    setShowConfirm(false)
    haptic?.('light')
    onRequestOpenProfileDelivery?.()
  }, [haptic, isGuidePreview, onRequestOpenProfileDelivery])

  const handleToggleDeliveryInfo = useCallback(() => {
    if (isGuidePreview) {
      return
    }

    setDeliveryInfoOpen((current) => !current)
    setPriceInfoOpen(false)
    haptic?.('light')
  }, [haptic, isGuidePreview])

  const handleTogglePriceInfo = useCallback(() => {
    if (isGuidePreview) {
      return
    }

    setPriceInfoOpen((current) => !current)
    setDeliveryInfoOpen(false)
    haptic?.('light')
  }, [haptic, isGuidePreview])

  const handleConfirmSubmit = async () => {
    if (isGuidePreview) {
      return
    }

    setSubmitLoading(true)

    try {
      await apiFetch('/api/cart/submit-order', {
        method: 'POST',
        body: JSON.stringify({
          user_id: userId,
          delivery_type: normalizeDeliveryType(deliveryType),
        }),
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

  const normalizedDeliveryType = resolvedDeliveryType
  const deliveryCity = String(resolvedDeliveryStatus.deliveryData?.city || '').trim()
  const settings = getDeliverySettings(resolvedPricingState.adminSettings || {})
  const deliveryInfo = {
    standard_days: resolvedPricingState.deliveryInfo?.standard_days || settings.standardDays,
    express_days: resolvedPricingState.deliveryInfo?.express_days || settings.expressDays,
    cdek_days: resolvedPricingState.deliveryInfo?.cdek_days || settings.cdekDays,
  }
  const pricingReady = resolvedPricingState.rateRubPerCny > 0
  const regionalDelivery = deliveryCity ? !isMoscowDeliveryCity(deliveryCity) : false
  const activeDeliveryTitle = normalizedDeliveryType === EXPRESS_DELIVERY_TYPE ? 'Экспресс доставка' : 'Обычная доставка'
  const activeDeliveryDays = normalizedDeliveryType === EXPRESS_DELIVERY_TYPE ? deliveryInfo.express_days : deliveryInfo.standard_days
  const regionalDeliveryDays = deliveryInfo.cdek_days || 'Срок уточняется'
  const deliveryDetails = [
    'В стоимость доставки входят облицовка и страховка.',
    'Доставка оплачивается при получении.',
  ]

  const previewItems = resolvedItems.map((item) => {
    const seed = getOrderPreviewSeed(item)
    const preview = pricingReady
      ? calculateOrderItemPreview({
        priceCny: seed.priceCny,
        weightKg: seed.weightKg,
        weightEstimated: seed.weightEstimated,
        adminSettings: resolvedPricingState.adminSettings,
        rate: resolvedPricingState.rateRubPerCny,
        deliveryType: normalizedDeliveryType,
        city: deliveryCity,
      })
      : null

    return {
      item,
      seed,
      preview,
      displayPrice: preview?.subtotalRub || item.subtotal_rub || item.total_with_margin_rub || 0,
    }
  })

  const total = previewItems.reduce((sum, entry) => sum + entry.displayPrice, 0)
  const breakdownReady = pricingReady && previewItems.length > 0 && previewItems.every(({ preview }) => Boolean(preview))
  const priceBreakdownTotals = previewItems.reduce((totals, { seed, preview }) => {
    if (!preview) {
      return totals
    }

    return {
      goodsCny: totals.goodsCny + Number(seed.priceCny || 0),
      goodsRub: totals.goodsRub + Number(preview.goodsRub || 0),
      commissionRub: totals.commissionRub + Number(preview.commissionRub || 0),
      deliveryToMoscowRub: totals.deliveryToMoscowRub + Number(preview.deliveryToMoscowRub || 0),
      cdekRub: totals.cdekRub + Number(preview.cdekRub || 0),
    }
  }, {
    goodsCny: 0,
    goodsRub: 0,
    commissionRub: 0,
    deliveryToMoscowRub: 0,
    cdekRub: 0,
  })
  const totalDeliveryRub = priceBreakdownTotals.deliveryToMoscowRub + priceBreakdownTotals.cdekRub
  const goodsRateNote = breakdownReady
    ? `${formatMetricValue(priceBreakdownTotals.goodsCny)} ¥ × ${formatMetricValue(resolvedPricingState.rateRubPerCny)} ₽/¥`
    : 'Состав появится после загрузки курса.'
  const deliveryRateNote = priceBreakdownTotals.cdekRub > 0
    ? 'До Москвы + СДЭК по России'
    : normalizedDeliveryType === EXPRESS_DELIVERY_TYPE
      ? 'Экспресс до Москвы'
      : 'Обычная до Москвы'
  const deliveryCueVisible = resolvedDeliveryStatus.isComplete === false

  return (
    <div className={`page orders-page buyer-page buyer-page--orders${isGuidePreview ? ' orders-page--guide-preview' : ''}`}>
      <div className="page-header">
        <h1>Заявки</h1>
        <p className="ord-overview text-secondary">{pluralItems(resolvedItems.length)}</p>
      </div>

      {resolvedLoading ? (
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
      ) : resolvedError ? (
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
      ) : resolvedSubmitSuccess ? (
        <div className="page-content ord-page__state">
          <StateSurface
            tone="complete"
            eyebrow={BUYER_STATE_COPY.orders.submitSuccess.eyebrow}
            title={BUYER_STATE_COPY.orders.submitSuccess.title}
            body={BUYER_STATE_COPY.orders.submitSuccess.body}
            icon={getOrdersIcon(BUYER_STATE_COPY.orders.submitSuccess.iconName)}
          />
        </div>
      ) : !resolvedItems.length ? (
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
                {previewItems.map(({ item, displayPrice }, index) => {
                  const imageUrl = getImageUrl(item.calc_json)
                  const isDeleting = Boolean(deleteLoading[item.id])

                  return (
                    <motion.article
                      key={item.id}
                      layout
                      className="ord-card card"
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
                          fallbackLabel={item.short_name || item.name || 'Товар'}
                          className="ord-card__thumb"
                          size="md"
                        />
                      </div>

                      <div className="ord-card__body">
                        <p className="ord-card__name">{item.short_name || item.name || 'Товар'}</p>
                        <p className="ord-card__price">{formatBuyerRub(displayPrice)}</p>
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

            <section
              className="ord-delivery card"
              data-order-guide-step-eight-target={isGuidePreview ? 'delivery' : undefined}
            >
                  <div className="ord-delivery__primary">
                    <div className="ord-delivery__icon" aria-hidden="true">
                      <IconPackage size={22} />
                    </div>
                    <div className="ord-delivery__copy">
                      <div className="ord-delivery__title-row" ref={deliveryInfoRef}>
                        <h2 className="ord-delivery__title">{activeDeliveryTitle}</h2>
                        <>
                          <button
                            type="button"
                            className={`ord-delivery__info-button pressable${resolvedDeliveryInfoOpen ? ' ord-delivery__info-button--open' : ''}`}
                            aria-label={resolvedDeliveryInfoOpen ? 'Скрыть детали доставки' : 'Показать детали доставки'}
                            aria-expanded={resolvedDeliveryInfoOpen}
                            aria-controls="orders-delivery-details"
                            onClick={handleToggleDeliveryInfo}
                          >
                            <IconQuestion size={14} />
                          </button>
                          <AnimatePresence initial={false}>
                            {resolvedDeliveryInfoOpen ? (
                              <motion.div
                                id="orders-delivery-details"
                                className="ord-delivery__popover"
                                initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 4, scale: 0.96 }}
                                animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
                                exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 4, scale: 0.98 }}
                                transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
                              >
                                {deliveryDetails.map((note, index) => (
                                  <p key={`${note}-${index}`}>{note}</p>
                                ))}
                              </motion.div>
                            ) : null}
                          </AnimatePresence>
                        </>
                      </div>
                      <p className="ord-delivery__subtitle">{activeDeliveryDays || 'Срок уточняется'}</p>
                    </div>
                  </div>

                  <div className="ord-delivery__divider" />

                  <div className="ord-delivery__toggle-row">
                    <div className="ord-delivery__toggle-copy">
                      <span className="ord-delivery__toggle-label">Экспресс доставка</span>
                      <span className="ord-delivery__toggle-hint">{deliveryInfo.express_days || 'Срок уточняется'}</span>
                    </div>
                    <button
                      type="button"
                      className={`ord-switch pressable${normalizedDeliveryType === EXPRESS_DELIVERY_TYPE ? ' ord-switch--active' : ''}`}
                      role="switch"
                      aria-checked={normalizedDeliveryType === EXPRESS_DELIVERY_TYPE}
                      aria-label="Включить экспресс доставку"
                      onClick={() => {
                        setDeliveryType((current) => (
                          normalizeDeliveryType(current) === EXPRESS_DELIVERY_TYPE
                            ? STANDARD_DELIVERY_TYPE
                            : EXPRESS_DELIVERY_TYPE
                        ))
                        haptic?.('light')
                      }}
                    >
                      <span className="ord-switch__thumb" />
                    </button>
                  </div>

                  {regionalDelivery ? (
                    <div className="ord-delivery__route">
                      <span className="ord-delivery__route-label">СДЭК по России со скидкой до 70%</span>
                      <span className="ord-delivery__route-value">за счет корпоративного контракта в течение {regionalDeliveryDays}</span>
                    </div>
                  ) : null}

                </section>

            <div className="ord-footer-shell">
                <div
                  className="ord-footer ui-surface-panel"
                  data-order-guide-step-eight-target={isGuidePreview ? 'footer' : undefined}
                >
                  <div className="ord-footer__info">
                    <div className="ord-footer__headline" ref={priceInfoRef}>
                      <span className="ord-footer__label">Итого</span>
                      <button
                        type="button"
                        className={`ord-delivery__info-button ord-footer__info-button pressable${resolvedPriceInfoOpen ? ' ord-delivery__info-button--open ord-footer__info-button--open' : ''}${guidePreviewFocusKind === 'popover' ? ' ord-footer__info-button--guide-preview-press' : ''}`}
                        aria-label={resolvedPriceInfoOpen ? 'Скрыть состав цены' : 'Показать состав цены'}
                        aria-expanded={resolvedPriceInfoOpen}
                        aria-controls="orders-price-details"
                        onClick={handleTogglePriceInfo}
                      >
                        <IconQuestion size={14} />
                      </button>
                      <AnimatePresence initial={false}>
                        {resolvedPriceInfoOpen ? (
                          <motion.div
                            id="orders-price-details"
                            className="ord-delivery__popover ord-footer__popover"
                            data-order-guide-step-eight-target={isGuidePreview ? 'popover' : undefined}
                            initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 4, scale: 0.96 }}
                            animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
                            exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 4, scale: 0.98 }}
                            transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
                          >
                            {breakdownReady ? (
                              <div className="ord-footer__breakdown">
                                <div className="ord-footer__breakdown-row">
                                  <div className="ord-footer__breakdown-copy">
                                    <span className="ord-footer__breakdown-label">Товар</span>
                                    <span className="ord-footer__breakdown-note">{goodsRateNote}</span>
                                  </div>
                                  <span className="ord-footer__breakdown-value">{formatBuyerRub(priceBreakdownTotals.goodsRub)}</span>
                                </div>
                                <div className="ord-footer__breakdown-row">
                                  <div className="ord-footer__breakdown-copy">
                                    <span className="ord-footer__breakdown-label">Комиссия</span>
                                  </div>
                                  <span className="ord-footer__breakdown-value">{formatBuyerRub(priceBreakdownTotals.commissionRub)}</span>
                                </div>
                                <div className="ord-footer__breakdown-row">
                                  <div className="ord-footer__breakdown-copy">
                                    <span className="ord-footer__breakdown-label">Доставка</span>
                                    <span className="ord-footer__breakdown-note">{deliveryRateNote}</span>
                                  </div>
                                  <span className="ord-footer__breakdown-value">{formatBuyerRub(totalDeliveryRub)}</span>
                                </div>
                                <div className="ord-footer__breakdown-divider" />
                                <div className="ord-footer__breakdown-row ord-footer__breakdown-row--total">
                                  <div className="ord-footer__breakdown-copy">
                                    <span className="ord-footer__breakdown-label">Итого</span>
                                  </div>
                                  <span className="ord-footer__breakdown-value">{formatBuyerRub(total)}</span>
                                </div>
                              </div>
                            ) : (
                              <p>Состав цены появится после загрузки курса.</p>
                            )}
                          </motion.div>
                        ) : null}
                      </AnimatePresence>
                    </div>
                    <span className="ord-footer__sum">{formatBuyerRub(total)}</span>
                  </div>

                  <button
                    type="button"
                    className="ord-footer__submit pressable"
                    onClick={handleSubmitClick}
                    disabled={!resolvedItems.length}
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
