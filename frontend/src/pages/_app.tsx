import type { AppProps } from 'next/app'
import Head from 'next/head'
import '../../styles/globals.css'
import Header from '../components/Header'
import Footer from '../components/Footer'
import { AuthProvider } from '../context/AuthContext'
import { ThemeProvider } from '../context/ThemeContext'
import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { useCartStore } from '../store/cart'
import { initCartSession } from '../lib/api'
import { appWithTranslation } from 'next-i18next'
// eslint-disable-next-line @typescript-eslint/no-var-requires
const nextI18NextConfig = require('../../next-i18next.config.js')

function App({ Component, pageProps }: AppProps) {
  const router = useRouter()
  const { refresh } = useCartStore()
  const is404 = router.pathname === '/404'
  
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
  return (
    <AuthProvider>
      <ThemeProvider>
        <Head>
          <meta name="viewport" content="width=device-width, initial-scale=1" />
        </Head>
        {is404 ? (
          <Component {...pageProps} />
        ) : (
          <div className="min-h-screen flex flex-col">
            <Header />
            <div className="flex-1">
              <Component {...pageProps} />
            </div>
            <Footer />
          </div>
        )}
      </ThemeProvider>
    </AuthProvider>
  )
}

export default appWithTranslation(App, nextI18NextConfig)
