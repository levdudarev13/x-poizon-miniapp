import { useState, useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import bannerChinaBuyer from '../../assets/banners/promo-china-buyer.webp'
import bannerGetsuga from '../../assets/banners/promo-getsuga.webp'
import { bootstrapWithInitData, fetchAdminShowcase, updateAdminShowcase } from '../../api/admin.js'
import BottomSheet from '../../components/ui/BottomSheet'
import FadeContent from '../../components/ui/FadeContent'
import LightRays from '../../components/ui/LightRays'
import LoadingGlyph from '../../components/ui/LoadingGlyph'
import ProductThumb from '../../components/ui/ProductThumb'
import CalculatorShowcase from './CalculatorShowcase'
import { resolveProductPriceState } from './priceState.js'
import { getSearchUnavailablePlatform, resolveSearchPagination } from './searchPagination.js'
import {
  IconArrowLeft,
  IconCalculator,
  IconChevronDown,
  IconCheck,
  IconExternalLink,
  IconInfo,
  IconLink,
  IconPackage,
  IconPlus,
  IconSearch,
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStateSuccess,
  IconTrash,
} from '../../components/ui/Icons'
import PriceBreakdown from '../../components/ui/PriceBreakdown'
import SpecsAccordion from '../../components/ui/SpecsAccordion'
import StateSurface from '../../components/ui/StateSurface'
import {
  formatBuyerCny,
  formatBuyerNumber,
  formatBuyerRub,
} from '../../constants/buyerNumbers'
import { PLATFORM_COLORS, PLATFORM_NAMES } from '../../constants/platformMeta'
import { BUYER_MOTION, BUYER_PRESS_SCALE } from '../../constants/buyerMotion'
import { BUYER_STATE_COPY } from '../../constants/buyerStateContent'
import { useTelegram } from '../../hooks/useTelegram'
import { getImageSourceCandidates, proxyImageUrl } from '../../utils/media'
import { shouldAllowFallbackVariantSelection } from '../../utils/productVariants'
import { repairMojibakeDeep } from '../../utils/text'
import './Calculator.css'

/* ── fetch wrapper with retry ── */
async function apiFetch(path, opts = {}, retries = 2) {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        ...opts,
      })
      const data = repairMojibakeDeep(await res.json())
      if (!res.ok || data.error) {
        const error = new Error(data.error || `HTTP ${res.status}`)
        error.code = data.code || ''
        error.status = res.status
        error.payload = data
        throw error
      }
      return data
    } catch (err) {
      const isNetwork = err.name === 'TypeError' || err.message === 'Failed to fetch'
      const isServerErr = err.message?.startsWith('HTTP 5')
      if (attempt < retries && (isNetwork || isServerErr)) {
        await new Promise(r => setTimeout(r, 1500 * (attempt + 1)))
        continue
      }
      throw err
    }
  }
}

const P_COLOR = { poizon: '#00c8c8', taobao: '#ff6b35', '1688': '#e74c3c', unknown: '#555' }
const P_NAME  = { poizon: 'Poizon', taobao: 'Taobao', '1688': '1688', unknown: 'Unknown' }
const NAME_SEARCH_PLATFORMS = new Set(['poizon', 'taobao', '1688'])
const NAME_SEARCH_PLATFORM_OPTIONS = [
  { key: 'taobao', label: 'Taobao' },
  { key: 'poizon', label: 'Poizon' },
  { key: '1688', label: '1688' },
]
const SEARCH_UNAVAILABLE_SHEET_META = {
  taobao: {
    badge: 'Taobao',
    title: 'Поиск временно недоступен',
    subtitle: 'Попробуйте чуть позже',
    text: 'Сейчас не можем показать результаты поиска по названию на Taobao.',
    note: 'Вернитесь немного позже или откройте товар по ссылке, если она уже есть.',
  },
  '1688': {
    badge: '1688',
    title: 'Поиск временно недоступен',
    subtitle: 'Попробуйте чуть позже',
    text: 'Сейчас не можем показать результаты поиска по названию на 1688.',
    note: 'Вернитесь немного позже или откройте товар по ссылке, если она уже есть.',
  },
}
const CALCULATOR_STATE_ICONS = {
  IconStateAlert,
  IconStateEmpty,
  IconStateRetry,
  IconStateSuccess,
}

function getCalculatorStateIcon(iconName, size = 24) {
  const Icon = CALCULATOR_STATE_ICONS[iconName]
  return Icon ? <Icon size={size} /> : null
}

function AddToCartSuccessIcon() {
  return (
    <span className="calc-success-icon">
      <span className="calc-success-icon__halo" />
      <span className="calc-success-icon__core">
        <svg className="calc-success-icon__check" width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M5 12l5 5L20 7" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </span>
  )
}

function SearchResultCardImage({ src, title }) {
  const [resolvedSrc, setResolvedSrc] = useState('')
  const [imageLoaded, setImageLoaded] = useState(false)

  useEffect(() => {
    const sourceCandidates = getImageSourceCandidates(src || '', { preferProxy: false })
    let cancelled = false

    setResolvedSrc('')
    setImageLoaded(false)

    const loadCandidate = (candidateIndex) => {
      if (cancelled || candidateIndex >= sourceCandidates.length) {
        return
      }

      const candidate = sourceCandidates[candidateIndex]
      const image = new window.Image()
      image.decoding = 'async'
      image.referrerPolicy = 'no-referrer'
      image.onload = () => {
        if (cancelled) return
        setResolvedSrc(candidate)
        setImageLoaded(true)
      }
      image.onerror = () => {
        if (cancelled) return
        loadCandidate(candidateIndex + 1)
      }
      image.src = candidate
    }

    if (sourceCandidates.length > 0) {
      loadCandidate(0)
    }

    return () => {
      cancelled = true
    }
  }, [src])

  return (
    <div className={`sr__card-img-wrap${imageLoaded ? ' is-loaded' : ''}`}>
      {resolvedSrc ? (
        <img
          src={resolvedSrc}
          alt={title || ''}
          className={`sr__card-img${imageLoaded ? ' is-loaded' : ''}`}
          loading="eager"
          fetchPriority="high"
          decoding="async"
          referrerPolicy="no-referrer"
          onLoad={() => setImageLoaded(true)}
          onError={() => {
            setImageLoaded(false)
            setResolvedSrc('')
          }}
        />
      ) : null}
      {!imageLoaded ? (
        <div className="sr__card-img-placeholder">
          <span style={{ opacity: 0.3 }}><IconPackage size={24} /></span>
        </div>
      ) : null}
    </div>
  )
}

function normalizeNameSearchPlatform(value) {
  const normalized = String(value || '').trim().toLowerCase()
  return NAME_SEARCH_PLATFORMS.has(normalized) ? normalized : ''
}

function buildTaobaoResultUrl(item) {
  const detailUrl = String(item?.detail_url || item?.url || '').trim()
  if (detailUrl) {
    return detailUrl
  }

  const itemId = String(item?.item_id || item?.id || '').trim()
  return itemId ? `https://item.taobao.com/item.htm?id=${itemId}` : ''
}

function build1688ResultUrl(item) {
  const detailUrl = String(item?.detail_url || item?.url || '').trim()
  if (detailUrl) {
    return detailUrl
  }

  const itemId = String(item?.item_id || item?.offer_id || item?.offerId || item?.id || '').trim()
  return itemId ? `https://detail.1688.com/offer/${itemId}.html` : ''
}

function buildMarketplaceResultUrl(item, platform) {
  if (platform === 'taobao') {
    return buildTaobaoResultUrl(item)
  }
  if (platform === '1688') {
    return build1688ResultUrl(item)
  }
  return ''
}

function getSelectedOptionsText(product, selVariants, selSize) {
  if (!product) return ''

  const orderedParts = Array.isArray(product.variants)
    ? product.variants
      .map((group) => {
        const groupName = typeof group?.name === 'string' ? group.name : ''
        const selectedValue = groupName ? selVariants[groupName] : ''
        return typeof selectedValue === 'string' ? selectedValue.trim() : ''
      })
      .filter(Boolean)
    : []

  const fallbackParts = orderedParts.length
    ? orderedParts
    : Object.values(selVariants)
      .map((value) => (typeof value === 'string' ? value.trim() : ''))
      .filter(Boolean)

  const normalizedSize = typeof selSize === 'string' ? selSize.trim() : ''
  if (normalizedSize && !fallbackParts.includes(normalizedSize)) {
    fallbackParts.push(normalizedSize)
  }

  return fallbackParts.join(' / ') || product.size || ''
}

function formatProductCnyLabel(product) {
  if (typeof product?.price_cny !== 'number') return ''
  const formattedPrice = formatBuyerCny(product.price_cny)
  return product?.price_is_starting ? `от ${formattedPrice}` : formattedPrice
}

function shouldKeepFallbackVariantsSelectable(product) {
  return shouldAllowFallbackVariantSelection(product)
}


/* items per page no longer used — single scroll */

/* ── mock data for Figma capture ── */
const _MOCK_STEP = new URLSearchParams(window.location.search).get('step')

const MOCK_PRODUCT = {
  url: 'https://dw4.co/t/A/abc123',
  platform: 'poizon',
  name: 'Nike Dunk Low Retro Premium MF — White / Grey',
  brand: 'Nike',
  price_cny: 620,
  price_is_starting: false,
  image_url: 'https://cdn.poizon.com/pro-img/origin-img/20240101/abc123.jpg',
  extra_images: [],
  variants: [
    { name: 'Цвет', options: ['White/Grey', 'Black/White', 'University Red'] },
    { name: 'Размер', options: ['38', '39', '40', '41', '42', '43', '44', '45'] },
  ],
  variant_price_map: {},
  available_sizes: [],
  specs: { 'Артикул': 'DV0831-003', 'Категория': 'Кроссовки', 'Пол': 'Мужской' },
}

const MOCK_RESULT = {
  subtotal_rub: 9847,
  breakdown: [
    { label: 'Товар', amount_rub: 8184, note: '620 ¥ × 13.20' },
    { label: 'Доставка по Китаю', amount_rub: 350, note: null },
    { label: 'Международная доставка', amount_rub: 813, note: '0.9 кг' },
    { label: 'Комиссия сервиса', amount_rub: 500, note: null },
  ],
  exchange_rate: { cny_rub: 13.20, age_human: '2 мин назад' },
}

const MOCK_SEARCH_RESULTS = Array.from({ length: 15 }, (_, i) => ({
  spu_id: `spu_${i}`,
  title: ['Nike Dunk Low Panda', 'Adidas Samba OG', 'New Balance 550', 'Jordan 1 Retro High', 'Nike Air Force 1'][i % 5],
  price_cny: [620, 380, 450, 890, 520][i % 5],
  image: null,
}))

const CALC_PROMO_BANNERS = [
  {
    image: bannerChinaBuyer,
    href: 'https://t.me/getsuga0',
    alt: 'China Buyer banner',
    label: 'China Buyer',
    tone: 'aqua',
  },
  {
    image: bannerGetsuga,
    href: 'https://t.me/KITAY_sofa',
    alt: 'Getsuga banner',
    label: 'Getsuga',
    tone: 'rose',
  },
]

/* ════════════════════════════════════════════════════════════════ */
const CALC_CURATED_SHOWCASE_PRODUCTS = [
  // Add pinned products here when you want the home showcase to use a fixed selection.
  // Example:
  // {
  //   id: 'bottega-veneta-tire',
  //   name: 'Bottega Veneta Tire ботинки',
  //   priceLabel: '52 105 ₽',
  //   platform: 'poizon',
  //   imageUrl: '/products/bottega-veneta-tire.png',
  //   sourceLabel: 'Poizon',
  //   note: 'Размер 41',
  //   productData: { ...historyLikePayload },
  // },
]

const SHOWCASE_DEFAULT_ACCENT = '#00c8c8'
const SHOWCASE_EDITOR_SECTIONS = [
  { id: 'top', title: 'Верхний ряд', start: 0, end: 5 },
  { id: 'bottom', title: 'Нижний ряд', start: 5, end: 10 },
]

function getShowcaseAccent(platform) {
  return PLATFORM_COLORS[platform] || SHOWCASE_DEFAULT_ACCENT
}

function buildShowcaseProductNote(product) {
  if (!product || typeof product !== 'object') {
    return ''
  }

  const size = typeof product.size === 'string' ? product.size.trim() : ''
  const brand = typeof product.brand === 'string' ? product.brand.trim() : ''
  const category = typeof product.category === 'string' ? product.category.trim() : ''

  return [size, brand || category].filter(Boolean).join(' / ')
}

function buildCuratedShowcaseProducts() {
  return CALC_CURATED_SHOWCASE_PRODUCTS
    .map((item, index) => ({
      id: item.id || `curated-${index}`,
      name: item.name || 'Товар без названия',
      imageUrl: item.imageUrl || item.image_url || '',
      priceLabel: item.priceLabel
        || (typeof item.totalRub === 'number' ? formatBuyerRub(item.totalRub) : '')
        || (typeof item.priceCny === 'number' ? formatBuyerCny(item.priceCny) : ''),
      sourceLabel: item.sourceLabel || PLATFORM_NAMES[item.platform] || 'Featured',
      note: item.note || '',
      accentColor: item.accentColor || getShowcaseAccent(item.platform),
      productData: item.productData || null,
      href: item.href || '',
    }))
    .filter((item) => item.name)
}

function buildHistoryShowcaseProducts(items) {
  if (!Array.isArray(items)) {
    return []
  }

  const seen = new Set()

  return items
    .filter((item) => {
      const key = item.product_url || item.url || `${item.name || 'item'}-${item.size || ''}-${item.platform || ''}`
      if (seen.has(key)) {
        return false
      }
      seen.add(key)
      return true
    })
    .map((item, index) => {
      const totalRub = item.subtotal_rub || item.total_with_margin_rub || 0
      const platformLabel = PLATFORM_NAMES[item.platform] || item.platform || 'Товар'
      const note = item.size ? `Размер ${item.size}` : (item.brand || '')

      return {
        id: item.id || `history-showcase-${index}`,
        name: item.name || 'Товар без названия',
        imageUrl: item.image_url || '',
        priceLabel: totalRub > 0
          ? formatBuyerRub(totalRub)
          : (typeof item.price_cny === 'number' ? formatBuyerCny(item.price_cny) : ''),
        sourceLabel: platformLabel,
        note,
        accentColor: getShowcaseAccent(item.platform),
        sourceData: item,
      }
    })
    .filter((item) => item.name && item.priceLabel)
    .slice(0, 10)
}

function normalizeShowcaseLinks(links) {
  return Array.from({ length: 10 }, (_, index) => String(links?.[index] || ''))
}

function extractShowcaseInputUrl(value) {
  const text = String(value || '').trim()
  if (!text) {
    return ''
  }

  if (text.startsWith('http://') || text.startsWith('https://')) {
    return text
  }

  const match = text.match(/https?:\/\/[^\s\u4e00-\u9fff\u0400-\u04FF"'<>]+/i)
  return match ? match[0].replace(/[.,;:!?)]*$/, '') : ''
}

function getShowcaseEditorRequestMessage(requestError, fallbackMessage) {
  if (requestError?.message === 'Not found') {
    return 'Сервер витрины не ответил. Перезапустите miniapp server и попробуйте еще раз.'
  }

  return requestError?.message || fallbackMessage
}

function buildManagedShowcaseProducts(items) {
  if (!Array.isArray(items)) {
    return []
  }

  return items
    .map((item) => {
      const product = item?.product || {}
      const platform = product.platform || 'poizon'
      const sourceLabel = PLATFORM_NAMES[platform] || platform || 'Товар'

      return {
        id: `managed-showcase-${item?.slot || product.url || product.name || 'item'}`,
        slot: Number(item?.slot) || null,
        name: product.name || 'Товар без названия',
        imageUrl: product.image_url || '',
        priceLabel: typeof item?.subtotal_rub === 'number' && Number.isFinite(item.subtotal_rub)
          ? formatBuyerRub(item.subtotal_rub)
          : formatProductCnyLabel(product),
        sourceLabel,
        note: buildShowcaseProductNote(product),
        accentColor: getShowcaseAccent(platform),
        sourceData: product,
        href: item?.url || product.url || '',
      }
    })
    .filter((item) => item.name)
    .slice(0, 10)
}

function buildShowcaseEditorSlots(links, items) {
  const itemBySlot = new Map(
    Array.isArray(items)
      ? items
        .filter((item) => Number(item?.slot) > 0)
        .map((item) => [Number(item.slot), item])
      : [],
  )

  return normalizeShowcaseLinks(links).map((url, index) => {
    const slot = index + 1
    const showcaseItem = itemBySlot.get(slot) || null
    const product = showcaseItem?.product || null
    const platform = product?.platform || 'poizon'

    return {
      slot,
      url,
      normalizedUrl: extractShowcaseInputUrl(url),
      product,
      occupied: Boolean(url),
      accentColor: getShowcaseAccent(platform),
      sourceLabel: PLATFORM_NAMES[platform] || platform || 'Товар',
      priceLabel: typeof showcaseItem?.subtotal_rub === 'number' && Number.isFinite(showcaseItem.subtotal_rub)
        ? formatBuyerRub(showcaseItem.subtotal_rub)
        : formatProductCnyLabel(product),
      note: buildShowcaseProductNote(product),
      href: showcaseItem?.url || product?.url || url || '',
    }
  })
}

function buildShowcaseUpdatePayloadFromSlots(slots) {
  return Array.from({ length: 10 }, (_, index) => String(slots?.[index]?.url || ''))
}

function getDefaultShowcaseSlotSelection(slots) {
  const safeSlots = Array.isArray(slots) ? slots : []
  const emptySlot = safeSlots.find((slot) => !slot.occupied)
  if (emptySlot) {
    return { slot: emptySlot.slot, input: '' }
  }

  const firstSlot = safeSlots[0]
  return {
    slot: firstSlot?.slot || 1,
    input: firstSlot?.url || '',
  }
}

const Calculator = forwardRef(function Calculator({ onCartChange, active = false }, ref) {
  const { userId, firstName, haptic, hideKeyboard, initData } = useTelegram()
  const prefersReducedMotion = useReducedMotion()

  const greeting = (() => {
    const h = new Date().getHours()
    if (h >= 6 && h < 12) return 'Доброе утро'
    if (h >= 12 && h < 18) return 'Добрый день'
    if (h >= 18 && h < 23) return 'Добрый вечер'
    return 'Доброй ночи'
  })()

  const [step, setStep] = useState(_MOCK_STEP === 'product' || _MOCK_STEP === 'search-results' ? _MOCK_STEP : 'idle')
  const [url, setUrl] = useState('')
  const [product, setProduct] = useState(_MOCK_STEP === 'product' ? MOCK_PRODUCT : null)
  const [result, setResult] = useState(_MOCK_STEP === 'product' ? MOCK_RESULT : null)
  const [calcLoading, setCalcLoading] = useState(false)
  const [error, setError] = useState(null)

  const [rate, setRate] = useState(_MOCK_STEP === 'product' ? { cny_rub: 13.20 } : null)
  const [activeImg, setActiveImg] = useState(0)
  const [selVariants, setSelVariants] = useState({})
  const [selSize, setSelSize] = useState('')
  const [manualPrice, setManualPrice] = useState('')

  const [savedCalcId, setSavedCalcId] = useState(null)
  const [addedToCart, setAddedToCart] = useState(false)
  const [cartAdding, setCartAdding] = useState(false)
  const addedCartUrlRef = useRef(null)
  const addToCartSuccessRef = useRef(null)
  const idlePageRef = useRef(null)
  const [loadingMode, setLoadingMode] = useState('product')
  const [loadingText, setLoadingText] = useState('')
  const [specsOpen, setSpecsOpen] = useState(false)
  const [adminSettings, setAdminSettings] = useState(null)

  /* ── compare state ── */
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareData, setCompareData] = useState(null)
  const [compareMarket, setCompareMarket] = useState(null)
  const [compareLoadingText, setCompareLoadingText] = useState('')
  const [compareShowAll, setCompareShowAll] = useState(false)
  const [promoSlideIndex, setPromoSlideIndex] = useState(0)

  /* ── search state ── */
  const [searchQuery, setSearchQuery] = useState(_MOCK_STEP === 'search-results' ? 'Nike Dunk Low' : '')
  const searchCount = 20
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchLoadingMore, setSearchLoadingMore] = useState(false)
  const [searchError, setSearchError] = useState(null)
  const [searchPlatform, setSearchPlatform] = useState('')
  const [activeSearchPlatform, setActiveSearchPlatform] = useState('')
  const [searchResultOpenError, setSearchResultOpenError] = useState(null)
  const [searchResults, setSearchResults] = useState(_MOCK_STEP === 'search-results' ? MOCK_SEARCH_RESULTS : [])
  const [searchRate, setSearchRate] = useState(_MOCK_STEP === 'search-results' ? 13.20 : null)
  const [searchHasMore, setSearchHasMore] = useState(false)
  const [searchNextStartId, setSearchNextStartId] = useState(0)
  const [searchUnavailablePlatform, setSearchUnavailablePlatform] = useState('')
  const [showcaseProducts, setShowcaseProducts] = useState(() => buildCuratedShowcaseProducts())
  const [isAdminViewer, setIsAdminViewer] = useState(false)
  const [showcaseEditorOpen, setShowcaseEditorOpen] = useState(false)
  const [showcaseEditorLoading, setShowcaseEditorLoading] = useState(false)
  const [showcaseEditorSaving, setShowcaseEditorSaving] = useState(false)
  const [showcaseEditorError, setShowcaseEditorError] = useState('')
  const [showcaseEditorSlotErrors, setShowcaseEditorSlotErrors] = useState({})
  const [showcaseEditorSlots, setShowcaseEditorSlots] = useState(() => buildShowcaseEditorSlots([], []))
  const [showcaseEditorActiveSlot, setShowcaseEditorActiveSlot] = useState(1)
  const [showcaseEditorInput, setShowcaseEditorInput] = useState('')
  const promoTouchRef = useRef({ x: 0, y: 0, moved: false })
  const showcaseFocusTimeoutsRef = useRef([])
  const showcaseEditorInputRef = useRef(null)

  const activeShowcaseEditorSlot = showcaseEditorSlots.find((slot) => slot.slot === showcaseEditorActiveSlot) || showcaseEditorSlots[0] || null
  const showcaseEditorInputUrl = extractShowcaseInputUrl(showcaseEditorInput)
  const showcaseEditorDuplicateSlot = showcaseEditorInputUrl
    ? showcaseEditorSlots.find(
      (slot) => slot.slot !== showcaseEditorActiveSlot && slot.normalizedUrl === showcaseEditorInputUrl,
    ) || null
    : null
  const showcaseEditorActiveSlotError = activeShowcaseEditorSlot
    ? showcaseEditorSlotErrors?.[activeShowcaseEditorSlot.slot] || ''
    : ''
  const showcaseEditorInputUnchanged = Boolean(
    activeShowcaseEditorSlot?.normalizedUrl
    && showcaseEditorInputUrl
    && showcaseEditorInputUrl === activeShowcaseEditorSlot.normalizedUrl,
  )

  const clearShowcaseFocusTimers = useCallback(() => {
    showcaseFocusTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId))
    showcaseFocusTimeoutsRef.current = []
  }, [])

  const dismissShowcaseKeyboard = useCallback(() => {
    const activeElement = document.activeElement
    if (activeElement instanceof HTMLElement) {
      activeElement.blur()
    }

    hideKeyboard?.()
  }, [hideKeyboard])

  const scrollShowcaseInputIntoView = useCallback((inputElement, behavior = 'smooth') => {
    if (!(inputElement instanceof HTMLElement)) return

    const body = inputElement.closest('.calc-showcase-sheet__body')
    if (body instanceof HTMLElement) {
      const bodyRect = body.getBoundingClientRect()
      const inputRect = inputElement.getBoundingClientRect()
      const inputOffsetWithinBody = inputRect.top - bodyRect.top + body.scrollTop
      const targetTop = Math.max(0, inputOffsetWithinBody - Math.max(88, Math.round(body.clientHeight * 0.3)))
      body.scrollTo({ top: targetTop, behavior })
    }

    inputElement.scrollIntoView({ block: 'center', inline: 'nearest', behavior })
  }, [])

  const scheduleShowcaseInputVisibilitySync = useCallback((inputElement) => {
    if (!(inputElement instanceof HTMLElement)) return

    clearShowcaseFocusTimers()

    ;[0, 140, 320].forEach((delay, index) => {
      const timeoutId = window.setTimeout(() => {
        scrollShowcaseInputIntoView(
          inputElement,
          prefersReducedMotion || index === 0 ? 'auto' : 'smooth',
        )
      }, delay)

      showcaseFocusTimeoutsRef.current.push(timeoutId)
    })
  }, [clearShowcaseFocusTimers, prefersReducedMotion, scrollShowcaseInputIntoView])
  /* featuredIdx removed — grid-only mode */

  /* ── imperative handle for opening product from History ── */
  useImperativeHandle(ref, () => ({
    openProduct(data) {
      const d = {
        url: data.product_url || '',
        platform: data.platform || 'poizon',
        name: data.name || '',
        brand: data.brand || '',
        price_cny: data.price_cny,
        price_is_starting: Boolean(data.price_is_starting),
        size: data.size || '',
        category: data.category || '',
        weight_kg: null,
        weight_estimated: false,
        city: data.city || '',
        delivery_type: data.delivery_type || '',
        image_url: data.image_url || '',
        extra_images: data.extra_images || [],
        specs: data.specs || {},
        available_sizes: data.available_sizes || [],
        variants: data.variants || [],
        variant_price_map: data.variant_price_map || {},
        original_variants: [],
        notes: '',
        auto_detected: [],
      }
      setProduct(d)
      setActiveImg(0)
      setSelVariants({})
      setSelSize('')
      setManualPrice('')
      setResult(null)
      setSavedCalcId(null)
      setAddedToCart(false)
      addedCartUrlRef.current = null
      setSpecsOpen(false)
      setSearchResults([])
      setStep('product')
    }
  }))

  /* ── bootstrap ── */
  const openShowcaseProduct = useCallback((data) => {
    const nextProduct = {
      url: data.product_url || data.url || '',
      platform: data.platform || 'poizon',
      name: data.name || '',
      brand: data.brand || '',
      price_cny: data.price_cny,
      price_is_starting: Boolean(data.price_is_starting),
      size: data.size || '',
      category: data.category || '',
      weight_kg: null,
      weight_estimated: false,
      city: data.city || '',
      delivery_type: data.delivery_type || '',
      image_url: data.image_url || '',
      extra_images: data.extra_images || [],
      specs: data.specs || {},
      available_sizes: data.available_sizes || [],
      variants: data.variants || [],
      variant_price_map: data.variant_price_map || {},
      original_variants: [],
      notes: '',
      auto_detected: [],
    }

    setProduct(nextProduct)
    setActiveImg(0)
    setSelVariants({})
    setSelSize('')
    setManualPrice('')
    setResult(null)
    setSavedCalcId(null)
    setAddedToCart(false)
    addedCartUrlRef.current = null
    setSpecsOpen(false)
    setSearchResults([])
    setStep('product')
  }, [])

  const applyShowcaseSource = useCallback(async (bootstrapPayload) => {
    const managedProducts = buildManagedShowcaseProducts(bootstrapPayload?.showcase_items)
    const showcaseConfiguredCount = Number(bootstrapPayload?.showcase_configured_count || 0)

    if (managedProducts.length || showcaseConfiguredCount > 0) {
      setShowcaseProducts(managedProducts)
      return
    }

    if (CALC_CURATED_SHOWCASE_PRODUCTS.length) {
      setShowcaseProducts(buildCuratedShowcaseProducts())
      return
    }

    if (!userId) {
      setShowcaseProducts([])
      return
    }

    try {
      const response = await fetch(`/api/history?user_id=${userId}`)
      const data = repairMojibakeDeep(await response.json())

      if (data?.error) {
        throw new Error(data.error)
      }

      setShowcaseProducts(buildHistoryShowcaseProducts(Array.isArray(data) ? data : []))
    } catch {
      setShowcaseProducts([])
    }
  }, [userId])

  const refreshBootstrap = useCallback(async () => {
    try {
      const data = await bootstrapWithInitData({ userId, initData })
      if (data?.rate) {
        setRate(data.rate)
        if (data.rate.cny_rub != null) setSearchRate(data.rate.cny_rub)
      }
      if (data?.admin_settings) {
        setAdminSettings(data.admin_settings)
      }
      setIsAdminViewer(Boolean(data?.is_admin))
      await applyShowcaseSource(data)
      return data
    } catch {
      setIsAdminViewer(false)
      return null
    }
  }, [applyShowcaseSource, initData, userId])

  useEffect(() => {
    if (!active) return
    refreshBootstrap()
  }, [active, refreshBootstrap])

  const handleShowcaseCardSelect = useCallback((item) => {
    const productData = item?.productData || item?.sourceData

    if (productData) {
      haptic?.('light')
      openShowcaseProduct(productData)
      return
    }

    if (item?.href) {
      haptic?.('light')
      window.open(item.href, '_blank', 'noopener,noreferrer')
    }
  }, [haptic, openShowcaseProduct])

  const handleOpenShowcaseEditor = useCallback(async () => {
    if (!initData) return

    const emptySlots = buildShowcaseEditorSlots([], [])

    setShowcaseEditorOpen(true)
    setShowcaseEditorLoading(true)
    setShowcaseEditorError('')
    setShowcaseEditorSlotErrors({})
    setShowcaseEditorSlots(emptySlots)
    setShowcaseEditorActiveSlot(1)
    setShowcaseEditorInput('')

    try {
      const data = await fetchAdminShowcase({ initData })
      const nextSlots = buildShowcaseEditorSlots(data?.links, data?.items)
      const defaultSelection = getDefaultShowcaseSlotSelection(nextSlots)

      setShowcaseEditorSlots(nextSlots)
      setShowcaseEditorActiveSlot(defaultSelection.slot)
      setShowcaseEditorInput(defaultSelection.input)
    } catch (requestError) {
      setShowcaseEditorError(
        getShowcaseEditorRequestMessage(requestError, 'Не удалось загрузить настройки витрины.'),
      )
    } finally {
      setShowcaseEditorLoading(false)
    }
  }, [initData])

  const clearShowcaseEditorSlotError = useCallback((slotNumber) => {
    setShowcaseEditorSlotErrors((currentErrors) => {
      if (!currentErrors?.[slotNumber]) return currentErrors
      const nextErrors = { ...currentErrors }
      delete nextErrors[slotNumber]
      return nextErrors
    })
  }, [])

  const focusShowcaseEditorInput = useCallback(() => {
    window.requestAnimationFrame(() => {
      const inputElement = showcaseEditorInputRef.current
      if (!(inputElement instanceof HTMLElement)) return

      inputElement.focus({ preventScroll: true })
      scheduleShowcaseInputVisibilitySync(inputElement)
    })
  }, [scheduleShowcaseInputVisibilitySync])

  const handleShowcaseSlotSelect = useCallback((slot, { focus = false } = {}) => {
    if (!slot) return

    setShowcaseEditorActiveSlot(slot.slot)
    setShowcaseEditorInput(slot.url || '')
    setShowcaseEditorError('')
    clearShowcaseEditorSlotError(slot.slot)

    if (focus) {
      focusShowcaseEditorInput()
    }
  }, [clearShowcaseEditorSlotError, focusShowcaseEditorInput])

  const handleShowcaseInputChange = useCallback((value) => {
    setShowcaseEditorInput(value)
    setShowcaseEditorError('')

    if (activeShowcaseEditorSlot) {
      clearShowcaseEditorSlotError(activeShowcaseEditorSlot.slot)
    }
  }, [activeShowcaseEditorSlot, clearShowcaseEditorSlotError])

  const handleShowcaseEditorClose = useCallback(() => {
    if (showcaseEditorSaving) return
    clearShowcaseFocusTimers()
    dismissShowcaseKeyboard()
    setShowcaseEditorOpen(false)
    setShowcaseEditorError('')
    setShowcaseEditorSlotErrors({})
  }, [clearShowcaseFocusTimers, dismissShowcaseKeyboard, showcaseEditorSaving])

  const handleShowcaseSubmit = useCallback(async () => {
    if (!initData || !activeShowcaseEditorSlot || !showcaseEditorInputUrl || showcaseEditorDuplicateSlot || showcaseEditorInputUnchanged) return

    clearShowcaseFocusTimers()
    dismissShowcaseKeyboard()
    setShowcaseEditorSaving(true)
    setShowcaseEditorError('')
    setShowcaseEditorSlotErrors({})

    try {
      const activeSlotNumber = activeShowcaseEditorSlot.slot
      const wasOccupied = activeShowcaseEditorSlot.occupied
      const nextLinks = buildShowcaseUpdatePayloadFromSlots(showcaseEditorSlots)
      nextLinks[activeSlotNumber - 1] = showcaseEditorInputUrl

      const data = await updateAdminShowcase({
        initData,
        links: nextLinks,
      })

      const nextSlots = buildShowcaseEditorSlots(data?.links, data?.items)
      const nextSelectedSlot = nextSlots.find((slot) => slot.slot === activeSlotNumber) || nextSlots[0] || null
      const nextEmptySlot = nextSlots.find((slot) => slot.slot > activeSlotNumber && !slot.occupied)
        || nextSlots.find((slot) => !slot.occupied)

      setShowcaseEditorSlots(nextSlots)
      await applyShowcaseSource({
        showcase_items: data?.items || [],
        showcase_configured_count: data?.configured_count || 0,
      })

      if (!wasOccupied && nextEmptySlot) {
        setShowcaseEditorActiveSlot(nextEmptySlot.slot)
        setShowcaseEditorInput('')
      } else {
        setShowcaseEditorActiveSlot(nextSelectedSlot?.slot || activeSlotNumber)
        setShowcaseEditorInput(nextSelectedSlot?.url || '')
      }

      haptic?.('success')
    } catch (requestError) {
      const nextErrorMessage = requestError.message === 'invalid_showcase_links'
        ? 'Проверьте ссылки: одна или несколько карточек заполнены некорректно.'
        : requestError.message === 'duplicate_showcase_links'
          ? 'Этот товар уже стоит на витрине. Уберите дубль или выберите другой слот.'
        : requestError.message === 'showcase_products_unavailable'
          ? 'Не удалось загрузить один или несколько товаров по указанным ссылкам.'
          : getShowcaseEditorRequestMessage(requestError, 'Не удалось сохранить витрину.')

      setShowcaseEditorError(nextErrorMessage)
      setShowcaseEditorSlotErrors(requestError?.slot_errors || {})
      haptic?.('error')
    } finally {
      setShowcaseEditorSaving(false)
    }
  }, [
    activeShowcaseEditorSlot,
    applyShowcaseSource,
    clearShowcaseFocusTimers,
    dismissShowcaseKeyboard,
    haptic,
    initData,
    showcaseEditorDuplicateSlot,
    showcaseEditorInputUnchanged,
    showcaseEditorInputUrl,
    showcaseEditorSlots,
  ])

  const handleShowcaseSlotRemove = useCallback(async (slot) => {
    if (!initData || !slot?.occupied) return

    clearShowcaseFocusTimers()
    dismissShowcaseKeyboard()
    setShowcaseEditorSaving(true)
    setShowcaseEditorError('')
    setShowcaseEditorSlotErrors({})

    try {
      const nextLinks = buildShowcaseUpdatePayloadFromSlots(showcaseEditorSlots)
      nextLinks[slot.slot - 1] = ''

      const data = await updateAdminShowcase({
        initData,
        links: nextLinks,
      })

      const nextSlots = buildShowcaseEditorSlots(data?.links, data?.items)
      const nextSelectedSlot = nextSlots.find((item) => item.slot === slot.slot) || nextSlots[0] || null

      setShowcaseEditorSlots(nextSlots)
      setShowcaseEditorActiveSlot(nextSelectedSlot?.slot || slot.slot)
      setShowcaseEditorInput('')

      await applyShowcaseSource({
        showcase_items: data?.items || [],
        showcase_configured_count: data?.configured_count || 0,
      })

      haptic?.('success')
    } catch (requestError) {
      const nextErrorMessage = getShowcaseEditorRequestMessage(
        requestError,
        'Не удалось убрать товар из витрины.',
      )

      setShowcaseEditorError(nextErrorMessage)
      setShowcaseEditorSlotErrors(requestError?.slot_errors || {})
      haptic?.('error')
    } finally {
      setShowcaseEditorSaving(false)
    }
  }, [
    applyShowcaseSource,
    clearShowcaseFocusTimers,
    dismissShowcaseKeyboard,
    haptic,
    initData,
    showcaseEditorSlots,
  ])

  useEffect(() => {
    if (!active || step !== 'idle' || prefersReducedMotion || CALC_PROMO_BANNERS.length < 2) {
      return undefined
    }

    const intervalId = window.setInterval(() => {
      setPromoSlideIndex((currentIndex) => (currentIndex + 1) % CALC_PROMO_BANNERS.length)
    }, 4000)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [active, prefersReducedMotion, step])

  /* ── publish calculator-specific shell swipe root ── */
  useEffect(() => {
    const blockShellSwipe = active && (step === 'search-results' || step === 'product' || step === 'loading' || compareOpen)
    document.body.dataset.shellSwipeRootCalculator = blockShellSwipe ? '0' : '1'
    return () => { document.body.dataset.shellSwipeRootCalculator = '1' }
  }, [active, step, compareOpen])

  /* ── keep legacy shell fallback in sync during migration ── */
  useEffect(() => {
    const blockShellSwipe = active && (step === 'search-results' || step === 'product' || step === 'loading' || compareOpen)
    document.body.dataset.blockTabSwipe = blockShellSwipe ? '1' : '0'
    return () => { document.body.dataset.blockTabSwipe = '0' }
  }, [active, step, compareOpen])

  /* ── gallery swipe ── */
  const galleryTouchRef = useRef({ x: 0, y: 0 })
  const onGalleryTouchStart = (e) => {
    galleryTouchRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
  }
  const onGalleryTouchEnd = (e) => {
    const dx = galleryTouchRef.current.x - e.changedTouches[0].clientX
    const dy = galleryTouchRef.current.y - e.changedTouches[0].clientY
    if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy) * 1.2) return
    const max = images.length - 1
    if (max <= 0) return
    if (dx > 0 && activeImg < max) {
      setActiveImg(activeImg + 1)
      haptic?.('light')
    } else if (dx < 0 && activeImg > 0) {
      setActiveImg(activeImg - 1)
      haptic?.('light')
    }
  }

  /* ── loading text stages ── */
  useEffect(() => {
    if (step !== 'loading') return
    // Don't override compare loading text
    if (compareLoadingText) return
    setLoadingText('Загружаю товар...')
    const t1 = setTimeout(() => setLoadingText('Анализирую данные...'), 5000)
    const t2 = setTimeout(() => setLoadingText('Почти готово...'), 15000)
    const t3 = setTimeout(() => setLoadingText('Ещё немного...'), 30000)
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
  }, [step, compareLoadingText])

  /* ── images ── */
  useEffect(() => {
    if (step !== 'loading' || compareLoadingText || loadingMode !== 'search') return
    setLoadingText('Ищу товары...')
    const t1 = setTimeout(() => setLoadingText('Собираю результаты...'), 5000)
    const t2 = setTimeout(() => setLoadingText('Почти готово...'), 15000)
    const t3 = setTimeout(() => setLoadingText('Ещё немного...'), 30000)
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
  }, [step, compareLoadingText, loadingMode])

  const images = product
    ? [product.image_url, ...(product.extra_images || [])].filter(Boolean).map(proxyImageUrl)
    : []

  /* ── current price from variants (cascade-aware) ── */
  const priceState = resolveProductPriceState(product, selVariants, manualPrice)

  /* ── cascade helpers ── */
  const getFilteredEntries = useCallback(
    (groupIndex) => {
      const map = product?.variant_price_map
      const groups = product?.variants || []
      if (!map) return []
      const entries = Object.entries(map)
      return entries.filter(([k]) => {
        try {
          const pairs = JSON.parse(k)
          for (let i = 0; i < groupIndex && i < groups.length; i++) {
            const gName = groups[i].name
            const sel = selVariants[gName]
            if (!sel) continue
            const found = pairs.find(([g]) => g === gName)
            if (found && found[1] !== sel) return false
          }
          return true
        } catch { return false }
      })
    },
    [product, selVariants],
  )

  const isOptionAvailable = useCallback(
    (groupName, opt, groupIndex) => {
      const map = product?.variant_price_map
      if (!map || !Object.keys(map).length) {
        return shouldKeepFallbackVariantsSelectable(product)
      }
      const filtered = getFilteredEntries(groupIndex)
      return filtered.some(([k]) => {
        try {
          return JSON.parse(k).some(([g, o]) => g === groupName && o === opt)
        } catch { return false }
      })
    },
    [getFilteredEntries, product],
  )

  const getOptionPrice = useCallback(
    (groupName, opt, groupIndex) => {
      const filtered = getFilteredEntries(groupIndex)
      let min = Infinity
      for (const [k, p] of filtered) {
        try {
          if (JSON.parse(k).some(([g, o]) => g === groupName && o === opt))
            min = Math.min(min, p)
        } catch {
          // Ignore malformed variant map entries and keep scanning the valid ones.
        }
      }
      return min === Infinity ? null : min
    },
    [getFilteredEntries],
  )

  /* ── auto-reset unavailable selections ── */
  useEffect(() => {
    const map = product?.variant_price_map
    const groups = product?.variants || []
    if (!map || !Object.keys(map).length || !groups.length) return

    let changed = false
    const next = { ...selVariants }

    for (let i = 0; i < groups.length; i++) {
      const g = groups[i]
      const opts = g.options || []
      if (opts.length < 2) continue
      const sel = next[g.name]
      if (!sel) continue

      const entries = Object.entries(map).filter(([k]) => {
        try {
          const pairs = JSON.parse(k)
          for (let j = 0; j < i; j++) {
            const gN = groups[j].name
            const sv = next[gN]
            if (!sv) continue
            const f = pairs.find(([gg]) => gg === gN)
            if (f && f[1] !== sv) return false
          }
          return true
        } catch { return false }
      })

      const available = entries.some(([k]) => {
        try {
          return JSON.parse(k).some(([gg, oo]) => gg === g.name && oo === sel)
        } catch { return false }
      })

      if (!available) {
        const names = opts.map(r => typeof r === 'string' ? r : r.name || String(r))
        const first = names.find(n =>
          entries.some(([k]) => {
            try {
              return JSON.parse(k).some(([gg, oo]) => gg === g.name && oo === n)
            } catch { return false }
          })
        )
        if (first) {
          next[g.name] = first
        } else {
          delete next[g.name]
        }
        changed = true
      }
    }

    if (changed) setSelVariants(next)
  }, [product, selVariants])

  const curPrice = priceState.calculationPrice
  const displayPriceCny = priceState.displayPrice
  const hasStartingPrice = priceState.isStartingPrice
  const curPriceRub = curPrice && rate ? Math.round(curPrice * rate.cny_rub) : null
  const selectedOptionsText = getSelectedOptionsText(product, selVariants, selSize)
  const pricingSnapshot = JSON.stringify({
    rate: rate?.cny_rub ?? null,
    commission: adminSettings?.commission_pct ?? null,
    minCommission: adminSettings?.min_commission_rub ?? null,
    logistics: adminSettings?.logistics_rub ?? null,
    insurance: adminSettings?.insurance_rub ?? null,
    perKg: adminSettings?.price_per_kg ?? null,
    deliveryTime: adminSettings?.delivery_time ?? null,
    nextShipmentDate: adminSettings?.next_shipment_date ?? null,
  })

  // Button state: ref survives any re-render/effect that resets addedToCart state
  const isInCart = addedToCart || (product && addedCartUrlRef.current === product.url)
  const searchStateCopy = searchError === 'empty'
    ? BUYER_STATE_COPY.calculator.searchEmpty
    : searchError === 'error'
      ? BUYER_STATE_COPY.calculator.searchError
      : null
  const addToCartSuccessState = BUYER_STATE_COPY.calculator.addToCartSuccess
  const canSubmitLink = Boolean(url.trim())
  const canSubmitNameSearch = Boolean(searchQuery.trim()) && NAME_SEARCH_PLATFORMS.has(searchPlatform)
  const searchUnavailableMeta = SEARCH_UNAVAILABLE_SHEET_META[searchUnavailablePlatform] || null
  const closeSearchUnavailableSheet = () => {
    setSearchUnavailablePlatform('')
    haptic?.('light')
  }
  const searchUnavailableSheet = (
    <BottomSheet
      open={Boolean(searchUnavailableMeta)}
      onClose={closeSearchUnavailableSheet}
      badge={searchUnavailableMeta?.badge || ''}
      title={searchUnavailableMeta?.title || ''}
      subtitle={searchUnavailableMeta?.subtitle || ''}
      className={`calc-search-unavailable-sheet${searchUnavailablePlatform ? ` calc-search-unavailable-sheet--${searchUnavailablePlatform}` : ''}`}
      overlayClassName="calc-search-unavailable-sheet__overlay"
      bodyClassName="calc-search-unavailable-sheet__body"
      footer={(
        <button
          type="button"
          className="calc-search-unavailable-sheet__button pressable"
          onClick={closeSearchUnavailableSheet}
        >
          Закрыть
        </button>
      )}
    >
      <div className="calc-search-unavailable-sheet__content" data-shell-swipe-block="true">
        <div className="calc-search-unavailable-sheet__icon" aria-hidden="true">
          <IconInfo size={18} />
        </div>
        <div className="calc-search-unavailable-sheet__copy">
          <p className="calc-search-unavailable-sheet__text">
            {searchUnavailableMeta?.text || ''}
          </p>
          <p className="calc-search-unavailable-sheet__note">
            {searchUnavailableMeta?.note || ''}
          </p>
        </div>
      </div>
    </BottomSheet>
  )

  /* ── auto-calculate when price changes ── */
  const calcKey = step === 'product' && product && curPrice
    ? `${product.url}:${curPrice}:${selectedOptionsText}`
    : null

  useEffect(() => {
    if (!active) return
    if (!calcKey || !product || !curPrice) {
      setResult(null)
      return
    }
    const ac = new AbortController()
    setCalcLoading(true)

    fetch('/api/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product: {
          ...product,
          price_cny: curPrice,
          price_is_starting: false,
          size: selectedOptionsText,
        },
        user_id: userId || 0,
        calc_id: savedCalcId || undefined,
      }),
      signal: ac.signal,
    })
      .then((r) => r.json())
      .then((r) => {
        if (!r.error) {
          setResult(r)
          if (r.calc_id) setSavedCalcId(r.calc_id)
        }
        setCalcLoading(false)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') setCalcLoading(false)
      })

    return () => ac.abort()
  }, [active, calcKey, curPrice, pricingSnapshot, product, savedCalcId, selectedOptionsText, userId])

  useEffect(() => {
    if (!addedToCart) return
    const target = addToCartSuccessRef.current
    if (!target) return

    const timeoutId = window.setTimeout(() => {
      target.scrollIntoView({
        behavior: prefersReducedMotion ? 'auto' : 'smooth',
        block: 'center',
        inline: 'nearest',
      })
    }, prefersReducedMotion ? 0 : 120)

    return () => window.clearTimeout(timeoutId)
  }, [addedToCart, prefersReducedMotion])

  useEffect(() => () => {
    clearShowcaseFocusTimers()
  }, [clearShowcaseFocusTimers])

  useEffect(() => {
    if (!showcaseEditorOpen) {
      clearShowcaseFocusTimers()
    }
  }, [clearShowcaseFocusTimers, showcaseEditorOpen])

  /* ═══════════ handlers ═══════════ */

  const handleSubmit = async () => {
    const u = url.trim()
    if (!u) return
    haptic?.('medium')
    setError(null)
    setLoadingMode('product')
    setLoadingText('Загружаю товар...')
    setStep('loading')
    try {
      const d = await apiFetch('/api/parse-product', {
        method: 'POST',
        body: JSON.stringify({ url: u }),
      })
      setProduct(d)
      setActiveImg(0)
      setSelVariants({})
      setSelSize('')
      setManualPrice('')
      setResult(null)
      setSavedCalcId(null)
      setAddedToCart(false)
      addedCartUrlRef.current = null
      setSpecsOpen(false)
      setStep('product')
      haptic?.('light')
    } catch {
      setError('Не удалось загрузить товар. Проверь ссылку.')
      setStep('idle')
      haptic?.('error')
    }
  }

  const handleSearchPlatformSelect = (platform) => {
    haptic?.('light')
    if (!NAME_SEARCH_PLATFORMS.has(platform)) {
      return
    }
    setSearchError(null)
    setSearchResultOpenError(null)
    setSearchPlatform(platform)
  }

  /* ── search handler ── */
  const handleSearch = async () => {
    const q = searchQuery.trim()
    const requestedPlatform = normalizeNameSearchPlatform(searchPlatform)
    if (!q || !requestedPlatform) return
    haptic?.('medium')
    setSearchError(null)
    setSearchResultOpenError(null)
    setSearchUnavailablePlatform('')
    setSearchLoading(true)
    setLoadingMode('search')
    setLoadingText('Ищу товары...')
    setStep('loading')
    try {
      const d = await apiFetch('/api/search-products', {
        method: 'POST',
        body: JSON.stringify({ query: q, platform: requestedPlatform, count: searchCount, start_id: 0 }),
      })
      const responsePlatform = normalizeNameSearchPlatform(d.platform) || requestedPlatform
      const normalizedProducts = Array.isArray(d.products)
        ? d.products.map((item) => ({
          ...item,
          platform: normalizeNameSearchPlatform(item?.platform) || responsePlatform,
        }))
        : []
      if (!normalizedProducts.length) {
        setSearchError('empty')
        setSearchLoading(false)
        setStep('idle')
        haptic?.('error')
        return
      }
      const { nextStartId, hasMore } = resolveSearchPagination(d, responsePlatform, {
        startId: 0,
        count: searchCount,
      })
      setSearchResults(normalizedProducts)
      setSearchRate(d.rate_cny_rub)
      setActiveSearchPlatform(responsePlatform)
      setSearchNextStartId(nextStartId)
      setSearchPlatform('')
      setSearchHasMore(hasMore)
      setSearchLoading(false)
      setStep('search-results')
      haptic?.('success')
    } catch (err) {
      const unavailablePlatform = getSearchUnavailablePlatform(err)
      if (unavailablePlatform) {
        setSearchUnavailablePlatform(unavailablePlatform)
      } else {
        setSearchError('error')
      }
      setSearchLoading(false)
      setStep('idle')
      haptic?.('error')
    }
  }

  const handleLoadMore = async () => {
    const q = searchQuery.trim()
    const requestedPlatform = normalizeNameSearchPlatform(activeSearchPlatform)
    if (!q || searchLoadingMore || !requestedPlatform || !searchHasMore) return
    const currentStartId = searchNextStartId
    haptic?.('light')
    setSearchUnavailablePlatform('')
    setSearchLoadingMore(true)
    try {
      const d = await apiFetch('/api/search-products', {
        method: 'POST',
        body: JSON.stringify({
          query: q,
          platform: requestedPlatform,
          count: searchCount,
          start_id: currentStartId,
        }),
      })
      const responsePlatform = normalizeNameSearchPlatform(d.platform) || requestedPlatform
      const normalizedProducts = Array.isArray(d.products)
        ? d.products.map((item) => ({
          ...item,
          platform: normalizeNameSearchPlatform(item?.platform) || responsePlatform,
        }))
        : []
      if (normalizedProducts.length > 0) {
        const { nextStartId, hasMore } = resolveSearchPagination(d, responsePlatform, {
          startId: currentStartId,
          count: searchCount,
        })
        const merged = [...searchResults, ...normalizedProducts]
        setSearchResults(merged)
        setActiveSearchPlatform(responsePlatform)
        setSearchNextStartId(nextStartId)
        setSearchHasMore(hasMore)
        haptic?.('success')
      } else {
        setSearchHasMore(false)
      }
    } catch (err) {
      const unavailablePlatform = getSearchUnavailablePlatform(err)
      if (unavailablePlatform) {
        setSearchUnavailablePlatform(unavailablePlatform)
        setSearchHasMore(false)
      }
      haptic?.('error')
    }
    setSearchLoadingMore(false)
  }

  const handleAddToCart = async () => {
    if (!result || isInCart || cartAdding || calcLoading) return
    setCartAdding(true)
    haptic?.('medium')
    try {
      if (savedCalcId) {
        await apiFetch('/api/cart/add', {
          method: 'POST',
          body: JSON.stringify({ user_id: userId || 0, calc_id: savedCalcId }),
        })
      } else {
        const resp = await apiFetch('/api/cart/save-and-add', {
          method: 'POST',
          body: JSON.stringify({
            product: {
              ...product,
              price_cny: curPrice,
              price_is_starting: false,
              size: selectedOptionsText,
            },
            user_id: userId || 0,
          }),
        })
        setSavedCalcId(resp.calc_id)
      }
      setAddedToCart(true)
      addedCartUrlRef.current = product?.url || null
      haptic?.('success')
      onCartChange?.()
    } catch (e) {
      console.error('[AddToCart] error:', e)
      haptic?.('error')
    } finally {
      setCartAdding(false)
    }
  }

  const handleCompare = async (market) => {
    const name = product?.name || ''
    if (!name) return
    haptic?.('light')
    setCompareMarket(market)
    setCompareData(null)
    setCompareOpen(false)
    setCompareShowAll(false)
    setStep('loading')
    const mktName = market === 'wb' ? 'Wildberries' : 'Ozon'
    setCompareLoadingText(`Ищем на ${mktName}...`)
    const t1 = setTimeout(() => setCompareLoadingText('Анализируем результаты...'), 8000)
    const t2 = setTimeout(() => setCompareLoadingText('Фильтруем товары...'), 20000)
    const t3 = setTimeout(() => setCompareLoadingText('Почти готово...'), 40000)
    try {
      const data = await apiFetch('/api/compare', {
        method: 'POST',
        body: JSON.stringify({
          product_name: name,
          category: product?.category || '',
          market,
          our_price_rub: result?.total_with_margin_rub || result?.subtotal_rub || 0,
        }),
      })
      setCompareData(data)
      setCompareOpen(true)
    } catch (err) {
      setCompareData({ status: 'error', error: err.message, items: [] })
      setCompareOpen(true)
    } finally {
      clearTimeout(t1); clearTimeout(t2); clearTimeout(t3)
      setCompareLoadingText('')
      setStep('product')
    }
  }

  const handleBack = () => {
    haptic?.('light')
    addedCartUrlRef.current = null
    if ((step === 'product' || step === 'loading') && searchResults.length > 0) {
      setProduct(null)
      setResult(null)
      setError(null)
      setSavedCalcId(null)
      setAddedToCart(false)
      setStep('search-results')
    } else {
      setStep('idle')
      setProduct(null)
      setResult(null)
      setError(null)
      setSavedCalcId(null)
      setAddedToCart(false)
      setActiveSearchPlatform('')
    }
  }

  const handleSearchHome = () => {
    haptic?.('light')
    setStep('idle')
    setSearchError(null)
    setSearchResultOpenError(null)
    setSearchResults([])
    setSearchHasMore(false)
    setSearchNextStartId(0)
    setSearchPlatform('')
    setActiveSearchPlatform('')
    setSearchUnavailablePlatform('')
  }

  const handlePromoTouchStart = (event) => {
    const touch = event.touches?.[0]
    if (!touch) return
    promoTouchRef.current = {
      x: touch.clientX,
      y: touch.clientY,
      moved: false,
    }
  }

  const handlePromoTouchEnd = (event) => {
    const touch = event.changedTouches?.[0]
    if (!touch) return

    const deltaX = promoTouchRef.current.x - touch.clientX
    const deltaY = promoTouchRef.current.y - touch.clientY
    if (Math.abs(deltaX) < 36 || Math.abs(deltaX) < Math.abs(deltaY) * 1.15) {
      promoTouchRef.current.moved = false
      return
    }

    promoTouchRef.current.moved = true
    setPromoSlideIndex((currentIndex) => {
      const direction = deltaX > 0 ? 1 : -1
      return (currentIndex + direction + CALC_PROMO_BANNERS.length) % CALC_PROMO_BANNERS.length
    })
    haptic?.('light')
  }

  const handlePromoBannerClick = (event) => {
    if (!promoTouchRef.current.moved) return
    event.preventDefault()
    promoTouchRef.current.moved = false
  }

  /* ── open product detail from search result ── */
  const handleOpenProduct = async (item) => {
    if (!item || typeof item !== 'object') return

    const itemPlatform = normalizeNameSearchPlatform(item.platform) || normalizeNameSearchPlatform(activeSearchPlatform)
    haptic?.('medium')
    setSearchResultOpenError(null)

    if (itemPlatform === 'taobao' || itemPlatform === '1688') {
      const targetUrl = buildMarketplaceResultUrl(item, itemPlatform)
      const platformLabel = P_NAME[itemPlatform] || itemPlatform
      if (!targetUrl) {
        setSearchResultOpenError(`Не удалось определить ссылку на товар ${platformLabel}.`)
        haptic?.('error')
        return
      }

      setLoadingMode('product')
      setLoadingText('Загружаю товар...')
      setStep('loading')

      try {
        const detailProduct = await apiFetch('/api/parse-product', {
          method: 'POST',
          body: JSON.stringify({ url: targetUrl }),
        })

        setProduct({
          url: detailProduct.url || targetUrl,
          platform: detailProduct.platform || itemPlatform,
          name: detailProduct.name || item.title || '',
          brand: detailProduct.brand || item.brand || '',
          price_cny: detailProduct.price_cny,
          price_is_starting: Boolean(detailProduct.price_is_starting),
          size: detailProduct.size || '',
          category: detailProduct.category || item.category || '',
          weight_kg: null,
          weight_estimated: false,
          city: detailProduct.city || '',
          delivery_type: detailProduct.delivery_type || '',
          image_url: detailProduct.image_url || item.image || '',
          extra_images: detailProduct.extra_images || item.extra_images || [],
          specs: detailProduct.specs || {},
          available_sizes: detailProduct.available_sizes || [],
          variants: detailProduct.variants || [],
          variant_price_map: detailProduct.variant_price_map || {},
          original_variants: detailProduct.original_variants || [],
          notes: detailProduct.notes || '',
          auto_detected: detailProduct.auto_detected || [],
        })
        setActiveImg(0)
        setSelVariants({})
        setSelSize('')
        setManualPrice('')
        setResult(null)
        setSavedCalcId(null)
        setAddedToCart(false)
        addedCartUrlRef.current = null
        setSpecsOpen(false)
        setStep('product')
        haptic?.('success')
      } catch {
        setSearchResultOpenError(`Не удалось загрузить детали товара ${platformLabel}. Попробуйте выбрать другую карточку.`)
        setStep('search-results')
        haptic?.('error')
      }
      return
    }

    const spuId = String(item.spu_id || '').trim()
    if (!spuId) {
      haptic?.('error')
      return
    }

    const d = {
      url: `https://fast.dewu.com/page/productDetail?spuId=${spuId}&sourceName=shareDetail`,
      platform: 'poizon',
      name: item.title || '',
      brand: item.brand || '',
      price_cny: item.price_cny,
      price_is_starting: Boolean(item.price_is_starting),
      size: '',
      category: item.category || '',
      weight_kg: null,
      weight_estimated: false,
      city: '',
      delivery_type: '',
      image_url: item.image || '',
      extra_images: item.extra_images || [],
      specs: item.specs || {},
      available_sizes: item.available_sizes || [],
      variants: item.variants || [],
      variant_price_map: item.variant_price_map || {},
      original_variants: [],
      notes: '',
      auto_detected: [],
    }

    setProduct(d)
    setActiveImg(0)
    setSelVariants({})
    setSelSize('')
    setManualPrice('')
    setResult(null)
    setSavedCalcId(null)
    setAddedToCart(false)
    addedCartUrlRef.current = null
    setSpecsOpen(false)
    setStep('product')
    haptic?.('light')
  }

  /* ═══════════════════════════════════════════════════════════════ */
  /*  IDLE                                                          */
  /* ═══════════════════════════════════════════════════════════════ */
  const showcaseComposerPrimaryLabel = showcaseEditorSaving
    ? 'Сохраняю...'
    : activeShowcaseEditorSlot?.occupied
      ? 'Заменить товар'
      : 'Добавить в слот'
  const showcaseComposerDisabled = showcaseEditorLoading
    || showcaseEditorSaving
    || !showcaseEditorInputUrl
    || Boolean(showcaseEditorDuplicateSlot)
    || showcaseEditorInputUnchanged
  const activePromoBanner = CALC_PROMO_BANNERS[promoSlideIndex] || CALC_PROMO_BANNERS[0]

  if (step === 'idle') {
    return (
      <div ref={idlePageRef} className="calc-page buyer-page buyer-page--calculator">
        <div className="calc-page__ambient" aria-hidden="true">
          {active && !prefersReducedMotion ? (
            <LightRays
              className="calc-page__light-rays"
              raysOrigin="top-center"
              raysColor="#43d7e8"
              raysSpeed={0.75}
              lightSpread={1.08}
              rayLength={1.65}
              pulsating
              fadeDistance={1.12}
              saturation={0.78}
              followMouse={false}
              mouseInfluence={0}
              noiseAmount={0.035}
              distortion={0.06}
            />
          ) : null}
          <div className="calc-page__orb" />
        </div>
        <div className="calc-page__content">
          <div className="calc-page__hero">
            <div className="calc-page__icon">
              <IconCalculator size={28} />
            </div>
            <p className="calc-page__greeting">{greeting},</p>
            <h1 className="calc-page__title">{firstName}</h1>
            <p className="calc-page__sub">
              Вставьте ссылку или название товара, который хотите найти
            </p>
          </div>

          <FadeContent
            className="calc-page__fade-field"
            container={idlePageRef}
            blur
            duration={900}
            delay={80}
            threshold={0.18}
            enabled={active && !prefersReducedMotion}
          >
            <div className="calc-page__input-wrap">
            <input
              className="calc-page__input"
              type="url"
              placeholder="Вставь ссылку на товар..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              autoComplete="off"
              autoCorrect="off"
              spellCheck="false"
            />
            <button className="calc-page__submit pressable" onClick={handleSubmit} disabled={!canSubmitLink}>
              <IconSearch size={20} />
            </button>
            </div>
          </FadeContent>

          {error ? (
            <div className="calc-page__state">
              <StateSurface
                tone="error"
                compact
                eyebrow={BUYER_STATE_COPY.calculator.linkError.eyebrow}
                title={BUYER_STATE_COPY.calculator.linkError.title}
                body={BUYER_STATE_COPY.calculator.linkError.body}
                actionLabel={BUYER_STATE_COPY.calculator.linkError.actionLabel}
                onAction={handleSubmit}
                icon={getCalculatorStateIcon(BUYER_STATE_COPY.calculator.linkError.iconName)}
              />
            </div>
          ) : null}

          <div className="calc-search">
            <FadeContent
              className="calc-page__fade-field"
              container={idlePageRef}
              blur
              duration={900}
              delay={180}
              threshold={0.18}
              enabled={active && !prefersReducedMotion}
            >
              <div className="calc-page__input-wrap">
              <input
                className="calc-page__input"
                type="text"
                placeholder="Название + выберите платформу ниже"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                autoComplete="off"
                autoCorrect="off"
                spellCheck="false"
                disabled={searchLoading}
              />
              <button className="calc-page__submit pressable" onClick={handleSearch} disabled={searchLoading || !canSubmitNameSearch}>
                {searchLoading ? (
                  <div className="calc-search__btn-spinner" />
                ) : (
                  <IconSearch size={20} />
                )}
              </button>
              </div>
            </FadeContent>

            <button
              type="button"
              className={`calc-search__btn pressable${searchLoading ? ' loading' : ''}`}
              onClick={handleSearch}
              disabled={searchLoading || !canSubmitNameSearch}
            >
              {searchLoading ? (
                <div className="calc-search__btn-spinner" />
              ) : (
                <>
                  <IconSearch size={18} />
                  Найти товары
                </>
              )}
            </button>

            {searchStateCopy ? (
              <div className="calc-search__state">
                <StateSurface
                  tone={searchError === 'empty' ? 'neutral' : 'error'}
                  compact
                  eyebrow={searchStateCopy.eyebrow}
                  title={searchStateCopy.title}
                  body={searchStateCopy.body}
                  actionLabel={searchError === 'error' ? searchStateCopy.actionLabel : undefined}
                  onAction={searchError === 'error' ? handleSearch : undefined}
                  icon={getCalculatorStateIcon(searchStateCopy.iconName)}
                />
              </div>
            ) : null}
          </div>

          <div className="calc-page__platforms calc-page__platforms--hero" aria-label="Поддерживаемые платформы">
            {NAME_SEARCH_PLATFORM_OPTIONS.map(({ key, label }) => {
              const isSelected = searchPlatform === key
              return (
                <button
                  key={key}
                  type="button"
                  className={`calc-page__platform-pill${isSelected ? ' calc-page__platform-pill--selected' : ''}`}
                  data-market={key}
                  aria-pressed={isSelected}
                  onClick={() => handleSearchPlatformSelect(key)}
                >
                  <span className="calc-page__platform-pill-shimmer" aria-hidden="true" />
                  <span className="calc-page__platform-pill-label">{label}</span>
                </button>
              )
            })}
          </div>

          <CalculatorShowcase
            items={showcaseProducts}
            onSelect={handleShowcaseCardSelect}
            actions={isAdminViewer ? (
              <button
                type="button"
                className="calc-showcase__manage pressable"
                onClick={handleOpenShowcaseEditor}
              >
                Управлять
              </button>
            ) : null}
          />

          <div className={`calc-banner-carousel calc-banner-carousel--${activePromoBanner.tone}`}>
            <a
              className="calc-banner pressable"
              href={activePromoBanner.href}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Открыть баннер ${activePromoBanner.label}`}
              onTouchStart={handlePromoTouchStart}
              onTouchEnd={handlePromoTouchEnd}
              onClick={handlePromoBannerClick}
            >
              <div className="calc-banner__aura calc-banner__aura--left" />
              <div className="calc-banner__aura calc-banner__aura--right" />
              <div className="calc-banner__viewport">
                {CALC_PROMO_BANNERS.map((banner, index) => (
                  <span
                    key={banner.label}
                    className={`calc-banner__slide${index === promoSlideIndex ? ' calc-banner__slide--active' : ''}`}
                    aria-hidden={index === promoSlideIndex ? 'false' : 'true'}
                  >
                    <img className="calc-banner__image" src={banner.image} alt={banner.alt} loading="lazy" />
                  </span>
                ))}
              </div>
              <div className="calc-banner__chrome">
                <span className="calc-banner__chip">Telegram picks</span>
                <span className="calc-banner__counter">{promoSlideIndex + 1} / {CALC_PROMO_BANNERS.length}</span>
              </div>
            </a>

            <div className="calc-banner__dots" role="tablist" aria-label="Переключение баннеров">
              {CALC_PROMO_BANNERS.map((banner, index) => (
                <button
                  key={`dot-${banner.label}`}
                  type="button"
                  className={`calc-banner__dot pressable${index === promoSlideIndex ? ' calc-banner__dot--active' : ''}`}
                  aria-label={`Показать баннер ${banner.label}`}
                  aria-pressed={index === promoSlideIndex}
                  onClick={() => {
                    setPromoSlideIndex(index)
                    haptic?.('light')
                  }}
                />
              ))}
            </div>
          </div>

          <BottomSheet
            open={showcaseEditorOpen}
            onClose={handleShowcaseEditorClose}
            badge="Admin"
            title="Настройка витрины"
            className="calc-showcase-sheet"
            overlayClassName="calc-showcase-sheet__overlay"
            bodyClassName="calc-showcase-sheet__body"
          >
            <div className="calc-showcase-sheet__content" data-shell-swipe-block="true">
              {showcaseEditorError ? (
                <div className="calc-showcase-sheet__notice calc-showcase-sheet__notice--error">
                  {showcaseEditorError}
                </div>
              ) : null}

              {showcaseEditorLoading ? (
                <div className="calc-showcase-sheet__loading">Загружаю текущую витрину...</div>
              ) : (
                <div className="calc-showcase-sheet__groups">
                  {SHOWCASE_EDITOR_SECTIONS.map((section) => (
                    <section key={section.id} className="calc-showcase-sheet__group">
                      <div className="calc-showcase-sheet__group-head">
                        <p className="calc-showcase-sheet__group-title">{section.title}</p>
                        {section.note ? (
                          <p className="calc-showcase-sheet__group-note">{section.note}</p>
                        ) : null}
                      </div>

                      <div className="calc-showcase-sheet__slots">
                        {showcaseEditorSlots.slice(section.start, section.end).map((slot, index) => {
                          const slotError = showcaseEditorSlotErrors?.[slot.slot]
                          const slotIsActive = slot.slot === (activeShowcaseEditorSlot?.slot || showcaseEditorActiveSlot)
                          const slotIsDuplicate = showcaseEditorDuplicateSlot?.slot === slot.slot

                          return (
                            <motion.div
                              key={`showcase-slot-${slot.slot}`}
                              className={`calc-showcase-sheet__slot${slotIsActive ? ' calc-showcase-sheet__slot--active' : ''}${slot.occupied ? ' calc-showcase-sheet__slot--occupied' : ''}${slotIsDuplicate ? ' calc-showcase-sheet__slot--duplicate' : ''}`}
                              style={{ '--showcase-slot-accent': slot.accentColor || SHOWCASE_DEFAULT_ACCENT }}
                              initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 14 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{
                                ...(prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.quick),
                                delay: prefersReducedMotion ? 0 : Math.min((section.start + index) * 0.03, 0.18),
                              }}
                            >
                              <div className="calc-showcase-sheet__slot-shell">
                                <button
                                  type="button"
                                  className="calc-showcase-sheet__slot-main pressable"
                                  onClick={() => handleShowcaseSlotSelect(slot)}
                                  aria-pressed={slotIsActive}
                                >
                                  {slotIsDuplicate ? (
                                    <div className="calc-showcase-sheet__slot-top">
                                      <div className="calc-showcase-sheet__slot-badges">
                                        <span className="calc-showcase-sheet__slot-badge calc-showcase-sheet__slot-badge--warning">
                                          Уже здесь
                                        </span>
                                      </div>
                                    </div>
                                  ) : null}

                                  <div className="calc-showcase-sheet__slot-body">
                                    {slot.occupied ? (
                                      <ProductThumb
                                        src={slot?.product?.image_url || ''}
                                        alt={slot?.product?.name || ''}
                                        fallbackLabel={slot?.sourceLabel || 'slot'}
                                        size="md"
                                        className="calc-showcase-sheet__slot-thumb"
                                      />
                                    ) : (
                                      <div className="calc-showcase-sheet__slot-placeholder" aria-hidden="true">
                                        <IconPackage size={18} />
                                      </div>
                                    )}

                                    <div className="calc-showcase-sheet__slot-copy">
                                      <p className="calc-showcase-sheet__slot-title">
                                        {slot.occupied
                                          ? (slot?.product?.name || 'Товар без названия')
                                          : 'Свободный слот'}
                                      </p>
                                      <p className="calc-showcase-sheet__slot-price">
                                        {slot.occupied
                                          ? (slot.priceLabel || slot.sourceLabel || 'Карточка без цены')
                                          : 'Вставьте ссылку на товар'}
                                      </p>
                                    </div>
                                  </div>
                                </button>

                                {slot.occupied ? (
                                  <button
                                    type="button"
                                    className="calc-showcase-sheet__slot-link pressable"
                                    onClick={() => window.open(slot.href, '_blank', 'noopener,noreferrer')}
                                    disabled={!slot.href}
                                    aria-label={`Открыть товар из слота ${slot.slot}`}
                                  >
                                    <IconExternalLink size={17} />
                                  </button>
                                ) : null}
                              </div>

                              {slotIsActive ? (
                                <div className="calc-showcase-sheet__slot-editor">
                                  <label className="calc-showcase-sheet__field-label" htmlFor="showcase-editor-input">
                                    Ссылка для слота {slot.slot}
                                  </label>

                                  <div className={`calc-showcase-sheet__composer-input${showcaseEditorActiveSlotError ? ' calc-showcase-sheet__composer-input--error' : ''}`}>
                                    <span className="calc-showcase-sheet__composer-icon" aria-hidden="true">
                                      <IconLink size={18} />
                                    </span>
                                    <input
                                      ref={showcaseEditorInputRef}
                                      id="showcase-editor-input"
                                      className="calc-showcase-sheet__input"
                                      type="url"
                                      value={showcaseEditorInput}
                                      placeholder="https://..."
                                      autoComplete="off"
                                      autoCorrect="off"
                                      spellCheck={false}
                                      enterKeyHint="done"
                                      onFocus={(event) => scheduleShowcaseInputVisibilitySync(event.currentTarget)}
                                      onChange={(event) => handleShowcaseInputChange(event.target.value)}
                                      onKeyDown={(event) => {
                                        if (event.key === 'Enter' && !showcaseComposerDisabled) {
                                          event.preventDefault()
                                          handleShowcaseSubmit()
                                        }
                                      }}
                                    />
                                  </div>

                                  {showcaseEditorActiveSlotError ? (
                                    <div className="calc-showcase-sheet__field-error">{showcaseEditorActiveSlotError}</div>
                                  ) : showcaseEditorDuplicateSlot ? (
                                    <div className="calc-showcase-sheet__notice calc-showcase-sheet__notice--warning">
                                      Эта ссылка уже крутится на витрине в слоте {showcaseEditorDuplicateSlot.slot}. Повторный парс не нужен.
                                    </div>
                                  ) : showcaseEditorInputUnchanged ? (
                                    <div className="calc-showcase-sheet__notice calc-showcase-sheet__notice--muted">
                                      Эта ссылка уже сохранена в выбранном слоте.
                                    </div>
                                  ) : null}

                                  <div className={`calc-showcase-sheet__slot-actions${slot.occupied ? ' calc-showcase-sheet__slot-actions--split' : ' calc-showcase-sheet__slot-actions--single'}`}>
                                    <button
                                      type="button"
                                      className="calc-showcase-sheet__submit pressable"
                                      onClick={handleShowcaseSubmit}
                                      disabled={showcaseComposerDisabled}
                                    >
                                      {showcaseComposerPrimaryLabel}
                                    </button>

                                    {slot.occupied ? (
                                      <button
                                        type="button"
                                        className="calc-showcase-sheet__ghost calc-showcase-sheet__ghost--danger pressable"
                                        onClick={() => handleShowcaseSlotRemove(slot)}
                                        disabled={showcaseEditorSaving}
                                      >
                                        <IconTrash size={16} />
                                        Удалить
                                      </button>
                                    ) : null}
                                  </div>
                                </div>
                              ) : slotError ? (
                                <span className="calc-showcase-sheet__field-error">{slotError}</span>
                              ) : slot.occupied ? (
                                <div className="calc-showcase-sheet__slot-actions calc-showcase-sheet__slot-actions--single">
                                  <button
                                    type="button"
                                    className="calc-showcase-sheet__ghost calc-showcase-sheet__ghost--danger pressable"
                                    onClick={() => handleShowcaseSlotRemove(slot)}
                                    disabled={showcaseEditorSaving}
                                  >
                                    <IconTrash size={16} />
                                    Удалить
                                  </button>
                                </div>
                              ) : null}
                            </motion.div>
                          )
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              )}
            </div>
          </BottomSheet>
          {searchUnavailableSheet}
        </div>
      </div>
    )
  }

  /* ═══════════════════════════════════════════════════════════════ */
  /*  SEARCH RESULTS — simple grid with scroll                      */
  /* ═══════════════════════════════════════════════════════════════ */
  if (step === 'search-results' && searchResults.length > 0) {
    return (
      <>
        <div className="sr" data-shell-swipe-block="true">
          <div className="sr__glow" />

        {/* header */}
        <div className="sr__search-bar">
          <button className="sr__back pressable" onClick={handleSearchHome}>
            <IconArrowLeft size={18} />
          </button>
          <div className="sr__title-wrap">
            <span className="sr__title">Найдено: {searchResults.length}</span>
            {activeSearchPlatform ? (
              <span className={`sr__platform-pill sr__platform-pill--${activeSearchPlatform}`}>
                {PLATFORM_NAMES[activeSearchPlatform] || activeSearchPlatform}
              </span>
            ) : null}
          </div>
        </div>

        {searchResultOpenError ? (
          <div className="sr__state">
            <StateSurface
              tone="error"
              compact
              eyebrow="Не удалось открыть товар"
              title={searchResultOpenError}
              body="Попробуйте выбрать другую карточку или вернитесь к поиску."
              icon={<IconStateAlert size={20} />}
            />
          </div>
        ) : null}

        {/* scrollable grid */}
        <div className="sr__scroll">
          <div className="sr__grid">
            {searchResults.map((item, i) => (
              <motion.div
                key={item.spu_id || item.item_id || item.id || i}
                className="sr__card pressable"
                initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  ...(prefersReducedMotion ? BUYER_MOTION.quick : BUYER_MOTION.emphasis),
                  delay: prefersReducedMotion ? 0 : Math.min(i * 0.035, 0.25),
                }}
                whileTap={prefersReducedMotion ? undefined : { scale: BUYER_PRESS_SCALE }}
                role="button"
                tabIndex={0}
                onClick={() => handleOpenProduct(item)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    handleOpenProduct(item)
                  }
                }}
              >
                <SearchResultCardImage src={item.image} title={item.title} />
                <div className="sr__card-info">
                  <span className="sr__card-name">{item.title || 'No title'}</span>
                  <div className="sr__card-bottom">
                    <span className="sr__card-price">
                      {item.price_cny != null
                        ? (searchRate ? formatBuyerRub(item.price_cny * searchRate) : formatBuyerCny(item.price_cny))
                        : '—'}
                    </span>
                    <button
                      className="sr__card-plus pressable"
                      onClick={(e) => { e.stopPropagation(); handleOpenProduct(item) }}
                    >
                      <IconPlus size={16} />
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
          {searchHasMore && (
            <button className="sr__load-more pressable" onClick={handleLoadMore} disabled={searchLoadingMore}>
              {searchLoadingMore ? (
                <div className="sr__load-more-spinner" />
              ) : (
                <>
                  Загрузить ещё
                  <IconChevronDown size={16} />
                </>
              )}
            </button>
          )}
        </div>
        </div>
        {searchUnavailableSheet}
      </>
    )
  }

  /* ═══════════════════════════════════════════════════════════════ */
  /*  LOADING                                                       */
  /* ═══════════════════════════════════════════════════════════════ */
  if (step === 'loading') {
    const isCompareLoading = !!compareLoadingText
    return (
      <div className="calc-page buyer-page buyer-page--calculator">
        <div className="calc-loader">
          <LoadingGlyph className="calc-loader__indicator" size="lg" />
          <p className="calc-loader__text">{isCompareLoading ? compareLoadingText : loadingText}</p>
          <button className="calc-loader__cancel pressable" onClick={() => {
            if (isCompareLoading) {
              setCompareLoadingText('')
              setStep('product')
            } else {
              handleBack()
            }
          }}>
            Отменить
          </button>
        </div>
      </div>
    )
  }

  /* ═══════════════════════════════════════════════════════════════ */
  /*  PRODUCT  (unified — card + live calc + actions)               */
  /* ═══════════════════════════════════════════════════════════════ */
  if (step === 'product' && product) {
    const pColor = P_COLOR[product.platform] || '#555'
    const pName = P_NAME[product.platform] || product.platform
    const hasVariants = (product.variants || []).some((g) => (g.options || []).length >= 2)
    const SIZE_NAMES = ['size', 'размер', 'sz', 'taille', '尺码', '尺寸']
    const variantHasSizes = (product.variants || []).some(
      (g) => (g.options || []).length >= 2 && SIZE_NAMES.includes(g.name.toLowerCase())
    )
    const hasSizes = !variantHasSizes && (product.available_sizes || []).length >= 2
    const variantGroups = (product.variants || []).filter((g) => (g.options || []).length >= 2)
    const allVariantsSelected = variantGroups.every((g) => selVariants[g.name])
    const sizeSelected = !hasSizes || !!selSize
    const allOptionsSelected = allVariantsSelected && sizeSelected
    const hasSpecs = product.specs && Object.keys(product.specs).length > 0
    const poizonVariantsUnavailable =
      product.platform === 'poizon' &&
      (product.url || '').includes('skuId=') &&
      !!product.size &&
      !hasVariants &&
      !hasSizes &&
      Object.keys(product.variant_price_map || {}).length === 0
    const canAddToCart = !poizonVariantsUnavailable && !isInCart && !cartAdding && !calcLoading && !!result && allOptionsSelected
    const waitingForExactPriceSelection = Boolean(product.price_is_starting && !allOptionsSelected)
    const hasExactPriceFromData = priceState.source === 'base' || priceState.source === 'variant'
    const shouldShowManualPriceInput = Boolean(
      !hasExactPriceFromData && (
        product.price_cny == null || (product.price_is_starting && allOptionsSelected)
      )
    )
    const missingManualPrice = shouldShowManualPriceInput && !curPrice
    const shouldHideSummaryTotal = shouldShowManualPriceInput && displayPriceCny == null && curPriceRub == null && !result
    const summaryTotal = typeof result?.subtotal_rub === 'number'
      ? formatBuyerRub(result.subtotal_rub)
      : hasStartingPrice && displayPriceCny != null
        ? `от ${formatBuyerCny(displayPriceCny)}`
        : curPriceRub != null
          ? formatBuyerRub(curPriceRub)
          : shouldHideSummaryTotal
            ? null
            : 'Уточните цену'
    const supportPriceLabel = displayPriceCny != null
      ? hasStartingPrice
        ? `от ${formatBuyerCny(displayPriceCny)}`
        : formatBuyerCny(displayPriceCny)
      : null
    const supportPriceFallback = shouldShowManualPriceInput && displayPriceCny == null
      ? 'Цена появится после ввода вручную'
      : 'Цена появится после выбора варианта'
    const needsExactPrice = Boolean(hasStartingPrice && !curPrice)
    const compareMarketName = compareMarket === 'wb' ? 'Wildberries' : compareMarket === 'ozon' ? 'Ozon' : ''
    const compareAlternateName = compareMarket === 'wb' ? 'Ozon' : 'Wildberries'
    const compareSheetClassName = compareMarket ? `cmp-sheet cmp-sheet--${compareMarket}` : 'cmp-sheet'
    const breakdownRows = (result?.breakdown || []).map((row, index) => ({
      id: `${row.label}-${index}`,
      label: row.label,
      note: row.note,
      amount: formatBuyerRub(row.amount_rub),
    }))
    const specRows = Object.entries(product.specs || {}).map(([key, value]) => ({
      key,
      value,
    }))
    const ctaNote = poizonVariantsUnavailable
      ? 'Этот вариант сейчас нельзя добавить в корзину.'
      : waitingForExactPriceSelection
        ? 'Выберите все доступные варианты, затем укажите точную цену в юанях для расчёта.'
        : !allOptionsSelected && missingManualPrice
          ? 'Выберите все доступные варианты и укажите цену в юанях, чтобы добавить товар в корзину.'
          : missingManualPrice
          ? 'Укажите точную цену в юанях, чтобы получить расчёт и добавить товар в корзину.'
          : !allOptionsSelected
            ? 'Выберите все доступные варианты, чтобы добавить товар в корзину.'
            : ''

    return (
      <div className="calc-page calc-page--filled buyer-page buyer-page--calculator">
        <button className="calc-back pressable" onClick={handleBack}>
          <IconArrowLeft size={20} />
        </button>

        <div className="calc-scroll">
          {/* ── gallery ── */}
          {images.length > 0 ? (
            <div className="cg">
              <div className="cg__main"
                data-shell-swipe-block="true"
                onTouchStart={onGalleryTouchStart}
                onTouchEnd={onGalleryTouchEnd}>
                <img src={images[activeImg] || images[0]} alt="" className="cg__img"
                  referrerPolicy="no-referrer"
                  onError={(e) => { e.target.style.display = 'none' }}
                  draggable={false} />
              </div>
              {images.length > 1 && (
                <div className="cg__thumbs">
                  {images.slice(0, 6).map((src, i) => (
                    <button key={i}
                      className={`cg__thumb pressable${i === activeImg ? ' active' : ''}`}
                      onClick={() => { setActiveImg(i); haptic?.('light') }}>
                      <img src={src} alt="" referrerPolicy="no-referrer" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="cg__empty">
              <span style={{ opacity: 0.25 }}><IconPackage size={48} /></span>
            </div>
          )}

          <section className="calc-result__summary ui-surface-panel">
            <div className="calc-result__summary-head">
              <div className="calc-result__summary-meta">
                <span className="cp-info__platform" style={{ color: pColor, borderColor: pColor + '40' }}>{pName}</span>
                {product.brand && <span className="cp-info__brand">{product.brand}</span>}
              </div>

              <h2 className="cp-info__name">{product.name || 'Товар без названия'}</h2>

              {summaryTotal ? (
                <div className="calc-result__total" style={calcLoading ? { opacity: 0.45 } : undefined}>
                  {summaryTotal}
                </div>
              ) : null}

              <p className="calc-result__support">
                {supportPriceLabel || supportPriceFallback}
                {needsExactPrice && <span> · нужна точная цена для расчёта</span>}
                {rate && <span> · {rate.cny_rub.toFixed(2)} ₽/¥</span>}
              </p>
            </div>

            {shouldShowManualPriceInput && (
              <div className="cp-manual">
                <label className="cp-manual__label">
                  {product.price_is_starting ? 'Укажите точную цену в юанях (¥)' : 'Введите цену в юанях (¥)'}
                </label>
                <input className="cp-manual__input" type="number" inputMode="decimal"
                  placeholder={product.price_is_starting ? 'например 1500 для выбранного варианта' : 'например 1500'}
                  value={manualPrice}
                  onChange={(e) => setManualPrice(e.target.value)} />
              </div>
            )}

            {poizonVariantsUnavailable && (
              <div className="cp-availability-note card">
                <div className="cp-availability-note__title">
                  <IconStateAlert size={16} />
                  <span>Доступных вариантов именно на Poizon сейчас нет</span>
                </div>
                <p className="cp-availability-note__text">
                  {`Poizon вернул только выбранный вариант: ${product.size}. Другие размеры и уточнения сейчас недоступны, поэтому добавить товар в корзину нельзя.`}
                </p>
              </div>
            )}
          </section>

          {/* ── variants ── */}
          {hasVariants && (
            <div className="cp-variants">
              {(product.variants || []).map((group, gi) => {
                const opts = group.options || []
                if (opts.length < 2) return null
                return (
                  <div key={group.name} className="cv-group">
                    <div className="cv-group__label">{group.name}</div>
                    <div className="cv-group__list">
                      {opts.map((raw) => {
                        const name = typeof raw === 'string' ? raw : raw.name || String(raw)
                        const active = selVariants[group.name] === name
                        const avail = isOptionAvailable(group.name, name, gi)
                        const mp = avail ? getOptionPrice(group.name, name, gi) : null
                        return (
                          <button key={name}
                            className={`cv-chip pressable${active ? ' active' : ''}${!avail ? ' disabled' : ''}${mp != null ? ' has-price' : ''}`}
                            disabled={!avail}
                            onClick={() => {
                              if (!avail) return
                              haptic?.('light')
                              setAddedToCart(false)
                              addedCartUrlRef.current = null
                              setSavedCalcId(null)
                              setSelVariants((p) => {
                                if (p[group.name] === name) {
                                  const next = { ...p }
                                  delete next[group.name]
                                  return next
                                }

                                return { ...p, [group.name]: name }
                              })
                            }}>
                            <span className="cv-chip__name">{name}</span>
                            {avail && mp != null ? (
                              <span className="cv-chip__price">{formatBuyerRub(mp * (rate?.cny_rub || 1))}</span>
                            ) : !avail ? (
                              <span className="cv-chip__price cv-chip__price--na">—</span>
                            ) : null}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* ── sizes ── */}
          {hasSizes && (
            <div className="cp-variants">
              <div className="cv-group">
                <div className="cv-group__label">Размер</div>
                <div className="cv-group__list cv-group__list--sizes">
                  {(product.available_sizes || []).map((raw) => {
                    const name = typeof raw === 'string' ? raw : raw.name || String(raw)
                    return (
                      <button key={name}
                        className={`cv-size pressable${selSize === name ? ' active' : ''}`}
                        onClick={() => { haptic?.('light'); setAddedToCart(false); addedCartUrlRef.current = null; setSavedCalcId(null); setSelSize((p) => (p === name ? '' : name)) }}>
                        {name}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {result && addedToCart ? (
            <div ref={addToCartSuccessRef} className="calc-result__section calc-result__state-banner">
              <StateSurface
                tone="complete"
                compact
                eyebrow={addToCartSuccessState.eyebrow}
                title={addToCartSuccessState.title}
                body={addToCartSuccessState.body}
                icon={<AddToCartSuccessIcon />}
              />
            </div>
          ) : null}

          {result && (
            <div className="calc-result__section">
              <PriceBreakdown
                title="Состав цены"
                rows={breakdownRows}
                totalLabel="Итоговая цена"
                totalAmount={formatBuyerRub(result.subtotal_rub)}
              />
            </div>
          )}

          <div className="calc-result__section">
            <section className="calc-result__compare ui-surface-panel">
              <div className="calc-result__compare-copy">
                <p className="section-label">Сравнение</p>
                <p className="calc-result__support">
                  Сравните итоговую цену с предложениями на Wildberries и Ozon, не выходя из калькулятора.
                </p>
              </div>

              <div className="calc-result__compare-actions">
                <button
                  type="button"
                  className="calc-result__compare-btn"
                  data-market="wb"
                  onClick={() => handleCompare('wb')}
                >
                  <span className="calc-result__compare-btn-shimmer" aria-hidden="true" />
                  <span className="calc-result__compare-btn-label">Wildberries</span>
                </button>
                <button
                  type="button"
                  className="calc-result__compare-btn"
                  data-market="ozon"
                  onClick={() => handleCompare('ozon')}
                >
                  <span className="calc-result__compare-btn-shimmer" aria-hidden="true" />
                  <span className="calc-result__compare-btn-label">Ozon</span>
                </button>
              </div>
            </section>
          </div>

          {result && (
            <div className="calc-result__section">
              <section className="calc-result__meta ui-surface-panel">
                <p className="section-label">Доставка и курс</p>

                {result.exchange_rate && (
                  <div className="calc-result__meta-row">
                    <div className="calc-result__meta-copy">
                      <span>Курс</span>
                      {result.exchange_rate.age_human && (
                        <span className="calc-result__support">{result.exchange_rate.age_human}</span>
                      )}
                    </div>
                    <span className="calc-result__meta-value">{result.exchange_rate.cny_rub?.toFixed(2)} ₽/¥</span>
                  </div>
                )}

                {adminSettings?.delivery_time && (
                  <div className="calc-result__meta-row">
                    <span>Срок доставки</span>
                    <span className="calc-result__meta-value">{adminSettings.delivery_time}</span>
                  </div>
                )}

                {adminSettings?.next_shipment_date && adminSettings.next_shipment_date !== '00.00.0000' && (
                  <div className="calc-result__meta-row">
                    <span>Ближайшая отправка</span>
                    <span className="calc-result__meta-value">{adminSettings.next_shipment_date}</span>
                  </div>
                )}
              </section>
            </div>
          )}

          {hasSpecs && (
            <div className="calc-result__section">
              <SpecsAccordion
                title="О товаре"
                open={specsOpen}
                onToggle={() => { setSpecsOpen((p) => !p); haptic?.('light') }}
                rows={specRows}
                icon={<IconInfo size={16} />}
              />
            </div>
          )}

          <div className="calc-spacer" />
        </div>

        <div className="calc-result__cta">
          {ctaNote && <p className="calc-result__cta-note">{ctaNote}</p>}

          <button
            className={`calc-result__cta-button pressable${isInCart ? ' done' : ''}${cartAdding ? ' loading' : ''}`}
            onClick={handleAddToCart}
            disabled={!canAddToCart}
          >
            {cartAdding ? (
              <><span className="cp-actions__spinner" /> Добавляем</>
            ) : isInCart ? (
              <><IconCheck /> В корзине</>
            ) : poizonVariantsUnavailable ? (
              <><IconPlus /> Недоступно</>
            ) : (
              <><IconPlus /> В корзину</>
            )}
          </button>
        </div>

        <BottomSheet
          open={compareOpen}
          onClose={() => setCompareOpen(false)}
          className={compareSheetClassName}
          badge={compareMarketName}
          title={compareData?.query || product.name || ''}
          bodyClassName="cmp-sheet__body"
        >
          <div className="cmp-sheet__content" data-shell-swipe-block="true">
            {compareData?.status === 'antibot' && (
              <StateSurface
                title="Маркетплейс временно недоступен"
                body={`${compareMarketName} сейчас не отдал стабильный ответ. Попробуйте позже или переключитесь на ${compareAlternateName}.`}
                tone="error"
                actionLabel="Попробовать снова"
                onAction={() => handleCompare(compareMarket)}
              />
            )}

            {compareData?.status === 'error' && (
              <StateSurface
                title="Ошибка сравнения"
                body={compareData.error
                  ? `Не удалось получить сравнение для ${compareMarketName}: ${compareData.error}. Попробуйте ещё раз или переключитесь на ${compareAlternateName}.`
                  : `Не удалось получить сравнение для ${compareMarketName}. Попробуйте ещё раз или переключитесь на ${compareAlternateName}.`}
                tone="error"
                actionLabel="Попробовать снова"
                onAction={() => handleCompare(compareMarket)}
              />
            )}

            {compareData?.status === 'empty' && (
              <StateSurface
                title="Похожих товаров не нашли"
                body={`На ${compareMarketName} сейчас не нашлось похожих предложений. Попробуйте позже или сравните с ${compareAlternateName}.`}
              />
            )}

            {compareData?.status === 'ok' && compareData.items?.length > 0 && (() => {
              const displayItems = compareShowAll && compareData.raw_items?.length > 0
                ? compareData.raw_items
                : compareData.items
              const avgPrice = compareShowAll && compareData.raw_items?.length > 0
                ? Math.round(compareData.raw_items.reduce((sum, item) => sum + item.price_rub, 0) / compareData.raw_items.length)
                : compareData.avg_price
              const ourPrice = compareData.our_price_rub || 0
              const cheaperHere = avgPrice > ourPrice

              return (
                <>
                  <div className="cmp-items">
                    {displayItems.map((item, index) => (
                      <a
                        key={index}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="cmp-card"
                        onClick={() => haptic?.('light')}
                      >
                        <div className="cmp-card__rank">{index + 1}</div>
                        {item.image_url && (
                          <div className="cmp-card__img-wrap">
                            <img src={proxyImageUrl(item.image_url)} alt="" className="cmp-card__img" loading="lazy" referrerPolicy="no-referrer" />
                          </div>
                        )}
                        <div className="cmp-card__info">
                          <p className="cmp-card__name">{item.name}</p>
                          <div className="cmp-card__meta">
                            <span className="cmp-card__price">{formatBuyerRub(item.price_rub)}</span>
                            {item.rating > 0 && (
                              <span className="cmp-card__rating">★ {item.rating.toFixed(1)}</span>
                            )}
                            {item.reviews > 0 && (
                              <span className="cmp-card__reviews">
                                {formatBuyerNumber(item.reviews)} отз.
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="cmp-card__arrow">
                          <IconExternalLink size={16} />
                        </div>
                      </a>
                    ))}
                  </div>

                  {compareData.raw_items?.length > 0 && (
                    <div className="cmp-show-all-wrap">
                      <button
                        className="cmp-show-all-btn pressable"
                        onClick={() => {
                          setCompareShowAll(!compareShowAll)
                          haptic?.('light')
                        }}
                      >
                        <span className={`cmp-show-all-btn__icon${compareShowAll ? ' open' : ''}`}>
                          <IconChevronDown size={16} />
                        </span>
                        {compareShowAll
                          ? `Свернуть до ${compareData.items.length}`
                          : `Показать все товары (${compareData.raw_items.length})`
                        }
                      </button>
                    </div>
                  )}

                  <div className="cmp-summary">
                    <div className="cmp-summary__row">
                      <span className="cmp-summary__label">
                        Средняя на {compareMarket === 'wb' ? 'WB' : 'Ozon'}
                        {compareShowAll && <span className="cmp-summary__label-note"> (все {displayItems.length})</span>}
                      </span>
                      <span className="cmp-summary__value">
                        {formatBuyerRub(avgPrice)}
                      </span>
                    </div>
                    <div className="cmp-summary__divider" />
                    <div className="cmp-summary__row cmp-summary__row--our">
                      <span className="cmp-summary__label">Ваша цена у нас</span>
                      <span className="cmp-summary__value cmp-summary__value--accent">
                        {formatBuyerRub(ourPrice)}
                      </span>
                    </div>
                    <div className={`cmp-verdict ${cheaperHere ? 'cmp-verdict--win' : 'cmp-verdict--lose'}`}>
                      {cheaperHere ? (
                        <>
                          <span className="cmp-verdict__title">Выгоднее у нас</span>
                          <span className="cmp-verdict__body">
                            Средняя цена на маркетплейсе выше. Можно закрывать сравнение, добавлять товар в корзину и оформлять всё прямо здесь.
                          </span>
                        </>
                      ) : (
                        <>
                          <span className="cmp-verdict__title cmp-verdict__title--alert">Осторожно!</span>
                          <span className="cmp-verdict__body">
                            Будьте внимательнее, скорее всего товар на маркетплейсе - это некачественная подделка
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </>
              )
            })()}
          </div>
        </BottomSheet>
      </div>
    )
  }

  return null
})

export default Calculator
