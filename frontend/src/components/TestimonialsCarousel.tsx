import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useTranslation } from 'next-i18next'
import Link from 'next/link'
import { LazyMotion, domAnimation, m, useReducedMotion } from 'framer-motion'
import { getSingleFlight } from '../lib/api'
import { StarIcon } from '@heroicons/react/20/solid'
import {
  ArrowUpRightIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  SpeakerWaveIcon,
  SpeakerXMarkIcon,
  PlayIcon,
  PauseIcon,
} from '@heroicons/react/24/outline'
import {
  applyImageFallback,
  getPlaceholderImageUrl,
  replaceFailedVideoWithFallback,
  resolveMediaUrl,
} from '../lib/media'
import {
  buildReviewAuthorUrl,
  buildReviewDetailUrl,
  ReviewFeedItem,
} from '../lib/testimonials'

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

interface TestimonialsCarouselProps {
  className?: string
}

function classNames(...classes: (string | boolean)[]) {
  return classes.filter(Boolean).join(' ')
}

export default function TestimonialsCarousel({ className = '' }: TestimonialsCarouselProps) {
  const { t } = useTranslation('common')
  const shouldReduceMotion = useReducedMotion()
  const [testimonials, setTestimonials] = useState<ReviewFeedItem[]>([])
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(0)
  const [isPointerOver, setIsPointerOver] = useState(false)
  const [hasFocusWithin, setHasFocusWithin] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const sectionRef = useRef<HTMLElement>(null)
  /** YouTube/Vimeo iframe только для карточек, попавших в viewport (или по клику play) — иначе PSI тянет base.js на всю страницу */
  const [lazyEmbedIds, setLazyEmbedIds] = useState<Set<string>>(() => new Set())
  const autoPlayRef = useRef<NodeJS.Timeout | null>(null)
  const videoRefs = useRef<Map<string, HTMLVideoElement>>(new Map())
  const iframeRefs = useRef<Map<string, HTMLIFrameElement>>(new Map())
  const iframeUrls = useRef<Map<string, string>>(new Map()) // Фиксированные URL для iframe
  const youtubePlayers = useRef<Map<string, any>>(new Map()) // YouTube IFrame API players
  const videoMutedRef = useRef<Map<string, boolean>>(new Map())
  const [videoMuted, setVideoMuted] = useState<Map<string, boolean>>(videoMutedRef.current)
  const videoPlayingRef = useRef<Map<string, boolean>>(new Map()) // Состояние воспроизведения видео
  const [videoPlaying, setVideoPlaying] = useState<Map<string, boolean>>(new Map()) // Для UI
  const isProgrammaticPauseRef = useRef<Map<string, boolean>>(new Map()) // Флаг программной паузы (при скролле)
  const [youtubeApiReady, setYoutubeApiReady] = useState(false)
  const playerReadyMapRef = useRef<Map<string, boolean>>(new Map())
  const itemsPerPage = 3 // A "page" for pagination dots
  const muteToggleTimeoutRef = useRef<Map<string, NodeJS.Timeout>>(new Map()) // Debounce для мобильных

  const updateVideoMuted = (mutator: (map: Map<string, boolean>) => void) => {
    // Обновляем ref сразу для мгновенного доступа
    const newMap = new Map(videoMutedRef.current)
    mutator(newMap)
    videoMutedRef.current = newMap
    // Обновляем состояние асинхронно, чтобы не блокировать UI
    setVideoMuted(newMap)
  }

  // Оптимизированный обработчик переключения звука - полностью синхронный для мгновенного отклика
  const handleToggleMute = useCallback((testimonialId: string, e: React.MouseEvent) => {
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
          if (newMuted) {
            // Выключаем звук - ТОЛЬКО через setVolume (без mute())
            player.setVolume(0)
          } else {
            // Включаем звук - ТОЛЬКО через setVolume (БЕЗ playVideo() и unMute())
            // НЕ вызываем playVideo(), т.к. YouTube блокирует это и ПАУЗИТ видео
            // Кнопка звука ТОЛЬКО переключает громкость, НЕ управляет воспроизведением
            player.setVolume(100)
          }
        } catch (error) {
          console.error('Error toggling mute via API:', error)
        }
      }
    }
  }, [])

  // Обработчик переключения play/pause для видео
  const handleTogglePlay = useCallback((testimonialId: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()

    setLazyEmbedIds((prev) => {
      if (prev.has(testimonialId)) return prev
      const next = new Set(prev)
      next.add(testimonialId)
      return next
    })

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
      const isPlayerReady = playerReadyMapRef.current.get(testimonialId)

      if (player && window.YT && isPlayerReady) {
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
            // На паузе или не запущено - воспроизводим СО ЗВУКОМ
            player.playVideo()
            // СРАЗУ включаем звук (обход Autoplay Policy: видео запускается muted=1, потом unmute)
            setTimeout(() => {
              try {
                player.setVolume(100)
              } catch (e) {
                console.error('Error setting volume after play:', e)
              }
            }, 100)

            videoPlayingRef.current.set(testimonialId, true)
            setVideoPlaying((prev) => {
              const newMap = new Map(prev)
              newMap.set(testimonialId, true)
              return newMap
            })
          }
        } catch (error) {
          console.error('Error toggling play/pause via YouTube API:', error, {
            testimonialId,
            hasPlayer: !!player,
            isPlayerReady,
            playerState: player ? player.getPlayerState() : 'N/A'
          })
        }
      }
    }
  }, [])

  // Отслеживаем изменения состояния воспроизведения для video_file
  useEffect(() => {
    const currentVideoRefs = videoRefs.current
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

    currentVideoRefs.forEach((video) => {
      if (video) {
        video.addEventListener('play', handlePlay)
        video.addEventListener('pause', handlePause)
      }
    })

    return () => {
      currentVideoRefs.forEach((video) => {
        if (video) {
          video.removeEventListener('play', handlePlay)
          video.removeEventListener('pause', handlePause)
        }
      })
    }
  }, [testimonials])

  const updatePlayerReady = (mutator: (map: Map<string, boolean>) => void) => {
    mutator(playerReadyMapRef.current)
  }

  // IntersectionObserver: разрешаем iframe только для карточек, реально попавших во viewport
  useEffect(() => {
    if (loading || testimonials.length === 0) return

    let cleanup: (() => void) | undefined
    const run = () => {
      const root = sectionRef.current
      if (!root) return

      const nodes = root.querySelectorAll<HTMLElement>('[data-testimonial-embed-lazy]')
      if (nodes.length === 0) return

      if (typeof IntersectionObserver === 'undefined') {
        setLazyEmbedIds((prev) => {
          const next = new Set(prev)
          nodes.forEach((node) => {
            const id = node.dataset.testimonialEmbedLazy
            if (id) next.add(id)
          })
          return next
        })
        return
      }

      const obs = new IntersectionObserver(
        (entries) => {
          entries.forEach((en) => {
            if (!en.isIntersecting) return
            const id = (en.target as HTMLElement).dataset.testimonialEmbedLazy
            if (!id) return
            setLazyEmbedIds((prev) => {
              if (prev.has(id)) return prev
              const next = new Set(prev)
              next.add(id)
              return next
            })
          })
        },
        { root: null, rootMargin: '80px', threshold: 0.15 }
      )
      nodes.forEach((n) => obs.observe(n))
      cleanup = () => obs.disconnect()
    }

    const tid = window.setTimeout(run, 0)
    return () => {
      window.clearTimeout(tid)
      cleanup?.()
    }
  }, [loading, testimonials])

  // YouTube IFrame API — только когда хотя бы один embed разрешён (есть iframe в DOM)
  useEffect(() => {
    if (lazyEmbedIds.size === 0) return

    let checkReady: NodeJS.Timeout | null = null

    const loadYouTubeApi = () => {
      if (window.YT && window.YT.Player) {
        setYoutubeApiReady(true)
        return
      }

      if (document.querySelector('script[src*="youtube.com/iframe_api"]')) {
        checkReady = setInterval(() => {
          if (window.YT && window.YT.Player) {
            setYoutubeApiReady(true)
            if (checkReady) clearInterval(checkReady)
          }
        }, 100)
        return
      }

      const tag = document.createElement('script')
      tag.src = 'https://www.youtube.com/iframe_api'
      const firstScriptTag = document.getElementsByTagName('script')[0]
      firstScriptTag.parentNode?.insertBefore(tag, firstScriptTag)

      ;(window as unknown as { onYouTubeIframeAPIReady?: () => void }).onYouTubeIframeAPIReady = () => {
        setYoutubeApiReady(true)
      }

      checkReady = setInterval(() => {
        if (window.YT && window.YT.Player) {
          setYoutubeApiReady(true)
          if (checkReady) clearInterval(checkReady)
        }
      }, 100)
    }

    loadYouTubeApi()

    return () => {
      if (checkReady) clearInterval(checkReady)
    }
  }, [lazyEmbedIds.size])

  // Cleanup таймаутов при размонтировании компонента
  useEffect(() => {
    const muteToggleTimeouts = muteToggleTimeoutRef.current
    return () => {
      // Очищаем все активные таймауты debounce
      muteToggleTimeouts.forEach((timeout) => {
        clearTimeout(timeout)
      })
      muteToggleTimeouts.clear()
    }
  }, [])

  useEffect(() => {
    const fetchTestimonials = async () => {
      try {
        const response = await getSingleFlight('/feedback/reviews-feed/', {
          params: { placement: 'homepage', page_size: 18 },
        })
        const data = response.data
        const testimonialsList = Array.isArray(data) ? data : data.results || []
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
      if (!videoMutedRef.current.has(testimonial.uid)) {
        updateVideoMuted((map) => {
          map.set(testimonial.uid, true)
        })
      }
      // Инициализируем состояние воспроизведения (по умолчанию пауза)
      if (!videoPlayingRef.current.has(testimonial.uid)) {
        videoPlayingRef.current.set(testimonial.uid, false)
        setVideoPlaying((prev) => {
          const newMap = new Map(prev)
          newMap.set(testimonial.uid, false)
          return newMap
        })
      }
    })
  }, [testimonials])

  const testimonialPages = useMemo(() => {
    const pages: ReviewFeedItem[][] = []
    for (let index = 0; index < testimonials.length; index += itemsPerPage) {
      pages.push(testimonials.slice(index, index + itemsPerPage))
    }
    return pages
  }, [testimonials])

  const totalPages = testimonialPages.length
  const isAutoplayPaused = isPointerOver || hasFocusWithin
  const isAnyVideoPlaying = useMemo(
    () => Array.from(videoPlaying.values()).some(Boolean),
    [videoPlaying]
  )

  const goToPage = useCallback((page: number) => {
    const container = scrollContainerRef.current
    if (!container || totalPages === 0) return

    const normalizedPage = (page + totalPages) % totalPages
    const pageElement = container.children[normalizedPage] as HTMLElement | undefined
    if (!pageElement) return

    container.scrollTo({
      left: pageElement.offsetLeft,
      behavior: shouldReduceMotion ? 'auto' : 'smooth',
    })
    setCurrentPage(normalizedPage)
  }, [shouldReduceMotion, totalPages])

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, Math.max(totalPages - 1, 0)))
  }, [totalPages])

  useEffect(() => {
    if (totalPages <= 1 || isAutoplayPaused || isAnyVideoPlaying) return

    autoPlayRef.current = setInterval(() => {
      goToPage(currentPage + 1)
    }, 7000)

    return () => {
      if (autoPlayRef.current) clearInterval(autoPlayRef.current)
    }
  }, [currentPage, goToPage, isAnyVideoPlaying, isAutoplayPaused, totalPages])

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

        const cardElement = video.closest('.testimonial-card') as HTMLElement
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

      // Управляем паузой YouTube видео при скролле
      iframeRefs.current.forEach((iframe, testimonialId) => {
        if (!iframe || !iframe.parentElement) return

        const player = youtubePlayers.current.get(testimonialId)
        if (!player || typeof player.getPlayerState !== 'function') return

        const cardElement = iframe.closest('.testimonial-card') as HTMLElement
        if (!cardElement) return

        const containerRect = container.getBoundingClientRect()
        const cardRect = cardElement.getBoundingClientRect()

        // Проверяем видимость карточки относительно VIEWPORT окна И контейнера карусели
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

        try {
          const playerState = player.getPlayerState()
          // 1 = playing, 2 = paused
          const isPlaying = playerState === 1

          // Если карточка видна на 30% и более - НЕ останавливаем видео
          if (isVisible && visibleRatio >= 0.3) {
            // Ничего не делаем - если пользователь запустил видео, оно продолжит воспроизводиться
          } else {
            // Карточка не видна или видна менее чем на 30% - ставим видео на паузу
            if (isPlaying) {
              player.pauseVideo()
              videoPlayingRef.current.set(testimonialId, false)
              setVideoPlaying((prev) => {
                const newMap = new Map(prev)
                newMap.set(testimonialId, false)
                return newMap
              })
            }
          }
        } catch (error) {
          // Игнорируем ошибки, если плеер не готов
        }
      })
    }

    const handleScroll = () => {
      // Немедленно проверяем и контролируем видео
      checkAndControlVideos()

      // Обновление страницы с debounce
      clearTimeout(pageUpdateTimeout)
      pageUpdateTimeout = setTimeout(() => {
        const pages = Array.from(container.children) as HTMLElement[]
        if (pages.length === 0) return

        const newPage = pages.reduce((closestIndex, page, index) => {
          const closestPage = pages[closestIndex]
          const distance = Math.abs(page.offsetLeft - container.scrollLeft)
          const closestDistance = Math.abs(closestPage.offsetLeft - container.scrollLeft)
          return distance < closestDistance ? index : closestIndex
        }, 0)

        if (newPage !== currentPage) {
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
    window.addEventListener('resize', throttledCheckVideos, { passive: true })

    // Первоначальная проверка
    checkAndControlVideos()

    return () => {
      container.removeEventListener('scroll', throttledHandleScroll)
      window.removeEventListener('scroll', throttledCheckVideos)
      window.removeEventListener('resize', throttledCheckVideos)
      clearTimeout(scrollTimeout)
      clearTimeout(pageUpdateTimeout)
    }
  }, [testimonials, videoMuted, currentPage, totalPages])

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

  // Останавливаем видео при переходе на другую вкладку (для video_file И YouTube)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Останавливаем все видео (video_file)
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

        // Останавливаем все YouTube видео
        youtubePlayers.current.forEach((player, testimonialId) => {
          if (!player || typeof player.getPlayerState !== 'function') return

          try {
            const playerState = player.getPlayerState()
            // 1 = playing
            if (playerState === 1) {
              player.pauseVideo()
              videoPlayingRef.current.set(testimonialId, false)
              setVideoPlaying((prev) => {
                const newMap = new Map(prev)
                newMap.set(testimonialId, false)
                return newMap
              })
            }
          } catch (error) {
            // Игнорируем ошибки, если плеер не готов
          }
        })
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

      const iframe = iframeRefs.current.get(testimonial.uid)
      if (!iframe) return

      const videoId = extractYouTubeId(firstMedia.video_url)
      if (!videoId) return

      if (!youtubePlayers.current.has(testimonial.uid)) {
        try {
          const isMuted = videoMutedRef.current.get(testimonial.uid) !== false
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
                // Обновляем состояние готовности плеера
                playerReadyMapRef.current.set(testimonial.uid, true)

                try {
                  // Инициализируем БЕЗ звука (для обхода Autoplay Policy)
                  // Звук включится при первом playVideo() в handleTogglePlay
                  event.target.setVolume(0)
                  // Инициализируем состояние воспроизведения (по умолчанию пауза, так как autoplay=0)
                  videoPlayingRef.current.set(testimonial.uid, false)
                  setVideoPlaying((prev) => {
                    const newMap = new Map(prev)
                    newMap.set(testimonial.uid, false)
                    return newMap
                  })
                } catch (e) {
                  console.error('Error setting volume on ready:', e)
                }
              },
              onStateChange: (event: any) => {
                // YT.PlayerState.UNSTARTED = -1, ENDED = 0, PLAYING = 1, PAUSED = 2, BUFFERING = 3, CUED = 5
                const isPlaying = event.data === 1
                videoPlayingRef.current.set(testimonial.uid, isPlaying)
                setVideoPlaying((prev) => {
                  const newMap = new Map(prev)
                  newMap.set(testimonial.uid, isPlaying)
                  return newMap
                })
              },
            },
          })
          youtubePlayers.current.set(testimonial.uid, player)
        } catch (error) {
          console.error('Error creating YouTube player:', error)
        }
      }
    })
  }, [youtubeApiReady, testimonials])

  useEffect(() => {
    const players = youtubePlayers.current
    return () => {
      players.forEach((player) => {
        try {
          const iframe = player.getIframe ? player.getIframe() : null
          if (iframe && iframe.parentNode) {
            player.destroy()
          }
        } catch (e) {
          // Игнорируем ошибки
        }
      })
      players.clear()
      updatePlayerReady((map) => map.clear())
    }
  }, [])

  if (loading) return <div className={`py-12 ${className}`} />

  const renderMedia = (testimonial: ReviewFeedItem) => {
    // Используем массив media; если его нет — показываем placeholder
    if (!testimonial.media || testimonial.media.length === 0) {
      const placeholder = getPlaceholderImageUrl({
        type: 'testimonial',
        id: testimonial.uid,
      })
      return (
        <img
          src={placeholder}
          alt={t('testimonial_image_alt', `Изображение к отзыву от ${testimonial.author_name}`)}
          className="w-full h-full object-cover"
          onError={(event) => applyImageFallback(event.currentTarget)}
        />
      )
    }

    // Показываем только первый медиа элемент в карусели
    const firstMedia = testimonial.media[0]

    if (firstMedia.media_type === 'image' && firstMedia.image_url) {
      return (
        <img
          src={resolveMediaUrl(firstMedia.image_url)}
          alt={t('testimonial_image_alt', `Изображение к отзыву от ${testimonial.author_name}`)}
          className="w-full h-full object-cover"
          onError={(event) => applyImageFallback(event.currentTarget)}
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
        let finalUrl = iframeUrls.current.get(testimonial.uid)
        if (!finalUrl) {
          // Создаем URL только один раз при первом рендере
          try {
            const url = new URL(embedUrl)

            // Убираем autoplay если есть
            url.searchParams.delete('autoplay')

            // Всегда начинаем с muted=1 (для обхода Autoplay Policy)
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
          iframeUrls.current.set(testimonial.uid, finalUrl)
        }

        const thumbnail = getYouTubeThumbnail(firstMedia.video_url || embedUrl)
        const showEmbed = lazyEmbedIds.has(testimonial.uid)

        return (
          <div
            className="w-full h-full relative"
            key={`container-${testimonial.uid}`}
            data-testimonial-embed-lazy={testimonial.uid}
          >
            {thumbnail && (
              <img
                src={thumbnail}
                alt={t('testimonial_video_alt', `Видео к отзыву от ${testimonial.author_name}`)}
                className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-300 ${showEmbed && playerReadyMapRef.current.get(testimonial.uid) ? 'opacity-0' : 'opacity-100'}`}
                onError={(event) => applyImageFallback(event.currentTarget)}
              />
            )}
            {showEmbed ? (
              <iframe
                ref={(el) => {
                  if (el) {
                    iframeRefs.current.set(testimonial.uid, el)
                  } else {
                    iframeRefs.current.delete(testimonial.uid)
                    iframeUrls.current.delete(testimonial.uid)
                  }
                }}
                src={finalUrl}
                title={t('testimonial_video_alt', `Видео к отзыву от ${testimonial.author_name}`)}
                frameBorder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                loading="lazy"
                className="absolute inset-0 w-full h-full"
              />
            ) : null}
          </div>
        )
      }

      return null
    }

    if (firstMedia.media_type === 'video_file' && firstMedia.video_file_url) {
      const isMuted = videoMuted.get(testimonial.uid) !== false
      return (
        <video
          ref={(el) => {
            if (el) {
              videoRefs.current.set(testimonial.uid, el)
              el.muted = isMuted
            } else {
              videoRefs.current.delete(testimonial.uid)
            }
          }}
          controls={false}
          muted={isMuted}
          playsInline
          loop
          className="w-full h-full object-cover"
          onError={(event) => replaceFailedVideoWithFallback(event.currentTarget, testimonial.author_name)}
        >
          <source src={resolveMediaUrl(firstMedia.video_file_url)} type="video/mp4" />
          {t('video_tag_unsupported', 'Ваш браузер не поддерживает видео.')}
        </video>
      )
    }

    return null
  }

  const renderVideoControls = (testimonial: ReviewFeedItem, compact: boolean) => {
    const hasVideo = testimonial.media?.some(
      media => (media.media_type === 'video_file' && media.video_file_url) ||
        (media.media_type === 'video' && media.video_url)
    )
    if (!hasVideo) return null

    const canToggleMute = testimonial.media?.some(
      media => (media.media_type === 'video_file' && media.video_file_url) ||
        (media.media_type === 'video' && media.video_url &&
          !media.video_url.includes('youtube.com') &&
          !media.video_url.includes('youtu.be') &&
          !media.video_url.includes('vimeo.com'))
    )
    const controlClass = compact ? 'h-9 w-9' : 'h-11 w-11'
    const iconClass = compact ? 'h-4 w-4' : 'h-5 w-5'

    return (
      <>
        <button
          type="button"
          onClick={(event) => handleTogglePlay(testimonial.uid, event)}
          className={classNames(
            'absolute left-3 top-3 z-20 inline-flex items-center justify-center rounded-full',
            'border border-white/20 bg-black/45 text-white shadow-lg backdrop-blur-md',
            'transition duration-200 hover:scale-105 hover:bg-black/65 active:scale-95',
            controlClass
          )}
          aria-label={videoPlaying.get(testimonial.uid) ? 'Пауза' : 'Воспроизведение'}
        >
          <span className={classNames('relative block', iconClass)}>
            <PauseIcon
              className={classNames(
                'absolute inset-0 transition-opacity duration-150',
                iconClass,
                videoPlaying.get(testimonial.uid) ? 'opacity-100' : 'opacity-0'
              )}
            />
            <PlayIcon
              className={classNames(
                'absolute inset-0 transition-opacity duration-150',
                iconClass,
                videoPlaying.get(testimonial.uid) ? 'opacity-0' : 'opacity-100'
              )}
            />
          </span>
        </button>

        {canToggleMute && (
          <button
            type="button"
            onClick={(event) => handleToggleMute(testimonial.uid, event)}
            className={classNames(
              'absolute right-3 top-3 z-20 inline-flex items-center justify-center rounded-full',
              'border border-white/20 bg-black/45 text-white shadow-lg backdrop-blur-md',
              'transition duration-200 hover:scale-105 hover:bg-black/65 active:scale-95',
              controlClass
            )}
            aria-label={videoMuted.get(testimonial.uid) !== false ? 'Включить звук' : 'Выключить звук'}
          >
            <span className={classNames('relative block', iconClass)}>
              <SpeakerXMarkIcon
                className={classNames(
                  'absolute inset-0 transition-opacity duration-150',
                  iconClass,
                  videoMuted.get(testimonial.uid) !== false ? 'opacity-100' : 'opacity-0'
                )}
              />
              <SpeakerWaveIcon
                className={classNames(
                  'absolute inset-0 transition-opacity duration-150',
                  iconClass,
                  videoMuted.get(testimonial.uid) !== false ? 'opacity-0' : 'opacity-100'
                )}
              />
            </span>
          </button>
        )}
      </>
    )
  }

  const renderRating = (testimonial: ReviewFeedItem, compact: boolean) => {
    if (!testimonial.rating) return null

    return (
      <div
        className="flex flex-shrink-0 items-center gap-0.5"
        aria-label={`${testimonial.rating} из 5`}
      >
        {[0, 1, 2, 3, 4].map((rating) => (
          <StarIcon
            key={rating}
            className={classNames(
              compact ? 'h-3.5 w-3.5' : 'h-4 w-4',
              (testimonial.rating || 0) > rating ? 'text-amber-400' : 'text-gray-300 dark:text-gray-600'
            )}
          />
        ))}
      </div>
    )
  }

  const renderAuthor = (testimonial: ReviewFeedItem, compact: boolean) => {
    const authorUrl = buildReviewAuthorUrl(testimonial)
    const content = (
      <>
        {testimonial.author_avatar_url ? (
          <img
            src={resolveMediaUrl(testimonial.author_avatar_url)}
            alt={testimonial.author_name}
            className={classNames(
              'flex-shrink-0 rounded-full object-cover ring-2 ring-white dark:ring-gray-800',
              compact ? 'h-7 w-7' : 'h-9 w-9'
            )}
            onError={(event) => applyImageFallback(event.currentTarget)}
          />
        ) : (
          <span
            aria-hidden="true"
            className={classNames(
              'inline-flex flex-shrink-0 items-center justify-center rounded-full bg-red-50 font-bold text-red-600 ring-2 ring-white dark:bg-red-950/50 dark:text-red-300 dark:ring-gray-800',
              compact ? 'h-7 w-7 text-[10px]' : 'h-9 w-9 text-xs'
            )}
          >
            {testimonial.author_name.trim().charAt(0).toUpperCase() || 'M'}
          </span>
        )}
        <span className="min-w-0 truncate font-semibold text-[var(--text-strong)]">
          {testimonial.author_name}
        </span>
      </>
    )

    const className = classNames(
      'flex min-w-0 items-center gap-2 transition-opacity hover:opacity-75',
      compact ? 'text-xs' : 'text-sm'
    )

    return authorUrl ? (
      <Link href={authorUrl} className={className} title={`Профиль ${testimonial.author_name}`}>
        {content}
      </Link>
    ) : (
      <div className={className}>{content}</div>
    )
  }

  const renderTestimonialCard = (
    testimonial: ReviewFeedItem,
    featured: boolean,
    cardIndex: number,
    pageSize: number
  ) => {
    const reviewUrl = buildReviewDetailUrl(testimonial)
    const isTallSecondary = !featured && pageSize === 2
    const isSingleCard = featured && pageSize === 1
    const subjectLabel = testimonial.review_type === 'service'
      ? t('review_about_service', 'Отзыв об услуге: {{name}}', { name: testimonial.product_name || '' })
      : testimonial.review_type === 'product'
        ? t('review_about_product', 'Отзыв о товаре: {{name}}', { name: testimonial.product_name || '' })
        : t('review_about_platform', 'Отзыв о платформе')
    const kindLabel = testimonial.review_type === 'service'
      ? t('review_kind_service', 'Услуга')
      : testimonial.review_type === 'product'
        ? t('review_kind_product', 'Товар')
        : t('review_kind_platform', 'Платформа')

    return (
      <m.article
        key={testimonial.uid}
        layout={!shouldReduceMotion}
        data-testid="homepage-testimonial-card"
        data-testimonial-id={testimonial.uid}
        data-featured={featured ? 'true' : 'false'}
        initial={shouldReduceMotion ? false : { opacity: 0, y: 24, scale: 0.97 }}
        whileInView={{ opacity: 1, y: 0, scale: 1 }}
        viewport={{ once: true, amount: 0.18 }}
        transition={{
          layout: { type: 'spring', stiffness: 260, damping: 30 },
          opacity: { duration: 0.35, delay: cardIndex * 0.07 },
          y: { type: 'spring', stiffness: 220, damping: 24, delay: cardIndex * 0.07 },
          scale: { type: 'spring', stiffness: 220, damping: 24, delay: cardIndex * 0.07 },
        }}
        whileHover={shouldReduceMotion ? undefined : { y: featured ? -6 : -4, scale: featured ? 1.004 : 1.01 }}
        className={classNames(
          'testimonial-card group relative isolate overflow-hidden rounded-[1.75rem]',
          'border border-white/80 bg-white/95 shadow-[0_20px_60px_-32px_rgba(15,23,42,0.45)]',
          'dark:border-white/10 dark:bg-[var(--surface)] dark:shadow-black/30',
          'focus-within:ring-2 focus-within:ring-red-500/60',
          featured
            ? 'min-h-[510px] sm:col-span-2 lg:col-span-1 lg:row-span-2'
            : 'min-h-[224px] sm:col-span-1 lg:col-start-2',
          isTallSecondary && 'lg:row-span-2',
          isSingleCard && 'lg:col-span-2'
        )}
      >
        <div
          className={classNames(
            'grid h-full min-h-[inherit]',
            featured
              ? 'md:grid-cols-[minmax(0,1.16fr)_minmax(260px,0.84fr)]'
              : 'grid-cols-[42%_58%]',
            isTallSecondary && 'lg:grid-cols-1 lg:grid-rows-[minmax(0,1.15fr)_auto]'
          )}
        >
          <div
            className={classNames(
              'relative min-w-0 overflow-hidden bg-gray-100 dark:bg-gray-900',
              featured ? 'min-h-[300px] md:min-h-0' : 'min-h-[224px]',
              isTallSecondary && 'lg:min-h-[300px]'
            )}
          >
            <Link
              href={reviewUrl}
              className="absolute inset-0 block overflow-hidden"
              aria-label={`${subjectLabel}: ${testimonial.text}`}
            >
              <div className="h-full w-full transition-transform duration-700 ease-out group-hover:scale-[1.045]">
                {renderMedia(testimonial)}
              </div>
              <div className="absolute inset-0 bg-gradient-to-t from-slate-950/50 via-slate-950/5 to-transparent" />
              <span className="absolute bottom-3 left-3 rounded-full border border-white/25 bg-black/35 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-white backdrop-blur-md">
                {kindLabel}
              </span>
            </Link>
            {renderVideoControls(testimonial, !featured)}
          </div>

          <div className={classNames('relative flex min-w-0 flex-col', featured ? 'p-6 sm:p-7' : 'p-4')}>
            <span
              aria-hidden="true"
              className={classNames(
                'pointer-events-none absolute right-4 top-1 select-none font-serif leading-none text-red-500/10 dark:text-red-300/10',
                featured ? 'text-[8rem]' : 'text-7xl'
              )}
            >
              “
            </span>

            <Link href={reviewUrl} className="relative z-10 flex min-h-0 flex-1 flex-col">
              <span className={classNames(
                'mb-3 block font-bold leading-snug text-red-600 dark:text-red-400',
                featured ? 'line-clamp-3 text-sm' : 'line-clamp-2 text-[11px]'
              )}>
                {subjectLabel}
              </span>
              <blockquote className={classNames(
                'text-balance text-gray-700 dark:text-gray-300',
                featured
                  ? 'line-clamp-8 text-lg leading-relaxed sm:text-xl'
                  : 'line-clamp-5 text-sm leading-relaxed'
              )}>
                «{testimonial.text}»
              </blockquote>

              {featured && (
                <span className="mt-auto inline-flex items-center gap-1.5 pt-5 text-sm font-bold text-[var(--text-strong)]">
                  {t('read_testimonial', 'Читать отзыв')}
                  <ArrowUpRightIcon className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </span>
              )}
            </Link>

            <div className={classNames(
              'relative z-20 mt-4 flex items-center justify-between gap-3 border-t border-gray-100 pt-4 dark:border-white/10',
              !featured && 'mt-3 pt-3'
            )}>
              {renderAuthor(testimonial, !featured)}
              {renderRating(testimonial, !featured)}
            </div>
          </div>
        </div>
      </m.article>
    )
  }

  return (
    <section ref={sectionRef} className={`py-12 sm:py-16 ${className}`}>
      <LazyMotion features={domAnimation}>
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div
            className="relative isolate overflow-hidden rounded-[2rem] border border-gray-200/80 bg-gradient-to-br from-slate-50 via-white to-red-50/70 px-4 py-7 shadow-[0_30px_100px_-55px_rgba(15,23,42,0.5)] sm:px-7 sm:py-9 dark:border-white/10 dark:from-slate-950 dark:via-gray-950 dark:to-red-950/20"
            onMouseEnter={() => setIsPointerOver(true)}
            onMouseLeave={() => setIsPointerOver(false)}
            onFocusCapture={() => setHasFocusWithin(true)}
            onBlurCapture={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setHasFocusWithin(false)
              }
            }}
          >
            <div className="testimonial-ambient testimonial-ambient-one" aria-hidden="true" />
            <div className="testimonial-ambient testimonial-ambient-two" aria-hidden="true" />
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.88),transparent_42%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.06),transparent_42%)]" />

            <div className="relative z-10">
              <div className="mb-7 flex flex-col gap-5 sm:mb-9 sm:flex-row sm:items-end sm:justify-between">
                <div className="max-w-2xl">
                  <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-red-200/80 bg-white/70 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.18em] text-red-600 shadow-sm backdrop-blur-md dark:border-red-500/20 dark:bg-white/5 dark:text-red-300">
                    <span className="h-1.5 w-1.5 rounded-full bg-red-500 shadow-[0_0_0_4px_rgba(239,68,68,0.12)]" />
                    {t('testimonials_eyebrow', 'Товары • услуги • платформа')}
                  </div>
                  <h2 className="text-balance text-3xl font-black tracking-tight text-main sm:text-4xl lg:text-5xl">
                    {t('testimonials_title', 'Что говорят наши клиенты')}
                  </h2>
                  <p className="mt-3 max-w-xl text-sm leading-relaxed text-gray-600 sm:text-base dark:text-gray-400">
                    {t('testimonials_spotlight_description', 'Истории покупателей о заказах, товарах и работе сервиса.')}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href="/testimonials"
                    className="inline-flex h-11 items-center gap-2 rounded-full border border-gray-200 bg-white/80 px-5 text-sm font-bold text-[var(--text-strong)] shadow-sm backdrop-blur-md transition hover:-translate-y-0.5 hover:border-red-200 hover:text-red-600 hover:shadow-md dark:border-white/10 dark:bg-white/5 dark:hover:border-red-500/30 dark:hover:text-red-300"
                  >
                    {t('show_all_testimonials', 'Все отзывы')}
                    <ArrowUpRightIcon className="h-4 w-4" />
                  </Link>

                  {totalPages > 1 && (
                    <div className="flex items-center gap-1 rounded-full border border-gray-200 bg-white/80 p-1 shadow-sm backdrop-blur-md dark:border-white/10 dark:bg-white/5">
                      <button
                        type="button"
                        onClick={() => goToPage(currentPage - 1)}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-full text-gray-700 transition hover:bg-gray-100 hover:text-red-600 active:scale-95 dark:text-gray-200 dark:hover:bg-white/10 dark:hover:text-red-300"
                        aria-label={t('previous_testimonials', 'Предыдущие отзывы')}
                      >
                        <ChevronLeftIcon className="h-5 w-5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => goToPage(currentPage + 1)}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-full text-gray-700 transition hover:bg-gray-100 hover:text-red-600 active:scale-95 dark:text-gray-200 dark:hover:bg-white/10 dark:hover:text-red-300"
                        aria-label={t('next_testimonials', 'Следующие отзывы')}
                      >
                        <ChevronRightIcon className="h-5 w-5" />
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {testimonials.length === 0 ? (
                <div className="rounded-[1.75rem] border border-white/80 bg-white/80 px-6 py-12 text-center shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/5">
                  <svg className="mx-auto mb-4 h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                  <p className="mb-6 text-lg text-gray-500">
                    {t('no_testimonials_yet', 'Пока нет отзывов. Станьте первым!')}
                  </p>
                  <Link
                    href="/testimonials?action=add"
                    className="inline-flex items-center gap-2 rounded-full bg-red-600 px-6 py-3 font-bold text-white shadow-lg shadow-red-600/20 transition hover:-translate-y-0.5 hover:bg-red-700 hover:shadow-xl"
                  >
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    <span>{t('add_testimonial', 'Оставить отзыв')}</span>
                  </Link>
                </div>
              ) : (
                <>
                  <div
                    ref={scrollContainerRef}
                    className="scrollbar-hide relative flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth px-1 py-3 lg:gap-6"
                    style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
                  >
                    {testimonialPages.map((page, pageIndex) => (
                      <div
                        key={page[0]?.uid || pageIndex}
                        className="grid min-w-0 flex-[0_0_100%] snap-start gap-4 sm:grid-cols-2 lg:min-h-[520px] lg:grid-cols-[minmax(0,1.65fr)_minmax(280px,0.85fr)] lg:grid-rows-2 lg:gap-5"
                        data-testid="homepage-testimonial-page"
                        aria-label={`${t('testimonials_page_title', 'Страница отзывов')} ${pageIndex + 1}`}
                      >
                        {page.map((testimonial, cardIndex) => (
                          renderTestimonialCard(testimonial, cardIndex === 0, cardIndex, page.length)
                        ))}
                      </div>
                    ))}
                  </div>

                  <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="min-w-[3.25rem] text-xs font-black tabular-nums tracking-[0.16em] text-gray-500 dark:text-gray-400">
                        {String(currentPage + 1).padStart(2, '0')} / {String(totalPages).padStart(2, '0')}
                      </span>
                      <div className="h-1.5 w-28 overflow-hidden rounded-full bg-gray-200/80 sm:w-40 dark:bg-white/10">
                        <span
                          key={currentPage}
                          className="testimonial-progress-fill block h-full origin-left rounded-full bg-gradient-to-r from-red-600 via-rose-500 to-amber-400"
                          style={{ animationPlayState: isAutoplayPaused || isAnyVideoPlaying ? 'paused' : 'running' }}
                        />
                      </div>
                      {totalPages > 1 && (
                        <div className="hidden items-center gap-1 sm:flex">
                          {testimonialPages.map((page, pageIndex) => (
                            <button
                              key={page[0]?.uid || pageIndex}
                              type="button"
                              onClick={() => goToPage(pageIndex)}
                              className="inline-flex h-8 w-8 items-center justify-center rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                              aria-label={`${t('go_to_testimonials_page', 'Перейти к отзывам')} ${pageIndex + 1}`}
                              aria-current={pageIndex === currentPage ? 'true' : undefined}
                            >
                              <span className={classNames(
                                'block rounded-full transition-all duration-300',
                                pageIndex === currentPage
                                  ? 'h-2.5 w-6 bg-gray-900 dark:bg-white'
                                  : 'h-2 w-2 bg-gray-300 hover:bg-red-400 dark:bg-gray-600'
                              )} />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    <Link
                      href="/testimonials?action=add"
                      className="inline-flex items-center justify-center gap-2 rounded-full bg-red-600 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-red-600/20 transition hover:-translate-y-0.5 hover:bg-red-700 hover:shadow-xl active:translate-y-0"
                    >
                      <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                      <span>{t('add_testimonial', 'Оставить отзыв')}</span>
                    </Link>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </LazyMotion>

      <style jsx>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }

        .testimonial-ambient {
          position: absolute;
          border-radius: 9999px;
          filter: blur(70px);
          pointer-events: none;
          opacity: 0.42;
          will-change: transform;
        }

        .testimonial-ambient-one {
          width: 22rem;
          height: 22rem;
          top: -10rem;
          right: -5rem;
          background: rgba(244, 63, 94, 0.24);
          animation: testimonial-float-one 14s ease-in-out infinite alternate;
        }

        .testimonial-ambient-two {
          width: 20rem;
          height: 20rem;
          bottom: -12rem;
          left: 8%;
          background: rgba(251, 191, 36, 0.18);
          animation: testimonial-float-two 17s ease-in-out infinite alternate;
        }

        .testimonial-progress-fill {
          width: 100%;
          animation: testimonial-progress 7s linear forwards;
        }

        @keyframes testimonial-progress {
          from { transform: scaleX(0); }
          to { transform: scaleX(1); }
        }

        @keyframes testimonial-float-one {
          from { transform: translate3d(0, 0, 0) scale(0.95); }
          to { transform: translate3d(-3rem, 2.5rem, 0) scale(1.08); }
        }

        @keyframes testimonial-float-two {
          from { transform: translate3d(0, 0, 0) scale(1); }
          to { transform: translate3d(4rem, -2rem, 0) scale(1.12); }
        }

        @media (prefers-reduced-motion: reduce) {
          .testimonial-ambient,
          .testimonial-progress-fill {
            animation: none;
          }
        }
      `}</style>
    </section>
  )
}
