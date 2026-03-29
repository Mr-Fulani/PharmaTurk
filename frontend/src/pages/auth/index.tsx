import { useState, useEffect, useRef } from 'react'
import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import { useRouter } from 'next/router'
import styles from './Auth.module.css'

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
      <main className="flex min-h-[80vh] items-center justify-center p-4">
        <div className={`${styles.container} ${tab === 'register' ? styles.active : ''}`}>
          
          <div className={`${styles.formBox} ${styles.login}`}>
            <LoginForm />
          </div>

          <div className={`${styles.formBox} ${styles.register}`}>
            <RegisterForm />
          </div>

          <div className={styles.toggleBox}>
            <div className={`${styles.togglePanel} ${styles.toggleLeft}`}>
              <h1>{t('auth_hello_welcome')}</h1>
              <p>{t('auth_dont_have_account')}</p>
              <button className={styles.btn} onClick={() => switchTo('register')}>
                {t('register')}
              </button>
            </div>

            <div className={`${styles.togglePanel} ${styles.toggleRight}`}>
              <h1>{t('auth_welcome_back')}</h1>
              <p>{t('auth_already_have_account')}</p>
              <button className={styles.btn} onClick={() => switchTo('login')}>
                {t('login')}
              </button>
            </div>
          </div>

        </div>
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
  const { t } = useTranslation('common')
  const uniqueId = useRef(`telegram-login-${Math.random().toString(36).substring(2, 9)}`)

  useEffect(() => {
    ; (window as any).onTelegramAuth = async (user: any) => {
      try {
        await loginWithTelegram(user)
        redirect()
      } catch (e: any) {
        const raw = e?.response?.data?.detail || e?.message || ''
        const msg = String(raw).toLowerCase().includes('csrf')
          ? t('auth_csrf_error')
          : (raw || t('auth_social_error', 'Ошибка входа через Telegram'))
        alert(msg)
      }
    }

    if (containerRef.current && containerRef.current.children.length === 0) {
      const botName = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || 'Turk_ExportBot'
      const script = document.createElement('script')
      script.src = 'https://telegram.org/js/telegram-widget.js?22'
      script.setAttribute('data-telegram-login', botName)
      script.setAttribute('data-size', 'small')
      script.setAttribute('data-radius', '4')
      script.setAttribute('data-request-access', 'write')
      script.setAttribute('data-userpic', 'false')
      script.setAttribute('data-onauth', 'onTelegramAuth(user)')
      script.id = uniqueId.current
      script.async = true
      
      // Очищаем контейнер перед добавлением скрипта
      containerRef.current.innerHTML = ''
      containerRef.current.appendChild(script)
    }

    const intervalId = setInterval(() => {
      const wrapper = document.getElementById(uniqueId.current + '-wrapper')
      if (!wrapper) return
      
      // Ищем сгенерированный Telegram iframe
      const iframes = document.querySelectorAll(`iframe[id^="telegram-login-"]`)
      let iframe = null
      
      // Ищем свободный iframe, который еще не перенесен в наш враппер
      for (let i = 0; i < iframes.length; i++) {
        const currentIframe = iframes[i] as HTMLIFrameElement;
        // Если iframe уже внутри какого-то враппера, пропускаем
        if (currentIframe.closest('.telegram-widget-wrapper')) continue;
        iframe = currentIframe;
        break;
      }
      
      // Если свободный не найден, возможно он уже внутри нашего враппера
      if (!iframe) {
        iframe = wrapper.querySelector('iframe') as HTMLIFrameElement | null
      }
      
      if (!iframe) return
      
      // Переносим iframe внутрь нашего враппера, если он отрендерился снаружи
      if (iframe.parentElement !== wrapper) {
        wrapper.appendChild(iframe)
      }

      const htmlWrapper = wrapper as HTMLElement
      htmlWrapper.style.position = 'absolute'
      htmlWrapper.style.inset = '0'
      htmlWrapper.style.zIndex = '50'
      
      iframe.style.width = '40px' // Ставим точные размеры как у нашей иконки
      iframe.style.height = '40px'
      iframe.style.opacity = '0.01'
      iframe.style.position = 'absolute'
      iframe.style.inset = '0'
      iframe.style.zIndex = '50'
      iframe.style.pointerEvents = 'auto'
      
      // Фикс для Telegram: иногда виджет внутри iframe блокирует клики, если iframe слишком большой или растянут
      // Мы ставим размеры точно по иконке, чтобы клик приходился ровно в центр виджета
      
      clearInterval(intervalId)
    }, 200)

    return () => clearInterval(intervalId)
  }, [loginWithTelegram, router, t])

  return (
    <div className="relative flex h-10 w-10 items-center justify-center overflow-hidden hover:opacity-80 transition-opacity">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#2AABEE] text-white shadow-sm pointer-events-none relative z-10">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M22.5 3.5L2.8 11.1c-1 .4-1 .9-.2 1.1l5 1.6 1.9 5.7c.2.6.3.8.6.8.3 0 .5-.2.8-.5l2.5-2.4 5.2 3.9c1 .6 1.7.3 2-1l3.6-16.9c.4-1.6-.6-2.3-1.7-1.8zM9.3 14.9l-.7 2.6-.4-3.6 9.7-6.2-8.6 7.2z" />
        </svg>
      </div>
      <div id={uniqueId.current + '-wrapper'} ref={containerRef} className="telegram-widget-wrapper absolute inset-0 z-50 flex items-center justify-center" style={{ cursor: 'pointer', pointerEvents: 'auto' }} />
    </div>
  )
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
      const raw = e?.response?.data?.detail || e?.message || ''
      const msg = String(raw).toLowerCase().includes('csrf')
        ? t('auth_csrf_error')
        : (raw || t('auth_social_error', 'Ошибка входа через Google'))
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
      
      const btnWrappers = document.querySelectorAll('.google-signin-btn-wrapper')
      
      btnWrappers.forEach((btn, index) => {
        const uniqueId = `google-signin-btn-${index}`
        btn.id = uniqueId
        btn.innerHTML = ''
        
        google.accounts.id.renderButton(
          document.getElementById(uniqueId),
          { theme: 'outline', size: 'large', type: 'icon', shape: 'circle' }
        )
      })
      
      google.accounts.id.initialize({
        client_id: googleClientId,
        callback: handleGoogleResponse,
        auto_select: false,
        cancel_on_tap_outside: true,
      })
    }

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
  }, [googleClientId, theme])

  if (!googleClientId) return null

  return (
    <div className="flex flex-col items-center gap-1 hover:opacity-80 transition-opacity" style={{ colorScheme: 'light' }}>
      <div
        className={`google-signin-btn-wrapper flex items-center justify-center ${loading ? 'opacity-60' : ''}`}
      />
      {error && <p className="text-xs text-red-500 absolute -bottom-5">{error}</p>}
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
      const width = 600
      const height = 500
      const left = window.screenX + (window.outerWidth - width) / 2
      const top = window.screenY + (window.outerHeight - height) / 2
      const redirectUri = `${window.location.origin}/auth/vk-callback`
      const vkAuthUrl = `https://oauth.vk.com/authorize?client_id=${vkAppId}&display=popup&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=token&v=5.199`

      const popup = window.open(vkAuthUrl, 'vk_auth', `width=${width},height=${height},left=${left},top=${top}`)

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
          const res = await import('../../lib/api').then(m => m.default.post('/users/social-auth/', {
            provider: 'vk',
            access_token,
            vk_user_id: user_id,
          }))
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
          window.location.reload()
        } catch (e2: any) {
          const raw = e2?.response?.data?.detail || ''
          const msg = String(raw).toLowerCase().includes('csrf')
            ? t('auth_csrf_error')
            : (raw || t('auth_social_error', 'Ошибка входа через ВКонтакте'))
          setError(msg)
          setLoading(false)
        }
      }

      window.addEventListener('message', handleMessage)

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
    <div className="flex flex-col items-center gap-1 relative">
      <button
        type="button"
        onClick={handleVKLogin}
        disabled={loading}
        className="flex h-10 w-10 items-center justify-center rounded-full bg-[#0077FF] hover:bg-[#005ecc] text-white shadow-sm disabled:opacity-60 transition-colors"
        aria-label="VK"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
          <path d="M15.684 0H8.316C1.592 0 0 1.592 0 8.316v7.368C0 22.408 1.592 24 8.316 24h7.368C22.408 24 24 22.408 24 15.684V8.316C24 1.592 22.391 0 15.684 0zm3.692 17.123h-1.744c-.66 0-.862-.523-2.049-1.712-1.033-1.01-1.49-1.135-1.744-1.135-.356 0-.458.102-.458.593v1.563c0 .424-.135.678-1.252.678-1.846 0-3.896-1.12-5.335-3.208C5.046 11.155 4.56 9.235 4.56 8.812c0-.254.102-.491.593-.491h1.744c.44 0 .61.203.779.678.864 2.49 2.303 4.675 2.896 4.675.22 0 .322-.102.322-.66V9.218c-.068-1.167-.683-1.269-.683-1.692 0-.203.17-.407.44-.407h2.743c.373 0 .508.203.508.643v3.473c0 .372.17.508.271.508.22 0 .407-.136.813-.542 1.254-1.405 2.151-3.574 2.151-3.574.119-.254.322-.491.762-.491h1.744c.526 0 .643.271.526.643-.22 1.017-2.354 4.031-2.354 4.031-.186.305-.254.44 0 .78.186.254.796.779 1.201 1.252.745.847 1.32 1.558 1.473 2.049.17.483-.086.728-.576.728z" />
        </svg>
      </button>
      {error && <p className="text-xs text-red-500 absolute -bottom-5">{error}</p>}
    </div>
  )
}

// ─── Блок соцсетей ────────────────────────────────────────────────────────────

function SocialLoginBlock() {
  const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
  const vkAppId = process.env.NEXT_PUBLIC_VK_APP_ID
  return (
    <div className={styles.socialIcons}>
      <TelegramLoginWidget />
      {googleClientId && <GoogleLoginButton />}
      {vkAppId && <VKLoginButton />}
    </div>
  )
}

// ─── Форма входа ──────────────────────────────────────────────────────────────

function LoginForm() {
  const { login } = useAuth()
  const redirect = usePostLoginRedirect()
  const [loginMethod, setLoginMethod] = useState<'password' | 'sms'>('password')
  const [loginValue, setLoginValue] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [smsCode, setSmsCode] = useState('')
  const [smsSent, setSmsSent] = useState(false)
  const { t } = useTranslation('common')

  useEffect(() => {
    setError('')
    setSmsSent(false)
    setSmsCode('')
    if (loginMethod === 'sms') setPassword('')
  }, [loginMethod])

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
    <div className="w-full max-w-[320px] mx-auto">
      <form onSubmit={submit} className="flex flex-col w-full">
        <h1>{t('login')}</h1>
        
        <div className="flex justify-center gap-2 mb-2 mt-4">
           <button 
              type="button" 
              onClick={() => setLoginMethod('password')} 
              className={`px-3 py-1.5 text-xs sm:text-sm rounded transition-colors ${loginMethod === 'password' ? 'bg-[var(--accent)] text-white' : 'bg-gray-200 dark:bg-gray-800 text-[var(--text-strong)]'}`}
           >
              {t('auth_login_method_password')}
           </button>
           <button 
              type="button" 
              onClick={() => setLoginMethod('sms')} 
              className={`px-3 py-1.5 text-xs sm:text-sm rounded transition-colors ${loginMethod === 'sms' ? 'bg-[var(--accent)] text-white' : 'bg-gray-200 dark:bg-gray-800 text-[var(--text-strong)]'}`}
           >
              {t('auth_login_method_sms')}
           </button>
        </div>

        {loginMethod === 'password' ? (
          <>
            <div className={styles.inputBox}>
              <input
                placeholder={t('auth_login_placeholder')}
                value={loginValue}
                onChange={(e) => setLoginValue(e.target.value)}
                onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity(t('auth_fill_field'))}
                onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                required
              />
            </div>
            <div className={styles.inputBox}>
              <input
                className="auth-password-input"
                placeholder={t('password_placeholder')}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity(t('auth_fill_field'))}
                onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                required
              />
            </div>
          </>
        ) : (
          <>
            <div className={`${styles.inputBox} flex gap-2`}>
              <input
                placeholder="+7 (999) 123-45-67"
                type="tel"
                value={loginValue}
                onChange={(e) => setLoginValue(e.target.value)}
                onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity(t('auth_fill_field'))}
                onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                required
              />
              <button
                type="button"
                onClick={handleSendSMS}
                disabled={smsSent || loading}
                className="rounded-md bg-[var(--accent)] px-3 text-white hover:bg-[var(--accent-strong)] disabled:opacity-60 text-sm whitespace-nowrap"
              >
                {smsSent ? t('auth_code_sent') : t('auth_send_code')}
              </button>
            </div>
            {smsSent && (
              <div className={styles.inputBox}>
                <input
                  placeholder={t('auth_sms_code_placeholder')}
                  type="text"
                  value={smsCode}
                  onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity(t('auth_fill_field'))}
                  onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                  maxLength={6}
                  required
                />
              </div>
            )}
          </>
        )}
        
        {error ? <div className="text-sm text-red-500 mb-2">{error}</div> : null}
        
        <button
          type="submit"
          disabled={loading}
          className={styles.btn}
        >
          {loading ? t('auth_logging_in') : t('login')}
        </button>

        <p className="mt-6 mb-2 text-sm text-[var(--text-weak)]">{t('auth_or_login_with')}</p>
        <SocialLoginBlock />
      </form>
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
    <div className="w-full max-w-[320px] mx-auto">
      <form onSubmit={submit} className="flex flex-col w-full">
        <h1>{t('register')}</h1>
        
        <div className={styles.inputBox}>
          <input 
            placeholder={t('email')} 
            type="email"
            value={email} 
            onChange={(e) => setEmail(e.target.value)} 
            onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity(t('auth_fill_field'))}
            onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
            required 
          />
        </div>
        <div className={styles.inputBox}>
          <input 
            placeholder={t('username')} 
            value={username} 
            onChange={(e) => setUsername(e.target.value)} 
            onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity(t('auth_fill_field'))}
            onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
            required 
          />
        </div>
        <div className={styles.inputBox}>
          <input
            className="auth-password-input"
            placeholder={t('password_placeholder')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity(t('auth_fill_field'))}
            onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
            required
          />
        </div>
        
        {error ? <div className="text-sm text-red-500 mb-2">{error}</div> : null}
        
        <button type="submit" disabled={loading} className={styles.btn}>
          {loading ? t('auth_registering') : t('auth_register_button')}
        </button>

        <p className="mt-6 mb-2 text-sm text-[var(--text-weak)]">{t('auth_or_register_with')}</p>
        <SocialLoginBlock />
      </form>
    </div>
  )
}

