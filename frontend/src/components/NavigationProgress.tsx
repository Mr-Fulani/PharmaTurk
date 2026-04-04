import { useCallback, useEffect, useRef, useState, type MutableRefObject } from 'react'
import { useRouter } from 'next/router'

/** Показ после старта перехода: меньше, чем раньше, иначе prefetch успевает до таймера */
const SHOW_DELAY_MS = 55
/**
 * Если кликнули по <a>, а routeChangeStart не случился (preventDefault, только hash и т.д.) —
 * убираем полоску.
 */
const CLICK_OR_POPSTATE_WATCHDOG_MS = 700

/** Внутренняя навигация SPA (тот же сайт), без mailto/tel/javascript и якорей «только #». */
function isSpaInternalHref(raw: string | null | undefined): boolean {
  if (raw == null) return false
  const t = raw.trim()
  if (!t || t === '#' || t.startsWith('#')) return false
  if (/^(mailto:|tel:|javascript:)/i.test(t)) return false
  try {
    if (t.startsWith('/')) return true
    if (typeof window === 'undefined') return false
    const u = new URL(t, window.location.origin)
    return u.origin === window.location.origin
  } catch {
    return false
  }
}

function armWatchdog(
  watchdogRef: MutableRefObject<ReturnType<typeof setTimeout> | null>,
  clearWatchdog: () => void,
  clearShowTimer: () => void,
  routeTransitionRef: MutableRefObject<boolean>,
  setVisible: (v: boolean) => void,
) {
  clearWatchdog()
  watchdogRef.current = setTimeout(() => {
    watchdogRef.current = null
    if (!routeTransitionRef.current) {
      clearShowTimer()
      setVisible(false)
    }
  }, CLICK_OR_POPSTATE_WATCHDOG_MS)
}

/**
 * Индикатор переходов: router.events + клики по внутренним ссылкам + popstate (назад/вперёд).
 * Покрывает случаи, когда routeChangeStart запаздывает или prefetch завершает слишком рано для длинной задержки.
 */
export default function NavigationProgress() {
  const router = useRouter()
  const [visible, setVisible] = useState(false)
  const showTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const clickWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Был ли routeChangeStart для текущей цепочки (сбрасывается в Complete/Error). */
  const routeTransitionRef = useRef(false)

  const clearShowTimer = useCallback(() => {
    if (showTimerRef.current !== null) {
      clearTimeout(showTimerRef.current)
      showTimerRef.current = null
    }
  }, [])

  const clearWatchdog = useCallback(() => {
    if (clickWatchdogRef.current !== null) {
      clearTimeout(clickWatchdogRef.current)
      clickWatchdogRef.current = null
    }
  }, [])

  const scheduleShow = useCallback(() => {
    clearShowTimer()
    showTimerRef.current = setTimeout(() => setVisible(true), SHOW_DELAY_MS)
  }, [clearShowTimer])

  const onRouteChangeStart = useCallback(() => {
    routeTransitionRef.current = true
    clearWatchdog()
    scheduleShow()
  }, [clearWatchdog, scheduleShow])

  const onRouteChangeEnd = useCallback(() => {
    routeTransitionRef.current = false
    clearShowTimer()
    clearWatchdog()
    setVisible(false)
  }, [clearShowTimer, clearWatchdog])

  useEffect(() => {
    const { events } = router
    events.on('routeChangeStart', onRouteChangeStart)
    events.on('routeChangeComplete', onRouteChangeEnd)
    events.on('routeChangeError', onRouteChangeEnd)
    return () => {
      events.off('routeChangeStart', onRouteChangeStart)
      events.off('routeChangeComplete', onRouteChangeEnd)
      events.off('routeChangeError', onRouteChangeEnd)
    }
  }, [router.events, onRouteChangeStart, onRouteChangeEnd])

  useEffect(() => {
    const onClickCapture = (e: MouseEvent) => {
      if (e.button !== 0) return
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const el = e.target
      if (!(el instanceof Element)) return
      const a = el.closest('a[href]')
      if (!(a instanceof HTMLAnchorElement)) return
      if (a.target === '_blank') return
      if (a.hasAttribute('download')) return
      const hrefAttr = a.getAttribute('href')
      if (!isSpaInternalHref(hrefAttr)) return

      scheduleShow()
      armWatchdog(clickWatchdogRef, clearWatchdog, clearShowTimer, routeTransitionRef, setVisible)
    }

    document.addEventListener('click', onClickCapture, true)
    return () => document.removeEventListener('click', onClickCapture, true)
  }, [scheduleShow, clearWatchdog, clearShowTimer])

  useEffect(() => {
    const onPopState = () => {
      scheduleShow()
      armWatchdog(clickWatchdogRef, clearWatchdog, clearShowTimer, routeTransitionRef, setVisible)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [scheduleShow, clearWatchdog, clearShowTimer])

  return (
    <>
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {visible ? 'Загрузка страницы' : ''}
      </div>
      {visible ? (
        <div
          className="pointer-events-none fixed left-0 right-0 top-0 z-[10050] h-[3px] overflow-hidden bg-black/10 dark:bg-white/15"
          aria-hidden
        >
          <div className="navigation-progress-bar h-full w-[38%] max-w-md rounded-r-full bg-[var(--accent)] shadow-[0_0_10px_var(--accent)]" />
        </div>
      ) : null}
    </>
  )
}
