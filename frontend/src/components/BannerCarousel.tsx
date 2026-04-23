import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import styles from './BannerCarousel.module.css'
import { resolveMediaUrl, getVideoEmbedUrl } from '../lib/media'

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
  initialBanners?: Banner[]
}

export default function BannerCarousel({ position, className = '', initialBanners = [] }: BannerCarouselProps) {
  const router = useRouter()
  const { t } = useTranslation('common')
  const [banners, setBanners] = useState<Banner[]>(initialBanners)
  const [displayBanners, setDisplayBanners] = useState<Banner[]>(initialBanners.slice(0, Math.min(6, initialBanners.length)))
  const [currentBannerIndex, setCurrentBannerIndex] = useState(0)
  const [currentMediaIndex, setCurrentMediaIndex] = useState(0)
  const [loading, setLoading] = useState(initialBanners.length === 0)
  const slideRef = useRef<HTMLDivElement>(null)

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
        // Инициализируем displayBanners
        // В слайдере: первые два элемента - большие, второй активный с контентом, остальные - миниатюры справа
        if (bannersWithMedia.length > 0) {
          console.log('=== BannerCarousel: Loaded banners ===')
          console.log('Position:', position)
          console.log('Count:', bannersWithMedia.length)
          bannersWithMedia.forEach((b, i) => {
            console.log(`Banner ${i + 1}:`, {
              id: b.id,
              title: b.title || 'НЕТ ЗАГОЛОВКА',
              link_text: b.link_text || 'НЕТ ТЕКСТА ССЫЛКИ',
              link_url: b.link_url || 'НЕТ URL',
              media_count: b.media_files.length
            })
          })
          console.log('=======================================')
          setDisplayBanners(bannersWithMedia.slice(0, Math.min(6, bannersWithMedia.length)))
          setCurrentBannerIndex(0)
          setCurrentMediaIndex(0)
        } else {
          setDisplayBanners([])
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
  }, [position, router.locale])

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
      setDisplayBanners((prev) => {
        const newBanners = [...prev]
        const firstBanner = newBanners.shift()
        if (firstBanner) {
          newBanners.push(firstBanner)
        }
        return newBanners
      })
      setCurrentBannerIndex((prev) => (prev + 1) % banners.length)
      setCurrentMediaIndex(0) // Сбрасываем индекс медиа при смене баннера
    }, 10000)

    return () => clearInterval(interval)
  }, [banners.length])

  const goToBanner = (index: number) => {
    const targetBanner = banners[index]
    // Пересоздаем displayBanners так, чтобы целевой баннер был на позиции 1 (активная)
    const newBanners = [...banners]
    // Находим индекс целевого баннера
    const targetIndexInBanners = newBanners.findIndex(b => b.id === targetBanner.id)
    if (targetIndexInBanners !== -1) {
      // Перемещаем элементы так, чтобы целевой был на позиции 1
      const before = newBanners.slice(0, targetIndexInBanners)
      const after = newBanners.slice(targetIndexInBanners + 1)
      const reordered = [targetBanner, ...after, ...before]
      setDisplayBanners(reordered.slice(0, Math.min(6, reordered.length)))
    }
    setCurrentBannerIndex(index)
    setCurrentMediaIndex(0)
  }

  const goToPreviousBanner = () => {
    if (banners.length <= 1) return
    
    console.log('⬅️ PREVIOUS button clicked')
    console.log('Before:', displayBanners.map((b, i) => `${i}:${b.id}`))
    
    // Вычисляем новый порядок баннеров
    const newBanners = [...displayBanners]
      const lastBanner = newBanners.pop()
      if (lastBanner) {
        newBanners.unshift(lastBanner)
      }
    
    console.log('After:', newBanners.map((b, i) => `${i}:${b.id}`))
    
    // Определяем новый активный баннер (на позиции 1)
      const activeBanner = newBanners[1] || newBanners[0]
      if (activeBanner) {
        const bannerIndex = banners.findIndex(b => b.id === activeBanner.id)
        if (bannerIndex !== -1) {
        console.log('New active banner index:', bannerIndex, 'ID:', activeBanner.id)
          setCurrentBannerIndex(bannerIndex)
        }
      }
    
    // Обновляем состояния
    setDisplayBanners(newBanners)
    setCurrentMediaIndex(0)
  }

  const goToNextBanner = () => {
    if (banners.length <= 1) return
    
    console.log('➡️ NEXT button clicked')
    console.log('Before:', displayBanners.map((b, i) => `${i}:${b.id}`))
    
    // Вычисляем новый порядок баннеров
    const newBanners = [...displayBanners]
      const firstBanner = newBanners.shift()
      if (firstBanner) {
        newBanners.push(firstBanner)
      }
    
    console.log('After:', newBanners.map((b, i) => `${i}:${b.id}`))
    
    // Определяем новый активный баннер (на позиции 1)
      const activeBanner = newBanners[1] || newBanners[0]
      if (activeBanner) {
        const bannerIndex = banners.findIndex(b => b.id === activeBanner.id)
        if (bannerIndex !== -1) {
        console.log('New active banner index:', bannerIndex, 'ID:', activeBanner.id)
          setCurrentBannerIndex(bannerIndex)
        }
      }
    
    // Обновляем состояния
    setDisplayBanners(newBanners)
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

  const hasMultipleBanners = banners.length > 1
  // Активный баннер - второй элемент (index 1), как в оригинальном примере
  const activeIndex = 1
  const currentBanner = displayBanners[activeIndex] || displayBanners[0] || banners[currentBannerIndex]
  const currentMedia = currentBanner?.media_files[currentMediaIndex]

  const renderBannerItem = (banner: Banner, index: number) => {
    // Для активного баннера используем currentMediaIndex
    // Если баннер один - index 0, если больше одного - index 1
    const isActive = displayBanners.length === 1 ? index === 0 : index === 1
    const mediaIndex = isActive ? currentMediaIndex : 0
    const media = banner.media_files[mediaIndex] || banner.media_files[0]
    const fullUrl = media ? resolveMediaUrl(media.content_url) : ''
    const embedUrl = media && media.content_type === 'video' ? getVideoEmbedUrl(fullUrl, 'ambient') : null

    // Отладка для КАЖДОГО элемента
    if (typeof window !== 'undefined') {
      console.log(`📌 Banner index ${index}:`, {
        id: banner.id,
        isActive,
        displayCount: displayBanners.length,
        title: banner.title || '❌ НЕТ',
        link_text: banner.link_text || '❌ НЕТ',
        hasMedia: !!media
      })
    }

    // Отладка для активного элемента
    if (isActive && typeof window !== 'undefined') {
      console.log('🔵 ACTIVE BANNER:', {
        index,
        id: banner.id,
        title: banner.title || '❌ НЕТ ЗАГОЛОВКА',
        link_text: banner.link_text || '❌ НЕТ ТЕКСТА',
        link_url: banner.link_url || '❌ НЕТ URL',
        hasMedia: !!media,
        mediaUrl: media?.content_url || '❌ НЕТ МЕДИА'
      })
    }

    // Обработчик клика на баннер
    const handleBannerClick = () => {
      // Если кликнули на миниатюру (index >= 2), делаем её активной
      if (index >= 2 && displayBanners.length > 1) {
        // Перемещаем элементы так, чтобы кликнутый был на позиции 1 (активный)
        // Количество шагов = index - 1 (чтобы элемент стал на позицию 1)
        const steps = index - 1
        const newBanners = [...displayBanners]
        for (let i = 0; i < steps; i++) {
          const firstBanner = newBanners.shift()
          if (firstBanner) {
            newBanners.push(firstBanner)
          }
        }
        
        setDisplayBanners(newBanners.slice(0, Math.min(6, newBanners.length)))
        
        // Обновляем currentBannerIndex
        const bannerIndex = banners.findIndex(b => b.id === banner.id)
        if (bannerIndex !== -1) {
          setCurrentBannerIndex(bannerIndex)
        }
        setCurrentMediaIndex(0)
      } else if (isActive && banner.link_url) {
        // Если кликнули на активный элемент с ссылкой, переходим по ссылке
        const isExternal = /^https?:\/\//.test(banner.link_url)
        if (isExternal) {
          window.location.href = banner.link_url
        } else {
          router.push(banner.link_url)
        }
      }
    }

    return (
      <div
        key={`banner-${banner.id}-pos-${index}`}
        className={styles.item}
        onClick={handleBannerClick}
      >
        {/* Фоновое изображение через <img> для оптимизации LCP */}
        {media && (media.content_type === 'image' || media.content_type === 'gif') && (
          <img
            src={fullUrl}
            alt={banner.title || ''}
            className={styles.itemImage}
            fetchPriority={isActive ? "high" : "auto"}
            loading={isActive ? "eager" : "lazy"}
            decoding="async"
            draggable={false}
          />
        )}

        {/* Видео контент */}
        {media && media.content_type === 'video' && embedUrl && (
          <iframe
            src={embedUrl}
            className={styles.itemIframe}
            allow="autoplay; encrypted-media"
            allowFullScreen
          />
        )}
        {media && media.content_type === 'video' && !embedUrl && (
          <video
            autoPlay
            loop
            muted
            playsInline
            preload={isActive ? "auto" : "metadata"}
            className={styles.itemVideo}
          >
            <source src={fullUrl} type={media.content_mime_type || 'video/mp4'} />
          </video>
        )}

        {/* Контент с текстом */}
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
                e.stopPropagation() // Предотвращаем всплытие клика на родительский элемент
                const isExternal = /^https?:\/\//.test(banner.link_url!)
                if (isExternal) {
                  window.location.href = banner.link_url!
                } else {
                  router.push(banner.link_url!)
                }
              }}
            >
              {banner.link_text && banner.link_text.trim().toLowerCase() === 'learn more' 
                ? t('view_product_details', 'Узнать подробнее о товаре') 
                : (banner.link_text || t('view_details', 'Подробнее'))}
            </button>
          )}
        </div>
      </div>
    )
  }

  // Лог перед рендером
  if (typeof window !== 'undefined' && displayBanners.length > 0) {
    console.log('🎬 RENDER:', {
      displayBannersCount: displayBanners.length,
      bannerIds: displayBanners.map((b, i) => `${i}:${b.id}`),
      activeIndex: 1,
      hasMultipleBanners
    })
  }

  return (
    <div className={`${styles.container} ${className}`}>
      <div ref={slideRef} className={styles.slide}>
        {displayBanners.map((banner, index) => renderBannerItem(banner, index))}
      </div>

      {hasMultipleBanners && (
        <div className={styles.buttonContainer}>
          <button
            className={styles.navButton}
            onClick={goToPreviousBanner}
            aria-label="Предыдущий баннер"
          >
            <svg className={styles.icon} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            className={styles.navButton}
            onClick={goToNextBanner}
            aria-label="Следующий баннер"
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
