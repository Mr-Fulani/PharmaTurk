import { useRef, useEffect, useState } from 'react'

export type InViewAmbientIframeProps = {
  src: string
  title: string
  className?: string
  iframeClassName?: string
  rootMargin?: string
  allow?: string
}

/**
 * Встраивание Vimeo (и др.) в карточку: iframe только после появления в viewport.
 */
export default function InViewAmbientIframe({
  src,
  title,
  className = '',
  iframeClassName = '',
  rootMargin = '100px',
  allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture',
}: InViewAmbientIframeProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(false)

  useEffect(() => {
    const el = wrapRef.current
    if (!el || typeof IntersectionObserver === 'undefined') {
      setActive(true)
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setActive(true)
      },
      { rootMargin, threshold: 0.02 }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [rootMargin])

  return (
    <div ref={wrapRef} className={`relative h-full w-full overflow-hidden ${className}`}>
      {active ? (
        <iframe
          src={src}
          title={title}
          loading="lazy"
          allow={allow}
          allowFullScreen
          className={`pointer-events-none absolute inset-0 h-full w-full border-0 object-cover ${iframeClassName}`.trim()}
        />
      ) : (
        <div className="absolute inset-0 bg-gray-200/80 dark:bg-gray-800/80" aria-hidden />
      )}
    </div>
  )
}
