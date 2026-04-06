/**
 * Google Analytics 4 через gtag.js.
 * Скрипт подключается в _app только после cookie-согласия.
 *
 * Если тот же поток GA4 (тот же G-...) уже настроен как тег внутри GTM,
 * отключите один из вариантов, иначе возможен двойной учёт просмотров.
 */

export const GA4_MEASUREMENT_ID = process.env.NEXT_PUBLIC_GA4_ID || ''

/**
 * Обновляет page_path в GA4 при навигации Next.js (SPA).
 */
export function ga4PageView(url: string): void {
  if (typeof window === 'undefined' || !GA4_MEASUREMENT_ID) return
  if (typeof window.gtag !== 'function') return
  window.gtag('config', GA4_MEASUREMENT_ID, { page_path: url })
}

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void
  }
}
