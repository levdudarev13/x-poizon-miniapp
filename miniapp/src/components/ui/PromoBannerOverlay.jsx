import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  getPromoBannerButtonThemeStyle,
  getPromoBannerContentBlocks,
  getPromoBannerDisplayName,
  normalizePromoBanner,
} from '../../utils/promoBanners.js'
import './PromoBannerOverlay.css'

function PromoBannerBlocks({ blocks = [], themeColor = '', onAction = null, actionDisabled = false }) {
  return blocks.map((block) => {
    if (block.type === 'heading') {
      return (
        <h3 key={block.id} className="promo-banner-story__block promo-banner-story__block--heading">
          {block.text}
        </h3>
      )
    }

    if (block.type === 'subheading') {
      return (
        <p key={block.id} className="promo-banner-story__block promo-banner-story__block--subheading">
          {block.text}
        </p>
      )
    }

    if (block.type === 'list') {
      return (
        <ul key={block.id} className="promo-banner-story__block promo-banner-story__list">
          {block.items.map((item, index) => (
            <li key={`${block.id}-${index}`}>{item}</li>
          ))}
        </ul>
      )
    }

    if (block.type === 'image') {
      return (
        <figure key={block.id} className="promo-banner-story__media">
          <div className="promo-banner-story__media-frame">
            <img
              src={block.image_url}
              alt={block.alt_text || ''}
              className="promo-banner-story__media-image"
              loading="lazy"
            />
          </div>
          {block.caption ? (
            <figcaption className="promo-banner-story__media-caption">{block.caption}</figcaption>
          ) : null}
        </figure>
      )
    }

    if (block.type === 'button') {
      const buttonStyle = getPromoBannerButtonThemeStyle(themeColor || block.button_color)
      const buttonLabel = String(block.button_label || '').trim()

      return (
        <div key={block.id} className="promo-banner-story__action-wrap promo-banner-story__action-wrap--inline">
          <button
            type="button"
            className="promo-banner-story__action pressable"
            style={buttonStyle}
            onClick={() => onAction?.(block.button_url, block)}
            disabled={actionDisabled || !block.button_url}
          >
            <span className="promo-banner-story__action-shimmer" aria-hidden="true" />
            <span className="promo-banner-story__action-label">{buttonLabel || ' '}</span>
          </button>
        </div>
      )
    }

    return (
      <p key={block.id} className="promo-banner-story__block promo-banner-story__block--text">
        {block.text}
      </p>
    )
  })
}

function PromoBannerOverlayPortal({ children }) {
  if (typeof document === 'undefined') {
    return children
  }

  return createPortal(children, document.body)
}

export function PromoBannerStory({
  banner = null,
  onClose = null,
  onAction = null,
  preview = false,
  actionDisabled = false,
}) {
  const normalizedBanner = normalizePromoBanner(banner)
  const contentBlocks = getPromoBannerContentBlocks(normalizedBanner)
  const actionStyle = getPromoBannerButtonThemeStyle(normalizedBanner)
  const displayName = getPromoBannerDisplayName(normalizedBanner)

  if (!normalizedBanner.story_image_url && contentBlocks.length === 0) {
    return null
  }

  return (
    <div
      className={`promo-banner-story${preview ? ' promo-banner-story--preview' : ''}`}
      style={actionStyle}
      data-shell-swipe-block={preview ? undefined : 'true'}
    >
      {typeof onClose === 'function' ? (
        <button
          type="button"
          className="promo-banner-story__close pressable"
          onClick={onClose}
          aria-label="Закрыть баннер"
        >
          &times;
        </button>
      ) : null}

      <div className="promo-banner-story__scroll" data-shell-swipe-block="true">
        <div className="promo-banner-story__frame">
          <div className="promo-banner-story__hero">
            <div className="promo-banner-story__brand-row">
              <div className="promo-banner-story__logo-wrap" aria-label={displayName}>
                <img
                  className="promo-banner-story__logo"
                  src="/101-popup.png"
                  alt={displayName || 'Logistics X'}
                  loading="eager"
                  fetchPriority="high"
                  decoding="sync"
                />
              </div>
            </div>

            {normalizedBanner.story_image_url ? (
              <div className="promo-banner-story__cover-wrap">
                <img
                  className="promo-banner-story__cover"
                  src={normalizedBanner.story_image_url}
                  alt={normalizedBanner.story_image_alt || normalizedBanner.title || ''}
                  loading="eager"
                />
              </div>
            ) : null}
          </div>

          <div className="promo-banner-story__content">
            <PromoBannerBlocks
              blocks={contentBlocks}
              themeColor={normalizedBanner.button_color}
              onAction={onAction}
              actionDisabled={actionDisabled}
            />
          </div>
        </div>
      </div>

    </div>
  )
}

export default function PromoBannerOverlay({
  open = false,
  banner = null,
  onClose = null,
  onAction = null,
}) {
  useEffect(() => {
    if (!open || typeof onClose !== 'function') {
      return undefined
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose, open])

  return (
    <AnimatePresence>
      {open ? (
        <PromoBannerOverlayPortal>
          <motion.div
            className="promo-banner-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            onClick={() => onClose?.()}
          >
            <motion.div
              className="promo-banner-overlay__shell"
              data-shell-swipe-block="true"
              initial={{ opacity: 0, y: 28, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 24, scale: 0.985 }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              onClick={(event) => event.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-label={getPromoBannerDisplayName(banner)}
            >
              <PromoBannerStory banner={banner} onClose={onClose} onAction={onAction} />
            </motion.div>
          </motion.div>
        </PromoBannerOverlayPortal>
      ) : null}
    </AnimatePresence>
  )
}
