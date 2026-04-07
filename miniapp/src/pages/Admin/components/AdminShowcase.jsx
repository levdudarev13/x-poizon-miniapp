import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { fetchAdminShowcase, updateAdminShowcase } from '../../../api/admin.js'
import ProductThumb from '../../../components/ui/ProductThumb.jsx'
import {
  IconExternalLink,
  IconLink,
  IconPackage,
  IconTrash,
} from '../../../components/ui/Icons.jsx'
import {
  formatBuyerCny,
  formatBuyerRub,
} from '../../../constants/buyerNumbers.js'
import { ADMIN_MOTION } from '../adminShared.js'
import { AdminBackIcon } from './AdminSharedBits.jsx'
import { AdminSectionShell } from './AdminSectionShell.jsx'

const SCREEN_ENTRY = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: ADMIN_MOTION.standard,
}

const SHOWCASE_DEFAULT_ACCENT = 'var(--poizon-blue)'
const SHOWCASE_SOURCE_LABEL = 'Poizon'
const SHOWCASE_EDITOR_SECTIONS = [
  { id: 'top', title: 'Верхний ряд', start: 0, end: 5 },
  { id: 'bottom', title: 'Нижний ряд', start: 5, end: 10 },
]

function formatProductCnyLabel(product) {
  if (typeof product?.price_cny !== 'number') return ''
  const formattedPrice = formatBuyerCny(product.price_cny)
  return product?.price_is_starting ? `от ${formattedPrice}` : formattedPrice
}

function buildShowcaseProductNote(product) {
  if (!product || typeof product !== 'object') {
    return ''
  }

  const size = typeof product.size === 'string' ? product.size.trim() : ''
  const brand = typeof product.brand === 'string' ? product.brand.trim() : ''
  const category = typeof product.category === 'string' ? product.category.trim() : ''

  return [size, brand || category].filter(Boolean).join(' / ')
}

function normalizeShowcaseLinks(links) {
  return Array.from({ length: 10 }, (_, index) => String(links?.[index] || ''))
}

function extractShowcaseInputUrl(value) {
  const text = String(value || '').trim()
  if (!text) {
    return ''
  }

  if (text.startsWith('http://') || text.startsWith('https://')) {
    return text
  }

  const match = text.match(/https?:\/\/[^\s\u4e00-\u9fff\u0400-\u04FF"'<>]+/i)
  return match ? match[0].replace(/[.,;:!?)]*$/, '') : ''
}

function getShowcaseRequestMessage(requestError, fallbackMessage) {
  if (requestError?.message === 'Not found') {
    return 'Сервер витрины не ответил. Перезапустите miniapp server и попробуйте еще раз.'
  }

  return requestError?.message || fallbackMessage
}

function getShowcaseSaveErrorMessage(requestError) {
  if (requestError?.message === 'invalid_showcase_links') {
    return 'Проверьте ссылки: одна или несколько карточек заполнены некорректно.'
  }

  if (requestError?.message === 'duplicate_showcase_links') {
    return 'Этот товар уже стоит на витрине. Уберите дубль или выберите другой слот.'
  }

  if (requestError?.message === 'showcase_products_unavailable') {
    return 'Не удалось загрузить один или несколько товаров по указанным ссылкам.'
  }

  return getShowcaseRequestMessage(requestError, 'Не удалось сохранить витрину.')
}

function buildShowcaseEditorSlots(links, items) {
  const itemBySlot = new Map(
    Array.isArray(items)
      ? items
        .filter((item) => Number(item?.slot) > 0)
        .map((item) => [Number(item.slot), item])
      : [],
  )

  return normalizeShowcaseLinks(links).map((url, index) => {
    const slot = index + 1
    const showcaseItem = itemBySlot.get(slot) || null
    const product = showcaseItem?.product || null

    return {
      slot,
      url,
      normalizedUrl: extractShowcaseInputUrl(url),
      product,
      occupied: Boolean(url),
      accentColor: SHOWCASE_DEFAULT_ACCENT,
      sourceLabel: SHOWCASE_SOURCE_LABEL,
      priceLabel: typeof showcaseItem?.subtotal_rub === 'number' && Number.isFinite(showcaseItem.subtotal_rub)
        ? formatBuyerRub(showcaseItem.subtotal_rub)
        : formatProductCnyLabel(product),
      note: buildShowcaseProductNote(product),
      href: showcaseItem?.url || product?.url || url || '',
    }
  })
}

function buildShowcaseUpdatePayloadFromSlots(slots) {
  return Array.from({ length: 10 }, (_, index) => String(slots?.[index]?.url || ''))
}

function getDefaultShowcaseSlotSelection(slots) {
  const safeSlots = Array.isArray(slots) ? slots : []
  const emptySlot = safeSlots.find((slot) => !slot.occupied)

  if (emptySlot) {
    return { slot: emptySlot.slot, input: '' }
  }

  const firstSlot = safeSlots[0]
  return {
    slot: firstSlot?.slot || 1,
    input: firstSlot?.url || '',
  }
}

export function AdminShowcase({ initData, onBack, haptic }) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(null)
  const [slotErrors, setSlotErrors] = useState({})
  const [slots, setSlots] = useState(() => buildShowcaseEditorSlots([], []))
  const [activeSlotNumber, setActiveSlotNumber] = useState(1)
  const [inputValue, setInputValue] = useState('')

  const hasLoadedRef = useRef(false)
  const activeSlotNumberRef = useRef(1)
  const inputRef = useRef(null)

  useEffect(() => {
    activeSlotNumberRef.current = activeSlotNumber
  }, [activeSlotNumber])

  const activeSlot = slots.find((slot) => slot.slot === activeSlotNumber) || slots[0] || null
  const inputUrl = extractShowcaseInputUrl(inputValue)
  const duplicateSlot = inputUrl
    ? slots.find(
      (slot) => slot.slot !== activeSlotNumber && slot.normalizedUrl === inputUrl,
    ) || null
    : null
  const activeSlotError = activeSlot ? slotErrors?.[activeSlot.slot] || '' : ''
  const inputUnchanged = Boolean(
    activeSlot?.normalizedUrl &&
    inputUrl &&
    inputUrl === activeSlot.normalizedUrl,
  )

  const configuredCount = slots.filter((slot) => slot.occupied).length
  const emptyCount = Math.max(0, slots.length - configuredCount)
  const submitDisabled = loading || saving || !inputUrl || Boolean(duplicateSlot) || inputUnchanged
  const submitLabel = saving
    ? 'Сохраняю...'
    : activeSlot?.occupied
      ? 'Заменить товар'
      : 'Добавить в слот'

  const clearSlotError = useCallback((slotNumber) => {
    setSlotErrors((currentErrors) => {
      if (!currentErrors?.[slotNumber]) {
        return currentErrors
      }

      const nextErrors = { ...currentErrors }
      delete nextErrors[slotNumber]
      return nextErrors
    })
  }, [])

  const loadShowcase = useCallback(async ({ mode = 'full', preserveSelection = false } = {}) => {
    if (!initData) {
      return null
    }

    setNotice(null)

    if (mode === 'full') {
      setLoading(true)
      setError('')
    }

    try {
      const data = await fetchAdminShowcase({ initData })
      const nextSlots = buildShowcaseEditorSlots(data?.links, data?.items)
      const preservedSlot = preserveSelection
        ? nextSlots.find((slot) => slot.slot === activeSlotNumberRef.current) || null
        : null
      const nextSelection = preservedSlot
        ? { slot: preservedSlot.slot, input: preservedSlot.url || '' }
        : getDefaultShowcaseSlotSelection(nextSlots)

      setSlots(nextSlots)
      setSlotErrors({})
      setActiveSlotNumber(nextSelection.slot)
      setInputValue(nextSelection.input)
      setError('')
      hasLoadedRef.current = true
      return nextSlots
    } catch (requestError) {
      const nextError = getShowcaseRequestMessage(requestError, 'Не удалось загрузить витрину.')

      if (mode === 'full' || !hasLoadedRef.current) {
        setError(nextError)
      } else {
        setNotice({ type: 'error', text: nextError })
      }

      return null
    } finally {
      if (mode === 'full') {
        setLoading(false)
      }
    }
  }, [initData])

  useEffect(() => {
    loadShowcase({ mode: 'full' })
  }, [loadShowcase])

  const focusInput = useCallback(() => {
    window.requestAnimationFrame(() => {
      inputRef.current?.focus?.({ preventScroll: true })
    })
  }, [])

  const handleSelectSlot = useCallback((slot, { focus = false } = {}) => {
    if (!slot) {
      return
    }

    setActiveSlotNumber(slot.slot)
    setInputValue(slot.url || '')
    setError('')
    setNotice(null)
    clearSlotError(slot.slot)
    haptic?.('light')

    if (focus) {
      focusInput()
    }
  }, [clearSlotError, focusInput, haptic])

  const handleInputChange = useCallback((value) => {
    setInputValue(value)
    setError('')
    setNotice(null)

    if (activeSlot) {
      clearSlotError(activeSlot.slot)
    }
  }, [activeSlot, clearSlotError])

  const handleSubmit = useCallback(async () => {
    if (!initData || !activeSlot || submitDisabled) {
      return
    }

    setSaving(true)
    setError('')
    setNotice(null)
    setSlotErrors({})

    try {
      const activeSlotValue = activeSlot.slot
      const wasOccupied = activeSlot.occupied
      const nextLinks = buildShowcaseUpdatePayloadFromSlots(slots)
      nextLinks[activeSlotValue - 1] = inputUrl

      const data = await updateAdminShowcase({
        initData,
        links: nextLinks,
      })

      const nextSlots = buildShowcaseEditorSlots(data?.links, data?.items)
      const nextSelectedSlot = nextSlots.find((slot) => slot.slot === activeSlotValue) || nextSlots[0] || null
      const nextEmptySlot = nextSlots.find((slot) => slot.slot > activeSlotValue && !slot.occupied)
        || nextSlots.find((slot) => !slot.occupied)

      setSlots(nextSlots)
      setSlotErrors({})
      setNotice({
        type: 'success',
        text: wasOccupied
          ? `Слот ${activeSlotValue} обновлен.`
          : `Товар добавлен в слот ${activeSlotValue}.`,
      })

      if (!wasOccupied && nextEmptySlot) {
        setActiveSlotNumber(nextEmptySlot.slot)
        setInputValue('')
      } else {
        setActiveSlotNumber(nextSelectedSlot?.slot || activeSlotValue)
        setInputValue(nextSelectedSlot?.url || '')
      }

      haptic?.('success')
    } catch (requestError) {
      setError(getShowcaseSaveErrorMessage(requestError))
      setSlotErrors(requestError?.slot_errors || {})
      haptic?.('error')
    } finally {
      setSaving(false)
    }
  }, [activeSlot, haptic, initData, inputUrl, slots, submitDisabled])

  const handleRemove = useCallback(async (slot) => {
    if (!initData || !slot?.occupied) {
      return
    }

    setSaving(true)
    setError('')
    setNotice(null)
    setSlotErrors({})

    try {
      const nextLinks = buildShowcaseUpdatePayloadFromSlots(slots)
      nextLinks[slot.slot - 1] = ''

      const data = await updateAdminShowcase({
        initData,
        links: nextLinks,
      })

      const nextSlots = buildShowcaseEditorSlots(data?.links, data?.items)
      const nextSelectedSlot = nextSlots.find((item) => item.slot === slot.slot) || nextSlots[0] || null

      setSlots(nextSlots)
      setActiveSlotNumber(nextSelectedSlot?.slot || slot.slot)
      setInputValue('')
      setNotice({
        type: 'success',
        text: `Слот ${slot.slot} очищен.`,
      })
      haptic?.('success')
    } catch (requestError) {
      setError(getShowcaseRequestMessage(requestError, 'Не удалось убрать товар из витрины.'))
      setSlotErrors(requestError?.slot_errors || {})
      haptic?.('error')
    } finally {
      setSaving(false)
    }
  }, [haptic, initData, slots])

  const handleOpenSlotLink = useCallback((slot) => {
    const targetUrl = String(slot?.href || '').trim()
    if (!targetUrl) {
      return
    }

    window.open(targetUrl, '_blank', 'noopener,noreferrer')
    haptic?.('light')
  }, [haptic])

  const topbar = (
    <div className="admin-shell__topbar">
      <button
        type="button"
        className="admin-shell__back pressable"
        onClick={onBack}
        aria-label="Назад к разделам"
      >
        <AdminBackIcon />
      </button>
      <div>
        <span className="admin-shell__eyebrow">Рабочая секция</span>
        <h1 className="admin-shell__detail-title">Витрина</h1>
      </div>
    </div>
  )

  if (loading) {
    return (
      <motion.div {...SCREEN_ENTRY}>
        <AdminSectionShell
          topbar={topbar}
          contentClassName="admin-showcase__stack"
          data-shell-swipe-block="true"
        >
          {[1, 2, 3].map((item) => (
            <div key={item} className="admin-skeleton card">
              <div className="admin-skeleton__line" style={{ width: '28%' }} />
              <div className="admin-skeleton__line" style={{ width: '82%' }} />
              <div className="admin-skeleton__line" style={{ width: '100%', height: 160, borderRadius: 18 }} />
            </div>
          ))}
        </AdminSectionShell>
      </motion.div>
    )
  }

  if (error && !hasLoadedRef.current) {
    return (
      <motion.div {...SCREEN_ENTRY}>
        <AdminSectionShell topbar={topbar} data-shell-swipe-block="true">
          <div className="admin-feedback admin-pricing__feedback card">
            <div className="admin-feedback__icon">!</div>
            <div className="admin-feedback__text">
              <strong>Не удалось загрузить витрину</strong>
              <span>{error}</span>
            </div>
            <button
              type="button"
              className="admin-pricing__ghost pressable"
              onClick={() => loadShowcase({ mode: 'full' })}
            >
              Повторить
            </button>
          </div>
        </AdminSectionShell>
      </motion.div>
    )
  }

  const hero = (
    <section className="admin-showcase__hero card">
      <div className="admin-showcase__hero-copy">
        <span className="admin-shell__eyebrow">Главный экран</span>
        <h2 className="admin-showcase__hero-title">Управление витриной вынесено в админ-панель</h2>
        <p className="admin-showcase__hero-subtitle">
          Здесь настраиваются карточки, которые клиент видит на первом экране миниаппа. Выберите слот,
          вставьте ссылку на товар и обновите нужную позицию без перехода в buyer-режим.
        </p>
      </div>

      <div className="admin-showcase__hero-actions">
        <div className="admin-showcase__hero-stat">
          <span className="admin-showcase__hero-stat-label">Заполнено</span>
          <strong className="admin-showcase__hero-stat-value">{configuredCount}/10</strong>
        </div>
        <div className="admin-showcase__hero-stat">
          <span className="admin-showcase__hero-stat-label">Свободно</span>
          <strong className="admin-showcase__hero-stat-value">{emptyCount}</strong>
        </div>
        <button
          type="button"
          className="admin-faq__add admin-showcase__refresh pressable"
          onClick={() => loadShowcase({ mode: 'full', preserveSelection: true })}
          disabled={saving}
        >
          Обновить витрину
        </button>
      </div>
    </section>
  )

  const noticeNode = notice ? (
    <div className={`admin-notice admin-notice--${notice.type}`} aria-live="polite">
      {notice.text}
    </div>
  ) : null

  return (
    <motion.div {...SCREEN_ENTRY}>
      <AdminSectionShell
        topbar={topbar}
        hero={hero}
        notice={noticeNode}
        contentClassName="admin-showcase__stack"
        data-shell-swipe-block="true"
      >
        <section className="admin-showcase__composer card">
          <div className="admin-showcase__composer-head">
            <div className="admin-showcase__composer-copy">
              <span className="admin-shell__eyebrow">Редактор</span>
              <h2 className="admin-showcase__composer-title">Слот {activeSlot?.slot || 1}</h2>
              <p className="admin-showcase__composer-subtitle">
                {activeSlot?.occupied
                  ? 'Можно заменить текущий товар новой ссылкой или очистить слот.'
                  : 'Вставьте ссылку на товар Poizon, и он появится на главном экране.'}
              </p>
            </div>

            <span className={`admin-showcase__slot-badge ${activeSlot?.occupied ? 'admin-showcase__slot-badge--live' : 'admin-showcase__slot-badge--empty'}`}>
              {activeSlot?.occupied ? 'Заполнен' : 'Свободен'}
            </span>
          </div>

          {error ? (
            <div className="admin-showcase__inline-notice admin-showcase__inline-notice--error">
              {error}
            </div>
          ) : null}

          <label className="admin-showcase__field">
            <span className="admin-modal__field-label">Ссылка на товар</span>
            <div className={`admin-showcase__input-wrap${activeSlotError ? ' admin-showcase__input-wrap--error' : ''}`}>
              <span className="admin-showcase__input-icon" aria-hidden="true">
                <IconLink size={18} />
              </span>
              <input
                ref={inputRef}
                className="admin-showcase__input"
                type="url"
                value={inputValue}
                placeholder="https://..."
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
                enterKeyHint="done"
                onChange={(event) => handleInputChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !submitDisabled) {
                    event.preventDefault()
                    handleSubmit()
                  }
                }}
              />
            </div>
          </label>

          {activeSlotError ? (
            <div className="admin-showcase__field-error">{activeSlotError}</div>
          ) : duplicateSlot ? (
            <div className="admin-showcase__inline-notice admin-showcase__inline-notice--warning">
              Эта ссылка уже сохранена в слоте {duplicateSlot.slot}. Повторный парс не нужен.
            </div>
          ) : inputUnchanged ? (
            <div className="admin-showcase__inline-notice admin-showcase__inline-notice--muted">
              Эта ссылка уже сохранена в выбранном слоте.
            </div>
          ) : (
            <div className="admin-showcase__inline-note">
              После сохранения карточка сразу обновится на главном экране buyer-миниаппа.
            </div>
          )}

          <div className={`admin-showcase__composer-actions${activeSlot?.occupied ? ' admin-showcase__composer-actions--split' : ''}`}>
            <button
              type="button"
              className="admin-faq__add pressable"
              onClick={handleSubmit}
              disabled={submitDisabled}
            >
              {submitLabel}
            </button>

            {activeSlot?.occupied ? (
              <button
                type="button"
                className="admin-pricing__ghost admin-pricing__ghost--danger pressable"
                onClick={() => handleRemove(activeSlot)}
                disabled={saving}
              >
                <IconTrash size={16} />
                <span>Очистить слот</span>
              </button>
            ) : null}
          </div>
        </section>

        <div className="admin-showcase__groups">
          {SHOWCASE_EDITOR_SECTIONS.map((section) => (
            <section key={section.id} className="admin-showcase__group card">
              <div className="admin-showcase__group-head">
                <h3 className="admin-showcase__group-title">{section.title}</h3>
                <p className="admin-showcase__group-note">
                  Нажмите на слот, чтобы подставить его ссылку в редактор и быстро заменить товар.
                </p>
              </div>

              <div className="admin-showcase__slots">
                {slots.slice(section.start, section.end).map((slot, index) => {
                  const slotError = slotErrors?.[slot.slot] || ''
                  const slotIsActive = slot.slot === (activeSlot?.slot || activeSlotNumber)
                  const slotIsDuplicate = duplicateSlot?.slot === slot.slot
                  const slotBadgeClass = slotIsDuplicate
                    ? 'admin-showcase__slot-badge--warning'
                    : slot.occupied
                      ? 'admin-showcase__slot-badge--live'
                      : 'admin-showcase__slot-badge--empty'
                  const slotBadgeLabel = slotIsDuplicate
                    ? 'Дубль'
                    : slot.occupied
                      ? 'Заполнен'
                      : 'Пусто'

                  return (
                    <motion.article
                      key={`admin-showcase-slot-${slot.slot}`}
                      className={`admin-showcase__slot${slotIsActive ? ' admin-showcase__slot--active' : ''}${slotIsDuplicate ? ' admin-showcase__slot--duplicate' : ''}`}
                      style={{ '--showcase-slot-accent': slot.accentColor || SHOWCASE_DEFAULT_ACCENT }}
                      initial={{ opacity: 0, y: 14 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ ...ADMIN_MOTION.quick, delay: Math.min((section.start + index) * 0.03, 0.18) }}
                    >
                      <button
                        type="button"
                        className="admin-showcase__slot-main pressable"
                        onClick={() => handleSelectSlot(slot, { focus: true })}
                        aria-pressed={slotIsActive}
                      >
                        <div className="admin-showcase__slot-top">
                          <span className="admin-showcase__slot-index">Слот {slot.slot}</span>
                          <span className={`admin-showcase__slot-badge ${slotBadgeClass}`}>
                            {slotBadgeLabel}
                          </span>
                        </div>

                        <div className="admin-showcase__slot-body">
                          {slot.occupied ? (
                            <ProductThumb
                              src={slot?.product?.image_url || ''}
                              alt={slot?.product?.name || ''}
                              fallbackLabel={slot?.sourceLabel || 'slot'}
                              size="md"
                              className="admin-showcase__slot-thumb"
                            />
                          ) : (
                            <div className="admin-showcase__slot-placeholder" aria-hidden="true">
                              <IconPackage size={18} />
                            </div>
                          )}

                          <div className="admin-showcase__slot-copy">
                            <p className="admin-showcase__slot-title">
                              {slot.occupied
                                ? (slot?.product?.name || 'Товар без названия')
                                : 'Свободный слот'}
                            </p>
                            <p className="admin-showcase__slot-price">
                              {slot.occupied
                                ? (slot.priceLabel || slot.sourceLabel || 'Карточка без цены')
                                : 'Добавьте ссылку на товар'}
                            </p>
                            {slot.note ? (
                              <p className="admin-showcase__slot-note">{slot.note}</p>
                            ) : null}
                          </div>
                        </div>
                      </button>

                      <div className="admin-showcase__slot-actions">
                        <button
                          type="button"
                          className="admin-pricing__ghost pressable"
                          onClick={() => handleSelectSlot(slot, { focus: true })}
                        >
                          {slotIsActive ? 'Редактируется' : 'Выбрать слот'}
                        </button>

                        {slot.href ? (
                          <button
                            type="button"
                            className="admin-pricing__ghost pressable"
                            onClick={() => handleOpenSlotLink(slot)}
                          >
                            <IconExternalLink size={15} />
                            <span>Открыть</span>
                          </button>
                        ) : null}
                      </div>

                      {!slotIsActive && slotError ? (
                        <span className="admin-showcase__field-error">{slotError}</span>
                      ) : null}
                    </motion.article>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
      </AdminSectionShell>
    </motion.div>
  )
}
