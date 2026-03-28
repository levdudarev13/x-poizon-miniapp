import { motion } from 'framer-motion'
import { ADMIN_MOTION, ADMIN_PRESS_SCALE } from '../adminShared.js'
import { AdminSectionIcon } from './AdminSharedBits.jsx'

export function AdminSectionCard({ icon, label, desc, badge, available = true, onClick }) {
  return (
    <motion.button
      type="button"
      className={`admin-card admin-card--button ${available ? 'admin-card--available' : 'admin-card--disabled'}`}
      whileTap={available ? { scale: ADMIN_PRESS_SCALE } : undefined}
      transition={ADMIN_MOTION.quick}
      onClick={onClick}
      disabled={!available}
    >
      <span className="admin-card__icon" aria-hidden="true">
        <AdminSectionIcon type={icon} />
      </span>
      <span className="admin-card__text">
        <span className="admin-card__label">{label}</span>
        <span className="admin-card__desc">{desc}</span>
      </span>
      <span className={`admin-card__badge ${available ? 'admin-card__badge--live' : ''}`}>
        {badge}
      </span>
    </motion.button>
  )
}
