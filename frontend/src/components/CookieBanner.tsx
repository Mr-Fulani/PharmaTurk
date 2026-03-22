import { useEffect, useRef } from 'react'
import { useTranslation } from 'next-i18next'
import Link from 'next/link'
import { useCookieConsent } from '../hooks/useCookieConsent'
import styles from './CookieBanner.module.css'

/**
 * Cookie Consent баннер.
 * Показывается всем пользователям до принятия/отказа от аналитических cookie.
 * После выбора не появляется (сохраняется в cookie на 30-365 дней).
 */
export default function CookieBanner() {
  const { t, i18n } = useTranslation('common')
  const { consent, accept, reject, isLoaded } = useCookieConsent()
  const bannerRef = useRef<HTMLDivElement>(null)

  // Анимация slide-up при появлении
  useEffect(() => {
    if (isLoaded && consent === null && bannerRef.current) {
      requestAnimationFrame(() => {
        if (bannerRef.current) {
          bannerRef.current.classList.add(styles.visible)
        }
      })
    }
  }, [isLoaded, consent])

  // Не рендерим до hydration и если согласие уже дано
  if (!isLoaded || consent !== null) return null

  const privacyPath = i18n.language === 'ru' ? '/ru/privacy' : '/privacy'

  return (
    <div
      ref={bannerRef}
      className={styles.banner}
      role="dialog"
      aria-live="polite"
      aria-label={t('cookie_banner_label', 'Уведомление о cookie')}
      id="cookie-consent-banner"
    >
      <div className={styles.inner}>
        {/* Иконка */}
        <div className={styles.icon} aria-hidden="true">
          🍪
        </div>

        {/* Текст */}
        <div className={styles.content}>
          <p className={styles.title}>
            {t('cookie_banner_title', 'Мы используем cookie')}
          </p>
          <p className={styles.text}>
            {t(
              'cookie_banner_text',
              'Мы используем файлы cookie для улучшения работы сайта, аналитики и персонализации. Без вашего согласия аналитические данные не собираются.'
            )}{' '}
            <Link href={privacyPath} className={styles.link} id="cookie-banner-privacy-link">
              {t('cookie_banner_learn_more', 'Подробнее')}
            </Link>
          </p>
        </div>

        {/* Кнопки */}
        <div className={styles.actions}>
          <button
            id="cookie-accept-btn"
            className={styles.btnAccept}
            onClick={accept}
            type="button"
          >
            {t('cookie_banner_accept', 'Принять все')}
          </button>
          <button
            id="cookie-reject-btn"
            className={styles.btnReject}
            onClick={reject}
            type="button"
          >
            {t('cookie_banner_essential', 'Только необходимые')}
          </button>
        </div>
      </div>
    </div>
  )
}
