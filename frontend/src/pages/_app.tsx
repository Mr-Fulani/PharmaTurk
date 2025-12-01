import type { AppProps } from 'next/app'
import '../../styles/globals.css'
import Header from '../components/Header'
import Footer from '../components/Footer'
import { AuthProvider } from '../context/AuthContext'
import { useEffect } from 'react'
import { useCartStore } from '../store/cart'
import { initCartSession } from '../lib/api'
import { appWithTranslation } from 'next-i18next'
// eslint-disable-next-line @typescript-eslint/no-var-requires
const nextI18NextConfig = require('../../next-i18next.config.js')

function App({ Component, pageProps }: AppProps) {
  const { refresh } = useCartStore()
  useEffect(() => {
    // Гарантируем, что cookie cart_session создана до первого запроса
    initCartSession()
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return (
    <AuthProvider>
      <div className="min-h-screen flex flex-col">
        <Header />
        <div className="flex-1">
          <Component {...pageProps} />
        </div>
        <Footer />
      </div>
    </AuthProvider>
  )
}

export default appWithTranslation(App, nextI18NextConfig)
