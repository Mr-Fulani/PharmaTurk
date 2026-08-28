import axios from 'axios'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'

import api from '../lib/api'
import { appendWhatsappText, selectMarketCheckDisplayPrice } from '../lib/medicineMarketCheck'
import { formatPrice } from '../lib/price'

type SupplementMarketCheck = {
  enabled: boolean
  status: 'not_requested' | 'pending' | 'running' | 'succeeded' | 'source_unavailable' | 'failed'
  product?: {
    id: number
    slug: string
    name: string
    dosage_form?: string | null
    active_ingredient?: string | null
    serving_size?: string | null
  }
  price?: { amount: string; currency: string } | null
  display_price?: { amount: string; currency: string } | null
  availability?: {
    status: string
    can_add_to_cart: boolean
    purchase_mode: string
    message: string
  }
  last_success_at?: string | null
  is_stale: boolean
  error?: { code: string; message: string } | null
  poll_after_seconds?: number | null
}

type Props = {
  slug: string
  name: string
  productUrl: string
  whatsappUrl?: string | null
  telegramUrl?: string | null
}

const ACTIVE_STATUSES = new Set(['pending', 'running'])
const MAX_POLL_ATTEMPTS = 65

export default function SupplementPurchasePanel({
  slug,
  name,
  productUrl,
  whatsappUrl,
  telegramUrl,
}: Props) {
  const { t, i18n } = useTranslation('common')
  const [result, setResult] = useState<SupplementMarketCheck | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [starting, setStarting] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const requestGeneration = useRef(0)

  useEffect(() => () => {
    requestGeneration.current += 1
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  const schedulePoll = (
    payload: SupplementMarketCheck,
    generation: number,
    attempt: number,
  ): void => {
    if (!ACTIVE_STATUSES.has(payload.status)) return
    if (attempt >= MAX_POLL_ATTEMPTS) {
      setErrorMessage(t('supplement_market_check_timeout', 'Проверка занимает больше обычного. Попробуйте позже.'))
      return
    }
    const delay = Math.max(1, payload.poll_after_seconds || 2) * 1000
    timerRef.current = setTimeout(async () => {
      if (generation !== requestGeneration.current) return
      try {
        const response = await api.get<SupplementMarketCheck>(
          `/catalog/supplements/products/${encodeURIComponent(slug)}/market-check`,
        )
        if (generation !== requestGeneration.current) return
        setResult(response.data)
        schedulePoll(response.data, generation, attempt + 1)
      } catch {
        if (generation === requestGeneration.current) {
          setErrorMessage(t('supplement_market_check_read_error', 'Не удалось получить состояние проверки. Попробуйте позже.'))
        }
      }
    }, delay)
  }

  const startCheck = async () => {
    if (starting || ACTIVE_STATUSES.has(result?.status || '')) return
    const generation = requestGeneration.current + 1
    requestGeneration.current = generation
    if (timerRef.current) clearTimeout(timerRef.current)
    setStarting(true)
    setErrorMessage('')
    try {
      const response = await api.post<SupplementMarketCheck>(
        `/catalog/supplements/products/${encodeURIComponent(slug)}/market-check`,
      )
      if (generation !== requestGeneration.current) return
      setResult(response.data)
      schedulePoll(response.data, generation, 0)
    } catch (error) {
      if (generation !== requestGeneration.current) return
      if (axios.isAxiosError(error) && error.response?.data) {
        const payload = error.response.data as SupplementMarketCheck
        setResult(payload)
        setErrorMessage(payload.error?.message || t('supplement_market_check_start_error', 'Не удалось запустить проверку цены.'))
      } else {
        setErrorMessage(t('supplement_market_check_start_error', 'Не удалось запустить проверку цены.'))
      }
    } finally {
      if (generation === requestGeneration.current) setStarting(false)
    }
  }

  const statusMessage = (() => {
    if (starting || result?.status === 'pending') return t('supplement_market_check_pending', 'Проверка поставлена в очередь…')
    if (result?.status === 'running') return t('supplement_market_check_running', 'Проверяем цену в первоисточнике…')
    if (result?.status === 'succeeded') return t('supplement_market_check_succeeded', 'Справочная цена проверена')
    if (result?.status === 'source_unavailable') return t('supplement_market_check_unavailable', 'Источник временно недоступен')
    if (result?.status === 'failed') return t('supplement_market_check_failed', 'Не удалось подтвердить актуальную цену')
    return ''
  })()

  const checkedAt = result?.last_success_at
    ? new Intl.DateTimeFormat(i18n.language || 'ru', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(result.last_success_at))
    : ''
  const displayPrice = selectMarketCheckDisplayPrice(result)
  const formattedDisplayPrice = displayPrice
    ? formatPrice(displayPrice.amount, displayPrice.currency, i18n.language) || displayPrice.amount
    : ''
  const consultMessage = useMemo(() => {
    const english = String(i18n.language || '').toLowerCase().startsWith('en')
    const referencePrice = displayPrice
      ? `${displayPrice.amount} ${displayPrice.currency}`
      : ''
    return [
      english
        ? `Hello! Please confirm availability and the final price for this supplement: ${name}.`
        : `Здравствуйте! Подтвердите, пожалуйста, наличие и итоговую цену БАДа: ${name}.`,
      referencePrice
        ? `${english ? 'Reference price' : 'Справочная цена'}: ${referencePrice}.`
        : '',
      productUrl ? `${english ? 'Product page' : 'Карточка'}: ${productUrl}` : '',
    ].filter(Boolean).join('\n')
  }, [displayPrice, i18n.language, name, productUrl])
  const whatsappHref = appendWhatsappText(whatsappUrl, consultMessage)

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100">
      <p className="text-sm font-semibold">
        {t('supplement_stock_unverified_title', 'Продажное наличие пока не подтверждено')}
      </p>
      <p className="mt-1 text-xs leading-5">
        {t('supplement_stock_unverified_text', 'Первоисточник сообщает справочную цену, но не складской остаток. Мы не добавляем товар в оплачиваемую корзину без проверки реального поставщика.')}
      </p>

      <button
        type="button"
        onClick={startCheck}
        disabled={starting || ACTIVE_STATUSES.has(result?.status || '')}
        className="mt-4 w-full rounded-md bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-wait disabled:opacity-70"
      >
        {statusMessage || t('supplement_market_check_button', 'Проверить актуальную справочную цену')}
      </button>

      {displayPrice && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-white px-4 py-3 text-gray-950 dark:border-amber-800 dark:bg-gray-900 dark:text-gray-100">
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {t('supplement_market_reference_price', 'Справочная цена первоисточника')}
          </p>
          <p className="mt-1 text-2xl font-bold">{formattedDisplayPrice} {displayPrice.currency}</p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {checkedAt
              ? t('supplement_market_checked_at', 'Проверено: {{date}}', { date: checkedAt })
              : t('supplement_market_price_disclaimer', 'Не является публичной офертой.')}
            {result.is_stale ? ` · ${t('supplement_market_price_stale', 'последняя подтверждённая цена')}` : ''}
          </p>
        </div>
      )}

      {(errorMessage || result?.error?.message) && (
        <p className="mt-3 rounded-md border border-amber-300 bg-white/70 px-3 py-2 text-xs dark:bg-gray-900/60">
          {errorMessage || result?.error?.message}
        </p>
      )}

      {(whatsappHref || telegramUrl) && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          {whatsappHref && (
            <a
              href={whatsappHref}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex flex-1 items-center justify-center rounded-md bg-[#25D366] px-4 py-3 text-sm font-semibold text-white hover:bg-[#128C7E]"
            >
              {t('supplement_consult_button', 'Уточнить наличие у консультанта')}
            </a>
          )}
          {telegramUrl && (
            <a
              href={telegramUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex flex-1 items-center justify-center rounded-md bg-[#0088cc] px-4 py-3 text-sm font-semibold text-white hover:bg-[#0077b5]"
            >
              {t('order_via_telegram', 'Заказать через Telegram')}
            </a>
          )}
        </div>
      )}
    </div>
  )
}
