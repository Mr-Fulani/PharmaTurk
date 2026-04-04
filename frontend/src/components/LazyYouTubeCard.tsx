import { useState, useEffect } from 'react'

export type LazyYouTubeCardProps = {
  youtubeId: string
  youtubeThumb: string | null
  title?: string
  alt?: string
  /** Задержка перед монтированием iframe (мс), как на главной */
  iframeDelayMs?: number
  className?: string
}

/**
 * Фоновый YouTube для карточек: сначала превью, iframe — после таймаута или при наведении/клике.
 * Снижает конкуренцию за сеть на страницах со многими карточками.
 */
export default function LazyYouTubeCard({
  youtubeId,
  youtubeThumb,
  title,
  alt,
  iframeDelayMs = 2500,
  className = '',
}: LazyYouTubeCardProps) {
  const [loadIframe, setLoadIframe] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setLoadIframe(true), iframeDelayMs)
    return () => clearTimeout(timer)
  }, [iframeDelayMs])

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
      className={`pointer-events-none absolute inset-0 h-full w-full overflow-hidden ${className}`}
      onMouseEnter={() => setLoadIframe(true)}
      onClick={() => setLoadIframe(true)}
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
          className={`pointer-events-none absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ${loadIframe ? 'opacity-0' : 'opacity-100'}`}
        />
      )}
      {loadIframe && (
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
