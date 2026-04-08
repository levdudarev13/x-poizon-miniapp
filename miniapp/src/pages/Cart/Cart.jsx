import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import BottomSheet from '../../components/ui/BottomSheet'
import PoizonManualChoiceHint from '../../components/ui/PoizonManualChoiceHint'
import PoizonManualVariantButton from '../../components/ui/PoizonManualVariantButton'
import {
  IconCheck,
  IconChevronDown,
  IconInfo,
  IconOrders,
  IconPackage,
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStatusArrived,
  IconStatusInOrder,
  IconStatusPaid,
  IconStatusPending,
  IconStatusShipped,
  IconTrash,
} from '../../components/ui/Icons'
import PriceBreakdown from '../../components/ui/PriceBreakdown'
import SpecsAccordion from '../../components/ui/SpecsAccordion'
import StateSurface from '../../components/ui/StateSurface'
import { BUYER_MOTION } from '../../constants/buyerMotion'
import { formatBuyerRub } from '../../constants/buyerNumbers'
import { BUYER_STATE_COPY } from '../../constants/buyerStateContent'
import { BUYER_STATUS_META } from '../../constants/buyerStatusMeta'
import { useTelegram } from '../../hooks/useTelegram'
import { proxyImageUrl } from '../../utils/media'
import {
  POIZON_MANUAL_OTHER_PLATFORM_PRICE_HELPER_TEXT,
  derivePersistedVariantSelection,
  POIZON_MANUAL_PRICE_HELPER_TEXT,
  POIZON_MANUAL_VARIANT_SELECTIONS,
  shouldAllowFallbackVariantSelection,
  shouldRequireManualPriceForSelection,
} from '../../utils/productVariants'
import { parseRepairJson, repairMojibakeDeep } from '../../utils/text'
import './Cart.css'

/* ── API ── */
async function apiFetch(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  const data = repairMojibakeDeep(await res.json())
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

function variantKey(sel) {
  return JSON.stringify(
    Object.entries(sel)
      .map(([k, v]) => [k.trim(), v.trim()])
      .filter(([k, v]) => k && v)
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : 1)),
  )
}

const CART_ICONS = {
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStatusArrived,
  IconStatusInOrder,
  IconStatusPaid,
  IconStatusPending,
  IconStatusShipped,
}

const POIZON_ACCENT_COLOR = 'var(--poizon-blue)'

function getStatus(item) {
  if (item.arrived) return 'arrived'
  if (item.shipped) return 'shipped'
  if (item.paid) return 'paid'
  if (item.in_order) return 'in_order'
  return 'pending'
}

function getCartIcon(iconName, size = 24) {
  const Icon = CART_ICONS[iconName]
  return Icon ? <Icon size={size} /> : null
}

function pluralItems(n) {
  const last = n % 10
  const last100 = n % 100
  if (last100 >= 11 && last100 <= 19) return `${n} товаров`
  if (last === 1) return `${n} товар`
  if (last >= 2 && last <= 4) return `${n} товара`
  return `${n} товаров`
}

/* ── Component ── */
export default function Cart({ active, guidePreview = null }) {
  const { userId, haptic } = useTelegram()
  const prefersReducedMotion = useReducedMotion()
  const isGuidePreview = Boolean(guidePreview)
  const [items, setItems] = useState(() => Array.isArray(guidePreview?.items) ? guidePreview.items : [])
  const [loading, setLoading] = useState(() => !isGuidePreview)
  const [error, setError] = useState(null)

  // Selection for order
  const [selected, setSelected] = useState(() => new Set(Array.isArray(guidePreview?.selectedIds) ? guidePreview.selectedIds : []))

  // Detail view
  const [detailItem, setDetailItem] = useState(null)
  const [detailData, setDetailData] = useState(null)
  const [detailError, setDetailError] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailActiveImg, setDetailActiveImg] = useState(0)
  const [detailSpecsOpen, setDetailSpecsOpen] = useState(false)
  const [detailVariantsOpen, setDetailVariantsOpen] = useState(false)
  const [detailSelVariants, setDetailSelVariants] = useState({})
  const [detailSelSize, setDetailSelSize] = useState('')
  const [detailManualPoizonVariantChoice, setDetailManualPoizonVariantChoice] = useState('')
  const [detailManualPrice, setDetailManualPrice] = useState('')
  const [detailRecalcLoading, setDetailRecalcLoading] = useState(false)
  const detailTouchX = useRef(null)
  const detailRecalcTimer = useRef(null)
  const detailSelectionResetKeyRef = useRef('')
  const detailManualPriceInputRef = useRef(null)
  const pendingDetailManualScrollRef = useRef(false)

  // Clear confirmation
  const [showClear, setShowClear] = useState(false)
  const [clearStep, setClearStep] = useState('menu')
  const [clearing, setClearing] = useState(false)

  // Action loading states
  const [actionLoading, setActionLoading] = useState({})
  const [submitting, setSubmitting] = useState(false)

  // Recently deleted (for undo)
  const [deletedItem, setDeletedItem] = useState(null)
  const undoTimerRef = useRef(null)

  const fetchCart = useCallback(async () => {
    if (isGuidePreview) {
      setItems(Array.isArray(guidePreview?.items) ? guidePreview.items : [])
      setError(null)
      setLoading(false)
      return
    }

    if (!userId) {
      setItems([])
      setError(null)
      setLoading(false)
      return
    }

    setLoading(true)

    try {
      const data = await apiFetch(`/api/cart?user_id=${userId}`)
      // Hide items that have been submitted as orders
      setItems((data || []).filter(i => !i.order_submitted && !i.paid && !i.shipped && !i.arrived))
      setError(null)
    } catch (e) {
      setItems([])
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [guidePreview, isGuidePreview, userId])

  // Initial fetch
  useEffect(() => { fetchCart() }, [fetchCart])

  // Refetch when tab becomes active
  useEffect(() => {
    if (active && !isGuidePreview) fetchCart()
  }, [active, fetchCart, isGuidePreview])

  useEffect(() => {
    if (!isGuidePreview) return

    setItems(Array.isArray(guidePreview?.items) ? guidePreview.items : [])
    setSelected(new Set(Array.isArray(guidePreview?.selectedIds) ? guidePreview.selectedIds : []))
    setError(null)
    setLoading(false)
  }, [guidePreview, isGuidePreview])

  useEffect(() => {
    const blockShellSwipe = active && (Boolean(detailItem) || showClear)
    document.body.dataset.shellSwipeRootCart = blockShellSwipe ? '0' : '1'
    return () => { document.body.dataset.shellSwipeRootCart = '1' }
  }, [active, detailItem, showClear])

  // ── Selection helpers ──

  const toggleSelect = (id) => {
    if (isGuidePreview) return
    haptic?.('light')
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Can this item be selected for order?
  const isSelectable = (item) => {
    const st = getStatus(item)
    return st === 'pending' // only pending items can be added to order
  }

  // Submit selected items to order
  const handleSubmitSelected = async () => {
    if (isGuidePreview) return
    if (selected.size === 0) return
    haptic?.('medium')
    setSubmitting(true)
    try {
      const ids = [...selected]
      for (const calcId of ids) {
        await apiFetch('/api/cart/set-order', {
          method: 'POST',
          body: JSON.stringify({ user_id: userId, calc_id: calcId, value: true }),
        })
      }
      // Update local state
      setItems(prev => prev.map(i =>
        selected.has(i.id) ? { ...i, in_order: 1 } : i
      ))
      setSelected(new Set())
      haptic?.('success')
    } catch {
      haptic?.('error')
    } finally {
      setSubmitting(false)
    }
  }

  // ── Actions ──

  const handleOpenDetail = async (item) => {
    if (isGuidePreview) return
    haptic?.('light')
    setDetailItem(item)
    setDetailLoading(true)
    setDetailData(null)
    setDetailError(false)
    setDetailActiveImg(0)
    setDetailSpecsOpen(false)
    setDetailVariantsOpen(false)
    setDetailSelVariants({})
    setDetailSelSize('')
    setDetailManualPoizonVariantChoice('')
    setDetailManualPrice('')
    detailSelectionResetKeyRef.current = ''
    try {
      const data = await apiFetch('/api/cart/item-detail', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, calc_id: item.id }),
      })
      setDetailData(data)
    } catch {
      setDetailError(true)
      haptic?.('error')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleCloseDetail = () => {
    if (isGuidePreview) return
    haptic?.('light')
    setDetailItem(null)
    setDetailData(null)
    setDetailError(false)
    setDetailSelVariants({})
    setDetailSelSize('')
    setDetailManualPoizonVariantChoice('')
    setDetailManualPrice('')
    detailSelectionResetKeyRef.current = ''
  }

  // ── Variant helpers for detail view ──
  const detailProduct = detailData?.product
  const detailVariantGroups = (detailProduct?.variants || []).filter((g) => (g.options || []).length >= 2)
  const SIZE_NAMES = ['size', 'размер', 'sz', 'taille', '尺码', '尺寸']
  const detailVariantHasSizes = (detailProduct?.variants || []).some(
    (g) => (g.options || []).length >= 2 && SIZE_NAMES.includes(g.name.toLowerCase())
  )
  const detailHasSizes = !detailVariantHasSizes && (detailProduct?.available_sizes || []).length >= 2
  const detailCanSelectStandaloneSizes = !detailHasSizes || shouldAllowFallbackVariantSelection(detailProduct)
  const detailHasVariants = detailVariantGroups.length > 0 || detailHasSizes
  const detailAllVariantsSelected = detailVariantGroups.every((group) => detailSelVariants[group.name])
  const detailAllOptionsSelected = Boolean(detailManualPoizonVariantChoice) || (
    detailAllVariantsSelected && (!detailHasSizes || !detailCanSelectStandaloneSizes || Boolean(detailSelSize))
  )
  const detailSelectedOptionsText = detailManualPoizonVariantChoice
    ? POIZON_MANUAL_VARIANT_SELECTIONS[detailManualPoizonVariantChoice]
    : [
      ...detailVariantGroups.map((group) => detailSelVariants[group.name]).filter(Boolean),
      ...(detailHasSizes && detailSelSize ? [detailSelSize] : []),
    ].join(' / ')
  const detailSavedSizeText = String(detailProduct?.size || detailItem?.size || '').trim()
  const detailSizeText = detailSelectedOptionsText || detailSavedSizeText
  const detailManualPriceRequired = Boolean(detailManualPoizonVariantChoice)
    || shouldRequireManualPriceForSelection(detailProduct, detailSelectedOptionsText)
  const detailNeedsManualPriceInput = detailAllOptionsSelected && (
    detailManualPriceRequired || Boolean(detailProduct?.price_is_starting)
  )
  const detailManualPriceHelperText = detailManualPoizonVariantChoice === 'right'
    ? POIZON_MANUAL_OTHER_PLATFORM_PRICE_HELPER_TEXT
    : POIZON_MANUAL_PRICE_HELPER_TEXT

  const detailGetFilteredEntries = useCallback(
    (groupIndex) => {
      const map = detailProduct?.variant_price_map
      const groups = detailProduct?.variants || []
      if (!map) return []
      return Object.entries(map).filter(([k]) => {
        try {
          const pairs = JSON.parse(k)
          for (let i = 0; i < groupIndex && i < groups.length; i++) {
            const gName = groups[i].name
            const sel = detailSelVariants[gName]
            if (!sel) continue
            const found = pairs.find(([g]) => g === gName)
            if (found && found[1] !== sel) return false
          }
          return true
        } catch { return false }
      })
    },
    [detailProduct, detailSelVariants],
  )

  const detailIsOptionAvailable = useCallback(
    (groupName, opt, groupIndex) => {
      const map = detailProduct?.variant_price_map
      if (!map || !Object.keys(map).length) return shouldAllowFallbackVariantSelection(detailProduct)
      const filtered = detailGetFilteredEntries(groupIndex)
      return filtered.some(([k]) => {
        try { return JSON.parse(k).some(([g, o]) => g === groupName && o === opt) }
        catch { return false }
      })
    },
    [detailGetFilteredEntries, detailProduct],
  )

  const detailGetOptionPrice = useCallback(
    (groupName, opt, groupIndex) => {
      const filtered = detailGetFilteredEntries(groupIndex)
      let min = Infinity
      for (const [k, p] of filtered) {
        try {
          if (JSON.parse(k).some(([g, o]) => g === groupName && o === opt))
            min = Math.min(min, p)
        } catch {
          // Ignore malformed variant map entries and keep scanning the valid ones.
        }
      }
      return min === Infinity ? null : min
    },
    [detailGetFilteredEntries],
  )

  const detailGetCurrentPrice = useCallback(() => {
    if (!detailProduct) return null
    if (detailManualPriceRequired || detailProduct.price_is_starting) {
      const parsedManualPrice = Number.parseFloat(String(detailManualPrice).replace(',', '.'))
      return Number.isFinite(parsedManualPrice) && parsedManualPrice > 0 ? parsedManualPrice : null
    }
    const map = detailProduct.variant_price_map
    const groups = detailProduct.variants || []
    if (map && Object.keys(map).length && Object.keys(detailSelVariants).length) {
      const p = map[variantKey(detailSelVariants)]
      if (p != null) return p
      const filtered = Object.entries(map).filter(([k]) => {
        try {
          const pairs = JSON.parse(k)
          for (let i = 0; i < groups.length; i++) {
            const gN = groups[i].name
            const sv = detailSelVariants[gN]
            if (!sv) continue
            const f = pairs.find(([gg]) => gg === gN)
            if (f && f[1] !== sv) return false
          }
          return true
        } catch { return false }
      })
      if (filtered.length) {
        let min = Infinity
        for (const [, v] of filtered) min = Math.min(min, v)
        if (min < Infinity) return min
      }
    }
    return detailProduct.price_cny
  }, [detailManualPrice, detailManualPriceRequired, detailProduct, detailSelVariants])

  const detailCurPrice = detailGetCurrentPrice()

  // Initialize variant selections when detail data loads
  useEffect(() => {
    if (!detailData?.product) return
    const restoredSelection = derivePersistedVariantSelection(detailData.product)
    setDetailSelVariants(restoredSelection.selectedVariants)
    setDetailSelSize(restoredSelection.selectedSize)
    setDetailManualPoizonVariantChoice('')
    setDetailManualPrice('')
    detailSelectionResetKeyRef.current = ''
    return
    const prod = detailData.product
    const groups = (prod.variants || []).filter((g) => (g.options || []).length >= 2)
    const savedSize = prod.size || ''
    const parts = savedSize.split(' / ').map(s => s.trim()).filter(Boolean)

    // Try to match saved size parts to variant groups
    const sel = {}
    for (const g of groups) {
      const opts = (g.options || []).map(r => typeof r === 'string' ? r : r.name || String(r))
      const match = parts.find(p => opts.includes(p))
      if (match) sel[g.name] = match
    }
    setDetailSelVariants(sel)

    // Check available_sizes
    const sizeNames = ['size', 'размер', 'sz', 'taille', '尺码', '尺寸']
    const varHasSizes = groups.some(g => sizeNames.includes(g.name.toLowerCase()))
    if (!varHasSizes && (prod.available_sizes || []).length >= 2) {
      const sizeMatch = (prod.available_sizes || [])
        .map(r => typeof r === 'string' ? r : r.name || String(r))
        .find(s => parts.includes(s) || savedSize.includes(s))
      if (sizeMatch) setDetailSelSize(sizeMatch)
      else setDetailSelSize('')
    } else {
      setDetailSelSize('')
    }
  }, [detailData])

  // Auto-reset unavailable variant selections
  useEffect(() => {
    if (!detailProduct) return
    const map = detailProduct.variant_price_map
    const groups = (detailProduct.variants || []).filter((g) => (g.options || []).length >= 2)
    if (!map || !Object.keys(map).length || !groups.length) return

    let changed = false
    const next = { ...detailSelVariants }
    for (let i = 0; i < groups.length; i++) {
      const g = groups[i]
      const opts = (g.options || []).map(r => typeof r === 'string' ? r : r.name || String(r))
      if (opts.length < 2) continue
      const sel = next[g.name]
      if (!sel) continue
      const entries = Object.entries(map).filter(([k]) => {
        try {
          const pairs = JSON.parse(k)
          for (let j = 0; j < i; j++) {
            const gN = groups[j].name
            const sv = next[gN]
            if (!sv) continue
            const f = pairs.find(([gg]) => gg === gN)
            if (f && f[1] !== sv) return false
          }
          return true
        } catch { return false }
      })
      const available = entries.some(([k]) => {
        try { return JSON.parse(k).some(([gg, oo]) => gg === g.name && oo === sel) }
        catch { return false }
      })
      if (!available) {
        const first = opts.find(n =>
          entries.some(([k]) => {
            try { return JSON.parse(k).some(([gg, oo]) => gg === g.name && oo === n) }
            catch { return false }
          })
        )
        if (first) next[g.name] = first
        else delete next[g.name]
        changed = true
      }
    }
    if (changed) setDetailSelVariants(next)
  }, [detailProduct, detailSelVariants])

  useEffect(() => {
    const baselineSelection = String(detailProduct?.size || '').trim()
    const shouldTrackSelectionChanges = shouldAllowFallbackVariantSelection(detailProduct) && baselineSelection
    const selectionResetKey = shouldTrackSelectionChanges
      ? `${detailItem?.id || 'detail'}:${detailSelectedOptionsText}`
      : ''

    if (!selectionResetKey) {
      detailSelectionResetKeyRef.current = ''
      return
    }

    if (
      detailSelectionResetKeyRef.current
      && detailSelectionResetKeyRef.current !== selectionResetKey
    ) {
      pendingDetailManualScrollRef.current = false
    }

    detailSelectionResetKeyRef.current = selectionResetKey
  }, [detailItem?.id, detailProduct, detailSelectedOptionsText])

  useEffect(() => {
    if (!pendingDetailManualScrollRef.current || !detailManualPriceInputRef.current) {
      return
    }

    pendingDetailManualScrollRef.current = false
    window.requestAnimationFrame(() => {
      detailManualPriceInputRef.current?.scrollIntoView({
        behavior: prefersReducedMotion ? 'auto' : 'smooth',
        block: 'center',
        inline: 'nearest',
      })
    })
  }, [detailSelectedOptionsText, prefersReducedMotion])

  // Recalculate & auto-save when variant/size changes
  const detailItemRef = useRef(null)
  const detailDataRef = useRef(null)
  detailItemRef.current = detailItem
  detailDataRef.current = detailData

  useEffect(() => {
    const item = detailItemRef.current
    const data = detailDataRef.current
    if (!item || !data || !detailCurPrice) return
    if (detailHasVariants && !detailAllOptionsSelected) return
    // Skip if nothing actually changed
    const origPrice = data.product?.price_cny
    const origSize = data.product?.size || item.size || ''
    if (detailCurPrice === origPrice && detailSizeText === origSize) return

    clearTimeout(detailRecalcTimer.current)
    detailRecalcTimer.current = setTimeout(async () => {
      setDetailRecalcLoading(true)
      try {
        const resp = await apiFetch('/api/cart/update-variant', {
          method: 'POST',
          body: JSON.stringify({
            user_id: userId,
            calc_id: item.id,
            price_cny: detailCurPrice,
            size: detailSizeText,
          }),
        })
        setDetailData(prev => ({
          ...prev,
          breakdown: resp.breakdown,
          subtotal_rub: resp.subtotal_rub,
          exchange_rate: resp.exchange_rate,
          delivery_info: resp.delivery_info || prev?.delivery_info,
          product: { ...prev.product, price_cny: detailCurPrice, price_is_starting: false, size: detailSizeText },
        }))
        setItems(prev => prev.map(i =>
          i.id === item.id ? { ...i, size: detailSizeText, subtotal_rub: resp.subtotal_rub } : i
        ))
        setDetailItem(prev => prev ? { ...prev, size: detailSizeText } : prev)
      } catch {
        // silent
      } finally {
        setDetailRecalcLoading(false)
      }
    }, 400)

    return () => clearTimeout(detailRecalcTimer.current)
  }, [detailAllOptionsSelected, detailCurPrice, detailHasVariants, detailSizeText, userId])

  const handleToggleOrder = async (calcId, currentInOrder) => {
    if (isGuidePreview) return
    const newValue = !currentInOrder
    haptic?.('medium')
    setActionLoading(prev => ({ ...prev, [`order_${calcId}`]: true }))
    try {
      await apiFetch('/api/cart/set-order', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, calc_id: calcId, value: newValue }),
      })
      setItems(prev => prev.map(i =>
        i.id === calcId ? { ...i, in_order: newValue ? 1 : 0 } : i
      ))
      if (detailItem?.id === calcId) {
        setDetailItem(prev => prev ? { ...prev, in_order: newValue ? 1 : 0 } : prev)
      }
      haptic?.('success')
    } catch {
      haptic?.('error')
    } finally {
      setActionLoading(prev => ({ ...prev, [`order_${calcId}`]: false }))
    }
  }

  const handleDelete = async (calcId) => {
    if (isGuidePreview) return
    haptic?.('medium')
    const itemToDelete = items.find(i => i.id === calcId)
    setActionLoading(prev => ({ ...prev, [`del_${calcId}`]: true }))
    try {
      await apiFetch('/api/cart/remove', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, calc_id: calcId }),
      })
      setItems(prev => prev.filter(i => i.id !== calcId))
      setSelected(prev => { const n = new Set(prev); n.delete(calcId); return n })
      if (detailItem?.id === calcId) {
        setDetailItem(null)
        setDetailData(null)
      }
      if (undoTimerRef.current) clearTimeout(undoTimerRef.current)
      setDeletedItem(itemToDelete)
      undoTimerRef.current = setTimeout(() => setDeletedItem(null), 5000)
      haptic?.('success')
    } catch {
      haptic?.('error')
    } finally {
      setActionLoading(prev => ({ ...prev, [`del_${calcId}`]: false }))
    }
  }

  const handleRestore = async () => {
    if (isGuidePreview) return
    if (!deletedItem) return
    haptic?.('medium')
    try {
      await apiFetch('/api/cart/add', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, calc_id: deletedItem.id }),
      })
      if (undoTimerRef.current) clearTimeout(undoTimerRef.current)
      setDeletedItem(null)
      fetchCart()
      haptic?.('success')
    } catch {
      haptic?.('error')
    }
  }

  const handleClearAll = async () => {
    if (isGuidePreview) return
    haptic?.('heavy')
    setClearing(true)
    try {
      await apiFetch('/api/cart/clear', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId }),
      })
      setItems([])
      setSelected(new Set())
      setShowClear(false)
      setClearStep('menu')
      haptic?.('success')
    } catch {
      haptic?.('error')
    } finally {
      setClearing(false)
    }
  }

  const handleDeleteSingle = async (calcId) => {
    if (isGuidePreview) return
    const clearDeleteKey = `clear_del_${calcId}`
    const currentItemCount = items.length
    haptic?.('medium')
    setActionLoading(prev => ({ ...prev, [clearDeleteKey]: true }))
    try {
      await apiFetch('/api/cart/remove', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, calc_id: calcId }),
      })
      setItems(prev => prev.filter(i => i.id !== calcId))
      setSelected(prev => { const n = new Set(prev); n.delete(calcId); return n })
      if (currentItemCount <= 1) {
        setShowClear(false)
        setClearStep('menu')
      }
      haptic?.('success')
    } catch {
      haptic?.('error')
    } finally {
      setActionLoading(prev => ({ ...prev, [clearDeleteKey]: false }))
    }
  }

  // ── Computed ──
  const orderItems = items.filter(i => i.in_order)
  const selectedItems = items.filter(i => selected.has(i.id))
  const selectedTotal = selectedItems.reduce((s, i) => s + (i.subtotal_rub || i.total_with_margin_rub || 0), 0)
  const orderTotal = orderItems.reduce((s, i) => s + (i.subtotal_rub || i.total_with_margin_rub || 0), 0)
  const allTotal = items.reduce((s, i) => s + (i.subtotal_rub || i.total_with_margin_rub || 0), 0)
  const pendingItems = items.filter(i => isSelectable(i))
  const footerMode = selected.size > 0
    ? 'selected'
    : orderItems.length > 0
      ? 'order-ready'
      : 'idle'
  const footerLabel = footerMode === 'selected'
    ? `Выбрано (${selected.size})`
    : footerMode === 'order-ready'
      ? `Заявка (${orderItems.length})`
      : 'Итого'
  const footerTotal = footerMode === 'selected'
    ? selectedTotal
    : footerMode === 'order-ready'
      ? orderTotal
      : allTotal
  const footerActionText = submitting
    ? 'Отправляю...'
    : footerMode === 'selected'
      ? `В заявку (${selected.size})`
      : 'Выберите товары'
  const footerSubmitDisabled = submitting || footerMode !== 'selected'
  const displayFooterLabel = typeof guidePreview?.footerLabel === 'string'
    ? guidePreview.footerLabel
    : footerLabel
  const displayFooterActionText = submitting && !isGuidePreview
    ? footerActionText
    : footerMode === 'selected'
      ? (guidePreview?.footerActionText || footerActionText)
      : footerActionText
  const displayFooterSubmitDisabled = isGuidePreview || footerSubmitDisabled
  const pageClassName = `page cart-page buyer-page buyer-page--cart${isGuidePreview ? ' cart-page--guide-preview' : ''}`
  const clearMenuDeletingId = items.find((item) => actionLoading[`clear_del_${item.id}`])?.id ?? null
  const clearMenuBusy = clearMenuDeletingId != null
  const detailStatus = detailItem ? getStatus(detailItem) : null
  const detailTitle = detailItem?.short_name || detailData?.product?.name || detailItem?.name || 'Товар'
  const detailBreakdownRows = (detailData?.breakdown || []).map((row, index) => ({
    id: `${row.label}-${index}`,
    label: row.label,
    note: index === 0 ? row.note : null,
    amount: formatBuyerRub(row.amount_rub),
  }))
  const detailShouldHidePriceBreakdown = detailNeedsManualPriceInput && !detailCurPrice
  const detailDisplayBreakdownRows = detailShouldHidePriceBreakdown ? [] : detailBreakdownRows
  const detailDisplayTotalAmount = detailShouldHidePriceBreakdown
    ? 'Уточните цену'
    : formatBuyerRub(detailData?.subtotal_rub)
  const detailDeliveryInfo = {
    standard_days: detailData?.delivery_info?.standard_days || '',
    express_days: detailData?.delivery_info?.express_days || '',
    cdek_days: detailData?.delivery_info?.cdek_days || '',
  }
  const detailSpecRows = detailData?.product?.specs
    ? Object.entries(detailData.product.specs).map(([key, value]) => ({ key, value }))
    : []
  const detailSheetBodyClassName = detailLoading || detailError
    ? 'cart-detail-sheet__body cart-detail-sheet__body--inset-state'
    : 'cart-detail-sheet__body'
  const detailSheetFooter = detailData && detailItem ? (
    <div className="cart-detail__sheet-actions">
      {detailStatus === 'pending' ? (
        <button
          className="cart-detail__action-btn cart-detail__action-btn--order pressable"
          onClick={() => handleToggleOrder(detailItem.id, false)}
          disabled={actionLoading[`order_${detailItem.id}`]}
        >
          {actionLoading[`order_${detailItem.id}`] ? (
            <span className="cart-detail__btn-spinner" />
          ) : (
            <>
              <IconOrders size={18} />
              В заявку
            </>
          )}
        </button>
      ) : detailStatus === 'in_order' ? (
        <button
          className="cart-detail__action-btn cart-detail__action-btn--remove-order pressable"
          onClick={() => handleToggleOrder(detailItem.id, true)}
          disabled={actionLoading[`order_${detailItem.id}`]}
        >
          {actionLoading[`order_${detailItem.id}`] ? (
            <span className="cart-detail__btn-spinner" />
          ) : (
            <>
              <IconCheck size={18} />
              Убрать из заявки
            </>
          )}
        </button>
      ) : null}

      <button
        className="cart-detail__action-btn cart-detail__action-btn--delete pressable"
        onClick={() => handleDelete(detailItem.id)}
        disabled={actionLoading[`del_${detailItem.id}`]}
      >
        {actionLoading[`del_${detailItem.id}`] ? (
          <span className="cart-detail__btn-spinner" />
        ) : (
          <IconTrash size={18} />
        )}
      </button>
    </div>
  ) : null

  // ── Loading state ──
  if (loading) {
    return (
      <div className={pageClassName}>
        <div className="page-header">
          <h1>Корзина</h1>
        </div>
        <div className="page-content">
          <div className="cart-loading">
            <StateSurface
              tone="progress"
              eyebrow={BUYER_STATE_COPY.cart.loading.eyebrow}
              title={BUYER_STATE_COPY.cart.loading.title}
              body={BUYER_STATE_COPY.cart.loading.body}
              icon={getCartIcon(BUYER_STATE_COPY.cart.loading.iconName)}
              compact
            />

            <div className="cart-skeleton">
              {[1, 2].map((i) => (
                <div key={i} className="cart-skeleton__card card">
                  <div className="cart-skeleton__img shimmer" />
                  <div className="cart-skeleton__body">
                    <div className="cart-skeleton__line shimmer" style={{ width: '70%' }} />
                    <div className="cart-skeleton__line shimmer" style={{ width: '40%' }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (error && !items.length) {
    return (
      <div className={pageClassName}>
        <div className="page-header">
          <h1>Корзина</h1>
        </div>
        <div className="page-content">
          <StateSurface
            tone="error"
            eyebrow={BUYER_STATE_COPY.cart.fetchError.eyebrow}
            title={BUYER_STATE_COPY.cart.fetchError.title}
            body={BUYER_STATE_COPY.cart.fetchError.body}
            actionLabel={BUYER_STATE_COPY.cart.fetchError.actionLabel}
            onAction={fetchCart}
            icon={getCartIcon(BUYER_STATE_COPY.cart.fetchError.iconName)}
          />
        </div>
      </div>
    )
  }

  // ── Empty state ──
  if (!items.length) {
    return (
      <div className={pageClassName}>
        <div className="page-header">
          <h1>Корзина</h1>
        </div>
        <div className="page-content">
          <StateSurface
            eyebrow={BUYER_STATE_COPY.cart.empty.eyebrow}
            title={BUYER_STATE_COPY.cart.empty.title}
            body={BUYER_STATE_COPY.cart.empty.body}
            icon={getCartIcon(BUYER_STATE_COPY.cart.empty.iconName)}
          />
        </div>
      </div>
    )
  }

  // ── Cart list view ──
  return (
    <div className={pageClassName}>
      <div className="page-header">
        <div className="cart-header-row">
          <div>
            <h1>Корзина</h1>
            <p className="text-secondary" style={{ fontSize: 14, marginTop: 4 }}>
              {pluralItems(items.length)}
              {orderItems.length > 0 && (
                <span className="cart-header__order-count"> · {orderItems.length} в заявке</span>
              )}
            </p>
          </div>
          <button
            className="cart-clear-btn pressable"
            onClick={() => { haptic?.('light'); setShowClear(true); setClearStep('menu') }}
            disabled={isGuidePreview}
          >
            <IconTrash size={18} />
          </button>
        </div>
      </div>

      <div className="page-content">
        {/* Select all pending hint */}
        {pendingItems.length > 1 && (
          <div className="cart-select-bar">
            <button
              className="cart-select-bar__btn pressable"
              onClick={() => {
                if (isGuidePreview) return
                haptic?.('light')
                const allPendingIds = pendingItems.map(i => i.id)
                const allSelected = allPendingIds.every(id => selected.has(id))
                if (allSelected) {
                  setSelected(new Set())
                } else {
                  setSelected(new Set(allPendingIds))
                }
              }}
            >
              <span className={`cart-checkbox ${pendingItems.every(i => selected.has(i.id)) ? 'cart-checkbox--checked' : ''}`}>
                {pendingItems.every(i => selected.has(i.id)) && <IconCheck size={12} />}
              </span>
              <span>Выбрать все</span>
            </button>
          </div>
        )}

        <div className="cart-list">
          <AnimatePresence>
            {items.map(item => {
              const status = getStatus(item)
              const statusMeta = BUYER_STATUS_META[status] || BUYER_STATUS_META.pending
              const price = item.subtotal_rub || item.total_with_margin_rub || 0
              const canSelect = isSelectable(item)
              const isSelected = selected.has(item.id)
              const isInOrder = status === 'in_order'

              return (
                <motion.div
                  key={item.id}
                  layout
                  initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: prefersReducedMotion ? 0 : -100 }}
                  transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
                  className={`cart-card card${isSelected ? ' cart-card--selected' : ''}${isInOrder ? ' cart-card--in-order' : ''}`}
                  data-order-guide-step-six-target={isGuidePreview && isSelected ? 'card' : undefined}
                >
                  {/* Checkbox area — only for pending items */}
                  {canSelect ? (
                    <button
                      className="cart-card__check pressable"
                      onClick={(e) => { e.stopPropagation(); toggleSelect(item.id) }}
                      disabled={isGuidePreview}
                    >
                      <span className={`cart-checkbox ${isSelected ? 'cart-checkbox--checked' : ''}`}>
                        {isSelected && <IconCheck size={18} />}
                      </span>
                    </button>
                  ) : (
                    <div className="cart-card__status-icon" aria-hidden="true">
                      <div
                        className="cart-card__status-icon-shell"
                        data-tone={statusMeta.tone}
                        style={{
                          color: statusMeta.color,
                          borderColor: `${statusMeta.color}40`,
                          background: `linear-gradient(180deg, ${statusMeta.color}1f 0%, rgba(255, 255, 255, 0.03) 100%)`,
                        }}
                      >
                        {getCartIcon(statusMeta.iconName, 18)}
                      </div>
                    </div>
                  )}

                  {/* Card body — clickable for detail */}
                  <div className="cart-card__main pressable" onClick={() => handleOpenDetail(item)}>
                    <div className="cart-card__accent" style={{ background: POIZON_ACCENT_COLOR }} />

                    <CartThumb calcJson={item.calc_json} />

                    <div className="cart-card__body">
                      <div className="cart-card__name">
                        {item.short_name || item.name || 'Товар'}
                      </div>
                      <span className="cart-card__price">{formatBuyerRub(price)}</span>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>

        <div className="cart-footer-shell">
          <div className="cart-footer ui-surface-panel">
            <div className="cart-footer__info" title={`${displayFooterLabel}: ${formatBuyerRub(footerTotal)}`}>
              <div className="cart-footer__meta">
                <span className="cart-footer__label">{displayFooterLabel}</span>
              </div>
              <span className="cart-footer__sum">{formatBuyerRub(footerTotal)}</span>
            </div>
            <button
              type="button"
              className={`cart-footer__submit cart-footer__submit--${footerMode} pressable`}
              onClick={handleSubmitSelected}
              disabled={displayFooterSubmitDisabled}
              aria-label={displayFooterActionText}
              data-order-guide-step-six-target={isGuidePreview && footerMode === 'selected' ? 'cta' : undefined}
            >
              <span className="cart-footer__submit-content">{displayFooterActionText}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Undo toast */}
      <AnimatePresence>
        {deletedItem && (
          <motion.div
            className="cart-undo-toast"
            initial={{ y: prefersReducedMotion ? 0 : 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: prefersReducedMotion ? 0 : 80, opacity: 0 }}
            transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.emphasis}
          >
            <span className="cart-undo-toast__text">Товар удалён</span>
            <button className="cart-undo-toast__btn pressable" onClick={handleRestore}>
              Вернуть
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <BottomSheet
        open={Boolean(detailItem)}
        onClose={handleCloseDetail}
        badge={null}
        title={detailTitle}
        subtitle={detailSizeText || ''}
        className="cart-detail-sheet"
        bodyClassName={detailSheetBodyClassName}
        footer={detailSheetFooter}
      >
        {detailLoading ? (
          <div className="cart-detail__state">
            <StateSurface
              tone="progress"
              compact
              eyebrow={BUYER_STATE_COPY.cart.detailLoading.eyebrow}
              title={BUYER_STATE_COPY.cart.detailLoading.title}
              body={BUYER_STATE_COPY.cart.detailLoading.body}
              icon={getCartIcon(BUYER_STATE_COPY.cart.detailLoading.iconName)}
            />
          </div>
        ) : detailError ? (
          <div className="cart-detail__state">
            <StateSurface
              tone="error"
              eyebrow={BUYER_STATE_COPY.cart.detailError.eyebrow}
              title={BUYER_STATE_COPY.cart.detailError.title}
              body={BUYER_STATE_COPY.cart.detailError.body}
              actionLabel={BUYER_STATE_COPY.cart.detailError.actionLabel}
              onAction={handleCloseDetail}
              icon={getCartIcon(BUYER_STATE_COPY.cart.detailError.iconName)}
            />
          </div>
        ) : detailData ? (
          <div className="cart-detail__content">
            {(() => {
              const imgs = [detailData.product?.image_url, ...(detailData.product?.extra_images || [])]
                .filter(Boolean)
                .map(proxyImageUrl)
              if (!imgs.length) return null
              return (
                <div className="cg">
                  <div
                    className="cg__main"
                    data-shell-swipe-block="true"
                    onTouchStart={(e) => { detailTouchX.current = e.touches[0].clientX }}
                    onTouchEnd={(e) => {
                      if (detailTouchX.current == null) return
                      const dx = e.changedTouches[0].clientX - detailTouchX.current
                      detailTouchX.current = null
                      if (Math.abs(dx) < 40) return
                      setDetailActiveImg((p) => dx < 0 ? Math.min(p + 1, imgs.length - 1) : Math.max(p - 1, 0))
                    }}
                  >
                    <img
                      src={imgs[detailActiveImg] || imgs[0]}
                      alt=""
                      className="cg__img"
                      referrerPolicy="no-referrer"
                      onError={(e) => { e.target.style.display = 'none' }}
                      draggable={false}
                    />
                  </div>
                  {imgs.length > 1 ? (
                    <div className="cg__thumbs">
                      {imgs.slice(0, 6).map((src, i) => (
                        <button
                          key={i}
                          className={`cg__thumb pressable${i === detailActiveImg ? ' active' : ''}`}
                          onClick={() => { setDetailActiveImg(i); haptic?.('light') }}
                        >
                          <img src={src} alt="" referrerPolicy="no-referrer" />
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              )
            })()}

            <div className="cart-detail__info card">
              <h2 className="cart-detail__name">{detailTitle}</h2>
              {detailSizeText ? (
                <div className="cart-detail__meta">
                  <span>{detailSizeText}</span>
                </div>
              ) : null}
              {detailData.product?.notes ? (
                <div className="cart-detail__notes">
                  <span className="cart-detail__notes-icon">💬</span>
                  <span>{detailData.product.notes}</span>
                </div>
              ) : null}
            </div>

            {detailProduct ? (
              <div className="cp-specs card">
                <button
                  className="cp-specs__toggle pressable"
                  onClick={() => { setDetailVariantsOpen((p) => !p); haptic?.('light') }}
                >
                  <div className="cp-specs__toggle-left">
                    <IconPackage size={16} />
                    <span>Варианты</span>
                  </div>
                  <span className={`cp-specs__arrow${detailVariantsOpen ? ' open' : ''}`}>
                    <IconChevronDown size={16} />
                  </span>
                </button>
                {detailVariantsOpen ? (
                  <div className="cart-detail__variants-content">
                    {detailRecalcLoading ? <div className="cart-detail__recalc-bar" /> : null}
                    {detailVariantGroups.map((group, gi) => {
                      const opts = group.options || []
                      if (opts.length < 2) return null
                      return (
                        <div key={group.name} className="cv-group">
                          <div className="cv-group__label">{group.name}</div>
                          <div className="cv-group__list">
                            {opts.map((raw) => {
                              const name = typeof raw === 'string' ? raw : raw.name || String(raw)
                              const active = detailSelVariants[group.name] === name
                              const avail = detailIsOptionAvailable(group.name, name, gi)
                              const mp = avail ? detailGetOptionPrice(group.name, name, gi) : null
                              const rate = detailData?.exchange_rate?.cny_rub

                              return (
                                <button
                                  key={name}
                                  className={`cv-chip pressable${active ? ' active' : ''}${!avail ? ' disabled' : ''}${mp != null ? ' has-price' : ''}`}
                                  disabled={!avail}
                                  onClick={() => {
                                    if (!avail) return
                                    haptic?.('light')
                                    setDetailManualPoizonVariantChoice('')
                                    setDetailManualPrice('')
                                    setDetailSelVariants((p) => {
                                      if (p[group.name] === name) {
                                        const next = { ...p }
                                        delete next[group.name]
                                        return next
                                      }

                                      return { ...p, [group.name]: name }
                                    })
                                  }}
                                >
                                  <span className="cv-chip__name">{name}</span>
                                  {avail && mp != null && rate ? (
                                    <span className="cv-chip__price">{formatBuyerRub(mp * rate)}</span>
                                  ) : !avail ? (
                                    <span className="cv-chip__price cv-chip__price--na">—</span>
                                  ) : null}
                                </button>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                    {detailHasSizes ? (
                      <div className="cv-group">
                        <div className="cv-group__label">Размер</div>
                        <div className="cv-group__list cv-group__list--sizes">
                          {(detailProduct.available_sizes || []).map((raw) => {
                            const name = typeof raw === 'string' ? raw : raw.name || String(raw)
                            return (
                              <button
                                key={name}
                                className={`cv-size pressable${detailSelSize === name ? ' active' : ''}${!detailCanSelectStandaloneSizes ? ' disabled' : ''}`}
                                aria-disabled={!detailCanSelectStandaloneSizes}
                                disabled={!detailCanSelectStandaloneSizes}
                                style={!detailCanSelectStandaloneSizes ? { opacity: 0.45, pointerEvents: 'none' } : undefined}
                                onClick={() => {
                                  if (!detailCanSelectStandaloneSizes) return
                                  haptic?.('light')
                                  setDetailManualPoizonVariantChoice('')
                                  setDetailManualPrice('')
                                  setDetailSelSize((p) => (p === name ? '' : name))
                                }}
                              >
                                {name}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ) : null}
                    <div className="cart-detail__manual-choice">
                      <PoizonManualChoiceHint className="cart-detail__manual-choice-hint" />
                      <PoizonManualVariantButton
                        activeChoice={detailManualPoizonVariantChoice}
                        onSelect={(choice) => {
                          haptic?.('light')
                          setDetailManualPrice('')
                          setDetailSelVariants({})
                          setDetailSelSize('')
                          pendingDetailManualScrollRef.current = choice !== detailManualPoizonVariantChoice
                          setDetailManualPoizonVariantChoice((currentValue) => (currentValue === choice ? '' : choice))
                        }}
                      />
                    </div>
                    {detailNeedsManualPriceInput ? (
                      <div className="cart-detail__manual-price">
                        <label className="cart-detail__manual-price-label" htmlFor="cart-detail-manual-price">
                          <span>
                            {detailProduct?.price_is_starting
                              ? 'Укажите точную цену в юанях (¥)'
                              : 'Введите цену в юанях (¥)'}, {detailManualPriceHelperText}
                          </span>
                        </label>
                        <input
                          id="cart-detail-manual-price"
                          ref={detailManualPriceInputRef}
                          className="cart-detail__manual-price-input"
                          type="number"
                          inputMode="decimal"
                          placeholder={detailProduct?.price_is_starting ? 'например 1500 для выбранного варианта' : 'например 1500'}
                          value={detailManualPrice}
                          onChange={(event) => setDetailManualPrice(event.target.value)}
                        />
                        <div className="cart-detail__manual-price-note">
                          После ввода цены расчёт в корзине обновится автоматически.
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            <PriceBreakdown
              title="Расчёт стоимости"
              rows={detailDisplayBreakdownRows}
              totalAmount={detailDisplayTotalAmount}
            />

            <div className="cart-detail__info-block card">
              {detailData.exchange_rate ? (
                <div className="cart-detail__info-row">
                  <IconInfo size={14} />
                  <span>Курс: {detailData.exchange_rate.cny_rub?.toFixed(2)} ₽/¥</span>
                </div>
              ) : null}
              {detailDeliveryInfo.standard_days ? (
                <div className="cart-detail__info-row">
                  <IconInfo size={14} />
                  <span>Обычная доставка до Москвы: {detailDeliveryInfo.standard_days}</span>
                </div>
              ) : null}
              {detailDeliveryInfo.express_days ? (
                <div className="cart-detail__info-row">
                  <IconInfo size={14} />
                  <span>Экспресс доставка до Москвы: {detailDeliveryInfo.express_days}</span>
                </div>
              ) : null}
              {detailDeliveryInfo.cdek_days ? (
                <div className="cart-detail__info-row">
                  <IconInfo size={14} />
                  <span>СДЭК по России: {detailDeliveryInfo.cdek_days}</span>
                </div>
              ) : null}
            </div>

            {detailSpecRows.length ? (
              <SpecsAccordion
                title="О товаре"
                open={detailSpecsOpen}
                onToggle={() => { setDetailSpecsOpen((p) => !p); haptic?.('light') }}
                rows={detailSpecRows}
                icon={<IconInfo size={16} />}
              />
            ) : null}
          </div>
        ) : null}
      </BottomSheet>

      <BottomSheet
        open={showClear}
        onClose={() => { setShowClear(false); setClearStep('menu') }}
        title={clearStep === 'menu' ? 'Удаление товаров' : 'Очистить корзину'}
        subtitle={clearStep === 'menu'
          ? 'Выберите товар для удаления или очистите корзину целиком.'
          : 'Подтвердите удаление всех товаров из корзины.'}
        className="cart-clear-sheet"
        bodyClassName="cart-clear-sheet__body"
      >
        {clearStep === 'menu' ? (
          <div className="cart-clear-menu">
            <div className="cart-clear-list">
              {items.map((item) => (
                <button
                  key={item.id}
                  className="cart-clear-item pressable"
                  onClick={() => handleDeleteSingle(item.id)}
                  disabled={clearMenuBusy}
                  aria-busy={actionLoading[`clear_del_${item.id}`]}
                >
                  <span className="cart-clear-item__name">{item.name || 'Товар'}</span>
                  <span className="cart-clear-item__icon" aria-hidden="true">
                    {actionLoading[`clear_del_${item.id}`] ? (
                      <span className="cart-clear-item__spinner" />
                    ) : (
                      <IconTrash size={16} />
                    )}
                  </span>
                </button>
              ))}
            </div>

            <div className="cart-clear-actions cart-clear-actions--menu">
              <button
                className="cart-clear-action cart-clear-action--danger pressable"
                onClick={() => setClearStep('confirm')}
                disabled={clearMenuBusy}
              >
                Удалить всё
              </button>
            </div>
          </div>
        ) : (
          <div className="cart-clear-confirm">
            <StateSurface
              tone="error"
              title="Удалить все товары?"
              body={`Все ${pluralItems(items.length)} будут удалены из корзины.`}
            />

            <div className="cart-clear-actions cart-clear-actions--confirm">
              <button
                className="cart-clear-action cart-clear-action--danger pressable"
                onClick={handleClearAll}
                disabled={clearing}
              >
                {clearing ? 'Удаляю...' : 'Удалить всё'}
              </button>
              <button
                className="cart-clear-action cart-clear-action--cancel pressable"
                onClick={() => setClearStep('menu')}
                disabled={clearing}
              >
                Назад
              </button>
            </div>
          </div>
        )}
      </BottomSheet>
    </div>
  )
}


function CartThumb({ calcJson }) {
  const [src, setSrc] = useState(null)

  useEffect(() => {
    if (!calcJson) return
    const data = parseRepairJson(calcJson)
    const url = data?.product?.image_url || data?.image_url
    if (url) {
      setSrc(proxyImageUrl(url))
    } else {
      setSrc(null)
    }
  }, [calcJson])

  if (!src) {
    return (
      <div
        className="cart-card__thumb"
        style={{ color: 'rgba(255, 255, 255, 0.45)', borderColor: 'rgba(var(--accent-rgb), 0.16)' }}
      >
        <IconPackage size={18} />
      </div>
    )
  }

  return (
    <img
      src={src}
      alt=""
      className="cart-card__thumb-img"
      onError={() => setSrc(null)}
    />
  )
}
