import { useState, useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { bootstrapWithInitData, updateAdminShowcase } from '../../api/admin.js'
import BottomSheet from '../../components/ui/BottomSheet'
import FadeContent from '../../components/ui/FadeContent'
import LightRays from '../../components/ui/LightRays'
import LoadingGlyph from '../../components/ui/LoadingGlyph'
import AboutDetailsSheet from '../../components/ui/AboutDetailsSheet'
import OrderGuideSheet from '../../components/ui/OrderGuideSheet'
import PromoBannerOverlay from '../../components/ui/PromoBannerOverlay'
import PoizonManualChoiceHint from '../../components/ui/PoizonManualChoiceHint'
import PoizonManualVariantButton from '../../components/ui/PoizonManualVariantButton'
import ProductThumb from '../../components/ui/ProductThumb'
import TextType from '../../components/ui/TextType'
import BrandGemIcon from '../../components/ui/BrandGemIcon'
import CalculatorShowcase from './CalculatorShowcase'
import { resolveProductPriceState } from './priceState.js'
import { resolveSearchPagination } from './searchPagination.js'
import {
  IconArrowLeft,
  IconChevronDown,
  IconCheck,
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
  formatBuyerRub,
} from '../../constants/buyerNumbers'
import { BUYER_MOTION, BUYER_PRESS_SCALE } from '../../constants/buyerMotion'
import { BUYER_STATE_COPY } from '../../constants/buyerStateContent'
import { useTelegram } from '../../hooks/useTelegram'
import { getImageSourceCandidates, proxyImageUrl } from '../../utils/media'
import {
  FALLBACK_PROMO_BANNERS,
  normalizePromoBanner,
} from '../../utils/promoBanners'
import { getDeliverySettings } from '../../utils/deliveryPricing'
import {
  POIZON_MANUAL_OTHER_PLATFORM_PRICE_HELPER_TEXT,
  derivePersistedVariantSelection,
  POIZON_MANUAL_PRICE_HELPER_TEXT,
  POIZON_MANUAL_VARIANT_SELECTIONS,
  shouldAllowFallbackVariantSelection,
  shouldRequireManualPriceForSelection,
} from '../../utils/productVariants'
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

const POIZON_PLATFORM = 'poizon'
const ORDER_GUIDE_AUTO_SELECT_SIZE_ALIASES = ['42', '10']
const SIZE_GROUP_NAMES = ['size', 'размер', 'sz', 'taille', '尺码', '尺寸']
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
  return normalized === POIZON_PLATFORM ? POIZON_PLATFORM : ''
}

function matchesOrderGuidePreferredSize(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) return false
  if (ORDER_GUIDE_AUTO_SELECT_SIZE_ALIASES.includes(normalized)) return true

  const numericTokens = normalized.match(/\d+(?:[.,]\d+)?/g) || []
  return numericTokens.some((token) => ORDER_GUIDE_AUTO_SELECT_SIZE_ALIASES.includes(token.replace(',', '.')))
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

const CALC_PROMO_BANNERS = FALLBACK_PROMO_BANNERS.map((banner) => normalizePromoBanner(banner))

const CALC_SEARCH_HINTS = ['【得物】得物er-X6J3M5V7发现一件好物...', 'Айфон 17 Pro...']
const ORDER_GUIDE_LIVE_PREVIEW_SNAPSHOT = {
  url: 'https://fast.dewu.com/router/product/ProductDetail?spuId=5631050&sourceName=shareDetail&outside_channel_type=0&share_platform_title=7&fromUserId=6441838e0d5af38cdf0c6da76686698d&skuId=628427964&propertyValueId=276554271&gSource=product&gContentId=5631050&gContentFlag=38&gType=1',
  product_url: 'https://fast.dewu.com/router/product/ProductDetail?spuId=5631050&sourceName=shareDetail&outside_channel_type=0&share_platform_title=7&fromUserId=6441838e0d5af38cdf0c6da76686698d&skuId=628427964&propertyValueId=276554271&gSource=product&gContentId=5631050&gContentFlag=38&gType=1',
  platform: 'poizon',
  name: 'Nike Sb Janoski+ Lilac Medium Soft Pink',
  brand: 'Nike',
  price_cny: 205,
  price_is_starting: false,
  size: 'Purple / 38',
  category: 'sneakers',
  weight_kg: 1,
  weight_estimated: true,
  city: 'moscow',
  delivery_type: 'standard',
  image_url: 'https://cdn.poizon.com/pro-img/origin-img/20251205/702385d2d6294e90bcc78d1e2b0b5295.jpg',
  extra_images: [
    'https://cdn.poizon.com/pro-img/origin-img/20251205/280fe31acd52458c9355151416f11496.jpg',
    'https://cdn.poizon.com/pro-img/origin-img/20251205/cbfbacad057c49debbe344505e397b89.jpg',
    'https://cdn.poizon.com/pro-img/origin-img/20251205/803005a7e7bc43be8648326a3763388e.jpg',
    'https://cdn.poizon.com/pro-img/origin-img/20251205/a3562fdaba394dde9e2c83325a3f2072.jpg',
  ],
  specs: {
    Brand: 'Nike',
    Series: 'DV5475-500',
    Material: 'Замша',
    Fit: 'All',
    Season: 'весна, лето, осень, зима',
    Category: 'Skateboard Shoes',
    'Category L2': 'Trendy Sneakers & Casual Shoes',
    'Category L1': 'Shoes',
    'Release Date': '2023-08-14',
    Barcode: '196606764153',
    Sales: '66',
  },
  available_sizes: ['36', '36.5', '37.5', '38', '38.5', '39', '40', '40.5', '41', '42', '42.5', '43', '44', '44.5', '45', '45.5', '46'],
  variants: [
    {
      name: 'Size',
      options: ['36', '36.5', '37.5', '38', '38.5', '39', '40', '40.5', '41', '42', '42.5', '43', '44', '44.5', '45', '45.5', '46'],
    },
  ],
  variant_price_map: {
    '[["Size", "36"]]': 327,
    '[["Size", "36.5"]]': 317,
    '[["Size", "37.5"]]': 327,
    '[["Size", "38"]]': 205,
    '[["Size", "38.5"]]': 259,
    '[["Size", "39"]]': 327,
    '[["Size", "40"]]': 497,
    '[["Size", "40.5"]]': 697,
    '[["Size", "41"]]': 328,
    '[["Size", "42"]]': 323,
    '[["Size", "42.5"]]': 327,
    '[["Size", "43"]]': 388,
    '[["Size", "44"]]': 367,
    '[["Size", "44.5"]]': 518,
    '[["Size", "45"]]': 597,
    '[["Size", "45.5"]]': 577,
    '[["Size", "46"]]': 597,
  },
  original_variants: [],
  notes: '',
  subtotal_rub: 3596.8605,
  total_with_margin_rub: 3596.8605,
  breakdown: [
    { label: 'Товар', amount_rub: 2346.8605, note: '205 ¥ × 11.45' },
    { label: 'Комиссия (10%)', amount_rub: 250, note: 'мин. 250 ₽' },
    { label: 'Доставка до Москвы', amount_rub: 1000, note: 'Обычная до Москвы • ~2 × 500 г' },
  ],
  exchange_rate: {
    cny_rub: 11.4481,
    usd_rub: 78.7277,
    eur_rub: 91.0034,
    updated_at: '2026-04-07T18:21:59.554086',
    age_seconds: 919.373111,
    age_human: '15 мин. назад',
    source: 'cbr',
  },
  delivery_info: {
    standard_days: '3-4 недели',
    express_days: '5-10 дней',
    cdek_days: '2-5 дней',
    includes_note: 'В стоимость доставки входят облицовка и страховка.',
    payment_note: 'Доставка оплачивается при получении.',
  },
}

/* ════════════════════════════════════════════════════════════════ */
const ORDER_GUIDE_STEP_SIX_PREVIEW_SETTING_KEY = 'order_guide_step_six_preview'
const ORDER_GUIDE_STEP_EIGHT_PREVIEW_SETTING_KEY = 'order_guide_step_eight_preview'
const ORDER_GUIDE_CART_PREVIEW_SELECTED_ITEM_ID = 'order-guide-step-six-item-3'
const ORDER_GUIDE_ORDERS_PREVIEW_ITEM_ID = 'order-guide-step-eight-item-1'

function buildOrderGuideCartPreviewItem({
  id,
  shortName,
  name,
  size,
  priceRub,
  imageUrl,
}) {
  return {
    id,
    short_name: shortName,
    name,
    size,
    subtotal_rub: priceRub,
    total_with_margin_rub: priceRub,
    calc_json: JSON.stringify({
      image_url: imageUrl,
      product: {
        name,
        image_url: imageUrl,
      },
    }),
    in_order: 0,
    order_submitted: 0,
    paid: 0,
    shipped: 0,
    arrived: 0,
  }
}

const ORDER_GUIDE_CART_PREVIEW = {
  items: [
    buildOrderGuideCartPreviewItem({
      id: 'order-guide-step-six-item-1',
      shortName: 'ALORGEEK T-Shirt',
      name: 'ALORGEEK T Shirts Unisex Crew Neck Moderate Straight Fit',
      size: 'Apricot / L',
      priceRub: 1196.4759,
      imageUrl: 'https://cdn.poizon.com/pro-img/origin-img/20250312/e1ed99bb50e44546916e90394b66e913.jpg',
    }),
    buildOrderGuideCartPreviewItem({
      id: 'order-guide-step-six-item-2',
      shortName: 'DIOR Perfume Set',
      name: 'DIOR Men\'s Perfume Sample, Woody Fougere 10ml Birthday Gift For Girlfriend',
      size: '10ml*8 / Shopping Bag Not Included',
      priceRub: 8055.745999999999,
      imageUrl: 'https://cdn.poizon.com/pro-img/origin-img/20250312/b74f5bd0fa294700bfaefcc7e3c2c6d4.jpg',
    }),
    buildOrderGuideCartPreviewItem({
      id: ORDER_GUIDE_CART_PREVIEW_SELECTED_ITEM_ID,
      shortName: 'Nike Sb Janoski+',
      name: 'Nike Sb Janoski+ Lilac Medium Soft Pink',
      size: '42',
      priceRub: 5067.50993,
      imageUrl: 'https://cdn.poizon.com/pro-img/origin-img/20251205/702385d2d6294e90bcc78d1e2b0b5295.jpg',
    }),
    buildOrderGuideCartPreviewItem({
      id: 'order-guide-step-six-item-4',
      shortName: 'Alexander McQueen',
      name: 'Alexander McQueen Oversized Lace Up Sneakers Women\'s',
      size: '36 / Original Shoe Box Not Included',
      priceRub: 50970.288905,
      imageUrl: 'https://cdn.poizon.com/pro-img/origin-img/20251217/e1b8757a474f4b499ca3f064e8921af1.jpg',
    }),
    buildOrderGuideCartPreviewItem({
      id: 'order-guide-step-six-item-5',
      shortName: 'Nike Dunk Low Cacao',
      name: 'Nike Dunk Low Cacao Wow Women\'s',
      size: '43',
      priceRub: 10072.16,
      imageUrl: 'https://cdn.poizon.com/pro-img/origin-img/20251206/6c8447a89bc24797a6429732cc71ab5d.jpg',
    }),
  ],
  selectedIds: [ORDER_GUIDE_CART_PREVIEW_SELECTED_ITEM_ID],
  footerActionText: '\u0412 \u0437\u0430\u044f\u0432\u043a\u0443',
}

function normalizeOrderGuideCartPreviewItem(item, index) {
  if (!item || typeof item !== 'object') {
    return null
  }

  const fallbackItem = ORDER_GUIDE_CART_PREVIEW.items[index] || ORDER_GUIDE_CART_PREVIEW.items[0]
  const id = typeof item.id === 'string' || typeof item.id === 'number'
    ? item.id
    : (fallbackItem?.id || `order-guide-step-six-item-${index + 1}`)
  const subtotalRub = Number(item.subtotal_rub)
  const totalWithMarginRub = Number(item.total_with_margin_rub)
  const calcJson = typeof item.calc_json === 'string'
    ? item.calc_json
    : item.calc_json && typeof item.calc_json === 'object'
      ? JSON.stringify(item.calc_json)
      : (fallbackItem?.calc_json || '')

  return {
    id,
    short_name: typeof item.short_name === 'string' && item.short_name.trim()
      ? item.short_name
      : (fallbackItem?.short_name || ''),
    name: typeof item.name === 'string' && item.name.trim()
      ? item.name
      : (fallbackItem?.name || ''),
    size: typeof item.size === 'string' ? item.size : (fallbackItem?.size || ''),
    subtotal_rub: Number.isFinite(subtotalRub)
      ? subtotalRub
      : (Number.isFinite(totalWithMarginRub) ? totalWithMarginRub : (fallbackItem?.subtotal_rub || 0)),
    total_with_margin_rub: Number.isFinite(totalWithMarginRub)
      ? totalWithMarginRub
      : (Number.isFinite(subtotalRub) ? subtotalRub : (fallbackItem?.total_with_margin_rub || 0)),
    calc_json: calcJson,
    in_order: item.in_order ? 1 : 0,
    order_submitted: item.order_submitted ? 1 : 0,
    paid: item.paid ? 1 : 0,
    shipped: item.shipped ? 1 : 0,
    arrived: item.arrived ? 1 : 0,
  }
}

function normalizeOrderGuideCartPreview(preview) {
  if (!preview || typeof preview !== 'object') {
    return ORDER_GUIDE_CART_PREVIEW
  }

  const items = Array.isArray(preview.items)
    ? preview.items
      .map((item, index) => normalizeOrderGuideCartPreviewItem(item, index))
      .filter(Boolean)
    : []

  if (!items.length) {
    return ORDER_GUIDE_CART_PREVIEW
  }

  const selectedIds = Array.isArray(preview.selectedIds)
    ? preview.selectedIds.filter((candidateId) => items.some((item) => item.id === candidateId))
    : []
  const fallbackSelectedId = items[2]?.id ?? items[items.length - 1]?.id ?? null

  return {
    items,
    selectedIds: selectedIds.length
      ? selectedIds
      : (fallbackSelectedId != null ? [fallbackSelectedId] : []),
    footerActionText: typeof preview.footerActionText === 'string' && preview.footerActionText.trim()
      ? preview.footerActionText
      : ORDER_GUIDE_CART_PREVIEW.footerActionText,
    ...(typeof preview.footerLabel === 'string' && preview.footerLabel.trim()
      ? { footerLabel: preview.footerLabel }
      : {}),
  }
}

function parseOrderGuideCartPreviewSetting(rawValue) {
  if (typeof rawValue !== 'string' || !rawValue.trim()) {
    return ORDER_GUIDE_CART_PREVIEW
  }

  try {
    return normalizeOrderGuideCartPreview(JSON.parse(rawValue))
  } catch {
    return ORDER_GUIDE_CART_PREVIEW
  }
}

function buildOrderGuideOrdersPreviewItem({
  id,
  shortName,
  name,
  size,
  priceCny,
  weightKg,
  weightEstimated,
  subtotalRub,
  imageUrl,
}) {
  return {
    id,
    short_name: shortName,
    name,
    size,
    price_cny: priceCny,
    weight_kg: weightKg,
    weight_estimated: weightEstimated,
    subtotal_rub: subtotalRub,
    total_with_margin_rub: subtotalRub,
    calc_json: JSON.stringify({
      image_url: imageUrl,
      product: {
        name,
        price_cny: priceCny,
        weight_kg: weightKg,
        weight_estimated: weightEstimated,
        image_url: imageUrl,
      },
    }),
    in_order: 1,
    order_submitted: 0,
    paid: 0,
    shipped: 0,
    arrived: 0,
  }
}

const ORDER_GUIDE_ORDERS_PREVIEW_PRICING_SETTINGS = {
  commission_pct: '10.0',
  min_commission_rub: '250.0',
  delivery_air_moscow_rub_500g: '1500.0',
  delivery_standard_moscow_rub_500g: '500.0',
  delivery_cdek_russia_rub_500g: '500.0',
  delivery_air_moscow_days: '5-10 дней',
  delivery_standard_moscow_days: '3-4 недели',
  delivery_cdek_russia_days: '2-5 дней',
}

const ORDER_GUIDE_ORDERS_PREVIEW = {
  items: [
    buildOrderGuideOrdersPreviewItem({
      id: ORDER_GUIDE_ORDERS_PREVIEW_ITEM_ID,
      shortName: 'Nike Sb Janoski кеды',
      name: 'Nike Sb Janoski+ Lilac Medium Soft Pink',
      size: '42',
      priceCny: 323,
      weightKg: 1,
      weightEstimated: true,
      subtotalRub: 5067.50993,
      imageUrl: 'https://cdn.poizon.com/pro-img/origin-img/20251205/702385d2d6294e90bcc78d1e2b0b5295.jpg',
    }),
  ],
  deliveryStatus: {
    isComplete: true,
    deliveryData: {
      recipient_name: 'Денис Рыжов',
      phone: '+79510204901',
      city: 'Владивосток',
      street: 'Жуковского',
      house: '13',
      apartment: '123',
      comment: 'Привет',
    },
    updatedAt: '2026-03-25 02:38:53',
  },
  pricingState: {
    adminSettings: ORDER_GUIDE_ORDERS_PREVIEW_PRICING_SETTINGS,
    deliveryInfo: {
      standard_days: ORDER_GUIDE_ORDERS_PREVIEW_PRICING_SETTINGS.delivery_standard_moscow_days,
      express_days: ORDER_GUIDE_ORDERS_PREVIEW_PRICING_SETTINGS.delivery_air_moscow_days,
      cdek_days: ORDER_GUIDE_ORDERS_PREVIEW_PRICING_SETTINGS.delivery_cdek_russia_days,
    },
    rateRubPerCny: 11.4481,
  },
  deliveryType: 'standard',
}

function normalizeOrderGuideOrdersPreviewItem(item, index) {
  if (!item || typeof item !== 'object') {
    return null
  }

  const fallbackItem = ORDER_GUIDE_ORDERS_PREVIEW.items[index] || ORDER_GUIDE_ORDERS_PREVIEW.items[0]
  const priceCny = Number(item.price_cny)
  const weightKg = Number(item.weight_kg)
  const subtotalRub = Number(item.subtotal_rub)
  const totalWithMarginRub = Number(item.total_with_margin_rub)
  const calcJson = typeof item.calc_json === 'string'
    ? item.calc_json
    : item.calc_json && typeof item.calc_json === 'object'
      ? JSON.stringify(item.calc_json)
      : (fallbackItem?.calc_json || '')

  return {
    id: typeof item.id === 'string' || typeof item.id === 'number'
      ? item.id
      : (fallbackItem?.id || ORDER_GUIDE_ORDERS_PREVIEW_ITEM_ID),
    short_name: typeof item.short_name === 'string' && item.short_name.trim()
      ? item.short_name
      : (fallbackItem?.short_name || ''),
    name: typeof item.name === 'string' && item.name.trim()
      ? item.name
      : (fallbackItem?.name || ''),
    size: typeof item.size === 'string' ? item.size : (fallbackItem?.size || ''),
    price_cny: Number.isFinite(priceCny) ? priceCny : (fallbackItem?.price_cny || 0),
    weight_kg: Number.isFinite(weightKg) ? weightKg : (fallbackItem?.weight_kg || 0),
    weight_estimated: typeof item.weight_estimated === 'boolean'
      ? item.weight_estimated
      : Boolean(fallbackItem?.weight_estimated),
    subtotal_rub: Number.isFinite(subtotalRub)
      ? subtotalRub
      : (Number.isFinite(totalWithMarginRub) ? totalWithMarginRub : (fallbackItem?.subtotal_rub || 0)),
    total_with_margin_rub: Number.isFinite(totalWithMarginRub)
      ? totalWithMarginRub
      : (Number.isFinite(subtotalRub) ? subtotalRub : (fallbackItem?.total_with_margin_rub || 0)),
    calc_json: calcJson,
    in_order: item.in_order ? 1 : 0,
    order_submitted: item.order_submitted ? 1 : 0,
    paid: item.paid ? 1 : 0,
    shipped: item.shipped ? 1 : 0,
    arrived: item.arrived ? 1 : 0,
  }
}

function normalizeOrderGuideOrdersPreview(preview) {
  if (!preview || typeof preview !== 'object') {
    return ORDER_GUIDE_ORDERS_PREVIEW
  }

  const items = Array.isArray(preview.items)
    ? preview.items
      .map((item, index) => normalizeOrderGuideOrdersPreviewItem(item, index))
      .filter(Boolean)
    : []

  const normalizedItems = items.length ? [items[0]] : ORDER_GUIDE_ORDERS_PREVIEW.items
  const deliveryStatus = preview.deliveryStatus && typeof preview.deliveryStatus === 'object'
    ? preview.deliveryStatus
    : {}
  const deliveryData = deliveryStatus.deliveryData && typeof deliveryStatus.deliveryData === 'object'
    ? deliveryStatus.deliveryData
    : {}
  const pricingState = preview.pricingState && typeof preview.pricingState === 'object'
    ? preview.pricingState
    : {}
  const pricingAdminSettings = pricingState.adminSettings && typeof pricingState.adminSettings === 'object'
    ? pricingState.adminSettings
    : {}
  const pricingDeliveryInfo = pricingState.deliveryInfo && typeof pricingState.deliveryInfo === 'object'
    ? pricingState.deliveryInfo
    : {}
  const rateRubPerCny = Number(pricingState.rateRubPerCny)

  return {
    items: normalizedItems,
    deliveryStatus: {
      isComplete: typeof deliveryStatus.isComplete === 'boolean'
        ? deliveryStatus.isComplete
        : ORDER_GUIDE_ORDERS_PREVIEW.deliveryStatus.isComplete,
      deliveryData: {
        ...ORDER_GUIDE_ORDERS_PREVIEW.deliveryStatus.deliveryData,
        ...deliveryData,
      },
      updatedAt: typeof deliveryStatus.updatedAt === 'string' && deliveryStatus.updatedAt.trim()
        ? deliveryStatus.updatedAt
        : ORDER_GUIDE_ORDERS_PREVIEW.deliveryStatus.updatedAt,
    },
    pricingState: {
      adminSettings: {
        ...ORDER_GUIDE_ORDERS_PREVIEW.pricingState.adminSettings,
        ...pricingAdminSettings,
      },
      deliveryInfo: {
        ...ORDER_GUIDE_ORDERS_PREVIEW.pricingState.deliveryInfo,
        ...pricingDeliveryInfo,
      },
      rateRubPerCny: Number.isFinite(rateRubPerCny)
        ? rateRubPerCny
        : ORDER_GUIDE_ORDERS_PREVIEW.pricingState.rateRubPerCny,
    },
    deliveryType: typeof preview.deliveryType === 'string' && preview.deliveryType.trim()
      ? preview.deliveryType
      : ORDER_GUIDE_ORDERS_PREVIEW.deliveryType,
  }
}

function parseOrderGuideOrdersPreviewSetting(rawValue) {
  if (typeof rawValue !== 'string' || !rawValue.trim()) {
    return ORDER_GUIDE_ORDERS_PREVIEW
  }

  try {
    return normalizeOrderGuideOrdersPreview(JSON.parse(rawValue))
  } catch {
    return ORDER_GUIDE_ORDERS_PREVIEW
  }
}

const ORDER_GUIDE_LIVE_PREVIEW_PRODUCT_URL = String(ORDER_GUIDE_LIVE_PREVIEW_SNAPSHOT.product_url || '').trim().toLowerCase()
const ORDER_GUIDE_LIVE_PREVIEW_NAME = String(ORDER_GUIDE_LIVE_PREVIEW_SNAPSHOT.name || '').trim().toLowerCase()

function isOrderGuideLivePreviewEntry(item) {
  const candidateUrl = String(item?.product_url || item?.url || '').trim().toLowerCase()
  const candidateName = String(item?.name || '').trim().toLowerCase()

  return candidateUrl === ORDER_GUIDE_LIVE_PREVIEW_PRODUCT_URL || candidateName === ORDER_GUIDE_LIVE_PREVIEW_NAME
}

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

const SHOWCASE_DEFAULT_ACCENT = 'var(--poizon-blue)'
const SHOWCASE_SOURCE_LABEL = 'Poizon'
const SHOWCASE_EDITOR_SECTIONS = [
  { id: 'top', title: 'Верхний ряд', start: 0, end: 5 },
  { id: 'bottom', title: 'Нижний ряд', start: 5, end: 10 },
]

function getShowcaseAccent() {
  return SHOWCASE_DEFAULT_ACCENT
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

function _buildCuratedShowcaseProducts() {
  return CALC_CURATED_SHOWCASE_PRODUCTS
    .map((item, index) => ({
      id: item.id || `curated-${index}`,
      name: item.name || 'Товар без названия',
      imageUrl: item.imageUrl || item.image_url || '',
      priceLabel: item.priceLabel
        || (typeof item.totalRub === 'number' ? formatBuyerRub(item.totalRub) : '')
        || (typeof item.priceCny === 'number' ? formatBuyerCny(item.priceCny) : ''),
      sourceLabel: item.sourceLabel || SHOWCASE_SOURCE_LABEL,
      note: item.note || '',
      accentColor: item.accentColor || getShowcaseAccent(),
      productData: item.productData || null,
      href: item.href || '',
    }))
    .filter((item) => item.name)
}

function _buildHistoryShowcaseProducts(items) {
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
      const note = item.size ? `Размер ${item.size}` : (item.brand || '')

      return {
        id: item.id || `history-showcase-${index}`,
        name: item.name || 'Товар без названия',
        imageUrl: item.image_url || '',
        priceLabel: totalRub > 0
          ? formatBuyerRub(totalRub)
          : (typeof item.price_cny === 'number' ? formatBuyerCny(item.price_cny) : ''),
        sourceLabel: SHOWCASE_SOURCE_LABEL,
        note,
        accentColor: getShowcaseAccent(),
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
      return {
        id: `managed-showcase-${item?.slot || product.url || product.name || 'item'}`,
        slot: Number(item?.slot) || null,
        name: product.name || 'Товар без названия',
        imageUrl: product.image_url || '',
        priceLabel: typeof item?.subtotal_rub === 'number' && Number.isFinite(item.subtotal_rub)
          ? formatBuyerRub(item.subtotal_rub)
          : formatProductCnyLabel(product),
        sourceLabel: SHOWCASE_SOURCE_LABEL,
        note: buildShowcaseProductNote(product),
        accentColor: getShowcaseAccent(),
        sourceData: product,
        href: item?.url || product.url || '',
      }
    })
    .filter((item) => item.name)
    .slice(0, 10)
}

function normalizeAboutDetailsSlides(items) {
  if (!Array.isArray(items)) {
    return null
  }

  const normalizedSlides = (Array.isArray(items) ? items : [])
    .map((item, index) => {
      const slot = Number(item?.slot) || index + 1
      const imageSrc = String(item?.image_url || '').trim()
      const imageAlt = String(item?.image_alt || `Слайд ${slot}`).trim() || `Слайд ${slot}`

      if (!imageSrc) {
        return null
      }

      return {
        id: slot,
        imageSrc,
        imageAlt,
      }
    })
    .filter(Boolean)

  return normalizedSlides
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
    return {
      slot,
      url,
      normalizedUrl: extractShowcaseInputUrl(url),
      product,
      occupied: Boolean(url),
      accentColor: getShowcaseAccent(),
      sourceLabel: SHOWCASE_SOURCE_LABEL,
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

const Calculator = forwardRef(function Calculator({ onCartChange, active = false }, ref) {
  const {
    userId,
    firstName,
    haptic,
    hideKeyboard,
    initData,
    tg,
    isTelegramWebView,
    isTelegramCompatibilityMode,
  } = useTelegram()
  const prefersReducedMotion = useReducedMotion()

  const greeting = (() => {
    const h = new Date().getHours()
    if (h >= 6 && h < 12) return 'Доброе утро'
    if (h >= 12 && h < 18) return 'Добрый день'
    if (h >= 18 && h < 23) return 'Добрый вечер'
    return 'Доброй ночи'
  })()

  const [step, setStep] = useState(_MOCK_STEP === 'product' || _MOCK_STEP === 'search-results' ? _MOCK_STEP : 'idle')
  const [searchInput, setSearchInput] = useState(_MOCK_STEP === 'search-results' ? 'Nike Dunk Low' : '')
  const [searchInputFocused, setSearchInputFocused] = useState(false)
  const [product, setProduct] = useState(_MOCK_STEP === 'product' ? MOCK_PRODUCT : null)
  const [result, setResult] = useState(_MOCK_STEP === 'product' ? MOCK_RESULT : null)
  const [calcLoading, setCalcLoading] = useState(false)
  const [error, setError] = useState(null)

  const [rate, setRate] = useState(_MOCK_STEP === 'product' ? { cny_rub: 13.20 } : null)
  const [activeImg, setActiveImg] = useState(0)
  const [selVariants, setSelVariants] = useState({})
  const [selSize, setSelSize] = useState('')
  const [manualPoizonVariantChoice, setManualPoizonVariantChoice] = useState('')
  const [manualPrice, setManualPrice] = useState('')
  const [persistedSelectionBaseline, setPersistedSelectionBaseline] = useState(null)
  const fallbackSelectionResetKeyRef = useRef('')

  const [savedCalcId, setSavedCalcId] = useState(null)
  const [addedToCart, setAddedToCart] = useState(false)
  const [cartAdding, setCartAdding] = useState(false)
  const addedCartUrlRef = useRef(null)
  const addToCartSuccessRef = useRef(null)
  const idlePageRef = useRef(null)
  const productScrollRef = useRef(null)
  const manualPriceInputRef = useRef(null)
  const pendingManualPriceScrollRef = useRef(false)
  const orderGuideAutoScrollFrameRef = useRef(0)
  const [loadingMode, setLoadingMode] = useState('product')
  const [loadingText, setLoadingText] = useState('')
  const [specsOpen, setSpecsOpen] = useState(false)
  const [adminSettings, setAdminSettings] = useState(null)

  /* ── home promo state ── */
  const [promoBanners, setPromoBanners] = useState(() => CALC_PROMO_BANNERS)
  const [aboutDetailsSlides, setAboutDetailsSlides] = useState(null)
  const [promoSlideIndex, setPromoSlideIndex] = useState(0)
  const [promoModalBannerId, setPromoModalBannerId] = useState(0)
  const [promoEntryBannerId, setPromoEntryBannerId] = useState(0)
  const [aboutDetailsOpen, setAboutDetailsOpen] = useState(false)
  const [orderGuideOpen, setOrderGuideOpen] = useState(false)
  const [orderGuideStep, setOrderGuideStep] = useState(1)

  /* ── search state ── */
  const [searchQuery, setSearchQuery] = useState(_MOCK_STEP === 'search-results' ? 'Nike Dunk Low' : '')
  const searchCount = 20
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchLoadingMore, setSearchLoadingMore] = useState(false)
  const [searchError, setSearchError] = useState(null)
  const [searchResultOpenError, setSearchResultOpenError] = useState(null)
  const [searchResults, setSearchResults] = useState(_MOCK_STEP === 'search-results' ? MOCK_SEARCH_RESULTS : [])
  const [searchRate, setSearchRate] = useState(_MOCK_STEP === 'search-results' ? 13.20 : null)
  const [searchHasMore, setSearchHasMore] = useState(false)
  const [searchNextStartId, setSearchNextStartId] = useState(0)
  const [showcaseProducts, setShowcaseProducts] = useState([])
  const [, setIsAdminViewer] = useState(false)
  const [showcaseEditorOpen, setShowcaseEditorOpen] = useState(false)
  const [showcaseEditorLoading] = useState(false)
  const [showcaseEditorSaving, setShowcaseEditorSaving] = useState(false)
  const [showcaseEditorError, setShowcaseEditorError] = useState('')
  const [showcaseEditorSlotErrors, setShowcaseEditorSlotErrors] = useState({})
  const [showcaseEditorSlots, setShowcaseEditorSlots] = useState(() => buildShowcaseEditorSlots([], []))
  const [showcaseEditorActiveSlot, setShowcaseEditorActiveSlot] = useState(1)
  const [showcaseEditorInput, setShowcaseEditorInput] = useState('')
  const [orderGuideLivePreviewData, setOrderGuideLivePreviewData] = useState(ORDER_GUIDE_LIVE_PREVIEW_SNAPSHOT)
  const [orderGuideCartPreview, setOrderGuideCartPreview] = useState(ORDER_GUIDE_CART_PREVIEW)
  const [orderGuideOrdersPreview, setOrderGuideOrdersPreview] = useState(ORDER_GUIDE_ORDERS_PREVIEW)
  const promoTouchRef = useRef({ x: 0, y: 0, moved: false })
  const promoEntryShownRef = useRef(false)
  const showcaseFocusTimeoutsRef = useRef([])
  const showcaseEditorInputRef = useRef(null)
  const parseProductRequestIdRef = useRef(0)
  const skipNextAutoCalculateRef = useRef(false)
  const orderGuideIdleSearchInputRef = useRef('')
  const orderGuideLivePreviewTriggeredRef = useRef(false)
  const orderGuideLivePreviewFetchIdRef = useRef(0)

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

  const openPersistedCalculation = useCallback((data) => {
    const nextProduct = {
      url: data?.product_url || data?.url || '',
      platform: data?.platform || 'poizon',
      name: data?.name || '',
      brand: data?.brand || '',
      price_cny: data?.price_cny,
      price_is_starting: Boolean(data?.price_is_starting),
      size: data?.size || '',
      category: data?.category || '',
      weight_kg: data?.weight_kg ?? null,
      weight_estimated: Boolean(data?.weight_estimated),
      city: data?.city || '',
      delivery_type: data?.delivery_type || '',
      image_url: data?.image_url || '',
      extra_images: Array.isArray(data?.extra_images) ? data.extra_images : [],
      specs: data?.specs || {},
      available_sizes: Array.isArray(data?.available_sizes) ? data.available_sizes : [],
      variants: Array.isArray(data?.variants) ? data.variants : [],
      variant_price_map: data?.variant_price_map || {},
      original_variants: Array.isArray(data?.original_variants) ? data.original_variants : [],
      notes: data?.notes || '',
      auto_detected: [],
    }
    const restoredSelection = derivePersistedVariantSelection(nextProduct)
    const persistedCalcId = data?.calc_id || data?.id || null

    const nextBreakdown = Array.isArray(data?.breakdown)
      ? data.breakdown
        .map((row) => ({
          label: row?.label || '',
          amount_rub: Number(row?.amount_rub || 0),
          note: row?.note || '',
        }))
        .filter((row) => row.label)
      : []

    const subtotalRub = Number(data?.subtotal_rub || data?.total_with_margin_rub || 0)
    const totalWithMarginRub = Number(data?.total_with_margin_rub || data?.subtotal_rub || 0)
    const nextResult = subtotalRub > 0 || nextBreakdown.length
      ? {
          subtotal_rub: subtotalRub,
          total_with_margin_rub: totalWithMarginRub,
          breakdown: nextBreakdown,
          exchange_rate: data?.exchange_rate || (rate?.cny_rub ? { cny_rub: rate.cny_rub } : null),
          delivery_info: data?.delivery_info || null,
        }
      : null

    skipNextAutoCalculateRef.current = Boolean(nextResult)
    setProduct(nextProduct)
    setActiveImg(0)
    setSelVariants(restoredSelection.selectedVariants)
    setSelSize(restoredSelection.selectedSize)
    setManualPoizonVariantChoice('')
    setManualPrice('')
    setPersistedSelectionBaseline({
      calcId: persistedCalcId,
      priceCny: nextProduct.price_cny ?? null,
      size: String(nextProduct.size || '').trim(),
    })
    setResult(nextResult)
    setSavedCalcId(persistedCalcId)
    setAddedToCart(false)
    addedCartUrlRef.current = null
    setSpecsOpen(false)
    setSearchResults([])
    setStep('product')
  }, [rate])

  const resetOrderGuideLivePreviewRuntime = useCallback(() => {
    parseProductRequestIdRef.current += 1
    skipNextAutoCalculateRef.current = false
    orderGuideLivePreviewTriggeredRef.current = false
  }, [])

  const resetOrderGuidePreviewSelectionState = useCallback(() => {
    setSelVariants({})
    setSelSize('')
    setManualPoizonVariantChoice('')
    setAddedToCart(false)
    addedCartUrlRef.current = null
    setPersistedSelectionBaseline(null)
    setSavedCalcId(null)
  }, [])

  const restoreOrderGuideIdleState = useCallback(() => {
    setSearchInput(orderGuideIdleSearchInputRef.current)
    setSearchInputFocused(false)
    setSearchQuery('')
    setProduct(null)
    setResult(null)
    setCalcLoading(false)
    setError(null)
    setLoadingMode('product')
    setLoadingText('')
    setActiveImg(0)
    setSelVariants({})
    setSelSize('')
    setManualPoizonVariantChoice('')
    setManualPrice('')
    setPersistedSelectionBaseline(null)
    setSavedCalcId(null)
    setAddedToCart(false)
    addedCartUrlRef.current = null
    setSpecsOpen(false)
    setSearchError(null)
    setSearchResultOpenError(null)
    setSearchResults([])
    setSearchLoading(false)
    setSearchLoadingMore(false)
    setSearchHasMore(false)
    setSearchNextStartId(0)
    setStep('idle')
  }, [])

  const clearShowcaseFocusTimers = useCallback(() => {
    showcaseFocusTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId))
    showcaseFocusTimeoutsRef.current = []
  }, [])

  const cancelOrderGuideAutoScroll = useCallback(() => {
    if (orderGuideAutoScrollFrameRef.current) {
      window.cancelAnimationFrame(orderGuideAutoScrollFrameRef.current)
      orderGuideAutoScrollFrameRef.current = 0
    }
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
  /* ── bootstrap ── */
  const hydrateOrderGuideLivePreviewFromHistory = useCallback(async () => {
    if (!userId) return null

    const requestId = ++orderGuideLivePreviewFetchIdRef.current

    try {
      const historyData = await apiFetch(`/api/history?user_id=${userId}`, { method: 'GET' })
      if (requestId !== orderGuideLivePreviewFetchIdRef.current) {
        return null
      }

      const historyItems = Array.isArray(historyData)
        ? historyData
        : historyData
          ? [historyData]
          : []
      const matchedItem = historyItems.find(isOrderGuideLivePreviewEntry) || null

      if (matchedItem) {
        setOrderGuideLivePreviewData(matchedItem)
      }

      return matchedItem
    } catch {
      return null
    }
  }, [userId])

  useEffect(() => {
    hydrateOrderGuideLivePreviewFromHistory()
  }, [hydrateOrderGuideLivePreviewFromHistory])

  useEffect(() => {
    setOrderGuideCartPreview(
      parseOrderGuideCartPreviewSetting(adminSettings?.[ORDER_GUIDE_STEP_SIX_PREVIEW_SETTING_KEY]),
    )
    setOrderGuideOrdersPreview(
      parseOrderGuideOrdersPreviewSetting(adminSettings?.[ORDER_GUIDE_STEP_EIGHT_PREVIEW_SETTING_KEY]),
    )
  }, [adminSettings])

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
    setManualPoizonVariantChoice('')
    setManualPrice('')
    setPersistedSelectionBaseline(null)
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

    setShowcaseProducts([])
  }, [])

  const applyPromoBannerSource = useCallback((bootstrapPayload) => {
    const nextBanners = (Array.isArray(bootstrapPayload?.promo_banners) ? bootstrapPayload.promo_banners : [])
      .map((banner) => normalizePromoBanner(banner))
      .filter((banner) => banner.title || banner.image_url)
    const nextEntryBannerId = Number(bootstrapPayload?.promo_entry_banner_id || 0)

    const resolvedBanners = nextBanners.length ? nextBanners : CALC_PROMO_BANNERS
    setPromoBanners(resolvedBanners)
    setPromoEntryBannerId(
      nextBanners.some((banner) => banner.id === nextEntryBannerId)
        ? nextEntryBannerId
        : 0,
    )
    setPromoModalBannerId((currentBannerId) => {
      if (!currentBannerId) return currentBannerId

      const bannerStillExists = resolvedBanners.some((banner) => banner.id === currentBannerId)
      if (bannerStillExists) {
        return currentBannerId
      }

      return nextEntryBannerId && resolvedBanners.some((banner) => banner.id === nextEntryBannerId)
        ? nextEntryBannerId
        : 0
    })
    setPromoSlideIndex((currentIndex) => {
      if (!resolvedBanners.length) return 0
      return Math.min(currentIndex, resolvedBanners.length - 1)
    })
  }, [])

  const applyAboutDetailsSource = useCallback((bootstrapPayload) => {
    setAboutDetailsSlides(normalizeAboutDetailsSlides(bootstrapPayload?.about_details_slides))
  }, [])

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
      applyAboutDetailsSource(data)
      applyPromoBannerSource(data)
      return data
    } catch {
      setIsAdminViewer(false)
      setAboutDetailsSlides(null)
      setPromoBanners(CALC_PROMO_BANNERS)
      setPromoEntryBannerId(0)
      return null
    }
  }, [applyAboutDetailsSource, applyPromoBannerSource, applyShowcaseSource, initData, userId])

  useEffect(() => {
    if (!active) return
    refreshBootstrap()
  }, [active, refreshBootstrap])

  useEffect(() => {
    if (!active || step !== 'idle' || promoModalBannerId || promoEntryShownRef.current) {
      return undefined
    }

    const entryBanner = promoBanners.find((banner) => banner.id === promoEntryBannerId)
    if (!entryBanner) {
      return undefined
    }

    promoEntryShownRef.current = true
    setPromoModalBannerId(entryBanner.id)
    return undefined
  }, [active, promoBanners, promoEntryBannerId, promoModalBannerId, step])

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
    if (!active || step !== 'idle' || prefersReducedMotion || promoBanners.length < 2) {
      return undefined
    }

    const intervalId = window.setInterval(() => {
      setPromoSlideIndex((currentIndex) => (currentIndex + 1) % promoBanners.length)
    }, 4000)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [active, prefersReducedMotion, promoBanners.length, step])

  /* ── publish calculator-specific shell swipe root ── */
  useEffect(() => {
    const blockShellSwipe = active && (step === 'search-results' || step === 'product' || step === 'loading')
    document.body.dataset.shellSwipeRootCalculator = blockShellSwipe ? '0' : '1'
    return () => { document.body.dataset.shellSwipeRootCalculator = '1' }
  }, [active, step])

  /* ── keep legacy shell fallback in sync during migration ── */
  useEffect(() => {
    const blockShellSwipe = active && (step === 'search-results' || step === 'product' || step === 'loading')
    document.body.dataset.blockTabSwipe = blockShellSwipe ? '1' : '0'
    return () => { document.body.dataset.blockTabSwipe = '0' }
  }, [active, step])

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
    setLoadingText('Загружаю товар...')
    const t1 = setTimeout(() => setLoadingText('Анализирую данные...'), 5000)
    const t2 = setTimeout(() => setLoadingText('Почти готово...'), 15000)
    const t3 = setTimeout(() => setLoadingText('Ещё немного...'), 30000)
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
  }, [step, loadingMode])

  /* ── images ── */
  useEffect(() => {
    if (step !== 'loading' || loadingMode !== 'search') return
    setLoadingText('Ищу товары...')
    const t1 = setTimeout(() => setLoadingText('Собираю результаты...'), 5000)
    const t2 = setTimeout(() => setLoadingText('Почти готово...'), 15000)
    const t3 = setTimeout(() => setLoadingText('Ещё немного...'), 30000)
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
  }, [step, loadingMode])

  const images = product
    ? [product.image_url, ...(product.extra_images || [])].filter(Boolean).map(proxyImageUrl)
    : []

  const selectedOptionsText = manualPoizonVariantChoice
    ? POIZON_MANUAL_VARIANT_SELECTIONS[manualPoizonVariantChoice]
    : getSelectedOptionsText(product, selVariants, selSize)
  const pricingSourceProduct = product && persistedSelectionBaseline?.calcId && savedCalcId === persistedSelectionBaseline.calcId
    ? {
        ...product,
        price_cny: persistedSelectionBaseline.priceCny ?? product.price_cny,
        size: persistedSelectionBaseline.size || product.size || '',
      }
    : product
  const manualVariantPriceRequired = Boolean(manualPoizonVariantChoice)
    || shouldRequireManualPriceForSelection(pricingSourceProduct, selectedOptionsText)
  const priceStateProduct = manualVariantPriceRequired && pricingSourceProduct
    ? {
        ...pricingSourceProduct,
        price_cny: null,
        price_is_starting: true,
      }
    : pricingSourceProduct

  /* ── current price from variants (cascade-aware) ── */
  const priceState = resolveProductPriceState(priceStateProduct, selVariants, manualPrice)

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
  const deliverySettings = getDeliverySettings(adminSettings || {})
  const pricingSnapshot = JSON.stringify({
    rate: rate?.cny_rub ?? null,
    commission: adminSettings?.commission_pct ?? null,
    minCommission: adminSettings?.min_commission_rub ?? null,
    standardDeliveryRub500g: adminSettings?.delivery_standard_moscow_rub_500g ?? null,
    expressDeliveryRub500g: adminSettings?.delivery_air_moscow_rub_500g ?? null,
    cdekDeliveryRub500g: adminSettings?.delivery_cdek_russia_rub_500g ?? null,
    standardDeliveryDays: adminSettings?.delivery_standard_moscow_days ?? null,
    expressDeliveryDays: adminSettings?.delivery_air_moscow_days ?? null,
    cdekDeliveryDays: adminSettings?.delivery_cdek_russia_days ?? null,
  })
  const deliveryInfo = {
    standard_days: result?.delivery_info?.standard_days || deliverySettings.standardDays,
    express_days: result?.delivery_info?.express_days || deliverySettings.expressDays,
    cdek_days: result?.delivery_info?.cdek_days || deliverySettings.cdekDays,
  }

  // Button state: ref survives any re-render/effect that resets addedToCart state
  const isInCart = addedToCart || (product && addedCartUrlRef.current === product.url)
  const searchStateCopy = searchError === 'empty'
    ? BUYER_STATE_COPY.calculator.searchEmpty
    : searchError === 'error'
      ? BUYER_STATE_COPY.calculator.searchError
      : null
  const addToCartSuccessState = BUYER_STATE_COPY.calculator.addToCartSuccess
  const searchInputText = searchInput.trim()
  const searchInputUrl = extractShowcaseInputUrl(searchInput)
  const canSubmitSearchInput = Boolean(searchInputText)
  const canSubmitNameSearch = Boolean(searchQuery.trim())
  const shouldShowSearchHint = !searchInputText && !searchInputFocused
  const showAnimatedSearchHint = shouldShowSearchHint && !prefersReducedMotion
  const showStaticSearchHint = shouldShowSearchHint && !showAnimatedSearchHint
  const allowAnimatedIntro = active && !prefersReducedMotion && !isTelegramWebView

  useEffect(() => {
    const baselineSelection = String(pricingSourceProduct?.size || '').trim()
    const shouldTrackSelectionChanges = shouldAllowFallbackVariantSelection(pricingSourceProduct) && baselineSelection
    const selectionResetKey = shouldTrackSelectionChanges
      ? `${savedCalcId || 'persisted'}:${selectedOptionsText}`
      : ''

    if (!selectionResetKey) {
      fallbackSelectionResetKeyRef.current = ''
      return
    }

    if (
      fallbackSelectionResetKeyRef.current
      && fallbackSelectionResetKeyRef.current !== selectionResetKey
    ) {
      setManualPrice('')
    }

    fallbackSelectionResetKeyRef.current = selectionResetKey
  }, [pricingSourceProduct, savedCalcId, selectedOptionsText])

  useEffect(() => {
    if (!pendingManualPriceScrollRef.current || !manualPriceInputRef.current) {
      return
    }

    pendingManualPriceScrollRef.current = false
    window.requestAnimationFrame(() => {
      manualPriceInputRef.current?.scrollIntoView({
        behavior: prefersReducedMotion ? 'auto' : 'smooth',
        block: 'center',
        inline: 'nearest',
      })
    })
  }, [prefersReducedMotion, selectedOptionsText])

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
    if (skipNextAutoCalculateRef.current) {
      skipNextAutoCalculateRef.current = false
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
          if (savedCalcId) {
            setPersistedSelectionBaseline({
              calcId: r.calc_id || savedCalcId,
              priceCny: curPrice,
              size: String(selectedOptionsText || '').trim(),
            })
          }
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

  const handleSubmit = useCallback(async (inputUrl = searchInputUrl, options = {}) => {
    const { withHaptic = true } = options
    const u = extractShowcaseInputUrl(inputUrl) || String(inputUrl || '').trim()
    if (!u) return
    const requestId = parseProductRequestIdRef.current + 1
    parseProductRequestIdRef.current = requestId
    if (withHaptic) {
      haptic?.('medium')
    }
    setError(null)
    setSearchError(null)
    setSearchResultOpenError(null)
    setLoadingMode('product')
    setLoadingText('Загружаю товар...')
    setStep('loading')
    try {
      const d = await apiFetch('/api/parse-product', {
        method: 'POST',
        body: JSON.stringify({ url: u }),
      })
      if (parseProductRequestIdRef.current !== requestId) {
        return
      }
      setProduct(d)
      setActiveImg(0)
      setSelVariants({})
      setSelSize('')
      setManualPoizonVariantChoice('')
      setManualPrice('')
      setPersistedSelectionBaseline(null)
      setResult(null)
      setSavedCalcId(null)
      setAddedToCart(false)
      addedCartUrlRef.current = null
      setSpecsOpen(false)
      setSearchInput('')
      setStep('product')
      if (withHaptic) {
        haptic?.('light')
      }
    } catch {
      if (parseProductRequestIdRef.current !== requestId) {
        return
      }
      setError('Не удалось загрузить товар. Проверь ссылку.')
      setStep('idle')
      if (withHaptic) {
        haptic?.('error')
      }
    }
  }, [haptic, searchInputUrl])

  /* ── search handler ── */
  const handleSearch = async (inputQuery = searchInputText) => {
    const q = String(inputQuery || '').trim()
    const requestedPlatform = POIZON_PLATFORM
    if (!q || !requestedPlatform) return
    haptic?.('medium')
    setError(null)
    setSearchError(null)
    setSearchResultOpenError(null)
    setSearchQuery(q)
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
      setSearchNextStartId(nextStartId)
      setSearchHasMore(hasMore)
      setSearchInput('')
      setSearchLoading(false)
      setStep('search-results')
      haptic?.('success')
    } catch {
      setSearchError('error')
      setSearchLoading(false)
      setStep('idle')
      haptic?.('error')
    }
  }

  const handlePrimarySearch = () => {
    if (!searchInputText) return

    if (searchInputUrl) {
      handleSubmit(searchInputUrl)
      return
    }

    handleSearch(searchInputText)
  }

  const handleLoadMore = async () => {
    const q = searchQuery.trim()
    const requestedPlatform = POIZON_PLATFORM
    if (!q || searchLoadingMore || !requestedPlatform || !searchHasMore) return
    const currentStartId = searchNextStartId
    haptic?.('light')
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
        setSearchNextStartId(nextStartId)
        setSearchHasMore(hasMore)
        haptic?.('success')
      } else {
        setSearchHasMore(false)
      }
    } catch {
      setSearchHasMore(false)
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

  const handleBack = () => {
    parseProductRequestIdRef.current += 1
    skipNextAutoCalculateRef.current = false
    haptic?.('light')
    addedCartUrlRef.current = null
    setManualPoizonVariantChoice('')
    if ((step === 'product' || step === 'loading') && searchResults.length > 0) {
      setProduct(null)
      setPersistedSelectionBaseline(null)
      setResult(null)
      setError(null)
      setSavedCalcId(null)
      setAddedToCart(false)
      setStep('search-results')
    } else {
      setStep('idle')
      setProduct(null)
      setPersistedSelectionBaseline(null)
      setResult(null)
      setError(null)
      setSavedCalcId(null)
      setAddedToCart(false)
    }
  }

  const handleSearchHome = () => {
    haptic?.('light')
    setStep('idle')
    setManualPoizonVariantChoice('')
    setSearchError(null)
    setSearchResultOpenError(null)
    setSearchResults([])
    setSearchHasMore(false)
    setSearchNextStartId(0)
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
    if (promoBanners.length < 2 || Math.abs(deltaX) < 36 || Math.abs(deltaX) < Math.abs(deltaY) * 1.15) {
      promoTouchRef.current.moved = false
      return
    }

    promoTouchRef.current.moved = true
    setPromoSlideIndex((currentIndex) => {
      const direction = deltaX > 0 ? 1 : -1
      return (currentIndex + direction + promoBanners.length) % promoBanners.length
    })
    haptic?.('light')
  }

  const handleClosePromoBanner = useCallback(() => {
    setPromoModalBannerId(0)
    haptic?.('light')
  }, [haptic])

  const handlePromoBannerAction = useCallback((banner, targetUrl = '') => {
    const resolvedUrl = String(targetUrl || banner?.button_url || '').trim()
    if (!resolvedUrl) {
      return
    }

    try {
      if (typeof tg?.openLink === 'function') {
        tg.openLink(resolvedUrl)
      } else {
        window.open(resolvedUrl, '_blank', 'noopener,noreferrer')
      }
      haptic?.('light')
    } catch {
      haptic?.('error')
    }
  }, [haptic, tg])

  const handlePromoBannerClick = (event) => {
    if (promoTouchRef.current.moved) {
      event.preventDefault()
      promoTouchRef.current.moved = false
      return
    }

    event.preventDefault()
    if (activePromoBanner?.id) {
      setPromoModalBannerId(activePromoBanner.id)
    }
    haptic?.('light')
  }

  /* ── open product detail from search result ── */
  const handleOpenProduct = async (item) => {
    if (!item || typeof item !== 'object') return

    haptic?.('medium')
    setSearchResultOpenError(null)
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
    setManualPoizonVariantChoice('')
    setManualPrice('')
    setPersistedSelectionBaseline(null)
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
  const activePromoBanner = promoBanners[promoSlideIndex] || promoBanners[0] || null
  const activePromoModalBanner = promoBanners.find((banner) => banner.id === promoModalBannerId) || null

  const handleOpenAboutDetails = () => {
    setAboutDetailsOpen(true)
    haptic?.('light')
  }

  const handleCloseAboutDetails = () => {
    setAboutDetailsOpen(false)
    haptic?.('light')
  }

  const handleOpenOrderGuide = useCallback(() => {
    hydrateOrderGuideLivePreviewFromHistory()
    orderGuideIdleSearchInputRef.current = searchInput
    orderGuideLivePreviewTriggeredRef.current = false
    resetOrderGuidePreviewSelectionState()
    setOrderGuideStep(1)
    setOrderGuideOpen(true)
    haptic?.('light')
  }, [haptic, hydrateOrderGuideLivePreviewFromHistory, resetOrderGuidePreviewSelectionState, searchInput])

  useImperativeHandle(ref, () => ({
    openProduct(data) {
      openPersistedCalculation(data)
    },
    openOrderGuide() {
      handleOpenOrderGuide()
    },
  }), [handleOpenOrderGuide, openPersistedCalculation])

  const handleOrderGuideStepChange = useCallback((nextStep) => {
    if (nextStep === 5) {
      resetOrderGuidePreviewSelectionState()
    }
    setOrderGuideStep(nextStep)
  }, [resetOrderGuidePreviewSelectionState])

  const handleCloseOrderGuide = () => {
    const shouldRestoreIdleState = orderGuideLivePreviewTriggeredRef.current
    resetOrderGuideLivePreviewRuntime()
    setOrderGuideStep(1)
    setOrderGuideOpen(false)
    if (shouldRestoreIdleState) {
      restoreOrderGuideIdleState()
    }
    haptic?.('light')
  }

  useEffect(() => {
    if (!orderGuideOpen || orderGuideStep !== 5 || orderGuideLivePreviewTriggeredRef.current) {
      return
    }

    orderGuideLivePreviewTriggeredRef.current = true
    openPersistedCalculation(orderGuideLivePreviewData || ORDER_GUIDE_LIVE_PREVIEW_SNAPSHOT)
  }, [openPersistedCalculation, orderGuideLivePreviewData, orderGuideOpen, orderGuideStep])

  const orderGuideOverlay = (
    <OrderGuideSheet
      open={orderGuideOpen}
      onClose={handleCloseOrderGuide}
      onCurrentStepChange={handleOrderGuideStepChange}
      cartGuidePreview={orderGuideCartPreview}
      ordersGuidePreview={orderGuideOrdersPreview}
    />
  )

  const shouldShowOrderGuideLiveProductScreen = orderGuideOpen
    && orderGuideStep === 5
    && orderGuideLivePreviewTriggeredRef.current
  const displayStep = orderGuideOpen
    && orderGuideLivePreviewTriggeredRef.current
    && !shouldShowOrderGuideLiveProductScreen
    ? 'idle'
    : step
  useEffect(() => {
    if (displayStep !== 'product' || !orderGuideOpen || orderGuideStep !== 5) {
      cancelOrderGuideAutoScroll()
      return undefined
    }

    let setupFrameId = 0

    const startAutoScroll = () => {
      const scrollNode = productScrollRef.current
      if (!(scrollNode instanceof HTMLElement)) {
        return
      }

      const maxScrollTop = Math.max(0, scrollNode.scrollHeight - scrollNode.clientHeight)
      const targetScrollTop = maxScrollTop * 0.4
      scrollNode.scrollTop = 0

      if (targetScrollTop <= 0) {
        return
      }

      const duration = prefersReducedMotion ? 2000 : 3400
      let startedAt = 0

      const stepScroll = (timestamp) => {
        if (!startedAt) {
          startedAt = timestamp
        }

        const elapsed = timestamp - startedAt
        const progress = Math.min(elapsed / duration, 1)
        const easedProgress = 1 - ((1 - progress) * (1 - progress) * (1 - progress))
        scrollNode.scrollTop = targetScrollTop * easedProgress

        if (progress < 1) {
          orderGuideAutoScrollFrameRef.current = window.requestAnimationFrame(stepScroll)
        } else {
          orderGuideAutoScrollFrameRef.current = 0
        }
      }

      orderGuideAutoScrollFrameRef.current = window.requestAnimationFrame(stepScroll)
    }

    cancelOrderGuideAutoScroll()
    setupFrameId = window.requestAnimationFrame(() => {
      startAutoScroll()
    })

    return () => {
      if (setupFrameId) {
        window.cancelAnimationFrame(setupFrameId)
      }
      cancelOrderGuideAutoScroll()
    }
  }, [cancelOrderGuideAutoScroll, displayStep, orderGuideOpen, orderGuideStep, prefersReducedMotion])

  if (displayStep === 'idle') {
    return (
      <>
        <div ref={idlePageRef} className="calc-page buyer-page buyer-page--calculator">
        <div className="calc-page__ambient" aria-hidden="true">
          {allowAnimatedIntro ? (
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
            <img
              className="calc-page__logo-media"
              src="/0403.gif"
              alt="Logistics Store"
              loading="eager"
              fetchPriority="high"
              decoding="sync"
            />
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
            enabled={allowAnimatedIntro}
          >
            <div className="calc-page__cta-stack">
              <div className="calc-page__input-spotlight-shell">
                <div
                  className="calc-page__input-spotlight-band calc-page__input-spotlight-band--top"
                  aria-hidden="true"
                />
                <div className="calc-page__input-wrap">
            {showAnimatedSearchHint ? (
              <div className="calc-page__input-ghost" aria-hidden="true">
                <TextType
                  as="span"
                  text={CALC_SEARCH_HINTS}
                  typingSpeed={50}
                  initialDelay={0}
                  pauseDuration={2000}
                  deletingSpeed={30}
                  loop
                  showCursor
                  hideCursorWhileTyping={false}
                  cursorCharacter="|"
                  cursorBlinkDuration={0.5}
                  className="calc-page__input-text-type"
                  cursorClassName="calc-page__input-text-type-cursor"
                />
              </div>
            ) : showStaticSearchHint ? (
              <div className="calc-page__input-ghost" aria-hidden="true">
                <span className="calc-page__input-text-type">{CALC_SEARCH_HINTS[0]}</span>
              </div>
            ) : null}
            <input
              className="calc-page__input"
              type="text"
              value={searchInput}
              placeholder=""
              onChange={(e) => {
                setSearchInput(e.target.value)
                setError(null)
                setSearchError(null)
                setSearchResultOpenError(null)
              }}
              onFocus={() => setSearchInputFocused(true)}
              onBlur={() => setSearchInputFocused(false)}
              onKeyDown={(e) => e.key === 'Enter' && handlePrimarySearch()}
              autoComplete="off"
              autoCorrect="off"
              spellCheck="false"
              enterKeyHint="search"
              aria-label="Поиск товара по ссылке или названию"
            />
            <button className="calc-page__submit pressable" onClick={handlePrimarySearch} disabled={!canSubmitSearchInput}>
              <IconSearch size={20} />
            </button>
                </div>
                <div
                  className="calc-page__input-spotlight-band calc-page__input-spotlight-band--bottom"
                  aria-hidden="true"
                />
              </div>
              <div className="calc-page__quick-actions" role="group" aria-label="Быстрые действия">
                <button type="button" className="calc-page__quick-action calc-page__quick-action--latched pressable" onClick={handleOpenAboutDetails}>
                  <IconInfo size={20} />
                  <span>Подробнее о нас</span>
                </button>
                <button type="button" className="calc-page__quick-action calc-page__quick-action--latched pressable" onClick={handleOpenOrderGuide}>
                  <BrandGemIcon size={20} colors={['currentColor', 'currentColor', 'currentColor']} />
                  <span>Как сделать заказ</span>
                </button>
              </div>
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
                onAction={handlePrimarySearch}
                icon={getCalculatorStateIcon(BUYER_STATE_COPY.calculator.linkError.iconName)}
              />
            </div>
          ) : null}

          <div className={searchStateCopy ? 'calc-search' : 'calc-search calc-search--collapsed'}>
            <FadeContent
              className="calc-page__fade-field"
              container={idlePageRef}
              blur
              duration={900}
              delay={180}
              threshold={0.18}
              enabled={allowAnimatedIntro}
            >
              <div className="calc-page__input-wrap">
              <input
                className="calc-page__input"
                type="text"
                placeholder="Название товара"
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
                  onAction={searchError === 'error' ? handlePrimarySearch : undefined}
                  icon={getCalculatorStateIcon(searchStateCopy.iconName)}
                />
              </div>
            ) : null}
          </div>

          <div className="calc-banner-carousel">
            <button
              type="button"
              className="calc-banner pressable"
              onTouchStart={handlePromoTouchStart}
              onTouchEnd={handlePromoTouchEnd}
              onClick={handlePromoBannerClick}
              aria-label={`Открыть баннер ${activePromoBanner.label}`}
            >
              <div className="calc-banner__aura calc-banner__aura--left" aria-hidden="true" />
              <div className="calc-banner__aura calc-banner__aura--right" aria-hidden="true" />
              <div className="calc-banner__surface">
                <div className="calc-banner__viewport">
                  {promoBanners.map((banner, index) => (
                    <span
                      key={banner.id || banner.label || index}
                      className={`calc-banner__slide${index === promoSlideIndex ? ' calc-banner__slide--active' : ''}`}
                      aria-hidden={index === promoSlideIndex ? 'false' : 'true'}
                    >
                      <img
                        className="calc-banner__image"
                        src={banner.image_url}
                        alt={banner.image_alt || banner.title || banner.label || ''}
                        loading={index === 0 ? 'eager' : 'lazy'}
                      />
                    </span>
                  ))}
                </div>

              </div>
            </button>

            <div className="calc-banner__dots" role="tablist" aria-label="Переключение баннеров">
              {promoBanners.map((banner, index) => (
                <button
                  key={`dot-${banner.id || banner.label || index}`}
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

          <PromoBannerOverlay
            open={Boolean(activePromoModalBanner)}
            banner={activePromoModalBanner}
            onClose={handleClosePromoBanner}
            onAction={(targetUrl) => handlePromoBannerAction(activePromoModalBanner, targetUrl)}
          />
          <AboutDetailsSheet
            open={aboutDetailsOpen}
            onClose={handleCloseAboutDetails}
            items={aboutDetailsSlides ?? undefined}
          />

          <CalculatorShowcase
            items={showcaseProducts}
            onSelect={handleShowcaseCardSelect}
            actions={null}
          />

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
        </div>
        </div>
        {orderGuideOverlay}
      </>
    )
  }

  /* ═══════════════════════════════════════════════════════════════ */
  /*  SEARCH RESULTS — simple grid with scroll                      */
  /* ═══════════════════════════════════════════════════════════════ */
  if (displayStep === 'search-results' && searchResults.length > 0) {
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
      </>
    )
  }

  /* ═══════════════════════════════════════════════════════════════ */
  /*  LOADING                                                       */
  /* ═══════════════════════════════════════════════════════════════ */
  if (displayStep === 'loading') {
    return (
      <>
        <div className="calc-page buyer-page buyer-page--calculator">
        <div className="calc-loader">
          <LoadingGlyph className="calc-loader__indicator" size="lg" />
          <p className="calc-loader__text">{loadingText}</p>
          <button className="calc-loader__cancel pressable" onClick={handleBack}>
            Отменить
          </button>
        </div>
        </div>
        {orderGuideOverlay}
      </>
    )
  }

  /* ═══════════════════════════════════════════════════════════════ */
  /*  PRODUCT  (unified — card + live calc + actions)               */
  /* ═══════════════════════════════════════════════════════════════ */
  if (displayStep === 'product' && product) {
    const hasVariants = (product.variants || []).some((g) => (g.options || []).length >= 2)
    const variantHasSizes = (product.variants || []).some(
      (g) => (g.options || []).length >= 2 && SIZE_GROUP_NAMES.includes(g.name.toLowerCase())
    )
    const hasSizes = !variantHasSizes && (product.available_sizes || []).length >= 2
    const canSelectStandaloneSizes = !hasSizes || shouldAllowFallbackVariantSelection(product)
    const variantGroups = (product.variants || []).filter((g) => (g.options || []).length >= 2)
    const showVariantControls = hasVariants || hasSizes
    const shouldExposeOrderGuideStepFiveFocus = orderGuideOpen && orderGuideStep === 5
    const allVariantsSelected = variantGroups.every((g) => selVariants[g.name])
    const sizeSelected = !hasSizes || !canSelectStandaloneSizes || !!selSize
    const allOptionsSelected = Boolean(manualPoizonVariantChoice) || (allVariantsSelected && sizeSelected)
    const hasSpecs = product.specs && Object.keys(product.specs).length > 0
    const canAddToCart = !isInCart && !cartAdding && !calcLoading && !!result && allOptionsSelected
    const waitingForExactPriceSelection = Boolean((product.price_is_starting || manualVariantPriceRequired) && !allOptionsSelected)
    const hasExactPriceFromData = priceState.source === 'base' || priceState.source === 'variant'
    const shouldShowManualPriceInput = Boolean(
      manualPoizonVariantChoice
        ? true
        : manualVariantPriceRequired
        ? allOptionsSelected
        : !hasExactPriceFromData && (
        product.price_cny == null || (product.price_is_starting && allOptionsSelected)
      )
    )
    const missingManualPrice = shouldShowManualPriceInput && !curPrice
    const shouldHideSummaryTotal = shouldShowManualPriceInput && displayPriceCny == null && curPriceRub == null && !result
    const manualPriceHelperText = manualPoizonVariantChoice === 'right'
      ? POIZON_MANUAL_OTHER_PLATFORM_PRICE_HELPER_TEXT
      : POIZON_MANUAL_PRICE_HELPER_TEXT
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
      ? manualPoizonVariantChoice
        ? 'Цена появится после ручного ввода для кнопки Poizon'
        : 'Цена появится после ввода вручную'
      : 'Цена появится после выбора варианта'
    const needsExactPrice = Boolean(hasStartingPrice && !curPrice)
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
    const shouldShowOrderGuideStepFiveSizeTarget = shouldExposeOrderGuideStepFiveFocus
    const shouldShowOrderGuideStepFiveCtaTarget = shouldExposeOrderGuideStepFiveFocus
      && !isInCart
      && !cartAdding
    const ctaNote = manualPoizonVariantChoice && missingManualPrice
        ? 'Укажите цену в юанях для варианта с кнопкой Poizon, чтобы получить расчёт и добавить товар в корзину.'
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
      <>
        <div className="calc-page calc-page--filled buyer-page buyer-page--calculator">
        <button className="calc-back pressable" onClick={handleBack}>
          <IconArrowLeft size={20} />
        </button>

        <div ref={productScrollRef} className="calc-scroll">
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
              {product.brand ? (
                <div className="calc-result__summary-meta">
                  <span className="cp-info__brand">{product.brand}</span>
                </div>
              ) : null}

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
                  <span>
                    {product.price_is_starting ? 'Укажите точную цену в юанях (¥)' : 'Введите цену в юанях (¥)'}, {manualPriceHelperText}
                  </span>
                </label>
                <input ref={manualPriceInputRef} className="cp-manual__input" type="number" inputMode="decimal"
                  placeholder={product.price_is_starting ? 'например 1500 для выбранного варианта' : 'например 1500'}
                  value={manualPrice}
                  onChange={(e) => setManualPrice(e.target.value)} />
              </div>
            )}

          </section>

          {showVariantControls ? (
            <div className="cp-variants">
              {hasVariants ? (
                (product.variants || []).map((group, gi) => {
                  const opts = group.options || []
                  if (opts.length < 2) return null
                  const isSizeVariantGroup = SIZE_GROUP_NAMES.includes(String(group?.name || '').trim().toLowerCase())
                  return (
                    <div key={group.name} className="cv-group">
                      <div className="cv-group__label">{group.name}</div>
                      <div className="cv-group__list">
                        {opts.map((raw) => {
                          const name = typeof raw === 'string' ? raw : raw.name || String(raw)
                          const active = selVariants[group.name] === name
                          const avail = isOptionAvailable(group.name, name, gi)
                          const mp = avail ? getOptionPrice(group.name, name, gi) : null
                          const shouldHighlightStepFiveFocus = shouldShowOrderGuideStepFiveSizeTarget
                            && isSizeVariantGroup
                            && matchesOrderGuidePreferredSize(name)
                            && avail
                          return (
                            <button key={name}
                              className={`cv-chip pressable${active ? ' active' : ''}${!avail ? ' disabled' : ''}${mp != null ? ' has-price' : ''}`}
                              data-order-guide-step-five-target={shouldHighlightStepFiveFocus ? 'size' : undefined}
                              disabled={!avail}
                              onClick={() => {
                                if (!avail) return
                                haptic?.('light')
                                setAddedToCart(false)
                                addedCartUrlRef.current = null
                                setSavedCalcId(null)
                                setManualPoizonVariantChoice('')
                                setManualPrice('')
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
                })
              ) : null}

              {hasSizes ? (
                <div className="cv-group">
                  <div className="cv-group__label">Размер</div>
                  <div className="cv-group__list cv-group__list--sizes">
                    {(product.available_sizes || []).map((raw) => {
                      const name = typeof raw === 'string' ? raw : raw.name || String(raw)
                      const shouldHighlightStepFiveFocus = shouldShowOrderGuideStepFiveSizeTarget
                        && matchesOrderGuidePreferredSize(name)
                      return (
                        <button key={name}
                          className={`cv-size pressable${selSize === name ? ' active' : ''}${!canSelectStandaloneSizes ? ' disabled' : ''}`}
                          data-order-guide-step-five-target={shouldHighlightStepFiveFocus ? 'size' : undefined}
                          aria-disabled={!canSelectStandaloneSizes}
                          disabled={!canSelectStandaloneSizes}
                          style={!canSelectStandaloneSizes ? { opacity: 0.45, pointerEvents: 'none' } : undefined}
                          onClick={() => {
                            if (!canSelectStandaloneSizes) return
                            haptic?.('light')
                            setAddedToCart(false)
                            addedCartUrlRef.current = null
                            setSavedCalcId(null)
                            setManualPoizonVariantChoice('')
                            setManualPrice('')
                            setSelSize((p) => (p === name ? '' : name))
                          }}>
                          {name}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="cp-variants cp-variants--manual-choice">
            <PoizonManualChoiceHint className="cp-variants__manual-hint" />
            <PoizonManualVariantButton
              activeChoice={manualPoizonVariantChoice}
              onSelect={(choice) => {
                haptic?.('light')
                setAddedToCart(false)
                addedCartUrlRef.current = null
                setSavedCalcId(null)
                setManualPrice('')
                setSelVariants({})
                setSelSize('')
                pendingManualPriceScrollRef.current = choice !== manualPoizonVariantChoice
                setManualPoizonVariantChoice((currentValue) => (currentValue === choice ? '' : choice))
              }}
            />
          </div>

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

          {result && (
            <div className="calc-result__section">
              <section className="calc-result__meta ui-surface-panel">
                <p className="section-label">Доставка и курс</p>

                {result.exchange_rate && (
                  <div className="calc-result__meta-row">
                    <div className="calc-result__meta-copy">
                      <span>Курс</span>
                    </div>
                    <span className="calc-result__meta-value">{result.exchange_rate.cny_rub?.toFixed(2)} ₽/¥</span>
                  </div>
                )}

                {deliveryInfo.standard_days && (
                  <div className="calc-result__meta-row">
                    <span>Обычная доставка до Москвы</span>
                    <span className="calc-result__meta-value">{deliveryInfo.standard_days}</span>
                  </div>
                )}

                {deliveryInfo.express_days && (
                  <div className="calc-result__meta-row">
                    <span>Экспресс доставка до Москвы</span>
                    <span className="calc-result__meta-value">{deliveryInfo.express_days}</span>
                  </div>
                )}

                {deliveryInfo.cdek_days && (
                  <div className="calc-result__meta-row">
                    <div className="calc-result__meta-copy">
                      <span>СДЭК по России</span>
                    </div>
                    <span className="calc-result__meta-value">{deliveryInfo.cdek_days}</span>
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
            data-order-guide-step-five-target={shouldShowOrderGuideStepFiveCtaTarget ? 'cta' : undefined}
            onClick={handleAddToCart}
            disabled={!canAddToCart}
          >
            {cartAdding ? (
              <><span className="cp-actions__spinner" /> Добавляем</>
            ) : isInCart ? (
              <><IconCheck /> В корзине</>
            ) : (
              <><IconPlus /> В корзину</>
            )}
          </button>
        </div>
        </div>
        {orderGuideOverlay}
      </>
    )
  }

  return null
})

export default Calculator
