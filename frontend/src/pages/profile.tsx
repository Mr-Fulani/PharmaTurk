import Head from 'next/head'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import Link from 'next/link'
import Cookies from 'js-cookie'
import api from '../lib/api'
import { setPreferredCurrency } from '../lib/api'
import { resolveMediaUrl } from '../lib/media'
import { useAuth } from '../context/AuthContext'

interface OrderItem {
  id: number
  product?: number
  product_name: string
  product_slug?: string
  product_image_url?: string
  price: string
  quantity: number
  total: string
}

interface Order {
  id: number
  number: string
  status: string
  total_amount: string
  currency: string
  items: OrderItem[]
  created_at: string
  contact_name: string
  contact_phone: string
  shipping_address_text?: string
}

interface UserProfile {
  id: number
  user_email: string
  user_username: string
  phone_number?: string
  first_name?: string
  last_name?: string
  avatar?: string
  avatar_url?: string
  whatsapp_phone?: string
  telegram_username?: string
  total_orders?: number
  total_spent?: string
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
  is_active: boolean
  created_at: string
  updated_at: string
}

const ORDER_STATUS_MAP: Record<string, string> = {
  new: 'profile_order_status_new',
  pending_payment: 'profile_order_status_pending_payment',
  paid: 'profile_order_status_paid',
  processing: 'profile_order_status_processing',
  shipped: 'profile_order_status_shipped',
  delivered: 'profile_order_status_delivered',
  cancelled: 'profile_order_status_cancelled',
}

export default function ProfilePage() {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const { t } = useTranslation('common')
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [orders, setOrders] = useState<Order[]>([])
  const [addresses, setAddresses] = useState<Address[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [avatarFile, setAvatarFile] = useState<File | null>(null)
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null)
  const [currency, setCurrency] = useState<string>('RUB')

  const totalSpentFromOrders = orders.reduce((acc, o) => {
    const v = parseFloat(String(o.total_amount || '0'))
    return acc + (Number.isFinite(v) ? v : 0)
  }, 0)

  // Состояние для адресов
  const [editingAddress, setEditingAddress] = useState<Address | null>(null)
  const [showAddressForm, setShowAddressForm] = useState(false)
  const [addressSaving, setAddressSaving] = useState(false)
  
  // Состояние для управления отображением заказов
  const [showAllOrders, setShowAllOrders] = useState(false)

  // Форма редактирования
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    phone_number: '',
    whatsapp_phone: '',
    telegram_username: '',
  })

  // Форма адреса
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

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace('/auth?next=/profile')
      return
    }

    if (user) {
      loadProfile()
      loadOrders()
      loadAddresses()
    }
  }, [user, authLoading, router])

  useEffect(() => {
    if (user?.currency) {
      setCurrency(user.currency)
      return
    }
    const savedCurrency = Cookies.get('currency')
    setCurrency(savedCurrency || 'RUB')
  }, [user])

  const handleCurrencyChange = async (nextCurrency: string) => {
    if (nextCurrency === currency) return

    Cookies.set('currency', nextCurrency, { sameSite: 'Lax', path: '/' })
    setPreferredCurrency(nextCurrency)
    setCurrency(nextCurrency)

    if (user?.id) {
      try {
        await api.patch(`/users/profile/${user.id}`, { currency: nextCurrency })
      } catch {
        // no-op
      }
    }

    setTimeout(() => {
      window.location.reload()
    }, 100)
  }

  const loadProfile = async () => {
    try {
      // Получаем профиль пользователя
      const profileResponse = await api.get('/users/profile')
      const profileList = Array.isArray(profileResponse.data) ? profileResponse.data : [profileResponse.data]
      const profileData = profileList[0] || {}
      
      setProfile({
        id: profileData.id || 0,
        user_email: profileData.user_email || '',
        user_username: profileData.user_username || '',
        phone_number: profileData.phone_number || '',
        first_name: profileData.first_name || '',
        last_name: profileData.last_name || '',
        avatar: profileData.avatar,
        avatar_url: profileData.avatar_url || (profileData.avatar ? resolveMediaUrl(profileData.avatar) : null),
        whatsapp_phone: profileData.whatsapp_phone || '',
        telegram_username: profileData.telegram_username || '',
        total_orders: profileData.total_orders || 0,
        total_spent: String(profileData.total_spent || '0'),
      })

      setFormData({
        first_name: profileData.first_name || '',
        last_name: profileData.last_name || '',
        phone_number: profileData.phone_number || '',
        whatsapp_phone: profileData.whatsapp_phone || '',
        telegram_username: profileData.telegram_username || '',
      })
    } catch (error) {
      console.error('Failed to load profile:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadOrders = async () => {
    try {
      const response = await api.get('/orders/orders')
      setOrders(response.data || [])
    } catch (error) {
      console.error('Failed to load orders:', error)
    }
  }

  const loadAddresses = async () => {
    try {
      const response = await api.get('/users/addresses')
      setAddresses(response.data || [])
    } catch (error) {
      console.error('Failed to load addresses:', error)
    }
  }

  const handleAddAddress = () => {
    setEditingAddress(null)
    setAddressFormData({
      address_type: 'home',
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
      is_default: addresses.length === 0,
    })
    setShowAddressForm(true)
  }

  const handleEditAddress = (address: Address) => {
    setEditingAddress(address)
    setAddressFormData({
      address_type: address.address_type,
      contact_name: address.contact_name,
      contact_phone: address.contact_phone,
      country: address.country,
      region: address.region || '',
      city: address.city,
      postal_code: address.postal_code || '',
      street: address.street,
      house: address.house,
      apartment: address.apartment || '',
      entrance: address.entrance || '',
      floor: address.floor || '',
      intercom: address.intercom || '',
      comment: address.comment || '',
      is_default: address.is_default,
    })
    setShowAddressForm(true)
  }

  const handleSaveAddress = async () => {
    setAddressSaving(true)
    try {
      if (editingAddress) {
        // Обновление существующего адреса
        await api.patch(`/users/addresses/${editingAddress.id}`, addressFormData)
      } else {
        // Создание нового адреса
        await api.post('/users/addresses', addressFormData)
      }
      await loadAddresses()
      setShowAddressForm(false)
      setEditingAddress(null)
    } catch (error: any) {
      console.error('Failed to save address:', error)
      alert(error?.response?.data?.error || t('profile_error'))
    } finally {
      setAddressSaving(false)
    }
  }

  const handleDeleteAddress = async (addressId: number) => {
    if (!confirm('Вы уверены, что хотите удалить этот адрес?')) {
      return
    }
    try {
      await api.delete(`/users/addresses/${addressId}`)
      await loadAddresses()
    } catch (error: any) {
      console.error('Failed to delete address:', error)
      const errorMsg =
        error?.response?.data?.detail ||
        error?.response?.data?.error ||
        t('profile_error')
      alert(errorMsg)
    }
  }

  const handleCancelAddressForm = () => {
    setShowAddressForm(false)
    setEditingAddress(null)
    setAddressFormData({
      address_type: 'home',
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
  }

  const handleEdit = () => {
    setEditing(true)
  }

  const handleCancel = () => {
    setEditing(false)
    setAvatarFile(null)
    setAvatarPreview(null)
    if (profile) {
      setFormData({
        first_name: profile.first_name || '',
        last_name: profile.last_name || '',
        phone_number: profile.phone_number || '',
        whatsapp_phone: profile.whatsapp_phone || '',
        telegram_username: profile.telegram_username || '',
      })
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      // Загружаем аватар, если выбран
      if (avatarFile) {
        const formDataAvatar = new FormData()
        formDataAvatar.append('avatar', avatarFile)
        await api.post('/users/profile/upload-avatar', formDataAvatar, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        })
      }

      // Обновляем профиль (используем list endpoint для получения текущего профиля, затем обновляем по id)
      const profileResponse = await api.get('/users/profile')
      const profileList = Array.isArray(profileResponse.data) ? profileResponse.data : [profileResponse.data]
      const currentProfile = profileList[0]
      
      if (currentProfile?.id) {
        await api.patch(`/users/profile/${currentProfile.id}`, {
          first_name: formData.first_name,
          last_name: formData.last_name,
          whatsapp_phone: formData.whatsapp_phone,
          telegram_username: formData.telegram_username,
        })
      }

      // Перезагружаем профиль
      await loadProfile()
      setEditing(false)
      setAvatarFile(null)
      setAvatarPreview(null)
    } catch (error: any) {
      console.error('Failed to save profile:', error)
      alert(error?.response?.data?.error || t('profile_error'))
    } finally {
      setSaving(false)
    }
  }

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      // Валидация типа файла
      if (!file.type.startsWith('image/')) {
        alert('Пожалуйста, выберите изображение')
        return
      }
      // Валидация размера (5MB)
      if (file.size > 5 * 1024 * 1024) {
        alert('Размер файла не должен превышать 5MB')
        return
      }
      setAvatarFile(file)
      const reader = new FileReader()
      reader.onloadend = () => {
        setAvatarPreview(reader.result as string)
      }
      reader.readAsDataURL(file)
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return new Intl.DateTimeFormat(router.locale || 'ru', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(date)
  }

  const getOrderStatusText = (status: string) => {
    const key = ORDER_STATUS_MAP[status] || status
    return t(key, status)
  }

  const getAddressTypeText = (type: string) => {
    const key = `profile_address_type_${type}`
    return t(key, type)
  }

  const getWhatsAppLink = (phone: string) => {
    if (!phone) return null
    // Убираем все символы кроме цифр
    const cleanPhone = phone.replace(/\D/g, '')
    if (!cleanPhone) return null
    return `https://wa.me/${cleanPhone}`
  }

  const getTelegramLink = (username: string) => {
    if (!username) return null
    // Убираем @ если есть
    const cleanUsername = username.replace(/^@/, '')
    if (!cleanUsername) return null
    return `https://t.me/${cleanUsername}`
  }

  const getOrderStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      new: 'bg-[var(--accent-soft)] text-[var(--accent)]',
      pending_payment: 'bg-[var(--surface)] text-[var(--text-strong)]',
      paid: 'bg-[var(--accent-soft)] text-[var(--accent)]',
      processing: 'bg-[var(--surface)] text-[var(--text-strong)]',
      shipped: 'bg-[var(--accent-soft)] text-[var(--accent)]',
      delivered: 'bg-[var(--accent-soft)] text-[var(--accent)]',
      cancelled: 'bg-[var(--surface)] text-[var(--text-strong)]',
    }
    return colors[status] || 'bg-gray-100 text-gray-800'
  }

  if (authLoading || loading) {
    return (
      <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex justify-center items-center min-h-[400px]">
          <div className="text-lg text-gray-600">{t('profile_loading')}</div>
        </div>
      </section>
    )
  }

  if (!user || !profile) {
    return null
  }

  const displayAvatar = avatarPreview || (profile.avatar_url ? resolveMediaUrl(profile.avatar_url) : null) || null
  const displayName = `${profile.first_name || ''} ${profile.last_name || ''}`.trim() || profile.user_username

  return (
    <>
      <Head>
        <title>{t('profile_title')} — Turk-Export</title>
      </Head>
      <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
          {/* Заголовок */}
          <h1 className="text-3xl font-bold text-gray-900 mb-8">{t('profile_title')}</h1>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Левая колонка - Профиль */}
            <div className="lg:col-span-1">
              <div className="bg-white rounded-lg shadow-md p-6">
                {/* Аватар */}
                <div className="flex flex-col items-center mb-6">
                  <div className="relative">
                    {displayAvatar ? (
                      <img
                        src={displayAvatar}
                        alt={displayName}
                        className="w-32 h-32 rounded-full object-cover border-4 border-[var(--accent-soft)]"
                      />
                    ) : (
                      <div className="w-32 h-32 rounded-full bg-[var(--surface)] flex items-center justify-center border-4 border-[var(--accent-soft)]">
                        <span className="text-4xl font-bold text-[var(--text-strong)]">
                          {displayName.charAt(0).toUpperCase()}
                        </span>
                      </div>
                    )}
                    {editing && (
                      <label className="absolute bottom-0 right-0 bg-[var(--accent)] text-white rounded-full p-2 cursor-pointer hover:bg-[var(--accent-strong)] transition-colors">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <input
                          type="file"
                          accept="image/*"
                          onChange={handleAvatarChange}
                          className="hidden"
                        />
                      </label>
                    )}
                  </div>
                  <h2 className="text-xl font-semibold text-gray-900 mt-4">{displayName}</h2>
                  {!editing && !displayAvatar && (
                    <button
                      onClick={handleEdit}
                      className="mt-2 text-sm text-main hover-text-warm"
                    >
                      {t('profile_upload_avatar')}
                    </button>
                  )}
                </div>

                {/* Личная информация */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">
                    {t('profile_personal_info')}
                  </h3>

                  {editing ? (
                    <>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          {t('profile_first_name')}
                        </label>
                        <input
                          type="text"
                          value={formData.first_name}
                          onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          {t('profile_last_name')}
                        </label>
                        <input
                          type="text"
                          value={formData.last_name}
                          onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          {t('profile_email')}
                        </label>
                        <input
                          type="email"
                          value={profile.user_email}
                          disabled
                          className="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50 text-gray-500"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          {t('profile_phone')}
                        </label>
                        <input
                          type="tel"
                          value={formData.phone_number}
                          disabled
                          className="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50 text-gray-500"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          {t('profile_whatsapp')}
                        </label>
                        <input
                          type="tel"
                          value={formData.whatsapp_phone}
                          onChange={(e) => setFormData({ ...formData, whatsapp_phone: e.target.value })}
                          placeholder="+1234567890"
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          {t('profile_telegram')}
                        </label>
                        <input
                          type="text"
                          value={formData.telegram_username}
                          onChange={(e) => setFormData({ ...formData, telegram_username: e.target.value })}
                          placeholder="@username"
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                        />
                      </div>
                      <div className="flex gap-2 pt-4">
                        <button
                          onClick={handleSave}
                          disabled={saving}
                          className="flex-1 bg-[var(--accent)] text-white px-4 py-2 rounded-md hover:bg-[var(--accent-strong)] transition-colors disabled:opacity-50"
                        >
                          {saving ? t('profile_saving') : t('profile_save')}
                        </button>
                        <button
                          onClick={handleCancel}
                          disabled={saving}
                          className="flex-1 bg-gray-200 text-gray-800 px-4 py-2 rounded-md hover:bg-gray-300 transition-colors disabled:opacity-50"
                        >
                          {t('profile_cancel')}
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <div className="text-sm text-gray-500">{t('profile_first_name')}</div>
                        <div className="text-base font-medium text-gray-900">
                          {profile.first_name || '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">{t('profile_last_name')}</div>
                        <div className="text-base font-medium text-gray-900">
                          {profile.last_name || '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">{t('profile_email')}</div>
                        <div className="text-base font-medium text-gray-900">
                          {profile.user_email}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">{t('profile_phone')}</div>
                        <div className="text-base font-medium text-gray-900">
                          {profile.phone_number || '—'}
                        </div>
                      </div>
                      {(profile.whatsapp_phone || profile.telegram_username) && (
                        <div>
                          <div className="text-sm text-gray-500 mb-2">{t('profile_messengers')}</div>
                          <div className="flex items-center gap-3">
                            {profile.whatsapp_phone && getWhatsAppLink(profile.whatsapp_phone) && (
                              <a
                                href={getWhatsAppLink(profile.whatsapp_phone)!}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="group inline-flex h-10 w-10 items-center justify-center rounded-full border border-green-200 bg-green-50 transition hover:-translate-y-0.5 hover:bg-green-100 hover:shadow-md"
                                aria-label="WhatsApp"
                                title={profile.whatsapp_phone}
                              >
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-green-600 transition group-hover:scale-110">
                                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
                                </svg>
                              </a>
                            )}
                            {profile.telegram_username && getTelegramLink(profile.telegram_username) && (
                              <a
                                href={getTelegramLink(profile.telegram_username)!}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="group inline-flex h-10 w-10 items-center justify-center rounded-full border border-[var(--accent-muted)] bg-[var(--accent-soft)] transition hover:-translate-y-0.5 hover:bg-[var(--surface)] hover:shadow-md"
                                aria-label="Telegram"
                                title={`@${profile.telegram_username.replace(/^@/, '')}`}
                              >
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-[var(--accent)] transition group-hover:scale-110">
                                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.05-.2-.06-.06-.14-.04-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.75-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z"/>
                                </svg>
                              </a>
                            )}
                          </div>
                        </div>
                      )}
                      <button
                        onClick={handleEdit}
                        className="w-full mt-4 bg-[var(--accent)] text-white px-4 py-2 rounded-md hover:bg-[var(--accent-strong)] transition-colors"
                      >
                        {t('profile_edit')}
                      </button>
                    </>
                  )}
                </div>

                {/* Статистика */}
                {!editing && (
                  <div className="mt-6 pt-6 border-t">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">
                      {t('profile_statistics')}
                    </h3>
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {t('currency', 'Валюта')}
                      </label>
                      <select
                        value={currency}
                        onChange={(e) => handleCurrencyChange(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-violet-500"
                      >
                        <option value="RUB">RUB</option>
                        <option value="USD">USD</option>
                        <option value="EUR">EUR</option>
                        <option value="TRY">TRY</option>
                        <option value="KZT">KZT</option>
                      </select>
                    </div>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-600">{t('profile_total_orders', 'Всего заказов')}</span>
                        <span className="text-base font-semibold text-gray-900">
                          {profile.total_orders || 0}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-600">{t('profile_total_spent', 'Потрачено всего')}</span>
                        <span className="text-base font-semibold text-[var(--text-strong)]">
                          {totalSpentFromOrders.toFixed(2)} {currency}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Правая колонка - Заказы */}
            <div className="lg:col-span-2">
              <div className="bg-white rounded-lg shadow-md p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-6">{t('profile_orders')}</h2>

                {orders.length === 0 ? (
                  <div className="text-center py-12">
                    <svg
                      className="mx-auto h-12 w-12 text-gray-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
                      />
                    </svg>
                    <p className="mt-4 text-gray-600">{t('profile_no_orders')}</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    {(showAllOrders ? orders : orders.slice(0, 1)).map((order) => (
                      <div
                        key={order.id}
                        className="group rounded-xl border border-gray-200 bg-white shadow-sm hover:shadow-lg transition-all duration-200 overflow-hidden"
                      >
                        {/* Заголовок заказа */}
                        <div className="bg-[var(--surface)] px-6 py-4 border-b border-[var(--border)]">
                          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                            <div className="flex-1">
                              <div className="flex items-center gap-3 mb-2">
                                <h3 className="text-xl font-bold text-gray-900">
                                  {t('profile_order_number')} #{order.number}
                                </h3>
                                <span
                                  className={`px-3 py-1 rounded-full text-xs font-semibold ${getOrderStatusColor(
                                    order.status
                                  )}`}
                                >
                                  {getOrderStatusText(order.status)}
                                </span>
                              </div>
                              <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600">
                                <div className="flex items-center gap-1">
                                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                  </svg>
                                  <span>{formatDate(order.created_at)}</span>
                                </div>
                                {order.shipping_address_text && (
                                  <div className="flex items-center gap-1">
                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                    </svg>
                                    <span className="max-w-xs truncate">{order.shipping_address_text}</span>
                                  </div>
                                )}
                                <div className="flex items-center gap-1">
                                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                  </svg>
                                  <span>{order.contact_name}</span>
                                </div>
                                <div className="flex items-center gap-1">
                                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                                  </svg>
                                  <span>{order.contact_phone}</span>
                                </div>
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="text-2xl font-bold text-[var(--text-strong)] mb-1">
                                {order.total_amount} {order.currency}
                              </div>
                              <div className="text-sm text-gray-600">
                                {order.items.length} {order.items.length === 1 ? 'товар' : order.items.length < 5 ? 'товара' : 'товаров'}
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Товары в заказе */}
                        <div className="p-6">
                          <h4 className="text-sm font-semibold text-gray-700 mb-4 uppercase tracking-wide">
                            {t('profile_order_items')}:
                          </h4>
                          <div className="space-y-3">
                            {order.items.map((item) => {
                              const productLink = item.product_slug ? `/product/${item.product_slug}` : '#'
                              return (
                                <div
                                  key={item.id}
                                  className="group/item flex flex-col sm:flex-row gap-4 rounded-lg border border-gray-100 bg-gray-50 p-4 hover:bg-white hover:border-gray-200 transition-all duration-200"
                                >
                                  {/* Изображение товара */}
                                  <Link
                                    href={productLink}
                                    className="relative w-full sm:w-24 h-24 flex-shrink-0 overflow-hidden rounded-lg bg-gray-200"
                                  >
                                    {item.product_image_url ? (
                                      <img
                                        src={resolveMediaUrl(item.product_image_url)}
                                        alt={item.product_name}
                                        className="h-full w-full object-cover transition-transform duration-200 group-hover/item:scale-105"
                                      />
                                    ) : (
                                      <div className="h-full w-full flex items-center justify-center bg-gray-200">
                                        <svg className="h-8 w-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                        </svg>
                                      </div>
                                    )}
                                  </Link>

                                  {/* Информация о товаре */}
                                  <div className="flex-1 flex flex-col justify-between min-w-0">
                                    <div>
                                      <Link
                                        href={productLink}
                                        className="block"
                                      >
                                        <h5 className="text-base font-semibold text-gray-900 hover-text-warm transition-colors line-clamp-2">
                                          {item.product_name}
                                        </h5>
                                      </Link>
                                      <div className="mt-2 flex items-center gap-4 text-sm text-gray-600">
                                        <span className="font-medium">
                                          {t('cart_item_quantity', 'Количество')}: {item.quantity}
                                        </span>
                                        <span className="text-[var(--text-strong)] font-semibold">
                                          {item.price} {order.currency}
                                        </span>
                                      </div>
                                    </div>
                                  </div>

                                  {/* Итого по товару */}
                                  <div className="flex flex-col justify-between items-end sm:items-end">
                                    <div className="text-right">
                                      <div className="text-xs text-gray-500 mb-1">{t('cart_item_total', 'Итого')}</div>
                                      <div className="text-lg font-bold text-gray-900">
                                        {item.total} {order.currency}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      </div>
                    ))}
                    
                    {/* Кнопка разворачивания истории заказов */}
                    {orders.length > 1 && (
                      <div className="flex justify-center pt-4">
                        <button
                          onClick={() => setShowAllOrders(!showAllOrders)}
                          className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border-2 border-[var(--accent-muted)] bg-white text-[var(--accent)] font-semibold hover:bg-[var(--surface)] hover:border-[var(--accent-muted)] transition-all duration-200"
                        >
                          {showAllOrders ? (
                            <>
                              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                              </svg>
                              {t('profile_hide_order_history', 'Скрыть историю заказов')}
                            </>
                          ) : (
                            <>
                              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                              </svg>
                              {t('profile_show_order_history', 'Показать все заказы')} ({orders.length - 1})
                            </>
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Раздел адресов доставки */}
          <div className="mt-8">
            <div className="bg-white rounded-lg shadow-md p-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-gray-900">{t('profile_addresses')}</h2>
                {!showAddressForm && (
                  <button
                    onClick={handleAddAddress}
                    className="bg-[var(--accent)] text-white px-4 py-2 rounded-md hover:bg-[var(--accent-strong)] transition-colors"
                  >
                    {t('profile_add_address')}
                  </button>
                )}
              </div>

              {/* Форма создания/редактирования адреса */}
              {showAddressForm && (
                <div className="mb-6 border border-gray-200 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    {editingAddress ? t('profile_edit_address') : t('profile_add_address')}
                  </h3>
                  
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

                  {/* Кнопки сохранения/отмены */}
                  <div className="flex gap-2 mt-6">
                    <button
                      onClick={handleSaveAddress}
                      disabled={addressSaving}
                      className="flex-1 bg-[var(--accent)] text-white px-4 py-2 rounded-md hover:bg-[var(--accent-strong)] transition-colors disabled:opacity-50"
                    >
                      {addressSaving
                        ? editingAddress
                          ? t('profile_address_updating')
                          : t('profile_address_creating')
                        : t('profile_save')}
                    </button>
                    <button
                      onClick={handleCancelAddressForm}
                      disabled={addressSaving}
                      className="flex-1 bg-gray-200 text-gray-800 px-4 py-2 rounded-md hover:bg-gray-300 transition-colors disabled:opacity-50"
                    >
                      {t('profile_cancel')}
                    </button>
                  </div>
                </div>
              )}

              {/* Список адресов */}
              {addresses.length === 0 && !showAddressForm ? (
                <div className="text-center py-12">
                  <svg
                    className="mx-auto h-12 w-12 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                  </svg>
                  <p className="mt-4 text-gray-600">{t('profile_no_addresses')}</p>
                </div>
              ) : (
                !showAddressForm && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {addresses.map((address) => (
                      <div
                        key={address.id}
                        className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow relative"
                      >
                        {address.is_default && (
                          <span className="absolute top-2 right-2 bg-[var(--accent-soft)] text-[var(--accent)] text-xs font-medium px-2 py-1 rounded">
                            {t('profile_address_default')}
                          </span>
                        )}
                        <div className="mb-2">
                          <span className="text-xs font-medium text-gray-500 uppercase">
                            {getAddressTypeText(address.address_type)}
                          </span>
                        </div>
                        <div className="space-y-1">
                          <div className="font-semibold text-gray-900">{address.contact_name}</div>
                          <div className="text-sm text-gray-600">{address.contact_phone}</div>
                          <div className="text-sm text-gray-700">
                            {address.country}
                            {address.region && `, ${address.region}`}, {address.city}
                            {address.postal_code && `, ${address.postal_code}`}
                          </div>
                          <div className="text-sm text-gray-700">
                            {address.street}, {address.house}
                            {address.apartment && `, кв. ${address.apartment}`}
                          </div>
                          {(address.entrance || address.floor || address.intercom) && (
                            <div className="text-xs text-gray-500 mt-1">
                              {address.entrance && `Подъезд: ${address.entrance} `}
                              {address.floor && `Этаж: ${address.floor} `}
                              {address.intercom && `Домофон: ${address.intercom}`}
                            </div>
                          )}
                          {address.comment && (
                            <div className="text-xs text-gray-500 mt-1 italic">
                              {address.comment}
                            </div>
                          )}
                        </div>
                        <div className="flex gap-2 mt-4 pt-4 border-t">
                          <button
                            onClick={() => handleEditAddress(address)}
                            className="flex-1 text-sm text-[var(--text-strong)] hover-text-warm font-medium"
                          >
                            {t('profile_edit')}
                          </button>
                          <button
                            onClick={() => handleDeleteAddress(address.id)}
                            className="flex-1 text-sm text-red-600 hover:text-red-700 font-medium"
                          >
                            {t('profile_delete_address')}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>
          </div>
      </section>
    </>
  )
}

export async function getServerSideProps({ locale }: { locale: string }) {
  return {
    props: {
      ...(await serverSideTranslations(locale || 'ru', ['common'])),
    },
  }
}
