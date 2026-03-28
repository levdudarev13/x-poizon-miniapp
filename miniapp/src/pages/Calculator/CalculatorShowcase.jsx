import { useReducedMotion } from 'framer-motion'
import ProductThumb from '../../components/ui/ProductThumb'
import { IconChevronRight } from '../../components/ui/Icons'
import { splitShowcaseRows } from './showcaseRows.js'

const SHOWCASE_FALLBACK_NAME = '\u0422\u043e\u0432\u0430\u0440 \u0431\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f'
const SHOWCASE_EMPTY = '\u041f\u043e\u0441\u043b\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u044f \u0441\u0441\u044b\u043b\u043e\u043a \u0437\u0434\u0435\u0441\u044c \u043f\u043e\u044f\u0432\u044f\u0442\u0441\u044f \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0438 \u0432\u0438\u0442\u0440\u0438\u043d\u044b.'

function CalculatorShowcaseRow({ items, reverse = false, onSelect, reducedMotion }) {
  if (!Array.isArray(items) || !items.length) {
    return null
  }

  const shouldAnimate = !reducedMotion && items.length > 0
  const baseLoopItems = shouldAnimate
    ? Array.from({ length: Math.max(1, Math.ceil(6 / items.length)) }, () => items).flat()
    : items
  const loopItems = shouldAnimate ? [...baseLoopItems, ...baseLoopItems] : items
  const animationDuration = `${Math.max(18, baseLoopItems.length * 4.6)}s`

  return (
    <div className={`calc-showcase__lane${shouldAnimate ? '' : ' calc-showcase__lane--static'}`}>
      <div
        className={`calc-showcase__track${reverse ? ' calc-showcase__track--reverse' : ''}${shouldAnimate ? '' : ' calc-showcase__track--static'}`}
        style={shouldAnimate ? { '--showcase-duration': animationDuration } : undefined}
      >
        {loopItems.map((item, index) => {
          const isClone = shouldAnimate && index >= baseLoopItems.length
          const isInteractive = typeof onSelect === 'function' && (item.productData || item.sourceData || item.href)

          return (
            <button
              key={`${item.id ?? item.name ?? 'showcase'}-${index}`}
              type="button"
              className={`calc-showcase__card pressable${isInteractive ? '' : ' calc-showcase__card--static'}`}
              style={{ '--showcase-accent': item.accentColor || '#00c8c8' }}
              disabled={!isInteractive}
              aria-hidden={isClone ? 'true' : undefined}
              tabIndex={isClone ? -1 : 0}
              onClick={() => {
                if (!isInteractive) return
                onSelect(item)
              }}
            >
              <ProductThumb
                src={item.imageUrl}
                alt=""
                size="md"
                className="calc-showcase__thumb"
                fallbackLabel={item.name || item.sourceLabel}
              />

              <span className="calc-showcase__card-copy">
                <span className="calc-showcase__card-name">{item.name || SHOWCASE_FALLBACK_NAME}</span>
                {item.priceLabel ? (
                  <span className="calc-showcase__card-price">{item.priceLabel}</span>
                ) : null}
              </span>

              {isInteractive ? (
                <span className="calc-showcase__card-arrow" aria-hidden="true">
                  <IconChevronRight size={18} />
                </span>
              ) : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function CalculatorShowcase({ items, onSelect, actions = null }) {
  const prefersReducedMotion = useReducedMotion()
  const hasItems = Array.isArray(items) && items.length > 0

  if (!hasItems && !actions) {
    return null
  }

  const normalizedItems = hasItems ? items : []
  const { firstRow, secondRow } = splitShowcaseRows(normalizedItems)
  const hasVisibleRows = firstRow.length > 0 || secondRow.length > 0

  return (
    <section className="calc-showcase" aria-label="Витрина товаров">
      {actions ? (
        <div className="calc-showcase__header">
          {actions}
        </div>
      ) : null}

      <div className="calc-showcase__surface">
        <div className="calc-showcase__fade calc-showcase__fade--left" aria-hidden="true" />
        <div className="calc-showcase__fade calc-showcase__fade--right" aria-hidden="true" />

        {firstRow.length ? (
          <CalculatorShowcaseRow
            items={firstRow}
            onSelect={onSelect}
            reducedMotion={prefersReducedMotion}
          />
        ) : null}

        {secondRow.length ? (
          <CalculatorShowcaseRow
            items={secondRow}
            reverse
            onSelect={onSelect}
            reducedMotion={prefersReducedMotion}
          />
        ) : null}

        {!hasVisibleRows ? (
          <div className="calc-showcase__empty">
            {SHOWCASE_EMPTY}
          </div>
        ) : null}
      </div>
    </section>
  )
}
