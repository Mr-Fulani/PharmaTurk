import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'next-i18next'
import { getSiteOrigin, buildProductUrl } from '../lib/urls'

interface ShareButtonProps {
  title: string
  description?: string
  imageUrl?: string | null
  slug: string
  productType?: string
  pageUrl?: string
  cornerIcon?: boolean
  className?: string
}

// ─── SVG Icons ──────────────────────────────────────────────────────────────

const FacebookIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.97h-1.513c-1.491 0-1.956.93-1.956 1.886v2.267h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/>
  </svg>
)

const WhatsAppIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z"/>
  </svg>
)

const XTwitterIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.737-8.835L1.254 2.25H8.08l4.253 5.622 5.911-5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
  </svg>
)

const CopyIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
  </svg>
)

const CheckIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
)

const LinkedInIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
  </svg>
)

const InstagramIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"/>
  </svg>
)

const TelegramIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1 .22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-1.93 1.25-5.45 3.63-.51.35-.98.53-1.39.52-.46-.01-1.33-.26-1.98-.48-.8-.27-1.43-.42-1.38-.89.03-.25.38-.51 1.07-.78 4.21-1.83 7.01-3.04 8.39-3.63 3.96-1.67 4.79-1.96 5.33-1.97.12 0 .38.03.55.17.14.12.18.28.2.4.02.1.03.29.02.4z"/>
  </svg>
)

const GitHubIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
  </svg>
)

const YouTubeIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
  </svg>
)

const ShareMainIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>
    <polyline points="16 6 12 2 8 6"/>
    <line x1="12" y1="2" x2="12" y2="15"/>
  </svg>
)

// ─── Types ───────────────────────────────────────────────────────────────────

interface ShareItem {
  key: string
  label: string
  icon: React.ReactNode
  color: string
  onClick: (e: React.MouseEvent) => void
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function ShareButton({
  title,
  description,
  imageUrl,
  slug,
  productType = 'medicines',
  pageUrl,
  cornerIcon = false,
  className = '',
}: ShareButtonProps) {
  const { t, i18n } = useTranslation('common')
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setIsMobile(
      typeof navigator !== 'undefined' &&
      /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent)
    )
  }, [])

  // Закрываем при клике вне компонента
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const getUrl = useCallback((): string => {
    if (pageUrl) return pageUrl
    const origin = getSiteOrigin()
    const defaultLocale = (i18n.options as any)?.defaultLocale || 'ru'
    const locale = i18n.language && i18n.language !== defaultLocale ? `/${i18n.language}` : ''
    return `${origin}${locale}${buildProductUrl(productType, slug)}`
  }, [pageUrl, i18n, productType, slug])

  const handleToggle = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (isMobile && typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({ title, url: getUrl() })
      } catch { /* cancelled */ }
      return
    }
    setOpen(prev => !prev)
  }

  // ─── Share actions ──────────────────────────────────────────────────────

  const shareViaFacebook = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(getUrl())}`, '_blank', 'noopener,noreferrer,width=600,height=500')
    setOpen(false)
  }, [getUrl])

  const shareViaWhatsApp = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    window.open(`https://wa.me/?text=${encodeURIComponent(getUrl())}`, '_blank', 'noopener,noreferrer')
    setOpen(false)
  }, [getUrl])

  const shareViaTwitter = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    window.open(`https://twitter.com/intent/tweet?url=${encodeURIComponent(getUrl())}&text=${encodeURIComponent(title)}`, '_blank', 'noopener,noreferrer,width=600,height=500')
    setOpen(false)
  }, [getUrl, title])

  const copyToClipboard = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    const url = getUrl()
    try {
      await navigator.clipboard.writeText(url)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = url
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopied(true)
    setOpen(false)
    setTimeout(() => setCopied(false), 2000)
  }, [getUrl])

  const shareViaLinkedIn = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    window.open(`https://www.linkedin.com/shareArticle?mini=true&url=${encodeURIComponent(getUrl())}&title=${encodeURIComponent(title)}`, '_blank', 'noopener,noreferrer,width=600,height=500')
    setOpen(false)
  }, [getUrl, title])

  const shareViaInstagram = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    // Instagram не имеет прямого web share URL — копируем ссылку
    const url = getUrl()
    try { navigator.clipboard.writeText(url) } catch { /* ignore */ }
    setCopied(true)
    setOpen(false)
    setTimeout(() => setCopied(false), 2000)
  }, [getUrl])

  const shareViaGitHub = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    // GitHub нет прямого share — открываем telegram как fallback или копируем
    const url = getUrl()
    window.open(`https://t.me/share/url?url=${encodeURIComponent(url)}`, '_blank', 'noopener,noreferrer,width=600,height=500')
    setOpen(false)
  }, [getUrl])

  const shareViaYouTube = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    window.open(`https://www.youtube.com/share?url=${encodeURIComponent(getUrl())}`, '_blank', 'noopener,noreferrer')
    setOpen(false)
  }, [getUrl])

  // ─── 8 items — full circle like the example ─────────────────────────────
  // Порядок: Facebook(0), WhatsApp(1), X(2), Copy/Reddit(3), LinkedIn(4), Instagram(5), GitHub(6), YouTube(7)
  const items: ShareItem[] = [
    { key: 'facebook',  label: 'Facebook',  icon: <FacebookIcon />,  color: '#1877f2', onClick: shareViaFacebook },
    { key: 'whatsapp',  label: 'WhatsApp',  icon: <WhatsAppIcon />,  color: '#25d366', onClick: shareViaWhatsApp },
    { key: 'twitter',   label: 'X (Twitter)', icon: <XTwitterIcon />, color: '#000000', onClick: shareViaTwitter },
    { key: 'copy',      label: t('copy_link', 'Копировать'), icon: copied ? <CheckIcon /> : <CopyIcon />, color: '#ff5733', onClick: copyToClipboard },
    { key: 'linkedin',  label: 'LinkedIn',  icon: <LinkedInIcon />,  color: '#0a66c2', onClick: shareViaLinkedIn },
    { key: 'instagram', label: 'Instagram', icon: <InstagramIcon />, color: '#c32aa3', onClick: shareViaInstagram },
    { key: 'telegram2', label: 'Telegram',  icon: <TelegramIcon />,  color: '#0088cc', onClick: shareViaGitHub },
    { key: 'youtube',   label: 'YouTube',   icon: <YouTubeIcon />,   color: '#ff0000', onClick: shareViaYouTube },
  ]

  // ─── Radial positioning — full 360° circle (8 items × 45°) ──────────────
  // Угол 0° = правая сторона, вращение по часовой стрелке.
  // Начинаем с -90° (вверх), чтобы первый элемент был сверху.
  const COUNT = items.length
  const RADIUS = 62 // px

  const getPos = (i: number) => {
    const angleDeg = -90 + (360 / COUNT) * i
    const rad = (angleDeg * Math.PI) / 180
    return {
      x: Math.round(Math.cos(rad) * RADIUS),
      y: Math.round(Math.sin(rad) * RADIUS),
    }
  }

  // ─── Render ──────────────────────────────────────────────────────────────

  const triggerBtn = (
    <button
      onClick={handleToggle}
      title={t('share', 'Поделиться')}
      aria-label={t('share', 'Поделиться')}
      style={{
        position: 'relative',
        zIndex: 2,
        width: 38,
        height: 38,
        borderRadius: '50%',
        background: open ? '#fff' : 'rgba(255,255,255,0.78)',
        backdropFilter: 'blur(6px)',
        WebkitBackdropFilter: 'blur(6px)',
        border: open ? '1.5px solid rgba(0,0,0,0.2)' : '1.5px solid rgba(255,255,255,0.65)',
        boxShadow: open
          ? '0 0 0 3px rgba(0,0,0,0.08), 0 6px 18px rgba(0,0,0,0.18)'
          : '0 3px 8px rgba(0,0,0,0.14)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'transform 1.25s cubic-bezier(.4,2,.3,.9), box-shadow 0.25s, background 0.25s',
        transform: open ? 'rotate(360deg)' : 'rotate(0deg)',
        color: open ? '#111' : '#6b7280',
        flexShrink: 0,
      }}
    >
      <ShareMainIcon />
    </button>
  )

  if (cornerIcon) {
    return (
      <>
        <style>{`
          .sr-item {
            position: absolute;
            top: 50%;
            left: 50%;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 3px;
            pointer-events: none;
            opacity: 0;
            transform: translate(-50%, -50%) scale(0);
            transition:
              opacity 0.25s ease,
              transform 0.35s cubic-bezier(.4,2,.4,.85);
            z-index: 10;
          }
          .sr-item.sr-open {
            opacity: 1;
            transform: var(--sr-pos);
            pointer-events: auto;
          }
          .sr-btn {
            width: 42px;
            height: 42px;
            border-radius: 50%;
            background: #fff;
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            box-shadow: 0 3px 8px rgba(0,0,0,0.16);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            color: var(--sr-clr);
            flex-shrink: 0;
          }
          .sr-btn:hover {
            transform: scale(1.2);
            box-shadow: 0 0 0 2.5px var(--sr-clr), 0 4px 14px rgba(0,0,0,0.18);
          }
          .sr-btn:active { transform: scale(0.92); }
          .sr-label {
            font-size: 9px;
            font-weight: 700;
            color: #1f2937;
            white-space: nowrap;
            background: rgba(255,255,255,0.93);
            border-radius: 4px;
            padding: 1px 5px;
            line-height: 1.5;
            box-shadow: 0 1px 4px rgba(0,0,0,0.10);
            pointer-events: none;
            letter-spacing: 0.01em;
          }
        `}</style>

        <div
          ref={containerRef}
          className={`relative ${className}`}
          style={{ width: 38, height: 38 }}
        >
          {triggerBtn}

          {items.map((item, idx) => {
            const { x, y } = getPos(idx)
            const posVar = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`
            return (
              <div
                key={item.key}
                className={`sr-item${open ? ' sr-open' : ''}`}
                style={{
                  '--sr-pos': posVar,
                  transitionDelay: open
                    ? `${idx * 0.045}s`
                    : `${(COUNT - 1 - idx) * 0.03}s`,
                } as React.CSSProperties}
              >
                <button
                  className="sr-btn"
                  style={{ '--sr-clr': item.color } as React.CSSProperties}
                  onClick={item.onClick}
                  title={item.label}
                  aria-label={item.label}
                >
                  {item.icon}
                </button>
              </div>
            )
          })}

          {copied && (
            <div style={{
              position: 'absolute',
              bottom: 'calc(100% + 10px)',
              right: 0,
              zIndex: 50,
              whiteSpace: 'nowrap',
              borderRadius: 8,
              padding: '5px 10px',
              fontSize: 11,
              fontWeight: 600,
              color: '#fff',
              background: 'rgba(17,24,39,0.93)',
              boxShadow: '0 4px 12px rgba(0,0,0,0.22)',
              pointerEvents: 'none',
            }}>
              {t('link_copied', 'Ссылка скопирована!')}
            </div>
          )}
        </div>
      </>
    )
  }

  // Обычный режим
  return (
    <button
      onClick={handleToggle}
      className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 transition-all duration-200 ${className}`}
    >
      <ShareMainIcon />
      <span>{t('share', 'Поделиться')}</span>
    </button>
  )
}
