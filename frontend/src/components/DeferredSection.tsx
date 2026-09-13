import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Mount client-only sections shortly before scrolling to them, once per visit. */
export default function DeferredSection({ children }: { children: ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      setReady(true)
      return
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setReady(true)
        observer.disconnect()
      }
    }, { rootMargin: '800px 0px' })
    if (containerRef.current) observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={containerRef} data-deferred-section={ready ? 'ready' : 'pending'}>
      {ready ? children : (
        <div aria-hidden="true" className="w-full min-h-[400px] bg-gray-100 dark:bg-gray-800 rounded-2xl mb-12" />
      )}
    </div>
  )
}
