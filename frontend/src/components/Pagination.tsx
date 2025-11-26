import { useRouter } from 'next/router'

interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange?: (page: number) => void
}

export default function Pagination({ currentPage, totalPages, onPageChange }: PaginationProps) {
  const router = useRouter()
  
  const handlePageChange = (page: number) => {
    if (onPageChange) {
      onPageChange(page)
    } else {
      router.push({
        pathname: router.pathname,
        query: { ...router.query, page }
      })
    }
  }

  const pages: number[] = []
  const max = Math.max(1, totalPages)
  const start = Math.max(1, currentPage - 2)
  const end = Math.min(max, currentPage + 2)
  for (let i = start; i <= end; i++) pages.push(i)

  if (totalPages <= 1) return null

  return (
    <nav className="flex items-center justify-center gap-2" aria-label="Pagination">
      <button
        onClick={() => handlePageChange(currentPage - 1)}
        disabled={currentPage <= 1}
        className={`rounded-md border px-4 py-2 text-sm font-medium transition ${
          currentPage > 1
            ? 'border-violet-200 text-violet-700 hover:bg-violet-50 hover:border-violet-300'
            : 'border-gray-200 text-gray-300 cursor-not-allowed'
        }`}
      >
        Назад
      </button>
      
      {start > 1 && (
        <>
          <button
            onClick={() => handlePageChange(1)}
            className="rounded-md border border-violet-200 px-4 py-2 text-sm font-medium text-violet-700 hover:bg-violet-50 transition"
          >
            1
          </button>
          {start > 2 && <span className="px-2 text-gray-400">…</span>}
        </>
      )}
      
      {pages.map((p) => (
        <button
          key={p}
          onClick={() => handlePageChange(p)}
          className={`rounded-md border px-4 py-2 text-sm font-medium transition ${
            p === currentPage
              ? 'bg-violet-600 border-violet-600 text-white'
              : 'border-violet-200 text-violet-700 hover:bg-violet-50 hover:border-violet-300'
          }`}
        >
          {p}
        </button>
      ))}
      
      {end < max && (
        <>
          {end < max - 1 && <span className="px-2 text-gray-400">…</span>}
          <button
            onClick={() => handlePageChange(max)}
            className="rounded-md border border-violet-200 px-4 py-2 text-sm font-medium text-violet-700 hover:bg-violet-50 transition"
          >
            {max}
          </button>
        </>
      )}
      
      <button
        onClick={() => handlePageChange(currentPage + 1)}
        disabled={currentPage >= max}
        className={`rounded-md border px-4 py-2 text-sm font-medium transition ${
          currentPage < max
            ? 'border-violet-200 text-violet-700 hover:bg-violet-50 hover:border-violet-300'
            : 'border-gray-200 text-gray-300 cursor-not-allowed'
        }`}
      >
        Вперед
      </button>
    </nav>
  )
}


