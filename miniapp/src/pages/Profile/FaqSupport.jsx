import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { fetchFaq } from '../../api/faq'
import StateSurface from '../../components/ui/StateSurface'
import {
  IconArrowLeft,
  IconChevronDown,
  IconExternalLink,
  IconStateAlert,
  IconStateRetry,
  IconSupport,
} from '../../components/ui/Icons'
import { BUYER_MOTION } from '../../constants/buyerMotion'
import { useTelegram } from '../../hooks/useTelegram'
import { normalizeAdminSupport, openAdminSupportChat } from '../../utils/support'
import './FaqSupport.css'

function buildFaqAnswerBlocks(answer) {
  const normalizedAnswer = String(answer || '').replace(/\r\n/g, '\n').trim()
  if (!normalizedAnswer) {
    return []
  }

  return normalizedAnswer
    .split(/\n{2,}/)
    .map((section) => section.trim())
    .filter(Boolean)
    .flatMap((section) => {
      const lines = section
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)

      const blocks = []
      let paragraphLines = []
      let listItems = []

      const flushParagraph = () => {
        if (!paragraphLines.length) {
          return
        }
        blocks.push({
          type: 'paragraph',
          text: paragraphLines.join(' '),
        })
        paragraphLines = []
      }

      const flushList = () => {
        if (!listItems.length) {
          return
        }
        blocks.push({
          type: 'list',
          items: listItems,
        })
        listItems = []
      }

      lines.forEach((line) => {
        if (/^[-•]\s+/.test(line)) {
          flushParagraph()
          listItems.push(line.replace(/^[-•]\s+/, ''))
          return
        }

        flushList()
        paragraphLines.push(line)
      })

      flushParagraph()
      flushList()

      return blocks
    })
}

export default function FaqSupport({
  active = true,
  supportLink,
  onBack,
  onRequestOpenOrderGuide,
}) {
  const prefersReducedMotion = useReducedMotion()
  const { haptic, tg } = useTelegram()
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(0)

  const resolvedSupport = useMemo(
    () => normalizeAdminSupport(supportLink),
    [supportLink],
  )

  const loadFaq = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const data = await fetchFaq()
      setPayload(data)

      const firstItemId = Number(data?.items?.[0]?.id || 0)
      setExpandedId((currentExpandedId) => (
        currentExpandedId && data?.items?.some?.((item) => item.id === currentExpandedId)
          ? currentExpandedId
          : firstItemId
      ))
      setError(null)
    } catch (requestError) {
      setError(requestError)
      setPayload(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!active) {
      return undefined
    }

    loadFaq()
    return undefined
  }, [active, loadFaq])

  const handleBack = useCallback(() => {
    haptic?.('light')
    onBack?.()
  }, [haptic, onBack])

  const handleToggle = useCallback((itemId) => {
    haptic?.('light')
    setExpandedId((currentExpandedId) => (currentExpandedId === itemId ? 0 : itemId))
  }, [haptic])

  const handleContactOperator = useCallback(() => {
    openAdminSupportChat(resolvedSupport, { tg, haptic })
  }, [haptic, resolvedSupport, tg])

  const handleOpenDetails = useCallback((url) => {
    const targetUrl = String(url || '').trim()
    if (!targetUrl) {
      return
    }

    try {
      if (typeof tg?.openLink === 'function') {
        tg.openLink(targetUrl)
      } else if (typeof window.open === 'function') {
        window.open(targetUrl, '_blank', 'noopener,noreferrer')
      } else {
        window.location.href = targetUrl
      }

      haptic?.('light')
    } catch {
      haptic?.('error')
    }
  }, [haptic, tg])

  const handleOpenOrderGuide = useCallback(() => {
    haptic?.('light')
    onRequestOpenOrderGuide?.()
  }, [haptic, onRequestOpenOrderGuide])

  const items = Array.isArray(payload?.items) ? payload.items : []

  return (
    <div className="page faq-support buyer-page buyer-page--faq">
      <div className="faq-support__header">
        <button type="button" className="faq-support__back pressable" onClick={handleBack}>
          <IconArrowLeft size={20} />
        </button>

        <div className="faq-support__header-copy">
          <h1 className="faq-support__title">FAQ и поддержка</h1>
          <p className="faq-support__subtitle">{'Ответы на часто задаваемые\nвопросы и связь с оператором'}</p>
        </div>

        {false ? (
          <button
            type="button"
            className="faq-support__manage pressable"
            onClick={undefined}
          >
            {null}
            <span>Управлять</span>
          </button>
        ) : null}
      </div>

      <div className="page-content faq-support__content" data-shell-swipe-block="true">
        {loading ? (
          <StateSurface
            tone="progress"
            compact
            eyebrow="FAQ"
            title="Загружаем ответы"
            body="Подтягиваем актуальные вопросы и ответы из панели управления."
            icon={<IconStateRetry size={22} />}
          />
        ) : error ? (
          <StateSurface
            tone="error"
            eyebrow="Поддержка"
            title="Не удалось открыть FAQ"
            body="Экран сохранил структуру, но список вопросов сейчас не загрузился. Можно повторить запрос или сразу написать оператору."
            actionLabel="Повторить"
            onAction={loadFaq}
            icon={<IconStateAlert size={22} />}
          />
        ) : (
          <>
            <div className="faq-support__list" role="list">
              {items.map((item, index) => {
                const isOpen = expandedId === item.id
                const answerBlocks = buildFaqAnswerBlocks(item.answer)
                const buttonLabel = String(item.button_label || '').trim() || (item.link_url ? 'Подробнее' : '')
                const normalizedButtonLabel = buttonLabel.toLowerCase().replace(/\s+/g, ' ').trim()
                const isOrderGuideAction = normalizedButtonLabel === 'пройти обучение'
                const hasActionButton = Boolean(buttonLabel)
                const isActionInteractive = isOrderGuideAction
                  ? typeof onRequestOpenOrderGuide === 'function'
                  : Boolean(item.link_url)

                return (
                  <motion.article
                    key={item.id}
                    className={`faq-support__item card${isOpen ? ' faq-support__item--open' : ''}`}
                    initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ ...(prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard), delay: index * 0.03 }}
                    role="listitem"
                  >
                    <button
                      type="button"
                      className="faq-support__trigger pressable"
                      onClick={() => handleToggle(item.id)}
                      aria-expanded={isOpen}
                    >
                      <span className="faq-support__question-index">{index + 1}</span>
                      <span className="faq-support__question">{item.question}</span>
                      <span
                        className={`faq-support__chevron${isOpen ? ' faq-support__chevron--open' : ''}`}
                        aria-hidden="true"
                      >
                        <IconChevronDown size={18} />
                      </span>
                    </button>

                    <AnimatePresence initial={false}>
                      {isOpen ? (
                        <motion.div
                          className="faq-support__answer-wrap"
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard}
                        >
                          <div className="faq-support__answer-panel">
                            <div className="faq-support__answer-card">
                              <div className="faq-support__answer">
                                {answerBlocks.map((block, blockIndex) => (
                                  block.type === 'list' ? (
                                    <ul key={`${item.id}-block-${blockIndex}`} className="faq-support__answer-list">
                                      {block.items.map((listItem, listIndex) => (
                                        <li
                                          key={`${item.id}-block-${blockIndex}-item-${listIndex}`}
                                          className="faq-support__answer-list-item"
                                        >
                                          {listItem}
                                        </li>
                                      ))}
                                    </ul>
                                  ) : (
                                    <p
                                      key={`${item.id}-block-${blockIndex}`}
                                      className="faq-support__answer-paragraph"
                                    >
                                      {block.text}
                                    </p>
                                  )
                                ))}
                              </div>

                              {hasActionButton ? (
                                <button
                                  type="button"
                                  className={`faq-support__details-button${isActionInteractive ? ' pressable' : ' faq-support__details-button--static'}`}
                                  onClick={isActionInteractive
                                    ? (isOrderGuideAction
                                        ? handleOpenOrderGuide
                                        : () => handleOpenDetails(item.link_url))
                                    : undefined}
                                  disabled={!isActionInteractive}
                                >
                                  <span>{buttonLabel}</span>
                                  {isActionInteractive && !isOrderGuideAction ? <IconExternalLink size={18} /> : null}
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </motion.div>
                      ) : null}
                    </AnimatePresence>
                  </motion.article>
                )
              })}
            </div>

            <section className="faq-support__operator card">
              <div className="faq-support__operator-copy">
                <span className="faq-support__operator-label">Нужен живой ответ?</span>
                <p className="faq-support__operator-text">
                  Если нужного вопроса нет в списке, откройте чат с оператором прямо из
                  мини-приложения.
                </p>
              </div>

              <button
                type="button"
                className="faq-support__operator-button pressable"
                onClick={handleContactOperator}
              >
                <IconSupport size={18} />
                <span>Связь с оператором</span>
              </button>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
