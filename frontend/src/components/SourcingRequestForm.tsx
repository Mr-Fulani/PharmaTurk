import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import api from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { gtmEvent } from '../lib/gtm'
import { ymReachGoal } from '../lib/ym'
import ContactChannelPicker, { isUsernameChannel } from './ContactChannelPicker'
import { CameraIcon, DocumentMagnifyingGlassIcon, LinkIcon, TruckIcon } from '@heroicons/react/24/outline'

const MAX_PHOTO_BYTES = 10 * 1024 * 1024
const PHONE_DIGITS_RE = /^\+?\d{9,15}$/
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

type Field = 'source_url' | 'image' | 'contact_name' | 'contact_phone' | 'contact_email' | 'contact_channel' | 'contact_username' | 'form'
type FieldErrors = Partial<Record<Field, string>>

interface SourcingRequestFormProps {
  /** Где показана форма — уходит в аналитику (home / category / search) */
  placement: string
  /** Начальный комментарий, например название категории или поисковый запрос */
  initialComment?: string
  /** Заголовок и подзаголовок блока вместо общих «Найдём любой товар из Турции» */
  title?: string
  subtitle?: string
}

const inputBase =
  'mt-1 block w-full rounded-xl border bg-[var(--bg)] px-3.5 py-2.5 text-sm text-[var(--text)] placeholder:text-[var(--text)]/40 shadow-sm transition focus:outline-none focus:ring-2'
const inputOk = 'border-[var(--border)] focus:border-[var(--accent)] focus:ring-[var(--accent-soft)]'
const inputErr = 'border-[var(--danger)] bg-[var(--danger-soft)] focus:border-[var(--danger)] focus:ring-[var(--danger-soft)]'
const labelClass = 'text-sm font-medium text-[var(--text-strong)]'

/**
 * «Найдём любой товар из Турции по ссылке или фото» — заявка менеджеру без входа.
 * Вошедшему пользователю контакты подставляются из аккаунта и профиля.
 */
export default function SourcingRequestForm({ placement, initialComment = '', title, subtitle }: SourcingRequestFormProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const { user } = useAuth()
  const formRef = useRef<HTMLFormElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [sourceUrl, setSourceUrl] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoPreview, setPhotoPreview] = useState('')
  const [comment, setComment] = useState(initialComment)
  const [quantity, setQuantity] = useState(1)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [channel, setChannel] = useState('')
  const [username, setUsername] = useState('')
  const [website, setWebsite] = useState('') // поле-ловушка для ботов
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle')
  const [errors, setErrors] = useState<FieldErrors>({})

  // Ссылка /#sourcing (например, с баннера): форма подгружается на клиенте, браузер не успевает
  // прокрутить к ней сам — прокручиваем после монтирования
  useEffect(() => {
    if (window.location.hash === '#sourcing') {
      document.getElementById('sourcing')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [])

  useEffect(() => {
    if (!user) return
    const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim()
    if (fullName) setName((prev) => prev || fullName)
    if (user.phone_number) setPhone((prev) => prev || user.phone_number || '')
    if (user.email) setEmail((prev) => prev || user.email || '')
  }, [user])

  useEffect(() => () => {
    if (photoPreview) URL.revokeObjectURL(photoPreview)
  }, [photoPreview])

  const clearError = (...fields: Field[]) =>
    setErrors((prev) => {
      if (!fields.some((f) => prev[f])) return prev
      const next = { ...prev }
      fields.forEach((f) => delete next[f])
      return next
    })

  const onPhotoChange = (file: File | null) => {
    if (file && file.size > MAX_PHOTO_BYTES) {
      setErrors((prev) => ({ ...prev, image: t('sourcing_photo_too_large', 'Фото больше 10 МБ. Выберите файл поменьше.') }))
      return
    }
    clearError('image', 'source_url')
    setPhoto(file)
    setPhotoPreview(file ? URL.createObjectURL(file) : '')
  }

  const removePhoto = () => {
    setPhoto(null)
    setPhotoPreview('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const validate = (): FieldErrors => {
    const next: FieldErrors = {}
    const url = sourceUrl.trim()
    if (!url && !photo) {
      next.source_url = t('sourcing_link_or_photo_required', 'Добавьте ссылку на товар или фото.')
    } else if (url && !/^https?:\/\//i.test(url)) {
      next.source_url = t('sourcing_link_invalid', 'Ссылка должна начинаться с http:// или https://')
    }
    if (!name.trim()) next.contact_name = t('field_required', 'Заполните это поле')
    const phoneDigits = phone.replace(/[\s()-]/g, '')
    if (!phoneDigits) next.contact_phone = t('field_required', 'Заполните это поле')
    else if (!PHONE_DIGITS_RE.test(phoneDigits)) next.contact_phone = t('phone_invalid', 'Укажите номер в формате +79991234567')
    if (!channel) next.contact_channel = t('checkout_contact_channel_required', 'Выберите, как с вами связаться')
    if (channel === 'email' && !email.trim()) {
      next.contact_email = t('checkout_email_required_for_channel', 'Укажите email: вы выбрали связь по email')
    } else if (email.trim() && !EMAIL_RE.test(email.trim())) {
      next.contact_email = t('email_invalid', 'Проверьте адрес email')
    }
    return next
  }

  const focusFirstError = () => {
    requestAnimationFrame(() => {
      const el = formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      if (el && 'focus' in el) el.focus({ preventScroll: true })
    })
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (state === 'sending') return
    const found = validate()
    setErrors(found)
    if (Object.keys(found).length) {
      focusFirstError()
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
      if (err?.response?.status === 429) {
        setErrors({ form: t('sourcing_rate_limited', 'Слишком много заявок. Попробуйте чуть позже.') })
        return
      }
      // Ошибки сервера — к своим полям, остальное — общей строкой
      const serverErrors: FieldErrors = {}
      if (data && typeof data === 'object') {
        Object.entries(data).forEach(([key, value]) => {
          const text = Array.isArray(value) ? String(value[0]) : String(value)
          const field = (['source_url', 'image', 'contact_name', 'contact_phone', 'contact_email', 'contact_channel', 'contact_username'] as Field[])
            .find((f) => f === key)
          serverErrors[field || 'form'] = text
        })
      }
      if (!Object.keys(serverErrors).length) {
        serverErrors.form = t('sourcing_error', 'Не удалось отправить заявку. Попробуйте ещё раз.')
      }
      setErrors(serverErrors)
      focusFirstError()
    }
  }

  const steps = [
    { Icon: LinkIcon, title: t('sourcing_step1_title', 'Ссылка или фото'), text: t('sourcing_step1_text', 'С Trendyol, Hepsiburada, сайта бренда или просто снимок товара.') },
    { Icon: DocumentMagnifyingGlassIcon, title: t('sourcing_step2_title', 'Найдём и посчитаем'), text: t('sourcing_step2_text', 'Менеджер проверит наличие и назовёт цену с доставкой.') },
    { Icon: TruckIcon, title: t('sourcing_step3_title', 'Доставим'), text: t('sourcing_step3_text', 'Согласуем оплату удобным способом и отправим заказ.') },
  ]

  const heading = (
    <div className="mb-8 text-center">
      <h2 className="text-2xl md:text-3xl font-bold text-main">
        {title || t('sourcing_title', 'Не нашли нужный товар? Найдём любой товар из Турции')}
      </h2>
      <p className="mx-auto mt-3 max-w-2xl text-sm md:text-base text-main/70">
        {subtitle || t('sourcing_subtitle', 'Пришлите ссылку с любого турецкого сайта или фото — менеджер найдёт товар и рассчитает цену с доставкой.')}
      </p>
    </div>
  )

  if (state === 'sent') {
    return (
      <section id="sourcing" className="scroll-mt-24">
        {heading}
        <div className="mx-auto max-w-2xl rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-8 text-center shadow-sm">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-2xl">✓</div>
          <p className="text-xl font-semibold text-main">{t('sourcing_sent_title', 'Заявка отправлена!')}</p>
          <p className="mt-2 text-sm text-main/70">
            {t('sourcing_sent_text', 'Менеджер найдёт товар, уточнит цену и доставку и свяжется с вами выбранным способом.')}
          </p>
        </div>
      </section>
    )
  }

  const fieldClass = (field: Field) => `${inputBase} ${errors[field] ? inputErr : inputOk}`
  const errorText = (field: Field) =>
    errors[field] ? <p className="mt-1 text-xs font-medium text-[var(--danger)]">{errors[field]}</p> : null

  return (
    <section id="sourcing" className="scroll-mt-24">
      {heading}
      <div className="grid gap-6 rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-sm md:p-8 lg:grid-cols-5">
        {/* Как это работает */}
        <aside className="lg:col-span-2">
          <p className="mb-4 text-sm font-semibold uppercase tracking-wide text-main/60">
            {t('sourcing_how_it_works', 'Как это работает')}
          </p>
          <ol className="space-y-3">
            {steps.map(({ Icon, title, text }, index) => (
              <li key={title} className="relative flex gap-4 rounded-2xl bg-[var(--bg)] p-4">
                {/* Пунктир между шагами — визуальная связка «1 → 2 → 3» */}
                {index < steps.length - 1 && (
                  <span aria-hidden className="absolute left-[2.35rem] top-[3.9rem] h-[calc(100%-2.6rem)] border-l-2 border-dashed border-[var(--accent)]/25" />
                )}
                <span aria-hidden className="relative flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--accent-soft)] to-[var(--surface)] text-[var(--accent)] ring-1 ring-[var(--accent)]/15">
                  <Icon className="h-5 w-5" strokeWidth={1.8} />
                  <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-white shadow-sm">
                    {index + 1}
                  </span>
                </span>
                <div className="min-w-0">
                  <p className="font-semibold text-main">{title}</p>
                  <p className="mt-0.5 text-sm text-main/70">{text}</p>
                </div>
              </li>
            ))}
          </ol>
        </aside>

        {/* Форма */}
        <form ref={formRef} onSubmit={submit} noValidate className="lg:col-span-3">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block sm:col-span-2">
              <span className={labelClass}>{t('sourcing_link', 'Ссылка на товар')}</span>
              <input
                type="url"
                inputMode="url"
                value={sourceUrl}
                onChange={(e) => { setSourceUrl(e.target.value); clearError('source_url') }}
                placeholder="https://www.trendyol.com/..."
                aria-invalid={errors.source_url ? true : undefined}
                className={fieldClass('source_url')}
              />
              {errorText('source_url')}
            </label>

            <div className="sm:col-span-2">
              <span className={labelClass}>{t('sourcing_photo', 'Или фото товара')}</span>
              {photo ? (
                <div className="mt-1 flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg)] p-2.5">
                  {/* eslint-disable-next-line @next/next/no-img-element -- локальный blob-превью */}
                  <img src={photoPreview} alt="" className="h-14 w-14 rounded-lg object-cover" />
                  <span className="flex-1 truncate text-sm text-main">{photo.name}</span>
                  <button type="button" onClick={removePhoto} className="rounded-lg px-3 py-1.5 text-sm text-main/70 transition hover:bg-[var(--surface)] hover:text-main">
                    {t('sourcing_photo_remove', 'Убрать')}
                  </button>
                </div>
              ) : (
                <label
                  className={`mt-1 flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-4 text-sm transition hover:border-[var(--accent)] hover:text-[var(--accent)] ${errors.image || errors.source_url ? 'border-[var(--danger)] text-[var(--danger)]' : 'border-[var(--border)] text-main/70'}`}
                >
                  <CameraIcon aria-hidden className="h-5 w-5 flex-shrink-0" strokeWidth={1.8} />
                  {t('sourcing_photo_pick', 'Выбрать фото (JPG, PNG, WebP, до 10 МБ)')}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(e) => onPhotoChange(e.target.files?.[0] || null)}
                    className="sr-only"
                  />
                </label>
              )}
              {errorText('image')}
            </div>

            <label className="block sm:col-span-2">
              <span className={labelClass}>{t('sourcing_comment', 'Что нужно (размер, цвет, дозировка…)')}</span>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={2}
                maxLength={2000}
                className={`${inputBase} ${inputOk}`}
              />
            </label>

            <label className="block">
              <span className={labelClass}>{t('checkout_recipient_name', 'Имя получателя')} *</span>
              <input
                type="text"
                value={name}
                onChange={(e) => { setName(e.target.value); clearError('contact_name') }}
                autoComplete="name"
                aria-invalid={errors.contact_name ? true : undefined}
                className={fieldClass('contact_name')}
              />
              {errorText('contact_name')}
            </label>
            <label className="block">
              <span className={labelClass}>{t('checkout_phone', 'Телефон')} *</span>
              <input
                type="tel"
                value={phone}
                onChange={(e) => { setPhone(e.target.value); clearError('contact_phone') }}
                autoComplete="tel"
                placeholder="+79991234567"
                aria-invalid={errors.contact_phone ? true : undefined}
                className={fieldClass('contact_phone')}
              />
              {errorText('contact_phone')}
            </label>

            <label className="block">
              <span className={labelClass}>
                {channel === 'email' ? `${t('checkout_email', 'Email')} *` : t('checkout_email_optional', 'Email (необязательно)')}
              </span>
              <input
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); clearError('contact_email') }}
                autoComplete="email"
                aria-invalid={errors.contact_email ? true : undefined}
                className={fieldClass('contact_email')}
              />
              {errorText('contact_email')}
            </label>
            <label className="block">
              <span className={labelClass}>{t('quantity', 'Количество')}</span>
              <input
                type="number"
                min={1}
                max={999}
                value={quantity}
                onChange={(e) => setQuantity(Math.min(999, Math.max(1, Number(e.target.value) || 1)))}
                className={`${inputBase} ${inputOk}`}
              />
            </label>

            <div className="space-y-3 sm:col-span-2">
              <ContactChannelPicker
                name={`sourcing_channel_${placement}`}
                channel={channel}
                onChannelChange={(value) => { setChannel(value); clearError('contact_channel', 'contact_email') }}
                username={username}
                onUsernameChange={(value) => { setUsername(value); clearError('contact_username') }}
                error={errors.contact_channel || errors.contact_username}
                inputClassName={fieldClass('contact_username')}
              />
            </div>
          </div>

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

          {errors.form && (
            <p className="mt-4 rounded-xl border border-[var(--danger)] bg-[var(--danger-soft)] px-4 py-3 text-sm text-[var(--danger)]" role="alert">
              {errors.form}
            </p>
          )}

          <button
            type="submit"
            disabled={state === 'sending'}
            className="mt-6 w-full rounded-xl bg-[var(--accent)] px-6 py-3 font-semibold text-white shadow-sm transition hover:bg-[var(--accent-strong)] disabled:opacity-60"
          >
            {state === 'sending' ? t('checkout_submitting', 'Отправка...') : t('sourcing_submit', 'Найти товар')}
          </button>
          <p className="mt-2 text-center text-xs text-main/50">
            {t('sourcing_no_payment_note', 'Это бесплатно и ни к чему не обязывает — оплату обсудим после расчёта.')}
          </p>
        </form>
      </div>
    </section>
  )
}
