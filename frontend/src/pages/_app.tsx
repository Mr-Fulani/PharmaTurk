import type { AppProps } from 'next/app'
import '../../styles/globals.css'
import Header from '../components/Header'
import { AuthProvider } from '../context/AuthContext'

export default function App({ Component, pageProps }: AppProps) {
  return (
    <AuthProvider>
      <Header />
      <Component {...pageProps} />
    </AuthProvider>
  )
}
