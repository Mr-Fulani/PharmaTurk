import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/router'

/** Задержка перед показом: быстрые переходы не дёргают UI */
const SHOW_DELAY_MS = 220

/**
 * Визуальная обратная связь при переходах Next.js (клик по ссылке, «назад», locale).
 * Пока грузится getServerSideProps / чанк страницы, пользователь видит полоску сверху.
 */
export default function NavigationProgress() {
  const router = useRouter()
  const [visible, setVisible] = useState(false)
  const delayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const clearDelay = () => {
      if (delayTimerRef.current !== null) {
        clearTimeout(delayTimerRef.current)
        delayTimerRef.current = null
      }
    }

    const onStart = () => {
      clearDelay()
      delayTimerRef.current = setTimeout(() => setVisible(true), SHOW_DELAY_MS)
    }

    const onEnd = () => {
      clearDelay()
      setVisible(false)
    }

    router.events.on('routeChangeStart', onStart)
    router.events.on('routeChangeComplete', onEnd)
    router.events.on('routeChangeError', onEnd)

    return () => {
      clearDelay()
      router.events.off('routeChangeStart', onStart)
      router.events.off('routeChangeComplete', onEnd)
      router.events.off('routeChangeError', onEnd)
    }
  }, [router])

  return (
    <>
      <div
        className="sr-only"
        aria-live="polite"
        aria-atomic="true"
      >
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
