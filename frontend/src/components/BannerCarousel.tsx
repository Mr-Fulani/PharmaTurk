import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import api from '../lib/api'

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

export default function BannerCarousel({ position, className = '' }: BannerCarouselProps) {
  const router = useRouter()
  const [banners, setBanners] = useState<Banner[]>([])
  const [currentBannerIndex, setCurrentBannerIndex] = useState(0)
  const [currentMediaIndex, setCurrentMediaIndex] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchBanners = async () => {
      try {
        const response = await api.get('/catalog/banners', {
          params: { position }
        })
        const data = response.data || []
        // Фильтруем баннеры, у которых есть хотя бы один медиа-файл
        const bannersWithMedia = data.filter((banner: Banner) => 
          banner.media_files && banner.media_files.length > 0
        )
        setBanners(bannersWithMedia)
        if (bannersWithMedia.length > 0) {
          setCurrentBannerIndex(0)
          setCurrentMediaIndex(0)
        }
      } catch (error: any) {
        console.error('Failed to fetch banners:', {
          error,
          message: error?.message,
          response: error?.response?.data,
          status: error?.response?.status,
          url: error?.config?.url,
          baseURL: error?.config?.baseURL,
          fullUrl: error?.config ? `${error?.config.baseURL}${error?.config.url}` : 'unknown',
          position,
          origin: typeof window !== 'undefined' ? window.location.origin : 'server'
        })
        setBanners([])
      } finally {
        setLoading(false)
      }
    }

    fetchBanners()
  }, [position])

  // Автоматическая смена медиа внутри баннера каждые 5 секунд
  useEffect(() => {
    const currentBanner = banners[currentBannerIndex]
    if (!currentBanner || currentBanner.media_files.length <= 1) return

    const interval = setInterval(() => {
      setCurrentMediaIndex((prev) => (prev + 1) % currentBanner.media_files.length)
    }, 5000)

    return () => clearInterval(interval)
  }, [banners, currentBannerIndex])

  // Автоматическая смена баннеров каждые 10 секунд (если больше одного баннера)
  useEffect(() => {
    if (banners.length <= 1) return

    const interval = setInterval(() => {
      setCurrentBannerIndex((prev) => {
        const nextIndex = (prev + 1) % banners.length
        setCurrentMediaIndex(0) // Сбрасываем индекс медиа при смене баннера
        return nextIndex
      })
    }, 10000)

    return () => clearInterval(interval)
  }, [banners.length])

  const goToBanner = (index: number) => {
    setCurrentBannerIndex(index)
    setCurrentMediaIndex(0)
  }

  const goToPreviousBanner = () => {
    const prevIndex = (currentBannerIndex - 1 + banners.length) % banners.length
    setCurrentBannerIndex(prevIndex)
    setCurrentMediaIndex(0)
  }

  const goToNextBanner = () => {
    const nextIndex = (currentBannerIndex + 1) % banners.length
    setCurrentBannerIndex(nextIndex)
    setCurrentMediaIndex(0)
  }

  const goToMedia = (index: number) => {
    setCurrentMediaIndex(index)
  }

  const goToPreviousMedia = () => {
    const currentBanner = banners[currentBannerIndex]
    if (!currentBanner) return
    setCurrentMediaIndex((prev) => (prev - 1 + currentBanner.media_files.length) % currentBanner.media_files.length)
  }

  const goToNextMedia = () => {
    const currentBanner = banners[currentBannerIndex]
    if (!currentBanner) return
    setCurrentMediaIndex((prev) => (prev + 1) % currentBanner.media_files.length)
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

  if (banners.length === 0) {
    return null
  }

  const currentBanner = banners[currentBannerIndex]
  const currentMedia = currentBanner.media_files[currentMediaIndex]

  const getFullUrl = (url: string) => {
    if (!url) return ''
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return url
    }
    // Динамически определяем базовый URL для работы на мобильных устройствах
    let apiBase = process.env.NEXT_PUBLIC_API_BASE
    if (!apiBase && typeof window !== 'undefined') {
      const origin = window.location.origin
      // Если порт 3001 (frontend), заменяем на 8000 (backend)
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

  // Функция для определения типа видео URL (YouTube, Vimeo, прямой файл)
  const getVideoEmbedUrl = (url: string): string | null => {
    if (!url) return null
    
    // YouTube - проверяем, является ли URL уже embed URL
    if (url.includes('youtube.com/embed/')) {
      // Уже embed URL, просто добавляем параметры если их нет
      if (!url.includes('?')) {
        return `${url}?autoplay=1&loop=1&muted=1&controls=0&showinfo=0&rel=0`
      } else if (!url.includes('autoplay')) {
        return `${url}&autoplay=1&loop=1&muted=1&controls=0&showinfo=0&rel=0`
      }
      return url
    }
    
    // Извлекаем ID из любого формата YouTube URL (включая мобильные версии и Shorts)
    if (url.includes('youtube.com') || url.includes('youtu.be')) {
      // Поддерживаем: /watch?v=, /embed/, /shorts/, youtu.be/, m.youtube.com/
      // Для обычных видео ID всегда 11 символов, для Shorts может быть разной длины
      let videoId = null
      
      // Сначала пробуем стандартный формат (11 символов)
      const standardRegex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})/
      let match = url.match(standardRegex)
      
      // Если не нашли, пробуем формат Shorts (может быть разной длины)
      if (!match) {
        const shortsRegex = /(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?\/\s]+)/
        match = url.match(shortsRegex)
      }
      
      if (match && match[1]) {
        videoId = match[1]
        return `https://www.youtube.com/embed/${videoId}?autoplay=1&loop=1&muted=1&playlist=${videoId}&controls=0&showinfo=0&rel=0`
      } else {
        // Если не удалось извлечь ID, возвращаем null
        console.warn('Invalid YouTube URL format:', url)
        return null
      }
    }
    
    // Vimeo - проверяем, является ли URL уже player URL
    if (url.includes('player.vimeo.com/video/')) {
      // Уже player URL, просто добавляем параметры если их нет
      if (!url.includes('?')) {
        return `${url}?autoplay=1&loop=1&muted=1&background=1`
      } else if (!url.includes('autoplay')) {
        return `${url}&autoplay=1&loop=1&muted=1&background=1`
      }
      return url
    }
    
    // Извлекаем ID из обычного Vimeo URL
    const vimeoRegex = /(?:vimeo\.com\/)(\d+)/
    const vimeoMatch = url.match(vimeoRegex)
    if (vimeoMatch && vimeoMatch[1]) {
      return `https://player.vimeo.com/video/${vimeoMatch[1]}?autoplay=1&loop=1&muted=1&background=1`
    }
    
    // Прямой файл - возвращаем как есть
    return null
  }

  const renderMedia = () => {
    if (!currentMedia || !currentMedia.content_url) {
      return (
        <div className="w-full h-full flex items-center justify-center bg-gray-200 text-gray-400">
          <span>Нет контента</span>
        </div>
      )
    }

    const fullUrl = getFullUrl(currentMedia.content_url)

    // Отладочная информация
    if (process.env.NODE_ENV === 'development') {
      console.log('Banner media:', {
        type: currentMedia.content_type,
        originalUrl: currentMedia.content_url,
        fullUrl,
        mimeType: currentMedia.content_mime_type
      })
    }

    const contentElement = (
      <>
        {currentMedia.content_type === 'image' && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={fullUrl}
            alt={currentBanner.title || 'Banner'}
            className="w-full h-full object-cover block"
            style={{ minHeight: '100%', minWidth: '100%' }}
            onError={(e) => {
              console.error('Failed to load banner image:', fullUrl)
              const target = e.currentTarget
              target.style.display = 'none'
              const placeholder = target.parentElement?.querySelector('.banner-placeholder')
              if (placeholder) {
                (placeholder as HTMLElement).style.display = 'flex'
              }
            }}
            onLoad={() => {
              console.log('Banner image loaded:', fullUrl)
            }}
          />
        )}
        {currentMedia.content_type === 'gif' && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={fullUrl}
            alt={currentBanner.title || 'Banner'}
            className="w-full h-full object-cover block"
            style={{ minHeight: '100%', minWidth: '100%' }}
            onError={(e) => {
              console.error('Failed to load banner GIF:', fullUrl)
              const target = e.currentTarget
              target.style.display = 'none'
              const placeholder = target.parentElement?.querySelector('.banner-placeholder')
              if (placeholder) {
                (placeholder as HTMLElement).style.display = 'flex'
              }
            }}
            onLoad={() => {
              console.log('Banner GIF loaded:', fullUrl)
            }}
          />
        )}
        {currentMedia.content_type === 'video' && (() => {
          const embedUrl = getVideoEmbedUrl(fullUrl)
          
          // Если это YouTube или Vimeo, используем iframe
          if (embedUrl) {
            return (
              <iframe
                src={embedUrl}
                className="w-full h-full object-cover block"
                style={{ minHeight: '100%', minWidth: '100%', border: 'none' }}
                allow="autoplay; encrypted-media"
                allowFullScreen
                onError={(e) => {
                  console.error('Failed to load banner video embed:', embedUrl)
                }}
              />
            )
          }
          
          // Прямой видеофайл - используем тег video с поддержкой разных форматов
          const videoExt = fullUrl.split('.').pop()?.toLowerCase()
          const mimeType = currentMedia.content_mime_type || 
            (videoExt === 'mp4' ? 'video/mp4' : 
             videoExt === 'webm' ? 'video/webm' : 
             videoExt === 'ogg' ? 'video/ogg' : 'video/mp4')
          
          return (
            <video
              autoPlay
              loop
              muted
              playsInline
              className="w-full h-full object-cover block"
              style={{ minHeight: '100%', minWidth: '100%' }}
              onError={(e) => {
                console.error('Failed to load banner video:', fullUrl, mimeType)
                const target = e.currentTarget
                target.style.display = 'none'
                const placeholder = target.parentElement?.querySelector('.banner-placeholder')
                if (placeholder) {
                  (placeholder as HTMLElement).style.display = 'flex'
                }
              }}
              onLoadedData={() => {
                console.log('Banner video loaded:', fullUrl, mimeType)
              }}
            >
              <source src={fullUrl} type={mimeType} />
              {/* Fallback для разных форматов */}
              {videoExt !== 'mp4' && <source src={fullUrl.replace(/\.(webm|ogg)$/i, '.mp4')} type="video/mp4" />}
              {videoExt !== 'webm' && <source src={fullUrl.replace(/\.(mp4|ogg)$/i, '.webm')} type="video/webm" />}
              Ваш браузер не поддерживает видео.
            </video>
          )
        })()}
        <div className="banner-placeholder hidden absolute inset-0 w-full h-full items-center justify-center bg-gray-200 text-gray-400">
          <span>Ошибка загрузки контента</span>
        </div>
      </>
    )

    const activeLink = currentMedia.link_url || currentBanner.link_url
    const isExternal = (link: string) => /^https?:\/\//.test(link)

    const handleNavigation = () => {
      if (!activeLink) return
      if (isExternal(activeLink)) {
        window.open(activeLink, '_blank', 'noopener, noreferrer')
      } else {
        router.push(activeLink)
      }
    }

    if (activeLink) {
      return (
        <div
          role="link"
          tabIndex={0}
          onClick={(event) => {
            event.stopPropagation()
            handleNavigation()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              handleNavigation()
            }
          }}
          className="w-full h-full cursor-pointer"
        >
          {contentElement}
        </div>
      )
    }

    return <div className="w-full h-full">{contentElement}</div>
  }

  const hasMultipleBanners = banners.length > 1
  const hasMultipleMedia = currentBanner.media_files.length > 1

  return (
    <div className={`relative w-full rounded-xl overflow-hidden shadow-lg ${className}`}>
      <div className="relative h-64 md:h-96 lg:h-[500px] w-full">
        {/* Контент медиа */}
        <div className="absolute inset-0 w-full h-full z-0">
          {renderMedia()}
        </div>
        
        {/* Текст баннера (заголовок и ссылка) - поверх медиа */}
        {(currentBanner.title || currentBanner.link_text) && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center px-4 text-center pointer-events-none">
            {currentBanner.title && (
              <h2 className="text-2xl md:text-4xl lg:text-5xl font-bold text-white mb-4 drop-shadow-lg">
                {currentBanner.title}
              </h2>
            )}
            {currentBanner.link_text && currentBanner.link_url && (
              <a
                href={currentBanner.link_url}
                className="inline-block mt-4 px-6 py-3 bg-white text-red-600 font-semibold rounded-lg shadow-lg hover:bg-red-50 transition-all duration-200 hover:scale-105 pointer-events-auto"
                onClick={(e) => {
                  e.stopPropagation()
                  e.preventDefault()
                  const isExternal = (link: string) => /^https?:\/\//.test(link)
                  if (isExternal(currentBanner.link_url!)) {
                    window.open(currentBanner.link_url, '_blank', 'noopener, noreferrer')
                  } else {
                    router.push(currentBanner.link_url!)
                  }
                }}
              >
                {currentBanner.link_text}
              </a>
            )}
          </div>
        )}
        
        {/* Навигационные стрелки для медиа (внутри баннера) */}
        {hasMultipleMedia && (
          <>
            <button
              onClick={goToPreviousMedia}
              className="absolute left-4 top-1/2 -translate-y-1/2 z-30 bg-white/90 hover:bg-white text-gray-800 rounded-full p-2 shadow-lg transition-all duration-200 hover:scale-110"
              aria-label="Предыдущее медиа"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button
              onClick={goToNextMedia}
              className="absolute right-4 top-1/2 -translate-y-1/2 z-30 bg-white/90 hover:bg-white text-gray-800 rounded-full p-2 shadow-lg transition-all duration-200 hover:scale-110"
              aria-label="Следующее медиа"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </>
        )}

        {/* Навигационные стрелки для баннеров (если несколько баннеров) */}
        {hasMultipleBanners && (
          <>
            <button
              onClick={goToPreviousBanner}
              className="absolute left-16 top-1/2 -translate-y-1/2 z-30 bg-white/90 hover:bg-white text-gray-800 rounded-full p-2 shadow-lg transition-all duration-200 hover:scale-110"
              aria-label="Предыдущий баннер"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>
            <button
              onClick={goToNextBanner}
              className="absolute right-16 top-1/2 -translate-y-1/2 z-30 bg-white/90 hover:bg-white text-gray-800 rounded-full p-2 shadow-lg transition-all duration-200 hover:scale-110"
              aria-label="Следующий баннер"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
              </svg>
            </button>
          </>
        )}

        {/* Индикаторы медиа (внутри баннера) */}
        {hasMultipleMedia && (
          <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-30 flex gap-2">
            {currentBanner.media_files.map((_, index) => (
              <button
                key={index}
                onClick={() => goToMedia(index)}
                className={`h-2 rounded-full transition-all duration-200 ${
                  index === currentMediaIndex
                    ? 'w-8 bg-white'
                    : 'w-2 bg-white/50 hover:bg-white/75'
                }`}
                aria-label={`Перейти к медиа ${index + 1}`}
              />
            ))}
          </div>
        )}

        {/* Индикаторы баннеров (если несколько баннеров) */}
        {hasMultipleBanners && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-30 flex gap-2">
            {banners.map((_, index) => (
              <button
                key={index}
                onClick={() => goToBanner(index)}
                className={`h-2 rounded-full transition-all duration-200 ${
                  index === currentBannerIndex
                    ? 'w-8 bg-white'
                    : 'w-2 bg-white/50 hover:bg-white/75'
                }`}
                aria-label={`Перейти к баннеру ${index + 1}`}
              />
            ))}
          </div>
        )}
      </div>
      
      {/* Точки навигации под баннерами (как у карточек) */}
      {hasMultipleBanners && (
        <div className="w-full flex justify-center items-center py-4 mt-4">
          <div className="flex justify-center items-center gap-2.5 px-4 py-2">
            {banners.map((_, index) => (
              <button
                key={index}
                onClick={() => goToBanner(index)}
                className="transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 rounded-full"
                style={{
                  width: index === currentBannerIndex ? '14px' : '10px',
                  height: index === currentBannerIndex ? '14px' : '10px',
                  borderRadius: '50%',
                  border: index === currentBannerIndex ? 'none' : '2px solid #9ca3af',
                  backgroundColor: index === currentBannerIndex ? '#111827' : '#ffffff',
                  cursor: 'pointer',
                  boxShadow:
                    index === currentBannerIndex
                      ? '0 2px 8px rgba(0,0,0,0.4), 0 0 0 2px rgba(255,255,255,0.5)'
                      : '0 1px 3px rgba(0,0,0,0.2)',
                }}
                aria-label={`Перейти к баннеру ${index + 1}`}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
