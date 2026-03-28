import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { fetchAdminOrders, updateAdminOrder } from '../../../api/admin.js'
import { AdminSectionShell } from './AdminSectionShell.jsx'
import {
  ADMIN_MOTION,
  formatAdminCny,
  formatAdminRub,
  getAdminMessageChatLink,
  getAdminOrderStatusMeta,
  getCartPlatformName,
  getDeliveryBadgeLabel,
  getDeliveryFieldRawValue,
  getLatestAdminDeliveryBatch,
  openAdminChat,
  openAdminExternalLink,
  pluralizeCartItems,
} from '../adminShared.js'
import {
  AdminBackIcon,
  AdminCartThumb,
  AdminCartsOverview,
  AdminDeliveryDialog,
  AdminDeliveryIcon,
  AdminExternalLinkIcon,
  AdminModalPortal,
  AdminUserAvatar,
  AdminValueDialog,
} from './AdminSharedBits.jsx'

const EMPTY_STATS = {
  users_total: 0,
  items_total: 0,
  pending_items: 0,
  submitted_items: 0,
  shipped_items: 0,
  arrived_items: 0,
  total_with_margin_rub: 0,
  latest_order_added_at_label: '—',
}

function getOrderItemKey(item) {
  return `${item.user_id}:${item.calc_id}`
}

function getDisplayItemNumber(item) {
  return String(item?.item_number || item?.calc_id || '').trim().replace(/^#+/, '')
}

function normalizeAdminVariantRows(rawVariants) {
  if (!Array.isArray(rawVariants)) return []

  return rawVariants
    .map((variant, index) => {
      if (!variant || typeof variant !== 'object') return null

      const label = String(variant.label || variant.name || `Вариант ${index + 1}`).trim()
      const value = String(variant.value || variant.option || variant.selected || '').trim()
      if (!value) return null

      return {
        label: label || `Вариант ${index + 1}`,
        value,
      }
    })
    .filter(Boolean)
}

function getOrderParameterRows(item) {
  const explicitVariants = normalizeAdminVariantRows(item?.selected_variants)
  if (explicitVariants.length) return explicitVariants

  const sizeText = String(item?.size_text || '').trim()
  return sizeText
    ? [{ label: 'Выбранный вариант', value: sizeText }]
    : []
}

function getValueDialogConfig(mode, item) {
  if (!mode || !item) return null
  const currentNumber = getDisplayItemNumber(item)
  if (mode === 'item_number') {
    return {
      eyebrow: 'Каталог',
      title: 'Номер товара',
      fieldLabel: 'Номер для товара',
      placeholder: currentNumber ? `Например, ${currentNumber}` : 'Например, 295',
    }
  }
  return {
    eyebrow: 'Логистика',
    title: 'Трек-номер',
    fieldLabel: 'Номер для клиента',
    placeholder: 'Например, CDEK-778899',
  }
}

export function AdminOrders({ initData, onBack, haptic, tg }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [payload, setPayload] = useState(null)
  const [selectedUserId, setSelectedUserId] = useState(0)
  const [updatingKey, setUpdatingKey] = useState('')
  const [notice, setNotice] = useState(null)
  const [deliveryDialogOpen, setDeliveryDialogOpen] = useState(false)
  const [listSummaryExpanded, setListSummaryExpanded] = useState(false)
  const [detailSummaryExpanded, setDetailSummaryExpanded] = useState(false)
  const [expandedActionKeys, setExpandedActionKeys] = useState({})
  const [valueDialogMode, setValueDialogMode] = useState('')
  const [valueDialogItem, setValueDialogItem] = useState(null)
  const [valueDialogDraft, setValueDialogDraft] = useState('')
  const [valueDialogError, setValueDialogError] = useState('')
  const [valueDialogSaving, setValueDialogSaving] = useState(false)

  const applyPayload = useCallback((nextPayload) => {
    setPayload(nextPayload)
    setSelectedUserId((currentUserId) => (
      nextPayload?.users?.some((user) => user.user_id === currentUserId) ? currentUserId : 0
    ))
  }, [])

  const loadOrders = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      applyPayload(await fetchAdminOrders({ initData }))
    } catch (requestError) {
      setError(requestError.message || 'Не удалось загрузить заявки.')
    } finally {
      setLoading(false)
    }
  }, [applyPayload, initData])

  useEffect(() => {
    let mounted = true
    fetchAdminOrders({ initData })
      .then((data) => {
        if (!mounted) return
        applyPayload(data)
        setError('')
      })
      .catch((requestError) => {
        if (!mounted) return
        setError(requestError.message || 'Не удалось загрузить заявки.')
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [applyPayload, initData])

  const users = payload?.users || []
  const stats = payload?.stats || EMPTY_STATS
  const selectedUser = users.find((user) => user.user_id === selectedUserId) || null
  const selectedDeliveryBatch = selectedUser ? getLatestAdminDeliveryBatch(selectedUser.items) : null
  const deliveryTone = !selectedDeliveryBatch?.hasSnapshot ? 'missing' : selectedDeliveryBatch.deliveryComplete ? 'ready' : 'warning'
  const deliveryBadgeLabel = getDeliveryBadgeLabel(selectedDeliveryBatch)
  const valueDialogConfig = getValueDialogConfig(valueDialogMode, valueDialogItem)

  useEffect(() => {
    if (!selectedUser) {
      setDeliveryDialogOpen(false)
      setDetailSummaryExpanded(false)
      setExpandedActionKeys({})
      setValueDialogMode('')
      setValueDialogItem(null)
      setValueDialogDraft('')
      setValueDialogError('')
    }
  }, [selectedUser])

  const closeValueDialog = (force = false) => {
    if (valueDialogSaving && !force) return
    setValueDialogMode('')
    setValueDialogItem(null)
    setValueDialogDraft('')
    setValueDialogError('')
  }

  const openValueDialog = (mode, item) => {
    setValueDialogMode(mode)
    setValueDialogItem(item)
    setValueDialogDraft(mode === 'item_number' ? getDisplayItemNumber(item) : String(item?.tracking_number || ''))
    setValueDialogError('')
    setDeliveryDialogOpen(false)
    haptic?.('light')
  }

  const toggleManagePanel = (item) => {
    const itemKey = getOrderItemKey(item)
    setExpandedActionKeys((current) => ({ ...current, [itemKey]: !current[itemKey] }))
    haptic?.('light')
  }

  const handleBack = () => {
    setNotice(null)
    if (valueDialogItem) {
      closeValueDialog()
      haptic?.('light')
      return
    }
    if (deliveryDialogOpen) {
      setDeliveryDialogOpen(false)
      haptic?.('light')
      return
    }
    if (selectedUser) {
      setSelectedUserId(0)
      setExpandedActionKeys({})
      haptic?.('light')
      return
    }
    onBack()
  }

  const handleOpenUser = (userId) => {
    closeValueDialog(true)
    setDeliveryDialogOpen(false)
    setListSummaryExpanded(false)
    setDetailSummaryExpanded(false)
    setExpandedActionKeys({})
    setNotice(null)
    setSelectedUserId(userId)
    haptic?.('light')
  }

  const handleOpenProduct = (url) => openAdminExternalLink(url, { tg, haptic, onError: (text) => setNotice({ type: 'error', text }) })
  const handleOpenChat = (user) => openAdminChat(user, { tg, haptic, onError: (text) => setNotice({ type: 'error', text }) })

  const handleAction = async (item, action) => {
    const actionKey = `${item.user_id}:${item.calc_id}:${action}`
    const successTextByAction = {
      mark_paid: 'Оплата отмечена.',
      remove_paid: 'Оплата снята.',
      mark_shipped: 'Статус отправки обновлен.',
      mark_arrived: 'Статус прибытия обновлен.',
      remove_order: 'Товар убран из заявки.',
    }
    setNotice(null)
    setUpdatingKey(actionKey)
    try {
      applyPayload(await updateAdminOrder({ initData, action, userId: item.user_id, calcId: item.calc_id }))
      setNotice({ type: 'success', text: successTextByAction[action] || 'Заявка обновлена.' })
      haptic?.('success')
    } catch (requestError) {
      setNotice({ type: 'error', text: requestError.message || 'Не удалось обновить заявку.' })
      haptic?.('error')
    } finally {
      setUpdatingKey('')
    }
  }

  const handleCopyToClipboard = async (text, successText) => {
    try {
      if (!navigator?.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(text)
      setNotice({ type: 'success', text: successText })
      haptic?.('success')
    } catch {
      setNotice({ type: 'error', text: 'Не удалось скопировать данные доставки.' })
      haptic?.('error')
    }
  }

  const handleCopyDeliveryField = async (field) => {
    const rawValue = getDeliveryFieldRawValue(selectedDeliveryBatch?.deliveryData, field.key)
    if (!rawValue) return
    await handleCopyToClipboard(rawValue, `Поле «${field.label}» скопировано.`)
  }

  const handleValueDialogSubmit = async (event) => {
    event.preventDefault()
    if (!valueDialogItem || !valueDialogMode) return
    const normalizedTrackingNumber = String(valueDialogDraft || '').trim()
    const normalizedItemNumber = String(valueDialogDraft || '').trim().replace(/^#+/, '')
    if (valueDialogMode === 'tracking' && !normalizedTrackingNumber) {
      setValueDialogError('Введите трек-номер, чтобы сохранить его для клиента.')
      haptic?.('error')
      return
    }
    if (valueDialogMode === 'item_number' && !normalizedItemNumber) {
      setValueDialogError('Введите номер товара, чтобы сохранить его для клиента.')
      haptic?.('error')
      return
    }
    setValueDialogError('')
    setValueDialogSaving(true)
    try {
      applyPayload(await updateAdminOrder({
        initData,
        action: valueDialogMode === 'item_number' ? 'set_item_number' : 'set_tracking',
        userId: valueDialogItem.user_id,
        calcId: valueDialogItem.calc_id,
        trackingNumber: normalizedTrackingNumber,
        itemNumber: normalizedItemNumber,
      }))
      closeValueDialog(true)
      setNotice({ type: 'success', text: valueDialogMode === 'item_number' ? 'Номер товара обновлен.' : 'Трек-номер сохранен.' })
      haptic?.('success')
    } catch (requestError) {
      setValueDialogError(requestError.message || (valueDialogMode === 'item_number' ? 'Не удалось сохранить номер товара.' : 'Не удалось сохранить трек-номер.'))
      haptic?.('error')
    } finally {
      setValueDialogSaving(false)
    }
  }

  const topbar = (
    <div className="admin-shell__topbar">
      <button
        className="admin-shell__back pressable"
        onClick={handleBack}
        aria-label={selectedUser ? 'Назад к списку заявок' : 'Назад к разделам'}
      >
        <AdminBackIcon />
      </button>
      <div className={`admin-shell__title-wrap ${selectedUser ? 'admin-shell__title-wrap--user' : ''}`}>
        {selectedUser && <AdminUserAvatar user={selectedUser} initData={initData} />}
        <div>
          <span className="admin-shell__eyebrow">{selectedUser ? 'Заявки клиента' : 'Рабочая секция'}</span>
          <h1 className="admin-shell__detail-title">{selectedUser ? selectedUser.display_name : 'Заявки'}</h1>
        </div>
      </div>
    </div>
  )

  if (loading) {
    return (
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={ADMIN_MOTION.standard}>
        <AdminSectionShell topbar={topbar} contentClassName="admin-orders__section">
          {[1, 2, 3].map((item) => (
            <div key={item} className="admin-skeleton card">
              <div className="admin-skeleton__line" style={{ width: '36%' }} />
              <div className="admin-skeleton__line" style={{ width: '60%' }} />
              <div className="admin-skeleton__line" style={{ width: '100%', height: 88, borderRadius: 18 }} />
            </div>
          ))}
        </AdminSectionShell>
      </motion.div>
    )
  }

  if (error && !payload) {
    return (
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={ADMIN_MOTION.standard}>
        <AdminSectionShell topbar={topbar}>
          <div className="admin-feedback card">
            <div className="admin-feedback__icon">!</div>
            <div className="admin-feedback__text">
              <strong>Не удалось загрузить заявки</strong>
              <span>{error}</span>
            </div>
            <button className="admin-pricing__ghost pressable" onClick={loadOrders}>Повторить</button>
          </div>
        </AdminSectionShell>
      </motion.div>
    )
  }

  const overviewItems = selectedUser ? [
    { label: 'Заявок', value: selectedUser.total_items, sub: pluralizeCartItems(selectedUser.total_items) },
    { label: 'Ожидают', value: selectedUser.pending_items, sub: selectedUser.pending_items ? 'Нужна проверка оплаты или связи' : 'Без ожидающих' },
    { label: 'В пути', value: selectedUser.shipped_items, sub: selectedUser.arrived_items ? `${selectedUser.arrived_items} доставлено` : 'Пока без доставленных' },
    { label: 'Сумма', value: formatAdminRub(selectedUser.total_with_margin_rub), sub: selectedUser.latest_order_added_at_label === '—' ? 'Дата еще не зафиксирована' : `Последняя: ${selectedUser.latest_order_added_at_label}` },
  ] : [
    { label: 'Клиентов', value: stats.users_total, sub: 'С отправленными заявками' },
    { label: 'Заявок', value: stats.items_total, sub: 'Пользователи уже нажали «Оформить заказ»' },
    { label: 'Ожидают', value: stats.pending_items, sub: `${stats.shipped_items} уже в пути` },
    { label: 'Сумма', value: formatAdminRub(stats.total_with_margin_rub), sub: stats.latest_order_added_at_label === '—' ? 'Пока без дат' : `Последняя: ${stats.latest_order_added_at_label}` },
  ]

  const hero = selectedUser ? (
    <section className="admin-pricing__hero admin-orders__hero card">
      <div className="admin-pricing__hero-copy admin-orders__hero-copy">
        <span className="admin-shell__eyebrow">Заявки клиента</span>
        <p className="admin-pricing__hero-subtitle">Указывайте статус заказа, чтобы клиент всегда был в курсе.</p>
      </div>
      <div className="admin-orders__actions">
        <button
          type="button"
          className={`admin-delivery admin-delivery--${deliveryTone} pressable`}
          onClick={() => setDeliveryDialogOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={deliveryDialogOpen}
        >
          <span className="admin-delivery__icon"><AdminDeliveryIcon /></span>
          <span className="admin-delivery__copy"><span className="admin-delivery__label">Адрес и контакты</span></span>
          <span className={`admin-delivery__badge admin-delivery__badge--${deliveryTone}`}>{deliveryBadgeLabel}</span>
        </button>
        {getAdminMessageChatLink(selectedUser) && (
          <button type="button" className="admin-message__chat pressable" onClick={() => handleOpenChat(selectedUser)}>
            Перейти в чат
          </button>
        )}
      </div>
      <div className="admin-orders__hero-footer">
        <button
          type="button"
          className="admin-orders__summary-toggle pressable"
          onClick={() => {
            setDetailSummaryExpanded((current) => !current)
            haptic?.('light')
          }}
          aria-expanded={detailSummaryExpanded}
        >
          <span className="admin-orders__summary-toggle-label">Краткая сводка</span>
          <span className="admin-orders__summary-toggle-meta">
            <span>{detailSummaryExpanded ? 'Свернуть' : 'Развернуть'}</span>
            <span className="admin-orders__summary-toggle-icon" aria-hidden="true">v</span>
          </span>
        </button>
        <AnimatePresence initial={false}>
          {detailSummaryExpanded && (
            <motion.div className="admin-orders__hero-summary" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={ADMIN_MOTION.quick}>
              <AdminCartsOverview items={overviewItems} showHeader={false} cardless className="admin-orders__hero-overview" />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  ) : (
    <section className="admin-pricing__hero admin-orders__hero admin-orders__hero--overview card">
      <div className="admin-pricing__hero-copy admin-orders__hero-copy">
        <span className="admin-shell__eyebrow">Orders</span>
        <h2 className="admin-pricing__hero-title">Управляйте заказами</h2>
        <p className="admin-pricing__hero-subtitle">Здесь собраны текущие статусы, логистика и действия по каждой заявке.</p>
      </div>
      <div className="admin-orders__hero-footer">
        <button
          type="button"
          className="admin-orders__summary-toggle pressable"
          onClick={() => {
            setListSummaryExpanded((current) => !current)
            haptic?.('light')
          }}
          aria-expanded={listSummaryExpanded}
        >
          <span className="admin-orders__summary-toggle-label">Краткая сводка</span>
          <span className="admin-orders__summary-toggle-meta">
            <span>{listSummaryExpanded ? 'Свернуть' : 'Развернуть'}</span>
            <span className="admin-orders__summary-toggle-icon" aria-hidden="true">v</span>
          </span>
        </button>
        <AnimatePresence initial={false}>
          {listSummaryExpanded && (
            <motion.div className="admin-orders__hero-summary" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={ADMIN_MOTION.quick}>
              <AdminCartsOverview items={overviewItems} showHeader={false} cardless className="admin-orders__hero-overview" />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  )

  const noticeNode = (
    <AnimatePresence>
      {notice && (
        <motion.div
          className={`admin-notice admin-notice--${notice.type}`}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={ADMIN_MOTION.quick}
          aria-live="polite"
        >
          {notice.text}
        </motion.div>
      )}
    </AnimatePresence>
  )

  const shellKey = selectedUser ? `orders-user-${selectedUser.user_id}` : 'orders-list'

  return (
    <>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={shellKey} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={ADMIN_MOTION.standard}>
          <AdminSectionShell topbar={topbar} hero={hero} notice={noticeNode} stats={null} contentClassName={selectedUser ? 'admin-orders__detail-shell' : 'admin-orders__list-shell'}>
            {selectedUser ? (
              <div className="admin-orders__detail-stack" data-shell-swipe-block="true">
                {selectedUser.items.length === 0 ? (
                  <section className="admin-messages__empty card">
                    <span className="admin-shell__eyebrow">Пусто</span>
                    <h2 className="admin-pricing__hero-title">У этого клиента пока нет активных заявок</h2>
                    <p className="admin-pricing__hero-subtitle">Сюда попадают только товары, которые клиент уже отправил на рассмотрение через кнопку «Оформить заказ».</p>
                  </section>
                ) : (
                  selectedUser.items.map((item, index) => {
                    const itemKey = getOrderItemKey(item)
                    const statusMeta = getAdminOrderStatusMeta(item.status_key)
                    const isUpdatingItem = Boolean(updatingKey && updatingKey.startsWith(`${selectedUser.user_id}:${item.calc_id}:`))
                    const actionsExpanded = Boolean(expandedActionKeys[itemKey])
                    const displayItemNumber = getDisplayItemNumber(item)
                    const productTitle = item.short_name || item.name || `Товар #${item.calc_id}`
                    const productMeta = [getCartPlatformName(item.platform), displayItemNumber ? `#${displayItemNumber}` : null].filter(Boolean).join(' • ')
                    const selectedVariants = getOrderParameterRows(item)
                    const paymentActionClass = `admin-pricing__ghost admin-order-item__action ${item.paid ? 'admin-order-item__action--paid-active' : 'admin-order-item__action--paid'} pressable`
                    const shippedActionClass = `admin-pricing__ghost admin-order-item__action ${item.shipped || item.arrived ? 'admin-order-item__action--shipped-done' : 'admin-order-item__action--shipped'} pressable`
                    const arrivedActionClass = `admin-pricing__ghost admin-order-item__action ${item.arrived ? 'admin-order-item__action--arrived-done' : 'admin-order-item__action--arrived'} pressable`
                    const trackingActionClass = `admin-pricing__ghost admin-order-item__action ${item.tracking_number ? 'admin-order-item__action--tracking-active' : 'admin-order-item__action--tracking'} pressable`
                    const itemNumberActionClass = `admin-pricing__ghost admin-order-item__action ${item.item_number ? 'admin-order-item__action--item-number-active' : 'admin-order-item__action--item-number'} pressable`
                    return (
                      <motion.article key={`${selectedUser.user_id}-${item.calc_id}`} className="admin-cart-item admin-order-item admin-orders__item-card card" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ...ADMIN_MOTION.standard, delay: index * 0.02 }}>
                        <div className="admin-cart-item__layout admin-order-item__layout">
                          <AdminCartThumb imageUrl={item.image_url} platform={item.platform} title={productTitle} />
                          <div className="admin-cart-item__main admin-order-item__main">
                            <div className="admin-order-item__identity">
                              <strong className="admin-cart-item__title admin-order-item__title">{productTitle}</strong>
                              <span className="admin-cart-item__meta admin-order-item__meta">{productMeta}</span>
                              <span className="admin-order-item__status" style={{ color: statusMeta.color, borderColor: `${statusMeta.color}33`, background: `${statusMeta.color}14` }}>{item.status_label || statusMeta.label}</span>
                            </div>
                          </div>
                          {item.product_url ? (
                            <button type="button" className="admin-order-item__link pressable" onClick={() => handleOpenProduct(item.product_url)} aria-label="Открыть товар">
                              <AdminExternalLinkIcon />
                            </button>
                          ) : null}
                        </div>
                        <div className="admin-order-item__detail-grid">
                          <section className="admin-orders__section admin-order-item__variants-section">
                            <span className="admin-orders__section-title">Параметры клиента</span>
                            <span className="admin-order-item__variant-title-override">{'\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b \u0442\u043e\u0432\u0430\u0440\u0430'}</span>
                            {selectedVariants.length ? (
                              <div className="admin-order-item__variant-list">
                                {selectedVariants.map((variant) => (
                                  <div key={`${itemKey}-${variant.label}-${variant.value}`} className="admin-order-item__variant-row">
                                    <span className="admin-order-item__variant-label">{variant.label}</span>
                                    <strong className="admin-order-item__variant-value">{variant.value}</strong>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="admin-order-item__variant-empty">Данные не сохранены</p>
                            )}
                          </section>
                          <div className="admin-cart-item__compare admin-order-item__compare admin-order-item__total-card">
                            <div className="admin-cart-item__compare-item admin-order-item__compare-item">
                              <span className="admin-cart-item__price-label">Цена товара</span>
                              <div className="admin-order-item__price-row">
                                <strong className="admin-cart-item__price-value">{formatAdminRub(item.goods_rub ?? item.subtotal_rub)}</strong>
                                <span className="admin-cart-item__price-sub">{`(${formatAdminCny(item.price_cny)})`}</span>
                              </div>
                            </div>
                            <span className="admin-cart-item__compare-divider admin-order-item__compare-divider" aria-hidden="true" />
                            <div className="admin-cart-item__compare-item admin-order-item__compare-item admin-order-item__compare-item--total">
                              <span className="admin-cart-item__price-label">Итог</span>
                              <strong className="admin-cart-item__price-value">{formatAdminRub(item.total_with_margin_rub)}</strong>
                            </div>
                          </div>
                        </div>
                        <button type="button" className="admin-order-item__manage-toggle pressable" onClick={() => toggleManagePanel(item)} aria-expanded={actionsExpanded}>
                          <span className="admin-order-item__manage-toggle-label">Управление</span>
                          <span className="admin-order-item__manage-toggle-meta">
                            <span>{actionsExpanded ? 'Свернуть' : 'Показать'}</span>
                            <span className="admin-order-item__manage-toggle-icon" aria-hidden="true">v</span>
                          </span>
                        </button>
                        <AnimatePresence initial={false}>
                          {actionsExpanded && (
                            <motion.div className="admin-order-item__manage-panel" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={ADMIN_MOTION.quick}>
                              <div className="admin-order-item__actions">
                                <button type="button" className={paymentActionClass} onClick={() => handleAction(item, item.paid ? 'remove_paid' : 'mark_paid')} disabled={isUpdatingItem}>{item.paid ? 'Снять оплату' : 'Отметить оплату'}</button>
                                <button type="button" className={shippedActionClass} onClick={() => handleAction(item, 'mark_shipped')} disabled={isUpdatingItem || item.shipped || item.arrived}>{item.shipped || item.arrived ? 'Отправлен' : 'Отметить отправку'}</button>
                                <button type="button" className={arrivedActionClass} onClick={() => handleAction(item, 'mark_arrived')} disabled={isUpdatingItem || item.arrived}>{item.arrived ? 'Доставлено' : 'Отметить прибытие'}</button>
                                <button type="button" className={trackingActionClass} onClick={() => openValueDialog('tracking', item)} disabled={isUpdatingItem}>{item.tracking_number ? 'Изменить трек-номер' : 'Добавить трек-номер'}</button>
                                <button type="button" className={itemNumberActionClass} onClick={() => openValueDialog('item_number', item)} disabled={isUpdatingItem}>Изменить номер товара</button>
                                <button type="button" className="admin-pricing__ghost admin-pricing__ghost--danger admin-order-item__action admin-order-item__action--danger pressable" onClick={() => handleAction(item, 'remove_order')} disabled={isUpdatingItem}>Убрать из заявки</button>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </motion.article>
                    )
                  })
                )}
              </div>
            ) : users.length === 0 ? (
              <section className="admin-messages__empty card">
                <span className="admin-shell__eyebrow">Пусто</span>
                <h2 className="admin-pricing__hero-title">Активных заявок пока нет</h2>
                <p className="admin-pricing__hero-subtitle">Как только пользователь нажмет «Оформить заказ», отправленные позиции появятся здесь для проверки и дальнейших действий.</p>
              </section>
            ) : (
              <div className="admin-carts__list">
                {users.map((user, index) => (
                  <motion.button key={user.user_id} type="button" className="admin-cart-user admin-order-user card pressable" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ...ADMIN_MOTION.standard, delay: index * 0.02 }} onClick={() => handleOpenUser(user.user_id)}>
                    <div className="admin-cart-user__header admin-order-user__header">
                      <strong className="admin-cart-user__title admin-order-user__title">{user.display_name}</strong>
                      <div className="admin-order-user__headline">
                        <span className={`admin-cart-user__badge admin-order-user__badge ${user.pending_items ? 'admin-cart-user__badge--active' : ''}`}>{pluralizeCartItems(user.total_items)}</span>
                        <span className="admin-cart-user__summary-chip admin-cart-user__summary-chip--sum admin-order-user__sum">{formatAdminRub(user.total_with_margin_rub)}</span>
                      </div>
                    </div>
                    <div className="admin-cart-user__summary admin-order-user__summary">
                      <span className="admin-cart-user__summary-chip admin-order-user__summary-chip">{user.pending_items ? `${user.pending_items} требуют внимания` : 'Без ожидания'}</span>
                      <span className="admin-cart-user__summary-chip admin-order-user__summary-chip">{user.shipped_items ? `${user.shipped_items} в пути` : 'Пока не отправлялись'}</span>
                    </div>
                  </motion.button>
                ))}
              </div>
            )}
          </AdminSectionShell>
        </motion.div>
      </AnimatePresence>
      <AdminModalPortal>
        <AnimatePresence>
          {valueDialogItem && valueDialogConfig && (
            <AdminValueDialog
              eyebrow={valueDialogConfig.eyebrow}
              title={valueDialogConfig.title}
              item={valueDialogItem}
              fieldLabel={valueDialogConfig.fieldLabel}
              placeholder={valueDialogConfig.placeholder}
              value={valueDialogDraft}
              error={valueDialogError}
              saving={valueDialogSaving}
              onChange={(nextValue) => {
                setValueDialogDraft(nextValue)
                if (valueDialogError) setValueDialogError('')
              }}
              onClose={closeValueDialog}
              onSubmit={handleValueDialogSubmit}
            />
          )}
        </AnimatePresence>
      </AdminModalPortal>
      <AdminModalPortal>
        <AnimatePresence>
          {deliveryDialogOpen && selectedUser && selectedDeliveryBatch && (
            <AdminDeliveryDialog user={selectedUser} batch={selectedDeliveryBatch} onClose={() => setDeliveryDialogOpen(false)} onCopyField={handleCopyDeliveryField} />
          )}
        </AnimatePresence>
      </AdminModalPortal>
    </>
  )
}
