import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { fetchDeliveryProfile, saveDeliveryProfile } from '../../api/delivery'
import StateSurface from '../../components/ui/StateSurface'
import {
  IconArrowLeft,
  IconCheck,
  IconStateAlert,
  IconStateRetry,
  IconStateSuccess,
} from '../../components/ui/Icons'
import { BUYER_MOTION } from '../../constants/buyerMotion'
import { useTelegram } from '../../hooks/useTelegram'
import './DeliveryProfile.css'

const DELIVERY_FIELDS = [
  {
    key: 'recipient_name',
    label: 'Получатель',
    placeholder: 'Имя и фамилия',
    autoComplete: 'name',
  },
  {
    key: 'phone',
    label: 'Телефон',
    placeholder: '+7 9XX XXX-XX-XX',
    autoComplete: 'tel',
    inputMode: 'tel',
  },
  {
    key: 'city',
    label: 'Город',
    placeholder: 'Например, Владивосток',
    autoComplete: 'address-level2',
    blocking: true,
  },
  {
    key: 'street',
    label: 'Улица',
    placeholder: 'Улица или проспект',
    autoComplete: 'address-line1',
    blocking: true,
  },
  {
    key: 'house',
    label: 'Дом',
    placeholder: 'Дом, корпус, строение',
    autoComplete: 'address-line1',
    blocking: true,
  },
  {
    key: 'apartment',
    label: 'Квартира',
    placeholder: 'Квартира или офис',
    autoComplete: 'address-line2',
  },
  {
    key: 'comment',
    label: 'Комментарий',
    placeholder: 'Ориентир, подъезд, звонок',
    multiline: true,
  },
]

const FIELD_KEYS = DELIVERY_FIELDS.map((field) => field.key)
const BLOCKING_FIELD_KEYS = DELIVERY_FIELDS
  .filter((field) => field.blocking)
  .map((field) => field.key)

function createEmptyDeliveryData() {
  return FIELD_KEYS.reduce((accumulator, fieldKey) => ({
    ...accumulator,
    [fieldKey]: '',
  }), {})
}

function normalizeDeliveryData(deliveryData = {}) {
  return FIELD_KEYS.reduce((accumulator, fieldKey) => ({
    ...accumulator,
    [fieldKey]: String(deliveryData?.[fieldKey] || ''),
  }), createEmptyDeliveryData())
}

function getMissingBlockingFields(deliveryData = {}) {
  return BLOCKING_FIELD_KEYS.filter((fieldKey) => !String(deliveryData?.[fieldKey] || '').trim())
}

function createCompletionSnapshot(payload = {}) {
  const deliveryData = normalizeDeliveryData(payload?.delivery_data)
  const missingBlockingFields = getMissingBlockingFields(deliveryData)

  return {
    deliveryData,
    isComplete: missingBlockingFields.length === 0,
    missingBlockingFields,
    updatedAt: String(payload?.updated_at || ''),
  }
}

function BlockingFieldStatus({ label, complete }) {
  return (
    <div
      className={`delivery-profile__requirement${complete ? ' delivery-profile__requirement--ready' : ''}`}
      aria-label={complete ? `${label}: обязательное поле заполнено` : `${label}: обязательное поле не заполнено`}
    >
      <span className="delivery-profile__requirement-marker" aria-hidden="true">
        {complete ? <IconCheck size={13} /> : <IconStateAlert size={13} />}
      </span>
      <span className="delivery-profile__requirement-copy">
        <span className="delivery-profile__requirement-label">{label}</span>
        <span className="delivery-profile__requirement-hint">
          {complete ? 'Есть в профиле' : 'Нужно для заказа'}
        </span>
      </span>
      <span className="delivery-profile__requirement-state">
        {complete ? 'Заполнено' : 'Пусто'}
      </span>
    </div>
  )
}

export default function DeliveryProfile({
  active = true,
  onBack,
  onCompletionChange,
}) {
  const { userId, haptic, hideKeyboard } = useTelegram()
  const prefersReducedMotion = useReducedMotion()
  const [formData, setFormData] = useState(() => createEmptyDeliveryData())
  const [serverData, setServerData] = useState(() => createEmptyDeliveryData())
  const [updatedAt, setUpdatedAt] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [saveStamp, setSaveStamp] = useState(0)

  const completion = useMemo(
    () => createCompletionSnapshot({ delivery_data: formData, updated_at: updatedAt }),
    [formData, updatedAt],
  )

  const isDirty = useMemo(
    () => FIELD_KEYS.some((fieldKey) => formData[fieldKey] !== serverData[fieldKey]),
    [formData, serverData],
  )

  const emitCompletion = useCallback((payload) => {
    if (typeof onCompletionChange !== 'function') {
      return
    }

    onCompletionChange(createCompletionSnapshot(payload))
  }, [onCompletionChange])

  const applyServerPayload = useCallback((payload) => {
    const nextDeliveryData = normalizeDeliveryData(payload?.delivery_data)
    const nextUpdatedAt = String(payload?.updated_at || '')

    setFormData(nextDeliveryData)
    setServerData(nextDeliveryData)
    setUpdatedAt(nextUpdatedAt)
    emitCompletion({
      delivery_data: nextDeliveryData,
      updated_at: nextUpdatedAt,
    })
  }, [emitCompletion])

  const loadProfile = useCallback(async () => {
    if (!userId) {
      const emptyPayload = {
        delivery_data: createEmptyDeliveryData(),
        updated_at: '',
      }

      setLoading(false)
      setError(new Error('Missing userId'))
      setSaveError(null)
      applyServerPayload(emptyPayload)
      return
    }

    setLoading(true)
    setError(null)
    setSaveError(null)

    try {
      const payload = await fetchDeliveryProfile({ userId })
      applyServerPayload(payload)
      setError(null)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [applyServerPayload, userId])

  useEffect(() => {
    if (active === false) {
      return undefined
    }

    let cancelled = false

    const run = async () => {
      setLoading(true)

      try {
        if (!userId) {
          throw new Error('Missing userId')
        }

        const payload = await fetchDeliveryProfile({ userId })
        if (cancelled) {
          return
        }

        applyServerPayload(payload)
        setError(null)
        setSaveError(null)
      } catch (err) {
        if (!cancelled) {
          setError(err)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    run()

    return () => {
      cancelled = true
    }
  }, [active, applyServerPayload, userId])

  useEffect(() => {
    if (!saveStamp) {
      return undefined
    }

    const timeoutId = window.setTimeout(() => {
      setSaveStamp((currentValue) => (currentValue === saveStamp ? 0 : currentValue))
    }, 2200)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [saveStamp])

  const handleFieldChange = useCallback((fieldKey, nextValue) => {
    setFormData((currentData) => ({
      ...currentData,
      [fieldKey]: nextValue,
    }))
    setSaveError(null)
  }, [])

  const handleSubmit = useCallback(async (event) => {
    event.preventDefault()

    if (!userId) {
      const nextError = new Error('Missing userId')
      setSaveError(nextError)
      haptic?.('error')
      return
    }

    setSaving(true)
    setSaveError(null)

    try {
      const payload = await saveDeliveryProfile({
        userId,
        deliveryData: formData,
      })

      applyServerPayload(payload)
      setError(null)
      setSaveStamp(Date.now())
      hideKeyboard?.()
      haptic?.('success')
    } catch (err) {
      setSaveError(err)
      haptic?.('error')
    } finally {
      setSaving(false)
    }
  }, [applyServerPayload, formData, haptic, hideKeyboard, userId])

  const handleBack = useCallback(() => {
    haptic?.('light')
    onBack?.()
  }, [haptic, onBack])

  const updatedAtLabel = updatedAt || 'Пока нет сохранения на сервере'

  if (loading) {
    return (
      <div className="page delivery-profile delivery-profile--loading buyer-page buyer-page--delivery-profile">
        <div className="page-content delivery-profile__content delivery-profile__content--loading">
          <StateSurface
            tone="progress"
            compact
            eyebrow="Доставка"
            title="Загружаем адрес"
            body="Подтягиваем сохраненные данные доставки из профиля."
            icon={<IconStateRetry size={22} />}
          />
        </div>
      </div>
    )
  }

  if (error && !serverData.city && !serverData.street && !serverData.house && !userId) {
    return (
      <div className="page delivery-profile buyer-page buyer-page--delivery-profile">
        <div className="delivery-profile__header">
          <button type="button" className="delivery-profile__back pressable" onClick={handleBack}>
            <IconArrowLeft size={20} />
          </button>

          <div className="delivery-profile__header-copy">
            <h1 className="delivery-profile__title">Данные для доставки</h1>
            <p className="delivery-profile__subtitle">Нужен Telegram user id, чтобы загрузить адрес из профиля.</p>
          </div>
        </div>

        <div className="page-content delivery-profile__content">
          <StateSurface
            tone="error"
            eyebrow="Профиль"
            title="Не удалось открыть форму"
            body="Mini App не передал пользователя. Откройте экран из Telegram и попробуйте снова."
            actionLabel="Повторить"
            onAction={loadProfile}
            icon={<IconStateAlert size={22} />}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="page delivery-profile buyer-page buyer-page--delivery-profile">
      <div className="delivery-profile__header">
        <button type="button" className="delivery-profile__back pressable" onClick={handleBack}>
          <IconArrowLeft size={20} />
        </button>

        <div className="delivery-profile__header-copy">
          <h1 className="delivery-profile__title">Данные для доставки</h1>
          <p className="delivery-profile__subtitle">Сохраните адрес и контакты, чтобы они указывались в заказе</p>
        </div>
      </div>

      <div className="page-content delivery-profile__content">
        {error ? (
          <StateSurface
            tone="error"
            compact
            eyebrow="Связь"
            title="Адрес не обновился"
            body="Последние сохраненные значения уже в форме. Можно повторить загрузку или продолжить редактирование."
            actionLabel="Повторить"
            onAction={loadProfile}
            icon={<IconStateAlert size={22} />}
          />
        ) : null}

        <motion.section
          className="delivery-profile__summary ui-surface-panel"
          initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
        >
          <span className="delivery-profile__eyebrow">Профиль заказа</span>

          <div className="delivery-profile__summary-meta">
            <div className="delivery-profile__summary-meta-item">
              <span className="delivery-profile__summary-meta-label">Что обязательно</span>
              <span className="delivery-profile__summary-meta-value">Город, улица и дом</span>
            </div>
            <div className="delivery-profile__summary-meta-item">
              <span className="delivery-profile__summary-meta-label">Последнее сохранение</span>
              <span className="delivery-profile__summary-meta-value">{updatedAtLabel}</span>
            </div>
          </div>

          <div className="delivery-profile__requirements" role="list" aria-label="Обязательные поля для оформления заказа">
            <BlockingFieldStatus label="Город" complete={!completion.missingBlockingFields.includes('city')} />
            <BlockingFieldStatus label="Улица" complete={!completion.missingBlockingFields.includes('street')} />
            <BlockingFieldStatus label="Дом" complete={!completion.missingBlockingFields.includes('house')} />
          </div>
        </motion.section>

        <motion.form
          className="delivery-profile__form"
          onSubmit={handleSubmit}
          data-shell-swipe-block="true"
          initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
        >
          <div className="delivery-profile__grid">
            {DELIVERY_FIELDS.map((field) => {
              const isBlocking = Boolean(field.blocking)
              const hasValue = Boolean(String(formData[field.key] || '').trim())
              const isMissingBlocking = isBlocking && completion.missingBlockingFields.includes(field.key)
              const fieldClassName = [
                'delivery-profile__field',
                isBlocking ? 'delivery-profile__field--blocking' : '',
                isMissingBlocking ? 'delivery-profile__field--missing' : '',
                field.multiline ? 'delivery-profile__field--full' : '',
                (field.key === 'house' || field.key === 'apartment') ? 'delivery-profile__field--half' : '',
              ].filter(Boolean).join(' ')

              return (
                <label key={field.key} className={fieldClassName}>
                  <span className="delivery-profile__field-label-row">
                    <span className="delivery-profile__field-label">{field.label}</span>
                    {isBlocking ? (
                      <span
                        className={`delivery-profile__field-status${hasValue ? ' delivery-profile__field-status--ready' : ''}`}
                        aria-hidden="true"
                      >
                        {hasValue ? 'Готово' : 'Обязательно'}
                      </span>
                    ) : null}
                  </span>

                  {field.multiline ? (
                    <textarea
                      className="delivery-profile__input delivery-profile__input--textarea"
                      name={field.key}
                      rows={4}
                      placeholder={field.placeholder}
                      value={formData[field.key]}
                      onChange={(event) => handleFieldChange(field.key, event.target.value)}
                    />
                  ) : (
                    <input
                      className="delivery-profile__input"
                      type="text"
                      name={field.key}
                      placeholder={field.placeholder}
                      value={formData[field.key]}
                      autoComplete={field.autoComplete || 'off'}
                      inputMode={field.inputMode || 'text'}
                      onChange={(event) => handleFieldChange(field.key, event.target.value)}
                    />
                  )}
                </label>
              )
            })}
          </div>

          <div className="delivery-profile__footer">
            <div className="delivery-profile__footer-copy" aria-live="polite">
              {saveError ? (
                <span className="delivery-profile__footer-note delivery-profile__footer-note--error">
                  {saveError.message || 'Не удалось сохранить данные доставки.'}
                </span>
              ) : saveStamp ? (
                <span className="delivery-profile__footer-note delivery-profile__footer-note--success">
                  <IconStateSuccess size={16} />
                  Сервер сохранил текущие данные, форму можно редактировать дальше.
                </span>
              ) : isDirty ? (
                <span className="delivery-profile__footer-note">
                  Есть изменения в форме. Сохраните их перед оформлением заказа.
                </span>
              ) : (
                <span className="delivery-profile__footer-note">
                  Храните актуальный адрес здесь, чтобы не вводить его заново при заказе.
                </span>
              )}
            </div>

            <button
              type="submit"
              className="delivery-profile__save-button pressable"
              disabled={saving || loading || !userId}
              aria-busy={saving}
            >
              {'Сохранить данные'}
            </button>
          </div>
        </motion.form>
      </div>
    </div>
  )
}
