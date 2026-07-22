import { useState, useEffect, useRef, useCallback, useId } from 'react'
import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useAuth } from '../../context/AuthContext'
import { useRouter } from 'next/router'
import styles from './Auth.module.css'
import { SITE_NAME } from '../../lib/siteMeta'
import { sanitizeNextPath } from '../../lib/authRedirect'

// ─── Утилита: редирект после входа ──────────────────────────────────────────

function usePostLoginRedirect() {
  const router = useRouter()
  return useCallback(() => {
    const next = sanitizeNextPath(router.query.next)
    if (next) router.push(next)
    else router.push('/')
  }, [router])
}

let googleIdentityScriptPromise: Promise<void> | null = null

function loadGoogleIdentityScript() {
  if (typeof window === 'undefined') return Promise.reject(new Error('Google SDK is only available in the browser'))
  if ((window as any).google?.accounts?.id) return Promise.resolve()
  if (googleIdentityScriptPromise) return googleIdentityScriptPromise

  googleIdentityScriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-google-identity-sdk="true"]')
    const script = existing || document.createElement('script')

    const handleLoad = () => {
      if ((window as any).google?.accounts?.id) resolve()
      else reject(new Error('Google Identity SDK loaded without accounts.id'))
    }
    const handleError = () => reject(new Error('Не удалось загрузить Google Identity SDK'))

    script.addEventListener('load', handleLoad, { once: true })
    script.addEventListener('error', handleError, { once: true })

    if (!existing) {
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.dataset.googleIdentitySdk = 'true'
      document.head.appendChild(script)
    }
  }).catch((error) => {
    googleIdentityScriptPromise = null
    throw error
  })

  return googleIdentityScriptPromise
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
        <title>{`${tab === 'login' ? t('login') : t('register')} — ${SITE_NAME}`}</title>
        <meta name="robots" content="noindex, nofollow" />
      </Head>
      <main className="flex min-h-[80vh] items-center justify-center p-4">
        <div className={`${styles.container} ${tab === 'register' ? styles.active : ''}`}>
          
          <div className={`${styles.formBox} ${styles.login}`}>
            <LoginForm socialLoginActive={tab === 'login'} />
          </div>

          <div className={`${styles.formBox} ${styles.register}`}>
            <RegisterForm socialLoginActive={tab === 'register'} />
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
  const redirect = usePostLoginRedirect()
  const containerRef = useRef<HTMLDivElement>(null)
  const { t } = useTranslation('common')
  const reactId = useId()
  const uniqueId = `telegram-login-${reactId.replace(/:/g, '')}`

  useEffect(() => {
    const container = containerRef.current
    const handleTelegramAuth = async (user: any) => {
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
    ;(window as any).onTelegramAuth = handleTelegramAuth

    const botName = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME
    if (botName && container && container.children.length === 0) {
      const script = document.createElement('script')
      script.src = 'https://telegram.org/js/telegram-widget.js?22'
      script.setAttribute('data-telegram-login', botName)
      script.setAttribute('data-size', 'small')
      script.setAttribute('data-radius', '4')
      script.setAttribute('data-request-access', 'write')
      script.setAttribute('data-userpic', 'false')
      script.setAttribute('data-onauth', 'onTelegramAuth(user)')
      script.id = uniqueId
      script.async = true
      
      // Очищаем контейнер перед добавлением скрипта
      container.replaceChildren()
      container.appendChild(script)
    }

    const intervalId = setInterval(() => {
      const wrapper = document.getElementById(uniqueId + '-wrapper')
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

    return () => {
      clearInterval(intervalId)
      if ((window as any).onTelegramAuth === handleTelegramAuth) delete (window as any).onTelegramAuth
      container?.replaceChildren()
    }
  }, [loginWithTelegram, redirect, t, uniqueId])

  return (
    <div className="relative flex h-10 w-10 items-center justify-center overflow-hidden hover:opacity-80 transition-opacity">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#2AABEE] text-white shadow-sm pointer-events-none relative z-10">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M22.5 3.5L2.8 11.1c-1 .4-1 .9-.2 1.1l5 1.6 1.9 5.7c.2.6.3.8.6.8.3 0 .5-.2.8-.5l2.5-2.4 5.2 3.9c1 .6 1.7.3 2-1l3.6-16.9c.4-1.6-.6-2.3-1.7-1.8zM9.3 14.9l-.7 2.6-.4-3.6 9.7-6.2-8.6 7.2z" />
        </svg>
      </div>
      <div id={uniqueId + '-wrapper'} ref={containerRef} className="telegram-widget-wrapper absolute inset-0 z-50 flex items-center justify-center" style={{ cursor: 'pointer', pointerEvents: 'auto' }} />
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
  const containerRef = useRef<HTMLDivElement>(null)
  const googleResponseRef = useRef<(response: any) => Promise<void>>(async () => {})
  const translateRef = useRef(t)

  const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID

  const handleGoogleResponse = useCallback(async (response: any) => {
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
  }, [loginWithSocial, redirect, t])
  googleResponseRef.current = handleGoogleResponse
  translateRef.current = t

  useEffect(() => {
    if (!googleClientId) return

    let cancelled = false
    const container = containerRef.current

    const initGoogle = async () => {
      try {
        await loadGoogleIdentityScript()
        if (cancelled || !container) return

        const google = (window as any).google?.accounts?.id
        if (!google) throw new Error('Google Identity SDK недоступен')

        // GIS требует initialize до renderButton. Инициализируем только текущую,
        // реально смонтированную кнопку вместо обхода скрытых форм страницы.
        google.initialize({
          client_id: googleClientId,
          callback: (response: any) => googleResponseRef.current(response),
          auto_select: false,
          cancel_on_tap_outside: true,
        })
        container.replaceChildren()
        google.renderButton(container, {
          theme: 'outline',
          size: 'large',
          type: 'icon',
          shape: 'circle',
        })
      } catch (e: any) {
        if (!cancelled) setError(e?.message || translateRef.current('auth_social_error', 'Ошибка входа через Google'))
      }
    }

    initGoogle()
    return () => {
      cancelled = true
      container?.replaceChildren()
    }
  }, [googleClientId])

  if (!googleClientId) return null

  return (
    <div className="flex flex-col items-center gap-1 hover:opacity-80 transition-opacity" style={{ colorScheme: 'light' }}>
      <div
        ref={containerRef}
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
  const [useFallbackLogin, setUseFallbackLogin] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const vkidRef = useRef<any>(null)
  const authHandlersRef = useRef({ loginWithSocial, redirect, t })

  useEffect(() => {
    authHandlersRef.current = { loginWithSocial, redirect, t }
  }, [loginWithSocial, redirect, t])

  const vkAppId = process.env.NEXT_PUBLIC_VK_APP_ID

  const completeVKLogin = useCallback(async (VKID: any, payload: any) => {
    setLoading(true)
    setError('')
    try {
      const data = await VKID.Auth.exchangeCode(payload.code, payload.device_id)
      await authHandlersRef.current.loginWithSocial('vk', data.access_token)
      authHandlersRef.current.redirect()
    } catch (e: any) {
      const raw = e?.response?.data?.detail || e?.error_description || e?.error || e?.message || ''
      const msg = String(raw).toLowerCase().includes('csrf')
        ? authHandlersRef.current.t('auth_csrf_error')
        : (raw || authHandlersRef.current.t('auth_social_error', 'Ошибка входа через ВКонтакте'))
      setError(String(msg))
    } finally {
      setLoading(false)
    }
  }, [])

  const handleFallbackLogin = useCallback(async () => {
    if (!useFallbackLogin || loading) return
    const VKID = vkidRef.current
    if (!VKID) {
      setError(authHandlersRef.current.t('auth_vk_open_error', 'Не удалось открыть VK. Попробуйте ещё раз.'))
      return
    }

    setLoading(true)
    setError('')
    try {
      const payload = await VKID.Auth.login()
      if (payload?.code && payload?.device_id) await completeVKLogin(VKID, payload)
      else setLoading(false)
    } catch (e: any) {
      const raw = e?.error_description || e?.error || e?.message || ''
      const isPopupError = Number(e?.code) === 101 || String(raw).toLowerCase().includes('new tab')
      setError(isPopupError
        ? authHandlersRef.current.t('auth_vk_browser_error', 'Не удалось открыть VK. Попробуйте войти во внешнем браузере.')
        : authHandlersRef.current.t('auth_vk_open_error', 'Не удалось открыть VK. Попробуйте ещё раз.'))
      setLoading(false)
    }
  }, [completeVKLogin, loading, useFallbackLogin])

  useEffect(() => {
    if (!vkAppId) return

    let cancelled = false
    let oneTap: any = null
    const container = containerRef.current
    const originalFetch = window.fetch
    const guardedFetch: typeof window.fetch = async (input, init) => {
      const requestUrl = typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : input.url
      let isVkidTelemetry = false

      try {
        const url = new URL(requestUrl, window.location.href)
        isVkidTelemetry = (url.hostname === 'id.vk.ru' || url.hostname === 'id.vk.com')
          && (url.pathname === '/stat_events_vkid_sdk' || url.pathname === '/vkid_sdk_get_config')
      } catch {
        // Для некорректного URL сохраняем стандартное поведение fetch.
      }

      try {
        return await originalFetch(input, init)
      } catch (fetchError) {
        if (!isVkidTelemetry) throw fetchError
        // Эти запросы относятся только к статистике SDK. Если WebView их блокирует,
        // возвращаем безопасный ответ вместо необработанного Promise rejection.
        return new Response(JSON.stringify({ response: { active: 0 } }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
    }
    window.fetch = guardedFetch
    const handleVkidTelemetryFailure = (event: PromiseRejectionEvent) => {
      const message = String(event.reason?.message || '')
      const stack = String(event.reason?.stack || '')
      const isBlockedTelemetry = message === 'Failed to fetch'
        && stack.includes('@vkid/sdk')
        && stack.includes('ProductionStatsCollector')

      if (isBlockedTelemetry) {
        // В некоторых WebView заблокирована только статистика VK ID. Это не должно
        // ронять всю страницу и не влияет на LOGIN_SUCCESS/exchangeCode.
        event.preventDefault()
        console.warn('VKID telemetry request was blocked by the browser')
      }
    }
    window.addEventListener('unhandledrejection', handleVkidTelemetryFailure)

    const initVK = async () => {
      try {
        const VKID = await import('@vkid/sdk')
        if (cancelled || !container) return
        vkidRef.current = VKID

        VKID.Config.init({
          app: Number(vkAppId),
          redirectUrl: window.location.origin + '/auth/vk-callback',
          responseMode: VKID.ConfigResponseMode.Callback,
          source: VKID.ConfigSource.LOWCODE,
          scope: '',
        })

        oneTap = new VKID.OneTap()
        container.replaceChildren()
        oneTap.render({
          container,
          showAlternativeLogin: false,
          styles: { width: 44, height: 44 },
        })
        .on(VKID.WidgetEvents.ERROR, (err: any) => {
          if (cancelled) return
          console.warn('VKID SDK Widget Error:', err)
          oneTap?.close?.()
          setUseFallbackLogin(true)
          // Переключение на резервный вход происходит незаметно: техническая
          // ошибка виджета не должна отображаться рядом с иконкой.
          setError('')
        })
        .on(VKID.OneTapInternalEvents.LOGIN_SUCCESS, function (payload: any) {
          if (cancelled) return
          void completeVKLogin(VKID, payload)
        })
      } catch (e: any) {
        if (!cancelled) {
          console.warn('VKID SDK initialization error:', e)
          setError(e?.message || authHandlersRef.current.t('auth_social_error', 'Ошибка входа через ВКонтакте'))
        }
      }
    }

    initVK()
    return () => {
      cancelled = true
      window.removeEventListener('unhandledrejection', handleVkidTelemetryFailure)
      if (window.fetch === guardedFetch) window.fetch = originalFetch
      oneTap?.close?.()
      container?.replaceChildren()
    }
  }, [completeVKLogin, vkAppId])

  if (!vkAppId) return null

  return (
    <div
      className={`relative flex h-10 w-10 items-center justify-center rounded-full bg-[#0077FF] shadow-sm hover:opacity-80 transition-opacity flex-shrink-0 ${loading ? 'opacity-60 grayscale cursor-not-allowed' : ''}`}
      onClick={useFallbackLogin ? handleFallbackLogin : undefined}
      role={useFallbackLogin ? 'button' : undefined}
      aria-label={useFallbackLogin ? t('auth_vk_login', 'Войти через ВКонтакте') : undefined}
    >
      {/* Настоящая SVG-иконка, которую видит пользователь */}
      <img src="/vk.svg" alt="VK" aria-hidden="true" className="h-[22px] w-[22px] object-cover pointer-events-none z-0" />
      
      {/* Скрытый виджет VK SDK, который безопасно перехватывает клик (без Security Error!) */}
      <div
        ref={containerRef}
        className={`absolute inset-0 z-10 flex items-center justify-center overflow-hidden cursor-pointer ${(loading || useFallbackLogin) ? 'pointer-events-none' : ''}`}
        style={{ opacity: 0.01 }} // opacity-0 иногда блокируется браузерами как clickjacking
        title={t('auth_vk_login', 'Войти через ВКонтакте')}
      />
      {error && (
        <p
          role="alert"
          className="absolute left-1/2 top-full z-[60] mt-2 w-64 -translate-x-1/2 rounded-md border border-red-200 bg-white px-3 py-2 text-center text-xs leading-4 text-red-600 shadow-md dark:border-red-900 dark:bg-gray-900 dark:text-red-400"
        >
          {error}
        </p>
      )}
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

function LoginForm({ socialLoginActive }: { socialLoginActive: boolean }) {
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
        {socialLoginActive && <SocialLoginBlock />}
      </form>
    </div>
  )
}

// ─── Форма регистрации ────────────────────────────────────────────────────────

function RegisterForm({ socialLoginActive }: { socialLoginActive: boolean }) {
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
        {socialLoginActive && <SocialLoginBlock />}
      </form>
    </div>
  )
}
