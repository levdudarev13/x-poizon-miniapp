const DEFAULT_PROMO_ACTION_LABEL = 'Подробнее'
export const DEFAULT_PROMO_BUTTON_COLOR = 'acid-lime'

export const PROMO_BANNER_BUTTON_COLORS = [
  {
    value: 'acid-lime',
    label: 'Лайм',
    description: 'Кислотный старт',
    chipGradient: 'linear-gradient(135deg, #dfff5f 0%, #98ff00 52%, #3ef470 100%)',
    chipGlow: 'rgba(152, 255, 0, 0.36)',
    style: {
      '--compare-brand-1': 'rgba(184, 255, 24, 0.92)',
      '--compare-brand-2': 'rgba(126, 255, 43, 0.3)',
      '--compare-brand-3': 'rgba(57, 118, 7, 0.78)',
      '--compare-shimmer': 'rgba(233, 255, 184, 0.42)',
      '--compare-label': 'rgba(251, 255, 241, 0.98)',
      '--compare-inner-bg': 'rgba(9, 18, 6, 0.96)',
      '--compare-inner-bg-hover': 'rgba(14, 26, 9, 0.97)',
      '--compare-glow-main': 'rgba(184, 255, 24, 0.3)',
      '--compare-glow-soft': 'rgba(85, 255, 116, 0.22)',
    },
  },
  {
    value: 'laser-cyan',
    label: 'Циан',
    description: 'Холодный digital',
    chipGradient: 'linear-gradient(135deg, #89f7ff 0%, #12f7ff 48%, #00a8ff 100%)',
    chipGlow: 'rgba(18, 247, 255, 0.34)',
    style: {
      '--compare-brand-1': 'rgba(102, 243, 255, 0.9)',
      '--compare-brand-2': 'rgba(19, 207, 255, 0.28)',
      '--compare-brand-3': 'rgba(7, 74, 117, 0.8)',
      '--compare-shimmer': 'rgba(193, 251, 255, 0.4)',
      '--compare-label': 'rgba(243, 254, 255, 0.98)',
      '--compare-inner-bg': 'rgba(4, 13, 18, 0.97)',
      '--compare-inner-bg-hover': 'rgba(7, 20, 27, 0.97)',
      '--compare-glow-main': 'rgba(36, 229, 255, 0.28)',
      '--compare-glow-soft': 'rgba(0, 116, 255, 0.2)',
    },
  },
  {
    value: 'hyper-pink',
    label: 'Фуксия',
    description: 'Pop-акцент',
    chipGradient: 'linear-gradient(135deg, #ff84f7 0%, #ff39d6 46%, #ff6b6b 100%)',
    chipGlow: 'rgba(255, 57, 214, 0.32)',
    style: {
      '--compare-brand-1': 'rgba(255, 109, 220, 0.9)',
      '--compare-brand-2': 'rgba(255, 57, 166, 0.28)',
      '--compare-brand-3': 'rgba(118, 11, 79, 0.82)',
      '--compare-shimmer': 'rgba(255, 206, 241, 0.38)',
      '--compare-label': 'rgba(255, 243, 251, 0.98)',
      '--compare-inner-bg': 'rgba(20, 7, 17, 0.96)',
      '--compare-inner-bg-hover': 'rgba(29, 10, 24, 0.97)',
      '--compare-glow-main': 'rgba(255, 78, 188, 0.28)',
      '--compare-glow-soft': 'rgba(255, 112, 112, 0.18)',
    },
  },
  {
    value: 'solar-orange',
    label: 'Мандарин',
    description: 'Теплый launch',
    chipGradient: 'linear-gradient(135deg, #ffe36b 0%, #ff8a00 50%, #ff4d4d 100%)',
    chipGlow: 'rgba(255, 138, 0, 0.34)',
    style: {
      '--compare-brand-1': 'rgba(255, 203, 76, 0.92)',
      '--compare-brand-2': 'rgba(255, 127, 22, 0.28)',
      '--compare-brand-3': 'rgba(120, 46, 9, 0.8)',
      '--compare-shimmer': 'rgba(255, 229, 186, 0.38)',
      '--compare-label': 'rgba(255, 248, 236, 0.98)',
      '--compare-inner-bg': 'rgba(22, 11, 5, 0.96)',
      '--compare-inner-bg-hover': 'rgba(31, 15, 7, 0.97)',
      '--compare-glow-main': 'rgba(255, 153, 33, 0.28)',
      '--compare-glow-soft': 'rgba(255, 86, 54, 0.18)',
    },
  },
  {
    value: 'acid-red',
    label: 'Кислотный красный',
    description: 'Агрессивный импульс',
    chipGradient: 'linear-gradient(135deg, #ff8f7a 0%, #ff2d55 42%, #ff0033 100%)',
    chipGlow: 'rgba(255, 36, 74, 0.38)',
    style: {
      '--compare-brand-1': 'rgba(255, 103, 117, 0.94)',
      '--compare-brand-2': 'rgba(255, 23, 68, 0.3)',
      '--compare-brand-3': 'rgba(130, 6, 34, 0.82)',
      '--compare-shimmer': 'rgba(255, 208, 218, 0.42)',
      '--compare-label': 'rgba(255, 244, 246, 0.98)',
      '--compare-inner-bg': 'rgba(23, 5, 9, 0.96)',
      '--compare-inner-bg-hover': 'rgba(31, 7, 12, 0.97)',
      '--compare-glow-main': 'rgba(255, 36, 74, 0.3)',
      '--compare-glow-soft': 'rgba(255, 82, 82, 0.22)',
    },
  },
  {
    value: 'nova-blue',
    label: 'Сапфир',
    description: 'Глубокий electric',
    chipGradient: 'linear-gradient(135deg, #8aa5ff 0%, #2d67ff 50%, #001eff 100%)',
    chipGlow: 'rgba(45, 103, 255, 0.34)',
    style: {
      '--compare-brand-1': 'rgba(119, 150, 255, 0.92)',
      '--compare-brand-2': 'rgba(45, 103, 255, 0.28)',
      '--compare-brand-3': 'rgba(14, 31, 130, 0.84)',
      '--compare-shimmer': 'rgba(215, 225, 255, 0.38)',
      '--compare-label': 'rgba(245, 248, 255, 0.98)',
      '--compare-inner-bg': 'rgba(5, 8, 24, 0.96)',
      '--compare-inner-bg-hover': 'rgba(8, 12, 32, 0.97)',
      '--compare-glow-main': 'rgba(45, 103, 255, 0.28)',
      '--compare-glow-soft': 'rgba(0, 30, 255, 0.18)',
    },
  },
  {
    value: 'chrome-ice',
    label: 'Хром',
    description: 'Ледяной металл',
    chipGradient: 'linear-gradient(135deg, #ffffff 0%, #b5d1ff 46%, #7ee7ff 100%)',
    chipGlow: 'rgba(181, 209, 255, 0.3)',
    style: {
      '--compare-brand-1': 'rgba(214, 233, 255, 0.92)',
      '--compare-brand-2': 'rgba(126, 184, 255, 0.24)',
      '--compare-brand-3': 'rgba(61, 94, 132, 0.82)',
      '--compare-shimmer': 'rgba(255, 255, 255, 0.42)',
      '--compare-label': 'rgba(245, 252, 255, 0.98)',
      '--compare-inner-bg': 'rgba(8, 14, 20, 0.96)',
      '--compare-inner-bg-hover': 'rgba(12, 18, 26, 0.97)',
      '--compare-glow-main': 'rgba(157, 211, 255, 0.26)',
      '--compare-glow-soft': 'rgba(111, 214, 255, 0.18)',
    },
  },
]

const PROMO_BANNER_BUTTON_COLOR_MAP = new Map(
  PROMO_BANNER_BUTTON_COLORS.map((option) => [option.value, option]),
)

export const PROMO_BANNER_BLOCK_TYPES = [
  {
    type: 'heading',
    label: 'Заголовок',
    description: 'Крупный акцент для главной мысли баннера.',
  },
  {
    type: 'subheading',
    label: 'Подзаголовок',
    description: 'Короткое пояснение под главным заголовком.',
  },
  {
    type: 'text',
    label: 'Текст',
    description: 'Основной абзац или короткая инструкция.',
  },
  {
    type: 'list',
    label: 'Список',
    description: 'Маркированные пункты с выгодами или шагами.',
  },
  {
    type: 'image',
    label: 'Фото',
    description: 'Внутреннее изображение для popup-истории.',
  },
  {
    type: 'button',
    label: 'Кнопка',
    description: 'Ссылка-кнопка в любом месте внутри popup.',
  },
]

export const PROMO_BANNER_RECOMMENDED_FORMAT = {
  cover: {
    format: 'WEBP',
    width: 1320,
    height: 480,
    quality: 0.9,
  },
  block: {
    format: 'WEBP',
    width: 1200,
    height: 1200,
    quality: 0.9,
  },
}

export const FALLBACK_PROMO_BANNERS = [
  {
    id: 101,
    label: 'Logistics X',
    title: 'Первый вход в miniapp без лишних переходов',
    subtitle: 'Здесь собраны быстрые действия для первого заказа и актуальные условия сервиса.',
    button_label: 'Подробнее',
    button_url: 'https://vk.ru/logisticsx',
    button_color: 'acid-lime',
    image_url: '/S4vXEAP-ycA.jpg',
    image_alt: 'Промо-баннер Logistics X',
    story_image_url: '/S4vXEAP-ycA.jpg',
    story_image_alt: 'Промо-баннер Logistics X',
    show_on_entry: true,
    blocks: [
      {
        id: 'welcome-heading',
        type: 'heading',
        text: 'Что можно сделать внутри miniapp',
      },
      {
        id: 'welcome-text',
        type: 'text',
        text: 'Рассчитать стоимость, собрать корзину и отправить заказ можно прямо внутри Telegram без пересылки данных вручную.',
      },
      {
        id: 'welcome-list',
        type: 'list',
        items: [
          'Мгновенный расчет по ссылке Poizon',
          'Корзина, доставка и отправка заказа в одном потоке',
          'Поддержка и FAQ всегда под рукой',
        ],
      },
    ],
  },
  {
    id: 102,
    label: 'Partner',
    title: 'Партнерская программа Logistics X',
    subtitle: 'Приглашайте друзей и переводите заинтересованных покупателей через свою ссылку.',
    button_label: 'Узнать условия',
    button_url: 'https://vk.ru/@logisticsx-partner',
    button_color: 'hyper-pink',
    image_url: '/17.png',
    image_alt: 'Партнерский баннер Logistics X',
    story_image_url: '/17.png',
    story_image_alt: 'Партнерский баннер Logistics X',
    show_on_entry: false,
    blocks: [
      {
        id: 'partner-heading',
        type: 'heading',
        text: 'Как работает партнерская механика',
      },
      {
        id: 'partner-text',
        type: 'text',
        text: 'После оформления заказов ваши рекомендации можно переводить в вознаграждение. Важно, чтобы покупатель указал вашу ссылку или имя при оформлении.',
      },
      {
        id: 'partner-list',
        type: 'list',
        items: [
          'Выплаты за приглашенных покупателей',
          'Отдельные условия для mystery box и повторных клиентов',
          'Подробные правила и примеры начислений по кнопке ниже',
        ],
      },
    ],
  },
]

function createPromoBlockId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `banner-${crypto.randomUUID()}`
  }

  return `banner-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function normalizeText(value = '') {
  return String(value ?? '').trim()
}

function normalizeListItems(value) {
  if (typeof value === 'string') {
    return value
      .split('\n')
      .map((item) => normalizeText(item))
      .filter(Boolean)
  }

  if (!Array.isArray(value)) {
    return []
  }

  return value
    .map((item) => normalizeText(item))
    .filter(Boolean)
}

export function createPromoBannerBlock(type = 'text', { empty = false } = {}) {
  const blockId = createPromoBlockId()

  if (type === 'heading') {
    return { id: blockId, type, text: empty ? '' : 'Новый заголовок' }
  }

  if (type === 'subheading') {
    return { id: blockId, type, text: empty ? '' : 'Новый подзаголовок' }
  }

  if (type === 'list') {
    return {
      id: blockId,
      type,
      items: empty ? [] : ['Первый пункт', 'Второй пункт'],
    }
  }

  if (type === 'image') {
    return {
      id: blockId,
      type,
      image_url: '',
      alt_text: '',
      caption: '',
    }
  }

  if (type === 'button') {
    return {
      id: blockId,
      type,
      button_label: empty ? '' : DEFAULT_PROMO_ACTION_LABEL,
      button_url: '',
      button_color: DEFAULT_PROMO_BUTTON_COLOR,
    }
  }

  return { id: blockId, type: 'text', text: empty ? '' : 'Новый текстовый блок' }
}

export function normalizePromoBannerBlocks(rawBlocks) {
  return (Array.isArray(rawBlocks) ? rawBlocks : [])
    .map((rawBlock, index) => {
      const block = rawBlock && typeof rawBlock === 'object' ? rawBlock : {}
      const type = normalizeText(block.type).toLowerCase()
      const id = normalizeText(block.id) || `block-${index + 1}`

      if (type === 'list') {
        return {
          id,
          type: 'list',
          items: normalizeListItems(block.items),
        }
      }

      if (type === 'image') {
        return {
          id,
          type: 'image',
          image_url: normalizeText(block.image_url),
          alt_text: normalizeText(block.alt_text),
          caption: normalizeText(block.caption),
        }
      }

      if (type === 'button') {
        const buttonUrl = normalizeText(block.button_url)
        const buttonLabel = normalizeText(block.button_label)

        return {
          id,
          type: 'button',
          button_label: buttonLabel,
          button_url: buttonUrl,
          button_color: normalizePromoBannerButtonColor(block.button_color),
        }
      }

      if (type === 'heading' || type === 'subheading' || type === 'text') {
        return {
          id,
          type,
          text: normalizeText(block.text),
        }
      }

      return null
    })
    .filter((block) => {
      if (!block) return false
      if (block.type === 'list') return block.items.length > 0
      if (block.type === 'image') return Boolean(block.image_url)
      if (block.type === 'button') return Boolean(block.button_label || block.button_url)
      return Boolean(block.text)
    })
}

export function normalizePromoBanner(rawBanner = {}) {
  const banner = rawBanner && typeof rawBanner === 'object' ? rawBanner : {}
  const storyImageUrl = normalizeText(banner.story_image_url)
  const blocks = normalizePromoBannerBlocks(banner.blocks)
  const primaryButtonBlock = blocks.find((block) => block.type === 'button') || null
  const buttonUrl = normalizeText(primaryButtonBlock?.button_url || banner.button_url)
  const buttonLabel = normalizeText(primaryButtonBlock?.button_label || banner.button_label)
  const buttonColor = normalizePromoBannerButtonColor(
    banner.button_color || primaryButtonBlock?.button_color,
  )

  return {
    id: Number(banner.id) || 0,
    label: normalizeText(banner.label),
    title: normalizeText(banner.title),
    subtitle: normalizeText(banner.subtitle),
    button_label: buttonLabel,
    button_url: buttonUrl,
    button_color: buttonColor,
    image_url: normalizeText(banner.image_url),
    image_alt: normalizeText(banner.image_alt) || normalizeText(banner.title),
    story_image_url: storyImageUrl,
    story_image_alt: storyImageUrl
      ? (normalizeText(banner.story_image_alt) || normalizeText(banner.title))
      : '',
    show_on_entry: Boolean(banner.show_on_entry),
    position: Number(banner.position) || 0,
    updated_at: Number(banner.updated_at) || 0,
    updated_at_label: normalizeText(banner.updated_at_label),
    blocks,
  }
}

export function getPromoBannerContentBlocks(source = {}) {
  const banner = normalizePromoBanner(source)
  const blocks = normalizePromoBannerBlocks(banner.blocks)
  const prefixedBlocks = []
  const titleAlreadyPresent = blocks.some(
    (block) => block.type === 'heading' && block.text === banner.title,
  )

  if (banner.title && !titleAlreadyPresent) {
    prefixedBlocks.push({
      id: createPromoBlockId(),
      type: 'heading',
      text: banner.title,
    })
  }

  if (banner.subtitle) {
    const subtitleAlreadyPresent = blocks.some(
      (block) => block.type === 'subheading' && block.text === banner.subtitle,
    )

    if (!subtitleAlreadyPresent) {
      prefixedBlocks.push({
        id: createPromoBlockId(),
        type: 'subheading',
        text: banner.subtitle,
      })
    }
  }

  const contentBlocks = [...prefixedBlocks, ...blocks]
  const hasInlineButton = blocks.some((block) => block.type === 'button')

  if (!hasInlineButton && (banner.button_label || banner.button_url)) {
    contentBlocks.push({
      id: createPromoBlockId(),
      type: 'button',
      button_label: banner.button_label,
      button_url: banner.button_url,
      button_color: banner.button_color || DEFAULT_PROMO_BUTTON_COLOR,
    })
  }

  return contentBlocks
}

export function createPromoBannerDraft(source = {}) {
  const banner = normalizePromoBanner(source)
  return {
    ...banner,
    id: banner.id || 0,
    label: banner.label || '',
    title: banner.title || '',
    subtitle: banner.subtitle || '',
    button_label: banner.button_label || '',
    button_url: banner.button_url || '',
    button_color: banner.button_color || DEFAULT_PROMO_BUTTON_COLOR,
    image_url: banner.image_url || '',
    image_alt: banner.image_alt || banner.title || '',
    story_image_url: banner.story_image_url || '',
    story_image_alt: banner.story_image_alt || '',
    show_on_entry: Boolean(banner.show_on_entry),
    blocks: getPromoBannerContentBlocks(banner),
  }
}

export function normalizePromoBannerButtonColor(value = '') {
  const normalizedValue = normalizeText(value).toLowerCase()
  if (normalizedValue === 'volt-yellow') {
    return 'acid-red'
  }
  return PROMO_BANNER_BUTTON_COLOR_MAP.has(normalizedValue)
    ? normalizedValue
    : DEFAULT_PROMO_BUTTON_COLOR
}

export function getPromoBannerButtonThemeStyle(source = '') {
  const buttonColor = typeof source === 'string'
    ? normalizePromoBannerButtonColor(source)
    : normalizePromoBanner(source).button_color

  return PROMO_BANNER_BUTTON_COLOR_MAP.get(buttonColor)?.style
    || PROMO_BANNER_BUTTON_COLOR_MAP.get(DEFAULT_PROMO_BUTTON_COLOR)?.style
    || {}
}

export function getPromoBannerActionLabel(banner) {
  const normalized = normalizePromoBanner(banner)
  if (!normalized.button_url) return ''
  return normalized.button_label || ''
}

export function getPromoBannerDisplayName(banner) {
  const normalized = normalizePromoBanner(banner)
  return normalized.title || normalized.label || 'Промо-баннер'
}

export function blocksToMultilineText(items = []) {
  return normalizeListItems(items).join('\n')
}

export async function fileToWebpDataUrl(
  file,
  {
    maxWidth = 1320,
    maxHeight = 480,
    quality = 0.9,
  } = {},
) {
  if (!(file instanceof File)) {
    throw new Error('Файл не найден')
  }

  const objectUrl = URL.createObjectURL(file)

  try {
    const image = await new Promise((resolve, reject) => {
      const nextImage = new Image()
      nextImage.onload = () => resolve(nextImage)
      nextImage.onerror = () => reject(new Error('Не удалось прочитать изображение'))
      nextImage.src = objectUrl
    })

    const scale = Math.min(
      1,
      maxWidth / Math.max(1, image.width),
      maxHeight / Math.max(1, image.height),
    )
    const targetWidth = Math.max(1, Math.round(image.width * scale))
    const targetHeight = Math.max(1, Math.round(image.height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = targetWidth
    canvas.height = targetHeight

    const context = canvas.getContext('2d', { alpha: false })
    if (!context) {
      throw new Error('Canvas недоступен для обработки изображения')
    }

    context.clearRect(0, 0, targetWidth, targetHeight)
    context.drawImage(image, 0, 0, targetWidth, targetHeight)

    const dataUrl = canvas.toDataURL('image/webp', quality)
    if (!dataUrl.startsWith('data:image/webp;base64,')) {
      throw new Error('Не удалось преобразовать изображение в WEBP')
    }

    return {
      dataUrl,
      width: targetWidth,
      height: targetHeight,
    }
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}
