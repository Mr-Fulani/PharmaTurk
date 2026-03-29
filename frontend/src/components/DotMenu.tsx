import { useState, useRef, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { useTheme } from '../context/ThemeContext'
import { useCartStore } from '../store/cart'
import { useFavoritesStore } from '../store/favorites'
import { motion, AnimatePresence } from 'framer-motion'
import styles from './DotMenu.module.css'

interface DotMenuProps {
  user: any
  currency: string
  onCurrencyChange: (code: string) => void
  onToggleLocale: () => void
  isDark: boolean
}

const currencyOptions = ['RUB', 'USD', 'EUR', 'TRY', 'KZT', 'USDT']

export default function DotMenu({ user, currency, onCurrencyChange, onToggleLocale, isDark }: DotMenuProps) {
  const [active, setActive] = useState(false)
  const [showCurrencyChoice, setShowCurrencyChoice] = useState(false)
  const { toggleTheme } = useTheme()
  const { itemsCount } = useCartStore()
  const { count: favoritesCount } = useFavoritesStore()
  const { t } = useTranslation('common')
  const router = useRouter()
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (active) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
      setShowCurrencyChoice(false)
    }
  }, [active])

  const menuItems = [
    {
      i: 0, x: -1, y: -0.8,
      icon: isDark ? (
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 0 1 11.21 3 7 7 0 1 0 21 12.79Z" /></svg>
      ) : (
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2m10-10h-2M4 12H2m15.536-7.536-1.414 1.414M7.879 16.121 6.465 17.535m12.071 0-1.414-1.414M7.879 7.879 6.465 6.465" /></svg>
      ),
      onClick: () => toggleTheme(),
      title: t('theme_dark_title')
    },
    {
      i: 1, x: 0, y: -0.8,
      icon: <span className="text-sm font-bold">{router.locale?.toUpperCase()}</span>,
      onClick: () => onToggleLocale(),
      title: t('language')
    },
    {
      i: 2, x: 1, y: -0.8,
      icon: <span className="text-xs font-bold leading-none">{currency}</span>,
      onClick: () => setShowCurrencyChoice(!showCurrencyChoice),
      title: t('currency')
    },
    {
      i: 3, x: -1, y: 0.8,
      icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>,
      href: '/favorites',
      badge: favoritesCount,
      title: t('menu_favorites')
    },
    {
      i: 4, x: 0, y: 0.8,
      icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>,
      href: '/profile',
      title: t('header_profile')
    },
    {
      i: 5, x: 1, y: 0.8,
      icon: <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M6 6h15l-1.5 9h-12z" /><path strokeLinecap="round" strokeLinejoin="round" d="M6 6l-1-3H3" /><circle cx="9" cy="20" r="1" /><circle cx="18" cy="20" r="1" /></svg>,
      href: '/cart',
      badge: itemsCount,
      title: t('menu_cart')
    }
  ]

  const closeMenu = () => {
    setActive(false)
    setShowCurrencyChoice(false)
  }

  return (
    <div className="relative w-[44px] h-[44px]">
      {/* Backdrop */}
      <AnimatePresence>
        {active && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed top-0 left-0 w-[100vw] h-[100vh] bg-black/60 backdrop-blur-md z-[990]"
            onClick={closeMenu}
          />
        )}
      </AnimatePresence>

      <div
        ref={menuRef}
        className={`${styles.navigation} ${active ? styles.active : ''}`}
        onClick={() => setActive(!active)}
        style={{
          // Fixed positioning works relative to the nearest filter (Header's backdrop-blur)
          // Therefore, % values take Header's size. Let's use vh to take viewport size!
          position: active ? 'fixed' : 'relative',
          top: active ? '15vh' : '0',
          left: active ? '50vw' : '0',
          transform: active ? 'translate(-50%, -50%)' : 'none',
          zIndex: 1000
        }}
      >
        <div className={styles.closeBar}></div>
        <div className={styles.closeBar}></div>

        {menuItems.map((item) => {
          const content = (
            <span
              key={item.i}
              style={{
                '--i': item.i,
                '--x': item.x,
                '--y': item.y
              } as any}
              onClick={(e) => {
                if (active) {
                  e.stopPropagation()
                  if (item.onClick) {
                    item.onClick()
                  } else if (item.href) {
                    closeMenu()
                    // If we navigate using standard router, setActive(false) is good
                    router.push(item.href)
                  }
                }
              }}
            >
              <div className={`${styles.icon} flex items-center justify-center`}>
                {item.icon}
              </div>
              {active && item.badge !== undefined && item.badge > 0 && (
                <span className={styles.badge}>{item.badge > 99 ? '99+' : item.badge}</span>
              )}
            </span>
          )

          return content
        })}

        {/* Currency choice sub-menu */}
        <AnimatePresence>
          {showCurrencyChoice && active && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              className="absolute z-[110] bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-2xl p-3 grid grid-cols-3 gap-2 w-[180px]"
              style={{ top: 'calc(100% + 15px)', left: '50%', transform: 'translateX(-50%)' }}
              onClick={(e) => e.stopPropagation()}
            >
              {currencyOptions.map((code) => (
                <button
                  key={code}
                  onClick={() => { onCurrencyChange(code); closeMenu() }}
                  className={`px-2 py-1.5 text-xs font-bold rounded transition-colors ${currency === code ? 'bg-[var(--accent)] text-white' : 'hover:bg-[var(--accent-soft)]'}`}
                >
                  {code}
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
