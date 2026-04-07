import { motion, useReducedMotion } from 'framer-motion'
import { BUYER_MOTION, BUYER_PRESS_SCALE } from '../../constants/buyerMotion'
import { IconHistory, IconCart, IconCalculatorCube, IconProfile, IconOrders, IconAdmin } from '../ui/Icons'
import BrandGemIcon from '../ui/BrandGemIcon'
import './BottomNav.css'

const TABS_BASE = [
  { id: 'history', Icon: IconHistory, label: 'История' },
  { id: 'cart', Icon: IconCart, label: 'Корзина' },
  { id: 'calculator', Icon: IconCalculatorCube, label: null, center: true },
  { id: 'profile', Icon: IconProfile, label: 'Профиль' },
  { id: 'orders', Icon: IconOrders, label: 'Заявки' },
]

const ADMIN_TAB = { id: 'admin', Icon: IconAdmin, label: 'Админ' }

export default function BottomNav({ active, onChange, cartCount = 0, isAdmin = false }) {
  const tabs = isAdmin ? [...TABS_BASE, ADMIN_TAB] : TABS_BASE
  const prefersReducedMotion = useReducedMotion()
  const isDense = tabs.length > 5

  return (
    <nav
      className={`bottom-nav ${isDense ? 'bottom-nav--dense' : ''}`}
      style={{ '--bottom-nav-columns': tabs.length }}
    >
      <div className="bottom-nav__inner">
        {tabs.map(({ id, Icon, label, center }) => {
          const isActive = active === id
          const isAdminTab = id === 'admin'

          if (center) {
            return (
              <motion.button
                key={id}
                type="button"
                className={`bottom-nav__fab ${isActive ? 'bottom-nav__fab--active' : ''}`}
                onClick={() => onChange(id)}
                aria-label="Калькулятор"
                data-nav-center="true"
                data-nav-active={isActive ? 'true' : 'false'}
                transition={BUYER_MOTION.quick}
              >
                <motion.div
                  className="bottom-nav__fab-inner"
                  initial={false}
                  animate={isActive
                    ? {
                        scale: prefersReducedMotion ? 1 : 1.02,
                      }
                    : {
                        scale: 1,
                      }}
                  transition={BUYER_MOTION.emphasis}
                >
                  <motion.div
                    className="bottom-nav__fab-art"
                    initial={false}
                    animate={prefersReducedMotion
                      ? { opacity: isActive ? 1 : 0.9 }
                      : { opacity: isActive ? 1 : 0.96 }}
                    transition={BUYER_MOTION.standard}
                  >
                    <BrandGemIcon />
                  </motion.div>
                </motion.div>
              </motion.button>
            )
          }

          return (
            <motion.button
              key={id}
              type="button"
              className={`bottom-nav__item pressable ${isActive ? 'bottom-nav__item--active' : ''} ${isAdminTab && isActive ? 'bottom-nav__item--admin-active' : ''}`}
              onClick={() => onChange(id)}
              aria-label={label}
              aria-current={isActive ? 'page' : undefined}
              data-nav-active={isActive ? 'true' : 'false'}
              data-nav-admin={isAdminTab ? 'true' : 'false'}
              whileTap={prefersReducedMotion ? undefined : { scale: BUYER_PRESS_SCALE }}
              transition={BUYER_MOTION.quick}
            >
              {id === 'cart' && cartCount > 0 && (
                <motion.span
                  className="bottom-nav__badge"
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={BUYER_MOTION.standard}
                >
                  {cartCount > 99 ? '99+' : cartCount}
                </motion.span>
              )}

              <motion.div
                className="bottom-nav__icon-wrap"
                initial={false}
                animate={prefersReducedMotion
                  ? { opacity: isActive ? 1 : 0.84 }
                  : { y: isActive ? -2 : 0, scale: isActive ? 1.04 : 1, opacity: isActive ? 1 : 0.84 }}
                transition={BUYER_MOTION.standard}
              >
                <Icon size={isDense ? 19 : 22} />
              </motion.div>

              <span className="bottom-nav__dot-wrap" aria-hidden="true">
                <motion.span
                  className={`bottom-nav__dot ${isAdminTab ? 'bottom-nav__dot--admin' : ''}`}
                  initial={false}
                  animate={{ opacity: isActive ? 1 : 0, scaleX: isActive ? 1 : 0.5 }}
                  transition={BUYER_MOTION.quick}
                />
              </span>

              <span className="bottom-nav__label">{label}</span>
            </motion.button>
          )
        })}
      </div>
    </nav>
  )
}
