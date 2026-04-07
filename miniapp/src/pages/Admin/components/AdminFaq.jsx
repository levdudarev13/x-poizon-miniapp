import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { deleteAdminFaq, fetchAdminFaq, saveAdminFaq } from '../../../api/faq.js'
import { IconLink, IconPlus, IconSupport, IconTrash } from '../../../components/ui/Icons.jsx'
import { ADMIN_MOTION } from '../adminShared.js'
import { AdminBackIcon, AdminModalPortal } from './AdminSharedBits.jsx'
import { AdminSectionShell } from './AdminSectionShell.jsx'

const SCREEN_ENTRY = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: ADMIN_MOTION.standard,
}

function createEmptyDraft() {
  return {
    id: 0,
    question: '',
    answer: '',
    linkUrl: '',
    buttonLabel: '',
  }
}

function normalizeDraft(entry) {
  return {
    id: Number(entry?.id || 0),
    question: String(entry?.question || ''),
    answer: String(entry?.answer || ''),
    linkUrl: String(entry?.link_url || ''),
    buttonLabel: String(entry?.button_label || ''),
  }
}

function FaqEditorDialog({
  draft,
  saving,
  error,
  onChange,
  onClose,
  onSubmit,
}) {
  const modeLabel = draft.id ? 'Редактирование' : 'Новый вопрос'
  const submitLabel = draft.id ? 'Сохранить изменения' : 'Добавить вопрос'

  return (
    <AdminModalPortal>
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
          className="admin-modal__card admin-faq__dialog"
          role="dialog"
          aria-modal="true"
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 18 }}
          transition={ADMIN_MOTION.standard}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="admin-modal__copy">
            <span className="admin-shell__eyebrow">{modeLabel}</span>
            <h3 className="admin-modal__title">Настройка карточки FAQ</h3>
          </div>

          <form className="admin-modal__body admin-modal__body--form admin-faq__dialog-body" onSubmit={onSubmit}>
            <label className="admin-modal__field">
              <span className="admin-modal__field-label">Вопрос</span>
              <div className="admin-modal__input-wrap">
                <input
                  className="admin-modal__input"
                  type="text"
                  value={draft.question}
                  maxLength={180}
                  placeholder="Например: Как считается итоговая стоимость?"
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => onChange('question', event.target.value)}
                />
              </div>
            </label>

            <label className="admin-modal__field">
              <span className="admin-modal__field-label">Ответ</span>
              <div className="admin-faq__textarea-wrap">
                <textarea
                  className="admin-faq__textarea"
                  value={draft.answer}
                  rows={7}
                  maxLength={2400}
                  placeholder="Опишите ответ так, как он должен отображаться в buyer-FAQ."
                  spellCheck={false}
                  onChange={(event) => onChange('answer', event.target.value)}
                />
              </div>
            </label>

            <label className="admin-modal__field">
              <span className="admin-modal__field-label">Текст кнопки</span>
              <div className="admin-modal__input-wrap">
                <input
                  className="admin-modal__input"
                  type="text"
                  value={draft.buttonLabel}
                  maxLength={80}
                  placeholder="Например: Подробнее или Пройти обучение"
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => onChange('buttonLabel', event.target.value)}
                />
              </div>
              <p className="admin-faq__field-note">Если оставить пусто и указать ссылку, buyer-FAQ автоматически покажет кнопку «Подробнее».</p>
            </label>

            <label className="admin-modal__field">
              <span className="admin-modal__field-label">Ссылка для кнопки</span>
              <div className="admin-modal__input-wrap">
                <input
                  className="admin-modal__input"
                  type="url"
                  value={draft.linkUrl}
                  maxLength={640}
                  placeholder="https://vk.ru/@logisticsx-pricing"
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => onChange('linkUrl', event.target.value)}
                />
              </div>
              <p className="admin-faq__field-note">Если ссылка пустая, кнопка останется визуальной и без действия.</p>
            </label>

            {error ? <span className="admin-modal__error">{error}</span> : null}

            <div className="admin-modal__actions">
              <button type="button" className="admin-pricing__ghost pressable" onClick={onClose}>
                Отмена
              </button>
              <button type="submit" className="admin-modal__submit pressable" disabled={saving}>
                {saving ? 'Сохраняем...' : submitLabel}
              </button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AdminModalPortal>
  )
}

function FaqDeleteDialog({ item, deleting, onClose, onConfirm }) {
  return (
    <AdminModalPortal>
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
          className="admin-modal__card admin-faq__dialog"
          role="dialog"
          aria-modal="true"
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 18 }}
          transition={ADMIN_MOTION.standard}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="admin-modal__copy">
            <span className="admin-shell__eyebrow">Удаление</span>
            <h3 className="admin-modal__title">Удалить вопрос из FAQ?</h3>
          </div>

          <div className="admin-modal__body admin-faq__dialog-body">
            <div className="admin-modal__current">
              <span className="admin-modal__current-label">Будет удалено</span>
              <strong className="admin-modal__current-value">{item?.question || 'Вопрос FAQ'}</strong>
            </div>

            <p className="admin-faq__delete-copy">
              После удаления карточка исчезнет из buyer-FAQ. Если ответ ещё нужен, лучше сначала изменить его.
            </p>

            <div className="admin-modal__actions">
              <button type="button" className="admin-pricing__ghost pressable" onClick={onClose}>
                Отмена
              </button>
              <button
                type="button"
                className="admin-modal__submit admin-pricing__ghost--danger pressable"
                disabled={deleting}
                onClick={onConfirm}
              >
                {deleting ? 'Удаляем...' : 'Удалить'}
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AdminModalPortal>
  )
}

export function AdminFaq({ initData, onBack, haptic }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [payload, setPayload] = useState(null)
  const [notice, setNotice] = useState(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [draft, setDraft] = useState(() => createEmptyDraft())
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const loadFaq = useCallback(async ({ mode = 'full' } = {}) => {
    if (mode === 'full') {
      setLoading(true)
      setError('')
    }

    try {
      const data = await fetchAdminFaq({ initData })
      setPayload(data)
      setError('')
    } catch (requestError) {
      const message = requestError.message || 'Не удалось загрузить FAQ.'

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
  }, [initData, payload])

  useEffect(() => {
    let mounted = true

    fetchAdminFaq({ initData })
      .then((data) => {
        if (!mounted) return
        setPayload(data)
        setError('')
      })
      .catch((requestError) => {
        if (!mounted) return
        setError(requestError.message || 'Не удалось загрузить FAQ.')
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })

    return () => {
      mounted = false
    }
  }, [initData])

  const items = useMemo(() => (
    Array.isArray(payload?.items) ? payload.items : []
  ), [payload])

  const openCreateDialog = useCallback(() => {
    setDraft(createEmptyDraft())
    setFormError('')
    setEditorOpen(true)
    haptic?.('light')
  }, [haptic])

  const openEditDialog = useCallback((item) => {
    setDraft(normalizeDraft(item))
    setFormError('')
    setEditorOpen(true)
    haptic?.('light')
  }, [haptic])

  const closeEditorDialog = useCallback(() => {
    if (saving) {
      return
    }

    setEditorOpen(false)
    setFormError('')
    setDraft(createEmptyDraft())
  }, [saving])

  const handleDraftChange = useCallback((field, value) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }))
    setFormError('')
  }, [])

  const handleSave = useCallback(async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    setNotice(null)

    try {
      const data = await saveAdminFaq({
        initData,
        id: draft.id,
        question: draft.question,
        answer: draft.answer,
        linkUrl: draft.linkUrl,
        buttonLabel: draft.buttonLabel,
      })

      setPayload(data)
      setEditorOpen(false)
      setDraft(createEmptyDraft())
      setNotice({
        type: 'success',
        text: draft.id ? 'Карточка FAQ обновлена.' : 'Новый вопрос добавлен в FAQ.',
      })
      haptic?.('success')
    } catch (requestError) {
      setFormError(requestError.message || 'Не удалось сохранить карточку FAQ.')
      haptic?.('error')
    } finally {
      setSaving(false)
    }
  }, [draft.answer, draft.buttonLabel, draft.id, draft.linkUrl, draft.question, haptic, initData])

  const openDeleteDialog = useCallback((item) => {
    setDeleteTarget(item)
    setNotice(null)
    haptic?.('light')
  }, [haptic])

  const closeDeleteDialog = useCallback(() => {
    if (deleting) {
      return
    }

    setDeleteTarget(null)
  }, [deleting])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget?.id) {
      return
    }

    setDeleting(true)
    setNotice(null)

    try {
      const data = await deleteAdminFaq({
        initData,
        id: deleteTarget.id,
      })

      setPayload(data)
      setDeleteTarget(null)
      setNotice({ type: 'success', text: 'Карточка FAQ удалена.' })
      haptic?.('success')
    } catch (requestError) {
      setNotice({
        type: 'error',
        text: requestError.message || 'Не удалось удалить карточку FAQ.',
      })
      haptic?.('error')
    } finally {
      setDeleting(false)
    }
  }, [deleteTarget?.id, haptic, initData])

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
        <h1 className="admin-shell__detail-title">FAQ и поддержка</h1>
      </div>
    </div>
  )

  if (loading) {
    return (
      <motion.div {...SCREEN_ENTRY}>
        <AdminSectionShell
          topbar={topbar}
          contentClassName="admin-faq__list"
          data-shell-swipe-block="true"
        >
          {[1, 2, 3].map((item) => (
            <div key={item} className="admin-skeleton card">
              <div className="admin-skeleton__line" style={{ width: '32%' }} />
              <div className="admin-skeleton__line" style={{ width: '86%' }} />
              <div className="admin-skeleton__line" style={{ width: '100%', height: 88, borderRadius: 18 }} />
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
              <strong>Не удалось загрузить FAQ</strong>
              <span>{error}</span>
            </div>
            <button
              type="button"
              className="admin-pricing__ghost pressable"
              onClick={() => loadFaq({ mode: 'full' })}
            >
              Повторить
            </button>
          </div>
        </AdminSectionShell>
      </motion.div>
    )
  }

  const hero = (
    <section className="admin-faq__hero card">
      <div className="admin-faq__hero-copy">
        <span className="admin-shell__eyebrow">База ответов</span>
        <h2 className="admin-faq__hero-title">Управляй экраном FAQ прямо из админки</h2>
        <p className="admin-faq__hero-subtitle">
          Здесь можно добавить новые вопросы, обновить формулировки и убрать неактуальные ответы без правок кода.
        </p>
      </div>

      <div className="admin-faq__hero-actions">
        <div className="admin-faq__hero-stat">
          <span className="admin-faq__hero-stat-label">Карточек</span>
          <strong className="admin-faq__hero-stat-value">{payload?.stats?.total || 0}</strong>
        </div>
        <div className="admin-faq__hero-stat">
          <span className="admin-faq__hero-stat-label">Последнее изменение</span>
          <strong className="admin-faq__hero-stat-value">{payload?.stats?.latest_updated_at_label || '—'}</strong>
        </div>
        <button type="button" className="admin-faq__add pressable" onClick={openCreateDialog}>
          <IconPlus size={16} />
          <span>Добавить вопрос</span>
        </button>
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
        contentClassName="admin-faq__list"
        data-shell-swipe-block="true"
      >
        {items.length ? (
          items.map((item, index) => (
            <motion.article
              key={item.id}
              className="admin-faq__item card"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ ...ADMIN_MOTION.standard, delay: index * 0.03 }}
            >
              <div className="admin-faq__item-head">
                <div className="admin-faq__item-index">{String(index + 1).padStart(2, '0')}</div>
                <div className="admin-faq__item-copy">
                  <h3 className="admin-faq__item-question">{item.question}</h3>
                  <span className="admin-faq__item-meta">Обновлено {item.updated_at_label}</span>
                </div>
              </div>

              <p className="admin-faq__item-answer">{item.answer}</p>

              {item.link_url ? (
                <a
                  className="admin-faq__item-link"
                  href={item.link_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <IconLink size={14} />
                  <span>{item.link_url}</span>
                </a>
              ) : null}

              {item.button_label ? (
                <div className="admin-faq__item-link admin-faq__item-link--static">
                  <IconLink size={14} />
                  <span>Кнопка: {item.button_label}</span>
                </div>
              ) : null}

              <div className="admin-faq__item-actions">
                <button
                  type="button"
                  className="admin-pricing__ghost pressable"
                  onClick={() => openEditDialog(item)}
                >
                  Изменить
                </button>
                <button
                  type="button"
                  className="admin-pricing__ghost admin-pricing__ghost--danger pressable"
                  onClick={() => openDeleteDialog(item)}
                >
                  <IconTrash size={15} />
                  <span>Удалить</span>
                </button>
              </div>
            </motion.article>
          ))
        ) : (
          <section className="admin-faq__empty card">
            <div className="admin-faq__empty-icon">
              <IconSupport size={22} />
            </div>
            <div className="admin-faq__empty-copy">
              <strong className="admin-faq__empty-title">FAQ пока пустой</strong>
              <span className="admin-faq__empty-text">
                Добавьте первый вопрос, и он сразу появится в buyer-разделе FAQ и поддержки.
              </span>
            </div>
            <button type="button" className="admin-faq__add pressable" onClick={openCreateDialog}>
              <IconPlus size={16} />
              <span>Создать первую карточку</span>
            </button>
          </section>
        )}

        <AnimatePresence>
          {editorOpen ? (
            <FaqEditorDialog
              draft={draft}
              saving={saving}
              error={formError}
              onChange={handleDraftChange}
              onClose={closeEditorDialog}
              onSubmit={handleSave}
            />
          ) : null}
        </AnimatePresence>

        <AnimatePresence>
          {deleteTarget ? (
            <FaqDeleteDialog
              item={deleteTarget}
              deleting={deleting}
              onClose={closeDeleteDialog}
              onConfirm={handleDelete}
            />
          ) : null}
        </AnimatePresence>
      </AdminSectionShell>
    </motion.div>
  )
}
