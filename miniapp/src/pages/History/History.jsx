import { useCallback, useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import StateSurface from '../../components/ui/StateSurface'
import {
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
} from '../../components/ui/Icons'
import BrandGemIcon from '../../components/ui/BrandGemIcon'
import ProductThumb from '../../components/ui/ProductThumb'
import { BUYER_MOTION } from '../../constants/buyerMotion'
import { formatBuyerRub } from '../../constants/buyerNumbers'
import { BUYER_STATE_COPY } from '../../constants/buyerStateContent'
import { useTelegram } from '../../hooks/useTelegram'
import { repairMojibakeDeep } from '../../utils/text'
import './History.css'

const HISTORY_STATE_ICONS = {
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
}

function getHistoryStateIcon(iconName) {
  const Icon = HISTORY_STATE_ICONS[iconName]
  return Icon ? <Icon size={24} /> : null
}

function HistoryState({
  eyebrow,
  title,
  body,
  tone = 'neutral',
  actionLabel,
  onAction,
  icon,
  compact = false,
}) {
  return (
    <div className="hist-body hist-body--state">
      <StateSurface
        tone={tone}
        eyebrow={eyebrow}
        title={title}
        body={body}
        actionLabel={actionLabel}
        onAction={onAction}
        icon={icon}
        compact={compact}
      />
    </div>
  )
}

export default function History({ onOpenProduct, active }) {
  const { userId, haptic } = useTelegram()
  const prefersReducedMotion = useReducedMotion()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchHistory = useCallback(async () => {
    if (!userId) {
      setLoading(false)
      setItems([])
      return
    }

    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`/api/history?user_id=${userId}`)
      const data = repairMojibakeDeep(await response.json())

      if (data.error) {
        throw new Error(data.error)
      }

      setItems(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  useEffect(() => {
    if (active) {
      fetchHistory()
    }
  }, [active, fetchHistory])

  const handleCalc = (item) => {
    haptic?.('medium')
    onOpenProduct?.(item)
  }

  return (
    <div className="page hist-page buyer-page buyer-page--history">
      <div className="page-content hist-content">
        <div className="hist-header">
          <div className="hist-header__sticky">
            <div className="hist-header__frame">
              <h1>История</h1>
              <p className="hist-overview text-secondary">
                {items.length} {items.length === 1 ? 'расчет' : items.length < 5 ? 'расчета' : 'расчетов'}
              </p>
            </div>
          </div>
        </div>

        {loading ? (
          <HistoryState
            tone="progress"
            eyebrow={BUYER_STATE_COPY.history.loading.eyebrow}
            title={BUYER_STATE_COPY.history.loading.title}
            body={BUYER_STATE_COPY.history.loading.body}
            icon={getHistoryStateIcon(BUYER_STATE_COPY.history.loading.iconName)}
            compact
          />
        ) : error ? (
          <HistoryState
            tone="error"
            eyebrow={BUYER_STATE_COPY.history.error.eyebrow}
            title={BUYER_STATE_COPY.history.error.title}
            body={BUYER_STATE_COPY.history.error.body}
            actionLabel={BUYER_STATE_COPY.history.error.actionLabel}
            onAction={fetchHistory}
            icon={getHistoryStateIcon(BUYER_STATE_COPY.history.error.iconName)}
          />
        ) : !items.length ? (
          <HistoryState
            eyebrow={BUYER_STATE_COPY.history.empty.eyebrow}
            title={BUYER_STATE_COPY.history.empty.title}
            body={BUYER_STATE_COPY.history.empty.body}
            icon={getHistoryStateIcon(BUYER_STATE_COPY.history.empty.iconName)}
          />
        ) : (
          <div className="hist-body">
            <div className="hist-grid">
              {items.map((item, index) => {
                const totalRub = item.subtotal_rub || item.total_with_margin_rub

                return (
                  <motion.article
                    key={item.id}
                    className="hist-card"
                    initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{
                      ...(prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.standard),
                      delay: prefersReducedMotion ? 0 : Math.min(index * 0.04, 0.24),
                    }}
                  >
                    <div className="hist-card__media">
                      <div className="hist-card__media-shell">
                        <ProductThumb
                          src={item.image_url}
                          alt=""
                          className="hist-card__thumb"
                          fallbackLabel={item.name || 'Товар'}
                          size="lg"
                        />
                      </div>
                    </div>

                    <div className="hist-card__body">
                      <p className="hist-card__name">{item.name || 'Без названия'}</p>

                      <div className="hist-card__footer">
                        <span className="hist-card__price">{formatBuyerRub(totalRub)}</span>

                        <button
                          type="button"
                          className="hist-card__calc ui-icon-button"
                          aria-label="Открыть расчет"
                          onClick={() => handleCalc(item)}
                        >
                          <BrandGemIcon className="hist-card__calc-art" />
                        </button>
                      </div>
                    </div>
                  </motion.article>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
