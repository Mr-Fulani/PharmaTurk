import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../lib/urls'
import { SITE_NAME, SITE_URL } from '../lib/siteMeta'

export default function HowToOrderMedicinesPage({ footerSettings }: { footerSettings: { phone?: string | null; email?: string | null; location?: string | null; telegram_url?: string | null; whatsapp_url?: string | null; vk_url?: string | null; instagram_url?: string | null; crypto_payment_text?: string | null } }) {
  const { t } = useTranslation('common')
  const hasTelegram = Boolean((footerSettings.telegram_url || '').trim())
  const hasWhatsapp = Boolean((footerSettings.whatsapp_url || '').trim())

  const faqs = [
    { q: t('medicine_how_to_order_q1', 'Можно ли купить лекарства на сайте?'), a: t('medicine_how_to_order_a1', 'Наш сайт не продает лекарства. Мы помогаем с консультацией по наличию, актуальным ценам и порядку заказа из Турции.') },
    { q: t('medicine_how_to_order_q2', 'Как узнать актуальную цену?'), a: t('medicine_how_to_order_a2', 'Оставьте запрос на консультацию или свяжитесь с нами. Мы проверим наличие и актуальные цены по официальным источникам и аптекам.') },
    { q: t('medicine_how_to_order_q3', 'Какие данные нужны для консультации?'), a: t('medicine_how_to_order_a3', 'Название препарата, форма выпуска, дозировка, объем или количество, а также страна доставки.') },
    { q: t('medicine_how_to_order_q4', 'Нужен ли рецепт?'), a: t('medicine_how_to_order_a4', 'Для рецептурных препаратов может потребоваться рецепт. Уточните у нашего консультанта, мы подскажем требования для конкретного препарата и страны доставки.') },
    { q: t('medicine_how_to_order_q5', 'Как происходит доставка?'), a: t('medicine_how_to_order_a5', 'Мы организуем доставку из Турции через проверенные логистические каналы. Сроки и стоимость зависят от страны и выбранного способа доставки.') },
    { q: t('medicine_how_to_order_q6', 'Можно ли оформить заказ на несколько препаратов?'), a: t('medicine_how_to_order_a6', 'Да, можно оформить один запрос на несколько препаратов. Мы проверим наличие и предложим оптимальный вариант.') }
  ]

  return (
    <>
      <Head>
        <title>{`${t('medicine_how_to_order_title', 'Как заказать лекарства из Турции')} — ${SITE_NAME}`}</title>
        <meta name="description" content={t('medicine_how_to_order_subtitle', 'Ответы на частые вопросы о заказе и доставке лекарственных препаратов из Турции.')} />
        <link rel="canonical" href={`${SITE_URL}/how-to-order-medicines`} />
        <link rel="alternate" hrefLang="ru" href={`${SITE_URL}/how-to-order-medicines`} />
        <link rel="alternate" hrefLang="en" href={`${SITE_URL}/en/how-to-order-medicines`} />
        <link rel="alternate" hrefLang="x-default" href={`${SITE_URL}/how-to-order-medicines`} />
        <meta property="og:title" content={`${t('medicine_how_to_order_title', 'Как заказать лекарства из Турции')} — ${SITE_NAME}`} />
        <meta property="og:description" content={t('medicine_how_to_order_subtitle', 'Ответы на частые вопросы о заказе и доставке лекарственных препаратов из Турции.')} />
        <meta property="og:url" content={`${SITE_URL}/how-to-order-medicines`} />
        <meta property="og:type" content="website" />
        <meta property="og:image" content={`${SITE_URL}/og-default.png`} />
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:title" content={`${t('medicine_how_to_order_title', 'Как заказать лекарства из Турции')} — ${SITE_NAME}`} />
        <meta property="twitter:description" content={t('medicine_how_to_order_subtitle', 'Ответы на частые вопросы о заказе и доставке лекарственных препаратов из Турции.')} />
        <meta property="twitter:image" content={`${SITE_URL}/og-default.png`} />
      </Head>
      <main className="mx-auto max-w-5xl p-6 sm:p-10 min-h-screen">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8 shadow-sm">
          <h1 className="mb-3 text-3xl font-bold text-main md:text-4xl text-center">
            {t('medicine_how_to_order_title', 'Как заказать лекарства из Турции')}
          </h1>
          <p className="mb-8 text-center text-base text-main/70 max-w-2xl mx-auto">
            {t('medicine_how_to_order_subtitle', 'Ответы на частые вопросы о заказе и доставке лекарственных препаратов из Турции.')}
          </p>
          <h2 className="mb-4 text-xl font-semibold text-main">
            {t('medicine_how_to_order_faq_title', 'Часто задаваемые вопросы')}
          </h2>
          <div className="space-y-3">
            {faqs.map((item, index) => (
              <details key={`${index}-${item.q}`} className="rounded-lg border border-gray-200 bg-white/70 p-4">
                <summary className="cursor-pointer text-sm font-semibold text-main">
                  {item.q}
                </summary>
                <div className="mt-2 text-sm text-main/70 leading-relaxed">
                  {item.a}
                </div>
              </details>
            ))}
          </div>
          {(hasWhatsapp || hasTelegram) && (
            <div className="mt-10 rounded-xl border border-gray-200 bg-white/70 p-6 text-center">
              <h3 className="text-xl font-semibold text-main">{t('customer_service', 'Служба поддержки')}</h3>
              <p className="mt-2 text-sm text-main/70">
                {t('customer_service_description', 'Наша служба поддержки готова помочь вам с любыми вопросами. Свяжитесь с нами в любое время.')}
              </p>
              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:justify-center">
                {hasWhatsapp && (
                  <a
                    href={footerSettings.whatsapp_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-900 transition-all hover:bg-gray-50"
                  >
                    <img src="/whatsapp-icon.png" alt="WhatsApp" width="18" height="18" />
                    {t('order_via_whatsapp', 'Заказать через WhatsApp')}
                  </a>
                )}
                {hasTelegram && (
                  <a
                    href={footerSettings.telegram_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-900 transition-all hover:bg-gray-50"
                  >
                    <img src="/telegram-icon.png" alt="Telegram" width="18" height="18" />
                    {t('order_via_telegram', 'Заказать через Telegram')}
                  </a>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  let footerSettings = { phone: '', email: '', location: '', telegram_url: '', whatsapp_url: '', vk_url: '', instagram_url: '', crypto_payment_text: '' }
  try {
    const res = await axios.get(getInternalApiUrl('settings/footer-settings'))
    const data = res.data || {}
    footerSettings = {
      phone: data.phone || '',
      email: data.email || '',
      location: data.location || '',
      telegram_url: data.telegram_url || '',
      whatsapp_url: data.whatsapp_url || '',
      vk_url: data.vk_url || '',
      instagram_url: data.instagram_url || '',
      crypto_payment_text: data.crypto_payment_text || '',
    }
  } catch {}
  return {
    props: {
      footerSettings,
      ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
    },
  }
}
