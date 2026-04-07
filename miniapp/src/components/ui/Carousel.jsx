import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, useMotionValue, useTransform } from 'motion/react'
import './Carousel.css'

const DEFAULT_ITEMS = [
  { id: 11, imageSrc: '/011-017/011.jpg', imageAlt: 'Слайд 011' },
  { id: 12, imageSrc: '/011-017/012.png', imageAlt: 'Слайд 012' },
  { id: 13, imageSrc: '/011-017/013.jpg', imageAlt: 'Слайд 013' },
  { id: 14, imageSrc: '/011-017/014.png', imageAlt: 'Слайд 014' },
  { id: 15, imageSrc: '/011-017/015.png', imageAlt: 'Слайд 015' },
  { id: 16, imageSrc: '/011-017/016.png', imageAlt: 'Слайд 016' },
  { id: 17, imageSrc: '/011-017/017.png', imageAlt: 'Слайд 017' },
]

const DRAG_BUFFER = 0
const VELOCITY_THRESHOLD = 500
const GAP = 16
const DEFAULT_BASE_WIDTH = 300
const CONTAINER_PADDING = 16
const SPRING_OPTIONS = { type: 'spring', stiffness: 300, damping: 30 }

function CarouselItem({ item, index, itemWidth, round, trackItemOffset, x, transition }) {
  const range = [-(index + 1) * trackItemOffset, -index * trackItemOffset, -(index - 1) * trackItemOffset]
  const outputRange = [90, 0, -90]
  const rotateY = useTransform(x, range, outputRange, { clamp: false })

  return (
    <motion.article
      className={`carousel-item${round ? ' round' : ''}`}
      style={{
        width: itemWidth,
        height: round ? itemWidth : '100%',
        rotateY,
        ...(round ? { borderRadius: '50%' } : {}),
      }}
      transition={transition}
    >
      <div className={`carousel-item-media${round ? ' round' : ''}`}>
        <img
          src={item.imageSrc}
          alt={item.imageAlt}
          className="carousel-item-image"
          loading={index < 2 ? 'eager' : 'lazy'}
          decoding="async"
          draggable="false"
        />
      </div>
    </motion.article>
  )
}

export default function Carousel({
  items = DEFAULT_ITEMS,
  baseWidth = DEFAULT_BASE_WIDTH,
  autoplay = false,
  autoplayDelay = 3000,
  pauseOnHover = false,
  loop = false,
  round = false,
}) {
  const scale = baseWidth / DEFAULT_BASE_WIDTH
  const containerPadding = CONTAINER_PADDING * scale
  const gap = GAP * scale
  const itemWidth = baseWidth - containerPadding * 2
  const trackItemOffset = itemWidth + gap
  const itemsForRender = useMemo(() => {
    if (!loop) return items
    if (items.length === 0) return []
    return [items[items.length - 1], ...items, items[0]]
  }, [items, loop])

  const [position, setPosition] = useState(loop ? 1 : 0)
  const x = useMotionValue(0)
  const [isHovered, setIsHovered] = useState(false)
  const [isJumping, setIsJumping] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)

  const containerRef = useRef(null)

  useEffect(() => {
    if (pauseOnHover && containerRef.current) {
      const container = containerRef.current
      const handleMouseEnter = () => setIsHovered(true)
      const handleMouseLeave = () => setIsHovered(false)
      container.addEventListener('mouseenter', handleMouseEnter)
      container.addEventListener('mouseleave', handleMouseLeave)
      return () => {
        container.removeEventListener('mouseenter', handleMouseEnter)
        container.removeEventListener('mouseleave', handleMouseLeave)
      }
    }

    return undefined
  }, [pauseOnHover])

  useEffect(() => {
    if (!autoplay || itemsForRender.length <= 1) return undefined
    if (pauseOnHover && isHovered) return undefined

    const timer = window.setInterval(() => {
      setPosition((prev) => Math.min(prev + 1, itemsForRender.length - 1))
    }, autoplayDelay)

    return () => window.clearInterval(timer)
  }, [autoplay, autoplayDelay, isHovered, pauseOnHover, itemsForRender.length])

  useEffect(() => {
    const startingPosition = loop ? 1 : 0
    setPosition(startingPosition)
    x.set(-startingPosition * trackItemOffset)
  }, [items.length, loop, trackItemOffset, x])

  useEffect(() => {
    if (!loop && position > itemsForRender.length - 1) {
      setPosition(Math.max(0, itemsForRender.length - 1))
    }
  }, [itemsForRender.length, loop, position])

  const effectiveTransition = isJumping ? { duration: 0 } : SPRING_OPTIONS

  const handleAnimationStart = () => {
    setIsAnimating(true)
  }

  const handleAnimationComplete = () => {
    if (!loop || itemsForRender.length <= 1) {
      setIsAnimating(false)
      return
    }

    const lastCloneIndex = itemsForRender.length - 1

    if (position === lastCloneIndex) {
      setIsJumping(true)
      const target = 1
      setPosition(target)
      x.set(-target * trackItemOffset)
      window.requestAnimationFrame(() => {
        setIsJumping(false)
        setIsAnimating(false)
      })
      return
    }

    if (position === 0) {
      setIsJumping(true)
      const target = items.length
      setPosition(target)
      x.set(-target * trackItemOffset)
      window.requestAnimationFrame(() => {
        setIsJumping(false)
        setIsAnimating(false)
      })
      return
    }

    setIsAnimating(false)
  }

  const handleDragEnd = (_, info) => {
    const { offset, velocity } = info
    const direction =
      offset.x < -DRAG_BUFFER || velocity.x < -VELOCITY_THRESHOLD
        ? 1
        : offset.x > DRAG_BUFFER || velocity.x > VELOCITY_THRESHOLD
          ? -1
          : 0

    if (direction === 0) return

    setPosition((prev) => {
      const next = prev + direction
      const max = itemsForRender.length - 1
      return Math.max(0, Math.min(next, max))
    })
  }

  const dragProps = loop
    ? {}
    : {
        dragConstraints: {
          left: -trackItemOffset * Math.max(itemsForRender.length - 1, 0),
          right: 0,
        },
      }

  const activeIndex = items.length === 0
    ? 0
    : loop
      ? (position - 1 + items.length) % items.length
      : Math.min(position, items.length - 1)

  return (
    <div
      ref={containerRef}
      className={`carousel-container${round ? ' round' : ''}`}
      style={{
        width: `${baseWidth}px`,
        '--carousel-scale': scale,
        '--carousel-padding': `${containerPadding}px`,
        ...(round ? { height: `${baseWidth}px`, borderRadius: '50%' } : {}),
      }}
    >
      <motion.div
        className="carousel-track"
        drag={isAnimating ? false : 'x'}
        {...dragProps}
        style={{
          width: itemWidth,
          gap: `${gap}px`,
          perspective: 1000,
          perspectiveOrigin: `${position * trackItemOffset + itemWidth / 2}px 50%`,
          x,
        }}
        onDragEnd={handleDragEnd}
        animate={{ x: -(position * trackItemOffset) }}
        transition={effectiveTransition}
        onAnimationStart={handleAnimationStart}
        onAnimationComplete={handleAnimationComplete}
      >
        {itemsForRender.map((item, index) => (
          <CarouselItem
            key={`${item?.id ?? 'index'}-${index}`}
            item={item}
            index={index}
            itemWidth={itemWidth}
            round={round}
            trackItemOffset={trackItemOffset}
            x={x}
            transition={effectiveTransition}
          />
        ))}
      </motion.div>

      <div className={`carousel-indicators-container${round ? ' round' : ''}`}>
        <div className="carousel-indicators">
          {items.map((item, index) => (
            <motion.button
              key={item?.id ?? index}
              type="button"
              className={`carousel-indicator ${activeIndex === index ? 'active' : 'inactive'}`}
              animate={{ scale: activeIndex === index ? 1.03 : 1 }}
              onClick={() => setPosition(loop ? index + 1 : index)}
              transition={{ duration: 0.15 }}
              aria-label={`Перейти к слайду ${index + 1}`}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
