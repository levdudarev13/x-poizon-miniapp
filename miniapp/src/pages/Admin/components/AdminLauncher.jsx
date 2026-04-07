import { motion } from 'framer-motion'
import { AdminSectionCard } from './AdminSectionCard.jsx'
import { AdminSectionShell } from './AdminSectionShell.jsx'
import { ADMIN_MOTION, SECTIONS } from '../adminShared.js'

const ACCESS_STATUS_META = {
  idle: {
    badge: 'Ожидаем',
    text: 'Проверка доступа начнется сразу после подключения сессии.',
  },
  checking: {
    badge: 'Проверка',
    text: 'Проверяем права администратора перед переходом в рабочие разделы.',
  },
  ready: {
    badge: 'Готово',
    text: 'Доступ подтвержден. Можно сразу открыть заявки, расценки или корзины.',
  },
  error: {
    badge: 'Ошибка',
    text: 'Не удалось подтвердить права администратора. Попробуйте открыть экран заново.',
  },
}

export function AdminLauncher({ authStatus, onOpenSection }) {
  const statusMeta = ACCESS_STATUS_META[authStatus] || ACCESS_STATUS_META.idle
  const launcherSections = [
    ...SECTIONS.slice(0, 4),
    {
      id: 'banners',
      label: 'Баннеры',
      icon: 'showcase',
      desc: 'Промо-карусель и popup-окна',
      available: true,
    },
    {
      id: 'about-carousel',
      label: '\u041e \u043d\u0430\u0441',
      icon: 'about-carousel',
      desc: '\u0424\u043e\u0442\u043e \u043a\u0430\u0440\u0443\u0441\u0435\u043b\u0438 2:3',
      available: true,
    },
    ...SECTIONS.slice(4),
  ]

  const hero = (
    <section className="admin-launcher__hero">
      <div className="admin-launcher__copy">
        <span className="admin-shell__eyebrow">Операционный доступ</span>
        <h1 className="admin-shell__title">Админ-панель</h1>
      </div>
      <div className="admin-launcher__status" aria-live="polite">
        <div className="admin-launcher__status-head">
          <span className="admin-launcher__status-label">Статус доступа</span>
          {authStatus === 'ready' ? (
            <span className="admin-shell__status-badge">{statusMeta.badge}</span>
          ) : authStatus === 'error' ? (
            <span className="admin-shell__status-error">{statusMeta.badge}</span>
          ) : (
            <span className="admin-launcher__status-value">{statusMeta.badge}</span>
          )}
        </div>
        <span className="admin-launcher__status-text">{statusMeta.text}</span>
      </div>
    </section>
  )

  return (
    <AdminSectionShell
      hero={hero}
      contentClassName="admin-shell__grid admin-launcher__grid"
      data-shell-swipe-block="true"
    >
      {launcherSections.map(({ id, label, icon, desc, available }, index) => {
        const isOpenable = available && authStatus === 'ready'

        return (
          <motion.div
            key={id}
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...ADMIN_MOTION.standard, delay: index * 0.04 }}
          >
            <AdminSectionCard
              icon={icon}
              label={label}
              desc={desc}
              badge={available ? (authStatus === 'ready' ? 'Доступно' : 'Проверка') : 'Скрыто'}
              available={isOpenable}
              onClick={() => {
                if (isOpenable) onOpenSection(id)
              }}
            />
          </motion.div>
        )
      })}
    </AdminSectionShell>
  )
}
