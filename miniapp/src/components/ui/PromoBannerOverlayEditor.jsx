import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { IconLink, IconPlus, IconSave } from './Icons.jsx'
import {
  blocksToMultilineText,
  getPromoBannerButtonThemeStyle,
  normalizePromoBannerButtonColor,
  PROMO_BANNER_BUTTON_COLORS,
} from '../../utils/promoBanners.js'
import './PromoBannerOverlay.css'
import './PromoBannerOverlayEditor.css'

const EDITOR_TOOLBAR_ITEMS = [
  { type: 'heading', token: 'H1', label: 'Заголовок', mode: 'style' },
  { type: 'subheading', token: 'H2', label: 'Подзаголовок', mode: 'style' },
  { type: 'text', token: 'Aa', label: 'Текст', mode: 'style' },
  { type: 'list', token: '::', label: 'Список', mode: 'style' },
  { type: 'image', token: '+', label: 'Фото', mode: 'insert' },
  { type: 'button', token: 'Go', label: 'Кнопка', mode: 'insert' },
]

function OverlayPortal({ children }) {
  if (typeof document === 'undefined') {
    return children
  }

  return createPortal(children, document.body)
}

function toEditableString(value = '') {
  return value == null ? '' : String(value)
}

function normalizeDraftItems(value) {
  if (typeof value === 'string') {
    return value.split('\n')
  }

  if (!Array.isArray(value)) {
    return []
  }

  return value.map((item) => toEditableString(item))
}

function normalizeDraftBlock(rawBlock, index) {
  const block = rawBlock && typeof rawBlock === 'object' ? rawBlock : {}
  const type = toEditableString(block.type).toLowerCase()
  const id = toEditableString(block.id) || `block-${index + 1}`

  if (type === 'image') {
    return {
      id,
      type: 'image',
      image_url: toEditableString(block.image_url),
      alt_text: toEditableString(block.alt_text),
      caption: toEditableString(block.caption),
    }
  }

  if (type === 'list') {
    return {
      id,
      type: 'list',
      items: normalizeDraftItems(block.items),
    }
  }

  if (type === 'button') {
    return {
      id,
      type: 'button',
      button_label: toEditableString(block.button_label),
      button_url: toEditableString(block.button_url),
      button_color: normalizePromoBannerButtonColor(block.button_color),
    }
  }

  if (type === 'heading' || type === 'subheading' || type === 'text') {
    return {
      id,
      type,
      text: toEditableString(block.text),
    }
  }

  return null
}

function normalizeDraftBanner(rawBanner = {}) {
  const banner = rawBanner && typeof rawBanner === 'object' ? rawBanner : {}
  const storyImageUrl = toEditableString(banner.story_image_url)
  const blocks = (Array.isArray(banner.blocks) ? banner.blocks : [])
    .map((block, index) => normalizeDraftBlock(block, index))
    .filter(Boolean)
  const primaryButtonBlock = blocks.find((block) => block.type === 'button') || null
  const buttonUrl = toEditableString(primaryButtonBlock?.button_url || banner.button_url)
  const buttonLabel = toEditableString(primaryButtonBlock?.button_label || banner.button_label)
  const buttonColor = normalizePromoBannerButtonColor(
    banner.button_color || primaryButtonBlock?.button_color,
  )

  return {
    id: Number(banner.id) || 0,
    label: toEditableString(banner.label),
    title: toEditableString(banner.title),
    subtitle: toEditableString(banner.subtitle),
    button_label: buttonLabel,
    button_url: buttonUrl,
    button_color: buttonColor,
    image_url: toEditableString(banner.image_url),
    image_alt: toEditableString(banner.image_alt),
    story_image_url: storyImageUrl,
    story_image_alt: storyImageUrl ? toEditableString(banner.story_image_alt) : '',
    show_on_entry: Boolean(banner.show_on_entry),
    blocks,
  }
}

function AutoGrowTextarea({
  value,
  onChange,
  onKeyDown = null,
  onBeforeInput = null,
  className,
  placeholder,
  minRows = 1,
  autoFocus = false,
  onFocus = null,
  onBlur = null,
  setInputRef = null,
  enterKeyHint = 'enter',
}) {
  const textareaRef = useRef(null)

  const handleRef = (node) => {
    textareaRef.current = node
    if (typeof setInputRef === 'function') {
      setInputRef(node)
    }
  }

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = '0px'
    element.style.height = `${element.scrollHeight}px`
  }, [value])

  useEffect(() => {
    if (autoFocus) {
      textareaRef.current?.focus()
    }
  }, [autoFocus])

  return (
    <textarea
      ref={handleRef}
      rows={minRows}
      value={value}
      placeholder={placeholder}
      className={className}
      enterKeyHint={enterKeyHint}
      onChange={onChange}
      onKeyDown={onKeyDown || undefined}
      onBeforeInput={onBeforeInput || undefined}
      onFocus={onFocus || undefined}
      onBlur={onBlur || undefined}
    />
  )
}

function isBlockEmpty(block) {
  if (!block) return true

  if (block.type === 'image') {
    return !String(block.image_url || '').trim() && !String(block.caption || '').trim()
  }

  if (block.type === 'list') {
    return !blocksToMultilineText(block.items).trim()
  }

  if (block.type === 'button') {
    return !String(block.button_label || '').trim() && !String(block.button_url || '').trim()
  }

  return !String(block.text || '').trim()
}

function getResolvedComposeType(composeType = '') {
  return composeType && composeType !== 'text' ? composeType : 'text'
}

function getEmptyBlockPatch(type = 'text') {
  if (type === 'heading') {
    return {
      type: 'heading',
      text: '',
      items: [],
      image_url: '',
      alt_text: '',
      caption: '',
    }
  }

  if (type === 'subheading') {
    return {
      type: 'subheading',
      text: '',
      items: [],
      image_url: '',
      alt_text: '',
      caption: '',
    }
  }

  if (type === 'list') {
    return {
      type: 'list',
      text: '',
      items: [],
      image_url: '',
      alt_text: '',
      caption: '',
      button_label: '',
      button_url: '',
      button_color: normalizePromoBannerButtonColor(''),
    }
  }

  return {
    type: 'text',
    text: '',
    items: [],
    image_url: '',
    alt_text: '',
    caption: '',
    button_label: '',
    button_url: '',
    button_color: normalizePromoBannerButtonColor(''),
  }
}

function buildStyledBlockPatch(block, nextType) {
  if (!block || block.type === 'image' || block.type === 'button') {
    return null
  }

  const resolvedType = getResolvedComposeType(nextType)
  const sourceText = block.type === 'list'
    ? blocksToMultilineText(block.items)
    : toEditableString(block.text)

  if (resolvedType === 'list') {
    return {
      type: 'list',
      text: '',
      items: sourceText ? [sourceText] : [],
      image_url: '',
      alt_text: '',
      caption: '',
      button_label: '',
      button_url: '',
      button_color: normalizePromoBannerButtonColor(''),
    }
  }

  return {
    type: resolvedType,
    text: sourceText,
    items: [],
    image_url: '',
    alt_text: '',
    caption: '',
    button_label: '',
    button_url: '',
    button_color: normalizePromoBannerButtonColor(''),
  }
}

function focusTextInput(node) {
  if (!node || typeof node.focus !== 'function') {
    return
  }

  node.focus({ preventScroll: true })

  if (typeof node.setSelectionRange === 'function') {
    const caretPosition = typeof node.value === 'string' ? node.value.length : 0
    node.setSelectionRange(caretPosition, caretPosition)
  }
}

function normalizeListEditorItems(items = []) {
  if (!Array.isArray(items) || items.length === 0) {
    return ['']
  }

  return items.map((item) => toEditableString(item))
}

function EditableBlock({
  block,
  themeColor,
  isActive,
  autoFocus,
  onSelect,
  onUpdate,
  onSplitBlock,
  onDeleteEmptyBlock,
  onRequestImageUpload,
  uploadingTarget,
  onRegisterInputRef,
}) {
  const lastSplitAtRef = useRef(0)
  const listInputRefsRef = useRef(new Map())
  const activeListInputIndexRef = useRef(0)
  const pendingListFocusRef = useRef(null)
  const listItems = normalizeListEditorItems(block.items)

  const handleLineBreak = (event) => {
    const now = Date.now()
    if (now - lastSplitAtRef.current < 48) {
      event.preventDefault()
      return true
    }

    lastSplitAtRef.current = now
    event.preventDefault()
    onSplitBlock?.(block.id)
    return true
  }

  const handleBeforeInput = (event) => {
    if (event.nativeEvent?.isComposing) {
      return
    }

    if (event.nativeEvent?.inputType === 'insertLineBreak') {
      handleLineBreak(event)
    }
  }

  const handleKeyDown = (event) => {
    if (event.nativeEvent?.isComposing) {
      return
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      if (handleLineBreak(event)) {
        return
      }
    }

    if (event.key === 'Backspace') {
      const input = event.currentTarget
      const isAtStart = input.selectionStart === 0 && input.selectionEnd === 0

      if (isAtStart && isBlockEmpty(block)) {
        event.preventDefault()
        onDeleteEmptyBlock?.(block.id)
      }
    }
  }

  useEffect(() => {
    if (block.type !== 'list' || typeof window === 'undefined') {
      return undefined
    }

    const pendingFocus = pendingListFocusRef.current
    if (!pendingFocus) {
      return undefined
    }

    const nextInput = listInputRefsRef.current.get(pendingFocus.index)
    if (!nextInput) {
      return undefined
    }

    const frameId = window.requestAnimationFrame(() => {
      focusTextInput(nextInput)
      if (typeof nextInput.setSelectionRange === 'function') {
        nextInput.setSelectionRange(pendingFocus.caret, pendingFocus.caret)
      }
      onRegisterInputRef?.(block.id, nextInput)
      pendingListFocusRef.current = null
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [block.id, block.items, block.type, onRegisterInputRef])

  const handleSelect = () => {
    onSelect?.(block.id)
  }

  const handleClearImage = (event) => {
    event.stopPropagation()
    onUpdate?.(block.id, {
      image_url: '',
      alt_text: '',
      caption: '',
    })
  }

  const setInputRef = (node) => {
    onRegisterInputRef?.(block.id, node)
  }

  const setListInputRef = (itemIndex, node) => {
    if (node) {
      listInputRefsRef.current.set(itemIndex, node)

      if (activeListInputIndexRef.current === itemIndex) {
        onRegisterInputRef?.(block.id, node)
      }

      return
    }

    listInputRefsRef.current.delete(itemIndex)
  }

  const handleListItemFocus = (itemIndex) => {
    activeListInputIndexRef.current = itemIndex
    handleSelect()
    const input = listInputRefsRef.current.get(itemIndex)
    if (input) {
      onRegisterInputRef?.(block.id, input)
    }
  }

  const updateListItems = (nextItems, nextFocus = null) => {
    pendingListFocusRef.current = nextFocus
    onUpdate?.(block.id, { items: nextItems })
  }

  const handleListItemChange = (itemIndex, value) => {
    const nextItems = [...listItems]
    nextItems[itemIndex] = value
    updateListItems(nextItems)
  }

  const handleListItemLineBreak = (event, itemIndex) => {
    const input = event.currentTarget
    const currentValue = toEditableString(listItems[itemIndex])
    const selectionStart = Number(input?.selectionStart ?? currentValue.length)
    const selectionEnd = Number(input?.selectionEnd ?? selectionStart)
    const nextItems = [...listItems]
    const nextText = currentValue.slice(selectionEnd)

    nextItems[itemIndex] = currentValue.slice(0, selectionStart)
    event.preventDefault()
    updateListItems(nextItems)
    onSplitBlock?.(block.id, { text: nextText })
  }

  const handleListItemBeforeInput = (event, itemIndex) => {
    if (event.nativeEvent?.isComposing) {
      return
    }

    if (event.nativeEvent?.inputType === 'insertLineBreak') {
      handleListItemLineBreak(event, itemIndex)
    }
  }

  const handleListItemKeyDown = (event, itemIndex) => {
    if (event.nativeEvent?.isComposing) {
      return
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      handleListItemLineBreak(event, itemIndex)
      return
    }

    if (event.key !== 'Backspace') {
      return
    }

    const input = event.currentTarget
    const itemValue = toEditableString(listItems[itemIndex])
    const isAtStart = input.selectionStart === 0 && input.selectionEnd === 0

    if (!isAtStart || itemValue) {
      return
    }

    event.preventDefault()

    if (listItems.length === 1) {
      onDeleteEmptyBlock?.(block.id)
      return
    }

    const nextItems = [...listItems]
    nextItems.splice(itemIndex, 1)
    const nextIndex = Math.max(0, itemIndex - 1)
    activeListInputIndexRef.current = nextIndex
    updateListItems(nextItems, {
      index: nextIndex,
      caret: toEditableString(nextItems[nextIndex]).length,
    })
  }

  if (block.type === 'image') {
    return (
      <article
        className={`promo-banner-editor__block promo-banner-editor__block--image${isActive ? ' promo-banner-editor__block--active' : ''}`}
        onClick={handleSelect}
      >
        <div className="promo-banner-editor__image-shell">
          {block.image_url ? (
            <div className="promo-banner-story__media-frame promo-banner-editor__media-frame">
              <button
                type="button"
                className="promo-banner-editor__media-remove pressable"
                onClick={handleClearImage}
                aria-label="Удалить фото"
              >
                &times;
              </button>
              <img
                src={block.image_url}
                alt={block.alt_text || ''}
                className="promo-banner-editor__image-preview"
              />
            </div>
          ) : (
            <button
              type="button"
              className="promo-banner-editor__image-picker pressable"
              disabled={uploadingTarget === block.id}
              onClick={(event) => {
                event.stopPropagation()
                onRequestImageUpload?.(block.id)
              }}
            >
              <IconPlus size={16} />
              <span>Добавить фото</span>
            </button>
          )}

          {block.image_url ? (
            <div className="promo-banner-editor__image-meta">
            <button
              type="button"
              className="promo-banner-editor__image-upload pressable"
              onClick={(event) => {
                event.stopPropagation()
                onRequestImageUpload?.(block.id)
              }}
            >
              {uploadingTarget === block.id ? 'Загружаю...' : block.image_url ? 'Заменить фото' : 'Выбрать фото'}
            </button>

            <AutoGrowTextarea
              value={block.caption || ''}
              placeholder="Подпись под фото"
              minRows={1}
              className="promo-banner-editor__caption-input"
              setInputRef={setInputRef}
              onFocus={handleSelect}
              onBeforeInput={handleBeforeInput}
              onKeyDown={handleKeyDown}
              onChange={(event) => onUpdate?.(block.id, { caption: event.target.value })}
            />
            </div>
          ) : null}
        </div>
      </article>
    )
  }

  if (block.type === 'list') {
    return (
      <article
        className={`promo-banner-editor__block${isActive ? ' promo-banner-editor__block--active' : ''}`}
        onClick={handleSelect}
      >
        <ul className="promo-banner-story__list promo-banner-editor__list">
          {listItems.map((item, itemIndex) => (/*
          placeholder="Каждый пункт с новой строки"
            */
            <li key={`${block.id}-item-${itemIndex}`} className="promo-banner-editor__list-item">
              <AutoGrowTextarea
                value={item}
                placeholder="Новый пункт"
                minRows={1}
                autoFocus={autoFocus && itemIndex === 0}
                className="promo-banner-editor__text-input promo-banner-editor__text-input--list-item"
                setInputRef={(node) => setListInputRef(itemIndex, node)}
                onFocus={() => handleListItemFocus(itemIndex)}
                onBeforeInput={(event) => handleListItemBeforeInput(event, itemIndex)}
                onKeyDown={(event) => handleListItemKeyDown(event, itemIndex)}
                onChange={(event) => handleListItemChange(itemIndex, event.target.value)}
              />
            </li>
          ))}
        </ul>
      </article>
    )
  }

  if (block.type === 'button') {
    const buttonStyle = getPromoBannerButtonThemeStyle(themeColor || block.button_color)
    const buttonLabel = String(block.button_label || '').trim()

    return (
      <article
        className={`promo-banner-editor__block promo-banner-editor__block--button${isActive ? ' promo-banner-editor__block--active' : ''}`}
        onClick={handleSelect}
      >
        <div className="promo-banner-editor__button-shell">
          <div className="promo-banner-editor__action-shell">
            <button
              type="button"
              className="promo-banner-editor__media-remove promo-banner-editor__media-remove--action pressable"
              onClick={(event) => {
                event.stopPropagation()
                onDeleteEmptyBlock?.(block.id)
              }}
              aria-label="Удалить кнопку"
            >
              &times;
            </button>

            <button
              type="button"
              className="promo-banner-story__action promo-banner-editor__action-button pressable"
              style={buttonStyle}
              aria-disabled={!block.button_url}
              onClick={(event) => {
                event.preventDefault()
                event.stopPropagation()
                handleSelect()
              }}
            >
              <span className="promo-banner-story__action-shimmer" aria-hidden="true" />
              <span className="promo-banner-story__action-label">{buttonLabel || ' '}</span>
            </button>
          </div>

          <div className="promo-banner-editor__meta-panel promo-banner-editor__meta-panel--inline">
            <label className="promo-banner-editor__field promo-banner-editor__field--full">
              <span className="promo-banner-editor__field-label">Текст кнопки</span>
              <input
                className="promo-banner-editor__field-input"
                value={block.button_label || ''}
                placeholder="Подробнее"
                ref={setInputRef}
                autoFocus={autoFocus}
                onFocus={handleSelect}
                onBeforeInput={handleBeforeInput}
                onKeyDown={handleKeyDown}
                onChange={(event) => onUpdate?.(block.id, { button_label: event.target.value })}
              />
            </label>

            <label className="promo-banner-editor__field promo-banner-editor__field--full">
              <span className="promo-banner-editor__field-label">Ссылка кнопки</span>
              <div className="promo-banner-editor__field-wrap">
                <span className="promo-banner-editor__field-icon" aria-hidden="true"><IconLink size={15} /></span>
                <input
                  className="promo-banner-editor__field-input"
                  value={block.button_url || ''}
                  placeholder="https://..."
                  onFocus={(event) => {
                    handleSelect()
                    onRegisterInputRef?.(block.id, event.currentTarget)
                  }}
                  onBeforeInput={handleBeforeInput}
                  onKeyDown={handleKeyDown}
                  onChange={(event) => onUpdate?.(block.id, { button_url: event.target.value })}
                />
              </div>
            </label>
          </div>
        </div>
      </article>
    )
  }

  return (
    <article
      className={`promo-banner-editor__block${isActive ? ' promo-banner-editor__block--active' : ''}`}
      onClick={handleSelect}
    >
      <AutoGrowTextarea
        value={block.text || ''}
        placeholder={block.type === 'heading' ? 'Новый заголовок' : block.type === 'subheading' ? 'Новый подзаголовок' : 'Введите текст'}
        minRows={block.type === 'heading' ? 1 : 2}
        autoFocus={autoFocus}
        className={`promo-banner-editor__text-input promo-banner-editor__text-input--${block.type}`}
        setInputRef={setInputRef}
        onFocus={handleSelect}
        onBeforeInput={handleBeforeInput}
        onKeyDown={handleKeyDown}
        onChange={(event) => onUpdate?.(block.id, { text: event.target.value })}
      />
    </article>
  )
}

export default function PromoBannerOverlayEditor({
  open = false,
  banner = null,
  onClose = null,
  onSave = null,
  onChangeField = null,
  onInsertBlock = null,
  onUpdateBlock = null,
  onRemoveBlock = null,
  onRequestCoverImageUpload = null,
  onRequestBlockImageUpload = null,
  saving = false,
  uploadingTarget = '',
}) {
  const normalizedBanner = normalizeDraftBanner(banner)
  const [activeBlockId, setActiveBlockId] = useState('')
  const [focusBlockId, setFocusBlockId] = useState('')
  const [themesOpen, setThemesOpen] = useState(false)
  const [composerVisible, setComposerVisible] = useState(false)
  const [composeType, setComposeType] = useState('')
  const [keyboardOffset, setKeyboardOffset] = useState(0)
  const [shellHeight, setShellHeight] = useState(0)
  const shellRef = useRef(null)
  const baseViewportHeightRef = useRef(0)
  const blockInputRefsRef = useRef(new Map())
  const pendingFocusBlockIdRef = useRef('')
  const emptyDraftInitializedRef = useRef(false)

  const activeBlock = normalizedBanner.blocks.find((block) => block.id === activeBlockId) || null

  const registerBlockInputRef = (blockId, node) => {
    if (!blockId) return

    if (node) {
      blockInputRefsRef.current.set(blockId, node)
      return
    }

    blockInputRefsRef.current.delete(blockId)
  }

  const flushPendingBlockFocus = () => {
    if (!open || typeof window === 'undefined') {
      return
    }

    const pendingBlockId = pendingFocusBlockIdRef.current
    if (!pendingBlockId) {
      return
    }

    const nextInput = blockInputRefsRef.current.get(pendingBlockId)
    if (!nextInput) {
      return
    }

    window.requestAnimationFrame(() => {
      if (pendingFocusBlockIdRef.current !== pendingBlockId) {
        return
      }

      focusTextInput(nextInput)
      pendingFocusBlockIdRef.current = ''
    })
  }

  useEffect(() => {
    if (!open) return
    if (activeBlockId && normalizedBanner.blocks.some((block) => block.id === activeBlockId)) return
    setActiveBlockId(normalizedBanner.blocks[normalizedBanner.blocks.length - 1]?.id || '')
  }, [activeBlockId, normalizedBanner.blocks, open])

  useEffect(() => {
    if (!focusBlockId) return undefined
    const timeoutId = window.setTimeout(() => setFocusBlockId(''), 220)
    return () => window.clearTimeout(timeoutId)
  }, [focusBlockId])

  useEffect(() => {
    if (!open || typeof window === 'undefined') {
      return undefined
    }

    const pendingBlockId = pendingFocusBlockIdRef.current
    if (!pendingBlockId) {
      return undefined
    }

    const nextInput = blockInputRefsRef.current.get(pendingBlockId)
    if (!nextInput) {
      return undefined
    }

    const frameId = window.requestAnimationFrame(() => {
      if (pendingFocusBlockIdRef.current !== pendingBlockId) {
        return
      }

      focusTextInput(nextInput)
      pendingFocusBlockIdRef.current = ''
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [focusBlockId, normalizedBanner.blocks, open])

  useEffect(() => {
    if (!open) {
      setThemesOpen(false)
      setComposerVisible(false)
      setComposeType('')
      setKeyboardOffset(0)
      setShellHeight(0)
      baseViewportHeightRef.current = 0
      pendingFocusBlockIdRef.current = ''
      emptyDraftInitializedRef.current = false
      blockInputRefsRef.current.clear()
    }
  }, [open])

  useEffect(() => {
    if (!open || normalizedBanner.blocks.length > 0 || emptyDraftInitializedRef.current) {
      return
    }

    emptyDraftInitializedRef.current = true
    setComposeType('text')
    setThemesOpen(false)
    setComposerVisible(true)
    const nextBlockId = onInsertBlock?.({
      type: 'text',
      afterBlockId: '',
      empty: true,
    })

    if (nextBlockId) {
      focusBlock(nextBlockId)
    }
  }, [normalizedBanner.blocks.length, onInsertBlock, open])

  useEffect(() => {
    if (!activeBlock || activeBlock.type === 'image' || activeBlock.type === 'button') {
      return
    }

    const nextComposeType = getResolvedComposeType(activeBlock.type)
    setComposeType((currentValue) => (currentValue === nextComposeType ? currentValue : nextComposeType))
  }, [activeBlock])

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

  useEffect(() => {
    if (!open || typeof document === 'undefined') {
      return undefined
    }

    const viewportMeta = document.querySelector('meta[name="viewport"]')
    const originalViewportContent = viewportMeta?.getAttribute('content') || ''

    if (viewportMeta) {
      const nextViewportParts = originalViewportContent
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean)
        .filter((part) => !/^maximum-scale\s*=|^user-scalable\s*=/.test(part))

      viewportMeta.setAttribute('content', [...nextViewportParts, 'maximum-scale=1', 'user-scalable=no'].join(', '))
    }

    let lastTouchEndAt = 0

    const preventGestureZoom = (event) => {
      event.preventDefault()
    }

    const preventPinchZoom = (event) => {
      if (event.touches?.length > 1) {
        event.preventDefault()
      }
    }

    const preventDoubleTapZoom = (event) => {
      const now = Date.now()
      if (now - lastTouchEndAt < 320) {
        event.preventDefault()
      }
      lastTouchEndAt = now
    }

    document.addEventListener('gesturestart', preventGestureZoom)
    document.addEventListener('gesturechange', preventGestureZoom)
    document.addEventListener('gestureend', preventGestureZoom)
    document.addEventListener('touchmove', preventPinchZoom, { passive: false })
    document.addEventListener('touchend', preventDoubleTapZoom, { passive: false })

    return () => {
      if (viewportMeta) {
        viewportMeta.setAttribute('content', originalViewportContent)
      }

      document.removeEventListener('gesturestart', preventGestureZoom)
      document.removeEventListener('gesturechange', preventGestureZoom)
      document.removeEventListener('gestureend', preventGestureZoom)
      document.removeEventListener('touchmove', preventPinchZoom)
      document.removeEventListener('touchend', preventDoubleTapZoom)
    }
  }, [open])

  useEffect(() => {
    if (!open || typeof window === 'undefined') {
      return undefined
    }

    const viewport = window.visualViewport

    const readViewportMetrics = () => {
      const height = Math.round(viewport?.height || window.innerHeight || document.documentElement.clientHeight || 0)
      const offsetTop = Math.round(viewport?.offsetTop || 0)
      return { height, offsetTop }
    }

    const syncViewportMetrics = () => {
      const { height, offsetTop } = readViewportMetrics()

      if (!baseViewportHeightRef.current || height >= baseViewportHeightRef.current - 56) {
        baseViewportHeightRef.current = height
      }

      const nextShellHeight = baseViewportHeightRef.current || height
      const nextKeyboardOffset = Math.max(0, nextShellHeight - height - offsetTop)

      setShellHeight(nextShellHeight)
      setKeyboardOffset(nextKeyboardOffset > 72 ? nextKeyboardOffset : 0)
    }

    syncViewportMetrics()

    viewport?.addEventListener('resize', syncViewportMetrics)
    viewport?.addEventListener('scroll', syncViewportMetrics)
    window.addEventListener('resize', syncViewportMetrics)

    return () => {
      viewport?.removeEventListener('resize', syncViewportMetrics)
      viewport?.removeEventListener('scroll', syncViewportMetrics)
      window.removeEventListener('resize', syncViewportMetrics)
    }
  }, [open])

  const focusBlock = (blockId) => {
    if (!blockId) return
    pendingFocusBlockIdRef.current = blockId
    setActiveBlockId(blockId)
    setFocusBlockId(blockId)
    setComposerVisible(true)
    flushPendingBlockFocus()
  }

  const ensureComposeTarget = (nextComposeType) => {
    const resolvedType = getResolvedComposeType(nextComposeType)

    if (activeBlock && activeBlock.type !== 'image' && activeBlock.type !== 'button') {
      const nextPatch = isBlockEmpty(activeBlock)
        ? getEmptyBlockPatch(resolvedType)
        : buildStyledBlockPatch(activeBlock, resolvedType)

      if (nextPatch) {
        onUpdateBlock?.(activeBlock.id, nextPatch)
      }

      focusBlock(activeBlock.id)
      return
    }

    if (activeBlock?.type === 'image' || activeBlock?.type === 'button') {
      const nextBlockId = onInsertBlock?.({
        type: resolvedType,
        afterBlockId: activeBlock.id,
        empty: true,
      })

      focusBlock(nextBlockId)
      return
    }

    if (!activeBlock) {
      const nextBlockId = onInsertBlock?.({
        type: resolvedType,
        afterBlockId: '',
        empty: true,
      })

      focusBlock(nextBlockId)
    }
  }

  const handleComposeSelect = (type) => {
    const nextComposeType = getResolvedComposeType(type)
    setComposeType(nextComposeType)
    setThemesOpen(false)
    ensureComposeTarget(nextComposeType)
  }

  const handleInsertBlockType = (type) => {
    setThemesOpen(false)
    const nextBlockId = onInsertBlock?.({
      type,
      afterBlockId: activeBlockId,
      empty: true,
    })

    if (nextBlockId) {
      focusBlock(nextBlockId)
    }
  }

  const handleSplitBlock = (blockId, nextBlockPatch = null) => {
    const nextBlockId = onInsertBlock?.({
      type: 'text',
      afterBlockId: blockId,
      empty: true,
    })

    setComposeType('text')

    if (nextBlockId && nextBlockPatch && typeof onUpdateBlock === 'function') {
      onUpdateBlock(nextBlockId, nextBlockPatch)
    }

    focusBlock(nextBlockId)
    setThemesOpen(false)
  }

  const handleDeleteEmptyBlock = (blockId) => {
    const blockIndex = normalizedBanner.blocks.findIndex((block) => block.id === blockId)
    if (blockIndex < 0) return

    const previousTextBlock = [...normalizedBanner.blocks.slice(0, blockIndex)]
      .reverse()
      .find((block) => block.type !== 'image' && block.type !== 'button')
    const nextTextBlock = normalizedBanner.blocks
      .slice(blockIndex + 1)
      .find((block) => block.type !== 'image' && block.type !== 'button')
    const previousBlock = normalizedBanner.blocks[blockIndex - 1] || null
    const nextBlock = normalizedBanner.blocks[blockIndex + 1] || null
    const focusCandidate = previousTextBlock || nextTextBlock || null

    onRemoveBlock?.(blockId)
    setActiveBlockId(focusCandidate?.id || previousBlock?.id || nextBlock?.id || '')

    if (focusCandidate?.id) {
      setFocusBlockId(focusCandidate.id)
    }
  }

  const handleEditorFocusCapture = () => {
    setComposerVisible(true)
  }

  const handleEditorBlurCapture = () => {
    window.setTimeout(() => {
      if (shellRef.current?.contains(document.activeElement)) {
        return
      }

      setComposerVisible(false)
      setThemesOpen(false)
    }, 0)
  }

  const handleToolbarPointerDown = (event) => {
    event.preventDefault()
  }

  const displayName = String(normalizedBanner.title || normalizedBanner.label || '').trim() || 'Промо-баннер'
  const actionStyle = getPromoBannerButtonThemeStyle(normalizedBanner)
  const hasStoryCover = Boolean(String(normalizedBanner.story_image_url || '').trim())
  const handleClearCoverImage = () => {
    onChangeField?.('story_image_url', '')
    onChangeField?.('story_image_alt', '')
  }
  const shellStyle = {
    '--promo-editor-keyboard-offset': `${keyboardOffset}px`,
    '--promo-editor-shell-height': shellHeight ? `${shellHeight}px` : '100vh',
    '--promo-editor-dock-reserve': themesOpen ? '188px' : '128px',
  }

  return (
    <AnimatePresence>
      {open ? (
        <OverlayPortal>
          <motion.div
            className="promo-banner-overlay promo-banner-overlay--editor"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            onClick={() => onClose?.()}
          >
            <motion.div
              ref={shellRef}
              className="promo-banner-overlay__shell promo-banner-overlay__shell--editor"
              data-shell-swipe-block="true"
              style={shellStyle}
              initial={{ opacity: 0, scale: 0.988 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.992 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              onClick={(event) => event.stopPropagation()}
              onFocusCapture={handleEditorFocusCapture}
              onBlurCapture={handleEditorBlurCapture}
              role="dialog"
              aria-modal="true"
              aria-label={displayName}
            >
              <div
                className="promo-banner-story promo-banner-story--editor"
                style={actionStyle}
                data-shell-swipe-block="true"
              >
                <div className="promo-banner-editor__top-actions">
                  <button
                    type="button"
                    className="promo-banner-story__close promo-banner-story__close--editor promo-banner-editor__top-action promo-banner-editor__top-action--save pressable"
                    onClick={() => onSave?.()}
                    aria-label="Сохранить баннер"
                    title="Сохранить баннер"
                    disabled={saving}
                  >
                    <IconSave size={16} />
                  </button>

                  <button
                    type="button"
                    className="promo-banner-story__close promo-banner-story__close--editor promo-banner-editor__top-action pressable"
                    onClick={onClose}
                    aria-label="Закрыть редактор баннера"
                  >
                    &times;
                  </button>
                </div>

                <div className="promo-banner-story__scroll promo-banner-story__scroll--editor" data-shell-swipe-block="true">
                  <div className="promo-banner-editor__frame">
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

                      {hasStoryCover ? (
                        <div className="promo-banner-editor__cover-shell">
                            <div className="promo-banner-story__cover-wrap promo-banner-editor__cover-wrap">
                              <button
                                type="button"
                                className="promo-banner-editor__media-remove promo-banner-editor__media-remove--cover pressable"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  handleClearCoverImage()
                                }}
                                aria-label="Удалить обложку"
                              >
                                &times;
                              </button>
                              <img
                                className="promo-banner-story__cover"
                                src={normalizedBanner.story_image_url}
                                alt={normalizedBanner.story_image_alt || normalizedBanner.title || ''}
                                loading="eager"
                              />
                            </div>
                            <button
                              type="button"
                              className="promo-banner-editor__image-upload pressable"
                              disabled={uploadingTarget === 'story-cover'}
                              onClick={(event) => {
                                event.stopPropagation()
                                onRequestCoverImageUpload?.()
                              }}
                            >
                              {uploadingTarget === 'story-cover' ? 'Загружаю...' : 'Заменить фото'}
                            </button>
                        </div>
                      ) : (
                          <button
                            type="button"
                            className="promo-banner-editor__image-picker promo-banner-editor__cover-picker pressable"
                            disabled={uploadingTarget === 'story-cover'}
                            onClick={(event) => {
                              event.stopPropagation()
                              onRequestCoverImageUpload?.()
                            }}
                          >
                            <IconPlus size={18} />
                            <span>{uploadingTarget === 'story-cover' ? 'Загружаю...' : 'Добавить фото'}</span>
                          </button>
                        )}
                    </div>

                    <div className="promo-banner-story__content promo-banner-editor__content">
                      {normalizedBanner.blocks.length ? (
                        normalizedBanner.blocks.map((block) => (
                          <EditableBlock
                            key={block.id}
                            block={block}
                            themeColor={normalizedBanner.button_color}
                            isActive={block.id === activeBlockId}
                            autoFocus={focusBlockId === block.id}
                            uploadingTarget={uploadingTarget}
                            onSelect={setActiveBlockId}
                            onUpdate={onUpdateBlock}
                            onSplitBlock={handleSplitBlock}
                            onDeleteEmptyBlock={handleDeleteEmptyBlock}
                            onRequestImageUpload={onRequestBlockImageUpload}
                            onRegisterInputRef={registerBlockInputRef}
                          />
                        ))
                      ) : (
                        <div
                          className="promo-banner-editor__empty"
                          onClick={() => handleComposeSelect('text')}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              handleComposeSelect('text')
                            }
                          }}
                          role="button"
                          tabIndex={0}
                        >
                          <strong>Нажмите, чтобы начать писать</strong>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className={`promo-banner-editor__dock${composerVisible ? ' promo-banner-editor__dock--visible' : ''}`} data-shell-swipe-block="true">
                  <div className="promo-banner-editor__dock-inner">
                    {themesOpen && composerVisible ? (
                      <div className="promo-banner-editor__meta-panel promo-banner-editor__meta-panel--themes">
                        <div className="promo-banner-editor__color-grid promo-banner-editor__color-grid--themes" role="radiogroup" aria-label="Темы popup">
                          {PROMO_BANNER_BUTTON_COLORS.map((option) => {
                            const isSelected = normalizedBanner.button_color === option.value

                            return (
                              <button
                                key={option.value}
                                type="button"
                                className={`promo-banner-editor__color-chip promo-banner-editor__color-chip--theme pressable${isSelected ? ' promo-banner-editor__color-chip--active' : ''}`}
                                style={{
                                  '--promo-button-chip-gradient': option.chipGradient,
                                  '--promo-button-chip-glow': option.chipGlow,
                                }}
                                onPointerDown={handleToolbarPointerDown}
                                onClick={() => onChangeField?.('button_color', option.value)}
                                role="radio"
                                aria-checked={isSelected}
                                aria-label={option.label}
                                title={option.label}
                              >
                                <span className="promo-banner-editor__color-swatch" aria-hidden="true" />
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ) : null}

                    <div className="promo-banner-editor__toolbar" role="toolbar" aria-label="Режимы редактирования popup">
                      {EDITOR_TOOLBAR_ITEMS.map((item) => {
                        const isActive = item.mode === 'style' ? composeType === item.type : false

                        return (
                          <button
                            key={item.type}
                            type="button"
                            className={`promo-banner-editor__toolbar-button pressable${isActive ? ' promo-banner-editor__toolbar-button--active' : ''}`}
                            onPointerDown={handleToolbarPointerDown}
                            onClick={() => {
                              if (item.mode === 'insert') {
                                handleInsertBlockType(item.type)
                                return
                              }

                              handleComposeSelect(item.type)
                            }}
                          >
                            <span className="promo-banner-editor__toolbar-token" aria-hidden="true">{item.token}</span>
                            <span className="promo-banner-editor__toolbar-label">{item.label}</span>
                          </button>
                        )
                      })}

                      <button
                        type="button"
                        className={`promo-banner-editor__toolbar-button promo-banner-editor__toolbar-button--meta pressable${themesOpen ? ' promo-banner-editor__toolbar-button--active' : ''}`}
                        onPointerDown={handleToolbarPointerDown}
                        onClick={() => {
                          setThemesOpen((currentValue) => !currentValue)
                          setComposerVisible(true)
                        }}
                      >
                        <span className="promo-banner-editor__toolbar-token promo-banner-editor__toolbar-token--icon" aria-hidden="true">Fx</span>
                        <span className="promo-banner-editor__toolbar-label">Темы</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </OverlayPortal>
      ) : null}
    </AnimatePresence>
  )
}
