import { useRef, useEffect, useState } from 'react'

export type InViewAutoplayVideoProps = {
  src: string
  poster?: string
  className?: string
  videoClassName?: string
  /** Корень для IntersectionObserver (например rootMargin) */
  rootMargin?: string
  onError?: (e: React.SyntheticEvent<HTMLVideoElement>) => void
}

/**
 * Видео в карточке: не грузит поток, пока блок не в зоне видимости; затем muted loop.
 */
export default function InViewAutoplayVideo({
  src,
  poster,
  className = '',
  videoClassName = '',
  rootMargin = '80px',
  onError,
}: InViewAutoplayVideoProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [shouldLoad, setShouldLoad] = useState(false)

  useEffect(() => {
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
  }, [rootMargin])

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
        preload="none"
        autoPlay={false}
        onError={onError}
      />
    </div>
  )
}
