import { useRef, useEffect, useState } from 'react'
import { applyImageFallback, DEFAULT_MEDIA_FALLBACK } from '../lib/media'

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
  fallbackSrc?: string
  alt?: string
}

export default function InViewAutoplayVideo({
  src,
  poster,
  className = '',
  videoClassName = '',
  rootMargin = '80px',
  deferUntilInView = true,
  onError,
  fallbackSrc = DEFAULT_MEDIA_FALLBACK,
  alt = 'MUDAROBA',
}: InViewAutoplayVideoProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [shouldLoad, setShouldLoad] = useState(!deferUntilInView)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [src])

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
        if (entry.isIntersecting) {
          setShouldLoad(true)
          io.disconnect()
        }
      },
      { rootMargin, threshold: 0.08 }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [deferUntilInView, rootMargin])

  return (
    <div ref={wrapRef} className={`absolute inset-0 h-full w-full ${className}`}>
      {failed ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={fallbackSrc}
          alt={alt}
          className={`pointer-events-none absolute inset-0 h-full w-full object-cover ${videoClassName}`.trim()}
          onError={(event) => applyImageFallback(event.currentTarget)}
        />
      ) : shouldLoad ? (
        <video
          src={src}
          poster={poster}
          className={`pointer-events-none absolute inset-0 h-full w-full object-cover ${videoClassName}`.trim()}
          muted
          loop
          playsInline
          autoPlay
          preload="metadata"
          onError={(event) => {
            onError?.(event)
            setFailed(true)
          }}
        />
      ) : (
        poster ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={poster}
            alt="Video poster"
            className={`pointer-events-none absolute inset-0 h-full w-full object-cover ${videoClassName}`.trim()}
            loading="lazy"
            onError={(event) => applyImageFallback(event.currentTarget, fallbackSrc)}
          />
        ) : null
      )}
    </div>
  )
}
