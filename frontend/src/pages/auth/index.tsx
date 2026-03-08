import { useState, useEffect, useRef } from 'react'
import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import { useRouter } from 'next/router'

// ─── Утилита: редирект после входа ──────────────────────────────────────────

function usePostLoginRedirect() {
  const router = useRouter()
  return () => {
    const next = router.query.next as string
    if (next && next.startsWith('/')) router.push(next)
    else router.push('/')
  }
}

// ─── Страница ────────────────────────────────────────────────────────────────

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

// ─── Telegram виджет ─────────────────────────────────────────────────────────

function TelegramLoginWidget() {
  const { loginWithTelegram } = useAuth()
  const router = useRouter()
  const redirect = usePostLoginRedirect()
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    ; (window as any).onTelegramAuth = async (user: any) => {
      try {
        await loginWithTelegram(user)
        redirect()
      } catch (e: any) {
        alert('Ошибка авторизации через Telegram: ' + (e?.response?.data?.detail || e?.message || 'Неизвестная ошибка'))
      }
    }

    if (containerRef.current && containerRef.current.children.length === 0) {
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

// ─── Google One Tap кнопка ────────────────────────────────────────────────────

function GoogleLoginButton() {
  const { loginWithSocial } = useAuth()
  const redirect = usePostLoginRedirect()
  const { t } = useTranslation('common')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { theme } = useTheme()

  const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID

  const handleGoogleResponse = async (response: any) => {
    // Google One Tap возвращает response.credential (id_token)
    const credential = response?.credential
    if (!credential) {
      setError(t('auth_social_error', 'Ошибка входа через Google'))
      return
    }
    setLoading(true)
    setError('')
    try {
      await loginWithSocial('google', credential)
      redirect()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || t('auth_social_error', 'Ошибка входа через Google')
      setError(String(msg))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!googleClientId) return

    const initGoogle = () => {
      const google = (window as any).google
      if (!google?.accounts?.id) return
      google.accounts.id.initialize({
        client_id: googleClientId,
        callback: handleGoogleResponse,
        auto_select: false,
        cancel_on_tap_outside: true,
      })
    }

    // Загружаем GSI если ещё не загружен
    if ((window as any).google?.accounts?.id) {
      initGoogle()
    } else {
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.onload = initGoogle
      document.head.appendChild(script)
    }
  }, [googleClientId])

  // Рендерим стандартную кнопку Google, так как кастомная через prompt()
  // может блокироваться браузером или если пользователь ранее закрыл One Tap
  useEffect(() => {
    if (!googleClientId) return
    const google = (window as any).google
    if (google?.accounts?.id) {
      google.accounts.id.renderButton(
        document.getElementById('google-signin-btn'),
        { theme: theme === 'dark' ? 'filled_black' : 'outline', size: 'large', width: '100%', text: "signin_with" }
      )
    } else {
      setTimeout(() => {
        const g = (window as any).google
        if (g?.accounts?.id && document.getElementById('google-signin-btn')) {
          g.accounts.id.renderButton(
            document.getElementById('google-signin-btn'),
            { theme: theme === 'dark' ? 'filled_black' : 'outline', size: 'large', width: '100%', text: "signin_with" }
          )
        }
      }, 1000) // fallback if loads later
    }
  }, [googleClientId, theme])

  const handleClick = () => {
    if (!googleClientId) {
      setError('Google Client ID не настроен')
      return
    }
    const google = (window as any).google
    if (!google?.accounts?.id) {
      setError(t('auth_social_error', 'Ошибка входа через Google'))
      return
    }
    google.accounts.id.prompt()
  }

  if (!googleClientId) return null

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={handleClick}
        disabled={loading}
        className="flex items-center justify-center gap-2 w-full rounded-md border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-60 transition-colors dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
      >
        <div id="google-signin-btn" className="w-full flex justify-center [&>div]:w-full"></div>
      </button>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

// ─── VK Login кнопка ─────────────────────────────────────────────────────────

function VKLoginButton() {
  const { loginWithSocial } = useAuth()
  const redirect = usePostLoginRedirect()
  const { t } = useTranslation('common')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const vkAppId = process.env.NEXT_PUBLIC_VK_APP_ID

  const handleVKLogin = async () => {
    if (!vkAppId) {
      setError('VK App ID не настроен')
      return
    }

    setLoading(true)
    setError('')

    try {
      // Открываем VK OAuth popup
      const width = 600
      const height = 500
      const left = window.screenX + (window.outerWidth - width) / 2
      const top = window.screenY + (window.outerHeight - height) / 2
      const redirectUri = `${window.location.origin}/auth/vk-callback`
      const vkAuthUrl = `https://oauth.vk.com/authorize?client_id=${vkAppId}&display=popup&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=token&v=5.199`

      const popup = window.open(vkAuthUrl, 'vk_auth', `width=${width},height=${height},left=${left},top=${top}`)

      // Слушаем сообщение от popup
      const handleMessage = async (event: MessageEvent) => {
        if (event.origin !== window.location.origin) return
        if (event.data?.type !== 'vk_auth') return

        window.removeEventListener('message', handleMessage)
        popup?.close()

        const { access_token, user_id } = event.data
        if (!access_token) {
          setError(t('auth_social_error', 'Ошибка входа через ВКонтакте'))
          setLoading(false)
          return
        }

        try {
          // Бэкенд принимает access_token + опциональный vk_user_id
          const res = await import('../../lib/api').then(m => m.default.post('/users/social-auth/', {
            provider: 'vk',
            access_token,
            vk_user_id: user_id,
          }))
          // loginWithSocial не подходит напрямую (нет vk_user_id), вызываем вручную
          const Cookies = (await import('js-cookie')).default
          const { setPreferredCurrency } = await import('../../lib/api')
          const { tokens, user: userData } = res.data
          if (tokens?.access) Cookies.set('access', tokens.access, { sameSite: 'Lax', path: '/' })
          if (tokens?.refresh) Cookies.set('refresh', tokens.refresh, { sameSite: 'Lax', path: '/' })
          if (userData?.currency) {
            Cookies.set('currency', userData.currency, { sameSite: 'Lax', path: '/' })
            setPreferredCurrency(userData.currency)
          }
          redirect()
          // Принудительный reload для обновления AuthContext
          window.location.reload()
        } catch (e2: any) {
          setError(e2?.response?.data?.detail || t('auth_social_error', 'Ошибка входа через ВКонтакте'))
          setLoading(false)
        }
      }

      window.addEventListener('message', handleMessage)

      // Таймаут — если popup закрыт без авторизации
      const checkClosed = setInterval(() => {
        if (popup?.closed) {
          clearInterval(checkClosed)
          window.removeEventListener('message', handleMessage)
          setLoading(false)
        }
      }, 500)
    } catch (e: any) {
      setError(t('auth_social_error', 'Ошибка входа через ВКонтакте'))
      setLoading(false)
    }
  }

  if (!vkAppId) return null

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={handleVKLogin}
        disabled={loading}
        className="flex items-center justify-center gap-2 w-full rounded-md bg-[#0077FF] hover:bg-[#005ecc] px-4 py-2.5 text-sm font-medium text-white shadow-sm disabled:opacity-60 transition-colors"
      >
        {/* VK logo */}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
          <path d="M15.684 0H8.316C1.592 0 0 1.592 0 8.316v7.368C0 22.408 1.592 24 8.316 24h7.368C22.408 24 24 22.408 24 15.684V8.316C24 1.592 22.391 0 15.684 0zm3.692 17.123h-1.744c-.66 0-.862-.523-2.049-1.712-1.033-1.01-1.49-1.135-1.744-1.135-.356 0-.458.102-.458.593v1.563c0 .424-.135.678-1.252.678-1.846 0-3.896-1.12-5.335-3.208C5.046 11.155 4.56 9.235 4.56 8.812c0-.254.102-.491.593-.491h1.744c.44 0 .61.203.779.678.864 2.49 2.303 4.675 2.896 4.675.22 0 .322-.102.322-.66V9.218c-.068-1.167-.683-1.269-.683-1.692 0-.203.17-.407.44-.407h2.743c.373 0 .508.203.508.643v3.473c0 .372.17.508.271.508.22 0 .407-.136.813-.542 1.254-1.405 2.151-3.574 2.151-3.574.119-.254.322-.491.762-.491h1.744c.526 0 .643.271.526.643-.22 1.017-2.354 4.031-2.354 4.031-.186.305-.254.44 0 .78.186.254.796.779 1.201 1.252.745.847 1.32 1.558 1.473 2.049.17.483-.086.728-.576.728z" />
        </svg>
        {loading ? t('auth_logging_in', 'Вход...') : t('auth_vk_login', 'Войти через ВКонтакте')}
      </button>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

// ─── Разделитель «или» ────────────────────────────────────────────────────────

function OrDivider({ label }: { label: string }) {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  return (
    <div className="relative mt-4">
      <div className="absolute inset-0 flex items-center">
        <div className="w-full border-t border-gray-300 dark:border-gray-600" />
      </div>
      <div className="relative flex justify-center text-sm">
        <span className={`px-2 ${isDark ? 'bg-gray-800 text-gray-400' : 'bg-white text-gray-500'}`}>{label}</span>
      </div>
    </div>
  )
}

// ─── Блок соцсетей ────────────────────────────────────────────────────────────

function SocialLoginBlock() {
  const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
  const vkAppId = process.env.NEXT_PUBLIC_VK_APP_ID
  if (!googleClientId && !vkAppId) return null
  return (
    <div className="flex flex-col gap-3 mt-2">
      {googleClientId && <GoogleLoginButton />}
      {vkAppId && <VKLoginButton />}
    </div>
  )
}

// ─── Форма входа ──────────────────────────────────────────────────────────────

function LoginForm() {
  const { login } = useAuth()
  const redirect = usePostLoginRedirect()
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
        redirect()
      } else {
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
    setError('')
    if (!loginValue) { setError('Введите номер телефона'); return }
    setSmsSent(true)
    setError('Отправка SMS будет доступна в ближайшее время')
  }

  return (
    <div className="space-y-4">
      {/* Переключатель метода входа */}
      <div className="inline-flex rounded-md border border-[var(--border)] p-1 bg-[var(--surface)]">
        <button
          type="button"
          onClick={() => { setLoginMethod('password'); setSmsSent(false); setSmsCode(''); setError('') }}
          className={`rounded px-3 py-1.5 text-sm transition-colors ${loginMethod === 'password' ? 'bg-[var(--accent)] text-white' : 'text-main hover:bg-[var(--surface)]'}`}
        >
          {t('auth_login_method_password')}
        </button>
        <button
          type="button"
          onClick={() => { setLoginMethod('sms'); setPassword(''); setError('') }}
          className={`rounded px-3 py-1.5 text-sm transition-colors ${loginMethod === 'sms' ? 'bg-[var(--accent)] text-white' : 'text-main hover:bg-[var(--surface)]'}`}
        >
          {t('auth_login_method_sms')}
        </button>
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
              className={`w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400 auth-password-input ${isDark ? 'border-gray-700 bg-gray-900 placeholder:text-gray-400' : ''}`}
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

      <OrDivider label={t('auth_or_login_with')} />
      <TelegramLoginWidget />
      <SocialLoginBlock />
    </div>
  )
}

// ─── Форма регистрации ────────────────────────────────────────────────────────

function RegisterForm() {
  const { register } = useAuth()
  const redirect = usePostLoginRedirect()
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
      redirect()
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
          className={`w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400 auth-password-input ${isDark ? 'border-gray-700 bg-gray-900 placeholder:text-gray-400' : ''}`}
          placeholder={t('password_placeholder', 'Пароль (мин. 8 знаков, буквы и цифры)')}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error ? <div className="text-sm text-[var(--text-strong)]">{error}</div> : null}
        <button type="submit" disabled={loading} className="rounded-md bg-[var(--accent)] px-4 py-2 text-white hover:bg-[var(--accent-strong)] disabled:opacity-60">{loading ? t('auth_registering') : t('auth_register_button')}</button>
      </form>
      <OrDivider label={t('auth_or_register_with')} />
      <TelegramLoginWidget />
      <SocialLoginBlock />
    </div>
  )
}
