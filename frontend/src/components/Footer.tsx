import { useTranslation } from 'next-i18next'

export default function Footer() {
  const { t } = useTranslation('common')

  return (
    <footer className="mt-10 border-t border-red-400 bg-gradient-to-b from-red-100 via-red-50 to-rose-100 shadow-xl">
      <div className="mx-auto max-w-6xl px-6 py-10 text-sm text-gray-700">
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
                <div className="bg-gray-800 text-white text-xs px-2 py-1 rounded whitespace-nowrap">
                  {t('footer_crypto_payment', 'Возможна оплата криптовалютой')}
                </div>
                <div className="w-2 h-2 bg-gray-800 rotate-45 absolute top-full left-1/2 -translate-x-1/2 -translate-y-1/2"></div>
              </div>
            </div>
          </div>
          <div className="text-center sm:text-left">
            <div className="mb-2 text-sm font-medium text-gray-800">{t('footer_contacts')}</div>
            <div className="space-y-2 text-sm text-gray-600">
              <a href="tel:+905550000000" className="group flex items-center justify-center gap-2 transition-all duration-200 hover:-translate-y-0.5 hover:text-red-700 sm:justify-start">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-red-700 transition-all duration-200 group-hover:scale-110 group-hover:text-red-800">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.86 19.86 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.86 19.86 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.86.33 1.7.62 2.5a2 2 0 0 1-.45 2.11L8 9a16 16 0 0 0 7 7l.67-1.28a2 2 0 0 1 2.11-.45c.8.29 1.64.5 2.5.62A2 2 0 0 1 22 16.92z" />
                </svg>
                <span>{t('footer_phone')}</span>
              </a>
              <a href="mailto:info@turk-export.example" className="group flex items-center justify-center gap-2 transition-all duration-200 hover:-translate-y-0.5 hover:text-red-700 sm:justify-start">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-red-700 transition-all duration-200 group-hover:scale-110 group-hover:text-red-800">
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
              <div className="mb-2 text-sm font-medium text-gray-800">{t('footer_social_networks')}</div>
              <div className="flex items-center gap-3">
                <a href="#" className="group inline-flex h-12 w-12 items-center justify-center rounded-full border border-red-200 bg-white transition hover:-translate-y-0.5 hover:bg-red-50 hover:shadow-md" aria-label="Telegram">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-blue-500 transition group-hover:scale-110">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.05-.2-.06-.06-.14-.04-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.75-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z"/>
                  </svg>
                </a>
                <a href="#" className="group inline-flex h-12 w-12 items-center justify-center rounded-full border border-red-200 bg-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-red-100 hover:border-red-400 hover:shadow-md" aria-label="WhatsApp">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-green-500 transition group-hover:scale-110">
                    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893A11.821 11.821 0 0020.885 3.488"/>
                  </svg>
                </a>
                <a href="#" className="group inline-flex h-12 w-12 items-center justify-center rounded-full border border-red-200 bg-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-red-100 hover:border-red-400 hover:shadow-md" aria-label="VK">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-blue-600 transition group-hover:scale-110">
                    <path d="M15.07 8.93v-1.4c0-.2-.13-.34-.33-.34h-1.4c-.2 0-.33.13-.33.34v1.4c0 .2.13.34.33.34h1.4c.2 0 .33-.13.33-.34zm-4.6 0v-1.4c0-.2-.13-.34-.33-.34H8.74c-.2 0-.33.13-.33.34v1.4c0 .2.13.34.33.34h1.4c.2 0 .33-.13.33-.34zm4.6 4.6v-1.4c0-.2-.13-.34-.33-.34h-1.4c-.2 0-.33.13-.33.34v1.4c0 .2.13.34.33.34h1.4c.2 0 .33-.13.33-.34zm-4.6 0v-1.4c0-.2-.13-.34-.33-.34H8.74c-.2 0-.33.13-.33.34v1.4c0 .2.13.34.33.34h1.4c.2 0 .33-.13.33-.34zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/>
                  </svg>
                </a>
                <a href="#" className="group inline-flex h-12 w-12 items-center justify-center rounded-full border border-red-200 bg-white transition-all duration-200 hover:-translate-y-0.5 hover:bg-red-100 hover:border-red-400 hover:shadow-md" aria-label="Instagram">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-pink-500 transition group-hover:scale-110">
                    <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
                  </svg>
                </a>
              </div>
            </div>
          </div>
          <div className="text-center sm:text-left">
            <div className="mb-2 text-sm font-medium text-gray-800">{t('footer_information')}</div>
            <ul className="space-y-1 text-sm text-gray-600">
              <li><a href="#" className="transition-all duration-200 hover:text-red-700 hover:underline hover:font-medium">{t('footer_delivery_payment')}</a></li>
              <li><a href="#" className="transition-all duration-200 hover:text-red-700 hover:underline hover:font-medium">{t('footer_return')}</a></li>
              <li><a href="#" className="transition-all duration-200 hover:text-red-700 hover:underline hover:font-medium">{t('footer_privacy')}</a></li>
            </ul>
          </div>
        </div>
        <div className="mt-8 border-t border-red-200 pt-4 text-center text-xs text-gray-600">
          © {new Date().getFullYear()} Turk-Export
        </div>
      </div>
    </footer>
  )
}


