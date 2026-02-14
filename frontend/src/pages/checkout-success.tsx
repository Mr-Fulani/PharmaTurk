// TODO: Функционал чеков временно отключен. Будет доработан позже.
// Включает: формирование чека, отправку по email, интеграцию с админкой.
import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useEffect, useMemo, useState } from 'react'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'

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
  subtotal_amount: string
  shipping_amount: string
  discount_amount: string
  total_amount: string
  currency: string
  contact_name: string
  contact_phone: string
  contact_email?: string
  shipping_address_text?: string
  payment_method?: string
  payment_status?: string
  promo_code?: { code: string } | null
  items: OrderItem[]
}

interface ReceiptItem extends OrderItem {}

interface OrderReceipt {
  number: string
  status: string
  issued_at: string
  currency: string
  items: ReceiptItem[]
  seller: Record<string, string>
  customer: Record<string, string>
  shipping: Record<string, string>
  payment: Record<string, string>
  totals: {
    items: string
    shipping: string
    discount: string
    total: string
    currency: string
  }
  promo_code?: string | null
}

type SendState = 'idle' | 'sending' | 'success' | 'error'

export default function CheckoutSuccessPage({ orderNumber }: { orderNumber?: string | null }) {
  const router = useRouter()
  const { t } = useTranslation('common')
  const number = useMemo(
    () => (orderNumber || (router.query?.number as string) || '').toString().trim(),
    [orderNumber, router.query]
  )

  const [order, setOrder] = useState<Order | null>(null)
  const [receipt, setReceipt] = useState<OrderReceipt | null>(null)
  const [loading, setLoading] = useState(Boolean(number))
  const [error, setError] = useState<string | null>(null)
  const [isAuthError, setIsAuthError] = useState(false)
  const [sendEmail, setSendEmail] = useState('')
  const [sendState, setSendState] = useState<SendState>('idle')
  const [sendMessage, setSendMessage] = useState('')

  // Восстановление языка при возврате с внешней оплаты (crypto): ?locale=ru → /ru/checkout-success
  useEffect(() => {
    const qLocale = (router.query?.locale as string)?.toLowerCase()
    if (qLocale === 'ru' && router.locale !== 'ru') {
      const num = (router.query?.number as string) || ''
      router.replace(`/ru/checkout-success?number=${encodeURIComponent(num)}`)
      return
    }
    if (qLocale === 'en' && router.locale !== 'en') {
      const num = (router.query?.number as string) || ''
      router.replace(`/checkout-success?number=${encodeURIComponent(num)}`)
      return
    }
  }, [router.query?.locale, router.locale, router])

  useEffect(() => {
    if (!number) {
      setLoading(false)
      return
    }

    let active = true
    const fetchData = async () => {
      setLoading(true)
      setError(null)
      setIsAuthError(false)
      try {
        const orderRes = await api.get(`/orders/orders/by-number/${number}`)
        if (!active) return
        setOrder(orderRes.data)
        setSendEmail(orderRes.data?.contact_email || orderRes.data?.user?.email || '')
      } catch (err: any) {
        if (!active) return
        const status = err?.response?.status
        const detail = err?.response?.data?.detail || t('order_success_send_error')
        setIsAuthError(status === 401)
        setError(status === 401 ? t('order_success_login_required', 'Войдите в аккаунт, чтобы увидеть заказ') : detail)
      }
      try {
        const receiptRes = await api.get(`/orders/orders/receipt/${number}`)
        if (!active) return
        setReceipt(receiptRes.data)
      } catch {
        // Чек опционален — заказ уже загружен
      } finally {
        if (active) setLoading(false)
      }
    }
    fetchData()
    return () => {
      active = false
    }
  }, [number, t])

  const totals = useMemo(() => {
    if (!receipt) return null
    return [
      { label: t('order_success_subtotal'), value: receipt.totals.items },
      { label: t('order_success_shipping_cost'), value: receipt.totals.shipping },
      { label: t('order_success_discount'), value: `-${receipt.totals.discount}` }
    ]
  }, [receipt, t])

  // TODO: Функционал чеков временно отключен. Будет доработан позже.
  const handlePrintReceipt = () => {
    if (!receipt) return
    const html = buildReceiptDocument(receipt)
    const printWindow = window.open('', '_blank', 'width=800,height=1000')
    if (!printWindow) return
    printWindow.document.write(html)
    printWindow.document.close()
    printWindow.focus()
    printWindow.print()
  }

  // TODO: Функционал чеков временно отключен. Будет доработан позже.
  const handleSendReceipt = async () => {
    if (!number || !sendEmail || sendState === 'sending') return
    setSendState('sending')
    setSendMessage('')
    try {
      const res = await api.post(`/orders/orders/send-receipt/${number}`, { email: sendEmail })
      setSendState('success')
      setSendMessage(res.data?.detail || t('order_success_send_success', { email: sendEmail }))
    } catch (err: any) {
      setSendState('error')
      setSendMessage(err?.response?.data?.detail || t('order_success_send_error'))
    }
  }

  return (
    <>
      <Head>
        <title>{t('order_success_page_title')} — PharmaTurk</title>
      </Head>
      <main className="min-h-screen bg-gradient-to-b from-violet-50/60 via-white to-white py-12">
        <div className="mx-auto w-full max-w-6xl px-4">
          {!number && (
            <div className="rounded-2xl border border-rose-100 bg-white/80 p-6 text-center shadow-sm">
              <p className="text-lg font-medium text-rose-600">{t('order_success_no_number')}</p>
              <div className="mt-4 flex flex-wrap justify-center gap-3">
                <Link
                  href="/profile"
                  className="rounded-full bg-violet-600 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-600/30 hover:bg-violet-700"
                >
                  {t('order_success_actions_view_orders')}
                </Link>
                <Link
                  href="/"
                  className="rounded-full border border-violet-200 px-5 py-2 text-sm font-semibold text-violet-700 hover:bg-violet-50"
                >
                  {t('order_success_actions_continue')}
                </Link>
              </div>
            </div>
          )}

          {loading && number && (
            <div className="mt-6 rounded-3xl border border-violet-100 bg-white p-10 text-center shadow-xl shadow-violet-100/60">
              <p className="text-base text-gray-500">{t('order_success_loading')}</p>
            </div>
          )}

          {error && !loading && (
            <div className="mt-6 rounded-2xl border border-rose-200 bg-rose-50/80 p-6 text-rose-700">
              <p>{error}</p>
              <div className="mt-4 flex flex-wrap gap-3">
                {isAuthError && (
                  <Link
                    href={`/auth?next=${encodeURIComponent(`/checkout-success?number=${number}`)}`}
                    className="rounded-full bg-violet-600 px-5 py-2 text-sm font-semibold text-white hover:bg-violet-700"
                  >
                    {t('order_success_actions_login', 'Войти')}
                  </Link>
                )}
                <Link
                  href="/profile"
                  className="rounded-full border border-violet-200 px-5 py-2 text-sm font-semibold text-violet-700 hover:bg-violet-50"
                >
                  {t('order_success_actions_view_orders', 'Мои заказы')}
                </Link>
                <Link
                  href="/"
                  className="rounded-full border border-gray-200 px-5 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-50"
                >
                  {t('order_success_actions_continue', 'Продолжить покупки')}
                </Link>
              </div>
            </div>
          )}

          {!loading && number && (
            <div className="mt-8 grid gap-8 lg:grid-cols-[1.15fr,0.85fr]">
              <section className="rounded-3xl border border-violet-100 bg-white/90 p-8 shadow-2xl shadow-violet-100/70 backdrop-blur">
                <div className="flex items-start gap-4">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-600">
                    <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-semibold uppercase tracking-widest text-emerald-600">
                      {t('order_success_subheading')}
                    </p>
                    <h1 className="mt-2 text-3xl font-black text-gray-900 sm:text-4xl">
                      {t('order_success_heading')}
                    </h1>
                    <p className="mt-3 max-w-2xl text-base text-gray-500">
                      {t('order_success_lead', { number })}
                    </p>
                  </div>
                </div>

                {order && (
                  <div className="mt-8 grid gap-4 md:grid-cols-2">
                    <StatisticCard
                      label={t('order_success_number')}
                      value={`#${order.number}`}
                      accent="from-violet-500/10 to-violet-100/40"
                    />
                    <StatisticCard
                      label={t('order_success_status')}
                      value={t(`order_status_${order.status}`, { defaultValue: order.status })}
                      accent="from-emerald-500/10 to-emerald-100/40"
                    />
                    <StatisticCard
                      label={t('order_success_payment_method')}
                      value={order.payment_method || '—'}
                      accent="from-blue-500/10 to-blue-100/40"
                    />
                    <StatisticCard
                      label={t('order_success_total')}
                      value={`${order.total_amount} ${order.currency}`}
                      accent="from-amber-500/10 to-amber-100/40"
                    />
                  </div>
                )}

                <div className="mt-10 flex flex-wrap gap-3">
                  <button
                    onClick={handlePrintReceipt}
                    disabled={!receipt}
                    className="inline-flex items-center gap-2 rounded-full bg-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-600/30 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 3H8v4h8V3z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 7H5a2 2 0 00-2 2v7h4v5h10v-5h4V9a2 2 0 00-2-2h-1" />
                    </svg>
                    {t('order_success_actions_download')}
                  </button>
                  <Link
                    href="/profile"
                    className="inline-flex items-center gap-2 rounded-full border border-violet-200 px-5 py-3 text-sm font-semibold text-violet-700 transition hover:bg-violet-50"
                  >
                    {t('order_success_actions_view_orders')}
                  </Link>
                  <Link
                    href="/"
                    className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-5 py-3 text-sm font-semibold text-gray-600 transition hover:bg-gray-50"
                  >
                    {t('order_success_actions_continue')}
                  </Link>
                </div>

                <div className="mt-10 rounded-2xl border border-violet-100 bg-violet-50/70 p-6">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm font-semibold uppercase tracking-[0.3em] text-violet-500">
                        {t('order_success_send_receipt_title')}
                      </p>
                      <p className="text-sm text-violet-700/80">{t('order_success_download_hint')}</p>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                    <input
                      type="email"
                      value={sendEmail}
                      onChange={(e) => setSendEmail(e.target.value)}
                      placeholder={t('order_success_send_receipt_placeholder') ?? ''}
                      className="flex-1 rounded-2xl border border-violet-200 bg-white/70 px-4 py-3 text-sm text-gray-700 outline-none ring-violet-500/40 focus:border-violet-500 focus:ring-2"
                    />
                    <button
                      onClick={handleSendReceipt}
                      disabled={!sendEmail || sendState === 'sending'}
                      className="rounded-2xl bg-violet-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-500/40 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {sendState === 'sending' ? t('order_success_send_receipt_sending') : t('order_success_send_button')}
                    </button>
                  </div>
                  {sendMessage && (
                    <p
                      className={`mt-3 text-sm ${
                        sendState === 'success' ? 'text-emerald-600' : 'text-rose-600'
                      }`}
                    >
                      {sendMessage}
                    </p>
                  )}
                </div>
              </section>

              <aside className="space-y-6">
                <div className="rounded-3xl border border-gray-100 bg-white/90 p-6 shadow-xl shadow-gray-100/70">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-gray-400">
                        {t('order_success_receipt_title')}
                      </p>
                      <h2 className="mt-1 text-xl font-semibold text-gray-900">{t('order_success_receipt_description')}</h2>
                    </div>
                    <span className="rounded-full bg-gray-900/5 px-3 py-1 text-xs font-semibold text-gray-600">
                      #{order?.number}
                    </span>
                  </div>

                  <div className="mt-6 space-y-4">
                    {(receipt?.items ?? []).map((item) => (
                      <div key={item.id} className="flex items-center justify-between rounded-2xl border border-gray-100 px-4 py-3">
                        <div>
                          <p className="font-semibold text-gray-900">{item.product_name}</p>
                          <p className="text-xs text-gray-500">
                            {t('order_success_qty', { defaultValue: '×{{count}}', count: item.quantity })}
                          </p>
                        </div>
                        <p className="text-sm font-semibold text-gray-900">
                          {item.total} {item.currency}
                        </p>
                      </div>
                    ))}
                  </div>

                  {totals && (
                    <div className="mt-6 space-y-2 border-t border-gray-100 pt-4 text-sm text-gray-600">
                      {totals.map(({ label, value }) => (
                        <div className="flex justify-between" key={label}>
                          <span>{label}</span>
                          <span>{value} {receipt?.totals.currency}</span>
                        </div>
                      ))}
                      <div className="flex items-center justify-between border-t border-gray-100 pt-4 text-base font-semibold text-gray-900">
                        <span>{t('order_success_total')}</span>
                        <span>{receipt?.totals.total} {receipt?.totals.currency}</span>
                      </div>
                    </div>
                  )}

                  {receipt?.promo_code && (
                    <div className="mt-6 rounded-2xl border border-dashed border-violet-200 bg-violet-50/60 px-4 py-3 text-sm text-violet-700">
                      {t('order_success_promo_code')}: <strong>{receipt.promo_code}</strong>
                    </div>
                  )}
                </div>

                <div className="rounded-3xl border border-gray-100 bg-white/80 p-6 shadow-lg shadow-gray-100/60">
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-gray-400">
                    {t('order_success_shipping')}
                  </p>
                  <h3 className="mt-2 text-lg font-semibold text-gray-900">{order?.contact_name}</h3>
                  <p className="text-sm text-gray-500">{order?.contact_phone}</p>
                  <p className="mt-3 text-sm text-gray-700">{order?.shipping_address_text}</p>
                </div>
              </aside>
            </div>
          )}
        </div>
      </main>
    </>
  )
}

function StatisticCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className={`rounded-2xl border border-gray-100 bg-gradient-to-br ${accent} p-4`}>
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <p className="mt-2 text-xl font-semibold text-gray-900">{value}</p>
    </div>
  )
}

// TODO: Функционал чеков временно отключен. Будет доработан позже.
function buildReceiptDocument(receipt: OrderReceipt) {
  const formatter = (value: string) => `${value} ${receipt.totals.currency}`
  const rows = receipt.items
    .map(
      (item) =>
        `<tr><td>${item.product_name}</td><td>${item.quantity}</td><td>${formatter(item.price)}</td><td>${formatter(
          item.total
        )}</td></tr>`
    )
    .join('')

  return `
    <!DOCTYPE html>
    <html lang="ru">
      <head>
        <meta charSet="utf-8" />
        <title>Receipt #${receipt.number}</title>
        <style>
          body { font-family: -apple-system,BlinkMacSystemFont,'Inter','Segoe UI',sans-serif; background:#f4f3ff; padding:40px; color:#1f1f35; }
          .card { max-width:800px; margin:0 auto; background:#fff; border-radius:32px; padding:40px; box-shadow:0 20px 60px rgba(31,31,53,.1); }
          h1 { margin:0 0 24px; font-size:28px; }
          table { width:100%; border-collapse:collapse; margin-top:24px; }
          th { text-align:left; font-size:12px; letter-spacing:0.3em; text-transform:uppercase; color:#8b8ca5; }
          td { border-top:1px solid #f1f1fb; padding:12px 0; }
          tfoot td { font-weight:700; font-size:18px; border:none; }
        </style>
      </head>
      <body>
        <div class="card">
          <h1>Чек заказа №${receipt.number}</h1>
          <p>Выдан: ${new Date(receipt.issued_at).toLocaleString()}</p>
          <table>
            <thead><tr><th>Товар</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr></thead>
            <tbody>${rows}</tbody>
            <tfoot>
              <tr><td colspan="3">Итого</td><td>${formatter(receipt.totals.total)}</td></tr>
            </tfoot>
          </table>
        </div>
      </body>
    </html>
  `
}

export async function getServerSideProps({ locale, query }: { locale?: string; query?: Record<string, string> }) {
  return {
    props: {
      ...(await serverSideTranslations(locale ?? 'ru', ['common'])),
      orderNumber: query?.number || null,
    },
  }
}
