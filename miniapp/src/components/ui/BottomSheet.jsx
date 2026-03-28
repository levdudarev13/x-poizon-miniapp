import { motion, useReducedMotion } from 'framer-motion'

const SHEET_CLOSE_LABEL = '\u0417\u0430\u043a\u0440\u044b\u0442\u044c'

export default function BottomSheet({
  open,
  onClose,
  badge = null,
  title,
  subtitle = '',
  footer = null,
  className = '',
  overlayClassName = '',
  bodyClassName = '',
  children,
}) {
  const reduceMotion = useReducedMotion()

  if (!open) return null

  const overlayClass = overlayClassName ? `ui-sheet-overlay ${overlayClassName}` : 'ui-sheet-overlay'
  const sheetClassName = className ? `ui-sheet ${className}` : 'ui-sheet'
  const bodyClass = bodyClassName ? `ui-sheet__body ${bodyClassName}` : 'ui-sheet__body'

  return (
    <div className={overlayClass} onClick={onClose}>
      <motion.div
        role="dialog"
        aria-modal="true"
        data-shell-swipe-block="true"
        className={sheetClassName}
        onClick={(event) => event.stopPropagation()}
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: '100%' }}
        animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: '100%' }}
        transition={
          reduceMotion
            ? { duration: 0.18, ease: 'easeOut' }
            : { type: 'spring', stiffness: 320, damping: 30, mass: 0.9 }
        }
      >
        <div className="ui-sheet__handle" />

        <div className="ui-sheet__header">
          <div className="ui-sheet__title-wrap">
            {badge ? <div className="ui-sheet__badge">{badge}</div> : null}
            <h2 className="ui-sheet__title">{title}</h2>
            {subtitle ? <p className="ui-sheet__subtitle">{subtitle}</p> : null}
          </div>

          <button
            type="button"
            className="ui-sheet__close pressable"
            aria-label={SHEET_CLOSE_LABEL}
            onClick={onClose}
          >
            {SHEET_CLOSE_LABEL}
          </button>
        </div>

        <div className={bodyClass}>{children}</div>

        {footer ? <div className="ui-sheet__footer">{footer}</div> : null}
      </motion.div>
    </div>
  )
}
