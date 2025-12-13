import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/router'
import api from '../lib/api'
import styles from './BannerCarousel.module.css'
import { resolveMediaUrl } from '../lib/media'

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
}

export default function BannerCarouselMedia({ position, className = '' }: BannerCarouselProps) {
  const router = useRouter()
  const [banner, setBanner] = useState<Banner | null>(null)
  const [displayMedia, setDisplayMedia] = useState<BannerMedia[]>([])
  const [activeMediaId, setActiveMediaId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const autoPlayIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const lastManualActionRef = useRef<number>(0)

  const hasMediaContent = (media: BannerMedia | null | undefined) => {
    if (!media) return false
    const trimVal = (v: any) => (typeof v === 'string' ? v.trim() : '')
    return !!(trimVal(media.title) || trimVal(media.description) || (trimVal(media.link_text) && trimVal(media.link_url)))
  }

  const rotateActiveToContent = (list: BannerMedia[]) => {
    if (list.length <= 1) return list
    const res = [...list]
    const max = res.length
    
    console.log('🔄 rotateActiveToContent called')
    console.log('Input:', res.map((m, i) => `${i}:${m.id}`))
    
    for (let i = 0; i < max; i++) {
      // Активный элемент теперь ВСЕГДА на позиции 0 (nth-child(1))
      const active = res[0]
      if (hasMediaContent(active)) {
        console.log('Output (after', i, 'rotations):', res.map((m, i) => `${i}:${m.id}`))
        return res
      }
      const first = res.shift()
      if (first) res.push(first)
    }
    
    console.log('Output (after max rotations):', res.map((m, i) => `${i}:${m.id}`))
    return res
  }

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
          const initialList = mediaFiles.slice(0, Math.min(6, mediaFiles.length))
          const displayMediaList = rotateActiveToContent(initialList)
          setDisplayMedia(displayMediaList)
          
          // Устанавливаем активный медиа: если медиа одно - первое, если несколько - второе (index 1)
          if (displayMediaList.length > 0) {
            const activeMedia = displayMediaList.length === 1 ? displayMediaList[0] : displayMediaList[1]
            setActiveMediaId(activeMedia.id)
          }
          
          console.log('🎨 Banner loaded with media:', {
            bannerId: firstBanner.id,
            title: firstBanner.title,
            mediaCount: mediaFiles.length,
            displayCount: displayMediaList.length,
            activeMediaId: displayMediaList.length === 1 ? displayMediaList[0]?.id : displayMediaList[1]?.id
          })
          
          // Детальное логирование данных медиа
          displayMediaList.forEach((media: BannerMedia, idx: number) => {
            console.log(`📦 Media [${idx}]:`, {
              id: media.id,
              title: media.title || '❌ НЕТ',
              description: media.description || '❌ НЕТ',
              link_text: media.link_text || '❌ НЕТ',
              link_url: media.link_url || '❌ НЕТ',
              hasTitle: !!media.title,
              hasDescription: !!media.description,
              hasLink: !!(media.link_text && media.link_url)
            })
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

  // Принудительное обновление при изменении активного медиа для запуска анимации
  useEffect(() => {
    if (displayMedia.length > 0) {
      // Активный элемент всегда на позиции 0 (nth-child(1))
      const activeMedia = displayMedia[0]
      if (activeMedia) {
        setActiveMediaId(activeMedia.id)
      }
    }
  }, [displayMedia])

  const goToPreviousMedia = () => {
    if (!banner || displayMedia.length <= 1) return
    
    console.log('⬅️ PREVIOUS button clicked')
    console.log('Before:', displayMedia.map((m, i) => `${i}:${m.id}`))
    
    // Отмечаем ручное действие
    lastManualActionRef.current = Date.now()
    resetAutoPlay()
    
    // Для PREVIOUS: берем ПОСЛЕДНИЙ элемент и помещаем его в НАЧАЛО (активная позиция nth-child(1))
    // Текущий активный (nth-child(1)) сдвинется на nth-child(2) и станет миниатюрой
    const newMedia = [...displayMedia]
    const lastItem = newMedia.pop()
    if (lastItem) {
      newMedia.unshift(lastItem)
    }
    
    console.log('After:', newMedia.map((m, i) => `${i}:${m.id}`))
    
    setDisplayMedia(newMedia)
    
    // Активный элемент всегда на позиции 0 (первый элемент, nth-child(1))
    const activeMedia = newMedia[0]
    if (activeMedia) {
      console.log('New active media:', activeMedia.id)
      setActiveMediaId(activeMedia.id)
    }
  }

  const goToNextMedia = () => {
    if (!banner || displayMedia.length <= 1) return
    
    console.log('➡️ NEXT button clicked')
    console.log('Before:', displayMedia.map((m, i) => `${i}:${m.id}`))
    
    // Отмечаем ручное действие
    lastManualActionRef.current = Date.now()
    resetAutoPlay()
    
    // Для NEXT: берем ПЕРВЫЙ элемент (активный nth-child(1)) и перемещаем в КОНЕЦ
    // Второй элемент (nth-child(2)) станет активным (переместится на nth-child(1))
    const newMedia = [...displayMedia]
    const firstItem = newMedia.shift()
    if (firstItem) {
      newMedia.push(firstItem)
    }
    
    console.log('After:', newMedia.map((m, i) => `${i}:${m.id}`))
    
    setDisplayMedia(newMedia)
    
    // Активный элемент всегда на позиции 0 (первый элемент, nth-child(1))
    const activeMedia = newMedia[0]
    if (activeMedia) {
      console.log('New active media:', activeMedia.id)
      setActiveMediaId(activeMedia.id)
    }
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
    // Активность определяем по id, а не только по индексу, чтобы текст был сразу
    const isActive =
      activeMediaId !== null
        ? media.id === activeMediaId
        : displayMedia.length === 1
          ? index === 0
          : index === 1
    
    const fullUrl = resolveMediaUrl(media.content_url)
    const embedUrl = media.content_type === 'video' ? getVideoEmbedUrl(fullUrl) : null

    const handleThumbnailClick = () => {
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
        const rotated = rotateActiveToContent(newMedia)
        const activeMedia = rotated.length === 1 ? rotated[0] : rotated[1]
        if (activeMedia) {
          setActiveMediaId(activeMedia.id)
        }
        setDisplayMedia(rotated)
      }
    }
    
    // Обработчик клика только для больших картинок (не для миниатюр)
    const handleLargeImageClick = () => {
      // Для больших картинок клик не должен ничего делать
      // Контент должен быть виден сразу
    }

    // Используем только данные из медиа (без fallback на баннер)
    // Проверяем, что значения не пустые строки и не null/undefined
    // Используем строгую проверку, чтобы избежать проблем с пустыми строками
    const getTrimmedValue = (value: any): string | null => {
      if (!value || typeof value !== 'string') return null
      const trimmed = value.trim()
      return trimmed.length > 0 ? trimmed : null
    }
    
    // Берём данные из медиа, если их нет — подставляем из баннера, чтобы текст был сразу
    const title = getTrimmedValue(media.title) ?? getTrimmedValue(banner?.title)
    const description = getTrimmedValue(media.description) ?? getTrimmedValue(banner?.description)
    const linkText = getTrimmedValue(media.link_text) ?? getTrimmedValue(banner?.link_text)
    const linkUrl = getTrimmedValue(media.link_url) ?? getTrimmedValue(banner?.link_url)
    
    // Проверяем, есть ли у медиа свои собственные данные для отображения
    // Учитываем, что значения могут быть пустыми строками
    const hasMediaContent = !!(title || description || (linkText && linkUrl))
    
    // Контент показываем только для активного элемента с данными, и только для больших (index < 2)
    const shouldShowContent = isActive && index < 2 && hasMediaContent
    
    // Отладка для активного элемента с данными
    if (isActive && typeof window !== 'undefined' && hasMediaContent) {
      console.log(`✅ Active media WITH CONTENT [index ${index}]:`, {
        mediaId: media.id,
        isActive,
        index,
        shouldShowContent,
        hasMediaContent,
        displayMediaLength: displayMedia.length,
        title: title || 'null',
        description: description || 'null',
        linkText: linkText || 'null',
        linkUrl: linkUrl || 'null',
        willRender: shouldShowContent,
        timestamp: Date.now()
      })
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
        onClick={index >= 2 ? handleThumbnailClick : handleLargeImageClick}
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

        {/* Контент с текстом - показываем только на большой картинке и только если у медиа есть свои данные */}
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
            {linkText && linkUrl && (
              <button
                className={styles.button}
                onClick={(e) => {
                  e.stopPropagation()
                  const isExternal = /^https?:\/\//.test(linkUrl)
                  if (isExternal) {
                    window.open(linkUrl, '_blank', 'noopener, noreferrer')
                  } else {
                    router.push(linkUrl)
                  }
                }}
              >
                {linkText}
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
      <div className={styles.slide}>
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

