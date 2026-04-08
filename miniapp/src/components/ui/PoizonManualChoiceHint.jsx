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
  const questionMarker = '95'
  const questionMarkerIndex = secondLine.lastIndexOf(questionMarker)
  const secondLineBeforeMarker = questionMarkerIndex >= 0
    ? secondLine.slice(0, questionMarkerIndex + questionMarker.length)
    : secondLine
  const secondLineAfterMarker = questionMarkerIndex >= 0
    ? secondLine.slice(questionMarkerIndex + questionMarker.length)
    : ''

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
          <span className="poizon-manual-choice-hint__line-copy">
            {secondLineBeforeMarker}
            <button
              type="button"
              className="poizon-manual-choice-hint__faq-button pressable"
              aria-label="Открыть FAQ и 4 вопрос"
              onClick={handleOpenFaq}
            >
              <IconQuestion size={18} />
            </button>
            {secondLineAfterMarker}
          </span>
        </span>
      ) : null}
    </p>
  )
}
