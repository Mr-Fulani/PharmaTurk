import { useState, useEffect, useRef } from 'react'

export type LazyYouTubeCardProps = {
  youtubeId: string
  youtubeThumb: string | null
  title?: string
  alt?: string
  /** Задержка после появления в viewport перед монтированием iframe (мс) */
  iframeDelayMs?: number
  className?: string
}

/**
 * Фоновый YouTube для карточек: превью до входа в viewport; iframe только при пересечении с экраном
 * и после задержки / наведения / клика — без лишней нагрузки на сеть вне видимой области.
 */
export default function LazyYouTubeCard({
  youtubeId,
  youtubeThumb,
  title,
  alt,
  iframeDelayMs = 2500,
  className = '',
}: LazyYouTubeCardProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)
  const [wantsIframe, setWantsIframe] = useState(false)

  useEffect(() => {
    const el = rootRef.current
    if (!el || typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) setInView(true)
      },
      { root: null, rootMargin: '0px', threshold: 0.01 }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!inView) return
    const timer = setTimeout(() => setWantsIframe(true), iframeDelayMs)
    return () => clearTimeout(timer)
  }, [inView, iframeDelayMs])

  const showIframe = inView && wantsIframe

  const base = `https://www.youtube-nocookie.com/embed/${youtubeId}`
  const params = [
    'autoplay=1',
    'mute=1',
    'loop=1',
    `playlist=${youtubeId}`,
    'controls=0',
    'playsinline=1',
    'rel=0',
    'modestbranding=1',
    'iv_load_policy=3',
    'cc_load_policy=0',
    'fs=0',
    'disablekb=1',
    'showinfo=0',
    'autohide=1',
  ].join('&')
  const embedUrl = `${base}?${params}`

  return (
    <div
      ref={rootRef}
      className={`pointer-events-none absolute inset-0 h-full w-full overflow-hidden ${className}`}
      onMouseEnter={() => setWantsIframe(true)}
      onClick={() => setWantsIframe(true)}
    >
      {youtubeThumb && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={youtubeThumb}
          alt={alt || title || 'Video thumbnail'}
          loading="lazy"
          decoding="async"
          width={480}
          height={360}
          className={`pointer-events-none absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ${showIframe ? 'opacity-0' : 'opacity-100'}`}
        />
      )}
      {showIframe && (
        <iframe
          src={embedUrl}
          title={alt || title || 'YouTube'}
          className="pointer-events-none absolute inset-0 h-full w-full object-cover"
          allow="autoplay; encrypted-media; picture-in-picture"
          loading="lazy"
          allowFullScreen={false}
          style={{ opacity: 0, transition: 'opacity 0.7s ease' }}
          onLoad={(e) => {
            e.currentTarget.style.opacity = '1'
          }}
        />
      )}
    </div>
  )
}
