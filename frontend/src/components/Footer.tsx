import { useTranslation } from 'next-i18next'
import { useTheme } from '../context/ThemeContext'

export default function Footer() {
  const { t } = useTranslation('common')
  const theme = useTheme()

  return (
    <footer className="mt-10 border-t border-main shadow-xl transition-colors duration-200 dark:bg-[#0c1628] dark:border-[#1f2a3d] dark:shadow-[0_-10px_40px_rgba(0,0,0,0.55)]" style={{ backgroundColor: 'var(--surface)', borderColor: 'var(--border)' }}>
      <div className="mx-auto max-w-6xl px-6 py-10 text-sm text-main">
        <div className="grid grid-cols-1 items-start gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <div className="flex items-start justify-center sm:justify-start">
            {/* Логотип/изображение оплат — увеличенный размер и правильное выравнивание */}
            <div className="group relative">
              <img 
                src="/footer-payments.png" 
                alt="payments" 
                className="h-28 w-auto transition-all duration-200 group-hover:scale-105 group-hover:brightness-110" 
              />
              <div className="absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none">
                <div className="bg-[var(--text-strong)] text-[var(--bg)] dark:bg-white dark:text-gray-900 text-xs px-2 py-1 rounded whitespace-nowrap shadow-lg">
                  {t('footer_crypto_payment', 'Возможна оплата криптовалютой')}
                </div>
                <div className="w-2 h-2 bg-[var(--text-strong)] dark:bg-white rotate-45 absolute top-full left-1/2 -translate-x-1/2 -translate-y-1/2"></div>
              </div>
            </div>
          </div>
          <div className="text-center sm:text-left">
            <div className="mb-2 text-sm font-medium text-main">{t('footer_contacts')}</div>
            <div className="space-y-2 text-sm text-main/80">
              <a href="tel:+905550000000" className="group flex items-center justify-center gap-2 transition-all duration-200 hover:-translate-y-0.5 hover:text-red-600 sm:justify-start">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-red-600 transition-all duration-200 group-hover:scale-110 group-hover:text-red-700">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.86 19.86 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.86 19.86 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.86.33 1.7.62 2.5a2 2 0 0 1-.45 2.11L8 9a16 16 0 0 0 7 7l.67-1.28a2 2 0 0 1 2.11-.45c.8.29 1.64.5 2.5.62A2 2 0 0 1 22 16.92z" />
                </svg>
                <span>{t('footer_phone')}</span>
              </a>
              <a href="mailto:info@turk-export.example" className="group flex items-center justify-center gap-2 transition-all duration-200 hover:-translate-y-0.5 hover:text-red-600 sm:justify-start">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-red-600 transition-all duration-200 group-hover:scale-110 group-hover:text-red-700">
                  <path d="M4 4h16v16H4z" />
                  <path d="m22 6-10 7L2 6" />
                </svg>
                <span>{t('footer_email')}</span>
              </a>
              <div className="flex items-center justify-center gap-2 sm:justify-start">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-red-700">
                  <path d="M21 10c0 7-9 12-9 12S3 17 3 10a9 9 0 1 1 18 0Z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                <span>{t('footer_location')}</span>
              </div>
            </div>
          </div>
          <div className="flex justify-center sm:justify-start">
            <div>
              <div className="mb-2 text-sm font-medium text-main">{t('footer_social_networks')}</div>
              <div className="flex items-center gap-3">
                <a 
                  href="#" 
                  className="group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-main bg-surface transition hover:-translate-y-0.5 hover:bg-surface/70 hover:shadow-md" 
                  aria-label="Telegram"
                  style={{
                    borderColor: theme.theme === 'dark' ? '#9ca3af' : undefined,
                    backgroundColor: theme.theme === 'dark' ? '#4b5563' : undefined
                  }}
                >
                  <img 
                    src="/telegram-icon.png" 
                    alt="Telegram" 
                    width="20" 
                    height="20" 
                    className="transition group-hover:scale-110" 
                    style={{ 
                      zIndex: 1
                    }}
                  />
                </a>
                <a 
                  href="#" 
                  className="group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-main bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-surface/70 hover:shadow-md" 
                  aria-label="WhatsApp"
                  style={{
                    borderColor: theme.theme === 'dark' ? '#9ca3af' : undefined,
                    backgroundColor: theme.theme === 'dark' ? '#4b5563' : undefined
                  }}
                >
                  <img 
                    src="/whatsapp-icon.png" 
                    alt="WhatsApp" 
                    width="20" 
                    height="20" 
                    className="transition group-hover:scale-110" 
                    style={{ 
                      zIndex: 1
                    }}
                  />
                </a>
                <a 
                  href="#" 
                  className="group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-main bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-surface/70 hover:shadow-md" 
                  aria-label="VK"
                  style={{
                    borderColor: theme.theme === 'dark' ? '#9ca3af' : undefined,
                    backgroundColor: theme.theme === 'dark' ? '#4b5563' : undefined
                  }}
                >
                  <img 
                    src="/vk_icon.png" 
                    alt="VK" 
                    width="20" 
                    height="20" 
                    className="transition group-hover:scale-110" 
                    style={{ 
                      zIndex: 1
                    }}
                  />
                </a>
                <a 
                  href="#" 
                  className="group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-main bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-surface/70 hover:shadow-md" 
                  aria-label="Instagram"
                  style={{
                    borderColor: theme.theme === 'dark' ? '#9ca3af' : undefined,
                    backgroundColor: theme.theme === 'dark' ? '#4b5563' : undefined
                  }}
                >
                  <img 
                    src="/instagram-icon.png" 
                    alt="Instagram" 
                    width="20" 
                    height="20" 
                    className="transition group-hover:scale-110" 
                    style={{ 
                      zIndex: 1
                    }}
                  />
                </a>
              </div>
            </div>
          </div>
          <div className="text-center sm:text-left">
            <div className="mb-2 text-sm font-medium text-main">{t('footer_information')}</div>
            <ul className="space-y-1 text-sm text-main/80">
              <li><a href="#" className="transition-all duration-200 hover:text-red-600 hover:underline hover:font-medium">{t('footer_delivery_payment')}</a></li>
              <li><a href="#" className="transition-all duration-200 hover:text-red-600 hover:underline hover:font-medium">{t('footer_return')}</a></li>
              <li><a href="#" className="transition-all duration-200 hover:text-red-600 hover:underline hover:font-medium">{t('footer_privacy')}</a></li>
            </ul>
          </div>
        </div>
        <div className="mt-8 border-t border-main pt-4 text-center text-xs text-main/70">
          © {new Date().getFullYear()} Turk-Export
        </div>
      </div>
    </footer>
  )
}


