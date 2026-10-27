import { useEffect, useState, type ReactNode, type RefObject } from 'react'
import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import { isActionBlockOffscreen } from '../lib/stickyBuyBar'

const BAR_HEIGHT = 72

interface MobileStickyBuyBarProps {
  /** Основной блок с кнопкой «В заявку»: пока он на экране, панель не нужна */
  actionRef: RefObject<HTMLElement | null>
  /** Блок выбора размера — к нему прокручивает кнопка «Выберите размер» */
  sizeRef?: RefObject<HTMLElement | null>
  mode: 'add' | 'choose_size' | 'go_to_cart' | 'hidden'
  price: string
  /** Кнопка «В заявку» с теми же параметрами, что в основном блоке */
  addButton: ReactNode
}

/** Липкая панель «цена + В заявку» внизу карточки товара, только на телефоне (< md). */
export default function MobileStickyBuyBar({ actionRef, sizeRef, mode, price, addButton }: MobileStickyBuyBarProps) {
  const { t } = useTranslation('common')
  const [offscreen, setOffscreen] = useState(false)
  const visible = mode !== 'hidden' && offscreen

  useEffect(() => {
    if (mode === 'hidden') return
    let frame = 0
    const update = () => {
      frame = 0
      const rect = actionRef.current?.getBoundingClientRect() ?? null
      setOffscreen(isActionBlockOffscreen(rect, window.innerHeight, BAR_HEIGHT))
    }
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    return () => {
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [actionRef, mode])

  // Плавающий виджет связи поднимается над панелью (globals.css, html[data-sticky-buy-bar])
  useEffect(() => {
    const root = document.documentElement
    if (visible) root.dataset.stickyBuyBar = 'on'
    else delete root.dataset.stickyBuyBar
    return () => { delete root.dataset.stickyBuyBar }
  }, [visible])

  if (mode === 'hidden') return null

  const scrollTo = (ref?: RefObject<HTMLElement | null>) => {
    ;(ref?.current || actionRef.current)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <div
      className={`fixed inset-x-0 bottom-0 z-[80] border-t border-[var(--border)] bg-[var(--bg)] px-4 pt-3 shadow-[0_-6px_20px_rgba(0,0,0,0.08)] transition-transform duration-200 md:hidden ${
        visible ? 'translate-y-0' : 'pointer-events-none translate-y-full'
      }`}
      style={{ paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom))' }}
      aria-hidden={!visible}
    >
      {/* Скрытая панель без содержимого: кнопки не попадают в фокус с клавиатуры */}
      {visible && <div className="flex items-center gap-3">
        <span className="min-w-0 shrink text-lg font-extrabold leading-tight text-[var(--text-strong)]">{price}</span>
        <div className="ml-auto flex min-w-0 flex-1 justify-end [&>button]:w-full">
          {mode === 'add' && addButton}
          {mode === 'choose_size' && (
            <button
              type="button"
              onClick={() => scrollTo(sizeRef)}
              className="min-h-[46px] w-full rounded-[0.6rem] bg-[var(--accent)] px-4 text-sm font-semibold text-white"
            >
              {t('select_size', 'Выберите размер')}
            </button>
          )}
          {mode === 'go_to_cart' && (
            <Link
              href="/cart"
              className="flex min-h-[46px] w-full items-center justify-center rounded-[0.6rem] bg-[var(--accent)] px-4 text-sm font-semibold text-white"
            >
              {t('go_to_request', 'Оформить заявку')} →
            </Link>
          )}
        </div>
      </div>}
    </div>
  )
}
