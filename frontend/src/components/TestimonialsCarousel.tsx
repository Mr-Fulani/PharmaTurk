import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { StarIcon } from '@heroicons/react/20/solid'
import { SpeakerWaveIcon, SpeakerXMarkIcon } from '@heroicons/react/24/outline'

interface Testimonial {
  id: number
  author_name: string
  author_avatar_url: string | null
  text: string
  rating: number | null
  media_type: 'none' | 'image' | 'video'
  image_url: string | null
  video_url: string | null
  video_file_url: string | null
  created_at: string
}

interface TestimonialsCarouselProps {
  className?: string
}

function classNames(...classes: (string | boolean)[]) {
  return classes.filter(Boolean).join(' ')
}

export default function TestimonialsCarousel({ className = '' }: TestimonialsCarouselProps) {
  const { t } = useTranslation('common')
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
        setTestimonials(Array.isArray(data) ? data : data.results || [])
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
    if (testimonial.media_type === 'image' && testimonial.image_url) {
      return (
        <img
          src={testimonial.image_url}
          alt={t('testimonial_image_alt', `Изображение к отзыву от ${testimonial.author_name}`)}
          className="w-full h-full object-cover"
        />
      )
    }
    if (testimonial.media_type === 'video') {
      if (testimonial.video_url) {
        // Для YouTube/Vimeo видео добавляем autoplay и muted в URL
        let embedUrl = testimonial.video_url
        
        // Обработка YouTube URL
        if (embedUrl.includes('youtube.com/watch?v=') || embedUrl.includes('youtu.be/')) {
          const youtubeRegex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/
          const match = embedUrl.match(youtubeRegex)
          if (match) {
            embedUrl = `https://www.youtube.com/embed/${match[1]}?autoplay=1&mute=1&loop=1&playlist=${match[1]}&controls=1&modestbranding=1`
          }
        }
        // Обработка Vimeo URL
        else if (embedUrl.includes('vimeo.com/')) {
          const vimeoRegex = /(?:vimeo\.com\/)(\d+)/
          const match = embedUrl.match(vimeoRegex)
          if (match) {
            embedUrl = `https://player.vimeo.com/video/${match[1]}?autoplay=1&muted=1&loop=1&controls=1&background=0`
          }
        }
        
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
      if (testimonial.video_file_url) {
        const isMuted = videoMuted.has(testimonial.id) ? videoMuted.get(testimonial.id) : true // По умолчанию muted
        return (
          <video
            ref={(el) => {
              if (el) {
                videoRefs.current.set(testimonial.id, el)
                el.muted = isMuted !== false
                // Инициализируем состояние если его еще нет
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
            <source src={testimonial.video_file_url} type="video/mp4" />
            {t('video_tag_unsupported', 'Ваш браузер не поддерживает видео.')}
          </video>
        )
      }
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
            {testimonials.map((testimonial) => (
              <div
                key={testimonial.id}
                className="flex-shrink-0 w-64 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-xl transition-all duration-300 overflow-hidden group cursor-pointer transform hover:-translate-y-2 hover:scale-[1.02]"
              >
                {testimonial.media_type !== 'none' && (
                   <div className="relative w-full h-80 overflow-hidden bg-gray-100">
                    <div className="w-full h-full transition-transform duration-300 group-hover:scale-110">
                      {renderMedia(testimonial)}
                    </div>
                    <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                    {testimonial.media_type === 'video' && testimonial.video_file_url && (
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
                  </div>
                )}
                <div className="p-4 transition-colors duration-300 group-hover:bg-gray-50">
                  {testimonial.rating && (
                    <div className="flex items-center mb-2">
                      {[0, 1, 2, 3, 4].map((rating) => (
                        <StarIcon
                          key={rating}
                          className={classNames(
                            (testimonial.rating || 0) > rating ? 'text-yellow-400 group-hover:text-yellow-500' : 'text-gray-300',
                            'h-4 w-4 flex-shrink-0 transition-all duration-300 group-hover:scale-110'
                          )}
                          style={{
                            transitionDelay: `${rating * 30}ms`
                          }}
                          aria-hidden="true"
                        />
                      ))}
                    </div>
                  )}
                  <p className="text-gray-600 mb-3 text-sm italic line-clamp-3 group-hover:text-gray-700 transition-colors duration-300">"{testimonial.text}"</p>
                  <div className="flex items-center">
                    {testimonial.author_avatar_url && (
                      <img
                        src={testimonial.author_avatar_url}
                        alt={testimonial.author_name}
                        className="w-8 h-8 rounded-full mr-3 object-cover ring-2 ring-gray-200 group-hover:ring-red-400 transition-all duration-300 group-hover:scale-110"
                      />
                    )}
                    <div className="text-xs font-semibold text-gray-900 group-hover:text-red-600 transition-colors duration-300">
                      {testimonial.author_name}
                    </div>
                  </div>
                </div>
              </div>
            ))}
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
