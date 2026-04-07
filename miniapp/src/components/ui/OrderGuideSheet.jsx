import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'motion/react'
import cn from '../../lib/utils'
import { formatBuyerRub } from '../../constants/buyerNumbers'
import DotPattern from '../../registry/magicui/dot-pattern'
import Iphone from '../../registry/magicui/iphone'
import Cart from '../../pages/Cart/Cart'
import Orders from '../../pages/Orders/Orders'
import Profile from '../../pages/Profile/Profile'
import { IconCheck, IconTrash } from './Icons'
import TextType from './TextType'
import Stepper, { Step } from './Stepper'
import './OrderGuideSheet.css'

const ORDER_GUIDE_STEP_COUNT = 9
const ORDER_GUIDE_SPOTLIGHT_WINDOW_PADDING = {
  top: 12,
  right: 0,
  bottom: 12,
  left: 0,
}
const ORDER_GUIDE_SPOTLIGHT_FEATHER_PADDING = {
  top: 46,
  right: 34,
  bottom: 46,
  left: 34,
}
const ORDER_GUIDE_STEP_FIVE_SEQUENCE = {
  primaryText: 0,
  sizeFocus: 1,
  secondaryText: 2,
  ctaFocus: 3,
  detailFocus: 4,
}
const ORDER_GUIDE_STEP_FIVE_SEQUENCE_DELAY_MS = 500
const ORDER_GUIDE_STEP_NINE_PRIMARY_COPY = 'Всего через несколько минут с вами свяжется оператор для уточнения деталей и оплаты.'
const ORDER_GUIDE_STEP_NINE_SECONDARY_COPY = 'Получить трек-номер и отслеживать статус заказа вы можете во вкладке мои заказы'
const ORDER_GUIDE_STEP_EIGHT_PRIMARY_COPY = 'Выберите тип доставки'
const ORDER_GUIDE_STEP_EIGHT_SECONDARY_COPY = 'и оформите заказ'
const ORDER_GUIDE_PROFILE_PREVIEW = {
  displayName: 'Buyer 101',
  username: 'buyer101',
  deliveryComplete: false,
}

function OrderGuidePortal({ children }) {
  if (typeof document === 'undefined') {
    return children
  }

  return createPortal(children, document.body)
}

function buildSurroundingRects(rect, boundsWidth, boundsHeight) {
  if (!rect || boundsWidth <= 0 || boundsHeight <= 0) return []

  const top = Math.max(0, rect.top)
  const left = Math.max(0, rect.left)
  const width = Math.max(0, rect.width)
  const height = Math.max(0, rect.height)
  const right = Math.min(boundsWidth, left + width)
  const bottom = Math.min(boundsHeight, top + height)
  const middleHeight = Math.max(0, bottom - top)

  return [
    { top: 0, left: 0, width: boundsWidth, height: top },
    { top, left: 0, width: left, height: middleHeight },
    { top, left: right, width: Math.max(0, boundsWidth - right), height: middleHeight },
    { top: bottom, left: 0, width: boundsWidth, height: Math.max(0, boundsHeight - bottom) },
  ].filter((segment) => segment.width > 0 && segment.height > 0)
}

function normalizeInsets(insets) {
  if (typeof insets === 'number') {
    return {
      top: insets,
      right: insets,
      bottom: insets,
      left: insets,
    }
  }

  return {
    top: Math.max(0, Number(insets?.top ?? 0)),
    right: Math.max(0, Number(insets?.right ?? 0)),
    bottom: Math.max(0, Number(insets?.bottom ?? 0)),
    left: Math.max(0, Number(insets?.left ?? 0)),
  }
}

function expandRect(rect, insets, boundsWidth, boundsHeight) {
  if (!rect || boundsWidth <= 0 || boundsHeight <= 0) return null

  const resolvedInsets = normalizeInsets(insets)
  const left = Math.max(0, rect.left - resolvedInsets.left)
  const top = Math.max(0, rect.top - resolvedInsets.top)
  const right = Math.min(boundsWidth, rect.left + rect.width + resolvedInsets.right)
  const bottom = Math.min(boundsHeight, rect.top + rect.height + resolvedInsets.bottom)

  return {
    top,
    left,
    width: Math.max(0, right - left),
    height: Math.max(0, bottom - top),
  }
}

function OrderGuideSecondaryProgress({ currentStep }) {
  return (
    <div className="order-guide-secondary-progress" aria-hidden="true">
      {Array.from({ length: ORDER_GUIDE_STEP_COUNT }, (_, index) => {
        const step = index + 1
        const status = currentStep === step ? 'active' : currentStep > step ? 'complete' : 'inactive'

        return (
          <Fragment key={`order-guide-secondary-progress-${step}`}>
            <div
              className={cn(
                'order-guide-secondary-progress-step',
                `order-guide-secondary-progress-step--${status}`
              )}
            >
              {status === 'complete' ? (
                <svg
                  className="order-guide-secondary-progress-check"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : status === 'active' ? (
                <span className="order-guide-secondary-progress-dot" />
              ) : (
                <span className="order-guide-secondary-progress-number">{step}</span>
              )}
            </div>
            {step < ORDER_GUIDE_STEP_COUNT ? (
              <div className="order-guide-secondary-progress-connector">
                <span
                  className={cn(
                    'order-guide-secondary-progress-connector-fill',
                    currentStep > step ? 'order-guide-secondary-progress-connector-fill--complete' : ''
                  )}
                />
              </div>
            ) : null}
          </Fragment>
        )
      })}
    </div>
  )
}

function areFocusClonesEqual(previous, next) {
  if (previous === next) return true
  if (!Array.isArray(previous) || !Array.isArray(next) || previous.length !== next.length) return false

  return previous.every((clone, index) => {
    const candidate = next[index]
    return candidate
      && clone.key === candidate.key
      && clone.kind === candidate.kind
      && clone.top === candidate.top
      && clone.left === candidate.left
      && clone.width === candidate.width
      && clone.height === candidate.height
      && clone.className === candidate.className
      && clone.innerHTML === candidate.innerHTML
      && clone.tagName === candidate.tagName
      && clone.dataAttributesSignature === candidate.dataAttributesSignature
  })
}

function extractCloneDataAttributes(node) {
  if (!(node instanceof HTMLElement)) {
    return {}
  }

  return Array.from(node.attributes).reduce((attributes, attribute) => {
    if (!attribute.name.startsWith('data-')) {
      return attributes
    }

    if (
      attribute.name === 'data-order-guide-step-five-target'
      || attribute.name === 'data-order-guide-step-six-target'
      || attribute.name === 'data-order-guide-step-seven-target'
      || attribute.name === 'data-order-guide-step-eight-target'
      || attribute.name === 'data-order-guide-step-nine-target'
    ) {
      return attributes
    }

    attributes[attribute.name] = attribute.value
    return attributes
  }, {})
}

function stringifyCloneDataAttributes(attributes) {
  return JSON.stringify(
    Object.keys(attributes || {})
      .sort()
      .map((name) => [name, attributes[name]])
  )
}

function readGuidePreviewImageUrl(item) {
  if (item?.image_url) return item.image_url

  try {
    const payload = JSON.parse(item?.calc_json || '{}')
    return payload?.product?.image_url || payload?.image_url || ''
  } catch {
    return ''
  }
}

function OrderGuideStepSixCartPreview({ guidePreview }) {
  const previewItem = Array.isArray(guidePreview?.items) ? guidePreview.items[0] || null : null

  if (!previewItem) {
    return null
  }

  const selectedCount = Array.isArray(guidePreview?.selectedIds) ? guidePreview.selectedIds.length : 1
  const total = Number(previewItem.subtotal_rub || previewItem.total_with_margin_rub || 0)
  const title = previewItem.short_name || previewItem.name || 'Товар'
  const imageUrl = readGuidePreviewImageUrl(previewItem)
  const footerActionText = guidePreview?.footerActionText || 'В заявку'

  return (
    <div className="page cart-page buyer-page buyer-page--cart cart-page--guide-preview" aria-hidden="true">
      <div className="page-header">
        <div className="cart-header-row">
          <div>
            <h1>Корзина</h1>
            <p className="text-secondary" style={{ fontSize: 14, marginTop: 4 }}>
              1 товар
            </p>
          </div>
          <button type="button" className="cart-clear-btn pressable" disabled>
            <IconTrash size={18} />
          </button>
        </div>
      </div>

      <div className="page-content">
        <div className="cart-list">
          <div className="cart-card card cart-card--selected" data-order-guide-step-six-target="card">
            <button type="button" className="cart-card__check pressable" disabled>
              <span className="cart-checkbox cart-checkbox--checked">
                <IconCheck size={18} />
              </span>
            </button>

            <div className="cart-card__main pressable">
              <div className="cart-card__accent" />
              {imageUrl ? (
                <img src={imageUrl} alt="" className="cart-card__thumb-img" />
              ) : (
                <div className="cart-card__thumb">
                  <IconCheck size={18} />
                </div>
              )}
              <div className="cart-card__body">
                <div className="cart-card__name">{title}</div>
                <span className="cart-card__price">{formatBuyerRub(total)}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="cart-footer-shell">
          <div className="cart-footer ui-surface-panel">
            <div className="cart-footer__info" title={`Выбрано (${selectedCount}): ${formatBuyerRub(total)}`}>
              <div className="cart-footer__meta">
                <span className="cart-footer__label">{`Выбрано (${selectedCount})`}</span>
              </div>
              <span className="cart-footer__sum">{formatBuyerRub(total)}</span>
            </div>
            <button
              type="button"
              className="cart-footer__submit cart-footer__submit--selected pressable"
              disabled
              aria-label={footerActionText}
              data-order-guide-step-six-target="cta"
            >
              <span className="cart-footer__submit-content">{footerActionText}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function buildFeatherSegments(innerRect, outerRect) {
  if (!innerRect || !outerRect) return []

  const innerTop = innerRect.top
  const innerLeft = innerRect.left
  const innerRight = innerRect.left + innerRect.width
  const innerBottom = innerRect.top + innerRect.height
  const outerTop = outerRect.top
  const outerLeft = outerRect.left
  const outerRight = outerRect.left + outerRect.width
  const outerBottom = outerRect.top + outerRect.height

  return [
    {
      key: 'top-left',
      variant: 'top-left',
      top: outerTop,
      left: outerLeft,
      width: innerLeft - outerLeft,
      height: innerTop - outerTop,
    },
    {
      key: 'top',
      variant: 'top',
      top: outerTop,
      left: innerLeft,
      width: innerRect.width,
      height: innerTop - outerTop,
    },
    {
      key: 'top-right',
      variant: 'top-right',
      top: outerTop,
      left: innerRight,
      width: outerRight - innerRight,
      height: innerTop - outerTop,
    },
    {
      key: 'right',
      variant: 'right',
      top: innerTop,
      left: innerRight,
      width: outerRight - innerRight,
      height: innerRect.height,
    },
    {
      key: 'bottom-right',
      variant: 'bottom-right',
      top: innerBottom,
      left: innerRight,
      width: outerRight - innerRight,
      height: outerBottom - innerBottom,
    },
    {
      key: 'bottom',
      variant: 'bottom',
      top: innerBottom,
      left: innerLeft,
      width: innerRect.width,
      height: outerBottom - innerBottom,
    },
    {
      key: 'bottom-left',
      variant: 'bottom-left',
      top: innerBottom,
      left: outerLeft,
      width: innerLeft - outerLeft,
      height: outerBottom - innerBottom,
    },
    {
      key: 'left',
      variant: 'left',
      top: innerTop,
      left: outerLeft,
      width: innerLeft - outerLeft,
      height: innerRect.height,
    },
  ].filter((segment) => segment.width > 0 && segment.height > 0)
}

function normalizeCloneClassName(className) {
  return String(className || '').replace(/\s+/g, ' ').trim()
}

function removeCloneClassTokens(className, tokens) {
  const tokenSet = new Set(tokens)
  return normalizeCloneClassName(className)
    .split(' ')
    .filter((token) => token && !tokenSet.has(token))
    .join(' ')
}

function buildStepFiveFocusCloneClassName(kind, className) {
  const cleanedClassName = removeCloneClassTokens(className, ['disabled', 'done', 'loading'])

  if (kind === 'size') {
    return normalizeCloneClassName(`${cleanedClassName} active`)
  }

  return cleanedClassName
}

export default function OrderGuideSheet({
  open = false,
  onClose,
  onCurrentStepChange,
  cartGuidePreview = null,
  ordersGuidePreview = null,
}) {
  const [currentStep, setCurrentStep] = useState(1)
  const [overlaySpotlightRect, setOverlaySpotlightRect] = useState(null)
  const [overlayInputHighlightRect, setOverlayInputHighlightRect] = useState(null)
  const [stageSpotlightRect, setStageSpotlightRect] = useState(null)
  const [stageInputHighlightRect, setStageInputHighlightRect] = useState(null)
  const [stepFiveFocusClones, setStepFiveFocusClones] = useState([])
  const [stepFiveSequenceStage, setStepFiveSequenceStage] = useState(ORDER_GUIDE_STEP_FIVE_SEQUENCE.primaryText)
  const [secondSlideOffset, setSecondSlideOffset] = useState(0)
  const stageRef = useRef(null)
  const secondSlideRef = useRef(null)
  const stepFiveSequenceTimeoutRef = useRef(0)
  const isStepTwo = currentStep === 2
  const isStepFour = currentStep === 4
  const isStepFive = currentStep === 5
  const isStepSix = currentStep === 6
  const isStepSeven = currentStep === 7
  const isStepEight = currentStep === 8
  const isStepNine = currentStep === 9
  const isProfileGuideStep = isStepSeven || isStepNine
  const isFullScreenGuideStep = isStepFive || isStepSix || isStepSeven || isStepEight || isStepNine
  const isSpotlightStep = isStepTwo || isStepFour
  const isCompactGuideStep = currentStep === 2 || currentStep === 4

  const clearStepFiveSequenceTimeout = useCallback(() => {
    if (stepFiveSequenceTimeoutRef.current) {
      window.clearTimeout(stepFiveSequenceTimeoutRef.current)
      stepFiveSequenceTimeoutRef.current = 0
    }
  }, [])

  const scheduleStepFiveSequenceStage = useCallback((nextStage) => {
    clearStepFiveSequenceTimeout()
    stepFiveSequenceTimeoutRef.current = window.setTimeout(() => {
      stepFiveSequenceTimeoutRef.current = 0
      setStepFiveSequenceStage((prev) => (prev < nextStage ? nextStage : prev))
    }, ORDER_GUIDE_STEP_FIVE_SEQUENCE_DELAY_MS)
  }, [clearStepFiveSequenceTimeout])

  const handleSequentialGuidePrimaryTypingComplete = useCallback(() => {
    if (
      !open
      || (!isStepEight && !isStepNine)
      || stepFiveSequenceStage !== ORDER_GUIDE_STEP_FIVE_SEQUENCE.primaryText
    ) {
      return
    }

    scheduleStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus)
  }, [isStepEight, isStepNine, open, scheduleStepFiveSequenceStage, stepFiveSequenceStage])

  useEffect(() => {
    if (!open || typeof onClose !== 'function') {
      return undefined
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose, open])

  useEffect(() => {
    if (!open || typeof document === 'undefined') {
      return undefined
    }

    const previousBlockTabSwipe = document.body.dataset.blockTabSwipe
    document.body.dataset.blockTabSwipe = '1'

    return () => {
      document.body.dataset.blockTabSwipe = previousBlockTabSwipe || '0'
    }
  }, [open])

  useEffect(() => {
    if (typeof document === 'undefined') {
      return undefined
    }

    const { body } = document
    const previousSpotlight = body.dataset.orderGuideSpotlight
    const previousTopPadding = body.style.getPropertyValue('--order-guide-spotlight-window-top')
    const previousBottomPadding = body.style.getPropertyValue('--order-guide-spotlight-window-bottom')

    if (open && isSpotlightStep) {
      body.dataset.orderGuideSpotlight = '2'
      body.style.setProperty('--order-guide-spotlight-window-top', `${ORDER_GUIDE_SPOTLIGHT_WINDOW_PADDING.top}px`)
      body.style.setProperty('--order-guide-spotlight-window-bottom', `${ORDER_GUIDE_SPOTLIGHT_WINDOW_PADDING.bottom}px`)
    } else {
      delete body.dataset.orderGuideSpotlight
      body.style.removeProperty('--order-guide-spotlight-window-top')
      body.style.removeProperty('--order-guide-spotlight-window-bottom')
    }

    return () => {
      if (previousSpotlight) {
        body.dataset.orderGuideSpotlight = previousSpotlight
      } else {
        delete body.dataset.orderGuideSpotlight
      }

      if (previousTopPadding) {
        body.style.setProperty('--order-guide-spotlight-window-top', previousTopPadding)
      } else {
        body.style.removeProperty('--order-guide-spotlight-window-top')
      }

      if (previousBottomPadding) {
        body.style.setProperty('--order-guide-spotlight-window-bottom', previousBottomPadding)
      } else {
        body.style.removeProperty('--order-guide-spotlight-window-bottom')
      }
    }
  }, [currentStep, isSpotlightStep, open])

  useEffect(() => {
    if (open) {
      clearStepFiveSequenceTimeout()
      setCurrentStep(1)
      setOverlaySpotlightRect(null)
      setOverlayInputHighlightRect(null)
      setStageSpotlightRect(null)
      setStageInputHighlightRect(null)
      setStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.primaryText)
      setSecondSlideOffset(0)
      onCurrentStepChange?.(1)
    }
  }, [clearStepFiveSequenceTimeout, onCurrentStepChange, open])

  useEffect(() => {
    if (!open || !isFullScreenGuideStep) {
      clearStepFiveSequenceTimeout()
      setStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.primaryText)
      return
    }

    clearStepFiveSequenceTimeout()
    setStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.primaryText)
  }, [clearStepFiveSequenceTimeout, currentStep, isFullScreenGuideStep, open])

  useEffect(() => () => {
    clearStepFiveSequenceTimeout()
  }, [clearStepFiveSequenceTimeout])

  useEffect(() => {
    if (!open || !isFullScreenGuideStep) {
      return undefined
    }

    if (
      (isStepFive || isStepSix || isStepEight || isStepNine)
      && stepFiveSequenceStage === ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus
    ) {
      scheduleStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.secondaryText)
    } else {
      return undefined
    }

    return () => {
      clearStepFiveSequenceTimeout()
    }
  }, [
    clearStepFiveSequenceTimeout,
    isFullScreenGuideStep,
    isStepEight,
    isStepFive,
    isStepNine,
    isStepSix,
    open,
    scheduleStepFiveSequenceStage,
    stepFiveSequenceStage,
  ])

  useLayoutEffect(() => {
    if (!open || !isSpotlightStep || typeof window === 'undefined') {
      setOverlaySpotlightRect(null)
      setOverlayInputHighlightRect(null)
      setStageSpotlightRect(null)
      setStageInputHighlightRect(null)
      setSecondSlideOffset(0)
      return undefined
    }

    const measureSpotlight = () => {
      const target = document.querySelector('.calc-page__input-wrap')
      const stageNode = stageRef.current
      const slideNode = secondSlideRef.current

      if (!target || !stageNode || !slideNode) {
        setOverlaySpotlightRect(null)
        setOverlayInputHighlightRect(null)
        setStageSpotlightRect(null)
        setStageInputHighlightRect(null)
        setSecondSlideOffset(0)
        return
      }

      const targetRect = target.getBoundingClientRect()
      const stageRect = stageNode.getBoundingClientRect()
      const slideRect = slideNode.getBoundingClientRect()

      const overlayInputRect = {
        top: Math.round(targetRect.top),
        left: Math.round(targetRect.left),
        width: Math.round(targetRect.width),
        height: Math.round(targetRect.height),
      }

      const stageInputRect = {
        top: Math.round(targetRect.top - stageRect.top),
        left: Math.round(targetRect.left - stageRect.left),
        width: Math.round(targetRect.width),
        height: Math.round(targetRect.height),
      }

      const normalizedOverlayRect = expandRect(
        overlayInputRect,
        ORDER_GUIDE_SPOTLIGHT_WINDOW_PADDING,
        window.innerWidth,
        window.innerHeight,
      )

      const normalizedStageRect = expandRect(
        stageInputRect,
        ORDER_GUIDE_SPOTLIGHT_WINDOW_PADDING,
        Math.round(stageRect.width),
        Math.round(stageRect.height),
      )

      if (!normalizedOverlayRect || !normalizedStageRect) {
        setOverlaySpotlightRect(null)
        setOverlayInputHighlightRect(null)
        setStageSpotlightRect(null)
        setStageInputHighlightRect(null)
        setSecondSlideOffset(0)
        return
      }

      setOverlaySpotlightRect({
        ...normalizedOverlayRect,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      })
      setOverlayInputHighlightRect({
        ...overlayInputRect,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      })

      setStageSpotlightRect({
        ...normalizedStageRect,
        containerWidth: Math.round(stageRect.width),
        containerHeight: Math.round(stageRect.height),
      })
      setStageInputHighlightRect({
        ...stageInputRect,
        containerWidth: Math.round(stageRect.width),
        containerHeight: Math.round(stageRect.height),
      })

      setSecondSlideOffset(Math.max(
        0,
        normalizedOverlayRect.top
          + normalizedOverlayRect.height
          + ORDER_GUIDE_SPOTLIGHT_FEATHER_PADDING.bottom
          - slideRect.top
          + 12,
      ))
    }

    const frameId = window.requestAnimationFrame(measureSpotlight)
    window.addEventListener('resize', measureSpotlight)
    window.addEventListener('scroll', measureSpotlight, true)

    return () => {
      window.cancelAnimationFrame(frameId)
      window.removeEventListener('resize', measureSpotlight)
      window.removeEventListener('scroll', measureSpotlight, true)
    }
  }, [currentStep, isSpotlightStep, open])

  useLayoutEffect(() => {
    if (!open || !isFullScreenGuideStep || typeof window === 'undefined') {
      setStepFiveFocusClones([])
      return undefined
    }

    setStepFiveFocusClones([])

    const measureStepFiveFocus = () => {
      const focusSelector = isStepFive
        ? '[data-order-guide-step-five-target]'
        : isStepSix
          ? '[data-order-guide-step-six-target]'
          : isStepSeven
            ? '[data-order-guide-step-seven-target]'
            : isStepEight
              ? '[data-order-guide-step-eight-target]'
              : isStepNine
                ? '[data-order-guide-step-nine-target]'
                : ''
      const focusNodes = (focusSelector
        ? Array.from(document.querySelectorAll(focusSelector))
        : [])
        .filter((node) => node instanceof HTMLElement && !node.closest('.order-guide-step-five-focus-layer'))

      if (!focusNodes.length) {
        setStepFiveFocusClones([])
        return
      }

      const nextClones = focusNodes
        .map((node, index) => {
          const rect = node.getBoundingClientRect()
          const dataAttributes = extractCloneDataAttributes(node)
          const kind = isStepFive
            ? node.dataset.orderGuideStepFiveTarget || 'control'
            : isStepSix
              ? node.dataset.orderGuideStepSixTarget || 'control'
              : isStepSeven
                ? node.dataset.orderGuideStepSevenTarget || 'control'
                : isStepEight
                  ? node.dataset.orderGuideStepEightTarget || 'control'
                  : node.dataset.orderGuideStepNineTarget || 'control'
          return {
            key: `${kind}-${index}`,
            kind,
            top: Math.round(rect.top),
            left: Math.round(rect.left),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            className: buildStepFiveFocusCloneClassName(kind, node.className),
            innerHTML: node.innerHTML,
            tagName: node.tagName.toLowerCase(),
            dataAttributes,
            dataAttributesSignature: stringifyCloneDataAttributes(dataAttributes),
            disabled: false,
          }
        })
        .filter((clone) => clone.width > 0 && clone.height > 0)

      setStepFiveFocusClones((previous) => (areFocusClonesEqual(previous, nextClones) ? previous : nextClones))
    }

    const frameId = window.requestAnimationFrame(measureStepFiveFocus)
    const observer = new MutationObserver(() => {
      measureStepFiveFocus()
    })

    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: [
        'class',
        'style',
        'disabled',
        'data-completion-state',
        'data-order-guide-step-five-target',
        'data-order-guide-step-six-target',
        'data-order-guide-step-seven-target',
        'data-order-guide-step-eight-target',
        'data-order-guide-step-nine-target',
      ],
    })

    window.addEventListener('resize', measureStepFiveFocus)
    window.addEventListener('scroll', measureStepFiveFocus, true)

    return () => {
      window.cancelAnimationFrame(frameId)
      observer.disconnect()
      window.removeEventListener('resize', measureStepFiveFocus)
      window.removeEventListener('scroll', measureStepFiveFocus, true)
    }
  }, [currentStep, isFullScreenGuideStep, isStepEight, isStepFive, isStepNine, isStepSix, isStepSeven, open])

  const handleFinalStepCompleted = () => {
    window.setTimeout(() => {
      onClose?.()
    }, 180)
  }

  const overlaySpotlightSegments = overlaySpotlightRect
    ? buildSurroundingRects(
      expandRect(
        overlaySpotlightRect,
        ORDER_GUIDE_SPOTLIGHT_FEATHER_PADDING,
        overlaySpotlightRect.viewportWidth,
        overlaySpotlightRect.viewportHeight,
      ),
      overlaySpotlightRect.viewportWidth,
      overlaySpotlightRect.viewportHeight,
    )
    : []

  const overlayFeatherRect = overlaySpotlightRect
    ? expandRect(
      overlaySpotlightRect,
      ORDER_GUIDE_SPOTLIGHT_FEATHER_PADDING,
      overlaySpotlightRect.viewportWidth,
      overlaySpotlightRect.viewportHeight,
    )
    : null

  const overlayFeatherSegments = overlaySpotlightRect && overlayFeatherRect
    ? buildFeatherSegments(overlaySpotlightRect, overlayFeatherRect)
    : []

  const stageSpotlightSegments = stageSpotlightRect
    ? buildSurroundingRects(
      expandRect(
        stageSpotlightRect,
        ORDER_GUIDE_SPOTLIGHT_FEATHER_PADDING,
        stageSpotlightRect.containerWidth,
        stageSpotlightRect.containerHeight,
      ),
      stageSpotlightRect.containerWidth,
      stageSpotlightRect.containerHeight,
    )
    : []

  const stageFeatherRect = stageSpotlightRect
    ? expandRect(
      stageSpotlightRect,
      ORDER_GUIDE_SPOTLIGHT_FEATHER_PADDING,
      stageSpotlightRect.containerWidth,
      stageSpotlightRect.containerHeight,
    )
    : null

  const stageFeatherSegments = stageSpotlightRect && stageFeatherRect
    ? buildFeatherSegments(stageSpotlightRect, stageFeatherRect)
    : []
  const stepEightShowDeliveryFocus = isStepEight
    && stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus
  const stepEightShowFooterFocus = isStepEight
    && stepFiveSequenceStage === ORDER_GUIDE_STEP_FIVE_SEQUENCE.ctaFocus
  const stepNineShowSecondaryCopy = isStepNine
    && stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.secondaryText
  const stepNineShowOrdersFocus = isStepNine
    && stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.ctaFocus
  const stepFivePrimaryFocusKind = isStepFive
    ? 'size'
    : isStepEight
      ? 'delivery'
      : isStepSix || isStepSeven || isStepNine
      ? 'card'
      : null
  const stepFivePrimaryFocusClone = isFullScreenGuideStep && stepFivePrimaryFocusKind
    ? stepFiveFocusClones.find((clone) => clone.kind === stepFivePrimaryFocusKind) || null
    : null
  const stepFiveCtaCloneKind = isStepEight ? 'footer' : 'cta'
  const stepFiveCtaClone = isFullScreenGuideStep
    ? stepFiveFocusClones.find((clone) => clone.kind === stepFiveCtaCloneKind) || null
    : null
  const stepFiveSecondaryText = isStepFive
    ? '\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u0442\u043e\u0432\u0430\u0440 \u0432 \u043a\u043e\u0440\u0437\u0438\u043d\u0443\n\u0447\u0442\u043e\u0431\u044b \u043d\u0435 \u043f\u043e\u0442\u0435\u0440\u044f\u0442\u044c'
  : isStepSix
      ? '\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u0432 \u0437\u0430\u044f\u0432\u043a\u0443'
      : isStepEight
        ? ORDER_GUIDE_STEP_EIGHT_SECONDARY_COPY
      : ''
  const stepFiveBetweenCopyRect = stepFivePrimaryFocusClone && stepFiveCtaClone
    ? (() => {
      const top = stepFivePrimaryFocusClone.top + stepFivePrimaryFocusClone.height + 10
      const bottom = stepFiveCtaClone.top - 10
      const height = bottom - top

      if (height <= 0) {
        return null
      }

      return {
        top,
        left: stepFiveCtaClone.left,
        width: stepFiveCtaClone.width,
        height,
      }
    })()
    : null
  const stepNineSecondaryCopyRect = stepNineShowSecondaryCopy && stepFivePrimaryFocusClone
    ? (() => {
      if (typeof window === 'undefined') {
        return null
      }

      const top = stepFivePrimaryFocusClone.top + stepFivePrimaryFocusClone.height + 22
      const viewportWidth = window.innerWidth || 0
      const viewportHeight = window.innerHeight || 0
      const rightPadding = 16
      const bottomPadding = 120
      const width = Math.min(
        Math.max(0, stepFivePrimaryFocusClone.width),
        Math.max(0, viewportWidth - stepFivePrimaryFocusClone.left - rightPadding),
      )

      if (width <= 0 || top >= (viewportHeight - bottomPadding)) {
        return null
      }

      return {
        top,
        left: stepFivePrimaryFocusClone.left,
        width,
      }
    })()
    : null
  const visibleStepFiveFocusClones = isFullScreenGuideStep
    ? (
      isStepEight
        ? stepFiveFocusClones.filter((clone) => (
          (clone.kind === 'delivery' && stepEightShowDeliveryFocus)
            || (clone.kind === 'footer' && stepEightShowFooterFocus)
        ))
        : isStepNine
          ? stepFiveFocusClones.filter((clone) => (
            clone.kind === stepFivePrimaryFocusKind
              ? stepNineShowOrdersFocus
              : true
          ))
        : stepFiveFocusClones.filter((clone) => (
          clone.kind === stepFivePrimaryFocusKind
            ? stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus
            : clone.kind === 'cta'
              ? stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.ctaFocus
              : true
        ))
    )
    : []

  return (
    <AnimatePresence>
      {open ? (
        <OrderGuidePortal>
            {isStepSix && cartGuidePreview ? (
              <div
                className={cn(
                  'order-guide-step-six-preview',
                  stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus
                    ? 'order-guide-step-six-preview--focus-card'
                    : '',
                  stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.ctaFocus
                    ? 'order-guide-step-six-preview--focus-cta'
                    : ''
                )}
                aria-hidden="true"
              >
                <Cart active={false} guidePreview={cartGuidePreview} />
              </div>
            ) : null}
            {isProfileGuideStep ? (
              <div
                className={cn(
                  'order-guide-step-profile-preview',
                  isStepSeven && stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus
                    ? 'order-guide-step-profile-preview--focus-delivery'
                    : '',
                  stepNineShowOrdersFocus
                    ? 'order-guide-step-profile-preview--focus-orders'
                    : ''
                )}
                aria-hidden="true"
              >
                <Profile
                  active={false}
                  guidePreview={ORDER_GUIDE_PROFILE_PREVIEW}
                  guideHighlightTarget={isStepNine ? 'orders' : 'delivery'}
                />
              </div>
            ) : null}
            {isStepEight && ordersGuidePreview ? (
              <div
                className={cn(
                  'order-guide-step-eight-preview',
                  stepEightShowDeliveryFocus ? 'order-guide-step-eight-preview--focus-delivery' : '',
                  stepEightShowFooterFocus ? 'order-guide-step-eight-preview--focus-footer' : ''
                )}
                aria-hidden="true"
              >
                <Orders
                  active={false}
                  guidePreview={ordersGuidePreview}
                  guidePreviewSequenceStage={stepFiveSequenceStage}
                />
              </div>
            ) : null}
            <motion.div
              className={cn(
                'order-guide-sheet-overlay',
                isSpotlightStep && overlaySpotlightRect ? 'order-guide-sheet-overlay--spotlight' : '',
                isFullScreenGuideStep ? 'order-guide-sheet-overlay--step-five' : ''
              )}
            data-shell-swipe-block="true"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            onClick={() => onClose?.()}
          >
            {isSpotlightStep && overlaySpotlightRect && overlaySpotlightSegments.length ? (
              <>
                {overlaySpotlightSegments.map((segment, index) => (
                  <div
                    key={`overlay-spotlight-segment-${index}`}
                    className="order-guide-spotlight-scrim-segment"
                    style={{
                      top: segment.top,
                      left: segment.left,
                      width: segment.width,
                      height: segment.height,
                    }}
                  />
                ))}
                {overlayFeatherSegments.map((segment) => (
                  <div
                    key={`overlay-feather-${segment.key}`}
                    className={cn(
                      'order-guide-spotlight-feather',
                      `order-guide-spotlight-feather--${segment.variant}`
                    )}
                    style={{
                      top: segment.top,
                      left: segment.left,
                      width: segment.width,
                      height: segment.height,
                    }}
                  />
                ))}
                {overlayInputHighlightRect ? (
                  <div
                    className="order-guide-spotlight-frame"
                    style={{
                      top: overlayInputHighlightRect.top,
                      left: overlayInputHighlightRect.left,
                      width: overlayInputHighlightRect.width,
                      height: overlayInputHighlightRect.height,
                    }}
                  />
                ) : null}
              </>
            ) : null}

            {isFullScreenGuideStep && stepFiveSequenceStage >= ORDER_GUIDE_STEP_FIVE_SEQUENCE.secondaryText && stepFiveBetweenCopyRect ? (
              <div
                className="order-guide-step-five-between-copy"
                style={{
                  top: stepFiveBetweenCopyRect.top,
                  left: stepFiveBetweenCopyRect.left,
                  width: stepFiveBetweenCopyRect.width,
                  height: stepFiveBetweenCopyRect.height,
                }}
              >
                <TextType
                  as="p"
                  text={stepFiveSecondaryText}
                  typingSpeed={50}
                  initialDelay={0}
                  pauseDuration={2000}
                  deletingSpeed={30}
                  loop={false}
                  showCursor
                  hideCursorWhileTyping={false}
                  cursorCharacter="|"
                  cursorBlinkDuration={0.5}
                  onTypingComplete={() => {
                    scheduleStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.ctaFocus)
                  }}
                  className="order-guide-slide-title order-guide-slide-title--left order-guide-slide-title--wide order-guide-step-five-type order-guide-step-five-type--between"
                  cursorClassName="order-guide-step-five-type-cursor"
                />
              </div>
            ) : null}

            {stepNineSecondaryCopyRect ? (
              <div
                className="order-guide-step-nine-secondary-copy-shell"
                style={{
                  top: stepNineSecondaryCopyRect.top,
                  left: stepNineSecondaryCopyRect.left,
                  width: stepNineSecondaryCopyRect.width,
                }}
              >
                <TextType
                  as="p"
                  text={ORDER_GUIDE_STEP_NINE_SECONDARY_COPY}
                  typingSpeed={50}
                  initialDelay={0}
                  pauseDuration={2000}
                  deletingSpeed={30}
                  loop={false}
                  showCursor
                  hideCursorWhileTyping={false}
                  cursorCharacter="|"
                  cursorBlinkDuration={0.5}
                  onTypingComplete={() => {
                    if (stepFiveSequenceStage === ORDER_GUIDE_STEP_FIVE_SEQUENCE.secondaryText) {
                      scheduleStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.ctaFocus)
                    }
                  }}
                  className="order-guide-slide-title order-guide-slide-title--left order-guide-slide-title--wide order-guide-step-five-type order-guide-step-nine-copy order-guide-step-nine-copy--secondary"
                  cursorClassName="order-guide-step-five-type-cursor"
                />
              </div>
            ) : null}

            {isFullScreenGuideStep && visibleStepFiveFocusClones.length ? (
              <div className="order-guide-step-five-focus-layer" aria-hidden="true">
                {visibleStepFiveFocusClones.map((clone) => (
                  <div
                    key={clone.key}
                    className={cn(
                      'order-guide-step-five-focus-shell',
                      `order-guide-step-five-focus-shell--${clone.kind}`
                    )}
                    style={{
                      top: clone.top,
                      left: clone.left,
                      width: clone.width,
                      height: clone.height,
                    }}
                  >
                    {(() => {
                      const CloneTag = clone.tagName === 'button' ? 'button' : 'div'
                      const cloneTagProps = clone.tagName === 'button'
                        ? { type: 'button', disabled: clone.disabled }
                        : {}

                      return (
                        <CloneTag
                          tabIndex={-1}
                          {...clone.dataAttributes}
                          {...cloneTagProps}
                          className={cn(clone.className, 'order-guide-step-five-focus-clone')}
                          dangerouslySetInnerHTML={{ __html: clone.innerHTML }}
                        />
                      )
                    })()}
                  </div>
                ))}
              </div>
            ) : null}

            <motion.section
              className={cn(
                'order-guide-sheet',
                isStepTwo ? 'order-guide-sheet--step-two' : '',
                isStepFour ? 'order-guide-sheet--step-four' : '',
                isFullScreenGuideStep ? 'order-guide-sheet--step-five' : ''
              )}
              data-shell-swipe-block="true"
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 18, scale: 0.985 }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              onClick={(event) => event.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-label="Order guide"
            >
              <div
                ref={stageRef}
                className={cn(
                  'order-guide-stage relative flex w-full flex-col items-center justify-center rounded-lg',
                  isCompactGuideStep ? 'overflow-visible' : 'overflow-hidden',
                  isCompactGuideStep ? 'order-guide-stage--step-two' : '',
                  isFullScreenGuideStep ? 'order-guide-stage--step-five' : '',
                  isStepTwo ? 'h-[425px]' : '',
                  isStepFour ? 'h-[375px]' : '',
                  !isCompactGuideStep && !isFullScreenGuideStep ? (currentStep === 1 || currentStep === 3 ? 'h-[590px]' : 'h-[500px]') : ''
                )}
              >
                {isSpotlightStep && stageSpotlightRect && stageSpotlightSegments.length ? (
                  <div className="order-guide-stage-surface order-guide-stage-surface--spotlight">
                    {stageSpotlightSegments.map((segment, index) => (
                      <div
                        key={`stage-spotlight-segment-${index}`}
                        className="order-guide-stage-surface-segment"
                        style={{
                          top: segment.top,
                          left: segment.left,
                          width: segment.width,
                          height: segment.height,
                        }}
                      >
                        <DotPattern
                          x={-segment.left}
                          y={-segment.top}
                          className="order-guide-stage-surface-pattern"
                          style={{
                            WebkitMaskImage: `radial-gradient(300px circle at ${Math.round((stageSpotlightRect.containerWidth / 2) - segment.left)}px ${Math.round((stageSpotlightRect.containerHeight / 2) - segment.top)}px, white, transparent)`,
                            maskImage: `radial-gradient(300px circle at ${Math.round((stageSpotlightRect.containerWidth / 2) - segment.left)}px ${Math.round((stageSpotlightRect.containerHeight / 2) - segment.top)}px, white, transparent)`,
                          }}
                        />
                      </div>
                    ))}
                    {stageFeatherSegments.map((segment) => (
                      <div
                        key={`stage-feather-${segment.key}`}
                        className={cn(
                          'order-guide-stage-feather',
                          `order-guide-stage-feather--${segment.variant}`
                        )}
                        style={{
                          top: segment.top,
                          left: segment.left,
                          width: segment.width,
                          height: segment.height,
                        }}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="order-guide-stage-surface">
                    <DotPattern
                      className={cn(
                        '[mask-image:radial-gradient(300px_circle_at_center,white,transparent)]'
                      )}
                    />
                  </div>
                )}

                {isSpotlightStep && stageInputHighlightRect ? (
                  <div
                    className="order-guide-stage-spotlight-frame"
                    style={{
                      top: stageInputHighlightRect.top,
                      left: stageInputHighlightRect.left,
                      width: stageInputHighlightRect.width,
                      height: stageInputHighlightRect.height,
                    }}
                  />
                ) : null}

                <div className="order-guide-stage-content">
                  <Stepper
                    className={cn(
                      'order-guide-stepper',
                      isCompactGuideStep ? 'order-guide-stepper--second-layout' : '',
                      isFullScreenGuideStep ? 'order-guide-stepper--step-five' : ''
                    )}
                    onStepChange={(step) => {
                      setCurrentStep(step)
                      onCurrentStepChange?.(step)
                    }}
                    onFinalStepCompleted={handleFinalStepCompleted}
                    footerClassName={cn(
                      'order-guide-footer',
                      currentStep === 1 ? 'order-guide-footer-first-step' : ''
                    )}
                    contentOverflow={isCompactGuideStep ? 'visible' : 'hidden'}
                    headerContent={
                      <img
                        src="/101-popup.png"
                        alt="101 popup"
                        className="order-guide-logo"
                        loading="eager"
                        decoding="async"
                      />
                    }
                  >
                    <Step>
                      <div className="order-guide-step-first-slide">
                        <p className="order-guide-slide-title">
                          {'\u0421\u041A\u0410\u0427\u0410\u0419\u0422\u0415 \u041F\u0420\u0418\u041B\u041E\u0416\u0415\u041D\u0418\u0415 DEWU'}
                        </p>
                        <div className="order-guide-step-phone-slide">
                          <div className="order-guide-phone-column">
                            <div className="w-[434px]">
                              <Iphone src="/1/1.png" />
                            </div>
                          </div>
                          <div className="order-guide-download-column">
                            <img
                              src="/1/1.1.png"
                              alt="Dewu QR"
                              className="order-guide-download-qr"
                              loading="eager"
                              decoding="async"
                            />
                            <div className="order-guide-download-actions">
                              <a
                                href="https://sj.qq.com/appdetail/com.shizhuang.duapp?android_schema=duappfrom_wxz=1"
                                className="btn-wrapper group inline-flex justify-center items-center hover:border-F97316 transition-colors duration-300 sm:w-auto w-full border-neutral-800 border pt-4 pr-4 pb-4 pl-4 relative"
                              >
                                <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-F97316 opacity-100 transition-all duration-300 translate-x-0 translate-y-0" />
                                <div className="opacity-100 transition-all duration-300 w-2 h-2 border-F97316 border-r border-b absolute right-0 bottom-0 translate-x-0 translate-y-0" />
                                <button type="button" className="btn flex gap-3 uppercase z-10 sm:justify-start text-sm font-medium text-white tracking-wider bg-transparent w-full relative gap-x-3 gap-y-3 items-center justify-center">
                                  <img src="/1/svg1.svg" alt="" className="order-guide-download-icon" />
                                  {'\u0421\u043a\u0430\u0447\u0430\u0442\u044c \u043d\u0430 IOS'}
                                </button>
                              </a>
                              <a
                                href="https://www.dewu.com"
                                className="btn-wrapper group inline-flex justify-center items-center hover:border-F97316 transition-colors duration-300 sm:w-auto w-full border-neutral-800 border pt-4 pr-4 pb-4 pl-4 relative"
                              >
                                <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-F97316 opacity-100 transition-all duration-300 translate-x-0 translate-y-0" />
                                <div className="opacity-100 transition-all duration-300 w-2 h-2 border-F97316 border-r border-b absolute right-0 bottom-0 translate-x-0 translate-y-0" />
                                <button type="button" className="btn flex gap-3 uppercase z-10 sm:justify-start text-sm font-medium text-white tracking-wider bg-transparent w-full relative gap-x-3 gap-y-3 items-center justify-center">
                                  <img src="/1/svg2.svg" alt="" className="order-guide-download-icon" />
                                  {'\u0421\u043a\u0430\u0447\u0430\u0442\u044c \u043d\u0430 Android'}
                                </button>
                              </a>
                            </div>
                          </div>
                        </div>
                      </div>
                    </Step>

                    <Step>
                      <div
                        ref={secondSlideRef}
                        className="order-guide-step-second-slide"
                        style={secondSlideOffset > 0
                          ? { '--order-guide-step-second-spotlight-offset': `${secondSlideOffset}px` }
                          : undefined}
                      >
                        <div className="order-guide-step-second-top">
                          <div className="order-guide-step-second-copy-column">
                            <p className="order-guide-slide-title order-guide-slide-title--left">
                              <span className="order-guide-slide-title-line">
                                {'\u041d\u0430\u0439\u0434\u0438\u0442\u0435 \u043d\u0443\u0436\u043d\u044b\u0439 \u0442\u043e\u0432\u0430\u0440'}
                              </span>
                              <span className="order-guide-slide-title-line">
                                {'\u043d\u0430 Dewu'}
                              </span>
                            </p>
                            <p className="order-guide-step-second-copy">
                              {'\u041B\u0438\u0431\u043E \u043D\u0430\u0439\u0434\u0438\u0442\u0435 \u043D\u0443\u0436\u043D\u044B\u0439 \u0442\u043E\u0432\u0430\u0440 \u0432 \u043D\u0430\u0448\u0435\u043C \u043F\u0440\u0438\u043B\u043E\u0436\u0435\u043D\u0438\u0438 \u043F\u043E \u043D\u0430\u0437\u0432\u0430\u043D\u0438\u044E'}
                            </p>
                          </div>
                          <div className="order-guide-phone-column order-guide-phone-column--right order-guide-phone-column--top">
                            <div className="order-guide-phone-fade-crop order-guide-phone-fade-crop--second">
                              <div className="w-[434px]">
                                <Iphone key="order-guide-step-2-phone" src="/1/2.png" />
                              </div>
                            </div>
                          </div>
                        </div>
                        <div className="order-guide-step-second-bottom">
                          <img
                            src="/101-popup.png"
                            alt="101 popup"
                            className="order-guide-logo order-guide-logo--secondary"
                            loading="eager"
                            decoding="async"
                          />
                          <OrderGuideSecondaryProgress currentStep={currentStep} />
                        </div>
                      </div>
                    </Step>

                    <Step>
                      <div className="order-guide-step-third-slide">
                        <div className="order-guide-step-third-column">
                          <p className="order-guide-slide-title order-guide-slide-title--stacked order-guide-slide-title--stacked-left">
                            <span className="order-guide-slide-title-line">
                              {'\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435'}
                            </span>
                            <span className="order-guide-slide-title-line">
                              {'\u0442\u043e\u0432\u0430\u0440 \u0438 \u0440\u0430\u0437\u043c\u0435\u0440'}
                            </span>
                          </p>
                          <div className="order-guide-phone-column order-guide-step-third-phone">
                            <div className="w-[434px]">
                              <Iphone src="/1/3_1.png" />
                            </div>
                          </div>
                        </div>
                        <div className="order-guide-step-third-column">
                          <div className="order-guide-phone-column">
                            <div className="w-[434px]">
                              <Iphone src="/1/3.png" />
                            </div>
                          </div>
                          <p className="order-guide-slide-title order-guide-slide-title--stacked order-guide-slide-title--stacked-bottom order-guide-slide-title--stacked-left">
                            <span className="order-guide-slide-title-line">
                              {'\u0421\u043a\u043e\u043f\u0438\u0440\u0443\u0439\u0442\u0435'}
                            </span>
                            <span className="order-guide-slide-title-line">
                              {'\u0441\u0441\u044b\u043b\u043a\u0443'}
                            </span>
                          </p>
                        </div>
                      </div>
                    </Step>

                    <Step>
                      <div
                        ref={secondSlideRef}
                        className="order-guide-step-second-slide order-guide-step-fourth-slide"
                        style={secondSlideOffset > 0
                          ? { '--order-guide-step-second-spotlight-offset': `${secondSlideOffset}px` }
                          : undefined}
                      >
                        <div className="order-guide-step-second-bottom">
                          <img
                            src="/101-popup.png"
                            alt="101 popup"
                            className="order-guide-logo order-guide-logo--secondary"
                            loading="eager"
                            decoding="async"
                          />
                          <OrderGuideSecondaryProgress currentStep={currentStep} />
                        </div>
                        <p className="order-guide-slide-title order-guide-slide-title--left order-guide-slide-title--wide">
                          <span className="order-guide-slide-title-line">
                            {'\u0412\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u0441\u0441\u044b\u043b\u043a\u0443 \u0432 \u043f\u043e\u043b\u0435'}
                          </span>
                          <span className="order-guide-slide-title-line">
                            {'\u0434\u043b\u044f \u0432\u0432\u043e\u0434\u0430 \u0438 \u043f\u043e\u0434\u043e\u0436\u0434\u0438\u0442\u0435'}
                          </span>
                          <span className="order-guide-slide-title-line">
                            {'10 - 15 \u0441\u0435\u043a\u0443\u043d\u0434'}
                          </span>
                        </p>
                      </div>
                    </Step>

                    <Step>
                      <div className="order-guide-step-fifth-slide">
                        <div className="order-guide-step-fifth-copy">
                          <TextType
                            as="p"
                            text={'Затем еще раз\nвыберите необходимый\nразмер или все\nдоступные варианты'}
                          typingSpeed={50}
                          initialDelay={1000}
                          pauseDuration={2000}
                          deletingSpeed={30}
                          loop={false}
                          showCursor
                            hideCursorWhileTyping={false}
                            cursorCharacter="|"
                            cursorBlinkDuration={0.5}
                            onTypingComplete={() => {
                            scheduleStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus)
                            }}
                            className="order-guide-slide-title order-guide-slide-title--left order-guide-slide-title--wide order-guide-step-five-type"
                            cursorClassName="order-guide-step-five-type-cursor"
                        />
                        </div>
                      </div>
                    </Step>

                    <Step>
                      <div className="order-guide-step-fifth-slide order-guide-step-sixth-slide">
                        <div className="order-guide-step-fifth-copy">
                          <TextType
                            as="p"
                            text={'\u041f\u0435\u0440\u0435\u0439\u0434\u0438\u0442\u0435 \u0432 \u043a\u043e\u0440\u0437\u0438\u043d\u0443\n\u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u043e\u0432\u0430\u0440\u044b\n\u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u0445\u043e\u0442\u0438\u0442\u0435 \u0437\u0430\u043a\u0430\u0437\u0430\u0442\u044c'}
                            typingSpeed={50}
                            initialDelay={1000}
                            pauseDuration={2000}
                            deletingSpeed={30}
                            loop={false}
                            showCursor
                            hideCursorWhileTyping={false}
                            cursorCharacter="|"
                            cursorBlinkDuration={0.5}
                            onTypingComplete={() => {
                              scheduleStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus)
                            }}
                            className="order-guide-slide-title order-guide-slide-title--left order-guide-slide-title--wide order-guide-step-five-type"
                            cursorClassName="order-guide-step-five-type-cursor"
                          />
                        </div>
                      </div>
                    </Step>

                    <Step>
                      <div className="order-guide-step-fifth-slide order-guide-step-seventh-slide">
                        <div className="order-guide-step-fifth-copy">
                          <TextType
                            as="p"
                            text={'\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044c\n\u0438 \u0437\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u0435\n\u0434\u0430\u043d\u043d\u044b\u0435 \u0434\u043b\u044f \u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0438'}
                            typingSpeed={50}
                            initialDelay={1000}
                            pauseDuration={2000}
                            deletingSpeed={30}
                            loop={false}
                            showCursor
                            hideCursorWhileTyping={false}
                            cursorCharacter="|"
                            cursorBlinkDuration={0.5}
                            onTypingComplete={() => {
                              scheduleStepFiveSequenceStage(ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus)
                            }}
                            className="order-guide-slide-title order-guide-slide-title--left order-guide-slide-title--wide order-guide-step-five-type"
                            cursorClassName="order-guide-step-five-type-cursor"
                          />
                        </div>
                      </div>
                    </Step>

                    <Step>
                      <div className="order-guide-step-fifth-slide order-guide-step-eighth-slide">
                        <div className="order-guide-step-fifth-copy">
                          <TextType
                            as="p"
                            text={ORDER_GUIDE_STEP_EIGHT_PRIMARY_COPY}
                            typingSpeed={50}
                            initialDelay={1000}
                            pauseDuration={2000}
                            deletingSpeed={30}
                            loop={false}
                            showCursor={stepFiveSequenceStage < ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus}
                            hideCursorWhileTyping={false}
                            cursorCharacter="|"
                            cursorBlinkDuration={0.5}
                            onTypingComplete={handleSequentialGuidePrimaryTypingComplete}
                            className="order-guide-slide-title order-guide-slide-title--left order-guide-slide-title--wide order-guide-step-five-type order-guide-step-eight-copy"
                            cursorClassName="order-guide-step-five-type-cursor"
                          />
                        </div>
                      </div>
                    </Step>

                    <Step>
                      <div className="order-guide-step-fifth-slide order-guide-step-ninth-slide">
                        <div className="order-guide-step-fifth-copy order-guide-step-ninth-copy">
                          <TextType
                            as="p"
                            text={ORDER_GUIDE_STEP_NINE_PRIMARY_COPY}
                            typingSpeed={50}
                            initialDelay={1000}
                            pauseDuration={2000}
                            deletingSpeed={30}
                            loop={false}
                            showCursor={stepFiveSequenceStage < ORDER_GUIDE_STEP_FIVE_SEQUENCE.sizeFocus}
                            hideCursorWhileTyping={false}
                            cursorCharacter="|"
                            cursorBlinkDuration={0.5}
                            onTypingComplete={handleSequentialGuidePrimaryTypingComplete}
                            className="order-guide-slide-title order-guide-slide-title--left order-guide-slide-title--wide order-guide-step-five-type order-guide-step-nine-copy"
                            cursorClassName="order-guide-step-five-type-cursor"
                          />
                        </div>
                      </div>
                    </Step>
                  </Stepper>
                </div>
              </div>
            </motion.section>
          </motion.div>
        </OrderGuidePortal>
      ) : null}
    </AnimatePresence>
  )
}
