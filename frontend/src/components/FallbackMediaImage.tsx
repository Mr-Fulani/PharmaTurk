import Image from 'next/image'
import { useEffect, useState } from 'react'
import { DEFAULT_MEDIA_FALLBACK } from '../lib/media'

const DEFAULT_SIZES = '(max-width: 640px) 210px, (max-width: 1024px) 33vw, 400px'

export type FallbackMediaImageProps = {
  src: string
  alt: string
  fallbackSrc?: string
  /** Под masonry 3/2/1 колонки на страницах брендов и категорий */
  sizes?: string
  /** Responsive sizes for homepage images served by the existing media proxy. */
  responsiveProxy?: boolean
}

/**
 * next/image для разрешённых CDN; иначе обычный img (proxy /api с query ломает оптимизатор).
 */
export default function FallbackMediaImage({
  src,
  alt,
  fallbackSrc = DEFAULT_MEDIA_FALLBACK,
  sizes = DEFAULT_SIZES,
  responsiveProxy = false,
}: FallbackMediaImageProps) {
  const [imgSrc, setImgSrc] = useState(src)

  useEffect(() => {
    setImgSrc(src || fallbackSrc)
  }, [src, fallbackSrc])

  const isProxyMedia = imgSrc.includes('/api/') || imgSrc.includes('proxy-media')

  const isExternal = imgSrc.startsWith('http')
  const allowedDomains = [
    'i.pinimg.com',
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
        srcSet={responsiveProxy && imgSrc.includes('proxy-media') ? [192, 320, 480, 600, 800].map(width => {
          const url = new URL(imgSrc, 'https://mudaroba.com')
          url.searchParams.delete('w')
          url.searchParams.set('max_width', String(width))
          const source = imgSrc.startsWith('/') ? `${url.pathname}${url.search}` : url.href
          return `${source} ${width}w`
        }).join(', ') : undefined}
        sizes={responsiveProxy ? sizes : undefined}
        alt={alt}
        loading="lazy"
        decoding="async"
        className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        onError={() => {
          if (imgSrc !== fallbackSrc) setImgSrc(fallbackSrc)
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
        if (imgSrc !== fallbackSrc) setImgSrc(fallbackSrc)
      }}
    />
  )
}
