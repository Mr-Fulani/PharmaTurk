import { useState } from 'react'
import { useTranslation } from 'next-i18next'
import { getSiteOrigin, buildProductUrl } from '../lib/urls'

interface ShareButtonProps {
  /** Заголовок для шаринга (название товара) */
  title: string
  /** Описание для шаринга */
  description?: string
  /** URL картинки-превью */
  imageUrl?: string | null
  /** slug товара */
  slug: string
  /** тип товара для построения URL */
  productType?: string
  /** Полный URL страницы (если уже известен, иначе строится автоматически) */
  pageUrl?: string
  /** Режим угловой иконки — стеклянный стиль без текста */
  cornerIcon?: boolean
  className?: string
}

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
  const [copied, setCopied] = useState(false)
  const [showMenu, setShowMenu] = useState(false)

  const getUrl = (): string => {
    if (pageUrl) return pageUrl
    const origin = getSiteOrigin()
    // По-умолчанию локаль 'ru', так что для 'en' добавляем префикс '/en'
    const defaultLocale = (i18n.options as any)?.defaultLocale || 'ru'
    const locale = i18n.language && i18n.language !== defaultLocale ? `/${i18n.language}` : ''
    return `${origin}${locale}${buildProductUrl(productType, slug)}`
  }

  // Мы полагаемся на OG-теги (Link Preview) для показа изображения и длинного описания в мессенджерах.
  // Передаем только заголовок, чтобы избежать дублирования текста и сделать сообщение "одним блоком".
  const shareText = title

  const handleShare = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()

    const url = getUrl()

    // Пробуем нативный Web Share API
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({
          title,
          text: shareText,
          url,
        })
        return
      } catch {
        // пользователь отменил — ничего не делаем
        return
      }
    }

    // Fallback: показываем мини-меню с вариантами шаринга
    setShowMenu((prev) => !prev)
  }

  const copyToClipboard = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const url = getUrl()
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setShowMenu(false)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // старый браузер
      const ta = document.createElement('textarea')
      ta.value = url
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setCopied(true)
      setShowMenu(false)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const shareViaWhatsApp = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const url = getUrl()
    const text = encodeURIComponent(`${shareText}\n${url}`)
    window.open(`https://wa.me/?text=${text}`, '_blank', 'noopener')
    setShowMenu(false)
  }

  const shareViaTelegram = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const url = getUrl()
    const text = encodeURIComponent(shareText)
    window.open(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${text}`, '_blank', 'noopener')
    setShowMenu(false)
  }

  const shareViaVK = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const url = getUrl()
    const params = new URLSearchParams({ url, title })
    if (imageUrl) params.set('image', imageUrl)
    if (description) params.set('description', description)
    window.open(`https://vk.com/share.php?${params.toString()}`, '_blank', 'noopener')
    setShowMenu(false)
  }

  // Иконка "поделиться" (стрелка вверх из квадрата)
  const ShareIcon = ({ size = 18, color = 'currentColor' }: { size?: number; color?: string }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
      <polyline points="16 6 12 2 8 6" />
      <line x1="12" y1="2" x2="12" y2="15" />
    </svg>
  )

  if (cornerIcon) {
    return (
      <div className={`relative ${className}`}>
        {/* Кнопка шаринга */}
        <button
          onClick={handleShare}
          title={t('share', 'Поделиться')}
          aria-label={t('share', 'Поделиться')}
          className="flex items-center justify-center transition-all duration-200"
          style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            background: copied ? 'rgba(34,197,94,0.15)' : 'rgba(255,255,255,0.75)',
            backdropFilter: 'blur(6px)',
            WebkitBackdropFilter: 'blur(6px)',
            border: copied ? '1.5px solid rgba(34,197,94,0.4)' : '1.5px solid rgba(255,255,255,0.6)',
            boxShadow: '0 2px 8px rgba(0,0,0,0.13)',
          }}
        >
          {copied ? (
            // Галочка — ссылка скопирована
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <ShareIcon size={16} color="#6b7280" />
          )}
        </button>

        {/* Выпадающее меню для desktop (когда нет navigator.share) */}
        {showMenu && (
          <>
            {/* Overlay для закрытия */}
            <div
              className="fixed inset-0 z-40"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowMenu(false) }}
            />
            <div
              className="absolute z-50 mt-1 rounded-xl overflow-hidden"
              style={{
                top: '100%',
                right: 0,
                minWidth: 200,
                background: 'rgba(255,255,255,0.97)',
                backdropFilter: 'blur(12px)',
                WebkitBackdropFilter: 'blur(12px)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
                border: '1px solid rgba(0,0,0,0.07)',
              }}
              onClick={(e) => { e.preventDefault(); e.stopPropagation() }}
            >
              <div style={{ padding: '6px 0' }}>
                {/* WhatsApp */}
                <button
                  onClick={shareViaWhatsApp}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-green-50 transition-colors text-left"
                >
                  <span style={{ color: '#25D366' }}>
                    <svg width={18} height={18} viewBox="0 0 24 24" fill="currentColor">
                      <path d="M17.472 14.382c-.022-.014-.503-.245-.582-.273-.08-.029-.137-.043-.194.043-.057.087-.222.28-.272.336-.05.056-.098.064-.188.019-.089-.044-.378-.14-.72-.445-.265-.236-.445-.53-.496-.618-.05-.088-.005-.136.039-.181.039-.039.088-.103.132-.154.044-.052.059-.088.088-.147.03-.059.015-.11-.008-.155-.022-.046-.194-.467-.266-.64-.07-.168-.14-.146-.194-.148-.05-.002-.108-.002-.165-.002-.057 0-.15-.021-.229.063-.079.084-.301.294-.301.718 0 .423.308.832.351.89.043.059.605.924 1.467 1.297.205.088.365.14.49.18.207.065.395.056.544.034.166-.024.503-.205.574-.403.072-.198.072-.367.05-.403-.022-.036-.081-.057-.17-.101zm-5.469 4.383c-1.206 0-2.388-.325-3.424-.94l-.246-.146-2.544.668.68-2.48-.16-.254a7.926 7.926 0 0 1-1.213-4.252c0-4.387 3.57-7.958 7.958-7.958 2.126 0 4.125.827 5.628 2.33s2.33 3.502 2.33 5.628c0 4.389-3.572 7.96-7.958 7.96zm7.957-17.758C17.935 1.006 15.011 0 12.003 0 5.432 0 .08 5.352.08 11.924c0 2.099.549 4.148 1.595 5.96L0 24l6.324-1.658c1.745.952 3.716 1.455 5.672 1.455 6.568 0 11.921-5.352 11.921-11.924 0-3.184-1.24-6.179-3.49-8.428z" />
                    </svg>
                  </span>
                  WhatsApp
                </button>
                {/* Telegram */}
                <button
                  onClick={shareViaTelegram}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-blue-50 transition-colors text-left"
                >
                  <span style={{ color: '#0088cc' }}>
                    <svg width={18} height={18} viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1 .22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-1.93 1.25-5.45 3.63-.51.35-.98.53-1.39.52-.46-.01-1.33-.26-1.98-.48-.8-.27-1.43-.42-1.38-.89.03-.25.38-.51 1.07-.78 4.21-1.83 7.01-3.04 8.39-3.63 3.96-1.67 4.79-1.96 5.33-1.97.12 0 .38.03.55.17.14.12.18.28.2.4.02.1.03.29.02.4z" />
                    </svg>
                  </span>
                  Telegram
                </button>
                {/* VK */}
                <button
                  onClick={shareViaVK}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-indigo-50 transition-colors text-left"
                >
                  <span style={{ color: '#4C75A3' }}>
                    <svg width={18} height={18} viewBox="0 0 24 24" fill="currentColor">
                      <path d="M15.684 0H8.316C1.592 0 0 1.592 0 8.316v7.368C0 22.408 1.592 24 8.316 24h7.368C22.408 24 24 22.408 24 15.684V8.316C24 1.592 22.408 0 15.684 0zm3.692 17.123h-1.744c-.66 0-.864-.525-2.05-1.727-1.033-1-1.49-1.135-1.744-1.135-.356 0-.458.102-.458.593v1.575c0 .424-.135.678-1.253.678-1.845 0-3.896-1.118-5.335-3.202C4.624 10.857 4.03 8.57 4.03 8.096c0-.254.102-.491.593-.491h1.744c.44 0 .61.203.78.677.864 2.49 2.303 4.675 2.896 4.675.22 0 .322-.102.322-.66V9.721c-.068-1.186-.695-1.287-.695-1.71 0-.204.17-.407.44-.407h2.744c.373 0 .508.203.508.643v3.473c0 .372.17.508.271.508.22 0 .407-.136.813-.542 1.254-1.406 2.151-3.574 2.151-3.574.119-.254.322-.491.762-.491h1.744c.525 0 .643.27.525.643-.22 1.017-2.354 4.031-2.354 4.031-.186.305-.254.44 0 .78.186.254.796.779 1.203 1.253.745.847 1.32 1.558 1.473 2.05.17.49-.085.745-.576.745z" />
                    </svg>
                  </span>
                  VKontakte
                </button>
                {/* Разделитель */}
                <div style={{ height: 1, background: 'rgba(0,0,0,0.06)', margin: '4px 12px' }} />
                {/* Копировать ссылку */}
                <button
                  onClick={copyToClipboard}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors text-left"
                >
                  <span style={{ color: '#6b7280' }}>
                    <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  </span>
                  {t('copy_link', 'Скопировать ссылку')}
                </button>
              </div>
            </div>
          </>
        )}

        {/* Toast: ссылка скопирована */}
        {copied && (
          <div
            className="absolute z-50 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium text-white"
            style={{
              bottom: 'calc(100% + 8px)',
              right: 0,
              background: 'rgba(17,24,39,0.92)',
              boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            }}
          >
            {t('link_copied', 'Ссылка скопирована!')}
          </div>
        )}
      </div>
    )
  }

  // Обычный режим (не cornerIcon) — не используется сейчас, но оставим для гибкости
  return (
    <button
      onClick={handleShare}
      className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 transition-all duration-200 ${className}`}
    >
      <ShareIcon size={16} />
      <span>{t('share', 'Поделиться')}</span>
    </button>
  )
}
