import Head from 'next/head'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import api from '../lib/api'
import { useAuth } from '../context/AuthContext'

export default function CheckoutPage() {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const { t } = useTranslation('common')
  const [contactName, setContactName] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [shippingAddressText, setShippingAddressText] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('cod')
  const [submitting, setSubmitting] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setSubmitting(true)
    try {
      const body = new URLSearchParams()
      body.set('contact_name', contactName)
      body.set('contact_phone', contactPhone)
      if (contactEmail) body.set('contact_email', contactEmail)
      if (shippingAddressText) body.set('shipping_address_text', shippingAddressText)
      if (paymentMethod) body.set('payment_method', paymentMethod)
      const res = await api.post('/orders/orders/create-from-cart', body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      const orderNumber = res.data?.number
      router.push(orderNumber ? `/checkout-success?number=${encodeURIComponent(orderNumber)}` : '/checkout-success')
      } catch (err: any) {
      const status = err?.response?.status
      if (status === 401) {
        alert(t('login_required_to_checkout', 'Для оформления заказа необходимо войти'))
          router.push('/auth/login?next=/checkout')
        return
      }
      const detail = err?.response?.data?.detail || err?.message || t('checkout_error_generic', 'Ошибка оформления заказа')
      alert(String(detail))
      // eslint-disable-next-line no-console
      console.error('Checkout error', status, err?.response?.data)
    } finally {
      setSubmitting(false)
    }
  }

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/auth/login?next=/checkout')
    }
  }, [user, authLoading, router])

  return (
    <>
      <Head><title>{t('checkout_page_title', 'Оформление заказа — Turk-Export')}</title></Head>
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
        <h1>{t('checkout_title', 'Оформление заказа')}</h1>
        <form onSubmit={submit} style={{ display: 'grid', gap: 12, marginTop: 12 }}>
          <label style={{ display: 'grid', gap: 6 }}>
            <span>{t('checkout_recipient_name', 'Имя получателя')}</span>
            <input value={contactName} onChange={(e)=>setContactName(e.target.value)} required />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span>{t('checkout_phone', 'Телефон')}</span>
            <input value={contactPhone} onChange={(e)=>setContactPhone(e.target.value)} required />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span>{t('checkout_email_optional', 'Email (необязательно)')}</span>
            <input type="email" value={contactEmail} onChange={(e)=>setContactEmail(e.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span>{t('checkout_shipping_address', 'Адрес доставки (текст)')}</span>
            <textarea value={shippingAddressText} onChange={(e)=>setShippingAddressText(e.target.value)} rows={4} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span>{t('checkout_payment_method', 'Способ оплаты')}</span>
            <select value={paymentMethod} onChange={(e)=>setPaymentMethod(e.target.value)}>
              <option value="cod">{t('payment_cod', 'Наложенный платёж')}</option>
              <option value="card">{t('payment_card', 'Банковская карта')}</option>
            </select>
          </label>
          <div>
            <button type="submit" disabled={submitting} style={{ padding: '8px 14px' }}>
              {submitting ? t('checkout_submitting', 'Отправка...') : t('checkout_submit', 'Оформить заказ')}
            </button>
          </div>
        </form>
      </main>
    </>
  )
}

export async function getServerSideProps({ locale }: { locale: string }) {
  return {
    props: {
      ...(await serverSideTranslations(locale ?? 'ru', ['common']))
    }
  }
}



