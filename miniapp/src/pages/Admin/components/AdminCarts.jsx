import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { fetchAdminCarts } from '../../../api/admin.js'
import { AdminSectionShell } from './AdminSectionShell.jsx'
import {
  ADMIN_MOTION,
  formatAdminCny,
  formatAdminRub,
  getAdminMessageChatLink,
  getCartPlatformName,
  openAdminChat,
  openAdminExternalLink,
  pluralizeCartItems,
} from '../adminShared.js'
import {
  AdminBackIcon,
  AdminCartThumb,
  AdminCartsOverview,
  AdminExternalLinkIcon,
  AdminUserAvatar,
} from './AdminSharedBits.jsx'

const EMPTY_STATS = {
  users_total: 0,
  items_total: 0,
  items_in_order: 0,
  total_with_margin_rub: 0,
}

function getCartStatusMeta(item) {
  if (item?.in_order) {
    return {
      label: 'В заявке',
      color: '#f59e0b',
    }
  }

  return {
    label: 'В корзине',
    color: '#12efac',
  }
}

export function AdminCarts({ initData, onBack, haptic, tg }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [payload, setPayload] = useState(null)
  const [selectedUserId, setSelectedUserId] = useState(0)
  const [notice, setNotice] = useState(null)
  const [listSummaryExpanded, setListSummaryExpanded] = useState(false)
  const [detailSummaryExpanded, setDetailSummaryExpanded] = useState(false)

  const applyPayload = useCallback((nextPayload) => {
    setPayload(nextPayload)
    setSelectedUserId((currentUserId) => (
      nextPayload?.users?.some((user) => user.user_id === currentUserId) ? currentUserId : 0
    ))
  }, [])

  const loadCarts = useCallback(async ({ mode = 'full' } = {}) => {
    if (mode === 'full') {
      setLoading(true)
      setError('')
    }

    try {
      const data = await fetchAdminCarts({ initData })
      applyPayload(data)
      setError('')
    } catch (requestError) {
      const message = requestError.message || 'Не удалось загрузить корзины.'

      if (mode === 'full' || !payload) {
        setError(message)
      } else {
        setNotice({ type: 'error', text: message })
      }
    } finally {
      if (mode === 'full') {
        setLoading(false)
      }
    }
  }, [applyPayload, initData, payload])

  useEffect(() => {
    let mounted = true

    fetchAdminCarts({ initData })
      .then((data) => {
        if (!mounted) return
        applyPayload(data)
        setError('')
      })
      .catch((requestError) => {
        if (!mounted) return
        setError(requestError.message || 'Не удалось загрузить корзины.')
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
  const selectedUserItemsInCart = Math.max(0, (selectedUser?.total_items || 0) - (selectedUser?.items_in_order || 0))

  const handleBack = () => {
    setNotice(null)
    if (selectedUser) {
      setSelectedUserId(0)
      setDetailSummaryExpanded(false)
      haptic?.('light')
      return
    }
    onBack()
  }

  const handleOpenUser = (userId) => {
    setNotice(null)
    setSelectedUserId(userId)
    setListSummaryExpanded(false)
    setDetailSummaryExpanded(false)
    haptic?.('light')
  }

  const topbar = (
    <div className="admin-shell__topbar">
      <button
        className="admin-shell__back pressable"
        onClick={handleBack}
        aria-label={selectedUser ? 'Назад к списку корзин' : 'Назад к разделам'}
      >
        <AdminBackIcon />
      </button>
      <div className={`admin-shell__title-wrap ${selectedUser ? 'admin-shell__title-wrap--user' : ''}`}>
        {selectedUser && <AdminUserAvatar user={selectedUser} initData={initData} />}
        <div>
          <span className="admin-shell__eyebrow">{selectedUser ? 'Корзина клиента' : 'Рабочая секция'}</span>
          <h1 className="admin-shell__detail-title">{selectedUser ? selectedUser.display_name : 'Корзины'}</h1>
        </div>
      </div>
    </div>
  )

  if (loading) {
    return (
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={ADMIN_MOTION.standard}>
        <AdminSectionShell topbar={topbar} contentClassName="admin-carts__section">
          {[1, 2, 3].map((item) => (
            <div key={item} className="admin-skeleton card">
              <div className="admin-skeleton__line" style={{ width: '32%' }} />
              <div className="admin-skeleton__line" style={{ width: '64%' }} />
              <div className="admin-skeleton__line" style={{ width: '100%', height: 72, borderRadius: 18 }} />
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
              <strong>Не удалось загрузить корзины</strong>
              <span>{error}</span>
            </div>
            <button className="admin-pricing__ghost pressable" onClick={() => loadCarts({ mode: 'full' })}>
              Повторить
            </button>
          </div>
        </AdminSectionShell>
      </motion.div>
    )
  }

  const overviewItems = selectedUser ? [
    {
      label: 'Товаров',
      value: selectedUser.total_items,
      sub: pluralizeCartItems(selectedUser.total_items),
    },
    {
      label: 'В заявке',
      value: selectedUser.items_in_order,
      sub: selectedUser.items_in_order ? 'Уже переданы в работу' : 'Пока без заявки',
    },
    {
      label: 'В корзине',
      value: selectedUserItemsInCart,
      sub: selectedUserItemsInCart ? 'Ещё ждут переноса' : 'Все позиции уже в работе',
    },
    {
      label: 'Сумма',
      value: formatAdminRub(selectedUser.total_with_margin_rub),
      sub: 'По текущим товарам клиента',
    },
  ] : [
    {
      label: 'Клиентов',
      value: stats.users_total,
      sub: 'С активными корзинами',
    },
    {
      label: 'Товаров',
      value: stats.items_total,
      sub: 'Во всех корзинах',
    },
    {
      label: 'В заявке',
      value: stats.items_in_order,
      sub: 'Уже переданы в оформление',
    },
    {
      label: 'Сумма',
      value: formatAdminRub(stats.total_with_margin_rub),
      sub: 'По всем актуальным корзинам',
    },
  ]
  const selectedUserHasChat = Boolean(selectedUser && getAdminMessageChatLink(selectedUser))

  const hero = selectedUser ? (
    <section className="admin-pricing__hero admin-orders__hero admin-carts__hero card">
      <div className="admin-pricing__hero-copy admin-orders__hero-copy">
        <span className="admin-shell__eyebrow">Корзина клиента</span>
        <p className="admin-pricing__hero-subtitle">
          Здесь собраны товары, которые клиент сохранил перед переносом в заявку или уже держит в работе.
        </p>
      </div>
      {selectedUserHasChat ? (
        <div className="admin-orders__actions admin-carts__actions">
          <button
            type="button"
            className="admin-message__chat pressable"
            onClick={() => openAdminChat(selectedUser, {
              tg,
              haptic,
              onError: (text) => setNotice({ type: 'error', text }),
            })}
          >
            Перейти в чат
          </button>
        </div>
      ) : null}
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
            <motion.div
              className="admin-orders__hero-summary"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={ADMIN_MOTION.quick}
            >
              <AdminCartsOverview items={overviewItems} showHeader={false} cardless className="admin-orders__hero-overview" />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  ) : (
    <section className="admin-pricing__hero admin-orders__hero admin-orders__hero--overview admin-carts__hero card">
      <div className="admin-pricing__hero-copy admin-orders__hero-copy">
        <span className="admin-shell__eyebrow">Carts</span>
        <h2 className="admin-pricing__hero-title">Следите за корзинами</h2>
        <p className="admin-pricing__hero-subtitle">Здесь собраны сохранённые товары, их текущий статус и общий объём.</p>
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
            <motion.div
              className="admin-orders__hero-summary"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={ADMIN_MOTION.quick}
            >
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

  const shellKey = selectedUser ? `carts-user-${selectedUser.user_id}` : 'carts-list'

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={shellKey}
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -12 }}
        transition={ADMIN_MOTION.standard}
      >
        <AdminSectionShell
          topbar={topbar}
          hero={hero}
          notice={noticeNode}
          stats={null}
          contentClassName={selectedUser ? 'admin-orders__detail-shell admin-carts__detail-shell' : 'admin-orders__list-shell admin-carts__list-shell'}
        >
          {selectedUser ? (
            <div className="admin-orders__detail-stack admin-carts__detail-stack" data-shell-swipe-block="true">
              {selectedUser.items.length === 0 ? (
                <section className="admin-messages__empty card">
                  <span className="admin-shell__eyebrow">Пусто</span>
                  <h2 className="admin-pricing__hero-title">В этой корзине пока нет товаров</h2>
                  <p className="admin-pricing__hero-subtitle">
                    После следующего обновления сюда попадут все актуальные товары пользователя.
                  </p>
                </section>
              ) : (
                selectedUser.items.map((item, index) => {
                  const statusMeta = getCartStatusMeta(item)
                  const productTitle = item.short_name || item.name || `Товар #${item.calc_id}`
                  const productMeta = [
                    getCartPlatformName(item.platform),
                    formatAdminCny(item.price_cny),
                    `#${item.calc_id}`,
                  ].filter(Boolean).join(' • ')

                  return (
                    <motion.article
                      key={`${selectedUser.user_id}-${item.calc_id}`}
                      className="admin-cart-item admin-order-item admin-orders__item-card admin-carts__item-card card"
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ ...ADMIN_MOTION.standard, delay: index * 0.02 }}
                    >
                      <div className="admin-cart-item__layout admin-order-item__layout">
                        <AdminCartThumb imageUrl={item.image_url} platform={item.platform} title={productTitle} />
                        <div className="admin-cart-item__main admin-order-item__main">
                          <div className="admin-order-item__identity">
                            <strong className="admin-cart-item__title admin-order-item__title">{productTitle}</strong>
                            <span className="admin-cart-item__meta admin-order-item__meta">{productMeta}</span>
                            <span
                              className="admin-order-item__status"
                              style={{
                                color: statusMeta.color,
                                borderColor: `${statusMeta.color}33`,
                                background: `${statusMeta.color}14`,
                              }}
                            >
                              {statusMeta.label}
                            </span>
                          </div>
                        </div>
                        {item.product_url ? (
                          <button
                            type="button"
                            className="admin-order-item__link pressable"
                            onClick={() => openAdminExternalLink(item.product_url, {
                              tg,
                              haptic,
                              onError: (text) => setNotice({ type: 'error', text }),
                            })}
                            aria-label="Открыть товар"
                          >
                            <AdminExternalLinkIcon />
                          </button>
                        ) : null}
                      </div>

                      <div className="admin-order-item__detail-grid">
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
                    </motion.article>
                  )
                })
              )}
            </div>
          ) : users.length === 0 ? (
            <section className="admin-messages__empty card">
              <span className="admin-shell__eyebrow">Пусто</span>
              <h2 className="admin-pricing__hero-title">Активных корзин пока нет</h2>
              <p className="admin-pricing__hero-subtitle">
                Как только пользователь добавит товар в корзину, он появится здесь без возврата в старый bot-flow.
              </p>
            </section>
          ) : (
            <div className="admin-carts__list">
              {users.map((user, index) => {
                const remainingCartItems = Math.max(0, user.total_items - user.items_in_order)

                return (
                  <motion.button
                    key={user.user_id}
                    type="button"
                    className="admin-cart-user admin-order-user card pressable"
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ ...ADMIN_MOTION.standard, delay: index * 0.02 }}
                    onClick={() => handleOpenUser(user.user_id)}
                  >
                    <div className="admin-cart-user__header admin-order-user__header">
                      <strong className="admin-cart-user__title admin-order-user__title">{user.display_name}</strong>
                      <div className="admin-order-user__headline">
                        <span className={`admin-cart-user__badge admin-order-user__badge ${user.items_in_order ? 'admin-cart-user__badge--active' : ''}`}>
                          {pluralizeCartItems(user.total_items)}
                        </span>
                        <span className="admin-cart-user__summary-chip admin-cart-user__summary-chip--sum admin-order-user__sum">
                          {formatAdminRub(user.total_with_margin_rub)}
                        </span>
                      </div>
                    </div>
                    <div className="admin-cart-user__summary admin-order-user__summary">
                      <span className="admin-cart-user__summary-chip admin-order-user__summary-chip">
                        {user.items_in_order ? `${user.items_in_order} в заявке` : 'Пока без заявки'}
                      </span>
                      <span className="admin-cart-user__summary-chip admin-order-user__summary-chip">
                        {remainingCartItems ? `${remainingCartItems} ещё в корзине` : 'Всё уже в работе'}
                      </span>
                    </div>
                  </motion.button>
                )
              })}
            </div>
          )}
        </AdminSectionShell>
      </motion.div>
    </AnimatePresence>
  )
}
