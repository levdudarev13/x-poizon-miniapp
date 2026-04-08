import { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import './PoizonManualVariantButton.css'

const POIZON_BUTTON_FRAMES = [
  '/10101.png',
  '/20202.png',
  '/30303.png',
  '/40404.png',
]

export default function PoizonManualVariantButton({
  active = false,
  onClick,
  title = 'Как на Poizon',
  caption = 'Цена вводится вручную',
  className = '',
}) {
  const prefersReducedMotion = useReducedMotion()
  const [activeFrameIndex, setActiveFrameIndex] = useState(0)

  useEffect(() => {
    if (prefersReducedMotion) {
      setActiveFrameIndex(0)
      return undefined
    }

    const intervalId = window.setInterval(() => {
      setActiveFrameIndex((currentIndex) => (currentIndex + 1) % POIZON_BUTTON_FRAMES.length)
    }, 850)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [prefersReducedMotion])

  return (
    <button
      type="button"
      className={`poizon-manual-variant pressable${active ? ' is-active' : ''}${className ? ` ${className}` : ''}`}
      aria-pressed={active}
      onClick={onClick}
    >
      <span className="poizon-manual-variant__eyebrow">Poizon</span>
      <span className="poizon-manual-variant__title">{title}</span>
      <span className="poizon-manual-variant__caption">{caption}</span>
      <span className="poizon-manual-variant__symbol" aria-hidden="true">≈</span>
      <span className="poizon-manual-variant__images" aria-hidden="true">
        {POIZON_BUTTON_FRAMES.map((src, index) => (
          <img
            key={src}
            src={src}
            alt=""
            className={`poizon-manual-variant__image${index === activeFrameIndex ? ' is-visible' : ''}`}
            decoding="async"
          />
        ))}
      </span>
    </button>
  )
}
