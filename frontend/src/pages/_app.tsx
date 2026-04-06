import type { AppProps } from 'next/app'
import Head from 'next/head'
import Script from 'next/script'
import '../../styles/globals.css'
import Header from '../components/Header'
import Footer from '../components/Footer'
import CookieBanner from '../components/CookieBanner'
import NavigationProgress from '../components/NavigationProgress'
import { AuthProvider } from '../context/AuthContext'
import { ThemeProvider } from '../context/ThemeContext'
import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { useCartStore } from '../store/cart'
import { initCartSession } from '../lib/api'
import { appWithTranslation } from 'next-i18next'
import { useCookieConsent } from '../hooks/useCookieConsent'
import { gtmPageView } from '../lib/gtm'
import { ga4PageView } from '../lib/gtag'
import { ymPageHit } from '../lib/ym'
// eslint-disable-next-line
const nextI18NextConfig = require('../../next-i18next.config.js')

const YM_ID = process.env.NEXT_PUBLIC_YM_ID
const GA4_ID = process.env.NEXT_PUBLIC_GA4_ID

function App({ Component, pageProps }: AppProps) {
  const router = useRouter()
  const { refresh } = useCartStore()
  const is404 = router.pathname === '/404'
  const { consent } = useCookieConsent()

  useEffect(() => {
    // Гарантируем, что cookie cart_session создана до первого запроса
    initCartSession()
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Отключаем автоматический скролл браузера и Next.js при навигации
  useEffect(() => {
    if (typeof window === 'undefined') return

    // Отключаем автоматический скролл браузера при возврате на вкладку
    if ('scrollRestoration' in window.history) {
      window.history.scrollRestoration = 'manual'
    }

    // Сохраняем позицию скролла перед навигацией
    const handleRouteChangeStart = (url: string) => {
      const currentPath = router.asPath || window.location.pathname + window.location.search
      if (url !== currentPath) {
        sessionStorage.setItem(`scroll_${currentPath}`, String(window.scrollY))
      }
    }

    // Восстанавливаем позицию скролла после навигации
    const handleRouteChangeComplete = (url: string) => {
      const savedScroll = sessionStorage.getItem(`scroll_${url}`)
      if (savedScroll) {
        const scrollY = parseInt(savedScroll, 10)
        // Используем двойной requestAnimationFrame для надежности
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            window.scrollTo({ top: scrollY, behavior: 'auto' })
          })
        })
      }
    }

    router.events.on('routeChangeStart', handleRouteChangeStart)
    router.events.on('routeChangeComplete', handleRouteChangeComplete)

    return () => {
      router.events.off('routeChangeStart', handleRouteChangeStart)
      router.events.off('routeChangeComplete', handleRouteChangeComplete)
    }
  }, [router])

  // ─── Аналитика: pageview при каждой смене маршрута ────────────────────────
  useEffect(() => {
    if (consent !== 'accepted') return

    const handleRouteChangeComplete = (url: string) => {
      gtmPageView(url)
      ga4PageView(url)
      ymPageHit(url)
    }

    router.events.on('routeChangeComplete', handleRouteChangeComplete)
    return () => {
      router.events.off('routeChangeComplete', handleRouteChangeComplete)
    }
  }, [router.events, consent])

  return (
    <AuthProvider>
      <ThemeProvider>
        <Head>
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
          <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        </Head>

        {/* Яндекс.Метрика — загружается только при наличии согласия */}
        {consent === 'accepted' && YM_ID && (
          <Script
            id="yandex-metrika"
            strategy="afterInteractive"
            dangerouslySetInnerHTML={{
              __html: `
(function(m,e,t,r,i,k,a){
  m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
  m[i].l=1*new Date();
  for(var j=0;j<document.scripts.length;j++){
    if(document.scripts[j].src===r){return;}
  }
  k=e.createElement(t),a=e.getElementsByTagName(t)[0];
  k.async=1;k.src=r;a.parentNode.insertBefore(k,a);
})(window,document,'script','https://mc.yandex.ru/metrika/tag.js','ym');

ym(${YM_ID},'init',{
  defer: true,
  clickmap: true,
  trackLinks: true,
  accurateTrackBounce: true,
  webvisor: false
});
              `.trim(),
            }}
          />
        )}

        {/* Google tag (gtag.js) / GA4 — только после согласия на аналитику */}
        {consent === 'accepted' && GA4_ID && (
          <>
            <Script
              src={`https://www.googletagmanager.com/gtag/js?id=${GA4_ID}`}
              strategy="afterInteractive"
            />
            <Script
              id="google-gtag-init"
              strategy="afterInteractive"
              dangerouslySetInnerHTML={{
                __html: `
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${GA4_ID.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}', { send_page_view: true });
                `.trim(),
              }}
            />
          </>
        )}

        <NavigationProgress />

        {is404 ? (
          <Component {...pageProps} />
        ) : (
          <div className="min-h-screen flex flex-col">
            <Header />
            <div className="flex-1 pt-[108px] md:pt-[72px]">
              <Component {...pageProps} />
            </div>
            <Footer initialSettings={(pageProps as Record<string, unknown>)?.footerSettings} />
          </div>
        )}

        {/* Cookie Consent баннер — показывается всем пользователям */}
        <CookieBanner />
      </ThemeProvider>
    </AuthProvider>
  )
}

export default appWithTranslation(App, nextI18NextConfig)
