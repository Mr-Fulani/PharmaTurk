import Link from 'next/link'
import { useRouter } from 'next/router'
import { useAuth } from '../context/AuthContext'
import { useEffect, useState } from 'react'
import api, { initCartSession } from '../lib/api'
import { useCartStore } from '../store/cart'

export default function Header() {
  const router = useRouter()
  const path = router.pathname
  const { user, logout } = useAuth()
  const { itemsCount, refresh } = useCartStore()
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [loadingSuggest, setLoadingSuggest] = useState(false)
  useEffect(() => { initCartSession(); refresh() }, [refresh])

  const goSearch = () => {
    const q = query.trim()
    if (!q) return
    router.push({ pathname: '/search', query: { query: q } })
  }

  const toggleLocale = () => {
    const next = router.locale === 'ru' ? 'en' : 'ru'
    router.push(router.asPath, router.asPath, { locale: next })
  }

  // i18n placeholder
  const placeholder = router.locale === 'ru'
    ? 'Искать витамины, магний, для суставов...'
    : 'Search vitamins, magnesium, joints...'

  // Debounced suggestions
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setSuggestions([])
      return
    }
    const id = setTimeout(async () => {
      setLoadingSuggest(true)
      try {
        let data: any[] = []
        try {
          const rList = await api.get('/catalog/products', { params: { search: q, page_size: 6 } })
          data = Array.isArray(rList.data) ? rList.data : (rList.data.results || [])
        } catch {}
        if (!data || data.length === 0) {
          try {
            const rAct = await api.get('/catalog/products/search', { params: { q, limit: 6 } })
            data = Array.isArray(rAct.data) ? rAct.data : (rAct.data.results || [])
          } catch {}
        }
        setSuggestions(data)
      } catch {
        setSuggestions([])
      } finally {
        setLoadingSuggest(false)
      }
    }, 250)
    return () => clearTimeout(id)
  }, [query])

  return (
    <header className="sticky top-0 z-10 border-b border-violet-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
        <Link href="/" className="text-lg font-bold text-violet-700">Turk-Export</Link>
        <div className="hidden flex-1 items-center gap-3 md:flex">
          <div className="relative flex w-full max-w-xl items-center">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={placeholder}
              onKeyDown={(e)=>{ if (e.key === 'Enter') { e.preventDefault(); goSearch() } }}
              className="w-full rounded-l-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-gray-400"
            />
            <button onClick={goSearch} className="rounded-r-lg border border-l-0 border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100">Поиск</button>
            {query.trim().length >= 2 && (suggestions.length > 0 || loadingSuggest) ? (
              <div className="absolute left-0 top-full z-20 mt-1 w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow">
                {loadingSuggest ? (
                  <div className="px-3 py-2 text-sm text-gray-500">Поиск…</div>
                ) : suggestions.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => router.push(`/product/${p.slug}`)}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-gray-50"
                  >
                    <span className="line-clamp-1 pr-2 text-gray-800">{p.name}</span>
                    <span className="whitespace-nowrap text-gray-600">{p.price ? `${p.price} ${p.currency}` : ''}</span>
                  </button>
                ))}
                <div className="border-t px-3 py-2 text-right">
                  <button onClick={goSearch} className="text-xs text-violet-700 hover:underline">Показать все результаты</button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/" className={path === '/' ? 'font-medium text-gray-900' : 'text-gray-600 hover:text-gray-800'}>Главная</Link>
          <Link href="/categories" className={path.startsWith('/categories') ? 'font-medium text-gray-900' : 'text-gray-600 hover:text-gray-800'}>Категории</Link>
          <Link href="/cart" className={path.startsWith('/cart') ? 'font-medium text-gray-900' : 'text-gray-600 hover:text-gray-800'}>
            Корзина {itemsCount ? `(${itemsCount})` : ''}
          </Link>
          {user ? (
            <>
              <Link href="/profile" className={path.startsWith('/profile') ? 'font-medium text-gray-900' : 'text-gray-600 hover:text-gray-800'}>Профиль</Link>
              <button onClick={logout} className="rounded-md border border-gray-300 px-3 py-1.5 text-gray-800 hover:bg-gray-50">Выйти</button>
            </>
          ) : (
            <>
              <Link href="/auth" className="rounded-md bg-violet-600 px-3 py-1.5 font-medium text-white hover:bg-violet-700">Войти / Регистрация</Link>
            </>
          )}
          <button onClick={toggleLocale} className="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50" title="Язык">{router.locale?.toUpperCase() || 'EN'}</button>
        </nav>
      </div>
    </header>
  )
}
