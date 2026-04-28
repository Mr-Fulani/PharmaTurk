import Link from 'next/link'
import { useRouter } from 'next/router'
import { useAuth } from '../context/AuthContext'
import { useEffect, useState, useRef } from 'react'
import api, { setPreferredCurrency } from '../lib/api'
import { useTranslation } from 'next-i18next'
import { useCartStore } from '../store/cart'
import { useFavoritesStore } from '../store/favorites'
import AnimatedLogoutButton from './AnimatedLogoutButton'
import { useTheme } from '../context/ThemeContext'
import Cookies from 'js-cookie'
import DotMenu from './DotMenu'
import { buildProductIdentityKey } from '../lib/product'

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
  const [showCurrencyMenu, setShowCurrencyMenu] = useState(false)
  const [currency, setCurrency] = useState('RUB')
  const [scrolled, setScrolled] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const mobileSearchRef = useRef<HTMLDivElement>(null)
  const currencyRef = useRef<HTMLDivElement>(null)
  const mobileCurrencyRef = useRef<HTMLDivElement>(null)
  const favoritesRefreshedRef = useRef(false)
  const { t } = useTranslation('common')
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'
  const currencyOptions = ['RUB', 'USD', 'EUR', 'TRY', 'KZT', 'USDT']

  useEffect(() => {
    setIsClient(true)
    // Загружаем избранное только один раз при монтировании
    if (!favoritesRefreshedRef.current) {
      favoritesRefreshedRef.current = true
      refreshFavorites()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleCurrencyChange = async (nextCurrency: string) => {
    if (nextCurrency === currency) {
      setShowCurrencyMenu(false)
      return
    }
    setShowCurrencyMenu(false)

    // Сохраняем валюту в cookie и глобальное состояние
    Cookies.set('currency', nextCurrency, { sameSite: 'Lax', path: '/' })
    setPreferredCurrency(nextCurrency)
    setCurrency(nextCurrency)

    // Для авторизованных сохраняем в профиль
    if (user) {
      try {
        await api.patch(`/users/profile/${user.id}`, { currency: nextCurrency })
      } catch {
        // no-op: UI already updated, API error will show in network logs
      }
    }

    // Даем время браузеру сохранить cookie, затем перезагружаем страницу
    setTimeout(() => {
      window.location.reload()
    }, 100)
  }

  useEffect(() => {
    // Cookie совпадает с X-Currency в api.ts; для авторизованных раньше брали только
    // user.currency — при неуспешном PATCH профиль в БД отставал, индикатор «залипал» на USDT.
    const savedCurrency = Cookies.get('currency')
    if (savedCurrency) {
      setCurrency(savedCurrency)
      return
    }
    if (user?.currency) {
      setCurrency(user.currency)
    } else {
      setCurrency('RUB')
    }
  }, [user])

  // Эффект изменения состояния хедера при скролле
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  // Закрываем выпадающее меню при переходе на другую страницу
  useEffect(() => {
    setShowSuggestions(false)
    setSuggestions([])
  }, [path])

  // Закрываем выпадающее меню при клике вне его области
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      const isInsideSearch = (searchRef.current && searchRef.current.contains(target))
        || (mobileSearchRef.current && mobileSearchRef.current.contains(target))
      if (!isInsideSearch) {
        setShowSuggestions(false)
      }
      const isInsideCurrency = (currencyRef.current && currencyRef.current.contains(target))
        || (mobileCurrencyRef.current && mobileCurrencyRef.current.contains(target))
      if (!isInsideCurrency) {
        setShowCurrencyMenu(false)
      }
    }
    if (showSuggestions || showCurrencyMenu) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showSuggestions, showCurrencyMenu])

  const goSearch = () => {
    const q = query.trim()
    if (!q) return
    router.push({ pathname: '/search', query: { query: q } })
  }

  const toggleLocale = () => {
    const next = router.locale === 'ru' ? 'en' : 'ru'
    // Сохраняем выбор в куки, чтобы api.ts подхватил его
    Cookies.set('NEXT_LOCALE', next, { expires: 365, path: '/' })
    // Используем replace вместо push для более быстрого переключения без добавления в историю
    router.replace({ pathname: router.pathname, query: router.query }, undefined, { locale: next, scroll: false })
  }

  // i18n placeholder - используем fallback для предотвращения ошибки гидратации
  const placeholder = t('search_placeholder', 'Поиск витаминов, магния...')

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
        // Параллельно запрашиваем товары и услуги для подсказок
        const [productsRes, servicesRes] = await Promise.all([
          api.get('/catalog/products', { params: { search: q, page_size: 6 } }).catch(() => ({ data: [] })),
          api.get('/catalog/services', { params: { search: q, page_size: 6 } }).catch(() => ({ data: [] }))
        ])

        const products = Array.isArray(productsRes.data) ? productsRes.data : (productsRes.data.results || [])
        const services = (Array.isArray(servicesRes.data) ? servicesRes.data : (servicesRes.data.results || []))
          .map((s: any) => ({ ...s, is_service: true }))

        setSuggestions([...products, ...services].slice(0, 10))
      } catch {
        setSuggestions([])
      } finally {
        setLoadingSuggest(false)
      }
    }, 250)
    return () => clearTimeout(id)
  }, [query])

  return (
    <header
      suppressHydrationWarning
      className={`fixed top-0 left-0 w-full z-50 border-b transition-all duration-300 ${
        isDark
          ? 'border-[#1f2a3d] bg-[#0a1222] shadow-[0_10px_40px_rgba(0,0,0,0.6)]'
          : 'border-[var(--border)] bg-[var(--surface)] shadow-md'
      }`}>
      <div className="mx-auto w-full max-w-6xl px-3 sm:px-6">
        <div className={`flex items-center justify-between gap-3 transition-all duration-300 ${scrolled ? 'py-1.5' : 'py-3'}`}>
          <Link href="/" className="flex items-center gap-2.5 transition-all duration-300 hover:opacity-90 group">
            <svg width="34" height="34" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" className={`flex-shrink-0 transition-transform duration-300 group-hover:scale-105 ${isDark ? 'drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]' : 'drop-shadow-md'}`}>
              <defs>
                <linearGradient id={`logo-grad-${isDark ? 'dark' : 'light'}`} x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
                  <stop stopColor={isDark ? "#ef4444" : "#dc2626"} />
                  <stop offset="1" stopColor={isDark ? "#b91c1c" : "#991b1b"} />
                </linearGradient>
              </defs>
              <rect width="40" height="40" rx="10" fill={`url(#logo-grad-${isDark ? 'dark' : 'light'})`} />
              <path d="M7 23H10.5L14.5 13L20 28L25.5 13L29.5 23H33" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="33" cy="23" r="1.5" fill="white" />
            </svg>
            <div className="flex flex-col justify-center">
              <span className={`text-xl font-black tracking-tight leading-none ${isDark ? 'text-slate-50' : 'text-gray-900'}`}>
                MUDAROBA<sup className="text-[0.55em] font-bold ml-0.5 opacity-70">TM</sup>
              </span>
            </div>
          </Link>
          <div className="hidden flex-1 items-center gap-3 md:flex">
            <div ref={searchRef} className="relative flex w-full max-w-xl items-center">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => { if (query.trim().length >= 2) setShowSuggestions(true) }}
                placeholder={t('search_placeholder', 'Поиск лекарств, магния...')}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); setShowSuggestions(false); goSearch() } }}
                className={`w-full rounded-l-lg border px-3 py-2 text-base md:text-sm outline-none transition-colors duration-200 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 placeholder:text-slate-400 focus:border-slate-500' : 'border-gray-300 bg-white text-gray-900 focus:border-gray-400'}`}
              />
              <button onClick={() => { setShowSuggestions(false); goSearch() }} className={`rounded-r-lg border border-l-0 px-3 py-2 text-sm transition-all duration-200 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 hover:bg-slate-700 hover:border-slate-500' : 'border-gray-300 bg-white text-gray-700 hover:bg-red-100 hover:border-red-400 hover:text-red-700 hover:font-medium'}`}>{t('search_button', 'Поиск')}</button>
              {showSuggestions && query.trim().length >= 2 && (suggestions.length > 0 || loadingSuggest) ? (
                <div className={`absolute left-0 top-full z-20 mt-1 w-full overflow-hidden rounded-lg border shadow-lg ${isDark ? 'border-slate-700 bg-slate-800' : 'border-gray-200 bg-white'}`}>
                  {loadingSuggest ? (
                    <div className={`px-3 py-2 text-sm ${isDark ? 'text-slate-300' : 'text-gray-500'}`}>{t('search_loading')}</div>
                  ) : suggestions.map((p) => (
                    <button
                      key={buildProductIdentityKey(p, p.is_service ? 'uslugi' : p.product_type)}
                      onClick={() => { 
                        setShowSuggestions(false); 
                        if (p.is_service) {
                          router.push(`/product/uslugi/${p.slug}`)
                        } else {
                          router.push(`/product/${p.slug}`)
                        }
                      }}
                      className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors duration-200 ${isDark ? 'text-slate-100 hover:bg-slate-700' : 'text-gray-800 hover:bg-red-50'}`}
                    >
                      <span className="line-clamp-1 pr-2">{p.name}</span>
                      <span className={isDark ? 'whitespace-nowrap text-slate-300' : 'whitespace-nowrap text-gray-600'}>{p.price ? `${p.price} ${p.currency}` : ''}</span>
                    </button>
                  ))}
                  {suggestions.length > 0 && (
                    <div className={`border-t px-3 py-2 text-right ${isDark ? 'border-slate-700' : 'border-gray-200'}`}>
                      <button onClick={() => { setShowSuggestions(false); goSearch() }} className={`text-xs transition-colors duration-200 ${isDark ? 'text-slate-100 hover:text-white underline' : 'text-red-700 hover:text-red-800 hover:underline'}`}>{t('search_show_all')}</button>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-2 md:hidden">
            {user ? (
              <AnimatedLogoutButton
                onLogout={() => { setShowSuggestions(false); logout() }}
                isDark={isDark}
                className="scale-90 origin-right"
              />
            ) : (
              <Link
                href="/auth"
                onClick={() => setShowSuggestions(false)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-200 hover:shadow-lg hover:scale-105 ${isDark ? 'bg-[var(--accent)] text-white hover:bg-[var(--accent-strong)]' : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-strong)]'}`}
              >
                {t('login', 'Войти')}
              </Link>
            )}
            <DotMenu 
              user={user}
              currency={currency}
              onCurrencyChange={handleCurrencyChange}
              onToggleLocale={toggleLocale}
              isDark={isDark}
            />
          </div>
          <nav className="relative z-50 hidden items-center gap-3 text-sm md:flex">
            <div ref={currencyRef} className="relative">
              <button
                type="button"
                onClick={() => { setShowSuggestions(false); setShowCurrencyMenu((v) => !v) }}
                className={`inline-flex items-center gap-2 rounded-md border px-2 py-1 text-xs transition-all duration-200 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 hover:border-slate-500' : 'border-red-200 bg-white text-gray-700 hover:bg-red-100 hover:border-red-400 hover:shadow-md'}`}
                title={t('currency', 'Валюта')}
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M8 12h8M10 8h4m-4 8h4" strokeLinecap="round" />
                </svg>
                <span>{currency}</span>
              </button>
              {showCurrencyMenu ? (
                <div className={`absolute right-0 z-20 mt-2 w-28 overflow-hidden rounded-md border shadow-lg ${isDark ? 'border-slate-700 bg-slate-800' : 'border-gray-200 bg-white'}`}>
                  {currencyOptions.map((code) => (
                    <button
                      key={code}
                      type="button"
                      onClick={() => handleCurrencyChange(code)}
                      className={`flex w-full items-center justify-between px-3 py-2 text-xs transition-colors duration-200 ${currency === code ? (isDark ? 'bg-slate-700 text-white' : 'bg-red-50 text-red-700') : (isDark ? 'text-slate-100 hover:bg-slate-700' : 'text-gray-700 hover:bg-red-50')}`}
                    >
                      <span>{code}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            {user && (
              <Link
                href="/profile"
                onClick={() => setShowSuggestions(false)}
                className={`transition-all duration-200 ${path.startsWith('/profile') ? (isDark ? 'font-medium text-white' : 'font-medium text-red-800') : (isDark ? 'text-slate-100 hover:text-white' : 'text-gray-700 hover:text-red-700 hover:font-medium')}`}
              >
                {t('header_profile', 'Профиль')}
              </Link>
            )}
            <Link
              href="/favorites"
              onClick={() => setShowSuggestions(false)}
              className={`relative inline-flex items-center justify-center rounded-full p-2 transition-all duration-200 ${isDark ? 'text-slate-100 hover:bg-slate-800' : 'text-main hover:bg-[var(--surface)] hover:text-gray-900'}`}
              title={t('menu_favorites', 'Избранное')}
              aria-label={t('menu_favorites', 'Избранное')}
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
              className={`transition-all duration-200 ${path.startsWith('/cart') ? (isDark ? 'font-medium text-white' : 'font-medium text-gray-900') : (isDark ? 'text-slate-100 hover:text-white' : 'text-main hover:text-gray-900 hover:font-medium')}`}
            >
              {t('menu_cart', 'Корзина')}{isClient && itemsCount ? ` (${itemsCount})` : ''}
            </Link>
            {user ? (
              <AnimatedLogoutButton
                onLogout={() => { setShowSuggestions(false); logout() }}
                isDark={false}
              />
            ) : (
              <Link
                href="/auth"
                onClick={() => setShowSuggestions(false)}
                className={`rounded-md px-3 py-1.5 font-medium transition-all duration-200 hover:shadow-lg hover:scale-105 ${isDark
                  ? 'bg-[var(--accent)] text-white hover:bg-[var(--accent-strong)]'
                  : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-strong)]'
                  }`}
              >
                {t('login', 'Войти')}
              </Link>
            )}
            <button
              onClick={() => { setShowSuggestions(false); toggleTheme() }}
              className={`inline-flex items-center gap-2 rounded-md border px-2 py-1 text-xs transition-all duration-200 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 hover:border-slate-500' : 'border-red-200 bg-white text-gray-700 hover:bg-red-100 hover:border-red-400 hover:shadow-md'}`}
              title={isDark ? t('theme_dark_title', 'Тёмная тема') : t('theme_light_title', 'Светлая тема')}
            >
              {isDark ? (
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M21 12.79A9 9 0 0 1 11.21 3 7 7 0 1 0 21 12.79Z" />
                </svg>
              ) : (
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2m0 16v2m10-10h-2M4 12H2m15.536-7.536-1.414 1.414M7.879 16.121 6.465 17.535m12.071 0-1.414-1.414M7.879 7.879 6.465 6.465" />
                </svg>
              )}
              <span>{isDark ? t('theme_dark', 'Тёмная') : t('theme_light', 'Светлая')}</span>
            </button>
            <button
              onClick={() => { setShowSuggestions(false); toggleLocale() }}
              className={`rounded-md border px-2 py-1 text-xs transition-all duration-200 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 hover:border-slate-500' : 'border-red-200 text-gray-700 hover:bg-red-100 hover:border-red-400 hover:shadow-md'}`}
              title={t('language', 'Язык')}
            >
              {router.locale?.toUpperCase() || 'EN'}
            </button>
          </nav>
        </div>

        <div className="md:hidden pb-4">
          <div ref={mobileSearchRef} className="relative flex w-full items-center">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => { if (query.trim().length >= 2) setShowSuggestions(true) }}
              placeholder={placeholder}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); setShowSuggestions(false); goSearch() } }}
              className={`w-full rounded-l-lg border px-3 py-2 text-base md:text-sm outline-none transition-colors duration-200 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 placeholder:text-slate-400 focus:border-slate-500' : 'border-gray-300 bg-white text-gray-900 focus:border-gray-400'}`}
            />
            <button onClick={() => { setShowSuggestions(false); goSearch() }} className={`rounded-r-lg border border-l-0 px-3 py-2 text-sm transition-all duration-200 ${isDark ? 'border-slate-700 bg-slate-800 text-slate-100 hover:bg-slate-700 hover:border-slate-500' : 'border-gray-300 bg-white text-gray-700 hover:bg-red-100 hover:border-red-400 hover:text-red-700 hover:font-medium'}`}>{t('search_button', 'Поиск')}</button>
            {showSuggestions && query.trim().length >= 2 && (suggestions.length > 0 || loadingSuggest) ? (
              <div className={`absolute left-0 top-full z-20 mt-1 w-full overflow-hidden rounded-lg border shadow-lg ${isDark ? 'border-slate-700 bg-slate-800' : 'border-gray-200 bg-white'}`}>
                {loadingSuggest ? (
                  <div className={`px-3 py-2 text-sm ${isDark ? 'text-slate-300' : 'text-gray-500'}`}>{t('search_loading')}</div>
                ) : suggestions.map((p) => (
                  <button
                    key={buildProductIdentityKey(p, p.product_type)}
                    onClick={() => { setShowSuggestions(false); router.push(`/product/${p.slug}`) }}
                    className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors duration-200 ${isDark ? 'text-slate-100 hover:bg-slate-700' : 'text-gray-800 hover:bg-red-50'}`}
                  >
                    <span className="line-clamp-1 pr-2">{p.name}</span>
                    <span className={isDark ? 'whitespace-nowrap text-slate-300' : 'whitespace-nowrap text-gray-600'}>{p.price ? `${p.price} ${p.currency}` : ''}</span>
                  </button>
                ))}
                {suggestions.length > 0 && (
                  <div className={`border-t px-3 py-2 text-right ${isDark ? 'border-slate-700' : 'border-gray-200'}`}>
                    <button onClick={() => { setShowSuggestions(false); goSearch() }} className={`text-xs transition-colors duration-200 ${isDark ? 'text-slate-100 hover:text-white underline' : 'text-red-700 hover:text-red-800 hover:underline'}`}>{t('search_show_all')}</button>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  )
}
