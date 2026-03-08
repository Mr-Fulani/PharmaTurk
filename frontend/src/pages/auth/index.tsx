import { useState, useEffect, useRef } from 'react'
import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import { useRouter } from 'next/router'

export default function AuthIndexPage() {
  const router = useRouter()
  const tabParam = (router.query.tab as string) || 'login'
  const [tab, setTab] = useState<'login' | 'register'>(tabParam === 'register' ? 'register' : 'login')
  const { t } = useTranslation('common')

  const switchTo = (nextTab: 'login' | 'register') => {
    setTab(nextTab)
    const q = { ...router.query, tab: nextTab }
    router.replace({ pathname: '/auth', query: q }, undefined, { shallow: true })
  }

  return (
    <>
      <Head>
        <title>{tab === 'login' ? t('login') : t('register')} — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-md p-6">
        <div className="mb-4 inline-flex rounded-md border border-[var(--border)] p-1 bg-[var(--surface)]">
          <button onClick={() => switchTo('login')} className={`rounded px-3 py-1.5 text-sm ${tab === 'login' ? 'bg-[var(--accent)] text-white' : 'text-main hover:bg-[var(--surface)]'}`}>{t('login')}</button>
          <button onClick={() => switchTo('register')} className={`rounded px-3 py-1.5 text-sm ${tab === 'register' ? 'bg-[var(--accent)] text-white' : 'text-main hover:bg-[var(--surface)]'}`}>{t('register')}</button>
        </div>
        {tab === 'login' ? <LoginForm /> : <RegisterForm />}
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])) } }
}

function TelegramLoginWidget() {
  const { loginWithTelegram } = useAuth()
  const router = useRouter()
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Функция-колбэк для Telegram
    ; (window as any).onTelegramAuth = async (user: any) => {
      try {
        await loginWithTelegram(user)
        const next = router.query.next as string
        if (next && next.startsWith('/')) router.push(next)
        else router.push('/')
      } catch (e: any) {
        alert('Ошибка авторизации через Telegram: ' + (e?.response?.data?.detail || e?.message || 'Неизвестная ошибка'))
      }
    }

    if (containerRef.current && containerRef.current.children.length === 0) {
      // NEXT_PUBLIC_TELEGRAM_BOT_USERNAME нужно добавить в .env, иначе используем дефолтный (или его нужно будет задать)
      const botName = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || 'Turk_ExportBot'
      const script = document.createElement('script')
      script.src = 'https://telegram.org/js/telegram-widget.js?22'
      script.setAttribute('data-telegram-login', botName)
      script.setAttribute('data-size', 'large')
      script.setAttribute('data-radius', '4')
      script.setAttribute('data-request-access', 'write')
      script.setAttribute('data-userpic', 'false')
      script.setAttribute('data-onauth', 'onTelegramAuth(user)')
      script.async = true
      containerRef.current.appendChild(script)
    }
  }, [loginWithTelegram, router])

  return <div ref={containerRef} className="flex justify-center my-4" />
}

function LoginForm() {
  const { login } = useAuth()
  const router = useRouter()
  const [loginValue, setLoginValue] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [loginMethod, setLoginMethod] = useState<'password' | 'sms'>('password')
  const [smsCode, setSmsCode] = useState('')
  const [smsSent, setSmsSent] = useState(false)
  const { t } = useTranslation('common')
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (loginMethod === 'password') {
        await login(loginValue, password)
        const next = router.query.next as string
        if (next && next.startsWith('/')) router.push(next)
        else router.push('/')
      } else {
        // TODO: Реализовать вход по SMS
        setError('Вход по SMS будет доступен в ближайшее время')
      }
    } catch (e: any) {
      const data = e?.response?.data
      const msg = (data?.detail)
        || (Array.isArray(data?.non_field_errors) ? data.non_field_errors[0] : '')
        || (typeof data === 'string' ? data : '')
        || 'Неверные учетные данные'
      setError(String(msg))
    } finally {
      setLoading(false)
    }
  }

  const handleSendSMS = async () => {
    // TODO: Реализовать отправку SMS кода
    setError('')
    if (!loginValue) {
      setError('Введите номер телефона')
      return
    }
    setSmsSent(true)
    setError('Отправка SMS будет доступна в ближайшее время')
  }

  return (
    <div className="space-y-4">
      {/* Переключатель метода входа */}
      <div className="inline-flex rounded-md border border-[var(--border)] p-1 bg-[var(--surface)]">
        <button
          type="button"
          onClick={() => {
            setLoginMethod('password')
            setSmsSent(false)
            setSmsCode('')
            setError('')
          }}
          className={`rounded px-3 py-1.5 text-sm transition-colors ${loginMethod === 'password'
            ? 'bg-[var(--accent)] text-white'
            : 'text-main hover:bg-[var(--surface)]'
            }`}
        >
          {t('auth_login_method_password')}
        </button>
        <button
          type="button"
          onClick={() => {
            setLoginMethod('sms')
            setPassword('')
            setError('')
          }}
          className={`rounded px-3 py-1.5 text-sm transition-colors ${loginMethod === 'sms'
            ? 'bg-[var(--accent)] text-white'
            : 'text-main hover:bg-[var(--surface)]'
            }`}
        >
          {t('auth_login_method_sms')}
        </button>
        {/* Кнопка для будущей интеграции соцсетей */}
        <div className="ml-2 flex items-center gap-2 border-l border-gray-300 pl-2">
          <span className="text-xs text-gray-500">{t('auth_coming_soon')}</span>
          <button
            type="button"
            disabled
            className="text-xs text-gray-400 cursor-not-allowed"
            title="Вход через соцсети будет доступен в ближайшее время"
          >
            🔵 Google
          </button>
          <button
            type="button"
            disabled
            className="text-xs text-gray-400 cursor-not-allowed"
            title="Вход через соцсети будет доступен в ближайшее время"
          >
            🔵 VK
          </button>
        </div>
      </div>

      <form onSubmit={submit} className="grid gap-3">
        {loginMethod === 'password' ? (
          <>
            <input
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400"
              placeholder={t('auth_login_placeholder')}
              value={loginValue}
              onChange={(e) => setLoginValue(e.target.value)}
              required
            />
            <input
              className={`w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400 auth-password-input ${isDark ? 'border-gray-700 bg-gray-900 placeholder:text-gray-400' : ''
                }`}
              placeholder={t('password_placeholder', 'Пароль (мин. 8 знаков, буквы и цифры)')}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </>
        ) : (
          <>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400"
                placeholder="+7 (999) 123-45-67"
                type="tel"
                value={loginValue}
                onChange={(e) => setLoginValue(e.target.value)}
                required
              />
              <button
                type="button"
                onClick={handleSendSMS}
                disabled={smsSent || loading}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-white hover:bg-[var(--accent-strong)] disabled:opacity-60 whitespace-nowrap"
              >
                {smsSent ? t('auth_code_sent') : t('auth_send_code')}
              </button>
            </div>
            {smsSent && (
              <input
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400"
                placeholder={t('auth_sms_code_placeholder')}
                type="text"
                value={smsCode}
                onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                required
              />
            )}
          </>
        )}
        {error ? <div className="text-sm text-[var(--text-strong)]">{error}</div> : null}
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-white hover:bg-[var(--accent-strong)] disabled:opacity-60"
        >
          {loading ? t('auth_logging_in') : t('login')}
        </button>
      </form>

      <div className="relative mt-6">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-gray-300"></div>
        </div>
        <div className="relative flex justify-center text-sm">
          <span className={`px-2 ${isDark ? 'bg-gray-800 text-gray-400' : 'bg-white text-gray-500'}`}>{t('auth_or_login_with')}</span>
        </div>
      </div>
      <TelegramLoginWidget />
    </div>
  )
}

function RegisterForm() {
  const { register } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { t } = useTranslation('common')
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(email, username, password)
      const next = router.query.next as string
      if (next && next.startsWith('/')) router.push(next)
      else router.push('/')
    } catch (e: any) {
      const data = e?.response?.data || {}
      const first = Object.values(data)[0] as any
      const msg = Array.isArray(first) ? first[0] : (typeof first === 'string' ? first : '')
      setError(String(msg || 'Ошибка регистрации'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="grid gap-3">
        <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder={t('email', 'Email')} value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder={t('username', 'Имя пользователя')} value={username} onChange={(e) => setUsername(e.target.value)} required />
        <input
          className={`w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400 auth-password-input ${isDark ? 'border-gray-700 bg-gray-900 placeholder:text-gray-400' : ''
            }`}
          placeholder={t('password_placeholder', 'Пароль (мин. 8 знаков, буквы и цифры)')}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error ? <div className="text-sm text-[var(--text-strong)]">{error}</div> : null}
        <button type="submit" disabled={loading} className="rounded-md bg-[var(--accent)] px-4 py-2 text-white hover:bg-[var(--accent-strong)] disabled:opacity-60">{loading ? t('auth_registering') : t('auth_register_button')}</button>
      </form>
      <div className="relative mt-6">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-gray-300"></div>
        </div>
        <div className="relative flex justify-center text-sm">
          <span className={`px-2 ${isDark ? 'bg-gray-800 text-gray-400' : 'bg-white text-gray-500'}`}>{t('auth_or_register_with')}</span>
        </div>
      </div>
      <TelegramLoginWidget />
    </div>
  )
}


