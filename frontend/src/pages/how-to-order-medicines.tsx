import { GetServerSideProps } from 'next'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

import SEO from '../components/SEO'
import api from '../lib/api'
import {
  appendWhatsappText,
  buildMedicineConsultMessage,
  normalizeMedicineSlug,
  shouldPollMedicineMarketCheck,
  startMedicineMarketCheckSingleFlight,
} from '../lib/medicineMarketCheck'
import { buildProductUrl, getInternalApiUrl, getSiteOrigin } from '../lib/urls'

type FooterSettings = {
  phone?: string | null
  email?: string | null
  location?: string | null
  telegram_url?: string | null
  whatsapp_url?: string | null
  vk_url?: string | null
  instagram_url?: string | null
  crypto_payment_text?: string | null
}

type MedicineSummary = {
  id: number
  slug: string
  name: string
  dosage_form?: string | null
  volume?: string | null
  active_ingredient?: string | null
}

type MarketCheckPayload = {
  enabled: boolean
  status: 'not_requested' | 'pending' | 'running' | 'succeeded' | 'source_unavailable' | 'failed'
  product: MedicineSummary
  price?: { amount: string; currency: string } | null
  previous_price?: string | null
  source?: string | null
  analog_count: number
  requested_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  last_success_at?: string | null
  is_stale: boolean
  error?: { code: string; message: string } | null
  poll_after_seconds?: number | null
  queued?: boolean
  cached?: boolean
}

type MedicineAnalogResult = {
  id?: number | null
  reference_id?: number | null
  slug?: string | null
  name: string
  dosage_form?: string | null
  active_ingredient?: string | null
  is_catalog_product?: boolean
  source_reference_price?: number | null
  source_reference_currency?: string | null
  original_price?: number | null
  original_currency?: string | null
  source_last_observed_at?: string | null
}

const MAX_POLL_ATTEMPTS = 65

export default function HowToOrderMedicinesPage({ footerSettings }: { footerSettings: FooterSettings }) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const requestedSlug = normalizeMedicineSlug(router.query.medicine)
  const translationRef = useRef(t)
  translationRef.current = t
  const [marketCheck, setMarketCheck] = useState<MarketCheckPayload | null>(null)
  const [marketError, setMarketError] = useState('')
  const [analogs, setAnalogs] = useState<MedicineAnalogResult[]>([])
  const [analogsLoading, setAnalogsLoading] = useState(false)

  const hasTelegram = Boolean((footerSettings.telegram_url || '').trim())
  const hasWhatsapp = Boolean((footerSettings.whatsapp_url || '').trim())

  const faqs = [
    { q: t('medicine_how_to_order_q1', 'Можно ли купить лекарства на сайте?'), a: t('medicine_how_to_order_a1', 'Наш сайт не продает лекарства. Мы помогаем с консультацией по наличию, актуальным ценам и порядку заказа из Турции.') },
    { q: t('medicine_how_to_order_q2', 'Как узнать актуальную цену?'), a: t('medicine_how_to_order_a2', 'Оставьте запрос на консультацию или свяжитесь с нами. Мы проверим наличие и актуальные цены по официальным источникам и аптекам.') },
    { q: t('medicine_how_to_order_q3', 'Какие данные нужны для консультации?'), a: t('medicine_how_to_order_a3', 'Название препарата, форма выпуска, дозировка, объем или количество, а также страна доставки.') },
    { q: t('medicine_how_to_order_q4', 'Нужен ли рецепт?'), a: t('medicine_how_to_order_a4', 'Для рецептурных препаратов может потребоваться рецепт. Уточните у нашего консультанта, мы подскажем требования для конкретного препарата и страны доставки.') },
    { q: t('medicine_how_to_order_q5', 'Как происходит доставка?'), a: t('medicine_how_to_order_a5', 'Мы организуем доставку из Турции через проверенные логистические каналы. Сроки и стоимость зависят от страны и выбранного способа доставки.') },
    { q: t('medicine_how_to_order_q6', 'Можно ли оформить заказ на несколько препаратов?'), a: t('medicine_how_to_order_a6', 'Да, можно оформить один запрос на несколько препаратов. Мы проверим наличие и предложим оптимальный вариант.') },
  ]

  useEffect(() => {
    if (!router.isReady) return
    if (!requestedSlug) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let pollAttempts = 0

    const loadAnalogs = async () => {
      if (cancelled) return
      setAnalogsLoading(true)
      try {
        const response = await api.get(
          `/catalog/medicines/products/${encodeURIComponent(requestedSlug)}/analogs`,
          { params: { limit: 10, currency: 'TRY' } },
        )
        if (!cancelled) setAnalogs(Array.isArray(response.data?.results) ? response.data.results : [])
      } catch {
        if (!cancelled) setAnalogs([])
      } finally {
        if (!cancelled) setAnalogsLoading(false)
      }
    }

    const acceptPayload = (payload: MarketCheckPayload) => {
      if (cancelled) return
      setMarketCheck(payload)
      if (!shouldPollMedicineMarketCheck(payload.status)) void loadAnalogs()
    }

    const poll = async () => {
      if (cancelled) return
      pollAttempts += 1
      if (pollAttempts > MAX_POLL_ATTEMPTS) {
        setMarketError(translationRef.current('medicine_market_check_timeout', 'Проверка занимает больше обычного. Обновите страницу немного позже.'))
        return
      }
      try {
        const response = await api.get<MarketCheckPayload>(
          `/catalog/medicines/products/${encodeURIComponent(requestedSlug)}/market-check`,
        )
        const payload = response.data
        acceptPayload(payload)
        if (shouldPollMedicineMarketCheck(payload.status) && !cancelled) {
          timer = setTimeout(poll, Math.max(1, payload.poll_after_seconds || 2) * 1000)
        }
      } catch {
        if (!cancelled) {
          setMarketError(translationRef.current('medicine_market_check_read_error', 'Не удалось получить состояние проверки. Обновите страницу позже.'))
        }
      }
    }

    const start = async () => {
      setMarketCheck(null)
      setMarketError('')
      setAnalogs([])
      try {
        const response = await startMedicineMarketCheckSingleFlight(
          requestedSlug,
          () => api.post<MarketCheckPayload>(
            `/catalog/medicines/products/${encodeURIComponent(requestedSlug)}/market-check`,
          ),
        )
        const payload = response.data
        acceptPayload(payload)
        if (shouldPollMedicineMarketCheck(payload.status) && !cancelled) {
          timer = setTimeout(poll, Math.max(1, payload.poll_after_seconds || 2) * 1000)
        }
      } catch (error) {
        if (cancelled) return
        if (axios.isAxiosError(error) && error.response?.data) {
          const payload = error.response.data as MarketCheckPayload
          if (payload.product) setMarketCheck(payload)
          setMarketError(payload.error?.message || translationRef.current('medicine_market_check_start_error', 'Не удалось запустить проверку цены.'))
        } else {
          setMarketError(translationRef.current('medicine_market_check_start_error', 'Не удалось запустить проверку цены.'))
        }
      }
    }

    void start()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [requestedSlug, router.isReady])

  const productPageUrl = useMemo(() => {
    const productSlug = marketCheck?.product?.slug || requestedSlug
    if (!productSlug) return ''
    return `${getSiteOrigin()}${buildProductUrl('medicines', productSlug)}`
  }, [marketCheck?.product?.slug, requestedSlug])
  const consultMessage = useMemo(
    () => buildMedicineConsultMessage(
      marketCheck?.product,
      marketCheck,
      productPageUrl,
      router.locale,
    ),
    [marketCheck, productPageUrl, router.locale],
  )
  const whatsappHref = appendWhatsappText(footerSettings.whatsapp_url, consultMessage)

  const checkedAt = marketCheck?.last_success_at
    ? new Intl.DateTimeFormat(router.locale || 'ru', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(marketCheck.last_success_at))
    : ''

  const statusMessage = (() => {
    if (!marketCheck) return t('medicine_market_check_starting', 'Запускаем проверку актуальной цены…')
    if (marketCheck.status === 'pending') return t('medicine_market_check_pending', 'Проверка поставлена в очередь…')
    if (marketCheck.status === 'running') return t('medicine_market_check_running', 'Проверяем цену в первоисточнике…')
    if (marketCheck.status === 'succeeded') return t('medicine_market_check_succeeded', 'Цена проверена')
    if (marketCheck.status === 'source_unavailable') return t('medicine_market_check_unavailable', 'Источник временно недоступен')
    if (marketCheck.status === 'failed') return t('medicine_market_check_failed', 'Не удалось подтвердить актуальную цену')
    return ''
  })()

  return (
    <>
      <SEO
        title={t('medicine_how_to_order_title', 'Как заказать лекарства из Турции')}
        description={t('medicine_how_to_order_subtitle', 'Ответы на частые вопросы о заказе и доставке лекарственных препаратов из Турции.')}
        canonical="/how-to-order-medicines"
      />
      <main className="mx-auto max-w-5xl p-6 sm:p-10 min-h-screen">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 sm:p-8 shadow-sm">
          <h1 className="mb-3 text-3xl font-bold text-main md:text-4xl text-center">
            {t('medicine_how_to_order_title', 'Как заказать лекарства из Турции')}
          </h1>
          <p className="mb-8 text-center text-base text-main/70 max-w-2xl mx-auto">
            {t('medicine_how_to_order_subtitle', 'Ответы на частые вопросы о заказе и доставке лекарственных препаратов из Турции.')}
          </p>

          {requestedSlug && (
            <section className="mb-10 rounded-xl border border-blue-200 bg-blue-50/70 p-5 sm:p-6" aria-live="polite">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                    {t('medicine_market_check_title', 'Проверка по вашему запросу')}
                  </p>
                  <h2 className="mt-1 text-xl font-bold text-gray-950">
                    {marketCheck?.product?.name || requestedSlug}
                  </h2>
                  {(marketCheck?.product?.dosage_form || marketCheck?.product?.volume) && (
                    <p className="mt-1 text-sm text-gray-700">
                      {[marketCheck.product.dosage_form, marketCheck.product.volume].filter(Boolean).join(' · ')}
                    </p>
                  )}
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  marketCheck?.status === 'succeeded'
                    ? 'bg-emerald-100 text-emerald-800'
                    : marketCheck?.status === 'failed' || marketCheck?.status === 'source_unavailable'
                      ? 'bg-amber-100 text-amber-900'
                      : 'bg-blue-100 text-blue-800'
                }`}>
                  {statusMessage}
                </span>
              </div>

              {marketCheck?.price && (
                <div className="mt-5 rounded-lg border border-white bg-white p-4 shadow-sm">
                  <p className="text-sm text-gray-600">{t('medicine_market_reference_price', 'Справочная цена первоисточника')}</p>
                  <p className="mt-1 text-3xl font-bold text-gray-950">
                    {marketCheck.price.amount} {marketCheck.price.currency}
                  </p>
                  <p className="mt-1 text-xs text-gray-500">
                    {checkedAt
                      ? t('medicine_market_checked_at', 'Проверено: {{date}}', { date: checkedAt })
                      : t('medicine_market_price_disclaimer', 'Цена носит информационный характер и не является публичной офертой.')}
                    {marketCheck.is_stale ? ` · ${t('medicine_market_price_stale', 'последняя успешно подтверждённая цена')}` : ''}
                  </p>
                </div>
              )}

              {marketError && (
                <p className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  {marketError}
                </p>
              )}

              {!marketError && marketCheck?.error?.message && (
                <p className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  {marketCheck.error.message}
                </p>
              )}

              <p className="mt-4 text-xs leading-5 text-gray-600">
                {t('medicine_market_medical_disclaimer', 'Эквиваленты приводятся только для справки. Не заменяйте назначенный препарат без консультации врача или фармацевта.')}
              </p>

              {(analogsLoading || analogs.length > 0) && (
                <div className="mt-6">
                  <h3 className="text-base font-semibold text-gray-950">
                    {t('medicine_market_analogs_title', 'Найденные эквиваленты')}
                  </h3>
                  {analogsLoading ? (
                    <p className="mt-2 text-sm text-gray-600">{t('loading', 'Загрузка…')}</p>
                  ) : (
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      {analogs.map((analog) => {
                        const referencePrice = analog.source_reference_price ?? analog.original_price
                        const referenceCurrency = analog.source_reference_currency || analog.original_currency || 'TRY'
                        const content = (
                          <>
                            <p className="font-semibold text-gray-950">{analog.name}</p>
                            {(analog.dosage_form || analog.active_ingredient) && (
                              <p className="mt-1 text-xs text-gray-600">
                                {[analog.dosage_form, analog.active_ingredient].filter(Boolean).join(' · ')}
                              </p>
                            )}
                            {referencePrice != null && (
                              <p className="mt-2 text-sm font-semibold text-blue-800">
                                {referencePrice} {referenceCurrency}
                              </p>
                            )}
                            <p className="mt-1 text-xs text-gray-500">
                              {analog.is_catalog_product
                                ? t('medicine_market_analog_catalog', 'Карточка в каталоге')
                                : t('medicine_market_analog_reference', 'Эквивалент из первоисточника')}
                            </p>
                          </>
                        )
                        return analog.slug ? (
                          <Link
                            key={`catalog-${analog.id || analog.slug}`}
                            href={buildProductUrl('medicines', analog.slug)}
                            className="rounded-lg border border-blue-100 bg-white p-4 transition hover:border-blue-300 hover:shadow-sm"
                          >
                            {content}
                          </Link>
                        ) : (
                          <div key={`reference-${analog.reference_id || analog.name}`} className="rounded-lg border border-blue-100 bg-white p-4">
                            {content}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}

              {(hasWhatsapp || hasTelegram) && marketCheck?.product && (
                <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                  {hasWhatsapp && whatsappHref && (
                    <a
                      href={whatsappHref}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex flex-1 items-center justify-center rounded-md bg-[#25D366] px-4 py-3 text-sm font-semibold text-white hover:bg-[#128C7E]"
                    >
                      {t('medicine_market_consult', 'Уточнить заказ у консультанта')}
                    </a>
                  )}
                  {hasTelegram && (
                    <a
                      href={footerSettings.telegram_url || ''}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex flex-1 items-center justify-center rounded-md bg-[#0088cc] px-4 py-3 text-sm font-semibold text-white hover:bg-[#0077b5]"
                    >
                      {t('order_via_telegram', 'Заказать через Telegram')}
                    </a>
                  )}
                </div>
              )}
            </section>
          )}

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

          {(hasWhatsapp || hasTelegram) && !requestedSlug && (
            <div className="mt-10 rounded-xl border border-gray-200 bg-white/70 p-6 text-center">
              <h3 className="text-xl font-semibold text-main">{t('customer_service', 'Служба поддержки')}</h3>
              <p className="mt-2 text-sm text-main/70">
                {t('customer_service_description', 'Наша служба поддержки готова помочь вам с любыми вопросами. Свяжитесь с нами в любое время.')}
              </p>
              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:justify-center">
                {hasWhatsapp && (
                  <a
                    href={footerSettings.whatsapp_url || ''}
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
                    href={footerSettings.telegram_url || ''}
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
  let footerSettings: FooterSettings = { phone: '', email: '', location: '', telegram_url: '', whatsapp_url: '', vk_url: '', instagram_url: '', crypto_payment_text: '' }
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
