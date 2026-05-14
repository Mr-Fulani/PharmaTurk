import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import type { FooterSettingsData } from '../lib/footerSettings'

type ContactItem = {
  key: string
  label: string
  color: string
  icon: React.ReactNode
  href?: string
}

const RADIUS = 58
const WIDGET_SIZE = 76
const ACTION_SIZE = 42
const EDGE_PADDING = 12
const DRAG_THRESHOLD = 6
const POSITION_STORAGE_KEY = 'contact-widget-position'

type WidgetPosition = {
  x: number
  y: number
}

type DragState = {
  active: boolean
  moved: boolean
  pointerId: number | null
  startX: number
  startY: number
  originX: number
  originY: number
}

const SSR_DEFAULT_POSITION: WidgetPosition = {
  x: WIDGET_SIZE / 2,
  y: WIDGET_SIZE / 2,
}

function getInitialSettings(initialSettings?: Partial<FooterSettingsData>): FooterSettingsData {
  return {
    phone: initialSettings?.phone || '',
    email: initialSettings?.email || '',
    location: initialSettings?.location || '',
    telegram_url: initialSettings?.telegram_url || '',
    whatsapp_url: initialSettings?.whatsapp_url || '',
    vk_url: initialSettings?.vk_url || '',
    instagram_url: initialSettings?.instagram_url || '',
    crypto_payment_text: initialSettings?.crypto_payment_text || '',
  }
}

function toWhatsAppUrl(rawUrl?: string, rawPhone?: string) {
  const directUrl = (rawUrl || '').trim()
  if (directUrl) return directUrl
  const digits = (rawPhone || '').replace(/\D/g, '')
  return digits ? `https://wa.me/${digits}` : ''
}

function toPhoneUrl(rawPhone?: string) {
  const phone = (rawPhone || '').trim()
  return phone ? `tel:${phone}` : ''
}

function toMailUrl(rawEmail?: string) {
  const email = (rawEmail || '').trim()
  return email ? `mailto:${email}` : ''
}

function getPos(i: number, count: number) {
  const angleDeg = -135 + (270 / (count - 1 || 1)) * i
  const rad = (angleDeg * Math.PI) / 180
  return {
    x: Math.round(Math.cos(rad) * RADIUS),
    y: Math.round(Math.sin(rad) * RADIUS),
  }
}

function getSafeMargin() {
  return Math.max(WIDGET_SIZE / 2, RADIUS + ACTION_SIZE / 2 + EDGE_PADDING)
}

function clampPosition(x: number, y: number) {
  if (typeof window === 'undefined') {
    return { x, y }
  }

  const safeMargin = getSafeMargin()

  return {
    x: Math.min(Math.max(x, safeMargin), window.innerWidth - safeMargin),
    y: Math.min(Math.max(y, safeMargin), window.innerHeight - safeMargin),
  }
}

function getDefaultPosition() {
  if (typeof window === 'undefined') {
    return {
      x: WIDGET_SIZE / 2,
      y: WIDGET_SIZE / 2,
    }
  }

  const safeMargin = getSafeMargin()

  return {
    x: window.innerWidth - safeMargin,
    y: window.innerHeight - safeMargin,
  }
}

function loadSavedPosition() {
  if (typeof window === 'undefined') return null

  try {
    const rawValue = window.localStorage.getItem(POSITION_STORAGE_KEY)
    if (!rawValue) return null

    const parsed = JSON.parse(rawValue) as Partial<WidgetPosition>
    if (typeof parsed.x !== 'number' || typeof parsed.y !== 'number') {
      return null
    }

    return clampPosition(parsed.x, parsed.y)
  } catch {
    return null
  }
}

export default function ContactWidget({ initialSettings: _initialSettings }: { initialSettings?: unknown }) {
  const { t } = useTranslation('common')
  const [open, setOpen] = useState(false)
  const [isMounted, setIsMounted] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const dragStateRef = useRef<DragState>({
    active: false,
    moved: false,
    pointerId: null,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  })
  const suppressClickRef = useRef(false)
  const [settings, setSettings] = useState<FooterSettingsData>(getInitialSettings(_initialSettings as Partial<FooterSettingsData> | undefined))
  const [position, setPosition] = useState<WidgetPosition>(SSR_DEFAULT_POSITION)

  useEffect(() => {
    setSettings((prev) => ({
      ...prev,
      ...getInitialSettings(_initialSettings as Partial<FooterSettingsData> | undefined),
    }))
  }, [_initialSettings])

  useEffect(() => {
    const initial = _initialSettings as Partial<FooterSettingsData> | undefined
    const hasPrimaryContact = initial?.phone || initial?.email || initial?.telegram_url || initial?.whatsapp_url || initial?.vk_url
    if (hasPrimaryContact) return

    let isCancelled = false

    api.get('/settings/footer-settings')
      .then((response) => {
        if (isCancelled) return
        const data = response.data || {}
        setSettings((prev) => ({
          ...prev,
          phone: data.phone || prev.phone || '',
          email: data.email || prev.email || '',
          location: data.location || prev.location || '',
          telegram_url: data.telegram_url || prev.telegram_url || '',
          whatsapp_url: data.whatsapp_url || prev.whatsapp_url || '',
          vk_url: data.vk_url || prev.vk_url || '',
          instagram_url: data.instagram_url || prev.instagram_url || '',
          crypto_payment_text: data.crypto_payment_text || prev.crypto_payment_text || '',
        }))
      })
      .catch(() => undefined)

    return () => {
      isCancelled = true
    }
  }, [_initialSettings])

  useEffect(() => {
    if (typeof window === 'undefined') return

    const savedPosition = loadSavedPosition()
    setPosition(savedPosition || getDefaultPosition())
    setIsMounted(true)
  }, [])

  useEffect(() => {
    if (!isMounted || typeof window === 'undefined') return

    window.localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(position))
  }, [isMounted, position])

  useEffect(() => {
    if (typeof window === 'undefined') return

    const handleResize = () => {
      setPosition((prev) => clampPosition(prev.x, prev.y))
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    if (!open) return

    const handler = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  useEffect(() => {
    if (typeof window === 'undefined') return

    const handlePointerMove = (event: PointerEvent) => {
      const dragState = dragStateRef.current
      if (!dragState.active || dragState.pointerId !== event.pointerId) return

      const deltaX = event.clientX - dragState.startX
      const deltaY = event.clientY - dragState.startY

      if (!dragState.moved && Math.hypot(deltaX, deltaY) >= DRAG_THRESHOLD) {
        dragState.moved = true
        suppressClickRef.current = true
        setIsDragging(true)
        setOpen(false)
      }

      if (!dragState.moved) return

      setPosition(clampPosition(dragState.originX + deltaX, dragState.originY + deltaY))
    }

    const stopDragging = (pointerId?: number) => {
      const dragState = dragStateRef.current
      if (!dragState.active) return
      if (typeof pointerId === 'number' && dragState.pointerId !== pointerId) return

      dragState.active = false
      dragState.pointerId = null
      setIsDragging(false)
    }

    const handlePointerUp = (event: PointerEvent) => {
      stopDragging(event.pointerId)
    }

    const handlePointerCancel = (event: PointerEvent) => {
      stopDragging(event.pointerId)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
    window.addEventListener('pointercancel', handlePointerCancel)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
      window.removeEventListener('pointercancel', handlePointerCancel)
    }
  }, [])

  const items: ContactItem[] = [
    { key: 'telegram', label: 'Telegram', color: '#0088cc', icon: <TelegramIcon />, href: settings.telegram_url || '' },
    { key: 'whatsapp', label: 'WhatsApp', color: '#25d366', icon: <WhatsAppIcon />, href: toWhatsAppUrl(settings.whatsapp_url, settings.phone) },
    { key: 'vk', label: 'VK', color: '#4C75A3', icon: <VKIcon />, href: settings.vk_url || '' },
    { key: 'email', label: 'Email', color: '#7c3aed', icon: <MailIcon />, href: toMailUrl(settings.email) },
    { key: 'phone', label: 'Phone', color: '#f59e0b', icon: <PhoneIcon />, href: toPhoneUrl(settings.phone) },
  ].filter((item) => Boolean(item.href))

  const count = items.length

  const handlePointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    dragStateRef.current = {
      active: true,
      moved: false,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: position.x,
      originY: position.y,
    }
  }

  const handleToggle = () => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false
      return
    }

    setOpen((prev) => !prev)
  }

  return (
    <>
      <style>{`
        .cw-item {
          position: absolute;
          top: 50%;
          left: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          pointer-events: none;
          opacity: 0;
          transform: translate(-50%, -50%) scale(0);
          transition:
            opacity 0.25s ease,
            transform 0.35s cubic-bezier(.4,2,.4,.85);
          z-index: 10;
        }
        .cw-item.cw-open {
          opacity: 1;
          transform: var(--cw-pos);
          pointer-events: auto;
        }
        .cw-btn {
          width: 42px;
          height: 42px;
          border-radius: 9999px;
          background: #fff;
          border: none;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: default;
          box-shadow: 0 3px 8px rgba(0,0,0,0.16);
          transition: transform 0.2s ease, box-shadow 0.2s ease;
          color: var(--cw-clr);
          flex-shrink: 0;
        }
        .cw-media {
          pointer-events: none;
          user-select: none;
          -webkit-user-drag: none;
        }
        .cw-btn:hover {
          transform: scale(1.12);
          box-shadow: 0 0 0 2.5px var(--cw-clr), 0 4px 14px rgba(0,0,0,0.18);
        }
        .cw-btn:active {
          transform: scale(0.94);
        }
        .cw-shell {
          animation: cw-heartbeat 2.8s ease-in-out infinite;
          transform-origin: center;
        }
        .cw-shell.cw-active {
          animation: none;
        }
        @keyframes cw-heartbeat {
          0% {
            transform: scale(1);
          }
          8% {
            transform: scale(1.03);
          }
          14% {
            transform: scale(0.99);
          }
          22% {
            transform: scale(1.075);
          }
          30% {
            transform: scale(1);
          }
          100% {
            transform: scale(1);
          }
        }
      `}</style>

      <div
        ref={containerRef}
        className="fixed z-[90]"
        style={{
          width: WIDGET_SIZE,
          height: WIDGET_SIZE,
          left: position.x - WIDGET_SIZE / 2,
          top: position.y - WIDGET_SIZE / 2,
          visibility: isMounted ? 'visible' : 'hidden',
          transform: 'translate3d(0, 0, 0)',
        }}
      >
        {items.map((item, idx) => {
          const { x, y } = getPos(idx, count)
          const posVar = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`
          return (
            <div
              key={item.key}
              className={`cw-item${open ? ' cw-open' : ''}`}
              style={{
                ['--cw-pos' as string]: posVar,
                transitionDelay: open
                  ? `${idx * 0.045}s`
                  : `${(count - 1 - idx) * 0.03}s`,
              } as React.CSSProperties}
            >
              <a
                className="cw-btn"
                style={{ ['--cw-clr' as string]: item.color } as React.CSSProperties}
                aria-label={item.label}
                title={item.label}
                href={item.href}
                target={item.href?.startsWith('http') ? '_blank' : undefined}
                rel={item.href?.startsWith('http') ? 'noopener noreferrer' : undefined}
              >
                {item.icon}
              </a>
            </div>
          )
        })}

        <div className={`group relative cw-shell${open || isDragging ? ' cw-active' : ''}`}>
          <div className="absolute -top-2 left-1/2 z-20 -translate-x-1/2 -translate-y-full opacity-0 transition-opacity duration-200 pointer-events-none group-hover:opacity-100">
            <div className="bg-[var(--text-strong)] dark:!bg-[#1f2937] text-[var(--bg)] dark:!text-white dark:border dark:border-gray-600 rounded px-2 py-1 text-xs whitespace-nowrap shadow-lg">
              {t('contact_widget_tooltip', 'Поддержка')}
            </div>
            <div className="absolute top-full left-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rotate-45 bg-[var(--text-strong)] dark:!bg-[#1f2937] dark:border-r dark:border-b dark:border-gray-600" />
          </div>

          <button
            type="button"
            onClick={handleToggle}
            onPointerDown={handlePointerDown}
            aria-expanded={open}
            aria-label={t('contact_widget_tooltip', 'Поддержка')}
            className="relative z-[2] flex h-[76px] w-[76px] items-center justify-center rounded-full border bg-[var(--surface)] p-1 shadow-[0_18px_40px_rgba(15,23,42,0.18)] transition-all duration-300 hover:-translate-y-0.5"
            style={{
              cursor: isDragging ? 'grabbing' : 'grab',
              touchAction: 'none',
              userSelect: 'none',
              WebkitUserSelect: 'none',
              borderColor: open ? 'rgba(0,0,0,0.2)' : 'var(--border)',
              boxShadow: open
                ? '0 0 0 3px rgba(0,0,0,0.08), 0 12px 28px rgba(0,0,0,0.18)'
                : '0 18px 40px rgba(15,23,42,0.18)',
              transform: open ? 'rotate(360deg)' : 'rotate(0deg)',
            }}
            >
            <span className="cw-media absolute inset-0 rounded-full bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.38),transparent_58%)] opacity-70" />
            <span className="cw-media relative block h-[66px] w-[66px] overflow-hidden rounded-full border border-[rgba(67,113,247,0.18)]">
              <img
                src="/support-contact-logo.jpg"
                alt={t('contact_widget_tooltip', 'Поддержка')}
                className="h-full w-full object-cover object-top"
                loading="lazy"
                decoding="async"
                draggable={false}
              />
            </span>
          </button>
        </div>
      </div>
    </>
  )
}

function TelegramIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M21 4 3.8 10.65c-.8.32-.78 1.47.03 1.75l4.4 1.55 1.7 5.08c.25.76 1.24.85 1.62.15l2.46-4.57 4.93 3.91c.58.46 1.43.15 1.58-.58L22 5.15C22.14 4.46 21.56 3.79 21 4Z" />
    </svg>
  )
}

function WhatsAppIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884" />
    </svg>
  )
}

function VKIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M15.684 0H8.316C1.592 0 0 1.592 0 8.316v7.368C0 22.408 1.592 24 8.316 24h7.368C22.408 24 24 22.408 24 15.684V8.316C24 1.592 22.408 0 15.684 0zm3.692 17.123h-1.744c-.66 0-.864-.525-2.05-1.727-1.033-1-1.49-1.135-1.744-1.135-.356 0-.458.102-.458.593v1.575c0 .424-.135.678-1.253.678-1.845 0-3.896-1.118-5.335-3.202C4.624 10.857 4.03 8.57 4.03 8.096c0-.254.102-.491.593-.491h1.744c.44 0 .61.203.78.677.864 2.49 2.303 4.675 2.896 4.675.22 0 .322-.102.322-.66V9.721c-.068-1.186-.695-1.287-.695-1.71 0-.204.17-.407.44-.407h2.744c.373 0 .508.203.508.643v3.473c0 .372.17.508.271.508.22 0 .407-.136.813-.542 1.254-1.406 2.151-3.574 2.151-3.574.119-.254.322-.491.762-.491h1.744c.525 0 .643.27.525.643-.22 1.017-2.354 4.031-2.354 4.031-.186.305-.254.44 0 .78.186.254.796.779 1.203 1.253.745.847 1.32 1.558 1.473 2.05.17.49-.085.745-.576.745z"/>
    </svg>
  )
}

function MailIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 6h16v12H4z" />
      <path d="m4 7 8 6 8-6" />
    </svg>
  )
}

function PhoneIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.86 19.86 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.86 19.86 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.86.33 1.7.62 2.5a2 2 0 0 1-.45 2.11L8 9a16 16 0 0 0 7 7l.67-1.28a2 2 0 0 1 2.11-.45c.8.29 1.64.5 2.5.62A2 2 0 0 1 22 16.92z" />
    </svg>
  )
}
