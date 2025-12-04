import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import Link from 'next/link'
import api from '../lib/api'
import { StarIcon } from '@heroicons/react/20/solid'
import { SpeakerWaveIcon, SpeakerXMarkIcon } from '@heroicons/react/24/outline'

interface TestimonialMedia {
  id: number
  media_type: 'image' | 'video' | 'video_file'
  image_url: string | null
  video_url: string | null
  video_file_url: string | null
  order: number
}

interface Testimonial {
  id: number
  author_name: string
  author_avatar_url: string | null
  text: string
  rating: number | null
  media: TestimonialMedia[]
  created_at: string
  user_id?: number | null
  user_username?: string | null
}

interface TestimonialsCarouselProps {
  className?: string
}

function classNames(...classes: (string | boolean)[]) {
  return classes.filter(Boolean).join(' ')
}

export default function TestimonialsCarousel({ className = '' }: TestimonialsCarouselProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const [testimonials, setTestimonials] = useState<Testimonial[]>([])
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(0)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const autoPlayRef = useRef<NodeJS.Timeout | null>(null)
  const videoRefs = useRef<Map<number, HTMLVideoElement>>(new Map())
  const [videoMuted, setVideoMuted] = useState<Map<number, boolean>>(new Map())
  const itemsPerPage = 3 // A "page" for pagination dots

  useEffect(() => {
    const fetchTestimonials = async () => {
      try {
        const response = await api.get('/feedback/testimonials/')
        const data = response.data
        const testimonialsList = Array.isArray(data) ? data : data.results || []
        // Отладочная информация для проверки данных
        console.log('Testimonials loaded:', testimonialsList.map(t => ({
          id: t.id,
          author_name: t.author_name,
          user_id: t.user_id,
          user_username: t.user_username,
          hasUser: !!(t.user_id && t.user_username),
          user_id_type: typeof t.user_id,
          user_username_type: typeof t.user_username
        })))
        console.log('Full testimonials data (first item):', testimonialsList[0])
        console.log('First testimonial user_id:', testimonialsList[0]?.user_id)
        console.log('First testimonial user_username:', testimonialsList[0]?.user_username)
        testimonialsList.forEach((t, idx) => {
          console.log(`Testimonial ${idx + 1} (ID: ${t.id}): user_id=${t.user_id}, user_username=${t.user_username}`)
        })
        setTestimonials(testimonialsList)
      } catch (error) {
        console.error('Failed to fetch testimonials:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchTestimonials()
  }, [])

  const totalPages = Math.ceil(testimonials.length / itemsPerPage)

  const goToPage = (page: number) => {
    if (scrollContainerRef.current) {
      const card = scrollContainerRef.current.children[0] as HTMLElement
      if (card) {
        const cardWidth = card.offsetWidth
        const gap = 16 // Corresponds to `gap-4`
        const targetIndex = page * itemsPerPage
        const maxScrollLeft = scrollContainerRef.current.scrollWidth - scrollContainerRef.current.clientWidth
        const scrollAmount = Math.min(targetIndex * (cardWidth + gap), maxScrollLeft)
        
        scrollContainerRef.current.scrollTo({
          left: scrollAmount,
          behavior: 'smooth',
        })
      }
    }
  }

  useEffect(() => {
    if (totalPages <= 1) return
    const startAutoPlay = () => {
      autoPlayRef.current = setInterval(() => {
        if (scrollContainerRef.current) {
          const container = scrollContainerRef.current
          const card = container.children[0] as HTMLElement
          if (!card) return
          const cardWidth = card.offsetWidth
          const gap = 16
          const scrollAmount = cardWidth + gap
          if (container.scrollLeft + container.clientWidth >= container.scrollWidth - 1) {
            container.scrollTo({ left: 0, behavior: 'smooth' })
          } else {
            container.scrollBy({ left: scrollAmount, behavior: 'smooth' })
          }
        }
      }, 7000) // Slower scroll for testimonials
    }
    startAutoPlay()
    return () => {
      if (autoPlayRef.current) clearInterval(autoPlayRef.current)
    }
  }, [totalPages])

  // Единый обработчик для управления видео при скролле
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container || testimonials.length === 0) return

    let scrollTimeout: NodeJS.Timeout
    let pageUpdateTimeout: NodeJS.Timeout
    
    const checkAndControlVideos = () => {
      // Сначала останавливаем ВСЕ видео
      videoRefs.current.forEach((video) => {
        if (video && !video.paused) {
          video.pause()
        }
      })
      
      // Затем запускаем только те, которые видны
      videoRefs.current.forEach((video, testimonialId) => {
        if (!video || !video.parentElement) return
        
        const cardElement = video.closest('.flex-shrink-0') as HTMLElement
        if (!cardElement) return
        
        const containerRect = container.getBoundingClientRect()
        const cardRect = cardElement.getBoundingClientRect()
        
        // Проверяем, видна ли карточка в контейнере
        const isVisible = 
          cardRect.left < containerRect.right &&
          cardRect.right > containerRect.left
        
        if (isVisible) {
          // Вычисляем процент видимости
          const visibleWidth = Math.min(cardRect.right, containerRect.right) - Math.max(cardRect.left, containerRect.left)
          const visibleRatio = Math.max(0, visibleWidth / cardRect.width)
          
          // Если карточка видна на 30% и более - воспроизводим
          if (visibleRatio >= 0.3) {
            const isMuted = videoMuted.get(testimonialId) !== false
            video.muted = isMuted
            video.play().catch(() => {})
          }
        }
      })
    }
    
    const handleScroll = () => {
      // Немедленно проверяем и контролируем видео
      checkAndControlVideos()
      
      // Обновление страницы с debounce
      clearTimeout(pageUpdateTimeout)
      pageUpdateTimeout = setTimeout(() => {
        const card = container.children[0] as HTMLElement
        if (!card) return
        
        const cardWidth = card.offsetWidth
        const gap = 16
        const pageWidth = itemsPerPage * (cardWidth + gap)
        const newPage = Math.floor((container.scrollLeft + pageWidth / 2) / pageWidth)
        if (newPage < totalPages && newPage !== currentPage) {
          setCurrentPage(newPage)
        }
      }, 100)
    }
    
    // Используем throttling для скролла (не debounce!)
    let lastScrollTime = 0
    const throttledHandleScroll = () => {
      const now = Date.now()
      if (now - lastScrollTime >= 50) { // Проверяем каждые 50мс
        lastScrollTime = now
        handleScroll()
      } else {
        // Если прошло меньше 50мс, планируем проверку
        clearTimeout(scrollTimeout)
        scrollTimeout = setTimeout(handleScroll, 50 - (now - lastScrollTime))
      }
    }
    
    container.addEventListener('scroll', throttledHandleScroll, { passive: true })
    
    // Первоначальная проверка
    checkAndControlVideos()
    
    // Периодическая проверка на случай пропущенных событий
    const intervalId = setInterval(checkAndControlVideos, 200)
    
    return () => {
      container.removeEventListener('scroll', throttledHandleScroll)
      clearInterval(intervalId)
      clearTimeout(scrollTimeout)
      clearTimeout(pageUpdateTimeout)
    }
  }, [testimonials, videoMuted, currentPage, totalPages, itemsPerPage])

  // Останавливаем все видео при смене страницы
  useEffect(() => {
    videoRefs.current.forEach((video) => {
      if (video) {
        video.pause()
        video.currentTime = 0
      }
    })
  }, [currentPage])

  if (loading) return <div className={`py-12 ${className}`} />
  if (testimonials.length === 0) return null

  const renderMedia = (testimonial: Testimonial) => {
    // Используем массив media
    if (!testimonial.media || testimonial.media.length === 0) return null
    
    // Показываем только первый медиа элемент в карусели
    const firstMedia = testimonial.media[0]
    
    if (firstMedia.media_type === 'image' && firstMedia.image_url) {
      return (
        <img
          src={firstMedia.image_url}
          alt={t('testimonial_image_alt', `Изображение к отзыву от ${testimonial.author_name}`)}
          className="w-full h-full object-cover"
        />
      )
    }
    
    if (firstMedia.media_type === 'video' && firstMedia.video_url) {
      // Для YouTube/Vimeo видео добавляем autoplay и muted в URL
      let embedUrl = firstMedia.video_url
      let isValidEmbedUrl = false
      
      // Обработка YouTube URL - улучшенная версия, поддерживающая все форматы
      // Проверяем, является ли URL уже embed URL
      if (embedUrl.includes('youtube.com/embed/')) {
        // Уже embed URL, просто добавляем параметры если их нет
        if (!embedUrl.includes('?')) {
          embedUrl += '?autoplay=1&muted=1&loop=1&controls=1&modestbranding=1'
        } else if (!embedUrl.includes('autoplay')) {
          embedUrl += '&autoplay=1&muted=1&loop=1&controls=1&modestbranding=1'
        }
        isValidEmbedUrl = true
      } else if (embedUrl.includes('youtube.com') || embedUrl.includes('youtu.be')) {
        // Извлекаем ID из любого формата YouTube URL (включая мобильные версии и Shorts)
        // Поддерживаем: /watch?v=, /embed/, /shorts/, youtu.be/, m.youtube.com/
        // Для обычных видео ID всегда 11 символов, для Shorts может быть разной длины
        let videoId = null
        
        // Сначала пробуем стандартный формат (11 символов)
        const standardRegex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})/
        let match = embedUrl.match(standardRegex)
        
        // Если не нашли, пробуем формат Shorts (может быть разной длины)
        if (!match) {
          const shortsRegex = /(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?\/\s]+)/
          match = embedUrl.match(shortsRegex)
        }
        
        if (match && match[1]) {
          videoId = match[1]
        }
        
        if (videoId) {
          embedUrl = `https://www.youtube.com/embed/${videoId}?autoplay=1&muted=1&loop=1&playlist=${videoId}&controls=1&modestbranding=1&rel=0`
          isValidEmbedUrl = true
        } else {
          // Если не удалось извлечь ID, не показываем iframe
          console.warn('Invalid YouTube URL format:', embedUrl)
          return null
        }
      }
      
      // Обработка Vimeo URL
      if (embedUrl.includes('vimeo.com/') && !embedUrl.includes('player.vimeo.com')) {
        const vimeoRegex = /(?:vimeo\.com\/)(\d+)/
        const match = embedUrl.match(vimeoRegex)
        if (match && match[1]) {
          embedUrl = `https://player.vimeo.com/video/${match[1]}?autoplay=1&muted=1&loop=1&controls=1&background=0`
          isValidEmbedUrl = true
        } else {
          console.warn('Invalid Vimeo URL format:', embedUrl)
          return null
        }
      } else if (embedUrl.includes('player.vimeo.com')) {
        isValidEmbedUrl = true
      }
      
      // Показываем iframe только если URL валидный
      if (isValidEmbedUrl) {
      return (
        <iframe
          src={embedUrl}
          title={t('testimonial_video_alt', `Видео к отзыву от ${testimonial.author_name}`)}
          frameBorder="0"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full h-full"
        ></iframe>
      )
      }
      
      return null
    }
    
    if (firstMedia.media_type === 'video_file' && firstMedia.video_file_url) {
      const isMuted = videoMuted.has(testimonial.id) ? videoMuted.get(testimonial.id) : true
      return (
        <video
          ref={(el) => {
            if (el) {
              videoRefs.current.set(testimonial.id, el)
              el.muted = isMuted !== false
              if (!videoMuted.has(testimonial.id)) {
                setVideoMuted((prev) => {
                  const newMap = new Map(prev)
                  newMap.set(testimonial.id, true)
                  return newMap
                })
              }
            } else {
              videoRefs.current.delete(testimonial.id)
            }
          }}
          controls={false}
          muted={isMuted !== false}
          playsInline
          loop
          className="w-full h-full object-cover"
        >
          <source src={firstMedia.video_file_url} type="video/mp4" />
          {t('video_tag_unsupported', 'Ваш браузер не поддерживает видео.')}
        </video>
      )
    }
    
    return null
  }

  return (
    <section className={`py-12 ${className}`}>
      <div className="mx-auto max-w-6xl px-4">
        <h2 className="text-3xl font-bold text-gray-900 mb-8 text-center">
          {t('testimonials_title', 'Что говорят наши клиенты')}
        </h2>
        <div className="relative mb-8">
          <div
            ref={scrollContainerRef}
            className="flex gap-4 overflow-x-auto scrollbar-hide scroll-smooth py-4"
            style={{
              scrollbarWidth: 'none',
              msOverflowStyle: 'none',
            }}
          >
            {testimonials.map((testimonial) => {
              const hasUser = testimonial.user_id != null && testimonial.user_username
              if (hasUser) {
                console.log('Rendering testimonial with user:', {
                  id: testimonial.id,
                  user_id: testimonial.user_id,
                  user_username: testimonial.user_username
                })
              }
              return (
              <div
                key={testimonial.id}
                className="flex-shrink-0 w-64 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-xl transition-all duration-300 overflow-hidden group transform hover:-translate-y-2 hover:scale-[1.02] flex flex-col"
              >
                {testimonial.media && testimonial.media.length > 0 && (
                  <Link
                    href="/testimonials"
                    className="relative w-full aspect-[9/16] overflow-hidden bg-gray-100 block"
                    onClick={(e) => {
                      // Не перехватываем клик, если кликнули на кнопку пользователя
                      const target = e.target as HTMLElement
                      if (target.closest('button[type="button"]')) {
                        e.preventDefault()
                        e.stopPropagation()
                      }
                    }}
                  >
                    <div className="w-full h-full transition-transform duration-300 group-hover:scale-110">
                      {renderMedia(testimonial)}
                    </div>
                    <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                    {testimonial.media && testimonial.media.some(
                      m => m.media_type === 'video_file' && m.video_file_url
                    ) && (
                      <button
                        onClick={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          const video = videoRefs.current.get(testimonial.id)
                          if (video) {
                            const currentMuted = videoMuted.get(testimonial.id) !== false
                            const newMuted = !currentMuted
                            video.muted = newMuted
                            setVideoMuted((prev) => {
                              const newMap = new Map(prev)
                              newMap.set(testimonial.id, newMuted)
                              return newMap
                            })
                          }
                        }}
                        className="absolute top-2 right-2 z-20 p-2 rounded-full bg-black/50 hover:bg-black/70 text-white transition-all duration-200 hover:scale-110"
                        aria-label={videoMuted.get(testimonial.id) !== false ? 'Включить звук' : 'Выключить звук'}
                      >
                        {(videoMuted.get(testimonial.id) !== false) ? (
                          <SpeakerXMarkIcon className="w-5 h-5" />
                        ) : (
                          <SpeakerWaveIcon className="w-5 h-5" />
                        )}
                      </button>
                    )}
                  </Link>
                )}
                
                {/* Текст отзыва - по центру */}
                <Link
                  href="/testimonials"
                  className="flex-1 p-4 min-h-[100px] cursor-pointer"
                  onClick={(e) => {
                    // Не перехватываем клик, если кликнули на кнопку пользователя
                    const target = e.target as HTMLElement
                    if (target.closest('button[type="button"]')) {
                      e.preventDefault()
                      e.stopPropagation()
                    }
                  }}
                >
                  <p className="text-gray-600 text-sm line-clamp-4">
                    "{testimonial.text}"
                  </p>
                </Link>
                
                {/* Нижняя часть: аватарка + имя слева, звездочки справа */}
                <div className="p-4 pt-0 flex items-center justify-between border-t border-gray-100 mt-auto">
                  {testimonial.user_id != null && testimonial.user_username ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        console.log('Clicking on user profile:', {
                          username: testimonial.user_username,
                          userId: testimonial.user_id,
                          testimonialId: testimonial.id
                        })
                        const url = `/user/${testimonial.user_username}?testimonial_id=${testimonial.id}`
                        console.log('Navigating to:', url)
                        router.push(url).catch(err => {
                          console.error('Navigation error:', err)
                        })
                      }}
                      onMouseDown={(e) => {
                        e.stopPropagation()
                      }}
                      className="flex items-center flex-1 min-w-0 hover:opacity-80 transition-opacity cursor-pointer text-left bg-transparent border-none p-0 outline-none focus:outline-none"
                      title={`Профиль ${testimonial.author_name}`}
                      style={{ zIndex: 10 }}
                    >
                      {testimonial.author_avatar_url && (
                        <img
                          src={testimonial.author_avatar_url}
                          alt={testimonial.author_name}
                          className="w-8 h-8 rounded-full mr-3 object-cover flex-shrink-0 pointer-events-none"
                        />
                      )}
                      <div className="text-xs font-semibold text-gray-900 truncate pointer-events-none">
                        {testimonial.author_name}
                      </div>
                    </button>
                  ) : (
                  <div className="flex items-center flex-1 min-w-0">
                    {testimonial.author_avatar_url && (
                      <img
                        src={testimonial.author_avatar_url}
                        alt={testimonial.author_name}
                        className="w-8 h-8 rounded-full mr-3 object-cover flex-shrink-0"
                      />
                    )}
                    <div className="text-xs font-semibold text-gray-900 truncate">
                      {testimonial.author_name}
                    </div>
                  </div>
                  )}
                  {testimonial.rating && (
                    <div className="flex items-center ml-2 flex-shrink-0">
                      {[0, 1, 2, 3, 4].map((rating) => (
                        <StarIcon
                          key={rating}
                          className={`h-4 w-4 ${
                            (testimonial.rating || 0) > rating
                              ? 'text-yellow-400'
                              : 'text-gray-300'
                          }`}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>
              )
            })}
          </div>
        </div>

        {totalPages > 1 && (
          <div className="w-full flex justify-center items-center py-4">
            <div className="flex justify-center items-center gap-2.5 px-4 py-2">
              {Array.from({ length: totalPages }, (_, i) => i).map((pageIndex) => (
                <button
                  key={pageIndex}
                  onClick={() => goToPage(pageIndex)}
                  className="transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 rounded-full"
                  style={{
                    width: pageIndex === currentPage ? '14px' : '10px',
                    height: pageIndex === currentPage ? '14px' : '10px',
                    borderRadius: '50%',
                    border: pageIndex === currentPage ? 'none' : '2px solid #9ca3af',
                    backgroundColor: pageIndex === currentPage ? '#111827' : '#ffffff',
                    cursor: 'pointer',
                  }}
                  aria-label={`Перейти на страницу ${pageIndex + 1}`}
                />
              ))}
            </div>
          </div>
        )}
      </div>
      <style jsx>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
      `}</style>
    </section>
  )
}
