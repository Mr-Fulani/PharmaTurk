import axios from 'axios'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'

import api from '../lib/api'
import { selectMarketCheckDisplayPrice } from '../lib/medicineMarketCheck'
import { formatPrice } from '../lib/price'

export type SupplementMarketCheck = {
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
  autoStart?: boolean
  renderStatus?: boolean
  onResult?: (result: SupplementMarketCheck) => void
}

const ACTIVE_STATUSES = new Set(['pending', 'running'])
const MAX_POLL_ATTEMPTS = 65

export default function SupplementPurchasePanel({
  slug,
  autoStart = false,
  renderStatus = true,
  onResult,
}: Props) {
  const { t, i18n } = useTranslation('common')
  const [result, setResult] = useState<SupplementMarketCheck | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [starting, setStarting] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const requestGeneration = useRef(0)
  const autoStartedSlug = useRef('')
  const onResultRef = useRef(onResult)

  useEffect(() => {
    onResultRef.current = onResult
  }, [onResult])

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
        onResultRef.current?.(response.data)
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
      onResultRef.current?.(response.data)
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

  useEffect(() => {
    if (!autoStart || autoStartedSlug.current === slug) return
    autoStartedSlug.current = slug
    void startCheck()
    // startCheck intentionally uses the current slug/result snapshot; the ref
    // prevents rerenders from starting duplicate checks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, slug])

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
  const liveOfferVerified = result?.availability?.status === 'live_on_cart'

  // The product card uses this component as a headless price refresher. All
  // hooks and polling remain active, but supplement-specific reference/status
  // copy is intentionally omitted from the customer-facing details page.
  if (!renderStatus) return null

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50/70 p-4 text-blue-950 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-100">
      <div className="flex items-center gap-2">
        {(starting || ACTIVE_STATUSES.has(result?.status || '')) && (
          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
        )}
        <p className="text-sm font-semibold">
          {t('supplement_market_check_compact_title', 'Проверка цены и наличия')}
        </p>
      </div>
      <p className="mt-1 text-xs leading-5">
        {statusMessage || t('supplement_market_check_auto_start', 'Актуализируем данные по источникам…')}
      </p>

      {!starting && !ACTIVE_STATUSES.has(result?.status || '') && result?.status !== 'succeeded' && (
        <button
          type="button"
          onClick={startCheck}
          className="mt-3 rounded-md border border-blue-400 px-3 py-2 text-xs font-semibold text-blue-800 transition hover:bg-blue-100 dark:text-blue-100"
        >
          {t('supplement_market_check_retry', 'Проверить ещё раз')}
        </button>
      )}

      {displayPrice && (
        <div className="mt-3 rounded-lg border border-blue-200 bg-white px-4 py-3 text-gray-950 dark:border-blue-800 dark:bg-gray-900 dark:text-gray-100">
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
        <p className="mt-3 rounded-md border border-amber-300 bg-white/70 px-3 py-2 text-xs text-amber-900 dark:bg-gray-900/60 dark:text-amber-100">
          {errorMessage || result?.error?.message}
        </p>
      )}

      {result?.status === 'succeeded' && (
        <p className="mt-3 text-xs leading-5">
          {liveOfferVerified
            ? t('supplement_live_offer_ready', 'Предложение продавца найдено. Наличие повторно проверится при покупке.')
            : t('supplement_confirmation_before_payment', 'Товар можно добавить в корзину. Наличие и итоговая цена будут подтверждены до оплаты.')}
        </p>
      )}
    </div>
  )
}
