import axios from 'axios'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'

import api from '../lib/api'
import {
  shouldPollMedicineMarketCheck,
  startMedicineMarketCheckSingleFlight,
} from '../lib/medicineMarketCheck'

type MedicineMarketCheck = {
  enabled: boolean
  status: 'not_requested' | 'pending' | 'running' | 'succeeded' | 'source_unavailable' | 'failed'
  price?: { amount: string; currency: string } | null
  last_success_at?: string | null
  is_stale: boolean
  error?: { code: string; message: string } | null
  poll_after_seconds?: number | null
}

type Props = {
  slug: string
  onPriceUpdated?: (price: { amount: string; currency: string }) => void
}

const MAX_POLL_ATTEMPTS = 65

export default function MedicinePriceCheck({ slug, onPriceUpdated }: Props) {
  const { t, i18n } = useTranslation('common')
  const [result, setResult] = useState<MedicineMarketCheck | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [starting, setStarting] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const requestGeneration = useRef(0)

  useEffect(() => {
    requestGeneration.current += 1
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = null
    setResult(null)
    setErrorMessage('')
    setStarting(false)
    return () => {
      requestGeneration.current += 1
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [slug])

  const acceptResult = (payload: MedicineMarketCheck) => {
    setResult(payload)
    if (payload.status === 'succeeded' && payload.price) {
      onPriceUpdated?.(payload.price)
    }
  }

  const schedulePoll = (
    payload: MedicineMarketCheck,
    generation: number,
    attempt: number,
  ): void => {
    if (!shouldPollMedicineMarketCheck(payload.status)) return
    if (attempt >= MAX_POLL_ATTEMPTS) {
      requestGeneration.current += 1
      setResult((current) => current ? { ...current, status: 'failed' } : current)
      setErrorMessage(t('medicine_market_check_timeout', 'Проверка занимает больше обычного. Попробуйте позже.'))
      return
    }
    const delay = Math.max(1, payload.poll_after_seconds || 2) * 1000
    timerRef.current = setTimeout(async () => {
      if (generation !== requestGeneration.current) return
      try {
        const response = await api.get<MedicineMarketCheck>(
          `/catalog/medicines/products/${encodeURIComponent(slug)}/market-check`,
        )
        if (generation !== requestGeneration.current) return
        acceptResult(response.data)
        schedulePoll(response.data, generation, attempt + 1)
      } catch {
        if (generation === requestGeneration.current) {
          requestGeneration.current += 1
          setResult((current) => current ? { ...current, status: 'failed' } : current)
          setErrorMessage(t('medicine_market_check_read_error', 'Не удалось получить результат проверки. Попробуйте позже.'))
        }
      }
    }, delay)
  }

  const startCheck = async () => {
    if (starting || shouldPollMedicineMarketCheck(result?.status)) return
    const generation = requestGeneration.current + 1
    requestGeneration.current = generation
    if (timerRef.current) clearTimeout(timerRef.current)
    setStarting(true)
    setErrorMessage('')
    try {
      const response = await startMedicineMarketCheckSingleFlight(
        slug,
        () => api.post<MedicineMarketCheck>(
          `/catalog/medicines/products/${encodeURIComponent(slug)}/market-check`,
        ),
      )
      if (generation !== requestGeneration.current) return
      acceptResult(response.data)
      schedulePoll(response.data, generation, 0)
    } catch (error) {
      if (generation !== requestGeneration.current) return
      if (axios.isAxiosError(error) && error.response?.data) {
        const payload = error.response.data as MedicineMarketCheck
        if (payload?.status && payload.status !== 'not_requested') {
          acceptResult(payload)
          if (shouldPollMedicineMarketCheck(payload.status)) {
            schedulePoll(payload, generation, 0)
          }
          return
        }
      }
      setErrorMessage(t('medicine_market_check_start_error', 'Не удалось запустить проверку цены. Попробуйте позже.'))
    } finally {
      if (generation === requestGeneration.current) setStarting(false)
    }
  }

  const active = starting || shouldPollMedicineMarketCheck(result?.status)
  const buttonLabel = (() => {
    if (starting || result?.status === 'pending') {
      return t('medicine_market_check_pending', 'Проверка поставлена в очередь…')
    }
    if (result?.status === 'running') {
      return t('medicine_market_check_running', 'Проверяем цену в первоисточнике…')
    }
    if (result?.status) {
      return t('medicine_market_check_retry', 'Обновить цену ещё раз')
    }
    return t('medicine_consult_button', 'Узнать актуальную цену')
  })()

  const checkedAt = result?.last_success_at
    ? new Intl.DateTimeFormat(i18n.language || 'ru', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(result.last_success_at))
    : ''

  return (
    <div aria-live="polite">
      <button
        type="button"
        onClick={startCheck}
        disabled={active}
        className="w-full rounded-md bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition-all duration-200 hover:bg-blue-700 disabled:cursor-wait disabled:opacity-70"
      >
        {buttonLabel}
      </button>

      {result?.price && (
        <div className={`mt-2 rounded-md border px-3 py-2 text-sm ${
          result.status === 'succeeded'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-100'
            : 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100'
        }`}>
          <span className="font-semibold">
            {result.status === 'succeeded'
              ? t('medicine_market_check_succeeded', 'Цена проверена')
              : t('medicine_market_reference_price', 'Последняя подтверждённая цена')}:
          </span>{' '}
          {result.price.amount} {result.price.currency}
          {checkedAt && (
            <span className="block pt-0.5 text-xs opacity-80">
              {t('medicine_market_checked_at', 'Проверено: {{date}}', { date: checkedAt })}
              {result.is_stale ? ` · ${t('medicine_market_price_stale', 'последняя успешно подтверждённая цена')}` : ''}
            </span>
          )}
        </div>
      )}

      {!errorMessage && result?.status === 'source_unavailable' && (
        <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100">
          {t('medicine_market_check_unavailable', 'Источник временно недоступен. Попробуйте позже.')}
        </p>
      )}

      {!errorMessage && result?.status === 'failed' && (
        <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100">
          {t('medicine_market_check_failed', 'Не удалось подтвердить актуальную цену. Попробуйте позже.')}
        </p>
      )}

      {errorMessage && (
        <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100">
          {errorMessage}
        </p>
      )}

      <p className="mt-2 text-xs leading-5 text-gray-500 dark:text-gray-400">
        {t('medicine_market_price_disclaimer', 'Цена носит информационный характер и не является публичной офертой.')}
      </p>
    </div>
  )
}
