import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  deleteAdminBanner,
  fetchAdminBanners,
  saveAdminBanner,
  uploadAdminBannerImage,
} from '../../../api/admin.js'
import PromoBannerOverlay from '../../../components/ui/PromoBannerOverlay.jsx'
import PromoBannerOverlayEditor from '../../../components/ui/PromoBannerOverlayEditor.jsx'
import {
  IconPackage,
  IconPlus,
  IconTrash,
} from '../../../components/ui/Icons.jsx'
import { ADMIN_MOTION } from '../adminShared.js'
import { AdminBackIcon } from './AdminSharedBits.jsx'
import { AdminSectionShell } from './AdminSectionShell.jsx'
import {
  PROMO_BANNER_RECOMMENDED_FORMAT,
  createPromoBannerBlock,
  createPromoBannerDraft,
  normalizePromoBanner,
  normalizePromoBannerBlocks,
  normalizePromoBannerButtonColor,
} from '../../../utils/promoBanners.js'

const SCREEN_ENTRY = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: ADMIN_MOTION.standard,
}

function getBannerRequestMessage(requestError, fallbackMessage) {
  const message = String(requestError?.message || '').trim()

  if (message === 'banner label is required') return 'Добавьте короткий label баннера для карусели.'
  if (message === 'banner title is required') return 'Укажите основной заголовок баннера.'
  if (message === 'banner image is required') return 'Загрузите обложку баннера.'
  if (message === 'banner limit reached') return 'Достигнут лимит баннеров. Удалите один из существующих.'
  if (message === 'banner not found') return 'Этот баннер уже удалён или не найден на сервере.'
  if (message === 'Not found') return 'Маршрут баннеров не найден. Перезапустите miniapp server и обновите Telegram WebApp.'
  return message || fallbackMessage
}

function getBannerUploadErrorMessage(requestError) {
  const message = String(requestError?.message || '').trim()

  if (message === 'unsupported_image_format') return 'Не удалось обработать фото. Выберите изображение ещё раз.'
  if (message === 'invalid_image_data') return 'Не удалось прочитать изображение. Выберите файл ещё раз.'
  if (message === 'image_too_large') return 'После конвертации файл всё ещё слишком большой.'
  return getBannerRequestMessage(requestError, 'Не удалось загрузить изображение.')
}

function moveItem(items, fromIndex, toIndex) {
  const nextItems = Array.isArray(items) ? [...items] : []
  if (fromIndex < 0 || toIndex < 0 || fromIndex >= nextItems.length || toIndex >= nextItems.length) {
    return nextItems
  }

  const [item] = nextItems.splice(fromIndex, 1)
  nextItems.splice(toIndex, 0, item)
  return nextItems
}

function readImageFileAsDataUrl(file) {
  if (!(file instanceof File)) {
    return Promise.reject(new Error('Файл не найден'))
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = String(reader.result || '')
      if (!dataUrl.startsWith('data:image/')) {
        reject(new Error('Не удалось прочитать изображение'))
        return
      }

      resolve({
        dataUrl,
      })
    }
    reader.onerror = () => reject(new Error('Не удалось прочитать изображение'))
    reader.readAsDataURL(file)
  })
}

async function encodeImageFileAsDataUrl(
  file,
  {
    maxWidth = 1320,
    maxHeight = 480,
    quality = 0.9,
    mimeTypes = ['image/webp', 'image/jpeg', 'image/png'],
  } = {},
) {
  if (!(file instanceof File)) {
    return Promise.reject(new Error('Файл не найден'))
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

    for (const mimeType of mimeTypes) {
      const dataUrl = canvas.toDataURL(mimeType, quality)
      if (dataUrl.startsWith(`data:${mimeType};base64,`)) {
        return {
          dataUrl,
          width: targetWidth,
          height: targetHeight,
        }
      }
    }

    throw new Error('Не удалось преобразовать изображение')
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}

function normalizePayloadItems(payload) {
  return (Array.isArray(payload?.items) ? payload.items : []).map((item) => normalizePromoBanner(item))
}

function getDraftLegacyFields(blocks = [], fallbackButtonColor = '') {
  const normalizedBlocks = Array.isArray(blocks) ? blocks : []
  const headingBlock = normalizedBlocks.find((block) => block?.type === 'heading') || null
  const subheadingBlock = normalizedBlocks.find((block) => block?.type === 'subheading') || null
  const buttonBlock = normalizedBlocks.find((block) => block?.type === 'button') || null

  return {
    title: String(headingBlock?.text || '').trim(),
    subtitle: String(subheadingBlock?.text || '').trim(),
    button_label: String(buttonBlock?.button_label || '').trim(),
    button_url: String(buttonBlock?.button_url || '').trim(),
    button_color: String(buttonBlock?.button_color || fallbackButtonColor || '').trim(),
  }
}

function buildPersistedBannerDraft(sourceDraft = {}) {
  const draft = sourceDraft && typeof sourceDraft === 'object' ? sourceDraft : {}
  const normalizedBlocks = normalizePromoBannerBlocks(draft.blocks)
  const legacyFields = getDraftLegacyFields(normalizedBlocks, draft.button_color)
  const resolvedTitle = legacyFields.title
  const resolvedLabel = resolvedTitle
  const resolvedImageAlt = resolvedTitle || resolvedLabel

  return {
    ...draft,
    label: resolvedLabel,
    title: resolvedTitle,
    subtitle: legacyFields.subtitle,
    button_label: legacyFields.button_label,
    button_url: legacyFields.button_url,
    button_color: legacyFields.button_color,
    image_alt: resolvedImageAlt,
    story_image_alt: draft.story_image_url ? resolvedImageAlt : '',
    blocks: normalizedBlocks,
  }
}

export function AdminBanners({ initData, onBack, haptic }) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploadingTarget, setUploadingTarget] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(null)
  const [payload, setPayload] = useState(null)
  const [view, setView] = useState('catalog')
  const [selectedBannerId, setSelectedBannerId] = useState(0)
  const [draft, setDraft] = useState(() => createPromoBannerDraft())
  const [previewBanner, setPreviewBanner] = useState(null)
  const [editorPreviewOpen, setEditorPreviewOpen] = useState(false)

  const mainCoverInputRef = useRef(null)
  const storyCoverInputRef = useRef(null)
  const blockInputRef = useRef(null)
  const blockUploadTargetRef = useRef('')
  const viewRef = useRef(view)
  const selectedBannerIdRef = useRef(selectedBannerId)

  const items = normalizePayloadItems(payload)
  const limits = payload?.limits || {}
  const uploadConfig = payload?.upload || {}
  const canCreateBanner = items.length < Number(limits.max_banners || 12)
  const coverSizeLabel = uploadConfig.cover_size || `${PROMO_BANNER_RECOMMENDED_FORMAT.cover.width} x ${PROMO_BANNER_RECOMMENDED_FORMAT.cover.height}`
  const persistedDraft = buildPersistedBannerDraft(draft)
  const resolvedDraftLabel = persistedDraft.label
  const resolvedDraftTitle = persistedDraft.title
  const resolvedDraftImageAlt = persistedDraft.image_alt
  const editorDraftBanner = {
    ...persistedDraft,
    blocks: Array.isArray(draft.blocks) ? draft.blocks : [],
  }
  const isEditorView = view === 'editor'

  useEffect(() => {
    viewRef.current = view
    selectedBannerIdRef.current = selectedBannerId
  }, [selectedBannerId, view])

  const applyPayload = useCallback((nextPayload, { preferredBannerId = 0, syncDraft = true } = {}) => {
    const nextItems = normalizePayloadItems(nextPayload)
    const selectedId = Number(preferredBannerId || selectedBannerIdRef.current || nextItems[0]?.id || 0)
    const selectedBanner = nextItems.find((item) => item.id === selectedId) || nextItems[0] || null

    setPayload({ ...nextPayload, items: nextItems })

    if (!syncDraft) {
      return
    }

    if (selectedBanner) {
      setSelectedBannerId(selectedBanner.id)
      setDraft(createPromoBannerDraft(selectedBanner))
      return
    }

    setSelectedBannerId(0)
    setDraft(createPromoBannerDraft())
  }, [])

  const loadBanners = useCallback(async (preferredBannerId = 0) => {
    if (!initData) return

    setLoading(true)
    setError('')

    try {
      const nextPayload = await fetchAdminBanners({ initData })
      applyPayload(nextPayload, {
        preferredBannerId,
        syncDraft: viewRef.current !== 'editor',
      })
    } catch (requestError) {
      setError(getBannerRequestMessage(requestError, 'Не удалось загрузить баннеры.'))
    } finally {
      setLoading(false)
    }
  }, [applyPayload, initData])

  useEffect(() => {
    loadBanners()
  }, [loadBanners])

  const updateDraft = useCallback((patch) => {
    setDraft((currentDraft) => ({ ...currentDraft, ...patch }))
  }, [])

  const updateDraftBlock = useCallback((blockId, patch) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      blocks: currentDraft.blocks.map((block) => (
        block.id === blockId
          ? { ...block, ...(typeof patch === 'function' ? patch(block) : patch) }
          : block
      )),
    }))
  }, [])

  const openEditor = useCallback((banner) => {
    if (!banner) return
    setError('')
    setNotice(null)
    setPreviewBanner(null)
    setEditorPreviewOpen(false)
    setSelectedBannerId(banner.id)
    setDraft(createPromoBannerDraft(banner))
    setView('editor')
    haptic?.('light')
  }, [haptic])

  const handleCreateBanner = useCallback(() => {
    setError('')
    setNotice(null)
    setPreviewBanner(null)
    setEditorPreviewOpen(false)
    setSelectedBannerId(0)
    setDraft(createPromoBannerDraft({
      blocks: [],
    }))
    setView('editor')
    haptic?.('light')
  }, [haptic])

  const handleReturnToCatalog = useCallback(() => {
    setError('')
    setPreviewBanner(null)
    setEditorPreviewOpen(false)
    setView('catalog')
    haptic?.('light')
  }, [haptic])

  const handleOpenPreview = useCallback((banner) => {
    if (!banner) return
    setEditorPreviewOpen(false)
    setPreviewBanner(normalizePromoBanner(banner))
    haptic?.('light')
  }, [haptic])

  const handleOpenEditorPreview = useCallback(() => {
    setPreviewBanner(null)
    setEditorPreviewOpen(true)
    haptic?.('light')
  }, [haptic])

  const handleOpenDraftPreview = useCallback(() => {
    setEditorPreviewOpen(false)
    setPreviewBanner(normalizePromoBanner(persistedDraft))
    haptic?.('light')
  }, [haptic, persistedDraft])

  const handleClosePreview = useCallback(() => {
    setPreviewBanner(null)
    setEditorPreviewOpen(false)
    haptic?.('light')
  }, [haptic])

  const handlePreviewAction = useCallback((targetUrl = '') => {
    const resolvedUrl = String(targetUrl || previewBanner?.button_url || '').trim()
    if (!resolvedUrl) return
    window.open(resolvedUrl, '_blank', 'noopener,noreferrer')
    haptic?.('light')
  }, [haptic, previewBanner])

  const handleInsertBlock = useCallback(({ type = 'text', afterBlockId = '', requestUpload = false, empty = false, atStart = false } = {}) => {
    const nextBlock = createPromoBannerBlock(type, { empty })

    setDraft((currentDraft) => {
      const nextBlocks = [...currentDraft.blocks]
      const insertIndex = afterBlockId ? nextBlocks.findIndex((block) => block.id === afterBlockId) : -1

      if (atStart) {
        nextBlocks.unshift(nextBlock)
      } else if (insertIndex >= 0) {
        nextBlocks.splice(insertIndex + 1, 0, nextBlock)
      } else {
        nextBlocks.push(nextBlock)
      }

      return {
        ...currentDraft,
        blocks: nextBlocks,
      }
    })

    if (requestUpload) {
      blockUploadTargetRef.current = nextBlock.id
      window.setTimeout(() => {
        blockInputRef.current?.click()
      }, 0)
    }

    return nextBlock.id
  }, [])

  const handleMoveBlock = useCallback((blockId, direction) => {
    setDraft((currentDraft) => {
      const currentIndex = currentDraft.blocks.findIndex((block) => block.id === blockId)
      return {
        ...currentDraft,
        blocks: moveItem(currentDraft.blocks, currentIndex, currentIndex + direction),
      }
    })
  }, [])

  const handleRemoveBlock = useCallback((blockId) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      blocks: currentDraft.blocks.filter((block) => block.id !== blockId),
    }))
  }, [])

  const persistDraft = useCallback(async (
    sourceDraft = draft,
    {
      returnToCatalog = false,
      closeEditorPreview = false,
      successText = 'Баннер сохранён.',
    } = {},
  ) => {
    if (!initData || saving) return false

    const draftToSave = buildPersistedBannerDraft(sourceDraft)

    setSaving(true)
    setError('')
    setNotice(null)

    try {
      const nextPayload = await saveAdminBanner({
        initData,
        banner: draftToSave,
      })
      const savedBannerId = Number(nextPayload?.saved_banner_id || draftToSave.id || 0)
      applyPayload(nextPayload, { preferredBannerId: savedBannerId })
      if (closeEditorPreview) {
        setEditorPreviewOpen(false)
      }
      if (returnToCatalog) {
        setView('catalog')
      }
      if (successText) {
        setNotice({ type: 'success', text: successText })
      }
      haptic?.('success')
      return true
    } catch (requestError) {
      setError(getBannerRequestMessage(requestError, 'Не удалось сохранить баннер.'))
      haptic?.('error')
      return false
    } finally {
      setSaving(false)
    }
  }, [applyPayload, draft, haptic, initData, saving])

  const handleUploadImage = useCallback(async (file, targetKind, blockId = '') => {
    if (!(file instanceof File) || !initData) return

    const isMainCover = targetKind === 'main-cover'
    const isStoryCover = targetKind === 'story-cover'
    const uploadAssetKind = targetKind === 'block' ? 'block' : 'cover'
    const previousMainCoverUrl = draft.image_url || ''
    const previousStoryCoverUrl = draft.story_image_url || ''
    const previousBlockImageUrl = blockId
      ? String(draft.blocks.find((block) => block.id === blockId)?.image_url || '')
      : ''

    setUploadingTarget(blockId || targetKind)
    setError('')
    setNotice(null)

    try {
      const format = targetKind === 'block'
        ? PROMO_BANNER_RECOMMENDED_FORMAT.block
        : PROMO_BANNER_RECOMMENDED_FORMAT.cover
      let prepared

      try {
        prepared = await encodeImageFileAsDataUrl(file, {
          maxWidth: format.width,
          maxHeight: format.height,
          quality: format.quality,
        })
      } catch {
        prepared = await readImageFileAsDataUrl(file)
      }

      if (isMainCover) {
        updateDraft({
          image_url: prepared.dataUrl || '',
          image_alt: resolvedDraftTitle || resolvedDraftLabel,
        })
      } else if (isStoryCover) {
        updateDraft({
          story_image_url: prepared.dataUrl || '',
          story_image_alt: resolvedDraftTitle || resolvedDraftLabel,
        })
      } else if (blockId) {
        updateDraftBlock(blockId, (block) => ({
          ...block,
          image_url: prepared.dataUrl || '',
          alt_text: block.alt_text || resolvedDraftTitle || resolvedDraftLabel,
        }))
      }

      const uploadResult = await uploadAdminBannerImage({
        initData,
        imageData: prepared.dataUrl,
        assetKind: uploadAssetKind,
      })

      if (isMainCover) {
        const nextDraft = {
          ...draft,
          image_url: uploadResult.url || prepared.dataUrl || '',
          image_alt: resolvedDraftTitle || resolvedDraftLabel,
        }
        setDraft(nextDraft)
        const saved = await persistDraft(nextDraft, {
          successText: 'Обложка баннера сохранена.',
        })
        if (!saved) {
          updateDraft({
            image_url: previousMainCoverUrl,
            image_alt: resolvedDraftTitle || resolvedDraftLabel,
          })
        }
      } else if (isStoryCover) {
        updateDraft({
          story_image_url: uploadResult.url || prepared.dataUrl || '',
          story_image_alt: resolvedDraftTitle || resolvedDraftLabel,
        })
      } else if (blockId) {
        updateDraftBlock(blockId, (block) => ({
          ...block,
          image_url: uploadResult.url || prepared.dataUrl || '',
          alt_text: block.alt_text || resolvedDraftTitle || resolvedDraftLabel,
        }))
      }

      if (!isMainCover) {
        setNotice({ type: 'success', text: 'Изображение загружено.' })
      }
    } catch (requestError) {
      if (isMainCover) {
        updateDraft({
          image_url: previousMainCoverUrl,
          image_alt: resolvedDraftTitle || resolvedDraftLabel,
        })
      } else if (isStoryCover) {
        updateDraft({
          story_image_url: previousStoryCoverUrl,
          story_image_alt: resolvedDraftTitle || resolvedDraftLabel,
        })
      } else if (blockId) {
        updateDraftBlock(blockId, (block) => ({
          ...block,
          image_url: previousBlockImageUrl,
          alt_text: block.alt_text || resolvedDraftTitle || resolvedDraftLabel,
        }))
      }

      setError(getBannerUploadErrorMessage(requestError))
    } finally {
      setUploadingTarget('')
    }
  }, [draft, initData, persistDraft, resolvedDraftLabel, resolvedDraftTitle, updateDraft, updateDraftBlock])

  const handleQuickSave = useCallback(async () => {
    await persistDraft(draft)
  }, [persistDraft])

  const deleteBannerByIdentity = useCallback(async (banner) => {
    const bannerId = Number(banner?.id || 0)
    if (!initData || !bannerId || saving) return

    const bannerName = banner?.title || banner?.label || 'без названия'
    if (!window.confirm(`Удалить баннер «${bannerName}»?`)) return

    setSaving(true)
    setError('')
    setNotice(null)

    try {
      const nextPayload = await deleteAdminBanner({ initData, id: bannerId })
      const remainingItems = normalizePayloadItems(nextPayload)
      applyPayload(nextPayload, { preferredBannerId: remainingItems[0]?.id || 0 })
      setView('catalog')
      setNotice({ type: 'success', text: 'Баннер удалён.' })
      haptic?.('success')
    } catch (requestError) {
      setError(getBannerRequestMessage(requestError, 'Не удалось удалить баннер.'))
      haptic?.('error')
    } finally {
      setSaving(false)
    }
  }, [applyPayload, haptic, initData, saving])

  const handleDelete = useCallback(async () => {
    await deleteBannerByIdentity(draft)
  }, [deleteBannerByIdentity, draft])

  const handleDeleteItem = useCallback(async (banner) => {
    await deleteBannerByIdentity(banner)
  }, [deleteBannerByIdentity])

  const handleCoverUploadRequest = useCallback(() => {
    mainCoverInputRef.current?.click()
  }, [])

  const handleStoryCoverUploadRequest = useCallback(() => {
    storyCoverInputRef.current?.click()
  }, [])

  const handleBlockUploadRequest = useCallback((blockId) => {
    blockUploadTargetRef.current = String(blockId || '')
    blockInputRef.current?.click()
  }, [])

  const handlePreviewFieldChange = useCallback((field, value) => {
    if (field === 'button_color') {
      const nextButtonColor = normalizePromoBannerButtonColor(value)
      setDraft((currentDraft) => ({
        ...currentDraft,
        button_color: nextButtonColor,
        blocks: currentDraft.blocks.map((block) => (
          block?.type === 'button'
            ? { ...block, button_color: nextButtonColor }
            : block
        )),
      }))
      return
    }

    updateDraft({ [field]: value })
  }, [updateDraft])

  const handleShowOnEntryChange = useCallback(async (event) => {
    const nextValue = event.target.checked
    const previousDraft = draft
    const nextDraft = {
      ...draft,
      show_on_entry: nextValue,
    }

    setDraft(nextDraft)
    const saved = await persistDraft(nextDraft, {
      successText: 'Автопоказ сохранён.',
    })

    if (!saved) {
      setDraft(previousDraft)
    }
  }, [draft, persistDraft])

  const handleCoverInputChange = useCallback(async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    await handleUploadImage(file, 'main-cover')
  }, [handleUploadImage])

  const handleStoryCoverInputChange = useCallback(async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    await handleUploadImage(file, 'story-cover')
  }, [handleUploadImage])

  const handleBlockInputChange = useCallback(async (event) => {
    const file = event.target.files?.[0]
    const blockId = blockUploadTargetRef.current
    event.target.value = ''
    await handleUploadImage(file, 'block', blockId)
  }, [handleUploadImage])

  const topbar = (
    <div className="admin-shell__topbar">
      <button type="button" className="admin-shell__back pressable" onClick={onBack} aria-label="Назад к разделам">
        <AdminBackIcon />
      </button>
      <div>
        <span className="admin-shell__eyebrow">Промо и первый вход</span>
        <h1 className="admin-shell__detail-title">Баннеры</h1>
      </div>
    </div>
  )

  if (loading) {
    return (
      <motion.div {...SCREEN_ENTRY}>
        <AdminSectionShell topbar={topbar} contentClassName="admin-banners__stack" data-shell-swipe-block="true">
          {[1, 2, 3].map((item) => (
            <div key={item} className="admin-skeleton card">
              <div className="admin-skeleton__line" style={{ width: '30%' }} />
              <div className="admin-skeleton__line" style={{ width: '72%' }} />
              <div className="admin-skeleton__line" style={{ width: '100%', height: 160, borderRadius: 22 }} />
            </div>
          ))}
        </AdminSectionShell>
      </motion.div>
    )
  }

  const noticeNode = notice ? (
    <div className={`admin-notice admin-notice--${notice.type}`} aria-live="polite">
      {notice.text}
    </div>
  ) : null

  return (
    <motion.div {...SCREEN_ENTRY}>
      <AdminSectionShell
        topbar={topbar}
        notice={noticeNode}
        contentClassName="admin-banners__stack"
        data-shell-swipe-block="true"
      >
        {error ? (
          <div className="admin-feedback admin-pricing__feedback card">
            <div className="admin-feedback__icon">!</div>
            <div className="admin-feedback__text">
              <strong>Ошибка баннерного модуля</strong>
              <span>{error}</span>
            </div>
          </div>
        ) : null}

        {isEditorView ? (
          <>
            <section className="admin-banners__editor card">
              <div className="admin-banners__editor-toolbar">
                <button type="button" className="admin-banners__editor-back pressable" onClick={handleReturnToCatalog}>
                  <AdminBackIcon />
                  <span>К каталогу</span>
                </button>
                <div className="admin-banners__editor-heading">
                  <span className="admin-shell__eyebrow">Редактор</span>
                  <h3 className="admin-banners__editor-title">{draft.id ? `Баннер #${draft.id}` : 'Новый баннер'}</h3>
                </div>
              </div>

              <section className="admin-banners__subcard">
                <div className="admin-banners__subcard-head">
                  <div>
                    <span className="admin-shell__eyebrow">Обложка</span>
                    <h4 className="admin-banners__subcard-title admin-banners__subcard-title--cover">Фото для банера на главном экране</h4>
                  </div>
                </div>

                <input ref={mainCoverInputRef} type="file" accept="image/*" hidden onChange={handleCoverInputChange} />
                <input ref={storyCoverInputRef} type="file" accept="image/*" hidden onChange={handleStoryCoverInputChange} />

                <button
                  type="button"
                  className={`admin-banners__cover-dropzone pressable${draft.image_url ? ' admin-banners__cover-dropzone--filled' : ''}`}
                  onClick={handleCoverUploadRequest}
                  disabled={saving || uploadingTarget === 'main-cover'}
                  aria-busy={uploadingTarget === 'main-cover'}
                >
                  {draft.image_url ? (
                    <>
                      <img src={draft.image_url} alt={resolvedDraftImageAlt} className="admin-banners__cover-preview" />
                      <span className="admin-banners__cover-overlay">
                        <span className="admin-banners__cover-plus" aria-hidden="true">
                          <IconPlus size={16} />
                        </span>
                        <span className="admin-banners__cover-copy">
                          {uploadingTarget === 'main-cover' ? 'Загружаю новую обложку...' : 'Нажмите, чтобы заменить фото'}
                        </span>
                        <span className="admin-banners__cover-meta">{coverSizeLabel}</span>
                      </span>
                    </>
                  ) : (
                    <span className="admin-banners__cover-empty">
                      <span className="admin-banners__cover-plus" aria-hidden="true">
                        <IconPlus size={18} />
                      </span>
                      <span className="admin-banners__cover-copy">
                        {uploadingTarget === 'main-cover' ? 'Загружаю обложку...' : 'Добавить фото для баннера'}
                      </span>
                      <span className="admin-banners__cover-meta">{coverSizeLabel}</span>
                    </span>
                  )}
                </button>
              </section>

              <label className="admin-banners__toggle">
                <input type="checkbox" checked={draft.show_on_entry} onChange={handleShowOnEntryChange} disabled={saving} />
                <span className="admin-banners__toggle-track" aria-hidden="true"><span className="admin-banners__toggle-knob" /></span>
                <span>Показывать popup при входе в miniapp</span>
              </label>

              <input ref={blockInputRef} type="file" accept="image/*" hidden onChange={handleBlockInputChange} />

              <div className="admin-banners__editor-actions">
                <button type="button" className="admin-pricing__ghost pressable" onClick={handleOpenEditorPreview} disabled={saving}>
                  Изменить popup
                </button>
                <button type="button" className="admin-pricing__ghost pressable" onClick={handleOpenDraftPreview} disabled={saving}>
                  Предпросмотр
                </button>
                {draft.id ? (
                  <button type="button" className="admin-pricing__ghost admin-pricing__ghost--danger pressable" onClick={handleDelete} disabled={saving}>
                    <IconTrash size={15} />
                    <span>Удалить баннер</span>
                  </button>
                ) : null}
              </div>
            </section>
          </>
        ) : (
          <section className="admin-banners__catalog card">
            <div className="admin-banners__catalog-head">
              <div className="admin-banners__catalog-copy">
                <h2 className="admin-banners__toolbar-title">Каталог баннеров</h2>
                <p className="admin-banners__toolbar-subtitle">
                  Если у нескольких баннеров включён автопоказ, при входе откроется верхний по списку.
                </p>
              </div>

              <div className="admin-banners__catalog-actions">
                <button type="button" className="admin-faq__add admin-banners__catalog-action pressable" onClick={handleCreateBanner} disabled={!canCreateBanner || saving}>
                  <IconPlus size={16} />
                  <span>Новый баннер</span>
                </button>
              </div>
            </div>

            <div className="admin-banners__items">
              {items.length > 0 ? items.map((banner, index) => (
                <motion.article
                  key={banner.id || `banner-${index}`}
                  className={`admin-banners__item${banner.id === selectedBannerId ? ' admin-banners__item--active' : ''}`}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ ...ADMIN_MOTION.quick, delay: Math.min(index * 0.03, 0.18) }}
                >
                  {banner.image_url ? (
                    <img src={banner.image_url} alt={banner.image_alt || banner.title || ''} className="admin-banners__item-cover" loading="lazy" />
                  ) : (
                    <div className="admin-banners__item-cover admin-banners__item-cover--empty" aria-hidden="true">
                      <IconPackage size={22} />
                    </div>
                  )}

                  <div className="admin-banners__item-body">
                    <div className="admin-banners__item-top">
                      <span className="admin-banners__item-label">{`Баннер ${index + 1}`}</span>
                      {banner.show_on_entry ? <span className="admin-banners__item-badge">Автопоказ</span> : null}
                    </div>

                    <div className="admin-banners__item-actions">
                      <button type="button" className="admin-pricing__ghost pressable" onClick={() => handleOpenPreview(banner)} disabled={saving}>
                        Предпросмотр
                      </button>
                      <button type="button" className="admin-faq__add pressable" onClick={() => openEditor(banner)} disabled={saving}>
                        Редактировать
                      </button>
                      <button type="button" className="admin-pricing__ghost admin-pricing__ghost--danger pressable" onClick={() => handleDeleteItem(banner)} disabled={saving}>
                        <IconTrash size={15} />
                        <span>Удалить</span>
                      </button>
                    </div>
                  </div>
                </motion.article>
              )) : (
                <div className="admin-banners__empty-state">
                  <strong>Баннеров пока нет</strong>
                  <span>Создайте первый сценарий, чтобы настроить входной popup и карточку в карусели.</span>
                </div>
              )}
            </div>
          </section>
        )}

        <PromoBannerOverlay
          open={Boolean(previewBanner)}
          banner={previewBanner}
          onClose={handleClosePreview}
          onAction={handlePreviewAction}
        />

        <PromoBannerOverlayEditor
          open={editorPreviewOpen}
          banner={editorDraftBanner}
          onClose={handleClosePreview}
          onSave={handleQuickSave}
          onChangeField={handlePreviewFieldChange}
          onInsertBlock={handleInsertBlock}
          onUpdateBlock={updateDraftBlock}
          onMoveBlock={handleMoveBlock}
          onRemoveBlock={handleRemoveBlock}
          onRequestCoverImageUpload={handleStoryCoverUploadRequest}
          onRequestBlockImageUpload={handleBlockUploadRequest}
          saving={saving}
          uploadingTarget={uploadingTarget}
        />
      </AdminSectionShell>
    </motion.div>
  )
}
