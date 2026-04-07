import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import ScrollTrigger from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

function resolveScrollerTarget(container) {
  if (typeof container === 'string') {
    return document.querySelector(container)
  }

  if (container?.current instanceof Element) {
    return container.current
  }

  if (container instanceof Element) {
    return container
  }

  return null
}

function toSeconds(value) {
  return typeof value === 'number' && value > 10 ? value / 1000 : value
}

function clearRevealProps(element) {
  gsap.set(element, {
    clearProps: 'opacity,visibility,filter,willChange',
  })
}

export default function FadeContent({
  children,
  container,
  blur = false,
  duration = 1000,
  ease = 'power2.out',
  delay = 0,
  threshold = 0.1,
  initialOpacity = 0,
  disappearAfter = 0,
  disappearDuration = 0.5,
  disappearEase = 'power2.in',
  onComplete,
  onDisappearanceComplete,
  className = '',
  style,
  enabled = true,
  ...props
}) {
  const ref = useRef(null)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return undefined

    try {
      if (!enabled) {
        clearRevealProps(element)
        return undefined
      }

      const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      if (prefersReducedMotion) {
        gsap.set(element, {
          autoAlpha: 1,
          filter: 'blur(0px)',
        })
        clearRevealProps(element)
        return undefined
      }

      const scrollerTarget = resolveScrollerTarget(container)
      const startPct = (1 - threshold) * 100
      const hiddenFilter = blur ? 'blur(10px)' : 'blur(0px)'
      let disappearanceTween = null

      gsap.set(element, {
        autoAlpha: initialOpacity,
        filter: hiddenFilter,
        willChange: 'opacity, filter',
      })

      const timeline = gsap.timeline({
        paused: true,
        delay: toSeconds(delay),
        onComplete: () => {
          clearRevealProps(element)
          onComplete?.()

          if (disappearAfter > 0) {
            gsap.set(element, { willChange: 'opacity, filter' })
            disappearanceTween = gsap.to(element, {
              autoAlpha: initialOpacity,
              filter: hiddenFilter,
              delay: toSeconds(disappearAfter),
              duration: toSeconds(disappearDuration),
              ease: disappearEase,
              onComplete: () => {
                clearRevealProps(element)
                onDisappearanceComplete?.()
              },
            })
          }
        },
      })

      timeline.to(element, {
        autoAlpha: 1,
        filter: 'blur(0px)',
        duration: toSeconds(duration),
        ease,
      })

      const trigger = ScrollTrigger.create({
        trigger: element,
        scroller: scrollerTarget || undefined,
        start: `top ${startPct}%`,
        once: true,
        onEnter: () => timeline.play(),
      })

      ScrollTrigger.refresh()

      return () => {
        trigger.kill()
        timeline.kill()
        disappearanceTween?.kill()
        gsap.killTweensOf(element)
        clearRevealProps(element)
      }
    } catch (error) {
      console.warn('FadeContent animation disabled:', error)
      gsap.set(element, {
        autoAlpha: 1,
        filter: 'blur(0px)',
      })
      clearRevealProps(element)
      return undefined
    }
  }, [
    blur,
    container,
    delay,
    disappearAfter,
    disappearDuration,
    disappearEase,
    duration,
    ease,
    enabled,
    initialOpacity,
    onComplete,
    onDisappearanceComplete,
    threshold,
  ])

  return (
    <div ref={ref} className={className} style={style} {...props}>
      {children}
    </div>
  )
}
