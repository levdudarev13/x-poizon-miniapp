import { IconQuestion } from './Icons'
import { useTelegram } from '../../hooks/useTelegram'
import { requestOpenFaqQuestion } from '../../utils/faqNavigation'
import { POIZON_MANUAL_VARIANT_HINT_TEXT } from '../../utils/productVariants'

export default function PoizonManualChoiceHint({
  className = '',
  faqQuestionIndex = 4,
}) {
  const { haptic } = useTelegram()
  const hintLines = String(POIZON_MANUAL_VARIANT_HINT_TEXT || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  const [firstLine = '', secondLine = ''] = hintLines

  const handleOpenFaq = (event) => {
    event.preventDefault()
    event.stopPropagation()
    haptic?.('light')
    requestOpenFaqQuestion(faqQuestionIndex)
  }

  return (
    <p className={`poizon-manual-choice-hint${className ? ` ${className}` : ''}`}>
      {firstLine ? (
        <span className="poizon-manual-choice-hint__line">{firstLine}</span>
      ) : null}
      {secondLine ? (
        <span className="poizon-manual-choice-hint__line">
          <span>{secondLine}</span>
          <button
            type="button"
            className="poizon-manual-choice-hint__faq-button pressable"
            aria-label="Открыть FAQ и 4 вопрос"
            onClick={handleOpenFaq}
          >
            <IconQuestion size={15} />
          </button>
        </span>
      ) : null}
    </p>
  )
}
