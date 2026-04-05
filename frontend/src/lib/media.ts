// Утилиты для медиаконтента (webp/avif, fallback) — русские комментарии.

import { getClientMediaBase, getInternalApiBase, getSiteOrigin } from './urls'

export type MediaSource = {
  url: string | null | undefined
}

const VIDEO_EXT_REGEX = /\.(mp4|webm|mov|avi|mkv|m4v)(\?|$)/i
const GIF_EXT_REGEX = /\.gif(\?|$)/i

/** Проверяет, что URL указывает на видео (по расширению или хосту), а не на картинку. */
export const isVideoUrl = (url?: string | null): boolean => {
  if (!url || typeof url !== 'string') return false
  const path = url.split('?')[0].toLowerCase()
  if (VIDEO_EXT_REGEX.test(path)) return true
  // proxy-media: /api/catalog/proxy-media/?path=... — тип файла только по path (иначе обложки книг ошибочно считались видео).
  if (/proxy-media/i.test(url) && url.includes('path=')) {
    try {
      const pathMatch = url.match(/[?&]path=([^&]+)/)
      const pathParam = pathMatch ? decodeURIComponent(pathMatch[1]) : ''
      if (pathParam && VIDEO_EXT_REGEX.test(pathParam)) return true
      // Карточки категорий/брендов (marketing/cards/.../videos/...) без суффикса в ключе R2
      if (pathParam && pathParam.toLowerCase().includes('/videos/')) return true
      if (pathParam) return false
    } catch {
      // ignore
    }
  }
  // main/videos, устаревший сегмент /video/; наши пути .../products/.../videos/ и marketing/cards/.../videos/
  if (url.includes('/video/') || url.includes('main_video')) return true
  const low = url.toLowerCase()
  if (low.includes('/videos/')) {
    if (low.includes('marketing/cards/') || low.includes('/products/')) return true
  }
  if (/youtube(?:-nocookie)?\.com|youtu\.be|vimeo\.com/i.test(url)) return true
  return false
}

/** URL анимированного GIF (по расширению или path= у proxy-media). */
export const isGifUrl = (url?: string | null): boolean => {
  if (!url || typeof url !== 'string') return false
  const path = url.split('?')[0].toLowerCase()
  if (GIF_EXT_REGEX.test(path)) return true
  if (/proxy-media/i.test(url) && url.includes('path=')) {
    try {
      const pathMatch = url.match(/[?&]path=([^&]+)/)
      const pathParam = pathMatch ? decodeURIComponent(pathMatch[1]) : ''
      if (pathParam && GIF_EXT_REGEX.test(pathParam)) return true
    } catch {
      // ignore
    }
  }
  return false
}

/**
 * Из нескольких URL выбирает лучший для воспроизведения: приоритет у proxy-media (файл в хранилище),
 * иначе часто остаётся внешний .mov без воспроизведения в Chrome.
 */
export function pickPreferredVideoUrl(urls: (string | null | undefined)[]): string | null {
  const cleaned: string[] = []
  for (const u of urls) {
    const t = u && String(u).trim()
    if (t && isVideoUrl(t) && !cleaned.includes(t)) cleaned.push(t)
  }
  if (!cleaned.length) return null
  const proxy = cleaned.find((x) => /proxy-media/i.test(x))
  if (proxy) return proxy
  return cleaned[0]
}

/** Режим встраивания: страница товара (с controls) или фон баннера (autoplay loop muted). */
export type VideoEmbedMode = 'player' | 'ambient'

const YOUTUBE_ID_STANDARD_RE =
  /(?:youtube(?:-nocookie)?\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?/\s]{11})/

const YOUTUBE_SHORTS_RE =
  /(?:youtube(?:-nocookie)?\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?/\s]+)/

function buildYouTubeEmbedUrl(videoId: string, mode: VideoEmbedMode): string {
  const base = `https://www.youtube.com/embed/${videoId}`
  if (mode === 'ambient') {
    return `${base}?autoplay=1&loop=1&muted=1&playlist=${encodeURIComponent(videoId)}&controls=0&showinfo=0&rel=0`
  }
  return `${base}?autoplay=0&controls=1&rel=0`
}

/**
 * URL для iframe YouTube/Vimeo. Поддерживает youtube-nocookie.com (иначе <video> не играет YouTube).
 */
export function getVideoEmbedUrl(url: string, mode: VideoEmbedMode = 'player'): string | null {
  if (!url || typeof url !== 'string') return null
  const trimmed = url.trim()
  if (!trimmed) return null

  if (/youtube(?:-nocookie)?\.com|youtu\.be|m\.youtube\.com/i.test(trimmed)) {
    if (/\/embed\//i.test(trimmed) && /youtube(?:-nocookie)?\.com/i.test(trimmed)) {
      const idMatch = trimmed.match(/\/embed\/([^/?&\s]+)/i)
      if (idMatch?.[1]) {
        if (mode === 'ambient' && /autoplay=1/i.test(trimmed)) {
          return trimmed
        }
        return buildYouTubeEmbedUrl(idMatch[1], mode)
      }
    }

    let match = trimmed.match(YOUTUBE_ID_STANDARD_RE)
    if (!match) match = trimmed.match(YOUTUBE_SHORTS_RE)
    if (match?.[1]) {
      return buildYouTubeEmbedUrl(match[1], mode)
    }
  }

  if (trimmed.includes('player.vimeo.com/video/')) {
    if (mode === 'ambient') {
      if (!trimmed.includes('?')) {
        return `${trimmed}?autoplay=1&loop=1&muted=1&background=1`
      }
      if (!trimmed.includes('autoplay')) {
        return `${trimmed}&autoplay=1&loop=1&muted=1&background=1`
      }
      return trimmed
    }
    return trimmed.includes('?') ? trimmed : `${trimmed}?autoplay=0&muted=0`
  }

  const vimeoMatch = trimmed.match(/(?:vimeo\.com\/)(\d+)/)
  if (vimeoMatch?.[1]) {
    const id = vimeoMatch[1]
    if (mode === 'ambient') {
      return `https://player.vimeo.com/video/${id}?autoplay=1&loop=1&muted=1&background=1`
    }
    return `https://player.vimeo.com/video/${id}?autoplay=0&muted=0`
  }

  return null
}

/** Извлекает id ролика YouTube из URL (watch, embed, shorts, youtu.be). */
export function extractYouTubeId(url?: string | null): string | null {
  if (!url || typeof url !== 'string') return null
  const match =
    url.match(
      /(?:youtube\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/|m\.youtube\.com\/watch\?v=)([^"&?/\s]{11})/
    ) || url.match(/(?:youtube\.com\/shorts\/|m\.youtube\.com\/shorts\/)([^"&?/\s]+)/)
  return match?.[1] ?? null
}

/** Превью для карточек (легче полного плеера). */
export function getYouTubeCardThumbnailUrl(url?: string | null): string | null {
  const id = extractYouTubeId(url)
  return id ? `https://img.youtube.com/vi/${id}/hqdefault.jpg` : null
}

const stripTrailingSlash = (value?: string | null) => (value || '').replace(/\/+$/, '')

/**
 * Преобразует URL медиа в рабочий для текущего окружения.
 * localhost / ngrok / production — всё строится динамически.
 */
export const resolveMediaUrl = (url?: string | null) => {
  if (!url) return '/product-placeholder.svg'
  if (url.startsWith('blob:')) return url

  const stripApiSuffix = (value?: string | null) => {
    if (!value) return ''
    return value.endsWith('/api') ? value.slice(0, -4) : value
  }

  const replaceBackendHost = (base: string) => {
    if (!base) return ''
    try {
      const u = new URL(base)
      if (u.hostname === 'backend') {
        if (typeof window !== 'undefined') {
          u.hostname = window.location.hostname
          u.port = ''
          return stripTrailingSlash(u.toString()) || getSiteOrigin()
        }
        return (getInternalApiBase().endsWith('/api') ? getInternalApiBase().slice(0, -4) : getInternalApiBase()).replace(/\/+$/, '')
      }
      return stripTrailingSlash(u.toString())
    } catch {
      return base
    }
  }

  const serverMediaBase = replaceBackendHost(stripApiSuffix(process.env.INTERNAL_API_BASE) || 'http://backend:8000')
  const clientMediaBase = typeof window === 'undefined'
    ? replaceBackendHost(process.env.INTERNAL_API_BASE || 'http://backend:8000')
    : getClientMediaBase()

  // Абсолютный URL: backend/localhost:8000 → относительный путь (браузер запросит с текущего origin).
  // Устраняет Mixed Content и hydration mismatch при ngrok/production.
  if (/^https?:\/\//i.test(url)) {
    try {
      const u = new URL(url)
      const isInternalBackend =
        u.hostname === 'backend' ||
        (u.hostname === 'localhost' && u.port === '8000') ||
        (u.hostname === '127.0.0.1' && u.port === '8000')
      if (isInternalBackend) {
        return `${u.pathname}${u.search || ''}`
      }
      if (serverMediaBase && url.startsWith(serverMediaBase)) {
        return url.replace(serverMediaBase, clientMediaBase || u.origin)
      }
      
      return url
    } catch {
      return url
    }
  }

  // Относительный путь: используем как есть — браузер запросит с текущего origin.
  // Это устраняет Mixed Content и hydration mismatch (сервер не должен подставлять backend:8000).
  if (url.startsWith('/')) {
    return url
  }

  if (clientMediaBase) {
    return `${clientMediaBase}/${url}`
  }

  if (typeof window !== 'undefined') {
    const origin = stripTrailingSlash(window.location.origin)
    return `${origin}/${url}`
  }
  return `/${url}`
}

/**
 * Превью для сетки товаров: запрос уменьшенного WebP через proxy-media (см. max_width в бэкенде).
 */
export function withListingImageMaxWidth(url: string, maxWidth = 480): string {
  if (!url || typeof url !== 'string') return url
  if (!url.includes('proxy-media')) return url
  if (/[?&](max_width|w)=/i.test(url)) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}max_width=${maxWidth}`
}

export const pickMedia = (media?: MediaSource, fallback?: string) => {
  const src = resolveMediaUrl(media?.url)
  if (src) return src
  return fallback || ''
}

/**
 * Универсальный генератор placeholder-изображений.
 */
export function getPlaceholderImageUrl(options?: {
  type?: 'brand' | 'category' | 'product' | 'banner' | 'testimonial'
  id?: number | string
  seed?: string
  width?: number
  height?: number
}): string {
  const {
    type = 'product',
    id,
    seed,
    width = 400,
    height = 300,
  } = options || {}

  const baseSeed = seed || (id !== undefined && id !== null ? `${type}-${id}` : type)
  const safeSeed = encodeURIComponent(String(baseSeed))

  return `https://picsum.photos/seed/${safeSeed}/${width}/${height}`
}
