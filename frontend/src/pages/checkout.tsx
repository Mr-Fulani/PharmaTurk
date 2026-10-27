import Head from 'next/head'
import { useRouter } from 'next/router'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { SITE_NAME } from '../lib/siteMeta'
import { formatMoney } from '../lib/price'
import Link from 'next/link'
import api, { getSingleFlight } from '../lib/api'
import {
  applyImageFallback,
  isVideoUrl,
  replaceFailedVideoWithFallback,
  resolveMediaUrl,
} from '../lib/media'
import { useAuth } from '../context/AuthContext'
import { useCartStore } from '../store/cart'
import { useTheme } from '../context/ThemeContext'
import { getLocalizedProductName } from '../lib/i18n'
import {
  getCartIssueCopy,
  getCartVerificationError,
  isBlockingCartItem,
  isSupplierConfirmationPending,
} from '../lib/cartVerification'
import { useReducedMotion } from 'framer-motion'
import AnimatedOrderButton, { OrderButtonState } from '../components/AnimatedOrderButton'
import type { Cart } from '../types/cart'
import { gtmBeginCheckout, gtmGenerateLead, type GtmEcommerceItem } from '../lib/gtm'
import { ONLINE_PAYMENTS_ENABLED } from '../lib/payments'
import ContactChannelPicker, { isUsernameChannel } from '../components/ContactChannelPicker'
import { defaultCurrencyForLocale } from '../lib/requestCurrency'

interface Address {
  id: number
  address_type: 'home' | 'work' | 'other'
  contact_name: string
  contact_phone: string
  country: string
  region?: string
  city: string
  postal_code?: string
  street: string
  house: string
  apartment?: string
  entrance?: string
  floor?: string
  intercom?: string
  comment?: string
  is_default: boolean
}


type CheckoutField = 'contact_name' | 'contact_phone' | 'contact_email' | 'contact_channel' | 'contact_username'
const CHECKOUT_FIELDS: CheckoutField[] = ['contact_name', 'contact_phone', 'contact_email', 'contact_channel', 'contact_username']
const PHONE_DIGITS_RE = /^\+?\d{9,15}$/
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const fieldInputClass = (hasError: boolean) =>
  `mt-1 block w-full rounded-md border px-3 py-2 shadow-sm focus:outline-none focus:ring-1 ${hasError
    ? 'border-[var(--danger)] bg-[var(--danger-soft)] focus:border-[var(--danger)] focus:ring-[var(--danger)]'
    : 'border-gray-300 focus:border-violet-500 focus:ring-violet-500'}`

function toGtmItems(cart: Cart): GtmEcommerceItem[] {
  return cart.items.map((item) => ({
    item_id: item.product,
    item_name: item.product_name || item.product_slug || String(item.product),
    price: Number(item.price) || undefined,
    quantity: item.quantity,
  }))
}

export default function CheckoutPage({ initialCart }: { initialCart?: Cart }) {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const { refresh: refreshCart, setCartSummary, setItemsCount } = useCartStore()
  const { t, i18n } = useTranslation('common')
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const prefersReducedMotion = useReducedMotion()
  const [cart, setCart] = useState<Cart | null>(initialCart || null)
  const [addresses, setAddresses] = useState<Address[]>([])
  const [selectedAddressId, setSelectedAddressId] = useState<number | null>(null)
  const [useSavedAddress, setUseSavedAddress] = useState(false)
  const [contactName, setContactName] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [shippingAddressText, setShippingAddressText] = useState('')
  const [shippingMethod, setShippingMethod] = useState<'ground' | 'air' | 'sea'>('ground')
  const [paymentMethod, setPaymentMethod] = useState(ONLINE_PAYMENTS_ENABLED ? 'cod' : 'manager')
  const [contactChannel, setContactChannel] = useState('')
  const [contactUsername, setContactUsername] = useState('')
  const usernameChannel = isUsernameChannel(contactChannel)
  const emailRequired = contactChannel === 'email'
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<CheckoutField, string>>>({})
  const [formError, setFormError] = useState('')
  const formRef = useRef<HTMLFormElement>(null)
  const clearFieldError = (...fields: CheckoutField[]) =>
    setFieldErrors((prev) => {
      if (!fields.some((f) => prev[f])) return prev
      const next = { ...prev }
      fields.forEach((f) => delete next[f])
      return next
    })
  const scrollToFirstError = () => {
    requestAnimationFrame(() => {
      const el = formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"], [data-form-error]')
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      if (el instanceof HTMLInputElement) el.focus({ preventScroll: true })
    })
  }
  const [submitting, setSubmitting] = useState(false)
  const cryptoIdempotencyKeyRef = useRef<string | null>(null)
  const [orderButtonState, setOrderButtonState] = useState<OrderButtonState>('idle')
  const [loadingAddresses, setLoadingAddresses] = useState(true)
  const [showAddressForm, setShowAddressForm] = useState(false)
  const [saveAddress, setSaveAddress] = useState(false)
  const [addressFormData, setAddressFormData] = useState({
    address_type: 'home' as 'home' | 'work' | 'other',
    contact_name: '',
    contact_phone: '',
    country: '',
    region: '',
    city: '',
    postal_code: '',
    street: '',
    house: '',
    apartment: '',
    entrance: '',
    floor: '',
    intercom: '',
    comment: '',
    is_default: false,
  })

  // Загружаем корзину и адреса при монтировании
  useEffect(() => {
    const loadData = async () => {
      try {
        const [cartRes, addressesRes] = await Promise.all([
          getSingleFlight('/orders/cart'),
          getSingleFlight('/users/addresses').catch(() => ({ data: [] }))
        ])
        setCart(cartRes.data)
        setCartSummary(cartRes.data)
        if (cartRes.data?.items?.length) {
          const loadedCart = cartRes.data as Cart
          gtmBeginCheckout(
            toGtmItems(loadedCart),
            Number(loadedCart.final_amount ?? loadedCart.total_amount) || 0,
            loadedCart.currency,
          )
        }
        setAddresses(addressesRes.data || [])

        // Автоматически выбираем адрес по умолчанию
        const defaultAddress = addressesRes.data?.find((addr: Address) => addr.is_default)
        if (defaultAddress) {
          setSelectedAddressId(defaultAddress.id)
          setUseSavedAddress(true)
          setContactName(defaultAddress.contact_name)
          setContactPhone(defaultAddress.contact_phone)
          setShippingAddressText(
            `${defaultAddress.country}, ${defaultAddress.city}, ${defaultAddress.street} ${defaultAddress.house}${defaultAddress.apartment ? `, кв. ${defaultAddress.apartment}` : ''}`
          )
        }
      } catch (error) {
        console.error('Failed to load data:', error)
      } finally {
        setLoadingAddresses(false)
      }
    }
    loadData()
  }, [setCartSummary])

  // Обновляем контактные данные при загрузке профиля пользователя
  useEffect(() => {
    if (user) {
      if (!selectedAddressId) {
        const fullName = `${(user as any).first_name || ''} ${(user as any).last_name || ''}`.trim()
        if (fullName && !contactName) setContactName(fullName)
        if ((user as any).phone_number && !contactPhone) setContactPhone((user as any).phone_number)
      }
      if (!contactEmail) setContactEmail(user.email || '')
    }
  }, [user, selectedAddressId, contactName, contactPhone, contactEmail])

  const handleAddressSelect = (address: Address) => {
    setSelectedAddressId(address.id)
    setUseSavedAddress(true)
    setContactName(address.contact_name)
    setContactPhone(address.contact_phone)
    setShippingAddressText(
      `${address.country}, ${address.city}, ${address.street} ${address.house}${address.apartment ? `, кв. ${address.apartment}` : ''}`
    )
  }

  const handleUseManualAddress = () => {
    setUseSavedAddress(false)
    setSelectedAddressId(null)
    setShowAddressForm(true)
    // Заполняем форму данными из контактной информации, если они уже введены
    setAddressFormData({
      address_type: 'home',
      contact_name: contactName || '',
      contact_phone: contactPhone || '',
      country: '',
      region: '',
      city: '',
      postal_code: '',
      street: '',
      house: '',
      apartment: '',
      entrance: '',
      floor: '',
      intercom: '',
      comment: '',
      is_default: addresses.length === 0,
    })
  }

  const handleCancelAddressForm = () => {
    setShowAddressForm(false)
    if (addresses.length > 0) {
      setUseSavedAddress(true)
      const defaultAddress = addresses.find(addr => addr.is_default) || addresses[0]
      if (defaultAddress) {
        handleAddressSelect(defaultAddress)
      }
    }
  }

  const handleSaveAddressFromForm = async () => {
    if (saveAddress) {
      try {
        await api.post('/users/addresses', addressFormData)
        const response = await getSingleFlight('/users/addresses')
        setAddresses(response.data || [])
      } catch (error) {
        console.error('Failed to save address:', error)
      }
    }
    // Формируем текстовый адрес для отправки
    const addressText = `${addressFormData.country}, ${addressFormData.city}, ${addressFormData.street} ${addressFormData.house}${addressFormData.apartment ? `, кв. ${addressFormData.apartment}` : ''}`
    setShippingAddressText(addressText)
    setContactName(addressFormData.contact_name)
    setContactPhone(addressFormData.contact_phone)
    setShowAddressForm(false)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setFormError('')
    if (!cart || cart.items.length === 0) {
      router.push('/cart')
      return
    }
    if (cart.has_blocking_issues || cart.items.some(isBlockingCartItem)) {
      setFormError(t('cart_checkout_blocked', 'Сначала подтвердите изменения или удалите недоступные позиции.'))
      scrollToFirstError()
      return
    }

    // Ошибки показываем у полей, а не всплывающими окнами
    const errors: Partial<Record<CheckoutField, string>> = {}
    if (!contactName.trim()) errors.contact_name = t('field_required', 'Заполните это поле')
    const phoneDigits = contactPhone.replace(/[\s()-]/g, '')
    if (!phoneDigits) errors.contact_phone = t('field_required', 'Заполните это поле')
    else if (!PHONE_DIGITS_RE.test(phoneDigits)) errors.contact_phone = t('phone_invalid', 'Укажите номер в формате +79991234567')
    if (!contactChannel) errors.contact_channel = t('checkout_contact_channel_required', 'Выберите, как с вами связаться')
    if (emailRequired && !contactEmail.trim()) {
      errors.contact_email = t('checkout_email_required_for_channel', 'Укажите email: вы выбрали связь по email')
    } else if (contactEmail.trim() && !EMAIL_RE.test(contactEmail.trim())) {
      errors.contact_email = t('email_invalid', 'Проверьте адрес email')
    }
    setFieldErrors(errors)
    if (Object.keys(errors).length) {
      scrollToFirstError()
      return
    }

    const animationStartedAt = Date.now()
    let orderCreated = false
    setSubmitting(true)
    setOrderButtonState('processing')
    try {
      const body = new URLSearchParams()
      body.set('contact_name', contactName)
      body.set('contact_phone', contactPhone)
      if (contactEmail) body.set('contact_email', contactEmail)
      body.set('contact_channel', contactChannel)
      if (usernameChannel && contactUsername.trim()) body.set('contact_username', contactUsername.trim())
      if (shippingAddressText) body.set('shipping_address_text', shippingAddressText)
      if (shippingMethod) body.set('shipping_method', shippingMethod)
      if (paymentMethod) body.set('payment_method', paymentMethod)
      if (useSavedAddress && selectedAddressId) {
        body.set('shipping_address', String(selectedAddressId))
      }
      // Передаем промокод из корзины, если он есть
      if (cart?.promo_code?.code) {
        body.set('promo_code', cart.promo_code.code)
      }
      // Язык для редиректа после оплаты (crypto) — чтобы не сбрасывался при возврате
      body.set('locale', (router.locale as string) || 'en')
      const headers: Record<string, string> = {
        'Content-Type': 'application/x-www-form-urlencoded',
      }
      // Заявка сохраняется в валюте, в которой клиент видел суммы на этой странице
      if (cart?.currency) headers['X-Currency'] = cart.currency
      if (paymentMethod === 'crypto') {
        if (!cryptoIdempotencyKeyRef.current) {
          cryptoIdempotencyKeyRef.current =
            globalThis.crypto?.randomUUID?.() ||
            `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
        }
        headers['Idempotency-Key'] = cryptoIdempotencyKeyRef.current
      }
      const res = await api.post('/orders/orders/create-from-cart', body, { headers })
      const orderNumber = res.data?.number
      if (paymentMethod === 'crypto') cryptoIdempotencyKeyRef.current = null
      if (orderNumber && cart) {
        const orderValue = Number(res.data?.total_amount) || 0
        const orderCurrency = res.data?.currency || cart.currency
        gtmGenerateLead({
          source: 'order',
          value: orderValue,
          currency: orderCurrency,
          transactionId: String(orderNumber),
          paymentMethod,
        })
      }
      setItemsCount(0)
      await refreshCart()

      const minimumAnimationDuration = prefersReducedMotion ? 0 : 7000
      const remainingAnimationTime = Math.max(
        0,
        minimumAnimationDuration - (Date.now() - animationStartedAt)
      )
      if (remainingAnimationTime) {
        await new Promise((resolve) => setTimeout(resolve, remainingAnimationTime))
      }

      orderCreated = true
      setOrderButtonState('success')
      if (!prefersReducedMotion) {
        await new Promise((resolve) => setTimeout(resolve, 1000))
      }

      if (paymentMethod === 'crypto' && orderNumber) {
        const invoiceUrl = res.data?.payment_data?.invoice_url
        if (invoiceUrl) {
          window.location.href = invoiceUrl
        } else {
          router.push(`/checkout-crypto?number=${encodeURIComponent(orderNumber)}`)
        }
      } else {
        const currencyQuery = cart?.currency ? `&currency=${encodeURIComponent(cart.currency)}` : ''
        router.push(orderNumber ? `/checkout-success?number=${encodeURIComponent(orderNumber)}${currencyQuery}` : '/checkout-success')
      }
    } catch (err: any) {
      const status = err?.response?.status
      if (paymentMethod === 'crypto' && status && status < 500) {
        cryptoIdempotencyKeyRef.current = null
      }
      if (status === 401) {
        router.push('/auth?next=/checkout')
        return
      }
      const responseCart = err?.response?.data
      if (Array.isArray(responseCart?.items)) {
        setCart(responseCart)
        setCartSummary(responseCart)
      }
      const conflict = getCartVerificationError(err)
      const copy = getCartIssueCopy(conflict?.code)
      const detail = conflict?.code
        ? responseCart?.has_blocking_issues
          ? t(
              'cart_checkout_blocked',
              'Сначала подтвердите изменения или удалите недоступные позиции.',
            )
          : t(copy.key, copy.fallback)
        : responseCart?.detail || err?.message || t('checkout_error_generic', 'Ошибка оформления заказа')
      // Ошибки сервера по полям контактов — к своим полям, остальное — плашкой над кнопкой
      const serverFieldErrors: Partial<Record<CheckoutField, string>> = {}
      if (!conflict?.code && responseCart && typeof responseCart === 'object') {
        CHECKOUT_FIELDS.forEach((field) => {
          const value = responseCart[field]
          if (value) serverFieldErrors[field] = Array.isArray(value) ? String(value[0]) : String(value)
        })
      }
      if (Object.keys(serverFieldErrors).length) {
        setFieldErrors(serverFieldErrors)
      } else {
        setFormError(String(detail))
      }
      scrollToFirstError()
    } finally {
      if (!orderCreated) {
        setOrderButtonState('idle')
      }
      setSubmitting(false)
    }
  }

  const hasBlockingIssues = Boolean(
    cart?.has_blocking_issues || cart?.items.some(isBlockingCartItem),
  )
  const hasPendingConfirmation = Boolean(
    cart?.items.some(isSupplierConfirmationPending),
  )

  if (!cart || cart.items.length === 0) {
    return (
      <>
              <Head><title>{`${t('checkout_page_title', 'Оформление заказа')} — ${SITE_NAME}`}</title><meta name="robots" content="noindex, nofollow" /></Head>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-12 text-center">
            <h3 className="text-lg font-semibold text-gray-900">{t('cart_empty', 'Корзина пуста')}</h3>
            <p className="mt-2 text-sm text-gray-600">{t('cart_empty_description', 'Добавьте товары в корзину, чтобы продолжить покупки')}</p>
            <div className="mt-6">
              <Link href="/" className="inline-block rounded-md bg-[var(--accent)] px-6 py-3 text-sm font-medium text-white hover:bg-[var(--accent-strong)] transition-colors">
                {t('cart_continue_shopping', 'Продолжить покупки')}
              </Link>
            </div>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
            <Head><title>{`${t('checkout_page_title', 'Оформление заказа')} — ${SITE_NAME}`}</title><meta name="robots" content="noindex, nofollow" /></Head>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">{t('checkout_title', 'Оформление заказа')}</h1>
          {!authLoading && !user && (
            <p className="mt-2 text-sm text-gray-600">
              {t('checkout_guest_hint', 'Регистрация не нужна: оставьте имя и телефон — менеджер свяжется и подтвердит цену.')}{' '}
              <Link href="/auth?next=/checkout" className="font-medium text-[var(--accent-strong)] underline">
                {t('checkout_guest_login', 'Войти, чтобы видеть статус в профиле')}
              </Link>
            </p>
          )}
        </div>

        {hasBlockingIssues && (
          <div
            className="mb-6 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-950"
            role="alert"
          >
            <p className="font-semibold">
              {hasPendingConfirmation
                ? t('cart_confirmation_pending_title', 'Некоторые товары ожидают подтверждения')
                : t('cart_verification_title', 'Некоторые товары требуют вашего внимания')}
            </p>
            <p className="mt-1 text-sm">
              {hasPendingConfirmation
                ? t(
                    'cart_confirmation_checkout_blocked',
                    'Оформление станет доступно после подтверждения наличия и итоговой цены.',
                  )
                : t(
                    'cart_checkout_blocked',
                    'Сначала подтвердите изменения или удалите недоступные позиции.',
                  )}
            </p>
            <Link
              href="/cart"
              className="mt-3 inline-flex rounded-md border border-amber-500 px-3 py-1.5 text-sm font-medium text-amber-950 hover:bg-amber-100"
            >
              {t('cart_resolve_issues', 'Вернуться в корзину и исправить')}
            </Link>
          </div>
        )}

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          {/* Форма оформления */}
          <div className="lg:col-span-2">
            <form ref={formRef} onSubmit={submit} noValidate className="space-y-6 checkout-form">
              {/* Выбор адреса доставки */}
              {addresses.length > 0 && (
                <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('profile_addresses', 'Адреса доставки')}</h2>
                  <div className="space-y-3">
                    {addresses.map((address) => (
                      <div
                        key={address.id}
                        className={`rounded-lg border-2 p-4 cursor-pointer transition-all ${selectedAddressId === address.id && useSavedAddress
                          ? (isDark ? 'border-violet-500 bg-violet-50' : 'border-[var(--accent)] bg-[var(--surface)]')
                          : 'border-gray-200 hover:border-gray-300'
                          }`}
                        onClick={() => handleAddressSelect(address)}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-900">{address.contact_name}</span>
                              {address.is_default && (
                                <span className="text-xs bg-[var(--surface)] text-[var(--text-strong)] px-2 py-1 rounded checkout-default-badge">
                                  {t('profile_address_default', 'По умолчанию')}
                                </span>
                              )}
                            </div>
                            <p className="text-sm text-gray-600 mt-1">
                              {address.country}, {address.city}, {address.street} {address.house}
                              {address.apartment && `, кв. ${address.apartment}`}
                            </p>
                            <p className="text-sm text-gray-500 mt-1">{address.contact_phone}</p>
                          </div>
                          {selectedAddressId === address.id && useSavedAddress && (
                            <svg className="h-5 w-5 text-[var(--accent)]" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                          )}
                        </div>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={handleUseManualAddress}
                      className="w-full text-sm text-main hover-text-warm font-medium py-2"
                    >
                      {t('checkout_use_manual_address', 'Указать адрес вручную')}
                    </button>
                  </div>
                </div>
              )}

              {/* Контактная информация */}
              <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('checkout_contact_info', 'Контактная информация')}</h2>
                <div className="space-y-4">
                  <label className="block">
                    <span className="text-sm font-medium text-gray-700">{t('checkout_recipient_name', 'Имя получателя')} *</span>
                    <input
                      type="text"
                      value={contactName}
                      onChange={(e) => { setContactName(e.target.value); clearFieldError('contact_name') }}
                      autoComplete="name"
                      aria-invalid={fieldErrors.contact_name ? true : undefined}
                      className={fieldInputClass(Boolean(fieldErrors.contact_name))}
                    />
                    {fieldErrors.contact_name && <span className="mt-1 block text-xs font-medium text-[var(--danger)]">{fieldErrors.contact_name}</span>}
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-gray-700">{t('checkout_phone', 'Телефон')} *</span>
                    <input
                      type="tel"
                      value={contactPhone}
                      onChange={(e) => { setContactPhone(e.target.value); clearFieldError('contact_phone') }}
                      autoComplete="tel"
                      placeholder="+79991234567"
                      aria-invalid={fieldErrors.contact_phone ? true : undefined}
                      className={fieldInputClass(Boolean(fieldErrors.contact_phone))}
                    />
                    {fieldErrors.contact_phone && <span className="mt-1 block text-xs font-medium text-[var(--danger)]">{fieldErrors.contact_phone}</span>}
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-gray-700">
                      {emailRequired ? `${t('checkout_email', 'Email')} *` : t('checkout_email_optional', 'Email (необязательно)')}
                    </span>
                    <input
                      type="email"
                      value={contactEmail}
                      onChange={(e) => { setContactEmail(e.target.value); clearFieldError('contact_email') }}
                      autoComplete="email"
                      aria-invalid={fieldErrors.contact_email ? true : undefined}
                      className={fieldInputClass(Boolean(fieldErrors.contact_email))}
                    />
                    {fieldErrors.contact_email && <span className="mt-1 block text-xs font-medium text-[var(--danger)]">{fieldErrors.contact_email}</span>}
                  </label>
                  <ContactChannelPicker
                    channel={contactChannel}
                    onChannelChange={(value) => { setContactChannel(value); clearFieldError('contact_channel', 'contact_email') }}
                    username={contactUsername}
                    onUsernameChange={(value) => { setContactUsername(value); clearFieldError('contact_username') }}
                    error={fieldErrors.contact_channel || fieldErrors.contact_username}
                    inputClassName={fieldInputClass(Boolean(fieldErrors.contact_username))}
                  />
                </div>
              </div>

              {/* Адрес доставки - форма */}
              {showAddressForm && (!useSavedAddress || addresses.length === 0) && (
                <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-gray-900">{t('checkout_shipping_address', 'Адрес доставки')}</h2>
                    <button
                      type="button"
                      onClick={handleCancelAddressForm}
                      className="text-sm text-gray-500 hover:text-gray-700"
                    >
                      {t('profile_cancel', 'Отмена')}
                    </button>
                  </div>

                  {/* Предложение сохранить адрес */}
                  {user && (
                    <div className="mb-4 p-3 bg-[var(--surface)] rounded-lg border border-[var(--border)] checkout-address-save">
                      <label className="flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={saveAddress}
                          onChange={(e) => setSaveAddress(e.target.checked)}
                          className="h-4 w-4 text-[var(--accent)] focus:ring-[var(--accent)] border-gray-300 rounded"
                        />
                        <span className="ml-2 text-sm text-gray-700">
                          {addresses.length > 0
                            ? t('checkout_save_address_as_second', 'Сохранить как второй адрес')
                            : t('checkout_save_address', 'Сохранить адрес в профиле')}
                        </span>
                      </label>
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Тип адреса */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_type')} <span className="text-[var(--text-strong)]">*</span>
                      </label>
                      <select
                        value={addressFormData.address_type}
                        onChange={(e) =>
                          setAddressFormData({
                            ...addressFormData,
                            address_type: e.target.value as 'home' | 'work' | 'other',
                          })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                      >
                        <option value="home">{t('profile_address_type_home')}</option>
                        <option value="work">{t('profile_address_type_work')}</option>
                        <option value="other">{t('profile_address_type_other')}</option>
                      </select>
                    </div>

                    {/* Адрес по умолчанию */}
                    {saveAddress && (
                      <div className="flex items-center">
                        <input
                          type="checkbox"
                          id="is_default"
                          checked={addressFormData.is_default}
                          onChange={(e) =>
                            setAddressFormData({ ...addressFormData, is_default: e.target.checked })
                          }
                          className="h-4 w-4 text-[var(--accent)] focus:ring-[var(--accent)] border-gray-300 rounded"
                        />
                        <label htmlFor="is_default" className="ml-2 text-sm text-gray-700">
                          {t('profile_address_set_default')}
                        </label>
                      </div>
                    )}

                    {/* Имя получателя */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_contact_name')} <span className="text-[var(--text-strong)]">*</span>
                      </label>
                      <input
                        type="text"
                        value={addressFormData.contact_name}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, contact_name: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                        required
                      />
                    </div>

                    {/* Телефон получателя */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_contact_phone')} <span className="text-[var(--text-strong)]">*</span>
                      </label>
                      <input
                        type="tel"
                        value={addressFormData.contact_phone}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, contact_phone: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                        required
                      />
                    </div>

                    {/* Страна */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_country')} <span className="text-[var(--text-strong)]">*</span>
                      </label>
                      <input
                        type="text"
                        value={addressFormData.country}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, country: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                        required
                      />
                    </div>

                    {/* Регион */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_region')}
                      </label>
                      <input
                        type="text"
                        value={addressFormData.region}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, region: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>

                    {/* Город */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_city')} <span className="text-[var(--text-strong)]">*</span>
                      </label>
                      <input
                        type="text"
                        value={addressFormData.city}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, city: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                        required
                      />
                    </div>

                    {/* Почтовый индекс */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_postal_code')}
                      </label>
                      <input
                        type="text"
                        value={addressFormData.postal_code}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, postal_code: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>

                    {/* Улица */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_street')} <span className="text-[var(--text-strong)]">*</span>
                      </label>
                      <input
                        type="text"
                        value={addressFormData.street}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, street: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                        required
                      />
                    </div>

                    {/* Дом */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_house')} <span className="text-[var(--text-strong)]">*</span>
                      </label>
                      <input
                        type="text"
                        value={addressFormData.house}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, house: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                        required
                      />
                    </div>

                    {/* Квартира */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_apartment')}
                      </label>
                      <input
                        type="text"
                        value={addressFormData.apartment}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, apartment: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>

                    {/* Подъезд */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_entrance')}
                      </label>
                      <input
                        type="text"
                        value={addressFormData.entrance}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, entrance: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>

                    {/* Этаж */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_floor')}
                      </label>
                      <input
                        type="text"
                        value={addressFormData.floor}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, floor: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>

                    {/* Домофон */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_intercom')}
                      </label>
                      <input
                        type="text"
                        value={addressFormData.intercom}
                        onChange={(e) =>
                          setAddressFormData({ ...addressFormData, intercom: e.target.value })
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>
                  </div>

                  {/* Комментарий */}
                  <div className="mt-4">
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      {t('profile_address_comment')}
                    </label>
                    <textarea
                      value={addressFormData.comment}
                      onChange={(e) =>
                        setAddressFormData({ ...addressFormData, comment: e.target.value })
                      }
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                    />
                  </div>

                  {/* Кнопка применения адреса */}
                  <button
                    type="button"
                    onClick={handleSaveAddressFromForm}
                    className="mt-4 w-full bg-[var(--accent)] text-white px-4 py-2 rounded-md hover:bg-[var(--accent-strong)] transition-colors"
                  >
                    {t('checkout_use_this_address', 'Использовать этот адрес')}
                  </button>
                </div>
              )}

              {/* Простой текстовый адрес (если форма не показана) */}
              {!showAddressForm && (!useSavedAddress || addresses.length === 0) && (
                <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('checkout_shipping_address', 'Адрес доставки')}</h2>
                  <label className="block">
                    <textarea
                      value={shippingAddressText}
                      onChange={(e) => setShippingAddressText(e.target.value)}
                      rows={4}
                      placeholder={t('checkout_address_placeholder', 'Страна, город, улица, дом, квартира')}
                      className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={handleUseManualAddress}
                    className="mt-3 text-sm text-main hover-text-warm font-medium"
                  >
                    {t('checkout_fill_address_form', 'Заполнить подробный адрес')}
                  </button>
                </div>
              )}

              {/* Способ доставки */}
              <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('checkout_shipping_method', 'Способ доставки')}</h2>
                {cart?.shipping_requires_quote && (
                  <div
                    className={`mb-4 rounded-lg border p-3 text-sm ${isDark ? 'border-amber-600/50 bg-amber-950/40 text-amber-100' : 'border-amber-200 bg-amber-50 text-amber-900'}`}
                    role="status"
                  >
                    {t(
                      'checkout_furniture_shipping_notice',
                      'В заказе есть мебель: стоимость доставки рассчитывается индивидуально после оформления. Сумма к оплате ниже — без доставки; менеджер свяжется с вами.',
                    )}
                  </div>
                )}
                <div className="space-y-3">
                  <label className={`flex items-center p-4 rounded-lg border-2 cursor-pointer transition-all ${shippingMethod === 'ground'
                    ? (isDark ? 'border-violet-500 bg-violet-50' : 'border-[var(--accent)] bg-[var(--surface)]')
                    : 'border-gray-200 hover:bg-gray-50'
                    }`}>
                    <input
                      type="radio"
                      name="shipping"
                      value="ground"
                      checked={shippingMethod === 'ground'}
                      onChange={(e) => setShippingMethod(e.target.value as 'ground')}
                      className="h-4 w-4 text-[var(--accent)] focus:ring-[var(--accent)]"
                    />
                    <div className="ml-3 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-900">{t('shipping_ground', 'Наземная доставка')}</span>
                        <span className="font-semibold text-gray-900">
                          {cart?.shipping_requires_quote
                            ? t('shipping_on_request', 'По запросу')
                            : cart?.shipping_options?.ground !== undefined
                              ? `+${formatMoney(cart.shipping_options.ground, cart.currency || 'USD', i18n.language)} ${cart.currency || 'USD'}`
                              : ''}
                        </span>
                      </div>
                      <p className="text-sm text-gray-500 mt-1">{t('shipping_ground_description', 'Доставка автотранспортом. Оптимальный выбор.')}</p>
                    </div>
                  </label>

                  <label className={`flex items-center p-4 rounded-lg border-2 cursor-pointer transition-all ${shippingMethod === 'air'
                    ? (isDark ? 'border-violet-500 bg-violet-50' : 'border-[var(--accent)] bg-[var(--surface)]')
                    : 'border-gray-200 hover:bg-gray-50'
                    }`}>
                    <input
                      type="radio"
                      name="shipping"
                      value="air"
                      checked={shippingMethod === 'air'}
                      onChange={(e) => setShippingMethod(e.target.value as 'air')}
                      className="h-4 w-4 text-[var(--accent)] focus:ring-[var(--accent)]"
                    />
                    <div className="ml-3 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-900">{t('shipping_air', 'Авиадоставка')}</span>
                        <span className="font-semibold text-gray-900">
                          {cart?.shipping_requires_quote
                            ? t('shipping_on_request', 'По запросу')
                            : cart?.shipping_options?.air !== undefined
                              ? `+${formatMoney(cart.shipping_options.air, cart.currency || 'USD', i18n.language)} ${cart.currency || 'USD'}`
                              : ''}
                        </span>
                      </div>
                      <p className="text-sm text-gray-500 mt-1">{t('shipping_air_description', 'Ускоренная воздушная доставка.')}</p>
                    </div>
                  </label>

                  <label className={`flex items-center p-4 rounded-lg border-2 cursor-pointer transition-all ${shippingMethod === 'sea'
                    ? (isDark ? 'border-violet-500 bg-violet-50' : 'border-[var(--accent)] bg-[var(--surface)]')
                    : 'border-gray-200 hover:bg-gray-50'
                    }`}>
                    <input
                      type="radio"
                      name="shipping"
                      value="sea"
                      checked={shippingMethod === 'sea'}
                      onChange={(e) => setShippingMethod(e.target.value as 'sea')}
                      className="h-4 w-4 text-[var(--accent)] focus:ring-[var(--accent)]"
                    />
                    <div className="ml-3 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-900">{t('shipping_sea', 'Морская доставка')}</span>
                        <span className="font-semibold text-gray-900">
                          {cart?.shipping_requires_quote
                            ? t('shipping_on_request', 'По запросу')
                            : cart?.shipping_options?.sea !== undefined
                              ? `+${formatMoney(cart.shipping_options.sea, cart.currency || 'USD', i18n.language)} ${cart.currency || 'USD'}`
                              : ''}
                        </span>
                      </div>
                      <p className="text-sm text-gray-500 mt-1">{t('shipping_sea_description', 'Доставка морем для крупногабаритных грузов.')}</p>
                    </div>
                  </label>
                </div>
              </div>

              {!ONLINE_PAYMENTS_ENABLED && (
                <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                  <h2 className="text-lg font-semibold text-gray-900 mb-2">{t('checkout_payment_method', 'Способ оплаты')}</h2>
                  <p className="text-sm text-gray-600">
                    {t('checkout_manager_payment_info', 'Оплата на сайте не требуется. После отправки заявки менеджер свяжется с вами выбранным способом, подтвердит наличие и итоговую сумму и согласует удобный способ оплаты.')}
                  </p>
                </div>
              )}

              {/* Способ оплаты (онлайн) — выключен, пока каждый заказ ведёт менеджер */}
              {ONLINE_PAYMENTS_ENABLED && (
              <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('checkout_payment_method', 'Способ оплаты')}</h2>
                <div className="space-y-3">
                  {/* Наложенный платёж */}
                  <label className={`flex items-center p-4 rounded-lg border-2 cursor-pointer transition-all ${paymentMethod === 'cod'
                    ? (isDark ? 'border-violet-500 bg-violet-50' : 'border-[var(--accent)] bg-[var(--surface)]')
                    : 'border-gray-200 hover:bg-gray-50'
                    }`}>
                    <input
                      type="radio"
                      name="payment"
                      value="cod"
                      checked={paymentMethod === 'cod'}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="h-4 w-4 text-[var(--accent)] focus:ring-[var(--accent)]"
                    />
                    <div className="ml-3 flex-1">
                      <div className="flex items-center gap-2">
                        <svg className="h-5 w-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
                        </svg>
                        <span className="font-medium text-gray-900">{t('payment_cod', 'Наложенный платёж')}</span>
                      </div>
                      <p className="text-sm text-gray-500 mt-1">{t('payment_cod_description', 'Оплата при получении товара')}</p>
                    </div>
                  </label>

                  {/* Криптовалюта */}
                  <label className={`flex items-center p-4 rounded-lg border-2 cursor-pointer transition-all ${paymentMethod === 'crypto'
                    ? 'border-violet-500 bg-violet-50'
                    : 'border-gray-200 hover:bg-gray-50'
                    }`}>
                    <input
                      type="radio"
                      name="payment"
                      value="crypto"
                      checked={paymentMethod === 'crypto'}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="h-4 w-4 text-violet-600 focus:ring-violet-500"
                    />
                    <div className="ml-3 flex-1">
                      <div className="flex items-center gap-2">
                        <svg className="h-5 w-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span className="font-medium text-gray-900">{t('payment_crypto', 'Криптовалюта')}</span>
                      </div>
                      <p className="text-sm text-gray-500 mt-1">{t('payment_crypto_description', 'Оплата криптовалютой (Bitcoin, Ethereum, USDT и др.)')}</p>
                    </div>
                  </label>
                </div>

                {/* Информация о крипто-оплате: адрес выдаётся на следующей странице */}
                {paymentMethod === 'crypto' && (
                  <div className="mt-6 p-4 rounded-lg bg-gradient-to-br from-amber-50 to-orange-50 border-2 border-amber-200">
                    <div className="flex items-start gap-2">
                      <svg className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <div className="text-xs text-amber-900">
                        <p className="font-medium mb-1">{t('payment_crypto_info_title', 'Как это работает:')}</p>
                        <ul className="list-disc list-inside space-y-1 text-amber-800">
                          <li>{t('payment_crypto_info_1', 'После подтверждения заказа вы получите адрес для оплаты')}</li>
                          <li>{t('payment_crypto_info_2', 'Отправьте точную сумму на указанный адрес')}</li>
                          <li>{t('payment_crypto_info_3', 'После подтверждения транзакции заказ будет обработан')}</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              )}

              {formError && (
                <p
                  data-form-error
                  role="alert"
                  className="rounded-lg border border-[var(--danger)] bg-[var(--danger-soft)] px-4 py-3 text-sm text-[var(--danger)]"
                >
                  {formError}
                </p>
              )}

              <AnimatedOrderButton
                state={orderButtonState}
                disabled={submitting || hasBlockingIssues}
                defaultLabel={ONLINE_PAYMENTS_ENABLED ? t('checkout_submit', 'Оформить заказ') : t('checkout_submit_request', 'Отправить заявку')}
                processingLabel={t('checkout_submitting', 'Отправка...')}
                successLabel={ONLINE_PAYMENTS_ENABLED ? t('checkout_order_placed', 'Заказ оформлен') : t('checkout_request_sent', 'Заявка отправлена')}
              />
            </form>
          </div>

          {/* Итоговая информация */}
          <div className="lg:col-span-1">
            <div className="sticky top-20 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-bold text-gray-900 mb-4">{t('checkout_order_summary', 'Итоги заказа')}</h2>

              {/* Товары */}
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
                  {t('checkout_items', 'Товары')} ({cart.payable_items_count ?? cart.items_count})
                </h3>
                {hasBlockingIssues && (
                  <p className="mb-3 text-xs text-amber-800">
                    {t('cart_items_saved_total', 'Всего сохранено в корзине: {{count}}', {
                      count: cart.items_count,
                    })}
                  </p>
                )}
                <div className="space-y-3 max-h-80 overflow-y-auto pr-2">
                  {cart.items.map((item) => {
                    const blocked = isBlockingCartItem(item)
                    const issueCode = item.issues?.[0]?.code || item.verification_issues?.[0]
                    const issueCopy = getCartIssueCopy(issueCode)
                    const resolvedImage = item.product_image_url ? resolveMediaUrl(item.product_image_url) : null
                    const resolvedVideoUrl = item.product_video_url && isVideoUrl(item.product_video_url) ? resolveMediaUrl(item.product_video_url) : null
                    const showVideo = Boolean(resolvedVideoUrl)
                    const localizedName = getLocalizedProductName(
                      item.product_name || `Товар #${item.product}`,
                      t,
                      item.product_translations,
                      i18n.language
                    )
                    return (
                      <div
                        key={item.id}
                        className={`flex gap-3 rounded-lg border p-3 transition-colors ${
                          blocked
                            ? 'border-amber-300 bg-amber-50'
                            : 'border-gray-200 bg-gray-50 hover:bg-gray-100'
                        }`}
                      >
                        {showVideo ? (
                          <video
                            src={resolvedVideoUrl!}
                            poster={resolvedImage || undefined}
                            muted
                            loop
                            playsInline
                            autoPlay
                            preload="metadata"
                            className="w-20 h-20 object-cover rounded-lg flex-shrink-0 border border-gray-200"
                            onError={(event) => replaceFailedVideoWithFallback(event.currentTarget, localizedName)}
                          />
                        ) : item.product_image_url ? (
                          <img
                            src={resolveMediaUrl(item.product_image_url)}
                            alt={localizedName}
                            className="w-20 h-20 object-cover rounded-lg flex-shrink-0 border border-gray-200"
                            onError={(event) => applyImageFallback(event.currentTarget)}
                          />
                        ) : (
                          <div className="w-20 h-20 rounded-lg flex-shrink-0 bg-gray-200 border border-gray-300 flex items-center justify-center">
                            <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-gray-900 text-sm leading-tight mb-1 line-clamp-2">
                            {localizedName}
                          </p>
                          {issueCode && (
                            <p className={`mb-1 text-xs ${blocked ? 'text-amber-800' : 'text-blue-700'}`}>
                              {t(issueCopy.key, issueCopy.fallback)}
                            </p>
                          )}
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs text-gray-500 bg-gray-200 px-2 py-0.5 rounded">
                              {t('checkout_qty', 'Кол-во')}: {item.quantity}
                            </span>
                            <span className="text-xs text-gray-500">
                              {formatMoney(item.price, item.currency, i18n.language)} {item.currency} {t('checkout_per_item', 'за шт.')}
                            </span>
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0">
                          {blocked ? (
                            <p className="text-xs font-semibold text-amber-800">
                              {t('cart_not_included_in_total', 'Не включено в итог')}
                            </p>
                          ) : (
                            <p className="font-bold text-gray-900 text-sm">
                              {formatMoney(parseFloat(String(item.price)) * item.quantity, item.currency, i18n.language)} {item.currency}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="border-t-2 border-gray-300 pt-4 space-y-3">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>{t('cart_subtotal', 'Сумма товаров')}</span>
                  <span className="font-medium text-gray-900">
                    {formatMoney(cart.total_amount, cart.currency || 'USD', i18n.language)} {cart.currency || 'USD'}
                  </span>
                </div>
                {parseFloat(String(cart.discount_amount ?? '0')) > 0 ? (
                  <>
                    <div className="flex justify-between text-sm !text-red-600">
                      <span>{t('cart_discount', 'Скидка')}</span>
                      <span className="font-medium">
                        -{formatMoney(cart.discount_amount, cart.currency || 'USD', i18n.language)} {cart.currency || 'USD'}
                      </span>
                    </div>
                    {cart.promo_code && (
                      <div className="text-xs !text-red-600">
                        <div>
                          {t('promo_code_applied', 'Промокод')}: {cart.promo_code.code}
                        </div>
                        <div className="mt-0.5">
                          {cart.promo_code.discount_type === 'percent'
                            ? `${cart.promo_code.discount_value}%`
                            : `${cart.promo_code.discount_value} ${cart.currency || 'USD'}`}
                        </div>
                      </div>
                    )}
                  </>
                ) : null}
                <div className="flex justify-between text-sm text-gray-600 mt-2">
                  <span>{t('checkout_shipping_cost', 'Стоимость доставки')}</span>
                  <span className="font-medium text-gray-900">
                    {cart?.shipping_requires_quote
                      ? t('shipping_on_request', 'По запросу')
                      : `+${formatMoney(cart.shipping_options?.[shippingMethod] || 0, cart.currency || 'USD', i18n.language)} ${cart.currency || 'USD'}`}
                  </span>
                </div>
                <div className="border-t border-gray-200 pt-4 mt-4">
                  <div className="flex justify-between items-baseline">
                    <span className="text-lg font-semibold text-gray-900">{t('cart_total', 'Итого')}</span>
                    <span className="text-2xl font-bold text-violet-600">
                      {formatMoney(
                        parseFloat(String(cart.final_amount || cart.total_amount || '0')) +
                        (cart?.shipping_requires_quote ? 0 : cart.shipping_options?.[shippingMethod] || 0)
                      , cart.currency || 'USD', i18n.language)}{' '}
                      {cart.currency || 'USD'}
                    </span>
                  </div>
                </div>

                {cart.free_shipping_threshold != null &&
                  cart.free_shipping_threshold > 0 &&
                  !cart.shipping_requires_quote && (
                    <div
                      className={`mt-4 rounded-lg p-4 text-xs ${isDark ? 'bg-violet-950/40 text-violet-100' : 'bg-gray-50 text-gray-700'}`}
                    >
                      <p className="font-medium">{t('cart_delivery_info_title', 'Бесплатная доставка')}</p>
                      <p className="mt-1">
                        {t(
                          'cart_delivery_info_text',
                          'При заказе от {{minAmount}} {{currency}} (сумма товаров без доставки)',
                          {
                            minAmount: formatMoney(cart.free_shipping_threshold, cart.currency || 'USD', i18n.language),
                            currency: cart.currency || 'USD',
                          },
                        )}
                      </p>
                    </div>
                  )}
              </div>

              <Link
                href="/cart"
                className="mt-6 block text-center text-sm text-violet-600 hover:text-violet-700 font-medium"
              >
                ← {t('checkout_back_to_cart', 'Вернуться в корзину')}
              </Link>
            </div>
          </div>
        </div>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  const { req, res: serverRes, locale } = ctx
  let initialCart = null

  try {
    const { getInternalApiUrl } = await import('../lib/urls')
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

    const currencyMatch = cookieHeader.match(/(?:^|;\s*)currency=([^;]+)/)
    const currency = currencyMatch ? currencyMatch[1] : defaultCurrencyForLocale(locale)

    const apiRes = await fetch(getInternalApiUrl('orders/cart'), {
      headers: {
        cookie: cookieHeader,
        'Accept-Language': locale || 'en',
        ...(cartSession ? { 'X-Cart-Session': cartSession } : {}),
        ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {}),
        'X-Currency': currency
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
