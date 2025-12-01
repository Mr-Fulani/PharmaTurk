import Head from 'next/head'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import Link from 'next/link'
import api from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { useCartStore } from '../store/cart'

interface CartItem {
  id: number
  product: number
  product_name?: string
  product_slug?: string
  product_image_url?: string
  quantity: number
  price: string
  currency: string
}

interface PromoCode {
  id: number
  code: string
  discount_type?: string
  discount_value: string
  description?: string
}

interface Cart {
  id: number
  items: CartItem[]
  items_count: number
  total_amount: string
  discount_amount?: string
  final_amount?: string
  currency?: string
  promo_code?: PromoCode | null
}

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

export default function CheckoutPage({ initialCart }: { initialCart?: Cart }) {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const { refresh: refreshCart, setItemsCount } = useCartStore()
  const { t } = useTranslation('common')
  const [cart, setCart] = useState<Cart | null>(initialCart || null)
  const [addresses, setAddresses] = useState<Address[]>([])
  const [selectedAddressId, setSelectedAddressId] = useState<number | null>(null)
  const [useSavedAddress, setUseSavedAddress] = useState(false)
  const [contactName, setContactName] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [shippingAddressText, setShippingAddressText] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('cod')
  const [submitting, setSubmitting] = useState(false)
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
          api.get('/orders/cart'),
          api.get('/users/addresses').catch(() => ({ data: [] }))
        ])
        setCart(cartRes.data)
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
  }, [])

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
        const response = await api.get('/users/addresses')
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
    if (!cart || cart.items.length === 0) {
      alert(t('cart_empty', 'Корзина пуста'))
      router.push('/cart')
      return
    }
    
    setSubmitting(true)
    try {
      const body = new URLSearchParams()
      body.set('contact_name', contactName)
      body.set('contact_phone', contactPhone)
      if (contactEmail) body.set('contact_email', contactEmail)
      if (shippingAddressText) body.set('shipping_address_text', shippingAddressText)
      if (paymentMethod) body.set('payment_method', paymentMethod)
      if (useSavedAddress && selectedAddressId) {
        body.set('shipping_address', String(selectedAddressId))
      }
      // Передаем промокод из корзины, если он есть
      if (cart?.promo_code?.code) {
        body.set('promo_code', cart.promo_code.code)
      }
      const res = await api.post('/orders/orders/create-from-cart', body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      const orderNumber = res.data?.number
      setItemsCount(0)
      await refreshCart()
      router.push(orderNumber ? `/checkout-success?number=${encodeURIComponent(orderNumber)}` : '/checkout-success')
      } catch (err: any) {
      const status = err?.response?.status
      if (status === 401) {
        alert(t('login_required_to_checkout', 'Для оформления заказа необходимо войти'))
          router.push('/auth?next=/checkout')
        return
      }
      const detail = err?.response?.data?.detail || err?.message || t('checkout_error_generic', 'Ошибка оформления заказа')
      alert(String(detail))
    } finally {
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

  if (!cart || cart.items.length === 0) {
    return (
      <>
        <Head><title>{t('checkout_page_title', 'Оформление заказа — Turk-Export')}</title></Head>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-12 text-center">
            <h3 className="text-lg font-semibold text-gray-900">{t('cart_empty', 'Корзина пуста')}</h3>
            <p className="mt-2 text-sm text-gray-600">{t('cart_empty_description', 'Добавьте товары в корзину, чтобы продолжить покупки')}</p>
            <div className="mt-6">
              <Link href="/" className="inline-block rounded-md bg-violet-600 px-6 py-3 text-sm font-medium text-white hover:bg-violet-700 transition-colors">
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
      <Head><title>{t('checkout_page_title', 'Оформление заказа — Turk-Export')}</title></Head>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">{t('checkout_title', 'Оформление заказа')}</h1>
        </div>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          {/* Форма оформления */}
          <div className="lg:col-span-2">
            <form onSubmit={submit} className="space-y-6">
              {/* Выбор адреса доставки */}
              {addresses.length > 0 && (
                <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('profile_addresses', 'Адреса доставки')}</h2>
                  <div className="space-y-3">
                    {addresses.map((address) => (
                      <div
                        key={address.id}
                        className={`rounded-lg border-2 p-4 cursor-pointer transition-all ${
                          selectedAddressId === address.id && useSavedAddress
                            ? 'border-violet-500 bg-violet-50'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                        onClick={() => handleAddressSelect(address)}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-900">{address.contact_name}</span>
                              {address.is_default && (
                                <span className="text-xs bg-violet-100 text-violet-700 px-2 py-1 rounded">
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
                            <svg className="h-5 w-5 text-violet-600" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                          )}
                        </div>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={handleUseManualAddress}
                      className="w-full text-sm text-violet-600 hover:text-violet-700 font-medium py-2"
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
                      onChange={(e) => setContactName(e.target.value)}
                      required
                      className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-gray-700">{t('checkout_phone', 'Телефон')} *</span>
                    <input
                      type="tel"
                      value={contactPhone}
                      onChange={(e) => setContactPhone(e.target.value)}
                      required
                      className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                    />
          </label>
                  <label className="block">
                    <span className="text-sm font-medium text-gray-700">{t('checkout_email_optional', 'Email (необязательно)')}</span>
                    <input
                      type="email"
                      value={contactEmail}
                      onChange={(e) => setContactEmail(e.target.value)}
                      className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                    />
          </label>
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
                    <div className="mb-4 p-3 bg-violet-50 rounded-lg border border-violet-200">
                      <label className="flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={saveAddress}
                          onChange={(e) => setSaveAddress(e.target.checked)}
                          className="h-4 w-4 text-violet-600 focus:ring-violet-500 border-gray-300 rounded"
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
                        {t('profile_address_type')} <span className="text-red-500">*</span>
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
                          className="h-4 w-4 text-violet-600 focus:ring-violet-500 border-gray-300 rounded"
                        />
                        <label htmlFor="is_default" className="ml-2 text-sm text-gray-700">
                          {t('profile_address_set_default')}
                        </label>
                      </div>
                    )}

                    {/* Имя получателя */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('profile_address_contact_name')} <span className="text-red-500">*</span>
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
                        {t('profile_address_contact_phone')} <span className="text-red-500">*</span>
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
                        {t('profile_address_country')} <span className="text-red-500">*</span>
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
                        {t('profile_address_city')} <span className="text-red-500">*</span>
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
                        {t('profile_address_street')} <span className="text-red-500">*</span>
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
                        {t('profile_address_house')} <span className="text-red-500">*</span>
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
                    className="mt-4 w-full bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 transition-colors"
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
                    className="mt-3 text-sm text-violet-600 hover:text-violet-700 font-medium"
                  >
                    {t('checkout_fill_address_form', 'Заполнить подробный адрес')}
                  </button>
                </div>
              )}

              {/* Способ оплаты */}
              <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('checkout_payment_method', 'Способ оплаты')}</h2>
                <div className="space-y-3">
                  <label className="flex items-center p-4 rounded-lg border-2 cursor-pointer transition-all hover:bg-gray-50">
                    <input
                      type="radio"
                      name="payment"
                      value="cod"
                      checked={paymentMethod === 'cod'}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="h-4 w-4 text-violet-600 focus:ring-violet-500"
                    />
                    <div className="ml-3 flex-1">
                      <span className="font-medium text-gray-900">{t('payment_cod', 'Наложенный платёж')}</span>
                      <p className="text-sm text-gray-500">{t('payment_cod_description', 'Оплата при получении товара')}</p>
                    </div>
          </label>
                  <label className="flex items-center p-4 rounded-lg border-2 cursor-pointer transition-all hover:bg-gray-50">
                    <input
                      type="radio"
                      name="payment"
                      value="card"
                      checked={paymentMethod === 'card'}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="h-4 w-4 text-violet-600 focus:ring-violet-500"
                    />
                    <div className="ml-3 flex-1">
                      <span className="font-medium text-gray-900">{t('payment_card', 'Банковская карта')}</span>
                      <p className="text-sm text-gray-500">{t('payment_card_description', 'Оплата банковской картой онлайн')}</p>
                    </div>
          </label>
                </div>
              </div>

            <button 
              type="submit" 
              disabled={submitting} 
                className="w-full rounded-md bg-violet-600 px-6 py-3 text-base font-medium text-white hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? t('checkout_submitting', 'Отправка...') : t('checkout_submit', 'Оформить заказ')}
            </button>
            </form>
          </div>

          {/* Итоговая информация */}
          <div className="lg:col-span-1">
            <div className="sticky top-20 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-bold text-gray-900 mb-4">{t('checkout_order_summary', 'Итоги заказа')}</h2>

              {/* Товары */}
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
                  {t('checkout_items', 'Товары')} ({cart.items_count})
                </h3>
                <div className="space-y-3 max-h-80 overflow-y-auto pr-2">
                  {cart.items.map((item) => (
                    <div
                      key={item.id}
                      className="flex gap-3 p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors border border-gray-200"
                    >
                      {item.product_image_url ? (
                        <img
                          src={item.product_image_url}
                          alt={item.product_name}
                          className="w-20 h-20 object-cover rounded-lg flex-shrink-0 border border-gray-200"
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
                          {item.product_name}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-gray-500 bg-gray-200 px-2 py-0.5 rounded">
                            {t('checkout_qty', 'Кол-во')}: {item.quantity}
                          </span>
                          <span className="text-xs text-gray-500">
                            {item.price} {item.currency} {t('checkout_per_item', 'за шт.')}
                          </span>
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="font-bold text-gray-900 text-sm">
                          {(parseFloat(item.price) * item.quantity).toFixed(2)} {item.currency}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t-2 border-gray-300 pt-4 space-y-3">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>{t('cart_subtotal', 'Сумма товаров')}</span>
                  <span className="font-medium text-gray-900">
                    {cart.total_amount} {cart.currency || 'USD'}
                  </span>
                </div>
                {cart.discount_amount && parseFloat(cart.discount_amount) > 0 && (
                  <>
                    <div className="flex justify-between text-sm text-green-600">
                      <span>{t('cart_discount', 'Скидка')}</span>
                      <span className="font-medium">
                        -{cart.discount_amount} {cart.currency || 'USD'}
                      </span>
                    </div>
                    {cart.promo_code && (
                      <div className="text-xs text-gray-500">
                        {t('promo_code_applied', 'Промокод')}: {cart.promo_code.code}
                      </div>
                    )}
                  </>
                )}
                <div className="border-t border-gray-200 pt-4">
                  <div className="flex justify-between items-baseline">
                    <span className="text-lg font-semibold text-gray-900">{t('cart_total', 'Итого')}</span>
                    <span className="text-2xl font-bold text-violet-600">
                      {cart.final_amount || cart.total_amount} {cart.currency || 'USD'}
                    </span>
                  </div>
                </div>
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



