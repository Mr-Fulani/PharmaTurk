/**
 * Централизованные утилиты для построения URL.
 * Работают для localhost, ngrok и production.
 */

/** Базовый URL бэкенда для SSR (getServerSideProps). Docker: backend:8000, локально: localhost:8000 */
export function getInternalApiBase(): string {
  const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
  return base.replace(/\/+$/, '')
}

/** Полный URL к API для SSR fetch/axios. Всегда заканчивается на /api */
export function getInternalApiUrl(path: string = ''): string {
  const base = getInternalApiBase()
  const apiBase = base.endsWith('/api') ? base : `${base}/api`
  const p = path.startsWith('/') ? path.slice(1) : path
  return p ? `${apiBase}/${p}` : apiBase
}

/**
 * Базовый URL для API на клиенте.
 * ngrok/production (без порта) → /api (rewrites проксируют)
 * localhost:3001/3000 → http://localhost:8000/api
 */
export function getClientApiBase(): string {
  if (typeof window === 'undefined') return '/api'
  const origin = window.location.origin
  if (!origin.match(/:\d+$/)) return '/api'
  if (origin.includes(':3001')) return origin.replace(':3001', ':8000') + '/api'
  if (origin.includes(':3000')) return origin.replace(':3000', ':8000') + '/api'
  return `${origin.replace(/:\d+$/, '')}:8000/api`
}

/**
 * Origin текущего сайта (для canonical, og:url, медиа).
 * На клиенте: window.location.origin
 * На сервере: NEXT_PUBLIC_SITE_URL или fallback
 */
export function getSiteOrigin(): string {
  if (typeof window !== 'undefined') {
    return window.location.origin.replace(/\/+$/, '')
  }
  const url = process.env.NEXT_PUBLIC_SITE_URL || process.env.SITE_URL || 'https://pharmaturk.ru'
  return url.replace(/\/+$/, '')
}

/**
 * Базовый URL для медиа (изображения, видео).
 * ngrok/production: тот же origin (rewrites проксируют /media)
 * localhost:3001: http://localhost:8000
 * На сервере: getSiteOrigin() (NEXT_PUBLIC_SITE_URL) или internal base
 */
export function getClientMediaBase(): string {
  if (typeof window === 'undefined') {
    return getSiteOrigin() || (getInternalApiBase().endsWith('/api') ? getInternalApiBase().slice(0, -4) : getInternalApiBase())
  }
  const origin = window.location.origin.replace(/\/+$/, '')
  if (!origin.match(/:\d+$/)) return origin
  if (origin.includes(':3001')) return origin.replace(':3001', ':8000')
  if (origin.includes(':3000')) return origin.replace(':3000', ':8000')
  return `${origin.replace(/:\d+$/, '')}:8000`
}
