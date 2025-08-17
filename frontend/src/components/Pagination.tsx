import Link from 'next/link'

export default function Pagination({ current, totalPages }: { current: number; totalPages: number }) {
  const make = (p: number) => ({ pathname: '/', query: { page: p } })
  const pages: number[] = []
  const max = Math.max(1, totalPages)
  const start = Math.max(1, current - 2)
  const end = Math.min(max, current + 2)
  for (let i = start; i <= end; i++) pages.push(i)

  return (
    <nav className="inline-flex items-center gap-1" aria-label="Pagination">
      {current > 1 ? (
        <Link href={make(current - 1)} className="rounded-md border border-violet-200 px-3 py-1.5 text-sm text-violet-700 transition hover:bg-violet-50">←</Link>
      ) : (
        <span className="cursor-not-allowed rounded-md border border-violet-100 px-3 py-1.5 text-sm text-gray-300">←</span>
      )}
      {start > 1 ? (
        <>
          <Link href={make(1)} className="rounded-md border border-violet-200 px-3 py-1.5 text-sm text-violet-700 transition hover:bg-violet-50">1</Link>
          {start > 2 ? <span className="px-1 text-gray-400">…</span> : null}
        </>
      ) : null}
      {pages.map((p) => (
        <Link
          key={p}
          href={make(p)}
          className={
            p === current
              ? 'rounded-md bg-violet-600 px-3 py-1.5 text-sm font-medium text-white'
              : 'rounded-md border border-violet-200 px-3 py-1.5 text-sm text-violet-700 transition hover:bg-violet-50'
          }
        >
          {p}
        </Link>
      ))}
      {end < max ? (
        <>
          {end < max - 1 ? <span className="px-1 text-gray-400">…</span> : null}
          <Link href={make(max)} className="rounded-md border border-violet-200 px-3 py-1.5 text-sm text-violet-700 transition hover:bg-violet-50">{max}</Link>
        </>
      ) : null}
      {current < max ? (
        <Link href={make(current + 1)} className="rounded-md border border-violet-200 px-3 py-1.5 text-sm text-violet-700 transition hover:bg-violet-50">→</Link>
      ) : (
        <span className="cursor-not-allowed rounded-md border border-violet-100 px-3 py-1.5 text-sm text-gray-300">→</span>
      )}
    </nav>
  )
}


