import { useState, useEffect, useRef, useCallback } from 'react'
import { MotionConfig, useReducedMotion } from 'framer-motion'
import BottomNav from './components/BottomNav/BottomNav'
import Calculator from './pages/Calculator/Calculator'
import Cart from './pages/Cart/Cart'
import Admin from './pages/Admin/Admin'
import History from './pages/History/History'
import Profile from './pages/Profile/Profile'
import Orders from './pages/Orders/Orders'
import { bootstrapWithInitData } from './api/admin.js'
import { useTelegram } from './hooks/useTelegram'
import { useShellSwipeGuard } from './hooks/useShellSwipeGuard'
import { OPEN_FAQ_REQUEST_EVENT } from './utils/faqNavigation'

const TAB_ORDER_BASE = ['history', 'cart', 'calculator', 'profile', 'orders']
const SHELL_TAB_SLIDE_DISTANCE = 24
const SHELL_KEYBOARD_OPEN_THRESHOLD = 48

function toPx(value) {
  return `${Math.max(0, Math.round(value))}px`
}

function readVisualViewportHeight() {
  return window.visualViewport?.height || window.innerHeight || 0
}

function toDataAttributeName(datasetKey) {
  return `data-${datasetKey.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`
}

export default function App() {
  const [activeTab, setActiveTab] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    const tab = params.get('tab')
    return TAB_ORDER_BASE.includes(tab) ? tab : 'calculator'
  })
  const [isAdmin, setIsAdmin] = useState(false)
  const [bootstrapPayload, setBootstrapPayload] = useState(null)
  const [profileRequestedView, setProfileRequestedView] = useState(null)
  const [tabDirection, setTabDirection] = useState(0)
  const [canSwipeShell, setCanSwipeShell] = useState(true)
  const prefersReducedMotion = useReducedMotion()
  const {
    tg,
    haptic,
    userId,
    initData,
    safeAreaInset,
    contentSafeAreaInset,
    viewportHeight,
    viewportStableHeight,
    disableVerticalSwipes,
  } = useTelegram()
  const [cartCount, setCartCount] = useState(0)
  const calcRef = useRef(null)
  const shellViewportBaselineRef = useRef({
    height: 0,
    width: 0,
  })
  const tabOrder = isAdmin ? [...TAB_ORDER_BASE, 'admin'] : TAB_ORDER_BASE
  const tabSwipeRootDatasetKeys = {
    calculator: 'shellSwipeRootCalculator',
    cart: 'shellSwipeRootCart',
    orders: 'shellSwipeRootOrders',
    profile: 'shellSwipeRootProfile',
  }
  const activeShellSwipeRootKey = tabSwipeRootDatasetKeys[activeTab]

  useEffect(() => {
    if (!tg) return

    tg.ready?.()
    tg.expand?.()
    disableVerticalSwipes?.()
  }, [disableVerticalSwipes, tg])

  const fetchCartCount = useCallback(async () => {
    if (!userId) return
    try {
      const res = await fetch(`/api/cart?user_id=${userId}`)
      const data = await res.json()
      if (Array.isArray(data)) {
        setCartCount(data.filter((item) => !item.order_submitted && !item.paid && !item.shipped && !item.arrived).length)
      }
    } catch {
      // Ignore cart count refresh errors.
    }
  }, [userId])

  useEffect(() => {
    fetchCartCount()
  }, [fetchCartCount])

  useEffect(() => {
    if (activeTab === 'cart' || activeTab === 'calculator' || activeTab === 'orders') {
      fetchCartCount()
    }
  }, [activeTab, fetchCartCount])

  useEffect(() => {
    if (!userId) {
      setIsAdmin(false)
      setBootstrapPayload(null)
      return
    }

    let isMounted = true

    bootstrapWithInitData({ userId, initData })
      .then((data) => {
        if (isMounted) {
          setBootstrapPayload(data || null)
          setIsAdmin(Boolean(data?.is_admin))
        }
      })
      .catch(() => {
        if (isMounted) {
          setBootstrapPayload(null)
          setIsAdmin(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [initData, userId])

  useEffect(() => {
    if (activeTab === 'admin' && !isAdmin) {
      setTabDirection(-1)
      setActiveTab('calculator')
    }
  }, [activeTab, isAdmin])

  const handleTabChange = useCallback((tab) => {
    if (tab === activeTab || !tabOrder.includes(tab)) return

    const currentIndex = tabOrder.indexOf(activeTab)
    const nextIndex = tabOrder.indexOf(tab)
    if (currentIndex !== -1 && nextIndex !== -1) {
      setTabDirection(nextIndex > currentIndex ? 1 : -1)
    }

    setActiveTab(tab)
  }, [activeTab, tabOrder])

  const handleOpenFromHistory = useCallback((productData) => {
    handleTabChange('calculator')
    setTimeout(() => {
      calcRef.current?.openProduct(productData)
    }, 50)
  }, [handleTabChange])

  const handleProfileRequestedViewConsumed = useCallback(() => {
    setProfileRequestedView(null)
  }, [])

  const handleRequestOpenProfileDelivery = useCallback(() => {
    const nextTab = 'profile'
    const currentIndex = tabOrder.indexOf(activeTab)
    const nextIndex = tabOrder.indexOf(nextTab)

    if (currentIndex !== -1 && nextIndex !== -1 && currentIndex !== nextIndex) {
      setTabDirection(nextIndex > currentIndex ? 1 : -1)
    }

    setProfileRequestedView('delivery')
    setActiveTab(nextTab)
  }, [activeTab, tabOrder])

  const handleRequestOpenOrderGuide = useCallback(() => {
    const nextTab = 'calculator'
    const currentIndex = tabOrder.indexOf(activeTab)
    const nextIndex = tabOrder.indexOf(nextTab)

    if (currentIndex !== -1 && nextIndex !== -1 && currentIndex !== nextIndex) {
      setTabDirection(nextIndex > currentIndex ? 1 : -1)
    }

    setActiveTab(nextTab)
    window.setTimeout(() => {
      calcRef.current?.openOrderGuide?.()
    }, 50)
  }, [activeTab, tabOrder])

  useEffect(() => {
    const handleOpenFaqRequest = () => {
      const nextTab = 'profile'
      const currentIndex = tabOrder.indexOf(activeTab)
      const nextIndex = tabOrder.indexOf(nextTab)

      if (currentIndex !== -1 && nextIndex !== -1 && currentIndex !== nextIndex) {
        setTabDirection(nextIndex > currentIndex ? 1 : -1)
      }

      setProfileRequestedView('faq')
      setActiveTab(nextTab)
    }

    window.addEventListener(OPEN_FAQ_REQUEST_EVENT, handleOpenFaqRequest)
    return () => {
      window.removeEventListener(OPEN_FAQ_REQUEST_EVENT, handleOpenFaqRequest)
    }
  }, [activeTab, tabOrder])
  const emitSwipeHaptic = useCallback(() => {
    window.requestAnimationFrame(() => {
      haptic?.('light')
    })
  }, [haptic])

  useEffect(() => {
    if (!document.body) return undefined

    const syncActiveShellSwipeRoot = () => {
      const activeShellSwipeRoot = activeShellSwipeRootKey ? (document.body.dataset[activeShellSwipeRootKey] ?? '1') : '1'
      if (document.body.dataset.shellSwipeRoot !== activeShellSwipeRoot) {
        document.body.dataset.shellSwipeRoot = activeShellSwipeRoot
      }

      const nextCanSwipeShell = activeShellSwipeRoot !== '0' && document.body.dataset.blockTabSwipe !== '1'
      setCanSwipeShell((currentValue) => (
        currentValue === nextCanSwipeShell ? currentValue : nextCanSwipeShell
      ))
    }

    syncActiveShellSwipeRoot()

    const observer = new MutationObserver(syncActiveShellSwipeRoot)
    const observedAttributes = activeShellSwipeRootKey
      ? [toDataAttributeName(activeShellSwipeRootKey), 'data-block-tab-swipe', 'data-shell-swipe-root']
      : ['data-block-tab-swipe', 'data-shell-swipe-root']
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: observedAttributes,
    })

    return () => {
      observer.disconnect()
      document.body.dataset.shellSwipeRoot = '1'
      setCanSwipeShell(true)
    }
  }, [activeShellSwipeRootKey])

  useEffect(() => {
    const root = document.documentElement
    const body = document.body

    if (!root || !body) return undefined

    const applyShellMetrics = () => {
      const safeTop = safeAreaInset?.top || 0
      const safeBottom = safeAreaInset?.bottom || 0
      const contentSafeBottom = contentSafeAreaInset?.bottom || safeBottom
      const visualViewportHeight = readVisualViewportHeight()
      const visualViewportWidth = Math.round(window.visualViewport?.width || window.innerWidth || 0)
      const telegramViewportHeight = Math.max(0, Math.round(viewportHeight || 0))
      const telegramStableHeight = Math.max(0, Math.round(viewportStableHeight || 0))
      const baseline = shellViewportBaselineRef.current
      const widthChanged = baseline.width > 0 && Math.abs(visualViewportWidth - baseline.width) > 120

      if (widthChanged) {
        baseline.height = 0
      }

      baseline.width = visualViewportWidth
      baseline.height = Math.max(
        baseline.height || 0,
        telegramStableHeight,
        telegramViewportHeight,
        Math.round(visualViewportHeight),
      )

      const stableViewport = Math.max(
        baseline.height || 0,
        telegramStableHeight,
        telegramViewportHeight,
        Math.round(visualViewportHeight),
      )
      let keyboardOffset = 0

      if (telegramStableHeight > telegramViewportHeight && telegramViewportHeight > 0) {
        keyboardOffset = telegramStableHeight - telegramViewportHeight
      }

      keyboardOffset = Math.max(
        keyboardOffset,
        stableViewport > visualViewportHeight
          ? stableViewport - visualViewportHeight
          : 0,
      )

      keyboardOffset = Math.max(0, Math.round(keyboardOffset))

      const keyboardOpen = keyboardOffset > SHELL_KEYBOARD_OPEN_THRESHOLD
      const navTranslate = keyboardOpen ? `calc(100% + ${contentSafeBottom}px)` : '0px'
      const pageBottomPadding = keyboardOpen
        ? `calc(${contentSafeBottom}px + ${keyboardOffset}px + 16px)`
        : `calc(var(--shell-nav-height) + ${contentSafeBottom}px + 16px)`
      const bottomActionOffset = keyboardOpen
        ? `calc(${contentSafeBottom}px + ${keyboardOffset}px)`
        : `calc(var(--shell-nav-height) + ${contentSafeBottom}px)`

      root.style.setProperty('--shell-safe-top', toPx(safeTop))
      root.style.setProperty('--shell-safe-bottom', toPx(safeBottom))
      root.style.setProperty('--shell-content-safe-bottom', toPx(contentSafeBottom))
      root.style.setProperty('--shell-viewport-stable-height', toPx(stableViewport))
      root.style.setProperty('--shell-keyboard-offset', toPx(keyboardOffset))
      root.style.setProperty('--shell-nav-translate', navTranslate)
      root.style.setProperty('--shell-nav-hidden', keyboardOpen ? '1' : '0')
      root.style.setProperty('--shell-page-bottom-padding', pageBottomPadding)
      root.style.setProperty('--shell-bottom-action-offset', bottomActionOffset)
      document.body.dataset.shellKeyboardOpen = keyboardOpen ? '1' : '0'
    }

    applyShellMetrics()

    window.addEventListener('resize', applyShellMetrics)
    window.visualViewport?.addEventListener('resize', applyShellMetrics)
    window.visualViewport?.addEventListener('scroll', applyShellMetrics)

    return () => {
      window.removeEventListener('resize', applyShellMetrics)
      window.visualViewport?.removeEventListener('resize', applyShellMetrics)
      window.visualViewport?.removeEventListener('scroll', applyShellMetrics)
      document.body.dataset.shellKeyboardOpen = '0'
    }
  }, [contentSafeAreaInset, safeAreaInset, viewportHeight, viewportStableHeight])

  const handleSwipeLeft = useCallback(() => {
    const activeIndex = tabOrder.indexOf(activeTab)
    if (activeIndex === -1 || activeIndex >= tabOrder.length - 1) return

    handleTabChange(tabOrder[activeIndex + 1])
    emitSwipeHaptic()
  }, [activeTab, emitSwipeHaptic, handleTabChange, tabOrder])

  const handleSwipeRight = useCallback(() => {
    const activeIndex = tabOrder.indexOf(activeTab)
    if (activeIndex <= 0) return

    handleTabChange(tabOrder[activeIndex - 1])
    emitSwipeHaptic()
  }, [activeTab, emitSwipeHaptic, handleTabChange, tabOrder])

  const shellSwipeHandlers = useShellSwipeGuard({
    canSwipeShell,
    onSwipeLeft: handleSwipeLeft,
    onSwipeRight: handleSwipeRight,
    horizontalThreshold: 72,
  })

  const panelTransition = prefersReducedMotion
    ? 'opacity 120ms linear'
    : 'transform 180ms cubic-bezier(0.22, 1, 0.36, 1), opacity 180ms ease'
  const inactivePanelOffset = prefersReducedMotion
    ? 0
    : tabDirection >= 0 ? SHELL_TAB_SLIDE_DISTANCE : -SHELL_TAB_SLIDE_DISTANCE

  const mountedPanels = [
    {
      id: 'history',
      content: <History onOpenProduct={handleOpenFromHistory} active={activeTab === 'history'} />,
    },
    {
      id: 'cart',
      content: <Cart active={activeTab === 'cart'} />,
    },
    {
      id: 'calculator',
      content: (
        <Calculator
          onCartChange={fetchCartCount}
          active={activeTab === 'calculator'}
          ref={calcRef}
        />
      ),
    },
    {
      id: 'profile',
      content: (
        <Profile
          active={activeTab === 'profile'}
          requestedView={profileRequestedView}
          onRequestedViewConsumed={handleProfileRequestedViewConsumed}
          onRequestOpenOrderGuide={handleRequestOpenOrderGuide}
          supportLink={{
            url: bootstrapPayload?.admin_contact_url,
            username: bootstrapPayload?.admin_contact_username,
            userId: bootstrapPayload?.admin_contact_user_id,
          }}
        />
      ),
    },
    {
      id: 'orders',
      content: (
        <Orders
          active={activeTab === 'orders'}
          onRequestOpenProfileDelivery={handleRequestOpenProfileDelivery}
        />
      ),
    },
  ]

  if (isAdmin) {
    mountedPanels.push({
      id: 'admin',
      content: <Admin active={activeTab === 'admin'} />,
    })
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="app-shell shell-gesture-root" {...shellSwipeHandlers}>
        {mountedPanels.map(({ id, content }) => {
          const isActive = activeTab === id

          return (
            <section
              key={id}
              aria-hidden={!isActive}
              className={`app-shell__panel ${isActive ? 'app-shell__panel--active' : 'app-shell__panel--inactive'}`}
              style={{
                pointerEvents: isActive ? 'auto' : 'none',
                opacity: isActive ? 1 : 0,
                transform: `translate3d(${isActive ? 0 : inactivePanelOffset}px, 0, 0)`,
                transition: panelTransition,
              }}
            >
              {content}
            </section>
          )
        })}

        <BottomNav
          active={activeTab}
          onChange={handleTabChange}
          cartCount={cartCount}
          isAdmin={isAdmin}
        />
      </div>
    </MotionConfig>
  )
}
