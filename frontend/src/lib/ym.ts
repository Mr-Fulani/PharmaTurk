/**
 * Яндекс.Метрика — утилита для отправки событий и pageview.
 * Инициализируется ТОЛЬКО после cookie-согласия пользователя.
 */

export const YM_ID = Number(process.env.NEXT_PUBLIC_YM_ID) || 0

/**
 * Отправляет pageview (hit) в Яндекс.Метрику.
 * Вызывается при каждом routeChangeComplete.
 */
export function ymPageHit(url: string): void {
  if (typeof window === 'undefined' || !window.ym || !YM_ID) return
  window.ym(YM_ID, 'hit', url)
}

/**
 * Регистрирует достижение цели.
 * @param target — название цели в Метрике
 * @param params — дополнительные параметры (опционально)
 */
export function ymReachGoal(target: string, params?: Record<string, unknown>): void {
  if (typeof window === 'undefined' || !window.ym || !YM_ID) return
  window.ym(YM_ID, 'reachGoal', target, params)
}

/**
 * Передаёт пользовательские параметры визита.
 */
export function ymParams(params: Record<string, unknown>): void {
  if (typeof window === 'undefined' || !window.ym || !YM_ID) return
  window.ym(YM_ID, 'params', params)
}

/**
 * Инициализирует счётчик программно — используется в useCookieConsent
 * когда скрипт уже загружен, но функция ym ещё не была вызвана.
 */
export function ymInit(): void {
  if (typeof window === 'undefined' || !window.ym || !YM_ID) return
  window.ym(YM_ID, 'init', {
    defer: true,
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: false,
  })
}

// ─── Типы window ─────────────────────────────────────────────────────────────

declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ym: (id: number, action: string, ...args: any[]) => void
  }
}
