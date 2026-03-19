import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import api from '../../lib/api'
import { resolveMediaUrl } from '../../lib/media'
import Link from 'next/link'

interface PublicUserProfile {
  id: number
  user_username: string
  email?: string
  phone_number?: string
  first_name?: string
  last_name?: string
  avatar_url?: string
  bio?: string
  whatsapp_phone?: string
  telegram_username?: string
  total_orders: number
  testimonial_id?: number
  social_links: {
    telegram?: string
    whatsapp?: string
    google?: string
    facebook?: string
    vk?: string
    yandex?: string
  }
}

export async function getServerSideProps(ctx: any) {
  return {
    props: {
      ...(await serverSideTranslations(ctx.locale || 'ru', ['common'])),
    },
  }
}

export default function UserProfilePage() {
  const router = useRouter()
  const { username, testimonial_id } = router.query
  const { t } = useTranslation('common')
  const [profile, setProfile] = useState<PublicUserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!username && !testimonial_id) return

    const fetchProfile = async () => {
      try {
        setLoading(true)
        setError(null)
        const params: any = {}
        if (username) params.username = username
        if (testimonial_id) params.testimonial_id = testimonial_id

        const response = await api.get('/users/public-profile/', { params })
        console.log('Profile data from API:', response.data)
        console.log('Avatar URL:', response.data?.avatar_url)
        setProfile(response.data)
      } catch (err: any) {
        console.error('Failed to load profile:', err)
        const rawError = err?.response?.data?.error
        if (rawError === 'Профиль не является публичным') {
          setError('profile_not_public')
        } else if (rawError === 'Пользователь не найден') {
          setError('user_not_found')
        } else {
          setError(rawError || 'user_not_found')
        }
      } finally {
        setLoading(false)
      }
    }

    fetchProfile()
  }, [username, testimonial_id])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-red-600 border-r-transparent"></div>
          <p className="mt-4 text-gray-600">{t('loading', 'Загрузка...')}</p>
        </div>
      </div>
    )
  }

  if (error || !profile) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">
            {error
              ? error === 'profile_not_public'
                ? t('profile_not_public', 'Профиль не является публичным')
                : t('user_not_found', 'Пользователь не найден')
              : t('user_not_found', 'Пользователь не найден')}
          </h1>
          <Link
            href="/"
            className="text-red-600 hover:text-red-700 underline"
          >
            {t('back_to_home', 'Вернуться на главную')}
          </Link>
        </div>
      </div>
    )
  }

  const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || profile.user_username

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-4xl px-4">
        <div className="bg-white rounded-xl shadow-md overflow-hidden">
          {/* Header с аватаром */}
          <div className="bg-gradient-to-r from-red-100 via-red-50 to-rose-100 px-6 py-8">
            <div className="flex flex-col md:flex-row items-center md:items-start gap-6">
              {profile.avatar_url ? (
                <img
                  src={resolveMediaUrl(profile.avatar_url)}
                  alt={fullName}
                  className="w-32 h-32 rounded-full object-cover border-4 border-white shadow-lg"
                />
              ) : (
                <div className="w-32 h-32 rounded-full bg-gray-300 flex items-center justify-center border-4 border-white shadow-lg">
                  <span className="text-4xl text-gray-600 font-bold">
                    {fullName.charAt(0).toUpperCase()}
                  </span>
                </div>
              )}
              <div className="flex-1 text-center md:text-left">
                <h1 className="text-3xl font-bold text-gray-900 mb-2">
                  {fullName}
                </h1>
                {(profile.email || profile.phone_number) && (
                  <div className="mb-3 text-gray-700 space-y-1">
                    {profile.email && (
                      <p className="text-sm">
                        <span className="font-semibold">{t('email', 'Email')}:</span>{' '}
                        <a href={`mailto:${profile.email}`} className="text-red-600 hover:text-red-700">
                          {profile.email}
                        </a>
                      </p>
                    )}
                    {profile.phone_number && (
                      <p className="text-sm">
                        <span className="font-semibold">{t('phone', 'Телефон')}:</span>{' '}
                        <a href={`tel:${profile.phone_number}`} className="text-red-600 hover:text-red-700">
                          {profile.phone_number}
                        </a>
                      </p>
                    )}
                  </div>
                )}
                {profile.bio && (
                  <p className="text-gray-600 mb-4">{profile.bio}</p>
                )}
                <div className="flex flex-wrap items-center justify-center md:justify-start gap-4">
                  <div className="flex items-center gap-2 text-gray-700">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                    </svg>
                    <span className="font-semibold">{profile.total_orders}</span>
                    <span className="text-sm">
                      {t('orders', 'заказов')}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Контент */}
          <div className="px-6 py-6">
            {/* Социальные сети */}
            {(profile.social_links.telegram || 
              profile.social_links.whatsapp || 
              profile.social_links.google || 
              profile.social_links.facebook || 
              profile.social_links.vk || 
              profile.social_links.yandex) && (
              <div className="mb-6">
                <h2 className="text-xl font-semibold text-gray-900 mb-4">
                  {t('social_networks', 'Социальные сети')}
                </h2>
                <div className="flex flex-wrap gap-3">
                  {profile.social_links.telegram && (
                    <a
                      href={profile.social_links.telegram}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                    >
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.329-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
                      </svg>
                      <span>Telegram</span>
                    </a>
                  )}
                  {profile.social_links.whatsapp && (
                    <a
                      href={profile.social_links.whatsapp}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
                    >
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.98 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
                      </svg>
                      <span>WhatsApp</span>
                    </a>
                  )}
                  {profile.social_links.google && (
                    <a
                      href={profile.social_links.google}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                    >
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                      </svg>
                      <span>Google</span>
                    </a>
                  )}
                  {profile.social_links.facebook && (
                    <a
                      href={profile.social_links.facebook}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                      </svg>
                      <span>Facebook</span>
                    </a>
                  )}
                  {profile.social_links.vk && (
                    <a
                      href={profile.social_links.vk}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-700 text-white rounded-lg hover:bg-blue-800 transition-colors"
                    >
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M12.785 16.241s.225-.027.34-.164c.115-.134.111-.384.111-.384s-.016-1.104.495-1.268c.505-.16 1.153.338 1.808.771.508.34.894.558 1.006.86.112.302.075.785-.017 1.08l-.234.899s-.034.22-.19.334c-.18.13-.43.086-.43.086h-1.7s-1.123.008-1.97-.533c-.413-.33-.72-.75-.95-1.006-.202-.22-.145-.34-.06-.52.085-.18.38-.45.65-.73.448-.45.78-.99.87-1.33.09-.34.05-.52-.03-.72-.08-.2-.57-.42-1.31-.73-.49-.2-1.04-.46-1.46-.94-.41-.47-.3-.7-.23-.77.07-.07.23-.14.3-.21.07-.07.095-.13.14-.22.045-.09.03-.15.015-.22-.015-.07-.045-.14-.045-.14s-.27-.65.06-1.5c.33-.85 1.95-1.8 1.95-1.8s.11-.06.06-.13c-.045-.07-.09-.04-.09-.04l-.12-.03s-.18-.01-.25.08c-.07.09-.16.29-.21.4-.05.11-.1.15-.18.12-.08-.03-.18-.1-.3-.18-.12-.08-.25-.18-.38-.24-.13-.06-.22-.1-.3-.08-.08.02-.13.1-.18.18-.05.08-.1.2-.13.3-.03.1-.06.15-.12.15h-.12s-.09.01-.15-.06c-.06-.07-.04-.2-.04-.2s.02-.58.08-.85c.06-.27.18-.46.33-.6.15-.14.33-.18.44-.19.11-.01.22-.01.29-.01h.11s.09-.02.13-.05c.04-.03.06-.08.06-.08s.01-.05.02-.08c.01-.03.03-.05.05-.07.02-.02.05-.03.08-.03.03 0 .07 0 .1.01.03.01.07.02.1.04.03.02.06.04.08.07.02.03.04.07.05.11.01.04.02.08.02.12 0 .04.01.08.01.12v.16s0 .08.01.12c.01.04.02.07.04.1.02.03.05.05.08.07.03.02.07.03.1.04.03.01.07.01.1.01.03 0 .06 0 .08-.03.02-.02.04-.04.05-.07.01-.03.02-.05.02-.08v-.08s.02-.05.06-.08c.04-.03.13-.05.13-.05h.11c.07 0 .18 0 .29.01.11.01.29.05.44.19.15.14.27.33.33.6.06.27.08.85.08.85s0 .13-.04.2c-.06.07-.15.06-.15.06h-.12s-.09 0-.12.15c-.03.1-.08.22-.13.3-.05.08-.1.16-.18.18-.08.02-.17-.02-.3.08-.13.06-.26.16-.38.24-.12.08-.22.15-.3.18-.08.03-.13-.01-.18-.12-.05-.11-.14-.31-.21-.4-.07-.09-.18-.08-.25-.08l-.12.03s-.045.03-.09.04c-.045.07.06.13.06.13s1.62.95 1.95 1.8c.33.85.06 1.5.06 1.5s-.03.07-.045.14c-.015.07 0 .15.015.22.015.07.05.13.1.22.05.09.07.15.14.22.07.07.23.14.3.21.07.07.18.1.23.77.05.67-.23.7-.23.77-.41.47-.97.74-1.46.94-.74.31-1.23.53-1.31.73-.08.2-.12.38-.03.72.09.34.42.88.87 1.33.27.28.565.55.65.73.085.18.142.3-.06.52-.23.256-.537.676-.95 1.006-.847.541-1.97.533-1.97.533h-1.7s-.25.044-.43-.086c-.156-.114-.19-.334-.19-.334l-.234-.899s-.129-.778-.017-1.08c.112-.302.498-.52 1.006-.86.655-.433 1.303-.931 1.808-.771.511.164.495 1.268.495 1.268s-.004.25.111.384c.115.137.34.164.34.164h.89s.18-.01.27-.08c.09-.07.12-.18.09-.28l-.45-1.2s-.03-.09-.01-.13c.02-.04.06-.07.11-.07h.68s1.12-.07 1.25-.24c.13-.17.13-.17.13-.17s.02-.09.05-.12c.03-.03.08-.02.08-.02l.84.05s.89.04.99.29c.1.25.08.56.08.78v.6s-.01.18.08.28c.09.1.27.08.27.08h.89z"/>
                      </svg>
                      <span>VK</span>
                    </a>
                  )}
                  {profile.social_links.yandex && (
                    <a
                      href={profile.social_links.yandex}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                    >
                      <span>Yandex</span>
                    </a>
                  )}
                </div>
              </div>
            )}

            {/* Ссылка на отзыв */}
            {profile.testimonial_id && (
              <div className="mt-6">
                <Link
                  href={`/testimonials?username=${profile.user_username}#testimonial-${profile.testimonial_id}`}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                  </svg>
                  <span>{t('view_testimonial', 'Посмотреть отзыв')}</span>
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

