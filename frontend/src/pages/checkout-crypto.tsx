import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'

const QR_URL = (text: string, size = 192) =>
  `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(text)}`

interface OrderItem {
  id: number
  product_name: string
  quantity: number
  price: string
  total: string
  currency: string
}

interface Order {
  id: number
  number: string
  status: string
  payment_method?: string
  payment_status?: string
  total_amount: string
  currency: string
  items: OrderItem[]
}

interface PaymentData {
  address: string
  qr_code: string
  amount: string
  amount_usd: string
  currency: string
  expires_at: string
  invoice_url?: string
}

const POLL_INTERVAL_MS = 12000
const DUMMY_ADDRESS = 'TDevWallet123456789012345678901'

export default function CheckoutCryptoPage({ orderNumber }: { orderNumber?: string | null }) {
  const router = useRouter()
  const { t } = useTranslation('common')
  const number = useMemo(
    () => (orderNumber || (router.query?.number as string) || '').toString().trim(),
    [orderNumber, router.query]
  )

  const [order, setOrder] = useState<Order | null>(null)
  const [paymentData, setPaymentData] = useState<PaymentData | null>(null)
  const [loading, setLoading] = useState(Boolean(number))
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const fetchOrder = useCallback(async () => {
    if (!number) return
    try {
      const res = await api.get<Order & { payment_data?: PaymentData }>(`/orders/orders/by-number/${number}`)
      if (res.data.payment_status === 'paid' || res.data.status === 'paid') {
        setOrder(res.data)
        setPaymentData(res.data.payment_data || null)
        setError(null)
        return
      }
      setOrder(res.data)
      if (res.data.payment_data) setPaymentData(res.data.payment_data)
      setError(null)
    } catch (err: any) {
      const detail = err?.response?.data?.detail || t('checkout_crypto_load_error', 'Не удалось загрузить заказ')
      setError(detail)
    } finally {
      setLoading(false)
    }
  }, [number, t])

  useEffect(() => {
    if (!number) {
      setLoading(false)
      return
    }
    fetchOrder()
  }, [number, fetchOrder])

  // Если есть ссылка на страницу CoinRemitter — сразу редирект туда (там адрес и QR)
  useEffect(() => {
    if (paymentData?.invoice_url) {
      window.location.href = paymentData.invoice_url
    }
  }, [paymentData?.invoice_url])

  useEffect(() => {
    if (!number || !order || order.payment_status === 'paid' || order.status === 'paid') return
    const id = setInterval(fetchOrder, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [number, order?.payment_status, order?.status, fetchOrder])

  // После отображения успеха — ждём 2.5 сек и редирект на страницу заказа
  const PAID_REDIRECT_DELAY_MS = 2500
  useEffect(() => {
    if (!(order?.payment_status === 'paid' || order?.status === 'paid') || !number) return
    const id = setTimeout(() => {
      const path = router.locale === 'ru' ? `/ru/checkout-success` : `/checkout-success`
      router.replace(`${path}?number=${encodeURIComponent(number)}`)
    }, PAID_REDIRECT_DELAY_MS)
    return () => clearTimeout(id)
  }, [order?.payment_status, order?.status, number, router])

  const copyAddress = () => {
    if (!paymentData?.address) return
    // Убираем пробелы, переносы и невидимые символы — кошельки их не принимают
    const clean = paymentData.address.replace(/\s+/g, '').replace(/[\u200B-\u200D\uFEFF]/g, '').trim()
    navigator.clipboard.writeText(clean).then(
      () => {
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      },
      () => {
        // Fallback: execCommand для старых браузеров/WebView
        const input = document.createElement('input')
        input.value = clean
        input.style.position = 'fixed'
        input.style.opacity = '0'
        document.body.appendChild(input)
        input.select()
        document.execCommand('copy')
        document.body.removeChild(input)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      }
    )
  }

  const expiresAt = paymentData?.expires_at ? new Date(paymentData.expires_at).getTime() : 0
  const [timeLeft, setTimeLeft] = useState('')
  useEffect(() => {
    if (!expiresAt) return
    const tick = () => {
      const now = Date.now()
      if (now >= expiresAt) {
        setTimeLeft(t('checkout_crypto_expired', 'Время истекло'))
        return
      }
      const s = Math.floor((expiresAt - now) / 1000)
      const m = Math.floor(s / 60)
      const sec = s % 60
      setTimeLeft(`${m}:${sec.toString().padStart(2, '0')}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [expiresAt, t])

  if (!number) {
    return (
      <>
        <Head><title>{t('checkout_crypto_pay_title', 'Оплата криптовалютой')}</title></Head>
        <main className="mx-auto max-w-2xl px-4 py-12 text-center">
          <p className="text-gray-600">{t('checkout_crypto_no_order', 'Укажите номер заказа')}</p>
          <Link href="/cart" className="mt-4 inline-block text-[var(--accent)] hover:underline">
            {t('cart_back_to_cart', 'В корзину')}
          </Link>
        </main>
      </>
    )
  }

  if (loading && !order) {
    return (
      <>
        <Head><title>{t('checkout_crypto_pay_title', 'Оплата криптовалютой')}</title></Head>
        <main className="mx-auto max-w-2xl px-4 py-12 text-center">
          <p className="text-gray-600">{t('loading', 'Загрузка...')}</p>
        </main>
      </>
    )
  }

  if (error) {
    return (
      <>
        <Head><title>{t('checkout_crypto_pay_title', 'Оплата криптовалютой')}</title></Head>
        <main className="mx-auto max-w-2xl px-4 py-12 text-center">
          <p className="text-red-600">{error}</p>
          <Link href="/checkout-success" className="mt-4 inline-block text-[var(--accent)] hover:underline">
            {t('checkout_back_to_cart', 'К заказу')}
          </Link>
        </main>
      </>
    )
  }

  if (order?.payment_status === 'paid' || order?.status === 'paid') {
    return (
      <>
        <Head><title>{t('checkout_crypto_paid', 'Оплачено')}</title></Head>
        <main className="mx-auto max-w-2xl px-4 py-12 text-center">
          <div className="rounded-xl border-2 border-green-200 bg-green-50 p-8">
            <p className="text-xl font-semibold text-green-700">{t('checkout_crypto_paid', 'Оплачено')}</p>
            <p className="mt-2 text-green-600">
              {t('checkout_crypto_redirecting', 'Переход на страницу заказа...')}
            </p>
            <Link href={`/checkout-success?number=${encodeURIComponent(number)}`} className="mt-6 inline-block text-[var(--accent)] hover:underline font-medium">
              {t('order_success_view_order', 'Перейти к заказу')}
            </Link>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <Head><title>{t('checkout_crypto_pay_title', 'Оплата криптовалютой')}</title></Head>
      <main className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          {t('checkout_crypto_pay_title', 'Оплата криптовалютой')}
        </h1>
        <p className="text-gray-600 mb-6">
          {t('checkout_crypto_instruction', 'Отправьте указанную сумму USDT на адрес ниже. После подтверждения транзакции заказ будет обработан.')}
        </p>

        {paymentData?.address === DUMMY_ADDRESS && (
          <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-800">
            <p className="font-medium">{t('checkout_crypto_dummy_warning_title', 'Режим тестирования')}</p>
            <p className="mt-1 text-sm">
              {t('checkout_crypto_dummy_warning', 'CoinRemitter не настроен или недоступен. Это тестовый адрес — не отправляйте реальные средства.')}
            </p>
          </div>
        )}

        {paymentData && (
          <div className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('checkout_crypto_amount', 'Сумма к оплате')}
              </label>
              <p className="text-xl font-semibold text-gray-900">
                {paymentData.amount} USDT
                {paymentData.amount_usd && (
                  <span className="text-gray-500 font-normal ml-2">≈ {paymentData.amount_usd} {paymentData.currency}</span>
                )}
              </p>
            </div>

            {paymentData.expires_at && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('checkout_crypto_expires', 'Время на оплату')}
                </label>
                <p className="text-lg font-mono text-gray-900">{timeLeft}</p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('checkout_crypto_address', 'Адрес для оплаты')}
              </label>
              {paymentData.address ? (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={paymentData.address}
                    className="flex-1 rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-sm font-mono"
                  />
                  <button
                    type="button"
                    onClick={copyAddress}
                    className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
                  >
                    {copied ? t('checkout_crypto_copied', 'Скопировано') : t('checkout_crypto_copy_address', 'Копировать')}
                  </button>
                </div>
              ) : paymentData.invoice_url ? (
                <p className="text-gray-600 text-sm">
                  {t('checkout_crypto_open_invoice_for_address', 'Откройте страницу оплаты по ссылке ниже, чтобы увидеть адрес и QR-код.')}
                </p>
              ) : (
                <p className="text-gray-500 text-sm">{t('checkout_crypto_address_unavailable', 'Адрес недоступен. Обратитесь в поддержку.')}</p>
              )}
            </div>

            <div className="flex justify-center">
              {(() => {
                const qrSrc =
                  paymentData.qr_code ||
                  (paymentData.address ? QR_URL(paymentData.address) : null) ||
                  (paymentData.invoice_url ? QR_URL(paymentData.invoice_url) : null)
                return qrSrc ? (
                  <img src={qrSrc} alt="QR для оплаты" className="h-48 w-48 rounded-lg border border-gray-200" />
                ) : (
                  <p className="text-gray-500 text-sm">{t('checkout_crypto_qr_unavailable', 'QR-код недоступен')}</p>
                )
              })()}
            </div>

            {paymentData.invoice_url && (
              <p className="text-sm text-gray-500">
                <a href={paymentData.invoice_url} target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] hover:underline">
                  {t('checkout_crypto_open_invoice', 'Открыть страницу оплаты')}
                </a>
              </p>
            )}
          </div>
        )}

        {order && !paymentData && (
          <p className="text-gray-500">{t('checkout_crypto_no_payment_data', 'Данные для оплаты недоступны. Обратитесь в поддержку.')}</p>
        )}

        <div className="mt-8">
          <Link href="/" className="text-[var(--accent)] hover:underline">{t('cart_continue_shopping', 'Продолжить покупки')}</Link>
        </div>
      </main>
    </>
  )
}

export async function getServerSideProps({ locale, query }: { locale?: string; query?: Record<string, string> }) {
  return {
    props: {
      ...(await serverSideTranslations(locale ?? 'ru', ['common'])),
      orderNumber: query?.number || null,
    },
  }
}
