import { MouseEvent, TouchEvent, useEffect, useMemo, useRef, useState } from 'react'
import { getPlaceholderImageUrl, resolveMediaUrl, withListingImageMaxWidth } from '../lib/media'

export interface ProductCardGalleryImage {
  id?: number | string
  image_url?: string | null
  alt_text?: string | null
  sort_order?: number | null
  is_main?: boolean
}

interface ProductCardImageGalleryProps {
  productId: number
  name: string
  mainImageUrl?: string | null
  images?: ProductCardGalleryImage[] | null
  imageFitClass: string
  className?: string
}

const imageKey = (url: string) => {
  try {
    const parsed = new URL(url, 'http://local')
    const proxyPath = parsed.searchParams.get('path')
    return decodeURIComponent(proxyPath || parsed.pathname).replace(/^\/+/, '').toLowerCase()
  } catch {
    return url.split('?')[0].replace(/^\/+/, '').toLowerCase()
  }
}

export function normalizeProductCardImages(
  mainImageUrl?: string | null,
  images?: ProductCardGalleryImage[] | null
) {
  const ordered = [...(images || [])].sort((a, b) => {
    if (Boolean(a.is_main) !== Boolean(b.is_main)) return a.is_main ? -1 : 1
    return (a.sort_order || 0) - (b.sort_order || 0)
  })
  const candidates: ProductCardGalleryImage[] = [
    ...(mainImageUrl ? [{ image_url: mainImageUrl, is_main: true }] : []),
    ...ordered,
  ]
  const seen = new Set<string>()

  return candidates.flatMap((item) => {
    const rawUrl = item.image_url?.trim()
    if (!rawUrl) return []
    const resolved = resolveMediaUrl(rawUrl)
    if (!resolved) return []
    const key = imageKey(resolved)
    if (seen.has(key)) return []
    seen.add(key)
    return [{ ...item, image_url: withListingImageMaxWidth(resolved) }]
  })
}

export default function ProductCardImageGallery({
  productId,
  name,
  mainImageUrl,
  images,
  imageFitClass,
  className = '',
}: ProductCardImageGalleryProps) {
  const gallery = useMemo(
    () => normalizeProductCardImages(mainImageUrl, images),
    [mainImageUrl, images]
  )
  const [activeIndex, setActiveIndex] = useState(0)
  const touchStart = useRef<{ x: number; y: number } | null>(null)
  const didSwipe = useRef(false)
  const hoverTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const fallback = getPlaceholderImageUrl({ type: 'product', id: productId })
  const effectiveGallery = gallery.length > 0 ? gallery : [{ image_url: fallback }]

  useEffect(() => {
    setActiveIndex(0)
  }, [gallery.length, mainImageUrl])

  useEffect(() => () => {
    if (hoverTimer.current) clearInterval(hoverTimer.current)
  }, [])

  const stopHoverPlayback = () => {
    if (hoverTimer.current) {
      clearInterval(hoverTimer.current)
      hoverTimer.current = null
    }
  }

  const startHoverPlayback = () => {
    if (effectiveGallery.length < 2 || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return
    stopHoverPlayback()
    hoverTimer.current = setInterval(() => {
      setActiveIndex((current) => (current + 1) % effectiveGallery.length)
    }, 900)
  }

  const handleMouseMove = (event: MouseEvent<HTMLDivElement>) => {
    if (effectiveGallery.length < 2 || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return
    const rect = event.currentTarget.getBoundingClientRect()
    const relativeX = Math.max(0, Math.min(rect.width - 1, event.clientX - rect.left))
    setActiveIndex(Math.floor((relativeX / rect.width) * effectiveGallery.length))
  }

  const handleTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    const touch = event.touches[0]
    touchStart.current = { x: touch.clientX, y: touch.clientY }
    didSwipe.current = false
  }

  const handleTouchMove = (event: TouchEvent<HTMLDivElement>) => {
    const start = touchStart.current
    const touch = event.touches[0]
    if (start && Math.abs(touch.clientX - start.x) > Math.abs(touch.clientY - start.y) && Math.abs(touch.clientX - start.x) > 8) {
      didSwipe.current = true
    }
  }

  return (
    <div
      className={`absolute inset-0 ${className}`}
      onMouseEnter={startHoverPlayback}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => {
        stopHoverPlayback()
        setActiveIndex(0)
      }}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onClickCapture={(event) => {
        if (didSwipe.current) {
          event.preventDefault()
          event.stopPropagation()
          didSwipe.current = false
        }
      }}
    >
      <div className="hidden h-full w-full md:block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={effectiveGallery[activeIndex]?.image_url || fallback}
          alt={effectiveGallery[activeIndex]?.alt_text || name}
          loading="lazy"
          decoding="async"
          width={400}
          height={500}
          className={`h-full w-full ${imageFitClass} transition-transform duration-500 group-hover:scale-105`}
          onError={(event) => { event.currentTarget.src = fallback }}
        />
      </div>

      <div
        className="flex h-full w-full snap-x snap-mandatory overflow-x-auto md:hidden [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        onScroll={(event) => {
          const element = event.currentTarget
          if (element.clientWidth > 0) setActiveIndex(Math.round(element.scrollLeft / element.clientWidth))
        }}
      >
        {effectiveGallery.map((item, index) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={`${item.id || imageKey(item.image_url || '')}-${index}`}
            src={item.image_url || fallback}
            alt={item.alt_text || name}
            loading="lazy"
            decoding="async"
            width={400}
            height={500}
            draggable={false}
            className={`h-full w-full shrink-0 snap-center ${imageFitClass}`}
            onError={(event) => { event.currentTarget.src = fallback }}
          />
        ))}
      </div>

      {effectiveGallery.length > 1 && (
        <div className="pointer-events-none absolute bottom-2 left-1/2 z-10 flex max-w-[80%] -translate-x-1/2 gap-1 opacity-80">
          {effectiveGallery.slice(0, 7).map((_, index) => (
            <span
              key={index}
              className={`h-1.5 w-1.5 rounded-full shadow-sm transition-transform ${index === Math.min(activeIndex, 6) ? 'scale-125 bg-white' : 'bg-white/60'}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
