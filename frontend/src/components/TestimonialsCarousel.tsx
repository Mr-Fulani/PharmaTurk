import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import Link from 'next/link'
import api from '../lib/api'
import { StarIcon } from '@heroicons/react/20/solid'
import { SpeakerWaveIcon, SpeakerXMarkIcon, PlayIcon, PauseIcon } from '@heroicons/react/24/outline'

declare global {
  interface Window {
    YT: any
    onYouTubeIframeAPIReady: () => void
  }
}

const extractYouTubeId = (url: string): string | null => {
  if (!url) return null
  const embedMatch = url.match(/youtube\.com\/embed\/([^\"&?\/\s]+)/)
  if (embedMatch && embedMatch[1]) {
    return embedMatch[1]
  }
  const standardRegex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?\/\s]{11})/
  let match = url.match(standardRegex)
  if (!match) {
    const shortsRegex = /(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?\/\s]+)/
    match = url.match(shortsRegex)
  }
  return match ? match[1] : null
}

const getYouTubeThumbnail = (url: string): string | null => {
  const youtubeId = extractYouTubeId(url)
  return youtubeId ? `https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg` : null
}

// Типы для YouTube IFrame API
declare global {
  interface Window {
    YT: any
    onYouTubeIframeAPIReady: () => void
  }
}

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
  const iframeRefs = useRef<Map<number, HTMLIFrameElement>>(new Map())
  const iframeUrls = useRef<Map<number, string>>(new Map()) // Фиксированные URL для iframe
  const youtubePlayers = useRef<Map<number, any>>(new Map()) // YouTube IFrame API players
  const videoMutedRef = useRef<Map<number, boolean>>(new Map())
  const [videoMuted, setVideoMuted] = useState<Map<number, boolean>>(videoMutedRef.current)
  const videoPlayingRef = useRef<Map<number, boolean>>(new Map()) // Состояние воспроизведения видео
  const [videoPlaying, setVideoPlaying] = useState<Map<number, boolean>>(new Map()) // Для UI
  const isProgrammaticPauseRef = useRef<Map<number, boolean>>(new Map()) // Флаг программной паузы (при скролле)
  const [youtubeApiReady, setYoutubeApiReady] = useState(false)
  const [playerReadyMap, setPlayerReadyMap] = useState<Map<number, boolean>>(new Map())
  const itemsPerPage = 3 // A "page" for pagination dots
  const muteToggleTimeoutRef = useRef<Map<number, NodeJS.Timeout>>(new Map()) // Debounce для мобильных

  const updateVideoMuted = (mutator: (map: Map<number, boolean>) => void) => {
    // Обновляем ref сразу для мгновенного доступа
    const newMap = new Map(videoMutedRef.current)
    mutator(newMap)
    videoMutedRef.current = newMap
    // Обновляем состояние асинхронно, чтобы не блокировать UI
    setVideoMuted(newMap)
  }

  // Оптимизированный обработчик переключения звука - полностью синхронный для мгновенного отклика
  const handleToggleMute = useCallback((testimonialId: number, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    // Очищаем предыдущий таймаут для этого видео (если есть)
    const existingTimeout = muteToggleTimeoutRef.current.get(testimonialId)
    if (existingTimeout) {
      clearTimeout(existingTimeout)
      muteToggleTimeoutRef.current.delete(testimonialId)
    }
    
    // Используем ref для получения текущего состояния без перерендера
    const currentMuted = videoMutedRef.current.get(testimonialId) !== false
    const newMuted = !currentMuted
    
    // СНАЧАЛА обновляем UI мгновенно для визуального отклика
    updateVideoMuted((map) => {
      map.set(testimonialId, newMuted)
    })
    
    // Затем применяем изменения к видео/iframe СИНХРОННО (без задержек)
    const video = videoRefs.current.get(testimonialId)
    const iframe = iframeRefs.current.get(testimonialId)
    
    if (video) {
      // Управление звуком для video_file
      // Важно: изменение muted не должно перезапускать видео
      try {
        // Проверяем, что видео загружено и готово
        if (video.readyState >= 2) { // HAVE_CURRENT_DATA или выше
          // Сохраняем текущее состояние воспроизведения
          const wasPlaying = !video.paused
          const currentTime = video.currentTime
          
          // Устанавливаем muted только если оно отличается
          if (video.muted !== newMuted) {
            video.muted = newMuted
            
            // Убеждаемся, что volume установлен правильно при включении звука
            if (!newMuted && video.volume === 0) {
              video.volume = 1.0
            }
          }
          
          // Проверяем, не сбросилось ли время воспроизведения (некоторые браузеры могут это делать)
          // Восстанавливаем только если разница значительная (>0.5 сек)
          if (wasPlaying && Math.abs(video.currentTime - currentTime) > 0.5) {
            video.currentTime = currentTime
          }
          
          // Восстанавливаем воспроизведение только если оно было и остановилось
          // НЕ вызываем play() если видео уже воспроизводится
          if (wasPlaying && video.paused) {
            // Используем requestAnimationFrame для более плавного восстановления
            requestAnimationFrame(() => {
              if (video.paused) {
                video.play().catch((err) => {
                  console.error('Error resuming video playback:', err)
                })
              }
            })
          }
        } else {
          // Если видео еще не загружено, просто устанавливаем muted
          // Это не вызовет перезапуск, так как видео еще не началось
          video.muted = newMuted
        }
      } catch (error) {
        console.error('Error toggling mute for video_file:', error)
        // Fallback: просто устанавливаем muted
        try {
          video.muted = newMuted
        } catch (e) {
          console.error('Error setting muted property:', e)
        }
      }
    } else if (iframe) {
      // Управление звуком для YouTube/Vimeo iframe через API - синхронно
      const player = youtubePlayers.current.get(testimonialId)
      if (player && window.YT) {
        try {
          // Используем YouTube IFrame API - синхронно
          if (newMuted) {
            player.mute()
          } else {
            player.unMute()
          }
        } catch (error) {
          console.error('Error toggling mute via API:', error)
          // В случае ошибки состояние уже обновлено, ничего не делаем
        }
      }
    }
  }, [])

  // Обработчик переключения play/pause для видео
  const handleTogglePlay = useCallback((testimonialId: number, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    const video = videoRefs.current.get(testimonialId)
    const iframe = iframeRefs.current.get(testimonialId)
    
    if (video) {
      // Управление воспроизведением для video_file
      try {
        if (video.paused) {
          video.play().catch((err) => {
            console.error('Error playing video:', err)
          })
          videoPlayingRef.current.set(testimonialId, true)
          setVideoPlaying((prev) => {
            const newMap = new Map(prev)
            newMap.set(testimonialId, true)
            return newMap
          })
        } else {
          video.pause()
          videoPlayingRef.current.set(testimonialId, false)
          setVideoPlaying((prev) => {
            const newMap = new Map(prev)
            newMap.set(testimonialId, false)
            return newMap
          })
        }
      } catch (error) {
        console.error('Error toggling play/pause for video_file:', error)
      }
    } else if (iframe) {
      // Управление воспроизведением для YouTube/Vimeo через API
      const player = youtubePlayers.current.get(testimonialId)
      if (player && window.YT) {
        try {
          const playerState = player.getPlayerState()
          // YT.PlayerState.PLAYING = 1, YT.PlayerState.PAUSED = 2
          if (playerState === 1) {
            // Воспроизводится - ставим на паузу
            player.pauseVideo()
            videoPlayingRef.current.set(testimonialId, false)
            setVideoPlaying((prev) => {
              const newMap = new Map(prev)
              newMap.set(testimonialId, false)
              return newMap
            })
          } else {
            // На паузе или не запущено - воспроизводим
            player.playVideo()
            videoPlayingRef.current.set(testimonialId, true)
            setVideoPlaying((prev) => {
              const newMap = new Map(prev)
              newMap.set(testimonialId, true)
              return newMap
            })
          }
        } catch (error) {
          console.error('Error toggling play/pause via YouTube API:', error)
        }
      }
    }
  }, [])

  // Отслеживаем изменения состояния воспроизведения для video_file
  useEffect(() => {
    const handlePlay = (e: Event) => {
      const video = e.target as HTMLVideoElement
      const testimonialId = Array.from(videoRefs.current.entries()).find(([_, v]) => v === video)?.[0]
      if (testimonialId !== undefined) {
        // Сбрасываем флаг программной паузы при пользовательском запуске
        isProgrammaticPauseRef.current.set(testimonialId, false)
        videoPlayingRef.current.set(testimonialId, true)
        setVideoPlaying((prev) => {
          const newMap = new Map(prev)
          newMap.set(testimonialId, true)
          return newMap
        })
      }
    }
    
    const handlePause = (e: Event) => {
      const video = e.target as HTMLVideoElement
      const testimonialId = Array.from(videoRefs.current.entries()).find(([_, v]) => v === video)?.[0]
      if (testimonialId !== undefined) {
        // Всегда обновляем состояние - UI должен отражать реальное состояние видео
        videoPlayingRef.current.set(testimonialId, false)
        setVideoPlaying((prev) => {
          const newMap = new Map(prev)
          newMap.set(testimonialId, false)
          return newMap
        })
        // Сбрасываем флаг программной паузы после обработки
        isProgrammaticPauseRef.current.set(testimonialId, false)
      }
    }
    
    videoRefs.current.forEach((video) => {
      if (video) {
        video.addEventListener('play', handlePlay)
        video.addEventListener('pause', handlePause)
      }
    })
    
    return () => {
      videoRefs.current.forEach((video) => {
        if (video) {
          video.removeEventListener('play', handlePlay)
          video.removeEventListener('pause', handlePause)
        }
      })
    }
  }, [testimonials])

  const updatePlayerReady = (mutator: (map: Map<number, boolean>) => void) => {
    setPlayerReadyMap((prev) => {
      const newMap = new Map(prev)
      mutator(newMap)
      return newMap
    })
  }

  // Загрузка YouTube IFrame API
  useEffect(() => {
    // Проверяем, не загружен ли уже скрипт
    if (window.YT && window.YT.Player) {
      setYoutubeApiReady(true)
      return
    }

    // Проверяем, не загружается ли уже скрипт
    if (document.querySelector('script[src*="youtube.com/iframe_api"]')) {
      // Ждем, пока API загрузится
      const checkReady = setInterval(() => {
        if (window.YT && window.YT.Player) {
          setYoutubeApiReady(true)
          clearInterval(checkReady)
        }
      }, 100)
      return () => clearInterval(checkReady)
    }

    // Загружаем скрипт
    const tag = document.createElement('script')
    tag.src = 'https://www.youtube.com/iframe_api'
    const firstScriptTag = document.getElementsByTagName('script')[0]
    firstScriptTag.parentNode?.insertBefore(tag, firstScriptTag)

    // Обработчик готовности API
    ;(window as any).onYouTubeIframeAPIReady = () => {
      setYoutubeApiReady(true)
    }

    // Проверяем, не загрузился ли API уже
    const checkReady = setInterval(() => {
      if (window.YT && window.YT.Player) {
        setYoutubeApiReady(true)
        clearInterval(checkReady)
      }
    }, 100)

    return () => {
      clearInterval(checkReady)
    }
  }, [])

  // Cleanup таймаутов при размонтировании компонента
  useEffect(() => {
    return () => {
      // Очищаем все активные таймауты debounce
      muteToggleTimeoutRef.current.forEach((timeout) => {
        clearTimeout(timeout)
      })
      muteToggleTimeoutRef.current.clear()
    }
  }, [])

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
      } catch (error: any) {
        console.error('Failed to fetch testimonials:', {
          error,
          message: error?.message,
          response: error?.response?.data,
          status: error?.response?.status,
          url: error?.config?.url,
          baseURL: error?.config?.baseURL,
          fullUrl: error?.config ? `${error?.config.baseURL}${error?.config.url}` : 'unknown',
          origin: typeof window !== 'undefined' ? window.location.origin : 'server'
        })
      } finally {
        setLoading(false)
      }
    }
    fetchTestimonials()
  }, [])
  
  useEffect(() => {
    testimonials.forEach((testimonial) => {
      if (!videoMutedRef.current.has(testimonial.id)) {
        updateVideoMuted((map) => {
          map.set(testimonial.id, true)
        })
      }
      // Инициализируем состояние воспроизведения (по умолчанию пауза)
      if (!videoPlayingRef.current.has(testimonial.id)) {
        videoPlayingRef.current.set(testimonial.id, false)
        setVideoPlaying((prev) => {
          const newMap = new Map(prev)
          newMap.set(testimonial.id, false)
          return newMap
        })
      }
    })
  }, [testimonials])

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
      // Управляем паузой видео при скролле (только для video_file, загруженных через админку)
      videoRefs.current.forEach((video, testimonialId) => {
        if (!video || !video.parentElement) return
        
        const cardElement = video.closest('.flex-shrink-0') as HTMLElement
        if (!cardElement) return
        
        const containerRect = container.getBoundingClientRect()
        const cardRect = cardElement.getBoundingClientRect()
        
        // Проверяем видимость карточки относительно VIEWPORT окна И контейнера карусели
        // Карточка должна быть видна И в контейнере И на экране
        const isVisibleInContainer = 
          cardRect.left < containerRect.right &&
          cardRect.right > containerRect.left
        
        const isVisibleInViewport = 
          cardRect.top < window.innerHeight &&
          cardRect.bottom > 0
        
        const isVisible = isVisibleInContainer && isVisibleInViewport
        
        // Вычисляем процент видимости по горизонтали
        const visibleWidth = Math.min(cardRect.right, containerRect.right) - Math.max(cardRect.left, containerRect.left)
        const visibleRatio = isVisible ? Math.max(0, visibleWidth / cardRect.width) : 0
        
        // Если карточка видна на 30% и более - только синхронизируем muted, НЕ останавливаем видео
        // Пользователь может запустить видео вручную, и оно будет продолжать воспроизводиться
        if (isVisible && visibleRatio >= 0.3) {
          const isMuted = videoMutedRef.current.get(testimonialId) !== false
          // Устанавливаем muted только если оно изменилось, чтобы не перезапускать видео
          if (video.muted !== isMuted) {
            video.muted = isMuted
          }
          // НЕ останавливаем видео - если пользователь его запустил, оно продолжит воспроизводиться
        } else {
          // Карточка не видна или видна менее чем на 30% - ставим видео на паузу
          if (!video.paused) {
            isProgrammaticPauseRef.current.set(testimonialId, true)
            video.pause()
            videoPlayingRef.current.set(testimonialId, false)
            setVideoPlaying((prev) => {
              const newMap = new Map(prev)
              newMap.set(testimonialId, false)
              return newMap
            })
          }
        }
      })
      
      // YouTube видео не останавливаются при скролле - они продолжают воспроизводиться
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
    
    // Обработчик для скролла страницы (window scroll)
    let lastWindowScrollTime = 0
    const throttledCheckVideos = () => {
      const now = Date.now()
      if (now - lastWindowScrollTime >= 50) {
        lastWindowScrollTime = now
        checkAndControlVideos()
      }
    }
    
    container.addEventListener('scroll', throttledHandleScroll, { passive: true })
    // Добавляем обработчик скролла страницы для остановки видео при вертикальном скролле
    window.addEventListener('scroll', throttledCheckVideos, { passive: true })
    
    // Первоначальная проверка
    checkAndControlVideos()
    
    // Периодическая проверка на случай пропущенных событий
    const intervalId = setInterval(checkAndControlVideos, 200)
    
    return () => {
      container.removeEventListener('scroll', throttledHandleScroll)
      window.removeEventListener('scroll', throttledCheckVideos)
      clearInterval(intervalId)
      clearTimeout(scrollTimeout)
      clearTimeout(pageUpdateTimeout)
    }
  }, [testimonials, videoMuted, currentPage, totalPages, itemsPerPage])

  // Автовоспроизведение отключено - не останавливаем видео при смене страницы
  // Пользователь управляет воспроизведением вручную
  // useEffect(() => {
  //   videoRefs.current.forEach((video) => {
  //     if (video) {
  //       video.pause()
  //       video.currentTime = 0
  //     }
  //   })
  //   // YouTube видео не останавливаются при смене страницы
  // }, [currentPage])
  
  // Останавливаем видео при переходе на другую вкладку (только для video_file)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Останавливаем все видео (только для video_file)
        videoRefs.current.forEach((video, testimonialId) => {
          if (video && !video.paused) {
            isProgrammaticPauseRef.current.set(testimonialId, true)
            video.pause()
            videoPlayingRef.current.set(testimonialId, false)
            setVideoPlaying((prev) => {
              const newMap = new Map(prev)
              newMap.set(testimonialId, false)
              return newMap
            })
          }
        })
        // YouTube видео не останавливаются при переходе на другую вкладку
      }
    }
    
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  // Создаем и обновляем YouTube плееры
  useEffect(() => {
    if (!youtubeApiReady || !window.YT || !window.YT.Player) return

    testimonials.forEach((testimonial) => {
      if (!testimonial.media || testimonial.media.length === 0) return
      const firstMedia = testimonial.media[0]
      if (firstMedia.media_type !== 'video' || !firstMedia.video_url) return

      const iframe = iframeRefs.current.get(testimonial.id)
      if (!iframe) return

      const videoId = extractYouTubeId(firstMedia.video_url)
      if (!videoId) return

      if (!youtubePlayers.current.has(testimonial.id)) {
        try {
          const isMuted = videoMutedRef.current.get(testimonial.id) !== false
          const player = new window.YT.Player(iframe, {
            videoId,
            playerVars: {
              autoplay: 0, // Автовоспроизведение отключено
              mute: isMuted ? 1 : 0,
              loop: 1,
              playlist: videoId,
              controls: 1,
              modestbranding: 1,
              rel: 0,
              enablejsapi: 1,
            },
            events: {
              onReady: (event: any) => {
                updatePlayerReady((map) => map.set(testimonial.id, true))
                const currentMuted = videoMutedRef.current.get(testimonial.id) !== false
                try {
                  if (currentMuted) {
                    event.target.mute()
                  } else {
                    event.target.unMute()
                  }
                  // Инициализируем состояние воспроизведения (по умолчанию пауза, так как autoplay=0)
                  videoPlayingRef.current.set(testimonial.id, false)
                  setVideoPlaying((prev) => {
                    const newMap = new Map(prev)
                    newMap.set(testimonial.id, false)
                    return newMap
                  })
                } catch (e) {
                  console.error('Error setting mute on ready:', e)
                }
              },
              onStateChange: (event: any) => {
                // YT.PlayerState.PLAYING = 1, YT.PlayerState.PAUSED = 2
                const isPlaying = event.data === 1
                videoPlayingRef.current.set(testimonial.id, isPlaying)
                setVideoPlaying((prev) => {
                  const newMap = new Map(prev)
                  newMap.set(testimonial.id, isPlaying)
                  return newMap
                })
              },
            },
          })
          youtubePlayers.current.set(testimonial.id, player)
        } catch (error) {
          console.error('Error creating YouTube player:', error)
        }
      }
    })
  }, [youtubeApiReady, testimonials])

  useEffect(() => {
    return () => {
      youtubePlayers.current.forEach((player) => {
        try {
          const iframe = player.getIframe ? player.getIframe() : null
          if (iframe && iframe.parentNode) {
            player.destroy()
          }
        } catch (e) {
          // Игнорируем ошибки
        }
      })
      youtubePlayers.current.clear()
      updatePlayerReady((map) => map.clear())
    }
  }, [])

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
      // Для YouTube/Vimeo видео добавляем параметры в URL (без autoplay)
      let embedUrl = firstMedia.video_url
      let isValidEmbedUrl = false
      
      // Обработка YouTube URL - улучшенная версия, поддерживающая все форматы
      // Проверяем, является ли URL уже embed URL
      if (embedUrl.includes('youtube.com/embed/')) {
        // Уже embed URL, просто добавляем параметры если их нет (без autoplay)
        if (!embedUrl.includes('?')) {
          embedUrl += '?muted=1&loop=1&controls=1&modestbranding=1&enablejsapi=1'
        } else {
          // Убираем autoplay если есть
          embedUrl = embedUrl.replace(/[?&]autoplay=\d+/g, '')
          if (!embedUrl.includes('muted')) embedUrl += '&muted=1'
          if (!embedUrl.includes('loop')) embedUrl += '&loop=1'
          if (!embedUrl.includes('controls')) embedUrl += '&controls=1'
          if (!embedUrl.includes('modestbranding')) embedUrl += '&modestbranding=1'
          if (!embedUrl.includes('enablejsapi')) embedUrl += '&enablejsapi=1'
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
          embedUrl = `https://www.youtube.com/embed/${videoId}?muted=1&loop=1&playlist=${videoId}&controls=1&modestbranding=1&rel=0&enablejsapi=1`
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
          embedUrl = `https://player.vimeo.com/video/${match[1]}?muted=1&loop=1&controls=1&background=0`
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
        // Создаем фиксированный URL один раз (с muted=1 по умолчанию)
        // Управление звуком будет через YouTube API, без изменения src
        let finalUrl = iframeUrls.current.get(testimonial.id)
        if (!finalUrl) {
          // Создаем URL только один раз при первом рендере
          try {
            const url = new URL(embedUrl)
            
            // Убираем autoplay если есть
            url.searchParams.delete('autoplay')
            
            // Всегда начинаем с muted=1 (звук выключен по умолчанию)
            url.searchParams.set('muted', '1')
            
            finalUrl = url.toString()
          } catch (error) {
            console.error('Error parsing URL:', error, embedUrl)
            // Fallback: простая замена - убираем autoplay
            finalUrl = embedUrl.replace(/[?&]autoplay=\d+/g, '')
            if (!finalUrl.includes('muted')) {
              const separator = finalUrl.includes('?') ? '&' : '?'
              finalUrl = `${finalUrl}${separator}muted=1`
            }
          }
          
          // Сохраняем фиксированный URL
          iframeUrls.current.set(testimonial.id, finalUrl)
        }
        
        // Отладочная информация
        if (process.env.NODE_ENV === 'development') {
          console.log('YouTube iframe URL:', { testimonialId: testimonial.id, finalUrl })
        }

        const thumbnail = getYouTubeThumbnail(firstMedia.video_url || embedUrl)
        const isPlayerReady = playerReadyMap.get(testimonial.id) === true

      return (
          <div className="w-full h-full relative" key={`container-${testimonial.id}`}>
            {thumbnail && (
              <img
                src={thumbnail}
                alt={t('testimonial_video_alt', `Видео к отзыву от ${testimonial.author_name}`)}
                className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-300 ${isPlayerReady ? 'opacity-0' : 'opacity-100'}`}
              />
            )}
        <iframe
              ref={(el) => {
                if (el) {
                  iframeRefs.current.set(testimonial.id, el)
                } else {
                  iframeRefs.current.delete(testimonial.id)
                  iframeUrls.current.delete(testimonial.id) // Очищаем URL при размонтировании
                }
              }}
              src={finalUrl}
          title={t('testimonial_video_alt', `Видео к отзыву от ${testimonial.author_name}`)}
          frameBorder="0"
              allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
              className="absolute inset-0 w-full h-full"
        ></iframe>
          </div>
      )
      }
      
      return null
    }
    
    if (firstMedia.media_type === 'video_file' && firstMedia.video_file_url) {
      const isMuted = videoMuted.get(testimonial.id) !== false
      return (
        <video
          ref={(el) => {
            if (el) {
              videoRefs.current.set(testimonial.id, el)
              el.muted = isMuted
            } else {
              videoRefs.current.delete(testimonial.id)
            }
          }}
          controls={false}
          muted={isMuted}
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
                      m => (m.media_type === 'video_file' && m.video_file_url) || (m.media_type === 'video' && m.video_url)
                    ) && (
                      <>
                        {/* Кнопка play/pause */}
                        <button
                          onClick={(e) => handleTogglePlay(testimonial.id, e)}
                          className="absolute top-2 left-2 z-20 p-2 rounded-full bg-black/50 hover:bg-black/70 text-white transition-all duration-150 hover:scale-110 active:scale-95"
                          aria-label={videoPlaying.get(testimonial.id) ? 'Пауза' : 'Воспроизведение'}
                        >
                          <div className="relative w-5 h-5">
                            <PauseIcon 
                              className={`absolute inset-0 w-5 h-5 transition-opacity duration-150 ${
                                videoPlaying.get(testimonial.id) ? 'opacity-100' : 'opacity-0'
                              }`}
                            />
                            <PlayIcon 
                              className={`absolute inset-0 w-5 h-5 transition-opacity duration-150 ${
                                videoPlaying.get(testimonial.id) ? 'opacity-0' : 'opacity-100'
                              }`}
                            />
                          </div>
                        </button>
                        {/* Кнопка звука */}
                      <button
                          onClick={(e) => handleToggleMute(testimonial.id, e)}
                          className="absolute top-2 right-2 z-20 p-2 rounded-full bg-black/50 hover:bg-black/70 text-white transition-all duration-150 hover:scale-110 active:scale-95"
                        aria-label={videoMuted.get(testimonial.id) !== false ? 'Включить звук' : 'Выключить звук'}
                      >
                          <div className="relative w-5 h-5">
                            <SpeakerXMarkIcon 
                              className={`absolute inset-0 w-5 h-5 transition-opacity duration-150 ${
                                videoMuted.get(testimonial.id) !== false ? 'opacity-100' : 'opacity-0'
                              }`}
                            />
                            <SpeakerWaveIcon 
                              className={`absolute inset-0 w-5 h-5 transition-opacity duration-150 ${
                                videoMuted.get(testimonial.id) !== false ? 'opacity-0' : 'opacity-100'
                              }`}
                            />
                          </div>
                      </button>
                      </>
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
