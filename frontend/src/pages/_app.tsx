import type { AppProps } from 'next/app'
import '../../styles/globals.css'
import Header from '../components/Header'
import { AuthProvider } from '../context/AuthContext'
import { useEffect } from 'react'
import { useCartStore } from '../store/cart'
import { initCartSession } from '../lib/api'

export default function App({ Component, pageProps }: AppProps) {
  const { refresh } = useCartStore()
  useEffect(() => {
    // Гарантируем, что cookie cart_session создана до первого запроса
    initCartSession()
    refresh()
  }, [refresh])
  return (
    <AuthProvider>
      <Header />
      <Component {...pageProps} />
    </AuthProvider>
  )
}
