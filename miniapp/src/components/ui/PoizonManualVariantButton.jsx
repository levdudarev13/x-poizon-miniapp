import { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import './PoizonManualVariantButton.css'

const POIZON_BUTTON_FRAMES = [
  '/10101.png',
  '/20202.png',
  '/30303.png',
  '/40404.png',
]

const POIZON_BUTTON_OPTIONS = [
  { id: 'left', src: '/5.png', alt: 'Poizon 5' },
  { id: 'right', src: '/6.png', alt: 'Poizon 6' },
]

export default function PoizonManualVariantButton({
  activeChoice = '',
  onSelect,
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
    }, 500)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [prefersReducedMotion])

  return (
    <div className={`poizon-manual-choice-grid${className ? ` ${className}` : ''}`}>
      {POIZON_BUTTON_OPTIONS.map((option) => {
        const isActive = activeChoice === option.id
        return (
          <button
            key={option.id}
            type="button"
            className={`poizon-manual-choice poizon-manual-choice--${option.id} pressable${isActive ? ' is-active' : ''}`}
            aria-pressed={isActive}
            onClick={() => onSelect?.(option.id)}
          >
            {option.id === 'left' ? (
              <span className="poizon-manual-choice__frames" aria-hidden="true">
                {POIZON_BUTTON_FRAMES.map((src, index) => (
                  <img
                    key={src}
                    src={src}
                    alt=""
                    className={`poizon-manual-choice__frame${index === activeFrameIndex ? ' is-visible' : ''}`}
                    decoding="async"
                  />
                ))}
              </span>
            ) : null}
            <img
              src={option.src}
              alt={option.alt}
              className="poizon-manual-choice__preview"
              decoding="async"
            />
          </button>
        )
      })}
    </div>
  )
}
