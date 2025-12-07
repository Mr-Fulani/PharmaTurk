import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import api from '../lib/api'
import styles from './BannerCarousel.module.css'

interface BannerMedia {
  id: number
  content_type: 'image' | 'video' | 'gif'
  content_url: string
  content_mime_type?: string
  sort_order: number
  link_url?: string
}

interface Banner {
  id: number
  title?: string
  position: string
  link_url?: string
  link_text?: string
  sort_order: number
  media_files: BannerMedia[]
}

interface BannerCarouselProps {
  position: 'main' | 'after_brands' | 'after_popular_products' | 'before_footer'
  className?: string
}

export default function BannerCarouselMedia({ position, className = '' }: BannerCarouselProps) {
  const router = useRouter()
  const [banner, setBanner] = useState<Banner | null>(null)
  const [displayMedia, setDisplayMedia] = useState<BannerMedia[]>([])
  const [loading, setLoading] = useState(true)
  const slideRef = useRef<HTMLDivElement>(null)
  const autoPlayIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const lastManualActionRef = useRef<number>(0)

  useEffect(() => {
    const fetchBanners = async () => {
      try {
        const response = await api.get('/catalog/banners', {
          params: { position }
        })
        const data = response.data || []
        const bannersWithMedia = data.filter((b: Banner) => 
          b.media_files && b.media_files.length > 0
        )
        
        if (bannersWithMedia.length > 0) {
          const firstBanner = bannersWithMedia[0]
          setBanner(firstBanner)
          
          // Инициализируем displayMedia: показываем все медиа-файлы (до 6 для слайдера)
          // НЕ дублируем - показываем только реальные медиа
          const mediaFiles = firstBanner.media_files
          setDisplayMedia(mediaFiles.slice(0, Math.min(6, mediaFiles.length)))
          
          console.log('🎨 Banner loaded with media:', {
            bannerId: firstBanner.id,
            title: firstBanner.title,
            mediaCount: mediaFiles.length,
            displayCount: mediaFiles.length
          })
        }
      } catch (error: any) {
        console.error('Failed to fetch banners:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchBanners()
  }, [position])

  // Функция для сброса и перезапуска автоматического переключения
  const resetAutoPlay = () => {
    if (autoPlayIntervalRef.current) {
      clearInterval(autoPlayIntervalRef.current)
    }
    
    if (banner && displayMedia.length > 1) {
      autoPlayIntervalRef.current = setInterval(() => {
        // Проверяем, не было ли ручного действия в последние 4 секунды
        const timeSinceLastManual = Date.now() - lastManualActionRef.current
        if (timeSinceLastManual > 4000) {
          goToNextMedia()
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
  }, [banner, displayMedia.length])

  const goToPreviousMedia = () => {
    if (!banner || displayMedia.length <= 1) return
    
    // Отмечаем ручное действие
    lastManualActionRef.current = Date.now()
    resetAutoPlay()
    
    // Сначала обновляем состояние
    setDisplayMedia((prev) => {
      const newMedia = [...prev]
      const lastMedia = newMedia.pop()
      if (lastMedia) {
        newMedia.unshift(lastMedia)
      }
      return newMedia
    })
    
    // Затем перемещаем DOM для плавной анимации
    requestAnimationFrame(() => {
      if (slideRef.current) {
        const items = slideRef.current.querySelectorAll('[data-banner-item]')
        if (items.length > 0) {
          const lastItem = items[items.length - 1] as HTMLElement
          slideRef.current.insertBefore(lastItem, slideRef.current.firstChild)
        }
      }
    })
  }

  const goToNextMedia = () => {
    if (!banner || displayMedia.length <= 1) return
    
    // Отмечаем ручное действие
    lastManualActionRef.current = Date.now()
    resetAutoPlay()
    
    // Сначала обновляем состояние
    setDisplayMedia((prev) => {
      const newMedia = [...prev]
      const firstMedia = newMedia.shift()
      if (firstMedia) {
        newMedia.push(firstMedia)
      }
      return newMedia
    })
    
    // Затем перемещаем DOM для плавной анимации
    requestAnimationFrame(() => {
      if (slideRef.current) {
        const items = slideRef.current.querySelectorAll('[data-banner-item]')
        if (items.length > 0) {
          const firstItem = items[0] as HTMLElement
          slideRef.current.appendChild(firstItem)
        }
      }
    })
  }

  const getFullUrl = (url: string) => {
    if (!url) return ''
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return url
    }
    let apiBase = process.env.NEXT_PUBLIC_API_BASE
    if (!apiBase && typeof window !== 'undefined') {
      const origin = window.location.origin
      if (origin.includes(':3001')) {
        apiBase = origin.replace(':3001', ':8000') + '/api'
      } else if (origin.includes(':3000')) {
        apiBase = origin.replace(':3000', ':8000') + '/api'
      } else {
        apiBase = '/api'
      }
    } else if (!apiBase) {
      apiBase = '/api'
    }
    return `${apiBase}${url.startsWith('/') ? url : `/${url}`}`
  }

  const getVideoEmbedUrl = (url: string): string | null => {
    if (!url) return null
    
    if (url.includes('youtube.com/embed/')) {
      if (!url.includes('?')) {
        return `${url}?autoplay=1&loop=1&muted=1&controls=0&showinfo=0&rel=0`
      }
      return url
    }
    
    if (url.includes('youtube.com') || url.includes('youtu.be')) {
      const standardRegex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})/
      let match = url.match(standardRegex)
      
      if (!match) {
        const shortsRegex = /(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?\/\s]+)/
        match = url.match(shortsRegex)
      }
      
      if (match && match[1]) {
        return `https://www.youtube.com/embed/${match[1]}?autoplay=1&loop=1&muted=1&playlist=${match[1]}&controls=0&showinfo=0&rel=0`
      }
    }
    
    return null
  }

  const renderMediaItem = (media: BannerMedia, index: number) => {
    const isActive = displayMedia.length === 1 ? index === 0 : index === 1
    const fullUrl = getFullUrl(media.content_url)
    const embedUrl = media.content_type === 'video' ? getVideoEmbedUrl(fullUrl) : null

    const handleMediaClick = () => {
      // Если кликнули на миниатюру (index >= 2), делаем её активной
      if (index >= 2 && displayMedia.length > 1) {
        // Отмечаем ручное действие
        lastManualActionRef.current = Date.now()
        resetAutoPlay()
        
        const steps = index - 1
        const newMedia = [...displayMedia]
        for (let i = 0; i < steps; i++) {
          const firstMedia = newMedia.shift()
          if (firstMedia) {
            newMedia.push(firstMedia)
          }
        }
        setDisplayMedia(newMedia)
      } else if (isActive && banner?.link_url) {
        const isExternal = /^https?:\/\//.test(banner.link_url)
        if (isExternal) {
          window.open(banner.link_url, '_blank', 'noopener, noreferrer')
        } else {
          router.push(banner.link_url)
        }
      }
    }

    return (
      <div
        key={media.id}
        data-banner-item
        className={styles.item}
        style={{
          backgroundImage: (media.content_type === 'image' || media.content_type === 'gif') 
            ? `url(${fullUrl})` 
            : 'none',
        }}
        onClick={handleMediaClick}
      >
        {/* Видео контент */}
        {media.content_type === 'video' && embedUrl && (
          <iframe
            src={embedUrl}
            className={styles.itemIframe}
            allow="autoplay; encrypted-media"
            allowFullScreen
          />
        )}
        {media.content_type === 'video' && !embedUrl && (
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

        {/* Контент с текстом - показываем данные баннера */}
        {banner && (
          <div className={styles.content}>
            {banner.title && (
              <div className={styles.name}>{banner.title}</div>
            )}
            {banner.link_text && (
              <div className={styles.des}>{banner.link_text}</div>
            )}
            {banner.link_text && banner.link_url && (
              <button
                className={styles.button}
                onClick={(e) => {
                  e.stopPropagation()
                  const isExternal = /^https?:\/\//.test(banner.link_url!)
                  if (isExternal) {
                    window.open(banner.link_url, '_blank', 'noopener, noreferrer')
                  } else {
                    router.push(banner.link_url!)
                  }
                }}
              >
                {banner.link_text}
              </button>
            )}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div className={`flex items-center justify-center h-64 md:h-96 lg:h-[500px] bg-gray-100 rounded-xl ${className}`}>
        <svg className="h-8 w-8 animate-spin text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </div>
    )
  }

  if (!banner) {
    return null
  }

  const hasMultipleMedia = displayMedia.length > 1

  return (
    <div className={`${styles.container} ${className}`}>
      <div ref={slideRef} className={styles.slide}>
        {displayMedia.map((media, index) => renderMediaItem(media, index))}
      </div>

      {hasMultipleMedia && (
        <div className={styles.buttonContainer}>
          <button
            className={styles.navButton}
            onClick={goToPreviousMedia}
            aria-label="Предыдущее медиа"
          >
            <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            className={styles.navButton}
            onClick={goToNextMedia}
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

