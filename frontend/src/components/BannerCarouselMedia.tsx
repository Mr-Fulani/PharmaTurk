import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import Image from 'next/image'
import { getSingleFlight } from '../lib/api'
import styles from './BannerCarousel.module.css'
import {
  getPlaceholderImageUrl,
  getVideoEmbedUrl,
  replaceFailedVideoWithFallback,
  resolveMediaUrl,
  withListingImageMaxWidth,
} from '../lib/media'

interface BannerMedia {
  id: number
  content_type: 'image' | 'video' | 'gif'
  content_url: string
  content_mime_type?: string
  sort_order: number
  link_url?: string
  title?: string
  description?: string
  link_text?: string
}

interface Banner {
  id: number
  title?: string
  description?: string
  position: string
  link_url?: string
  link_text?: string
  sort_order: number
  media_files: BannerMedia[]
}

interface BannerCarouselProps {
  position: 'main' | 'after_brands' | 'after_popular_products' | 'before_footer' | 'how_to_order'
  className?: string
  initialBanners?: Banner[]
}

const EMPTY_BANNERS: Banner[] = []
// Пауза перед единственной повторной загрузкой слайда: сбой CDN/сети обычно разовый
const IMAGE_RETRY_DELAY_MS = 1500
// Миниатюры видны только шире 640px (BannerCarousel.module.css)
const THUMBNAILS_MEDIA_QUERY = '(min-width: 641px)'

const withRetryParam = (url: string) => `${url}${url.includes('?') ? '&' : '?'}retry=1`

export default function BannerCarousel({ position, className = '', initialBanners = EMPTY_BANNERS }: BannerCarouselProps) {
  const router = useRouter()
  const { t } = useTranslation('common')
  const [banners, setBanners] = useState<Banner[]>(initialBanners)
  const [displayMedia, setDisplayMedia] = useState<BannerMedia[]>(() => {
    const allMedia: BannerMedia[] = []
    initialBanners.forEach((b) => {
      if (b.media_files) {
        b.media_files.forEach((m) => {
          allMedia.push({ ...m, link_url: m.link_url || b.link_url, link_text: m.link_text || b.link_text })
        })
      }
    })
    return allMedia.slice(0, Math.min(10, allMedia.length))
  })
  const firstMediaId = banners.find(banner => banner.media_files?.length)?.media_files[0].id
  const [expandedMediaIds, setExpandedMediaIds] = useState<Record<number, boolean>>({})
  const [firstMediaReady, setFirstMediaReady] = useState(false)
  const [inViewport, setInViewport] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [activeMediaId, setActiveMediaId] = useState<number | null>(null)
  const [loading, setLoading] = useState(initialBanners.length === 0)
  const [fallbackMediaIds, setFallbackMediaIds] = useState<Record<number, boolean>>({})
  const [retriedMediaIds, setRetriedMediaIds] = useState<Record<number, boolean>>({})
  const [thumbnailsVisible, setThumbnailsVisible] = useState(false)
  const autoPlayIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const lastManualActionRef = useRef<number>(0)
  const initialMountRef = useRef(true)

  useEffect(() => {
    // Пропускаем запрос при первой отрисовке, если у нас уже есть SSR данные, 
    // чтобы не было мерцания и лишних запросов
    if (initialMountRef.current && initialBanners.length > 0) {
      initialMountRef.current = false
      return
    }
    initialMountRef.current = false

    setLoading(true)
    const fetchBanners = async () => {
      try {
        const response = await getSingleFlight('/catalog/banners', {
          params: { position }
        })
        const data = response.data || []
        setBanners(data.filter((b: Banner) => b.media_files && b.media_files.length > 0))
      } catch (error: any) {
        console.error('Failed to fetch banners:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchBanners()
  }, [position, router.locale, initialBanners.length])

  useEffect(() => {
    if (banners.length > 0) {
      const allMedia: BannerMedia[] = []
      banners.forEach((b) => {
        if (b.media_files) {
          b.media_files.forEach((m) => {
            allMedia.push({ ...m, link_url: m.link_url || b.link_url, link_text: m.link_text || b.link_text })
          })
        }
      })
      setDisplayMedia(allMedia.slice(0, Math.min(10, allMedia.length)))
    } else {
      setDisplayMedia([])
    }
  }, [banners])
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    if (typeof IntersectionObserver === 'undefined') {
      setInViewport(true)
      return
    }
    const observer = new IntersectionObserver(([entry]) => {
      setInViewport(entry.isIntersecting)
    }, { threshold: 0.1 })
    observer.observe(container)
    return () => observer.disconnect()
  }, [loading, banners.length])

  // На телефоне миниатюры скрыты: не тянем их полноразмерные картинки с CDN
  useEffect(() => {
    const query = window.matchMedia(THUMBNAILS_MEDIA_QUERY)
    const update = () => setThumbnailsVisible(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  // Функция для сброса и перезапуска автоматического переключения
  const resetAutoPlay = useCallback(() => {
    if (autoPlayIntervalRef.current) {
      clearInterval(autoPlayIntervalRef.current)
    }
    
    if (inViewport && firstMediaReady && displayMedia.length > 1) {
      autoPlayIntervalRef.current = setInterval(() => {
        if (document.visibilityState === 'hidden') return
        const timeSinceLastManual = Date.now() - lastManualActionRef.current
        if (timeSinceLastManual > 6000) {
          setDisplayMedia((prev) => {
            if (prev.length <= 1) return prev
            const nextMedia = [...prev]
            const firstItem = nextMedia.shift()
            if (firstItem) nextMedia.push(firstItem)
            if (nextMedia[0]) setActiveMediaId(nextMedia[0].id)
            return nextMedia
          })
        }
      }, 8000)
    }
  }, [inViewport, firstMediaReady, displayMedia.length])

  // Даём первому слайду загрузиться и быть видимым до запуска автопрокрутки.
  useEffect(() => {
    resetAutoPlay()
    
    return () => {
      if (autoPlayIntervalRef.current) {
        clearInterval(autoPlayIntervalRef.current)
      }
    }
  }, [resetAutoPlay])

  // Принудительное обновление при изменении активного медиа для запуска анимации
  useEffect(() => {
    if (displayMedia.length > 0) {
      const activeMedia = displayMedia[0]
      if (activeMedia) {
        setActiveMediaId(activeMedia.id)
        setExpandedMediaIds(previous => previous[activeMedia.id]
          ? previous : { ...previous, [activeMedia.id]: true })
      }
    }
  }, [displayMedia])

  const goToPreviousMedia = (isManual: boolean) => {
    if (displayMedia.length <= 1) return
    
    if (isManual) {
      lastManualActionRef.current = Date.now()
      resetAutoPlay()
    }
    
    setDisplayMedia((prev) => {
      if (prev.length <= 1) return prev
      const newMedia = [...prev]
      const lastItem = newMedia.pop()
      if (lastItem) {
        newMedia.unshift(lastItem)
      }
      const activeMedia = newMedia[0]
      if (activeMedia) {
        setActiveMediaId(activeMedia.id)
      }
      return newMedia
    })
  }

  const goToNextMedia = (isManual: boolean) => {
    if (displayMedia.length <= 1) return
    
    if (isManual) {
      lastManualActionRef.current = Date.now()
      resetAutoPlay()
    }
    
    setDisplayMedia((prev) => {
      if (prev.length <= 1) return prev
      const newMedia = [...prev]
      const firstItem = newMedia.shift()
      if (firstItem) {
        newMedia.push(firstItem)
      }
      const activeMedia = newMedia[0]
      if (activeMedia) {
        setActiveMediaId(activeMedia.id)
      }
      return newMedia
    })
  }

  const renderMediaItem = (media: BannerMedia, index: number) => {
    const isActive = activeMediaId !== null ? media.id === activeMediaId : index === 0
    const fullUrl = media.content_url ? resolveMediaUrl(media.content_url) : ''
    const embedUrl = media.content_type === 'video' ? getVideoEmbedUrl(fullUrl, 'ambient') : null

    const handleThumbnailClick = () => {
      if (index >= 1 && displayMedia.length > 1) {
        lastManualActionRef.current = Date.now()
        resetAutoPlay()
        
        const clickedMediaIndex = displayMedia.findIndex(m => m.id === media.id)
        if (clickedMediaIndex === -1) return
        
        const newMedia = [...displayMedia]
        const steps = clickedMediaIndex
        for (let i = 0; i < steps; i++) {
          const firstMedia = newMedia.shift()
          if (firstMedia) {
            newMedia.push(firstMedia)
          }
        }
        
        const activeMedia = newMedia[0]
        if (activeMedia) {
          setActiveMediaId(activeMedia.id)
        }
        setDisplayMedia(newMedia)
      }
    }
    
    const getTrimmedValue = (value: any): string | null => {
      if (!value || typeof value !== 'string') return null
      const trimmed = value.trim()
      return trimmed.length > 0 ? trimmed : null
    }
    
    const title = getTrimmedValue(media.title)
    const description = getTrimmedValue(media.description)
    const linkText = getTrimmedValue(media.link_text)
    const linkUrl = getTrimmedValue(media.link_url)
    
    const hasMediaContent = !!(title || description || (linkText && linkUrl))
    const shouldShowContent = isActive && index === 0 && hasMediaContent

    return (
      <div
        key={media.id}
        data-banner-item
        className={styles.item}
        onClick={index >= 1 ? handleThumbnailClick : undefined}
      >
        {(media.content_type === 'image' || media.content_type === 'gif') && (() => {
          const isFallback = !fullUrl || fallbackMediaIds[media.id]
          const finalUrl = isFallback 
            ? getPlaceholderImageUrl({ type: 'product', id: media.id.toString() })
            : fullUrl

          // Keep a visited slide's full-size source when it becomes a thumbnail.
          // Otherwise rotation downloads a second image and demotes the LCP resource.
          const fullSize = index === 0 || media.id === firstMediaId || expandedMediaIds[media.id]
          // Hidden phone thumbnails get no image, except the next slide once the
          // first one has loaded, so autoplay does not reveal an empty slide.
          if (!fullSize && !thumbnailsVisible && !(index === 1 && firstMediaReady)) return null
          const isHero = position === 'main' && media.id === firstMediaId
          const optimizedUrl = fullSize
            ? finalUrl
            : withListingImageMaxWidth(finalUrl, 440)
          const imageUrl = retriedMediaIds[media.id] && !isFallback
            ? withRetryParam(optimizedUrl)
            : optimizedUrl

          return (
            <div className="relative h-full w-full">
              <Image
                src={imageUrl}
                alt={title || t('banner_image_alt', 'Banner')}
                fill
                // Ready-made CDN webp (~1672px) is served as is: the /_next/image
                // optimizer runs inside Next and ran out of memory under load.
                unoptimized
                priority={isHero}
                fetchPriority={isHero ? 'high' : 'auto'}
                loading={isHero ? 'eager' : 'lazy'}
                className={`${styles.itemImage} object-cover`}
                onLoadingComplete={() => {
                  if (media.id === firstMediaId) setFirstMediaReady(true)
                  if (isActive) setLoading(false)
                }}
                onError={() => {
                  if (isFallback) return
                  if (!retriedMediaIds[media.id]) {
                    setTimeout(() => setRetriedMediaIds(prev => ({ ...prev, [media.id]: true })), IMAGE_RETRY_DELAY_MS)
                    return
                  }
                  setFallbackMediaIds(prev => ({ ...prev, [media.id]: true }))
                }}
              />
            </div>
          )
        })()}
        {media.content_type === 'video' && embedUrl && fullUrl && (
          <iframe
            src={embedUrl}
            className={styles.itemIframe}
            allow="autoplay; encrypted-media"
            allowFullScreen
            onLoad={() => { if (media.id === firstMediaId) setFirstMediaReady(true) }}
          />
        )}
        {media.content_type === 'video' && !embedUrl && fullUrl && (
          <video
            autoPlay
            loop
            muted
            playsInline
            onLoadedData={() => { if (media.id === firstMediaId) setFirstMediaReady(true) }}
            className={styles.itemVideo}
            onError={(event) => replaceFailedVideoWithFallback(event.currentTarget, title || 'MUDAROBA')}
          >
            <source src={fullUrl} type={media.content_mime_type || 'video/mp4'} />
          </video>
        )}

        {shouldShowContent && (
          <div className={styles.scrim} aria-hidden="true" />
        )}
        {shouldShowContent && (
          <div 
            key={`content-${media.id}-${isActive}`}
            className={styles.content}
            style={{
              display: 'block',
              visibility: 'visible',
              opacity: 1,
              zIndex: 1000,
              position: 'absolute'
            }}
          >
            {title && (
              <h2 className={styles.name}>{title}</h2>
            )}
            {description && (
              <h3 className={styles.des}>{description}</h3>
            )}
            {media.link_text && linkUrl && (
            <button
              className={styles.button}
              onClick={(e) => {
                e.stopPropagation()
                if (linkUrl) {
                  const isExternal = /^https?:\/\//.test(linkUrl)
                  if (isExternal) {
                    window.location.href = linkUrl
                  } else {
                    router.push(linkUrl)
                  }
                }
              }}
            >
              {linkText && linkText.trim().toLowerCase() === 'learn more' 
                ? t('view_product_details', 'Узнать подробнее о товаре') 
                : (linkText || t('view_details', 'Подробнее'))}
            </button>
          )}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div
        className={`relative overflow-hidden rounded-[18px] ${className}`}
        style={{ height: 'clamp(280px, 55vw, 600px)', background: 'linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)', backgroundSize: '200% 100%', animation: 'bannerSkeleton 1.5s infinite' }}
        aria-hidden="true"
      >
        <style>{`@keyframes bannerSkeleton { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }`}</style>
      </div>
    )
  }

  if (banners.length === 0) {
    // Нет баннеров (удалены или деактивированы в админке) — не показываем блок
    return null
  }

  const hasMultipleMedia = displayMedia.length > 1

  return (
    <div ref={containerRef} className={`${styles.container} ${className}`}>
      <div className={styles.slide}>
        {displayMedia.map((media, index) => renderMediaItem(media, index))}
      </div>

      {hasMultipleMedia && (
        <div className={styles.buttonContainer}>
          <button
            className={styles.navButton}
            onClick={() => goToPreviousMedia(true)}
            aria-label="Предыдущее медиа"
          >
            <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            className={styles.navButton}
            onClick={() => goToNextMedia(true)}
            aria-label="Следующее медиа"
          >
            <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      )}
    </div>
  )
}
