import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import Image from 'next/image'
import api from '../lib/api'
import styles from './BannerCarousel.module.css'
import { resolveMediaUrl, getPlaceholderImageUrl, getVideoEmbedUrl } from '../lib/media'

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
  position: 'main' | 'after_brands' | 'after_popular_products' | 'before_footer'
  className?: string
  initialBanners?: Banner[]
}

const EMPTY_BANNERS: Banner[] = []

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
  const [activeMediaId, setActiveMediaId] = useState<number | null>(null)
  const [loading, setLoading] = useState(initialBanners.length === 0)
  const [fallbackToPicsumIds, setFallbackToPicsumIds] = useState<Record<number, boolean>>({})
  const autoPlayIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const lastManualActionRef = useRef<number>(0)

  useEffect(() => {
    if (initialBanners.length > 0) {
      setBanners(initialBanners)
      setLoading(false)
      return
    }

    const fetchBanners = async () => {
      try {
        const response = await api.get('/catalog/banners', {
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
  }, [position, router.locale, initialBanners])



  // Функция для сброса и перезапуска автоматического переключения
  const resetAutoPlay = () => {
    if (autoPlayIntervalRef.current) {
      clearInterval(autoPlayIntervalRef.current)
    }
    
    if (banners.length > 0 && displayMedia.length > 1) {
      autoPlayIntervalRef.current = setInterval(() => {
        const timeSinceLastManual = Date.now() - lastManualActionRef.current
        if (timeSinceLastManual > 4000) {
          goToNextMedia(false)
        }
      }, 5000)
    }
  }

  // Автоматическая смена медиа каждые 5 секунд
  useEffect(() => {
    resetAutoPlay()
    
    return () => {
      if (autoPlayIntervalRef.current) {
        clearInterval(autoPlayIntervalRef.current)
      }
    }
  }, [banners, displayMedia.length])

  // Принудительное обновление при изменении активного медиа для запуска анимации
  useEffect(() => {
    if (displayMedia.length > 0) {
      const activeMedia = displayMedia[0]
      if (activeMedia) {
        setActiveMediaId(activeMedia.id)
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
          const isFallback = !fullUrl || fallbackToPicsumIds[media.id]
          const finalUrl = isFallback 
            ? getPlaceholderImageUrl({ type: 'product', id: media.id.toString() })
            : fullUrl

          return (
            <div className="relative h-full w-full">
              <Image
                src={finalUrl}
                alt={title || t('banner_image_alt', 'Banner')}
                fill
                priority={index === 0 && position === 'main'}
                sizes="(max-width: 768px) 100vw, 1200px"
                className={`${styles.itemImage} object-cover`}
                onLoadingComplete={() => {
                  if (isActive) setLoading(false)
                }}
                onError={() => {
                  if (!isFallback) {
                    setFallbackToPicsumIds(prev => ({ ...prev, [media.id]: true }))
                  }
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
          />
        )}
        {media.content_type === 'video' && !embedUrl && fullUrl && (
          <video
            autoPlay
            loop
            muted
            playsInline
            className={styles.itemVideo}
          >
            <source src={fullUrl} type={media.content_mime_type || 'video/mp4'} />
          </video>
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
    <div className={`${styles.container} ${className}`}>
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
