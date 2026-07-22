import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { AnimatePresence, motion } from 'framer-motion'
import { useTheme } from '../context/ThemeContext'
import { useCartStore } from '../store/cart'
import { useFavoritesStore } from '../store/favorites'
import styles from './DotMenu.module.css'

interface DotMenuProps {
  user: any
  currency: string
  onCurrencyChange: (code: string) => void
  onToggleLocale: () => void
  isDark: boolean
  forceClosed?: boolean
  onOpenChange?: (open: boolean) => void
  onOpenSearch?: () => void
}

interface MenuCenter {
  x: number
  y: number
}

interface MenuItem {
  key: string
  label: string
  icon: React.ReactNode
  href?: string
  badge?: number
  onClick?: () => void
  isCurrency?: boolean
}

const currencyOptions = ['RUB', 'USD', 'EUR', 'TRY', 'KZT', 'USDT']
const currencySymbols: Record<string, string> = {
  RUB: '₽',
  USD: '$',
  EUR: '€',
  TRY: '₺',
  KZT: '₸',
  USDT: '₮',
}
const ITEM_GAP = 42
const ITEM_SIZE = 40

export default function DotMenu({
  user,
  currency,
  onCurrencyChange,
  onToggleLocale,
  isDark,
  forceClosed = false,
  onOpenChange,
  onOpenSearch,
}: DotMenuProps) {
  const [active, setActive] = useState(false)
  const [showCurrencyChoice, setShowCurrencyChoice] = useState(false)
  const [menuCenter, setMenuCenter] = useState<MenuCenter | null>(null)
  const [isClient, setIsClient] = useState(false)
  const { toggleTheme } = useTheme()
  const { itemsCount } = useCartStore()
  const { count: favoritesCount } = useFavoritesStore()
  const { t } = useTranslation('common')
  const router = useRouter()
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const portalRef = useRef<HTMLDivElement>(null)

  const closeMenu = useCallback(() => {
    setActive(false)
    setShowCurrencyChoice(false)
  }, [])

  const updateMenuPosition = useCallback(() => {
    if (!triggerRef.current) return
    const rect = triggerRef.current.getBoundingClientRect()
    setMenuCenter({
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    })
  }, [])

  useEffect(() => setIsClient(true), [])

  useEffect(() => {
    onOpenChange?.(active)
  }, [active, onOpenChange])

  useEffect(() => {
    if (forceClosed) closeMenu()
  }, [closeMenu, forceClosed])

  useEffect(() => {
    closeMenu()
  }, [closeMenu, router.asPath])

  useEffect(() => {
    if (!active) return

    updateMenuPosition()

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      if (!containerRef.current?.contains(target) && !portalRef.current?.contains(target)) {
        closeMenu()
      }
    }
    const syncPosition = () => updateMenuPosition()

    document.addEventListener('mousedown', handleClickOutside)
    window.addEventListener('resize', syncPosition)
    window.addEventListener('scroll', syncPosition, true)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      window.removeEventListener('resize', syncPosition)
      window.removeEventListener('scroll', syncPosition, true)
    }
  }, [active, closeMenu, updateMenuPosition])

  const menuItems: MenuItem[] = [
    {
      key: 'cart',
      label: t('menu_cart', 'Корзина'),
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h15l-1.5 9h-12z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 6l-1-3H3" />
          <circle cx="9" cy="20" r="1" />
          <circle cx="18" cy="20" r="1" />
        </svg>
      ),
      href: '/cart',
      badge: itemsCount,
    },
    {
      key: 'favorites',
      label: t('menu_favorites', 'Избранное'),
      icon: (
        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
        </svg>
      ),
      href: '/favorites',
      badge: favoritesCount,
    },
    {
      key: 'profile',
      label: t('header_profile', 'Профиль'),
      icon: (
        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ),
      href: user ? '/profile' : '/auth?next=/profile',
    },
    {
      key: 'currency',
      label: t('currency', 'Валюта'),
      icon: <CurrencyIcon code={currency} />,
      isCurrency: true,
      onClick: () => setShowCurrencyChoice((value) => !value),
    },
    {
      key: 'language',
      label: t('language', 'Язык'),
      icon: <LanguageFlag locale={router.locale || 'en'} />,
      onClick: onToggleLocale,
    },
    {
      key: 'theme',
      label: isDark ? t('theme_dark_title', 'Тёмная тема') : t('theme_light_title', 'Светлая тема'),
      icon: isDark ? (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
          <path d="M21 12.79A9 9 0 0 1 11.21 3 7 7 0 1 0 21 12.79Z" />
        </svg>
      ) : (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2m0 16v2m10-10h-2M4 12H2m15.536-7.536-1.414 1.414M7.879 16.121 6.465 17.535m12.071 0-1.414-1.414M7.879 7.879 6.465 6.465" />
        </svg>
      ),
      onClick: toggleTheme,
    },
    {
      key: 'search',
      label: t('search_open', 'Открыть поиск'),
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m16 16 5 5" strokeLinecap="round" />
        </svg>
      ),
      onClick: onOpenSearch,
    },
  ]

  const handleMenuItemClick = (item: MenuItem) => {
    if (item.isCurrency) {
      item.onClick?.()
      return
    }
    if (item.onClick) item.onClick()
    if (item.href) router.push(item.href)
    closeMenu()
  }

  const currencyItemIndex = menuItems.findIndex((item) => item.isCurrency)
  const currencyItemX = menuCenter ? menuCenter.x - ITEM_GAP * (currencyItemIndex + 1) : 0
  const currencyPanelWidth = 208
  const currencyPanelLeft = isClient
    ? Math.min(Math.max(currencyItemX - currencyPanelWidth / 2, 12), window.innerWidth - currencyPanelWidth - 12)
    : 12

  const getItemOffset = (index: number) => {
    const isLastItem = index === menuItems.length - 1
    if (isClient && window.innerWidth < 360 && isLastItem) {
      return { x: -ITEM_GAP, y: 48 }
    }
    return { x: -ITEM_GAP * (index + 1), y: 0 }
  }

  const portalContent = isClient && menuCenter
    ? createPortal(
      <div ref={portalRef} className={styles.portalLayer}>
        <AnimatePresence>
          {active && menuItems.map((item, index) => {
            const offset = getItemOffset(index)
            return (
              <motion.div
                key={item.key}
                initial={{ x: 0, y: 0, scale: 0.25, opacity: 0 }}
                animate={{ x: offset.x, y: offset.y, scale: 1, opacity: 1 }}
                exit={{
                  x: 0,
                  y: 0,
                  scale: 0.25,
                  opacity: 0,
                  transition: {
                    duration: 0.4,
                    delay: (menuItems.length - 1 - index) * 0.045,
                    ease: [0.22, 1, 0.36, 1],
                  },
                }}
                transition={{
                  duration: 0.4,
                  delay: index * 0.045,
                  ease: [0.22, 1, 0.36, 1],
                }}
                className={styles.menuItem}
                style={{
                  top: menuCenter.y - ITEM_SIZE / 2,
                  left: menuCenter.x - ITEM_SIZE / 2,
                }}
              >
                <button
                  type="button"
                  onClick={() => handleMenuItemClick(item)}
                  className={`${styles.menuButton} ${item.isCurrency && showCurrencyChoice ? styles.menuButtonActive : ''}`}
                  title={item.label}
                  aria-label={item.label}
                  aria-expanded={item.isCurrency ? showCurrencyChoice : undefined}
                >
                  {item.icon}
                  {item.badge !== undefined && item.badge > 0 && (
                    <span className={styles.badge}>{item.badge > 99 ? '99+' : item.badge}</span>
                  )}
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>

        <AnimatePresence>
          {active && showCurrencyChoice && (
            <motion.div
              initial={{ opacity: 0, y: -8, scale: 0.92 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.92 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className={styles.currencyPanel}
              style={{
                top: menuCenter.y + 30,
                left: currencyPanelLeft,
                width: currencyPanelWidth,
              }}
              role="menu"
              aria-label={t('currency', 'Валюта')}
            >
              {currencyOptions.map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => {
                    closeMenu()
                    onCurrencyChange(code)
                  }}
                  className={`${styles.currencyButton} ${currency === code ? styles.currencyButtonActive : ''}`}
                  role="menuitem"
                >
                  <CurrencyIcon code={code} compact />
                  <span>{code}</span>
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>,
      document.body
    )
    : null

  return (
    <>
      <div ref={containerRef} className={styles.root}>
        <motion.button
          ref={triggerRef}
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            if (!active) updateMenuPosition()
            setShowCurrencyChoice(false)
            setActive((value) => !value)
          }}
          initial={false}
          animate={{ rotate: active ? 360 : 0 }}
          transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
          className={`${styles.trigger} ${active ? styles.triggerActive : ''}`}
          aria-label={active ? t('header_menu_close', 'Закрыть меню') : t('header_menu_open', 'Открыть меню')}
          title={active ? t('header_menu_close', 'Закрыть меню') : t('header_menu_open', 'Открыть меню')}
          aria-expanded={active}
        >
          <span className={`${styles.dotGrid} ${active ? styles.dotGridHidden : ''}`} aria-hidden="true">
            {Array.from({ length: 6 }, (_, index) => <span key={index} />)}
          </span>
          <span className={`${styles.closeIcon} ${active ? styles.closeIconVisible : ''}`} aria-hidden="true">
            <span />
            <span />
          </span>
        </motion.button>
      </div>
      {portalContent}
    </>
  )
}

function LanguageFlag({ locale }: { locale: string }) {
  const isRussian = locale.toLowerCase() === 'ru'

  return (
    <svg
      className={styles.languageFlag}
      viewBox="0 0 32 32"
      role="img"
      aria-label={isRussian ? 'Русский' : 'English'}
    >
      <defs>
        <clipPath id="dot-menu-language-flag">
          <circle cx="16" cy="16" r="15" />
        </clipPath>
      </defs>
      <g clipPath="url(#dot-menu-language-flag)">
        {isRussian ? (
          <>
            <rect width="32" height="11" y="0" fill="#fff" />
            <rect width="32" height="11" y="11" fill="#1857a4" />
            <rect width="32" height="10" y="22" fill="#d52b1e" />
          </>
        ) : (
          <>
            <rect width="32" height="32" fill="#fff" />
            {[0, 4.92, 9.84, 14.76, 19.68, 24.6, 29.52].map((y) => (
              <rect key={y} width="32" height="2.47" y={y} fill="#b22234" />
            ))}
            <rect width="17.5" height="17.25" fill="#3c3b6e" />
            {[3, 8.5, 14].flatMap((y) => [3, 7, 11, 15].map((x) => (
              <circle key={`${x}-${y}`} cx={x} cy={y} r="0.9" fill="#fff" />
            )))}
          </>
        )}
      </g>
      <circle cx="16" cy="16" r="15" fill="none" stroke="rgba(15, 23, 42, 0.22)" />
    </svg>
  )
}

function CurrencyIcon({ code, compact = false }: { code: string; compact?: boolean }) {
  const normalizedCode = code.toUpperCase()

  return (
    <span className={`${styles.currencyIcon} ${compact ? styles.currencyIconCompact : ''}`} aria-hidden="true">
      <svg className={styles.currencyFlag} viewBox="0 0 32 32">
        {normalizedCode === 'RUB' && (
          <>
            <rect width="32" height="11" fill="#fff" />
            <rect width="32" height="11" y="11" fill="#1857a4" />
            <rect width="32" height="10" y="22" fill="#d52b1e" />
          </>
        )}
        {normalizedCode === 'USD' && (
          <>
            <rect width="32" height="32" fill="#fff" />
            {[0, 4.92, 9.84, 14.76, 19.68, 24.6, 29.52].map((y) => (
              <rect key={y} width="32" height="2.47" y={y} fill="#b22234" />
            ))}
            <rect width="17.5" height="17.25" fill="#3c3b6e" />
            {[3, 8.5, 14].flatMap((y) => [3, 7, 11, 15].map((x) => (
              <circle key={`${x}-${y}`} cx={x} cy={y} r="0.9" fill="#fff" />
            )))}
          </>
        )}
        {normalizedCode === 'EUR' && (
          <>
            <rect width="32" height="32" fill="#003399" />
            {Array.from({ length: 12 }, (_, index) => {
              const angle = (index * Math.PI * 2) / 12 - Math.PI / 2
              return (
                <circle
                  key={index}
                  cx={16 + Math.cos(angle) * 8.5}
                  cy={16 + Math.sin(angle) * 8.5}
                  r="1.25"
                  fill="#ffcc00"
                />
              )
            })}
          </>
        )}
        {normalizedCode === 'TRY' && (
          <>
            <rect width="32" height="32" fill="#e30a17" />
            <circle cx="13.2" cy="16" r="7.6" fill="#fff" />
            <circle cx="15.7" cy="14.6" r="6.4" fill="#e30a17" />
            <path d="m22.8 12.2 1.05 2.15 2.38.34-1.72 1.68.4 2.37-2.11-1.12-2.12 1.12.4-2.37-1.71-1.68 2.37-.34Z" fill="#fff" />
          </>
        )}
        {normalizedCode === 'KZT' && (
          <>
            <rect width="32" height="32" fill="#00afca" />
            <circle cx="16" cy="12.5" r="4.1" fill="#f6c445" />
            {Array.from({ length: 12 }, (_, index) => {
              const angle = (index * Math.PI * 2) / 12
              return (
                <path
                  key={index}
                  d="M16 6.3v2.1"
                  stroke="#f6c445"
                  strokeWidth="1.1"
                  strokeLinecap="round"
                  transform={`rotate(${(angle * 180) / Math.PI} 16 12.5)`}
                />
              )
            })}
            <path d="M7 21.3c3.2 1.1 5.8.45 9-2.35 3.2 2.8 5.8 3.45 9 2.35-2.1 4.7-15.9 4.7-18 0Z" fill="#f6c445" />
          </>
        )}
        {normalizedCode === 'USDT' && (
          <>
            <rect width="32" height="32" fill="#26a17b" />
            <path d="M8 8h16v4H18v2.1c5.4.25 9.4 1.25 9.4 2.45S23.4 18.75 18 19v6h-4v-6c-5.4-.25-9.4-1.25-9.4-2.45s4-2.2 9.4-2.45V12H8Zm6 8.2c-3.25.16-5.42.55-5.42 1s2.17.84 5.42 1Zm4 2c3.25-.16 5.42-.55 5.42-1s-2.17-.84-5.42-1Z" fill="#fff" />
          </>
        )}
      </svg>
      {!compact && (
        <span className={styles.currencySymbol}>{currencySymbols[normalizedCode] || normalizedCode.slice(0, 1)}</span>
      )}
    </span>
  )
}
