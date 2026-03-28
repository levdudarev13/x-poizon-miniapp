import { useEffect, useState } from 'react'
import { proxyImageUrl } from '../../utils/media'

const SIZES = new Set(['sm', 'md', 'lg'])

export default function ProductThumb({
  src,
  alt = '',
  fallbackLabel,
  className = '',
  size = 'md',
}) {
  const [imageSrc, setImageSrc] = useState(proxyImageUrl(src || ''))

  useEffect(() => {
    setImageSrc(proxyImageUrl(src || ''))
  }, [src])

  const resolvedSize = SIZES.has(size) ? size : 'md'
  const classes = ['ui-product-thumb', `ui-product-thumb--${resolvedSize}`, className]
    .filter(Boolean)
    .join(' ')
  const fallbackText = (fallbackLabel || '?').slice(0, 3).toUpperCase()

  return (
    <div className={classes}>
      {imageSrc ? (
        <img
          src={imageSrc}
          alt={alt}
          className="ui-product-thumb__image"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setImageSrc('')}
        />
      ) : (
        <span aria-hidden="true">{fallbackText}</span>
      )}
    </div>
  )
}
