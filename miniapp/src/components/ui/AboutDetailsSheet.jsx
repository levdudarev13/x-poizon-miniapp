import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import Carousel from './Carousel'
import './AboutDetailsSheet.css'

const ABOUT_DETAILS_MAX_WIDTH = 560

function getAboutDetailsWidth() {
  if (typeof window === 'undefined') {
    return 300
  }

  const viewportWidth = window.visualViewport?.width || window.innerWidth
  const viewportHeight = window.visualViewport?.height || window.innerHeight
  const widthFromHeight = Math.max((viewportHeight - 64) * (2 / 3), 280)
  return Math.min(Math.max(viewportWidth - 32, 280), ABOUT_DETAILS_MAX_WIDTH, widthFromHeight)
}

function AboutDetailsPortal({ children }) {
  if (typeof document === 'undefined') {
    return children
  }

  return createPortal(children, document.body)
}

export default function AboutDetailsSheet({
  open = false,
  onClose,
  items,
}) {
  const [carouselWidth, setCarouselWidth] = useState(getAboutDetailsWidth)

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
    if (!open || typeof window === 'undefined') {
      return undefined
    }

    const syncWidth = () => {
      setCarouselWidth(getAboutDetailsWidth())
    }

    syncWidth()
    window.addEventListener('resize', syncWidth)
    window.visualViewport?.addEventListener('resize', syncWidth)

    return () => {
      window.removeEventListener('resize', syncWidth)
      window.visualViewport?.removeEventListener('resize', syncWidth)
    }
  }, [open])

  return (
    <AnimatePresence>
      {open ? (
        <AboutDetailsPortal>
          <motion.div
            className="about-details-sheet-overlay"
            data-shell-swipe-block="true"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            onClick={() => onClose?.()}
          >
            <motion.div
              className="about-details-sheet"
              data-shell-swipe-block="true"
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.985 }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              onClick={(event) => event.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-label="About details"
            >
              <div className="about-details-sheet__carousel" data-shell-swipe-block="true">
                <Carousel items={items} baseWidth={carouselWidth} />
              </div>
            </motion.div>
          </motion.div>
        </AboutDetailsPortal>
      ) : null}
    </AnimatePresence>
  )
}
