import Head from 'next/head'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import api from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { useCartStore } from '../store/cart'

interface Cart {
  promo_code?: { code: string } | null
}

export default function CheckoutPage({ initialCart }: { initialCart?: Cart }) {
  console.log('CheckoutPage component mounted')
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const { refresh: refreshCart, setItemsCount } = useCartStore()
  const { t } = useTranslation('common')
  const [cart, setCart] = useState<Cart | null>(initialCart || null)
  const [contactName, setContactName] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [shippingAddressText, setShippingAddressText] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('cod')
  const [submitting, setSubmitting] = useState(false)

  // Загружаем корзину при монтировании
  useEffect(() => {
    const loadCart = async () => {
      try {
        const res = await api.get('/orders/cart')
        setCart(res.data)
      } catch (error) {
        console.error('Failed to load cart:', error)
      }
    }
    loadCart()
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    console.log('Starting checkout submission')
    setSubmitting(true)
    try {
      const body = new URLSearchParams()
      body.set('contact_name', contactName)
      body.set('contact_phone', contactPhone)
      if (contactEmail) body.set('contact_email', contactEmail)
      if (shippingAddressText) body.set('shipping_address_text', shippingAddressText)
      if (paymentMethod) body.set('payment_method', paymentMethod)
      // Передаем промокод из корзины, если он есть
      if (cart?.promo_code?.code) {
        body.set('promo_code', cart.promo_code.code)
      }
      const res = await api.post('/orders/orders/create-from-cart', body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      const orderNumber = res.data?.number
      console.log('Order created successfully:', orderNumber)
      // Сразу обнуляем счетчик корзины
      console.log('Setting items count to 0')
      setItemsCount(0)
      // Обновляем корзину в фоне для синхронизации
      console.log('Refreshing cart')
      await refreshCart()
      // Дополнительная проверка через небольшую задержку
      setTimeout(() => {
        console.log('Double-checking cart state')
        refreshCart()
      }, 100)
      router.push(orderNumber ? `/checkout-success?number=${encodeURIComponent(orderNumber)}` : '/checkout-success')
      } catch (err: any) {
      console.error('Checkout submission failed:', err)
      const status = err?.response?.status
      if (status === 401) {
        alert(t('login_required_to_checkout', 'Для оформления заказа необходимо войти'))
          router.push('/auth?next=/checkout')
        return
      }
      const detail = err?.response?.data?.detail || err?.message || t('checkout_error_generic', 'Ошибка оформления заказа')
      alert(String(detail))
      console.error('Checkout error details:', { status, data: err?.response?.data, message: err?.message })
    } finally {
      console.log('Checkout submission finished, submitting:', submitting)
      setSubmitting(false)
    }
  }

  useEffect(() => {
    console.log('CheckoutPage useEffect: authLoading =', authLoading, 'user =', user ? 'authenticated' : 'not authenticated')
    if (!authLoading && !user) {
      console.log('Redirecting to auth page due to no user')
      router.push('/auth?next=/checkout')
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
            <button 
              type="submit" 
              disabled={submitting} 
              style={{ padding: '8px 14px' }}
              onClick={() => console.log('Submit button clicked, submitting:', submitting)}
            >
              {submitting ? t('checkout_submitting', 'Отправка...') : t('checkout_submit', 'Оформить заказ')}
            </button>
          </div>
        </form>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  const { req, res: serverRes, locale } = ctx
  let initialCart = null
  
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const cookieHeader: string = req.headers.cookie || ''
    const cartSessionMatch = cookieHeader.match(/(?:^|;\s*)cart_session=([^;]+)/)
    let cartSession = cartSessionMatch ? cartSessionMatch[1] : ''
    const accessMatch = cookieHeader.match(/(?:^|;\s*)access=([^;]+)/)
    const accessToken = accessMatch ? accessMatch[1] : ''

    if (!cartSession) {
      cartSession = Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2)
      if (serverRes && typeof serverRes.setHeader === 'function') {
        serverRes.setHeader('Set-Cookie', `cart_session=${cartSession}; Path=/; SameSite=Lax`)
      }
    }

    const apiRes = await fetch(`${base}/api/orders/cart`, {
      headers: {
        cookie: cookieHeader,
        'Accept-Language': locale || 'en',
        ...(cartSession ? { 'X-Cart-Session': cartSession } : {}),
        ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {})
      }
    })
    if (apiRes.ok) {
      initialCart = await apiRes.json()
    }
  } catch (e) {
    console.error('Failed to load cart in checkout:', e)
  }

  return {
    props: {
      ...(await serverSideTranslations(locale ?? 'ru', ['common'])),
      initialCart: initialCart || null
    }
  }
}



