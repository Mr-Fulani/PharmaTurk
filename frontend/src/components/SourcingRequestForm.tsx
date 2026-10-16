import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { gtmEvent } from '../lib/gtm'
import { ymReachGoal } from '../lib/ym'
import ContactChannelPicker, { isUsernameChannel } from './ContactChannelPicker'

const MAX_PHOTO_BYTES = 10 * 1024 * 1024

interface SourcingRequestFormProps {
  /** Где показана форма — уходит в аналитику (home / category / search) */
  placement: string
  /** Начальный комментарий, например название категории или поисковый запрос */
  initialComment?: string
}

const inputClass =
  'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500'

/**
 * «Найдём любой товар из Турции по ссылке или фото» — заявка менеджеру без входа.
 * Вошедшему пользователю контакты подставляются из аккаунта и профиля.
 */
export default function SourcingRequestForm({ placement, initialComment = '' }: SourcingRequestFormProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const { user } = useAuth()

  const [sourceUrl, setSourceUrl] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [comment, setComment] = useState(initialComment)
  const [quantity, setQuantity] = useState(1)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [channel, setChannel] = useState('')
  const [username, setUsername] = useState('')
  const [website, setWebsite] = useState('') // поле-ловушка для ботов
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim()
    if (fullName) setName((prev) => prev || fullName)
    if (user.phone_number) setPhone((prev) => prev || user.phone_number || '')
    if (user.email) setEmail((prev) => prev || user.email || '')
  }, [user])

  const onPhotoChange = (file: File | null) => {
    setError('')
    if (file && file.size > MAX_PHOTO_BYTES) {
      setError(t('sourcing_photo_too_large', 'Фото больше 10 МБ. Выберите файл поменьше.'))
      return
    }
    setPhoto(file)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (state === 'sending') return
    setError('')
    if (!sourceUrl.trim() && !photo) {
      setError(t('sourcing_link_or_photo_required', 'Добавьте ссылку на товар или фото.'))
      return
    }
    if (!channel) {
      setError(t('checkout_contact_channel_required', 'Выберите, как с вами связаться'))
      return
    }
    if (channel === 'email' && !email.trim()) {
      setError(t('checkout_email_required_for_channel', 'Укажите email: вы выбрали связь по email'))
      return
    }

    const body = new FormData()
    if (sourceUrl.trim()) body.append('source_url', sourceUrl.trim())
    if (photo) body.append('image', photo)
    if (comment.trim()) body.append('comment', comment.trim())
    body.append('quantity', String(quantity))
    body.append('contact_name', name.trim())
    body.append('contact_phone', phone.trim())
    if (email.trim()) body.append('contact_email', email.trim())
    body.append('contact_channel', channel)
    if (isUsernameChannel(channel) && username.trim()) body.append('contact_username', username.trim())
    body.append('locale', router.locale || 'ru')
    if (website) body.append('website', website)

    setState('sending')
    try {
      await api.post('/orders/sourcing-requests/', body)
      setState('sent')
      ymReachGoal('sourcing_request', { placement })
      gtmEvent({ event: 'sourcing_request', placement })
    } catch (err: any) {
      setState('idle')
      const data = err?.response?.data
      const firstError = data && typeof data === 'object'
        ? Object.values(data).flat().find((v) => typeof v === 'string')
        : null
      setError(
        err?.response?.status === 429
          ? t('sourcing_rate_limited', 'Слишком много заявок. Попробуйте чуть позже.')
          : String(firstError || t('sourcing_error', 'Не удалось отправить заявку. Попробуйте ещё раз.'))
      )
    }
  }

  if (state === 'sent') {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center">
        <p className="text-lg font-semibold text-emerald-800">{t('sourcing_sent_title', 'Заявка отправлена!')}</p>
        <p className="mt-2 text-sm text-emerald-700">
          {t('sourcing_sent_text', 'Менеджер найдёт товар, уточнит цену и доставку и свяжется с вами выбранным способом.')}
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm" noValidate>
      <h2 className="text-xl font-bold text-gray-900">
        {t('sourcing_title', 'Не нашли нужный товар? Найдём любой товар из Турции')}
      </h2>
      <p className="mt-1 text-sm text-gray-600">
        {t('sourcing_subtitle', 'Пришлите ссылку с любого турецкого сайта или фото — менеджер найдёт товар и рассчитает цену с доставкой.')}
      </p>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">{t('sourcing_link', 'Ссылка на товар')}</span>
            <input
              type="url"
              inputMode="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://www.trendyol.com/..."
              className={inputClass}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">{t('sourcing_photo', 'Или фото товара')}</span>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => onPhotoChange(e.target.files?.[0] || null)}
              className="mt-1 block w-full text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-gray-200"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">{t('sourcing_comment', 'Что нужно (размер, цвет, дозировка…)')}</span>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              maxLength={2000}
              className={inputClass}
            />
          </label>
          <label className="block w-32">
            <span className="text-sm font-medium text-gray-700">{t('quantity', 'Количество')}</span>
            <input
              type="number"
              min={1}
              max={999}
              value={quantity}
              onChange={(e) => setQuantity(Math.min(999, Math.max(1, Number(e.target.value) || 1)))}
              className={inputClass}
            />
          </label>
        </div>

        <div className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">{t('checkout_recipient_name', 'Имя получателя')} *</span>
            <input type="text" required value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" className={inputClass} />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">{t('checkout_phone', 'Телефон')} *</span>
            <input type="tel" required value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" className={inputClass} />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">
              {channel === 'email' ? `${t('checkout_email', 'Email')} *` : t('checkout_email_optional', 'Email (необязательно)')}
            </span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" className={inputClass} />
          </label>
          <ContactChannelPicker
            name={`sourcing_channel_${placement}`}
            channel={channel}
            onChannelChange={setChannel}
            username={username}
            onUsernameChange={setUsername}
          />
          {/* Поле-ловушка: скрыто от людей, боты его заполняют */}
          <input
            type="text"
            name="website"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            className="hidden"
          />
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={state === 'sending'}
        className="mt-5 w-full rounded-lg bg-[var(--accent)] px-6 py-3 font-semibold text-white transition hover:opacity-90 disabled:opacity-60 md:w-auto"
      >
        {state === 'sending' ? t('checkout_submitting', 'Отправка...') : t('sourcing_submit', 'Найти товар')}
      </button>
    </form>
  )
}
