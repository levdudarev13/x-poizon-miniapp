import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  deleteAdminAboutCarouselSlide,
  fetchAdminAboutCarousel,
  uploadAdminAboutCarouselImage,
} from '../../../api/admin.js'
import {
  IconImage,
  IconPackage,
  IconPlus,
  IconTrash,
} from '../../../components/ui/Icons.jsx'
import { ADMIN_MOTION } from '../adminShared.js'
import { AdminBackIcon } from './AdminSharedBits.jsx'
import { AdminSectionShell } from './AdminSectionShell.jsx'

const SCREEN_ENTRY = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: ADMIN_MOTION.standard,
}

const DEFAULT_REQUIRED_FORMAT = '2:3'

function clampInsertSlot(value, maxSlot) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) {
    return 1
  }

  return Math.max(1, Math.min(Math.round(numericValue), Math.max(1, maxSlot)))
}

function getAboutCarouselRequestMessage(requestError, fallbackMessage) {
  const message = String(requestError?.message || '').trim()

  if (message === 'unsupported_image_format') return 'Не удалось обработать фото. Выберите изображение ещё раз.'
  if (message === 'invalid_image_data') return 'Не удалось прочитать изображение. Выберите файл ещё раз.'
  if (message === 'image_too_large') return 'Файл слишком большой после обработки.'
  if (message === 'Invalid slide slot') return 'Не удалось определить слайд.'
  if (message === 'about slide slot is invalid') return 'Не удалось определить позицию слайда.'
  if (message === 'about slide not found') return 'Слайд уже удалён.'
  if (message === 'Not found') return 'Маршрут карусели не найден. Перезапустите miniapp server и обновите Telegram WebApp.'
  return message || fallbackMessage
}

async function encodeImageFileAsDataUrl(
  file,
  {
    maxWidth = 1200,
    maxHeight = 1800,
    quality = 0.92,
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

function normalizeAboutCarouselSlides(payload) {
  return (Array.isArray(payload?.items) ? payload.items : [])
    .map((item, index) => {
      const slot = Number(item?.slot) || index + 1
      return {
        slot,
        image_url: String(item?.image_url || '').trim(),
        image_alt: String(item?.image_alt || `Слайд ${slot}`).trim() || `Слайд ${slot}`,
      }
    })
    .filter((item) => item.slot > 0 && item.image_url)
}

export function AdminAboutCarousel({ initData, onBack, haptic }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [payload, setPayload] = useState(null)
  const [uploadingSlot, setUploadingSlot] = useState(0)
  const [deletingSlot, setDeletingSlot] = useState(0)
  const [insertSlot, setInsertSlot] = useState(1)

  const inputRef = useRef(null)
  const pendingSlotRef = useRef(0)
  const pendingInsertRef = useRef(false)

  const slides = normalizeAboutCarouselSlides(payload)
  const requiredFormat = String(
    payload?.upload?.required_size || payload?.upload?.format || DEFAULT_REQUIRED_FORMAT,
  ).trim() || DEFAULT_REQUIRED_FORMAT
  const maxInsertSlot = slides.length + 1
  const isBusy = Boolean(uploadingSlot || deletingSlot)

  useEffect(() => {
    setInsertSlot((currentValue) => clampInsertSlot(currentValue, maxInsertSlot))
  }, [maxInsertSlot])

  const loadSlides = useCallback(async () => {
    if (!initData) {
      setLoading(false)
      return
    }

    setLoading(true)
    setError('')

    try {
      const nextPayload = await fetchAdminAboutCarousel({ initData })
      setPayload(nextPayload)
    } catch (requestError) {
      setError(getAboutCarouselRequestMessage(requestError, 'Не удалось загрузить слайды.'))
    } finally {
      setLoading(false)
    }
  }, [initData])

  useEffect(() => {
    loadSlides()
  }, [loadSlides])

  const openPicker = useCallback((slot, { insert = false } = {}) => {
    pendingSlotRef.current = slot
    pendingInsertRef.current = insert
    setError('')
    setNotice('')

    if (inputRef.current) {
      inputRef.current.value = ''
      inputRef.current.click()
    }

    haptic?.('light')
  }, [haptic])

  const handleDeleteSlide = useCallback(async (slot) => {
    if (!initData || !slot || isBusy) {
      return
    }

    setDeletingSlot(slot)
    setError('')
    setNotice('')

    try {
      const nextPayload = await deleteAdminAboutCarouselSlide({ initData, slot })
      setPayload(nextPayload)
      setNotice(`Слайд ${slot} удалён.`)
      haptic?.('light')
    } catch (requestError) {
      setError(getAboutCarouselRequestMessage(requestError, 'Не удалось удалить слайд.'))
    } finally {
      setDeletingSlot(0)
    }
  }, [haptic, initData, isBusy])

  const handleFileChange = useCallback(async (event) => {
    const file = event.target.files?.[0]
    const slot = pendingSlotRef.current
    const insertMode = pendingInsertRef.current
    event.target.value = ''

    if (!(file instanceof File) || !slot || !initData) {
      pendingSlotRef.current = 0
      pendingInsertRef.current = false
      return
    }

    setUploadingSlot(slot)
    setError('')
    setNotice('')

    try {
      const { dataUrl } = await encodeImageFileAsDataUrl(file)
      const nextPayload = await uploadAdminAboutCarouselImage({
        initData,
        slot,
        imageData: dataUrl,
        imageAlt: insertMode ? '__insert__' : '',
        insert: insertMode,
      })
      setPayload(nextPayload)

      if (insertMode) {
        setNotice(`Слайд вставлен на позицию ${slot}.`)
      } else {
        setNotice(`Слайд ${slot} обновлён.`)
      }

      haptic?.('light')
    } catch (requestError) {
      setError(getAboutCarouselRequestMessage(requestError, 'Не удалось обновить слайд.'))
    } finally {
      setUploadingSlot(0)
      pendingSlotRef.current = 0
      pendingInsertRef.current = false
    }
  }, [haptic, initData])

  const topbar = (
    <div className="admin-shell__topbar admin-about-carousel__topbar">
      <div className="admin-about-carousel__title-wrap">
        <h1 className="admin-about-carousel__title">Подробнее о нас</h1>
      </div>
      <button type="button" className="admin-about-carousel__back pressable" onClick={onBack}>
        <AdminBackIcon />
        <span>Назад</span>
      </button>
    </div>
  )

  const noticeBlock = error ? (
    <div className="admin-notice admin-notice--error" role="alert">
      {error}
    </div>
  ) : notice ? (
    <div className="admin-notice admin-notice--success" role="status">
      {notice}
    </div>
  ) : null

  return (
    <motion.div {...SCREEN_ENTRY}>
      <AdminSectionShell
        topbar={topbar}
        notice={noticeBlock}
        contentClassName="admin-about-carousel__stack"
        data-shell-swipe-block="true"
      >
        <section className="admin-about-carousel__grid" aria-busy={loading ? 'true' : 'false'}>
          {slides.map((slide, index) => {
            const number = index + 1
            const isUploading = uploadingSlot === slide.slot
            const isDeleting = deletingSlot === slide.slot

            return (
              <article key={`${slide.slot}-${slide.image_url}`} className="admin-about-carousel__item card">
                <div className="admin-about-carousel__thumb">
                  <img
                    src={slide.image_url}
                    alt={slide.image_alt}
                    className="admin-about-carousel__thumb-image"
                    loading="lazy"
                  />

                  <span className="admin-about-carousel__slot-badge">#{number}</span>

                  {isUploading || isDeleting ? (
                    <span className="admin-about-carousel__thumb-overlay">
                      {isDeleting ? 'Удаление...' : 'Загрузка...'}
                    </span>
                  ) : null}
                </div>

                <div className="admin-about-carousel__item-footer">
                  <span className="admin-about-carousel__item-label">Слайд {number}</span>
                  <div className="admin-about-carousel__actions">
                    <button
                      type="button"
                      className="admin-about-carousel__icon-button pressable"
                      onClick={() => openPicker(slide.slot)}
                      disabled={loading || isBusy}
                      aria-label={`Заменить слайд ${number}`}
                      title="Заменить"
                    >
                      <IconImage size={16} />
                    </button>
                    <button
                      type="button"
                      className="admin-about-carousel__icon-button admin-about-carousel__icon-button--danger pressable"
                      onClick={() => handleDeleteSlide(slide.slot)}
                      disabled={loading || isBusy}
                      aria-label={`Удалить слайд ${number}`}
                      title="Удалить"
                    >
                      <IconTrash size={16} />
                    </button>
                  </div>
                </div>
              </article>
            )
          })}

          <article className="admin-about-carousel__adder card">
            <span className="admin-about-carousel__adder-frame">
              <span className="admin-about-carousel__adder-icon" aria-hidden="true">
                {uploadingSlot === insertSlot ? <IconPackage size={24} /> : <IconPlus size={24} />}
              </span>
              <span className="admin-about-carousel__adder-title">
                {uploadingSlot === insertSlot ? 'Загрузка...' : 'Добавить слайд'}
              </span>
              <span className="admin-about-carousel__adder-meta">Фото {requiredFormat}</span>
            </span>

            <div className="admin-about-carousel__adder-controls">
              <label className="admin-about-carousel__position-field">
                <span className="admin-about-carousel__position-label">№</span>
                <input
                  type="number"
                  min="1"
                  max={String(maxInsertSlot)}
                  inputMode="numeric"
                  className="admin-about-carousel__position-input"
                  value={insertSlot}
                  onChange={(event) => setInsertSlot(clampInsertSlot(event.target.value, maxInsertSlot))}
                  disabled={loading || isBusy}
                />
              </label>

              <button
                type="button"
                className="admin-about-carousel__insert-button pressable"
                onClick={() => openPicker(clampInsertSlot(insertSlot, maxInsertSlot), { insert: true })}
                disabled={loading || isBusy}
              >
                <IconPlus size={16} />
                <span>Вставить</span>
              </button>
            </div>
          </article>
        </section>

        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="admin-about-carousel__input"
          onChange={handleFileChange}
        />
      </AdminSectionShell>
    </motion.div>
  )
}
