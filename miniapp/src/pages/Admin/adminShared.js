export const ADMIN_EASE = [0.22, 1, 0.36, 1]

export const ADMIN_MOTION = {
  quick: { duration: 0.18, ease: ADMIN_EASE },
  standard: { duration: 0.24, ease: ADMIN_EASE },
  emphasis: { duration: 0.32, ease: ADMIN_EASE },
}

export const ADMIN_PRESS_SCALE = 0.97

export const SECTIONS = [
  { id: 'orders', label: 'Заявки', icon: 'orders', desc: 'Управление заказами', available: true },
  { id: 'pricing', label: 'Расценки', icon: 'pricing', desc: 'Цены, комиссии и курс', available: true },
  { id: 'carts', label: 'Корзины', icon: 'carts', desc: 'Просмотр корзин клиентов', available: true },
]

export const PRICING_FIELDS = [
  {
    key: 'commission_pct',
    label: 'Комиссия',
    hint: 'Процент комиссии со стоимости товара.',
    suffix: '%',
    inputMode: 'decimal',
    placeholder: '10.0',
  },
  {
    key: 'min_commission_rub',
    label: 'Минимальная комиссия',
    hint: 'Минимальная сумма комиссии в рублях.',
    suffix: '₽',
    inputMode: 'decimal',
    placeholder: '300',
  },
  {
    key: 'logistics_rub',
    label: 'Логистика',
    hint: 'Фиксированная стоимость логистики по заказу.',
    suffix: '₽',
    inputMode: 'decimal',
    placeholder: '500',
  },
  {
    key: 'insurance_rub',
    label: 'Страховка',
    hint: 'Доплата за страховку заказа.',
    suffix: '₽',
    inputMode: 'decimal',
    placeholder: '200',
  },
  {
    key: 'price_per_kg',
    label: 'Цена за 1 кг',
    hint: 'Стоимость килограмма международной доставки.',
    suffix: '₽',
    inputMode: 'decimal',
    placeholder: '250',
  },
  {
    key: 'delivery_time',
    label: 'Срок доставки',
    hint: 'Текст, который видит пользователь в расчёте.',
    placeholder: 'до 2 недель',
  },
  {
    key: 'next_shipment_date',
    label: 'Ближайшая отправка',
    hint: 'Дата следующей отправки для карточек товаров.',
    placeholder: '00.00.0000',
  },
]

export const RATE_OVERRIDE_FIELD = {
  key: 'rate_override',
  label: 'Ручной курс',
  hint: 'Оставьте пусто или 0, чтобы использовать курс ЦБ.',
  suffix: '₽/¥',
  inputMode: 'decimal',
  placeholder: '0',
}

export const DELIVERY_FIELDS = [
  { key: 'recipient_name', label: 'Получатель' },
  { key: 'phone', label: 'Телефон' },
  { key: 'city', label: 'Город' },
  { key: 'street', label: 'Улица' },
  { key: 'house', label: 'Дом' },
  { key: 'apartment', label: 'Квартира' },
  { key: 'comment', label: 'Комментарий' },
]

const CART_PLATFORM_NAMES = {
  poizon: 'Poizon',
  taobao: 'Taobao',
  '1688': '1688',
}

const CART_PLATFORM_COLORS = {
  poizon: 'var(--accent)',
  taobao: '#ff7a45',
  '1688': '#ef5b4d',
}

const ADMIN_ORDER_STATUS_META = {
  in_order: {
    label: 'В заявке',
    color: '#f59e0b',
  },
  submitted: {
    label: 'На рассмотрении',
    color: '#f97316',
  },
  paid: {
    label: 'Оплачен',
    color: '#3b82f6',
  },
  shipped: {
    label: 'Отправлен',
    color: '#8b5cf6',
  },
  arrived: {
    label: 'Доставлено',
    color: '#22c55e',
  },
}

function parseDecimalString(value) {
  return String(value ?? '')
    .trim()
    .replace(',', '.')
}

export function getAdminOrderStatusMeta(statusKey) {
  return ADMIN_ORDER_STATUS_META[statusKey] || {
    label: 'Статус',
    color: '#94a3b8',
  }
}

export function formatRate(value) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '—'

  return `${numericValue.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ₽/¥`
}

export function formatExpiry(value) {
  if (!value) return 'Автоматически от ЦБ'

  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return String(value)
  }
}

export function formatAdminDateTime(value) {
  const text = String(value || '').trim()
  if (!text) return '—'

  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(text))
  } catch {
    return text
  }
}

export function getDeliveryFieldRawValue(deliveryData, fieldKey) {
  return String(deliveryData?.[fieldKey] ?? '').trim()
}

export function getDeliveryBadgeLabel(batch) {
  if (!batch?.hasSnapshot) return 'Нет данных'
  return batch.deliveryComplete ? 'Заполнено' : 'Проверить'
}

export function getLatestAdminDeliveryBatch(items) {
  const submittedItems = Array.isArray(items)
    ? items.filter((item) => (
      String(item?.submission_batch_id || '').trim() &&
      String(item?.submitted_at || '').trim()
    ))
    : []

  if (submittedItems.length === 0) {
    return {
      hasSnapshot: false,
      batchId: '',
      submittedAt: '',
      submittedAtLabel: '—',
      itemsCount: 0,
      deliveryData: {},
      deliveryComplete: false,
    }
  }

  const latestItem = submittedItems.reduce((currentLatest, item) => {
    if (!currentLatest) return item

    const itemTime = Date.parse(String(item?.submitted_at || '').trim())
    const latestTime = Date.parse(String(currentLatest?.submitted_at || '').trim())
    const itemRank = Number.isFinite(itemTime) ? itemTime : Number.NEGATIVE_INFINITY
    const latestRank = Number.isFinite(latestTime) ? latestTime : Number.NEGATIVE_INFINITY

    return itemRank >= latestRank ? item : currentLatest
  }, null)

  const batchId = String(latestItem?.submission_batch_id || '').trim()
  const batchItems = submittedItems.filter((item) => String(item?.submission_batch_id || '').trim() === batchId)
  const deliveryData = latestItem?.delivery_data || {}

  return {
    hasSnapshot: Boolean(batchId),
    batchId,
    submittedAt: String(latestItem?.submitted_at || '').trim(),
    submittedAtLabel: formatAdminDateTime(latestItem?.submitted_at),
    itemsCount: batchItems.length,
    deliveryData,
    deliveryComplete: Boolean(latestItem?.delivery_complete),
  }
}

export function normalizeComparableValue(field, value) {
  const rawValue = String(value ?? '').trim()

  if (field?.inputMode === 'decimal') {
    const normalizedValue = Number(parseDecimalString(rawValue))
    return Number.isFinite(normalizedValue) ? normalizedValue : rawValue
  }

  return rawValue
}

export function formatFieldPreview(field, value) {
  const text = String(value ?? '').trim()
  if (!text) return 'Не задано'

  if (field?.inputMode === 'decimal') {
    const numericValue = Number(parseDecimalString(text))
    if (!Number.isFinite(numericValue)) return text

    const suffix = field?.suffix ? ` ${field.suffix}` : ''
    return `${numericValue.toLocaleString('ru-RU', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    })}${suffix}`
  }

  return text
}

export function formatAdminRub(value) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '—'
  return `${numericValue.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽`
}

export function formatAdminCny(value) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '—'
  return `${numericValue.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ¥`
}

export function pluralizeCartItems(value) {
  const amount = Math.max(0, Number(value) || 0)
  const mod10 = amount % 10
  const mod100 = amount % 100

  if (mod10 === 1 && mod100 !== 11) return `${amount} товар`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${amount} товара`
  return `${amount} товаров`
}

export function getCartPlatformName(platform) {
  return CART_PLATFORM_NAMES[platform] || 'Маркетплейс'
}

export function getCartPlatformColor(platform) {
  return CART_PLATFORM_COLORS[platform] || 'var(--accent)'
}

export function getAdminUserAvatarInitial(user) {
  const source = String(
    user?.display_name ||
    user?.username ||
    user?.first_name ||
    user?.contact_label ||
    'A',
  ).trim()

  return source.charAt(0).toUpperCase() || 'A'
}

export function getAdminMessageChatLink(entity) {
  const username = String(entity?.username || '').trim().replace(/^@/, '')
  return username ? `https://t.me/${username}` : ''
}

export function openAdminChat(entity, { tg, haptic, onError }) {
  const chatLink = getAdminMessageChatLink(entity)
  if (!chatLink) {
    onError?.('Для этого пользователя нет публичной ссылки на чат.')
    haptic?.('error')
    return
  }

  try {
    if (typeof tg?.openTelegramLink === 'function') {
      tg.openTelegramLink(chatLink)
    } else if (typeof tg?.openLink === 'function') {
      tg.openLink(chatLink)
    } else {
      window.open(chatLink, '_blank', 'noopener,noreferrer')
    }
    haptic?.('light')
  } catch {
    onError?.('Не удалось открыть чат пользователя.')
    haptic?.('error')
  }
}

export function openAdminExternalLink(url, { tg, haptic, onError }) {
  const nextUrl = String(url || '').trim()
  if (!nextUrl) {
    onError?.('У товара нет ссылки для перехода.')
    haptic?.('error')
    return
  }

  try {
    if (typeof tg?.openLink === 'function') {
      tg.openLink(nextUrl)
    } else {
      window.open(nextUrl, '_blank', 'noopener,noreferrer')
    }
    haptic?.('light')
  } catch {
    onError?.('Не удалось открыть ссылку на товар.')
    haptic?.('error')
  }
}
