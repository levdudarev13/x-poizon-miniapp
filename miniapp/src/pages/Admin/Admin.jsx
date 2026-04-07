import { useEffect, useState } from 'react'
import { MotionConfig } from 'framer-motion'
import { adminRequest } from '../../api/admin.js'
import { useTelegram } from '../../hooks/useTelegram'
import { AdminLauncher } from './components/AdminLauncher.jsx'
import { AdminOrders } from './components/AdminOrders.jsx'
import { AdminCarts } from './components/AdminCarts.jsx'
import { AdminPricing } from './components/AdminPricing.jsx'
import { AdminFaq } from './components/AdminFaq.jsx'
import { AdminBanners } from './components/AdminBanners.jsx'
import { AdminShowcase } from './components/AdminShowcase.jsx'
import { AdminAboutCarousel } from './components/AdminAboutCarousel.jsx'
import './styles/admin-foundation.css'
import './styles/admin-motion.css'
import './styles/admin-launcher.css'
import './styles/admin-orders.css'
import './styles/admin-carts.css'
import './styles/admin-pricing.css'
import './styles/admin-faq.css'
import './styles/admin-banners.css'
import './styles/admin-showcase.css'
import './styles/admin-about-carousel.css'
export default function Admin({ active, requestedView = null, onRequestedViewConsumed }) {
  const [authStatus, setAuthStatus] = useState('idle')
  const [view, setView] = useState('menu')
  const { initData, haptic, tg } = useTelegram()
  useEffect(() => {
    if (!active || !initData) {
      setAuthStatus('idle')
      return
    }
    let isMounted = true
    setAuthStatus('checking')
    adminRequest('/api/admin/ping', { initData })
      .then(() => {
        if (isMounted) setAuthStatus('ready')
      })
      .catch(() => {
        if (isMounted) setAuthStatus('error')
      })
    return () => {
      isMounted = false
    }
  }, [active, initData])
  useEffect(() => {
    if (!active || !requestedView) {
      return
    }

    setView(requestedView)
    onRequestedViewConsumed?.()
  }, [active, onRequestedViewConsumed, requestedView])
  if (!active) return null
  const goMenu = () => {
    haptic?.('light')
    setView('menu')
  }
  return (
    <MotionConfig reducedMotion="user">
      <div className="admin-runtime">
        {view === 'orders' && (
          <AdminOrders initData={initData} haptic={haptic} tg={tg} onBack={goMenu} />
        )}
        {view === 'pricing' && (
          <AdminPricing initData={initData} haptic={haptic} onBack={goMenu} />
        )}
        {view === 'carts' && (
          <AdminCarts initData={initData} haptic={haptic} tg={tg} onBack={goMenu} />
        )}
        {view === 'faq' && (
          <AdminFaq initData={initData} haptic={haptic} onBack={goMenu} />
        )}
        {view === 'banners' && (
          <AdminBanners initData={initData} haptic={haptic} onBack={goMenu} />
        )}
        {view === 'showcase' && (
          <AdminShowcase initData={initData} haptic={haptic} onBack={goMenu} />
        )}
        {view === 'about-carousel' && (
          <AdminAboutCarousel initData={initData} haptic={haptic} onBack={goMenu} />
        )}
        {view === 'menu' && (
          <AdminLauncher
            authStatus={authStatus}
            onOpenSection={(sectionId) => {
              haptic?.('light')
              setView(sectionId)
            }}
          />
        )}
      </div>
    </MotionConfig>
  )
}
