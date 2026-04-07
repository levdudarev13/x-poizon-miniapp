import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { fetchAdminSettings, updateAdminSetting } from '../../../api/admin.js'
import { AdminSectionShell } from './AdminSectionShell.jsx'
import {
  ADMIN_MOTION,
  DELIVERY_PRICE_FIELDS,
  DELIVERY_TIMING_FIELDS,
  PRICING_FIELDS,
  RATE_OVERRIDE_FIELD,
  formatExpiry,
  formatFieldPreview,
  formatRate,
  normalizeComparableValue,
} from '../adminShared.js'
import { AdminBackIcon } from './AdminSharedBits.jsx'

const SCREEN_ENTRY = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: ADMIN_MOTION.standard,
}

const DISCLOSURE_CONFIG = [
  {
    id: 'delivery',
    title: 'Доставка',
    fields: DELIVERY_PRICE_FIELDS,
    footer: 'СДЭК по России добавляется только в заявках, если город покупателя отличается от Москвы.',
  },
  {
    id: 'timings',
    title: 'Сроки доставки',
    fields: DELIVERY_TIMING_FIELDS,
    footer: 'Для регионов срок СДЭК по России показывается отдельно и добавляется к маршруту до Москвы.',
  },
]

function PricingFieldCard({
  field,
  draft,
  settings,
  savingField,
  isDirty,
  onFieldChange,
  onFieldSave,
}) {
  const dirty = isDirty(field)
  const isSaving = savingField === field.key

  return (
    <section className={`admin-setting admin-pricing__field-card card ${dirty ? 'admin-setting--dirty admin-pricing__dirty' : ''}`}>
      <div className="admin-pricing__field-head">
        <div className="admin-setting__copy">
          <h3 className="admin-setting__label">{field.label}</h3>
          <p className="admin-setting__hint">{field.hint}</p>
        </div>
        <span className="admin-setting__preview">
          {formatFieldPreview(field, settings?.[field.key])}
        </span>
      </div>
      <div className="admin-pricing__field-row">
        <label className={`admin-setting__input-wrap ${dirty ? 'admin-setting__input-wrap--dirty' : ''}`}>
          <input
            className="admin-setting__input"
            type="text"
            inputMode={field.inputMode || 'text'}
            placeholder={field.placeholder}
            value={draft[field.key] ?? ''}
            onChange={(event) => onFieldChange(field.key, event.target.value)}
          />
          {field.suffix ? <span className="admin-setting__suffix">{field.suffix}</span> : null}
        </label>
        <div className="admin-pricing__field-actions">
          <button
            type="button"
            className={`admin-setting__save admin-pricing__submit pressable ${dirty ? 'admin-setting__save--dirty' : ''}`}
            onClick={() => onFieldSave(field)}
            disabled={!dirty || isSaving}
          >
            {isSaving ? <span className="admin-setting__spinner" /> : dirty ? 'Сохранить' : 'Сохранено'}
          </button>
        </div>
      </div>
    </section>
  )
}

function PricingDisclosure({
  section,
  open,
  settings,
  draft,
  savingField,
  isDirty,
  onToggle,
  onFieldChange,
  onFieldSave,
}) {
  return (
    <motion.section
      className={`admin-pricing__disclosure card ${open ? 'admin-pricing__disclosure--open' : ''}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={ADMIN_MOTION.standard}
    >
      <button
        type="button"
        className="admin-pricing__disclosure-toggle pressable"
        onClick={() => onToggle(section.id)}
        aria-expanded={open}
      >
        <div className="admin-pricing__disclosure-copy">
          <span className="admin-shell__eyebrow">{section.title}</span>
          <h3 className="admin-pricing__disclosure-title">{section.title}</h3>
        </div>
        <div className="admin-pricing__disclosure-meta">
          <span className={`admin-pricing__disclosure-button ${open ? 'admin-pricing__disclosure-button--open' : ''}`}>
            <span className="admin-pricing__disclosure-button-label">{open ? 'Свернуть' : 'Открыть'}</span>
            <span className={`admin-pricing__disclosure-chevron ${open ? 'admin-pricing__disclosure-chevron--open' : ''}`} aria-hidden="true">
              ▾
            </span>
          </span>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            className="admin-pricing__disclosure-body"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={ADMIN_MOTION.quick}
          >
            <div className="admin-pricing__disclosure-fields">
              {section.fields.map((field) => (
                <PricingFieldCard
                  key={field.key}
                  field={field}
                  draft={draft}
                  settings={settings}
                  savingField={savingField}
                  isDirty={isDirty}
                  onFieldChange={onFieldChange}
                  onFieldSave={onFieldSave}
                />
              ))}
            </div>
            <p className="admin-pricing__disclosure-note">{section.footer}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.section>
  )
}

export function AdminPricing({ initData, onBack, haptic }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [payload, setPayload] = useState(null)
  const [draft, setDraft] = useState({})
  const [savingField, setSavingField] = useState('')
  const [notice, setNotice] = useState(null)
  const [openSections, setOpenSections] = useState({
    delivery: true,
    timings: false,
  })

  const applyPayload = useCallback((nextPayload, mode = 'replace', keys = []) => {
    setPayload(nextPayload)

    if (mode === 'replace') {
      setDraft(nextPayload?.settings || {})
      return
    }

    setDraft((currentDraft) => {
      const nextDraft = { ...currentDraft }
      keys.forEach((key) => {
        nextDraft[key] = nextPayload?.settings?.[key] ?? ''
      })
      return nextDraft
    })
  }, [])

  const loadSettings = useCallback(async ({ mode = 'full' } = {}) => {
    if (mode === 'full') {
      setLoading(true)
      setError('')
    }

    try {
      const data = await fetchAdminSettings({ initData })
      applyPayload(data, 'replace')
      setError('')
    } catch (requestError) {
      const message = requestError.message || 'Не удалось загрузить расценки.'

      if (mode === 'full') {
        setError(message)
      } else {
        setNotice({ type: 'error', text: message })
      }
    } finally {
      if (mode === 'full') {
        setLoading(false)
      }
    }
  }, [applyPayload, initData])

  useEffect(() => {
    loadSettings({ mode: 'full' })
  }, [loadSettings])

  const isDirty = (field) => (
    normalizeComparableValue(field, draft[field.key]) !==
    normalizeComparableValue(field, payload?.settings?.[field.key])
  )

  const handleFieldChange = (fieldKey, nextValue) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      [fieldKey]: nextValue,
    }))
  }

  const handleFieldSave = async (field) => {
    setNotice(null)
    setSavingField(field.key)

    try {
      const data = await updateAdminSetting({
        initData,
        field: field.key,
        value: draft[field.key] ?? '',
      })

      applyPayload(data, 'patch', [field.key])
      setNotice({ type: 'success', text: `Поле «${field.label}» обновлено.` })
      haptic?.('success')
    } catch (requestError) {
      setNotice({
        type: 'error',
        text: requestError.message || 'Не удалось сохранить поле.',
      })
      haptic?.('error')
    } finally {
      setSavingField('')
    }
  }

  const toggleSection = useCallback((sectionId) => {
    setOpenSections((current) => ({
      ...current,
      [sectionId]: !current[sectionId],
    }))
  }, [])

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
        <h1 className="admin-shell__detail-title">Расценки</h1>
      </div>
    </div>
  )

  if (loading) {
    return (
      <motion.div {...SCREEN_ENTRY}>
        <AdminSectionShell
          topbar={topbar}
          contentClassName="admin-pricing__field-list"
          data-shell-swipe-block="true"
        >
          {[1, 2, 3].map((item) => (
            <div key={item} className="admin-skeleton card">
              <div className="admin-skeleton__line" style={{ width: '42%' }} />
              <div className="admin-skeleton__line" style={{ width: '78%' }} />
              <div className="admin-skeleton__line" style={{ width: '100%', height: 52, borderRadius: 16 }} />
            </div>
          ))}
        </AdminSectionShell>
      </motion.div>
    )
  }

  if (error && !payload) {
    return (
      <motion.div {...SCREEN_ENTRY}>
        <AdminSectionShell topbar={topbar} data-shell-swipe-block="true">
          <div className="admin-feedback admin-pricing__feedback card">
            <div className="admin-feedback__icon">!</div>
            <div className="admin-feedback__text">
              <strong>Не удалось загрузить расценки</strong>
              <span>{error}</span>
            </div>
            <button
              type="button"
              className="admin-pricing__ghost pressable"
              onClick={() => loadSettings({ mode: 'full' })}
            >
              Повторить
            </button>
          </div>
        </AdminSectionShell>
      </motion.div>
    )
  }

  const settings = payload?.settings || {}
  const rateOverrideDirty = isDirty(RATE_OVERRIDE_FIELD)
  const rateOverrideSaving = savingField === RATE_OVERRIDE_FIELD.key
  const rateSourceIsManual = payload?.rate_source === 'manual'
  const effectiveRateLabel = formatRate(payload?.effective_rate)
  const rateOverrideRawValue = String(settings[RATE_OVERRIDE_FIELD.key] ?? '').trim()
  const rateOverrideNumericValue = Number(rateOverrideRawValue.replace(',', '.'))
  const rateOverrideUsesCbRate = (
    !rateOverrideRawValue ||
    (Number.isFinite(rateOverrideNumericValue) && rateOverrideNumericValue === 0)
  )
  const rateOverridePreview = rateOverrideUsesCbRate
    ? effectiveRateLabel
    : formatFieldPreview(RATE_OVERRIDE_FIELD, settings[RATE_OVERRIDE_FIELD.key])
  const rateOverrideNote = rateSourceIsManual
    ? `Ручной курс действует до ${formatExpiry(payload?.rate_override_expires_at)}.`
    : 'Сейчас расчёты используют автоматический курс ЦБ.'

  const hero = (
    <section className="admin-pricing__hero card">
      <div className="admin-pricing__hero-copy">
        <span className="admin-shell__eyebrow">Тарифы и курс</span>
        <h2 className="admin-pricing__hero-title">Управляй формулой расчёта</h2>
        <p className="admin-pricing__hero-subtitle">
          Комиссия, курс и доставка за 500 грамм сразу влияют на калькулятор, корзину и итоговую сумму в заявках.
        </p>
      </div>
    </section>
  )

  const noticeNode = (
    <AnimatePresence>
      {notice && (
        <motion.div
          className="admin-pricing__feedback"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={ADMIN_MOTION.quick}
        >
          <div className={`admin-notice admin-notice--${notice.type}`} aria-live="polite">
            {notice.text}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )

  return (
    <motion.div {...SCREEN_ENTRY}>
      <AdminSectionShell
        topbar={topbar}
        hero={hero}
        notice={noticeNode}
        contentClassName="admin-pricing__field-list"
        data-shell-swipe-block="true"
      >
        <motion.section
          className={`admin-setting admin-pricing__field-card card ${rateOverrideDirty ? 'admin-setting--dirty admin-pricing__dirty' : ''}`}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={ADMIN_MOTION.standard}
        >
          <div className="admin-pricing__field-head">
            <div className="admin-setting__copy">
              <h3 className="admin-setting__label">{RATE_OVERRIDE_FIELD.label}</h3>
              <p className="admin-setting__hint">{RATE_OVERRIDE_FIELD.hint}</p>
            </div>
            <span className="admin-setting__preview">{rateOverridePreview}</span>
          </div>
          <div className="admin-pricing__field-row">
            <label className={`admin-setting__input-wrap ${rateOverrideDirty ? 'admin-setting__input-wrap--dirty' : ''}`}>
              <input
                className="admin-setting__input"
                type="text"
                inputMode={RATE_OVERRIDE_FIELD.inputMode}
                placeholder={RATE_OVERRIDE_FIELD.placeholder}
                value={draft[RATE_OVERRIDE_FIELD.key] ?? ''}
                onChange={(event) => handleFieldChange(RATE_OVERRIDE_FIELD.key, event.target.value)}
              />
              <span className="admin-setting__suffix">{RATE_OVERRIDE_FIELD.suffix}</span>
            </label>
            <div className="admin-pricing__field-actions">
              <button
                type="button"
                className={`admin-setting__save admin-pricing__submit pressable ${rateOverrideDirty ? 'admin-setting__save--dirty' : ''}`}
                onClick={() => handleFieldSave(RATE_OVERRIDE_FIELD)}
                disabled={!rateOverrideDirty || rateOverrideSaving}
              >
                {rateOverrideSaving ? <span className="admin-setting__spinner" /> : rateOverrideDirty ? 'Сохранить' : 'Сохранено'}
              </button>
            </div>
          </div>
          <p className="admin-pricing__field-note">{rateOverrideNote}</p>
        </motion.section>

        {PRICING_FIELDS.map((field, index) => (
          <motion.div
            key={field.key}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...ADMIN_MOTION.standard, delay: index * 0.02 }}
          >
            <PricingFieldCard
              field={field}
              draft={draft}
              settings={settings}
              savingField={savingField}
              isDirty={isDirty}
              onFieldChange={handleFieldChange}
              onFieldSave={handleFieldSave}
            />
          </motion.div>
        ))}

        {DISCLOSURE_CONFIG.map((section) => (
          <PricingDisclosure
            key={section.id}
            section={section}
            open={Boolean(openSections[section.id])}
            settings={settings}
            draft={draft}
            savingField={savingField}
            isDirty={isDirty}
            onToggle={toggleSection}
            onFieldChange={handleFieldChange}
            onFieldSave={handleFieldSave}
          />
        ))}
      </AdminSectionShell>
    </motion.div>
  )
}
