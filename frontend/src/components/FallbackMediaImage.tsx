import Image from 'next/image'
import { useState } from 'react'

const DEFAULT_SIZES = '(max-width: 640px) 210px, (max-width: 1024px) 33vw, 400px'

export type FallbackMediaImageProps = {
  src: string
  alt: string
  fallbackSrc?: string
  /** Под masonry 3/2/1 колонки на страницах брендов и категорий */
  sizes?: string
}

/**
 * next/image для разрешённых CDN; иначе обычный img (proxy /api с query ломает оптимизатор).
 */
export default function FallbackMediaImage({
  src,
  alt,
  fallbackSrc,
  sizes = DEFAULT_SIZES,
}: FallbackMediaImageProps) {
  const [imgSrc, setImgSrc] = useState(src)

  const isProxyMedia = imgSrc.includes('/api/') || imgSrc.includes('proxy-media')

  const isExternal = imgSrc.startsWith('http')
  const allowedDomains = [
    'i.pinimg.com',
    'fastly.picsum.photos',
    'picsum.photos',
    'static.street-beat.ru',
    'img.youtube.com',
    'cdn.mudaroba.com',
  ]
  let isValidHost = !isProxyMedia
  if (!isProxyMedia && isExternal) {
    try {
      const hostname = new URL(imgSrc).hostname
      isValidHost = allowedDomains.includes(hostname) || hostname === 'localhost'
    } catch {
      isValidHost = false
    }
  }

  if (!isValidHost || isProxyMedia) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={imgSrc}
        alt={alt}
        loading="lazy"
        decoding="async"
        className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        onError={() => {
          if (fallbackSrc && imgSrc !== fallbackSrc) setImgSrc(fallbackSrc)
        }}
      />
    )
  }

  return (
    <Image
      src={imgSrc}
      alt={alt}
      loading="lazy"
      fill
      sizes={sizes}
      className="pointer-events-none object-cover"
      onError={() => {
        if (fallbackSrc && imgSrc !== fallbackSrc) setImgSrc(fallbackSrc)
      }}
    />
  )
}
