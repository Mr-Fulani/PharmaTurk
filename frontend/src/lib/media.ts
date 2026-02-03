// Утилиты для медиаконтента (webp/avif, fallback) — русские комментарии.

export type MediaSource = {
  url: string | null | undefined
}

const VIDEO_EXT_REGEX = /\.(mp4|webm|mov|avi|mkv|m4v)(\?|$)/i

/** Проверяет, что URL указывает на видео (по расширению или хосту), а не на картинку. */
export const isVideoUrl = (url?: string | null): boolean => {
  if (!url || typeof url !== 'string') return false
  const path = url.split('?')[0].toLowerCase()
  if (VIDEO_EXT_REGEX.test(path)) return true
  // Прокси бэкенда: /api/catalog/proxy-media/?path=...file.MP4
  if (/\/proxy-media\//i.test(url) && url.includes('path=')) {
    try {
      const pathParam = new URL(url).searchParams.get('path') || ''
      if (VIDEO_EXT_REGEX.test(pathParam)) return true
    } catch {
      // ignore
    }
  }
  if (/youtube\.com|youtu\.be|vimeo\.com/i.test(url)) return true
  return false
}

const stripTrailingSlash = (value?: string | null) => (value || '').replace(/\/+$/, '')

export const resolveMediaUrl = (url?: string | null) => {
  if (!url) return '/product-placeholder.svg'

  const clientApi = process.env.NEXT_PUBLIC_API_BASE
  const serverApi = process.env.INTERNAL_API_BASE

  const stripApiSuffix = (value?: string | null) => {
    if (!value) return ''
    return value.endsWith('/api') ? value.slice(0, -4) : value
  }

  const fallbackMediaBase = process.env.NEXT_PUBLIC_MEDIA_BASE || 'http://localhost:8000'

  const replaceBackendHost = (base: string) => {
    if (!base) return ''
    try {
      const u = new URL(base)
      if (u.hostname === 'backend') {
        if (typeof window !== 'undefined') {
          u.hostname = window.location.hostname
        } else {
          u.hostname = 'localhost'
          u.port = u.port || '8000'
        }
      }
      return stripTrailingSlash(u.toString())
    } catch {
      return base
    }
  }

  const serverMediaBase = replaceBackendHost(stripApiSuffix(serverApi) || 'http://backend:8000')
  const clientMediaBase =
    typeof window === 'undefined'
      ? replaceBackendHost(stripApiSuffix(serverApi) || stripApiSuffix(clientApi) || fallbackMediaBase)
      : replaceBackendHost(stripApiSuffix(clientApi) || '') ||
        `${window.location.protocol}//${window.location.hostname}:8000`

  // Абсолютный URL: если указывает на backend/внутренний хост — заменяем на публичный
  if (/^https?:\/\//i.test(url)) {
    try {
      const u = new URL(url)
      if (serverMediaBase && url.startsWith(serverMediaBase)) {
        return url.replace(serverMediaBase, clientMediaBase || u.origin)
      }
      if (u.hostname === 'backend') {
        const origin8000 =
          typeof window !== 'undefined'
            ? `${window.location.protocol}//${window.location.hostname}:8000`
            : fallbackMediaBase
        return `${origin8000}${u.pathname}${u.search}`
      }
      return url
    } catch {
      return url
    }
  }

  // Относительный путь
  if (clientMediaBase) {
    return url.startsWith('/') ? `${clientMediaBase}${url}` : `${clientMediaBase}/${url}`
  }

  if (typeof window !== 'undefined') {
    const origin = stripTrailingSlash(window.location.origin)
    return url.startsWith('/') ? `${origin}${url}` : `${origin}/${url}`
  }
  return url
}

export const pickMedia = (media?: MediaSource, fallback?: string) => {
  // Возвращает webp/avif если это исходный формат, иначе оригинал/фолбек.
  const src = resolveMediaUrl(media?.url)
  if (src) return src
  return fallback || ''
}

