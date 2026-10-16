import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'next-i18next'
import { getSingleFlight } from '../lib/api'
import { useAuth } from '../context/AuthContext'

export const CONTACT_CHANNELS = ['telegram', 'whatsapp', 'phone', 'email'] as const
export type ContactChannel = (typeof CONTACT_CHANNELS)[number]

// Фирменные цвета иконок — те же, что в ContactWidget
const CONTACT_CHANNEL_COLORS: Record<ContactChannel, string> = {
  telegram: '#0088cc',
  whatsapp: '#25d366',
  phone: '#f59e0b',
  email: '#7c3aed',
}

export const isUsernameChannel = (channel: string) => channel === 'telegram' || channel === 'whatsapp'

interface ContactChannelPickerProps {
  channel: string
  onChannelChange: (channel: string) => void
  username: string
  onUsernameChange: (username: string) => void
  /** Имя группы радиокнопок — уникальное на странице */
  name?: string
}

/**
 * Выбор канала связи (плашки в фирменных цветах) и юзернейм Telegram/WhatsApp.
 * Юзернейм подставляется из профиля при выборе канала, если клиент не ввёл своё.
 */
export default function ContactChannelPicker({
  channel,
  onChannelChange,
  username,
  onUsernameChange,
  name = 'contact_channel',
}: ContactChannelPickerProps) {
  const { t } = useTranslation('common')
  const { user } = useAuth()
  const [profileMessengers, setProfileMessengers] = useState<{ telegram: string; whatsapp: string }>({ telegram: '', whatsapp: '' })
  const autoUsernameRef = useRef('')

  useEffect(() => {
    if (!user) return
    getSingleFlight('/users/profile')
      .then((r) => {
        const profile = r.data?.[0]
        setProfileMessengers({
          telegram: profile?.telegram_username || '',
          whatsapp: profile?.whatsapp_phone || '',
        })
      })
      .catch(() => undefined)
  }, [user])

  useEffect(() => {
    if (channel !== 'telegram' && channel !== 'whatsapp') return
    // Не перетираем то, что клиент ввёл сам
    if (username && username !== autoUsernameRef.current) return
    const value = profileMessengers[channel]
    autoUsernameRef.current = value
    onUsernameChange(value)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel, profileMessengers])

  return (
    <>
      <fieldset>
        <legend className="text-sm font-medium text-gray-700">{t('checkout_contact_channel', 'Как с вами связаться')} *</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {CONTACT_CHANNELS.map((option) => (
            <label
              key={option}
              style={{
                '--chip-clr': CONTACT_CHANNEL_COLORS[option],
                '--chip-bg': `${CONTACT_CHANNEL_COLORS[option]}1f`,
              } as React.CSSProperties}
              className={`cursor-pointer rounded-full border-2 px-4 py-1.5 text-sm font-medium transition-all hover:border-[var(--chip-clr)] hover:bg-[var(--chip-bg)] hover:text-[var(--chip-clr)] ${channel === option
                ? 'border-[var(--chip-clr)] bg-[var(--chip-bg)] text-[var(--chip-clr)]'
                : 'border-gray-200 text-gray-700'
                }`}
            >
              <input
                type="radio"
                name={name}
                value={option}
                checked={channel === option}
                onChange={(e) => onChannelChange(e.target.value)}
                className="sr-only"
              />
              {t(`contact_channel_${option}`)}
            </label>
          ))}
        </div>
      </fieldset>
      {isUsernameChannel(channel) && (
        <label className="block">
          <span className="text-sm font-medium text-gray-700">
            {t(`checkout_username_${channel}`, channel === 'telegram' ? 'Ник в Telegram (необязательно)' : 'Юзернейм или номер в WhatsApp (необязательно)')}
          </span>
          <input
            type="text"
            value={username}
            onChange={(e) => onUsernameChange(e.target.value)}
            placeholder={channel === 'whatsapp' ? '@username / +79990000000' : '@username'}
            autoComplete="off"
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
          />
          <span className="mt-1 block text-xs text-gray-500">
            {t('checkout_username_hint', 'Если не указать, менеджер свяжется с вами по номеру телефона.')}
          </span>
        </label>
      )}
    </>
  )
}
