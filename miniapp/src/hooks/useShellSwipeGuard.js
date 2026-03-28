import { useCallback, useRef } from 'react'

function getEventElement(target) {
  if (target instanceof Element) return target
  return target?.parentElement ?? null
}

export function useShellSwipeGuard({
  canSwipeShell,
  onSwipeLeft,
  onSwipeRight,
  horizontalThreshold = 72,
  dominanceRatio = 1.75,
  protectedSelector = '[data-shell-swipe-block="true"]',
}) {
  const touchRef = useRef({
    startX: 0,
    startY: 0,
    blocked: false,
  })
  const supportsPointerEvents = typeof window !== 'undefined' && 'PointerEvent' in window

  const resetTouch = useCallback(() => {
    touchRef.current = {
      startX: 0,
      startY: 0,
      blocked: false,
    }
  }, [])

  const startGesture = useCallback((clientX, clientY, target) => {
    const targetElement = getEventElement(target)
    touchRef.current = {
      startX: clientX,
      startY: clientY,
      blocked: Boolean(targetElement?.closest(protectedSelector)),
    }
  }, [protectedSelector])

  const finishGesture = useCallback((clientX, clientY) => {
    const { startX, startY, blocked } = touchRef.current

    if (blocked || !canSwipeShell) {
      resetTouch()
      return
    }

    const deltaX = clientX - startX
    const deltaY = clientY - startY
    const absDeltaX = Math.abs(deltaX)
    const absDeltaY = Math.abs(deltaY)

    if (
      absDeltaX < horizontalThreshold ||
      absDeltaX < absDeltaY * dominanceRatio
    ) {
      resetTouch()
      return
    }

    if (deltaX < 0) {
      onSwipeLeft?.()
    } else {
      onSwipeRight?.()
    }

    resetTouch()
  }, [canSwipeShell, dominanceRatio, horizontalThreshold, onSwipeLeft, onSwipeRight, resetTouch])

  const onTouchStart = useCallback((event) => {
    if (supportsPointerEvents) return

    const touch = event.touches?.[0]
    if (!touch) {
      resetTouch()
      return
    }

    startGesture(touch.clientX, touch.clientY, event.target)
  }, [resetTouch, startGesture, supportsPointerEvents])

  const onTouchEnd = useCallback((event) => {
    if (supportsPointerEvents) return

    const touch = event.changedTouches?.[0]
    if (!touch) {
      resetTouch()
      return
    }

    finishGesture(touch.clientX, touch.clientY)
  }, [finishGesture, resetTouch, supportsPointerEvents])

  const onPointerDown = useCallback((event) => {
    if (!supportsPointerEvents || event.pointerType !== 'touch') return

    startGesture(event.clientX, event.clientY, event.target)
  }, [startGesture, supportsPointerEvents])

  const onPointerUp = useCallback((event) => {
    if (!supportsPointerEvents || event.pointerType !== 'touch') return

    if (touchRef.current.startX === 0 && touchRef.current.startY === 0) {
      resetTouch()
      return
    }

    finishGesture(event.clientX, event.clientY)
  }, [finishGesture, resetTouch, supportsPointerEvents])

  const onTouchCancel = useCallback(() => {
    resetTouch()
  }, [resetTouch])

  return {
    onPointerDown,
    onPointerUp,
    onPointerCancel: onTouchCancel,
    onTouchStart,
    onTouchEnd,
    onTouchCancel,
  }
}
