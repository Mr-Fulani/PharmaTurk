// Утилиты для медиаконтента (webp/avif, fallback) — русские комментарии.

import { getClientMediaBase, getInternalApiBase, getSiteOrigin } from './urls'

export type MediaSource = {
  url: string | null | undefined
}

const VIDEO_EXT_REGEX = /\.(mp4|webm|mov|avi|mkv|m4v)(\?|$)/i

/** Проверяет, что URL указывает на видео (по расширению или хосту), а не на картинку. */
export const isVideoUrl = (url?: string | null): boolean => {
  if (!url || typeof url !== 'string') return false
  const path = url.split('?')[0].toLowerCase()
  if (VIDEO_EXT_REGEX.test(path)) return true
  // proxy-media: /api/catalog/proxy-media/?path=... или proxy-media?path=...
  if (/proxy-media/i.test(url) && url.includes('path=')) {
    try {
      const pathMatch = url.match(/[?&]path=([^&]+)/)
      const pathParam = pathMatch ? decodeURIComponent(pathMatch[1]) : ''
      if (pathParam && VIDEO_EXT_REGEX.test(pathParam)) return true
    } catch {
      // ignore
    }
  }
  if (/youtube\.com|youtu\.be|vimeo\.com/i.test(url)) return true
  return false
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
