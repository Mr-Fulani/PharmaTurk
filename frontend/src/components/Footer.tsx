import { useState, useEffect } from 'react'
import { useTranslation } from 'next-i18next'
import { useTheme } from '../context/ThemeContext'
import api from '../lib/api'
import Link from 'next/link'

interface FooterSettings {
  phone: string
  email: string
  location: string
  telegram_url: string
  whatsapp_url: string
  vk_url: string
  instagram_url: string
  crypto_payment_text: string
}

export default function Footer({ initialSettings }: { initialSettings?: Partial<FooterSettings> }) {
  const { t, i18n } = useTranslation('common')
  const theme = useTheme()
  const [isMounted, setIsMounted] = useState(false)
  const envSupportEmail = process.env.NEXT_PUBLIC_SUPPORT_EMAIL || ''
  const defaultLocation = t('footer_location', 'Стамбул, Турция')
  const defaultCryptoText = t('footer_crypto_payment', 'Возможна оплата криптовалютой')
  
  // Инициализируем с дефолтными значениями, чтобы избежать проблем при SSR
  const [settings, setSettings] = useState<FooterSettings>({
    phone: initialSettings?.phone || '+90 552 582 14 97',
    email: initialSettings?.email || envSupportEmail,
    location: initialSettings?.location || 'Стамбул, Турция',
    telegram_url: initialSettings?.telegram_url || '',
    whatsapp_url: initialSettings?.whatsapp_url || '',
    vk_url: initialSettings?.vk_url || '',
    instagram_url: initialSettings?.instagram_url || '',
    crypto_payment_text: initialSettings?.crypto_payment_text || 'Возможна оплата криптовалютой'
  })

  useEffect(() => {
    setIsMounted(true)
  }, [])

  useEffect(() => {
    const isNonRu = !i18n.language?.toLowerCase().startsWith('ru')
    
    const resolveValue = (raw: string | undefined, defaultValue: string, defaultKey: string) => {
      const trimmed = (raw || '').trim()
      if (!trimmed) return defaultValue
      // Если значение из базы совпадает с дефолтной русской строкой - используем перевод ключа
      if (isNonRu && trimmed === defaultKey) return defaultValue
      return trimmed
    }

    if (initialSettings) {
      setSettings((prev) => ({
        phone: initialSettings.phone || prev.phone || '+90 552 582 14 97',
        email: initialSettings.email || prev.email || envSupportEmail,
        location: resolveValue(initialSettings.location, defaultLocation, 'Стамбул, Турция'),
        telegram_url: initialSettings.telegram_url || prev.telegram_url || '',
        whatsapp_url: initialSettings.whatsapp_url || prev.whatsapp_url || '',
        vk_url: initialSettings.vk_url || prev.vk_url || '',
        instagram_url: initialSettings.instagram_url || prev.instagram_url || '',
        crypto_payment_text: resolveValue(initialSettings.crypto_payment_text, defaultCryptoText, 'Возможна оплата криптовалютой')
      }))
    }

    if (typeof window !== 'undefined') {
      const hasSocialFromSSR = initialSettings?.telegram_url || initialSettings?.whatsapp_url ||
        initialSettings?.vk_url || initialSettings?.instagram_url
      
      // Даже если есть данные из SSR, мы могли захотеть обновить их (или если SSR не полный)
      // Но по вашей логике мы выходим. Чтобы перевод работал для SSR, мы его применили выше.
      if (hasSocialFromSSR) return

      api.get('/settings/footer-settings')
        .then(response => {
          const data = response.data || {}
          setSettings((prev) => ({
            phone: data.phone || prev.phone || '+90 552 582 14 97',
            email: data.email || prev.email || envSupportEmail,
            location: resolveValue(data.location, defaultLocation, 'Стамбул, Турция'),
            telegram_url: data.telegram_url || prev.telegram_url || '',
            whatsapp_url: data.whatsapp_url || prev.whatsapp_url || '',
            vk_url: data.vk_url || prev.vk_url || '',
            instagram_url: data.instagram_url || prev.instagram_url || '',
            crypto_payment_text: resolveValue(data.crypto_payment_text, defaultCryptoText, 'Возможна оплата криптовалютой')
          }))
        })
        .catch(err => console.error('Error fetching footer settings:', err))
    }
  }, [initialSettings, i18n.language, defaultLocation, defaultCryptoText, envSupportEmail])

  // Используем значения из API или значения по умолчанию
  const phone = settings.phone
  const email = settings.email
  const location = settings.location
  const cryptoText = settings.crypto_payment_text || defaultCryptoText

  return (
    <footer suppressHydrationWarning className="mt-10 border-t border-main shadow-xl transition-colors duration-200 dark:bg-[#0c1628] dark:border-[#1f2a3d] dark:shadow-[0_-10px_40px_rgba(0,0,0,0.55)]" style={{ backgroundColor: 'var(--surface)', borderColor: 'var(--border)' }}>
      <div className="mx-auto max-w-6xl px-3 sm:px-6 py-10 text-sm text-main">
        <div className="grid grid-cols-1 items-start gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <div className="flex items-start justify-center sm:justify-start">
            {/* Логотип/изображение оплат — увеличенный размер и правильное выравнивание */}
            <div className="group relative">
              <img
                src="/footer-payments.png"
                alt={t('footer_payments', 'Способы оплаты')}
                width={160}
                height={112}
                loading="lazy"
                decoding="async"
                className="h-28 w-auto transition-all duration-200 group-hover:scale-105 group-hover:brightness-110"
              />
              <div className="absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none">
                <div className="bg-[var(--text-strong)] dark:!bg-[#1f2937] text-[var(--bg)] dark:!text-white dark:border dark:border-gray-600 text-xs px-2 py-1 rounded whitespace-nowrap shadow-lg">
                  {cryptoText}
                </div>
                <div className="w-2 h-2 bg-[var(--text-strong)] dark:!bg-[#1f2937] dark:border-r dark:border-b dark:border-gray-600 rotate-45 absolute top-full left-1/2 -translate-x-1/2 -translate-y-1/2"></div>
              </div>
            </div>
          </div>
          <div className="text-center sm:text-left">
            <div className="mb-2 text-sm font-medium text-main">{t('footer_contacts')}</div>
            <div className="space-y-2 text-sm text-main/80">
              <a href={`tel:${phone}`} className="group flex items-center justify-center gap-2 transition-all duration-200 hover:-translate-y-0.5 hover:text-red-600 sm:justify-start">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-red-600 transition-all duration-200 group-hover:scale-110 group-hover:text-red-700">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.86 19.86 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.86 19.86 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.86.33 1.7.62 2.5a2 2 0 0 1-.45 2.11L8 9a16 16 0 0 0 7 7l.67-1.28a2 2 0 0 1 2.11-.45c.8.29 1.64.5 2.5.62A2 2 0 0 1 22 16.92z" />
                </svg>
                <span>{phone}</span>
              </a>
              <a href={`mailto:${email}`} className="group flex items-center justify-center gap-2 transition-all duration-200 hover:-translate-y-0.5 hover:text-red-600 sm:justify-start">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-red-600 transition-all duration-200 group-hover:scale-110 group-hover:text-red-700">
                  <path d="M4 4h16v16H4z" />
                  <path d="m22 6-10 7L2 6" />
                </svg>
                <span>{email}</span>
              </a>
              <div className="flex items-center justify-center gap-2 sm:justify-start">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-red-700">
                  <path d="M21 10c0 7-9 12-9 12S3 17 3 10a9 9 0 1 1 18 0Z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                <span>{location}</span>
              </div>
            </div>
          </div>
          <div className="flex flex-col items-center">
            <div>
              <div className="mb-2 text-center text-sm font-medium text-main">{t('footer_social_networks')}</div>
              <div className="flex items-center justify-center gap-3">
                <a
                  href={settings.telegram_url || '#'}
                  target={settings.telegram_url ? '_blank' : undefined}
                  rel={settings.telegram_url ? 'noopener noreferrer' : undefined}
                  className="group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-main bg-surface transition hover:-translate-y-0.5 hover:bg-surface/70 hover:shadow-md"
                  aria-label={t('footer_telegram', 'Связаться через Telegram')}
                  title={t('footer_telegram', 'Связаться через Telegram')}
                  style={{
                    borderColor: theme.theme === 'dark' ? '#9ca3af' : undefined,
                    backgroundColor: theme.theme === 'dark' ? '#4b5563' : undefined
                  }}
                >
                  <img
                    src="/telegram.svg"
                    alt="Telegram"
                    width="20"
                    height="20"
                    className="transition group-hover:scale-110"
                    style={{
                      zIndex: 1,
                      filter: theme.theme === 'dark' ? 'invert(1)' : 'none'
                    }}
                  />
                </a>
                <a
                  href={settings.whatsapp_url || '#'}
                  target={settings.whatsapp_url ? '_blank' : undefined}
                  rel={settings.whatsapp_url ? 'noopener noreferrer' : undefined}
                  className="group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-main bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-surface/70 hover:shadow-md"
                  aria-label={t('footer_whatsapp', 'Связаться через WhatsApp')}
                  title={t('footer_whatsapp', 'Связаться через WhatsApp')}
                  style={{
                    borderColor: theme.theme === 'dark' ? '#9ca3af' : undefined,
                    backgroundColor: theme.theme === 'dark' ? '#4b5563' : undefined
                  }}
                >
                  <img
                    src="/whatsapp.svg"
                    alt="WhatsApp"
                    width="20"
                    height="20"
                    className="transition group-hover:scale-110"
                    style={{
                      zIndex: 1,
                      filter: theme.theme === 'dark' ? 'invert(1)' : 'none'
                    }}
                  />
                </a>
                <a
                  href={settings.vk_url || '#'}
                  target={settings.vk_url ? '_blank' : undefined}
                  rel={settings.vk_url ? 'noopener noreferrer' : undefined}
                  className="group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-main bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-surface/70 hover:shadow-md"
                  aria-label={t('footer_vk', 'Мы ВКонтакте')}
                  title={t('footer_vk', 'Мы ВКонтакте')}
                  style={{
                    borderColor: theme.theme === 'dark' ? '#9ca3af' : undefined,
                    backgroundColor: theme.theme === 'dark' ? '#4b5563' : undefined
                  }}
                >
                  <img
                    src="/vk.svg"
                    alt="VK"
                    width="20"
                    height="20"
                    className="transition group-hover:scale-110"
                    style={{
                      zIndex: 1,
                      filter: theme.theme === 'dark' ? 'invert(1)' : 'none'
                    }}
                  />
                </a>
                <a
                  href={settings.instagram_url || '#'}
                  target={settings.instagram_url ? '_blank' : undefined}
                  rel={settings.instagram_url ? 'noopener noreferrer' : undefined}
                  className="group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-main bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-surface/70 hover:shadow-md"
                  aria-label={t('footer_instagram', 'Мы в Instagram')}
                  title={t('footer_instagram', 'Мы в Instagram')}
                  style={{
                    borderColor: theme.theme === 'dark' ? '#9ca3af' : undefined,
                    backgroundColor: theme.theme === 'dark' ? '#4b5563' : undefined
                  }}
                >
                  <img
                    src="/instagram.svg"
                    alt="Instagram"
                    width="20"
                    height="20"
                    className="transition group-hover:scale-110"
                    style={{
                      zIndex: 1,
                      filter: theme.theme === 'dark' ? 'invert(1)' : 'none'
                    }}
                  />
                </a>
              </div>
            </div>
          </div>
          <div className="text-center sm:text-left">
            <div className="mb-2 text-sm font-medium text-main">{t('footer_information')}</div>
            <ul className="space-y-1 text-sm text-main/80">
              <li><Link href="/delivery" className="transition-all duration-200 hover:text-red-600 hover:underline hover:font-medium">{t('footer_delivery_payment')}</Link></li>
              <li><Link href="/returns" className="transition-all duration-200 hover:text-red-600 hover:underline hover:font-medium">{t('footer_return')}</Link></li>
              <li><Link href="/privacy" className="transition-all duration-200 hover:text-red-600 hover:underline hover:font-medium">{t('footer_privacy')}</Link></li>
            </ul>
          </div>
        </div>
        <div className="mt-8 border-t border-main pt-4 text-center text-xs text-main/70">
          © <span suppressHydrationWarning>{new Date().getFullYear()}</span> Mudaroba<sup className="text-[0.6em] font-medium ml-0.5 opacity-80">TM</sup>
        </div>
      </div>
    </footer>
  )
}
