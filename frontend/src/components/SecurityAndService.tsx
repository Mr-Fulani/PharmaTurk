import { useState } from 'react'
import { useTranslation } from 'next-i18next'

/**
 * Компонент "Безопасность и сервис" с раскрывающимися секциями
 * При раскрытии показывает все 4 секции сразу с их описаниями
 */
export default function SecurityAndService() {
  const { t } = useTranslation('common')
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="mt-6 rounded-lg border border-gray-200 bg-white overflow-hidden">
      {/* Заголовок с зеленым фоном */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 text-left bg-green-50 hover:bg-green-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span className="font-medium text-green-700">{t('security_and_service', 'Безопасность и сервис')}</span>
        </div>
        <svg
          className={`w-5 h-5 text-green-600 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isExpanded && (
        <div className="bg-stone-50 p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Безопасность платежей */}
            <div>
              <div className="flex items-center gap-3 mb-3">
                <div className="relative flex-shrink-0">
                  <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                  </svg>
                  <svg className="w-4 h-4 text-green-600 absolute -top-1 -right-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                </div>
                <span className="text-sm font-medium text-gray-900">{t('payment_security', 'Безопасность платежей')}</span>
              </div>
              <p className="text-sm text-gray-600 pl-11">
                {t('payment_security_description', 'Мы гарантируем безопасность ваших платежей. Ваши платежные данные защищены и передаются только проверенным платежным системам.')}
              </p>
            </div>

            {/* Защита конфиденциальности */}
            <div>
              <div className="flex items-center gap-3 mb-3">
                <div className="relative flex-shrink-0">
                  <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  <svg className="w-4 h-4 text-green-600 absolute -bottom-1 -right-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </div>
                <span className="text-sm font-medium text-gray-900">{t('privacy_protection', 'Защита конфиденциальности')}</span>
              </div>
              <p className="text-sm text-gray-600 pl-11">
                {t('privacy_protection_description', 'Мы используем современные методы шифрования для защиты ваших персональных данных. Ваша конфиденциальность - наш приоритет.')}
              </p>
            </div>

            {/* Быстрая и безопасная доставка */}
            <div>
              <div className="flex items-center gap-3 mb-3">
                <div className="relative flex-shrink-0">
                  <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
                  </svg>
                  <svg className="w-4 h-4 text-green-600 absolute -top-1 -right-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <span className="text-sm font-medium text-gray-900">{t('fast_safe_delivery', 'Быстрая и безопасная доставка')}</span>
              </div>
              <p className="text-sm text-gray-600 pl-11">
                {t('delivery_description', 'Мы обеспечиваем быструю и надежную доставку. Вы можете отслеживать статус заказа в реальном времени.')}
              </p>
            </div>

            {/* Служба поддержки */}
            <div>
              <div className="flex items-center gap-3 mb-3">
                <div className="relative flex-shrink-0">
                  <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                </div>
                <span className="text-sm font-medium text-gray-900">{t('customer_service', 'Служба поддержки')}</span>
              </div>
              <p className="text-sm text-gray-600 pl-11">
                {t('customer_service_description', 'Наша служба поддержки готова помочь вам с любыми вопросами. Свяжитесь с нами в любое время.')}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

