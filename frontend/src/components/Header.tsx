import Link from 'next/link'
import { useRouter } from 'next/router'
import { useAuth } from '../context/AuthContext'
import { useEffect, useState, useRef } from 'react'
import api from '../lib/api'
import { useTranslation } from 'next-i18next'
import { useCartStore } from '../store/cart'
import { useFavoritesStore } from '../store/favorites'

export default function Header() {
  const router = useRouter()
  const path = router.pathname
  const { user, logout } = useAuth()
  const { itemsCount, refresh } = useCartStore()
  const { count: favoritesCount, refresh: refreshFavorites } = useFavoritesStore()
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [loadingSuggest, setLoadingSuggest] = useState(false)
  const [isClient, setIsClient] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const favoritesRefreshedRef = useRef(false)
  const { t } = useTranslation('common')
  
  useEffect(() => { 
    setIsClient(true)
    // Загружаем избранное только один раз при монтировании
    if (!favoritesRefreshedRef.current) {
      favoritesRefreshedRef.current = true
      refreshFavorites()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Закрываем выпадающее меню при переходе на другую страницу
  useEffect(() => {
    setShowSuggestions(false)
    setSuggestions([])
  }, [path])

  // Закрываем выпадающее меню при клике вне его области
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSuggestions(false)
      }
    }
    if (showSuggestions) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showSuggestions])

  const goSearch = () => {
    const q = query.trim()
    if (!q) return
    router.push({ pathname: '/search', query: { query: q } })
  }

  const toggleLocale = () => {
    const next = router.locale === 'ru' ? 'en' : 'ru'
    // Меняем только pathname + locale, без asPath (чтобы сработал перевод и SSR словарей)
    router.push({ pathname: router.pathname, query: router.query }, undefined, { locale: next })
  }

  // i18n placeholder - используем fallback для предотвращения ошибки гидратации
  const placeholder = isClient ? t('search_placeholder') : 'Search...'

  // Debounced suggestions
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }
    setShowSuggestions(true)
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
    <header className="sticky top-0 z-50 border-b border-red-400 bg-gradient-to-r from-red-100 via-red-50 to-rose-100 backdrop-blur shadow-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
        <Link href="/" className="text-lg font-bold text-red-700 transition-all duration-200 hover:text-red-800 hover:scale-105">Turk-Export</Link>
        <div className="hidden flex-1 items-center gap-3 md:flex">
          <div ref={searchRef} className="relative flex w-full max-w-xl items-center">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => { if (query.trim().length >= 2) setShowSuggestions(true) }}
              placeholder={placeholder}
              onKeyDown={(e)=>{ if (e.key === 'Enter') { e.preventDefault(); setShowSuggestions(false); goSearch() } }}
              className="w-full rounded-l-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-gray-400"
            />
            <button onClick={() => { setShowSuggestions(false); goSearch() }} className="rounded-r-lg border border-l-0 border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 transition-all duration-200 hover:bg-red-100 hover:border-red-400 hover:text-red-700 hover:font-medium">{t('search_button', 'Поиск')}</button>
            {showSuggestions && query.trim().length >= 2 && (suggestions.length > 0 || loadingSuggest) ? (
              <div className="absolute left-0 top-full z-20 mt-1 w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg">
                {loadingSuggest ? (
                  <div className="px-3 py-2 text-sm text-gray-500">Поиск…</div>
                ) : suggestions.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => { setShowSuggestions(false); router.push(`/product/${p.slug}`) }}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors duration-200 hover:bg-red-50"
                  >
                    <span className="line-clamp-1 pr-2 text-gray-800">{p.name}</span>
                    <span className="whitespace-nowrap text-gray-600">{p.price ? `${p.price} ${p.currency}` : ''}</span>
                  </button>
                ))}
                {suggestions.length > 0 && (
                  <div className="border-t px-3 py-2 text-right">
                    <button onClick={() => { setShowSuggestions(false); goSearch() }} className="text-xs text-red-700 transition-colors duration-200 hover:text-red-800 hover:underline">Показать все результаты</button>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
        <nav className="relative z-50 flex items-center gap-4 text-sm">
          {user && (
            <Link 
              href="/profile" 
              onClick={() => setShowSuggestions(false)}
              className={`transition-all duration-200 ${path.startsWith('/profile') ? 'font-medium text-red-800' : 'text-gray-700 hover:text-red-700 hover:font-medium'}`}
            >
              {t('header_profile', 'Профиль')}
            </Link>
          )}
          <Link 
            href="/favorites" 
            onClick={() => setShowSuggestions(false)}
            className="relative inline-flex items-center justify-center rounded-full p-2 text-gray-700 transition-all duration-200 hover:bg-red-100 hover:text-red-700"
            title={t('menu_favorites', 'Избранное')}
          >
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
              />
            </svg>
            {isClient && favoritesCount > 0 && (
              <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-600 text-xs font-bold text-white">
                {favoritesCount > 99 ? '99+' : favoritesCount}
              </span>
            )}
          </Link>
          <Link 
            href="/cart" 
            onClick={() => setShowSuggestions(false)}
            className={`transition-all duration-200 ${path.startsWith('/cart') ? 'font-medium text-red-800' : 'text-gray-700 hover:text-red-700 hover:font-medium'}`}
          >
            {t('menu_cart', 'Корзина')} {isClient && itemsCount ? `(${itemsCount})` : ''}
          </Link>
          {user ? (
            <button 
              onClick={() => { setShowSuggestions(false); logout() }} 
              className="rounded-md border border-red-200 px-3 py-1.5 text-gray-800 transition-all duration-200 hover:bg-red-100 hover:border-red-400 hover:shadow-md"
            >
              {t('header_logout', 'Выйти')}
            </button>
          ) : (
            <Link 
              href="/auth" 
              onClick={() => setShowSuggestions(false)}
              className="rounded-md bg-red-600 px-3 py-1.5 font-medium text-white transition-all duration-200 hover:bg-red-700 hover:shadow-lg hover:scale-105"
            >
              {t('menu_login_register', 'Войти / Регистрация')}
            </Link>
          )}
          <button 
            onClick={() => { setShowSuggestions(false); toggleLocale() }} 
            className="rounded-md border border-red-200 px-2 py-1 text-xs text-gray-700 transition-all duration-200 hover:bg-red-100 hover:border-red-400 hover:shadow-md" 
            title="Язык"
          >
            {router.locale?.toUpperCase() || 'EN'}
          </button>
        </nav>
      </div>
    </header>
  )
}
