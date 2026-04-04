import { useRef, useEffect, useState } from 'react'

export type InViewAutoplayVideoProps = {
  src: string
  poster?: string
  className?: string
  videoClassName?: string
  /** Корень для IntersectionObserver (например rootMargin) */
  rootMargin?: string
  /**
   * true (по умолчанию): не подставлять src, пока блок не в зоне видимости — на витрине долго виден только poster.
   * false: сразу грузить ролик (карточки товаров: приоритет видео должен быть заметен).
   */
  deferUntilInView?: boolean
  onError?: (e: React.SyntheticEvent<HTMLVideoElement>) => void
}

/**
 * Видео в карточке: по умолчанию ленивая загрузка по IntersectionObserver; muted loop.
 */
export default function InViewAutoplayVideo({
  src,
  poster,
  className = '',
  videoClassName = '',
  rootMargin = '80px',
  deferUntilInView = true,
  onError,
}: InViewAutoplayVideoProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [shouldLoad, setShouldLoad] = useState(!deferUntilInView)

  useEffect(() => {
    if (!deferUntilInView) {
      setShouldLoad(true)
      return
    }
    const el = wrapRef.current
    if (!el || typeof IntersectionObserver === 'undefined') {
      setShouldLoad(true)
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setShouldLoad(true)
      },
      { rootMargin, threshold: 0.08 }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [deferUntilInView, rootMargin])

  useEffect(() => {
    const v = videoRef.current
    if (!v || !shouldLoad) return
    const run = () => {
      v.play().catch(() => {})
    }
    if (v.readyState >= 2) run()
    else v.addEventListener('canplay', run, { once: true })
    return () => v.removeEventListener('canplay', run)
  }, [shouldLoad, src])

  return (
    <div ref={wrapRef} className={`absolute inset-0 h-full w-full ${className}`}>
      <video
        ref={videoRef}
        src={shouldLoad ? src : undefined}
        poster={poster}
        className={`pointer-events-none absolute inset-0 h-full w-full object-cover ${videoClassName}`.trim()}
        muted
        loop
        playsInline
        preload={deferUntilInView ? 'none' : 'metadata'}
        autoPlay={false}
        onError={onError}
      />
    </div>
  )
}
