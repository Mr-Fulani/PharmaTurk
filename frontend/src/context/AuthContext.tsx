import { createContext, useContext, useEffect, useMemo, useState, useRef } from 'react'
import Cookies from 'js-cookie'
import api, { setPreferredCurrency } from '../lib/api'
import { useCartStore } from '../store/cart'
import { useFavoritesStore } from '../store/favorites'

interface User {
  id: number
  email: string
  username: string
  first_name?: string
  last_name?: string
  phone_number?: string
  currency?: string
}

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (loginValue: string, password: string) => Promise<void> // loginValue может быть email, username или телефон
  register: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  // Будущие методы для SMS и соцсетей
  loginWithSMS?: (phone: string, code: string) => Promise<void>
  loginWithSocial: (provider: 'google' | 'vk', token: string) => Promise<void>
  loginWithTelegram: (telegramData: any) => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const refreshCartRef = useRef(useCartStore.getState().refresh)
  const refreshFavoritesRef = useRef(useFavoritesStore.getState().refresh)

  // Обновляем ref при изменении store
  useEffect(() => {
    refreshCartRef.current = useCartStore.getState().refresh
    refreshFavoritesRef.current = useFavoritesStore.getState().refresh
  }, [])

  useEffect(() => {
    // Попытка получить профиль по access
    const access = Cookies.get('access')
    console.log('AuthContext: checking access token:', access ? 'exists' : 'missing')
    if (!access) {
      setLoading(false)
      return
    }
    api.get('/users/profile').then((r) => {
      const profile = r.data?.[0]
      console.log('AuthContext: profile loaded:', profile ? 'success' : 'failed')
      if (profile) {
        setUser({
          id: profile.id,
          email: profile.user_email,
          username: profile.user_username,
          first_name: profile.first_name,
          last_name: profile.last_name,
          phone_number: profile.phone_number,
          currency: profile.currency
        })
        if (profile.currency) {
          Cookies.set('currency', profile.currency, { sameSite: 'Lax', path: '/' })
          setPreferredCurrency(profile.currency)
        }
        // Обновляем избранное после загрузки профиля пользователя
        refreshFavoritesRef.current()
      }
    }).catch((err) => {
      console.log('AuthContext: profile error:', err?.response?.status)
      // Не удаляем токены на 401 здесь, чтобы избежать принудительного логаута
    }).finally(() => setLoading(false))
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    async login(loginValue, password) {
      // loginValue может быть email, username или телефон
      const res = await api.post('/users/login/', { email: loginValue, password })
      const { tokens, user } = res.data
      if (tokens?.access) Cookies.set('access', tokens.access, { sameSite: 'Lax', path: '/' })
      if (tokens?.refresh) Cookies.set('refresh', tokens.refresh, { sameSite: 'Lax', path: '/' })
      setUser({
        id: user.id,
        email: user.email,
        username: user.username,
        first_name: user.first_name,
        last_name: user.last_name,
        phone_number: user.phone_number,
        currency: user.currency
      })
      if (user.currency) {
        Cookies.set('currency', user.currency, { sameSite: 'Lax', path: '/' })
        setPreferredCurrency(user.currency)
      }
      // Обновляем корзину после входа для переноса товаров с анонимной сессии
      refreshCartRef.current()
      // Обновляем избранное после входа для загрузки избранного пользователя
      refreshFavoritesRef.current()
    },
    async loginWithSocial(provider, token) {
      const res = await api.post('/users/social-auth/', { provider, access_token: token })
      const { tokens, user: userData } = res.data
      if (tokens?.access) Cookies.set('access', tokens.access, { sameSite: 'Lax', path: '/' })
      if (tokens?.refresh) Cookies.set('refresh', tokens.refresh, { sameSite: 'Lax', path: '/' })
      setUser({
        id: userData.id,
        email: userData.email,
        username: userData.username,
        first_name: userData.first_name,
        last_name: userData.last_name,
        phone_number: userData.phone_number,
        currency: userData.currency
      })
      if (userData.currency) {
        Cookies.set('currency', userData.currency, { sameSite: 'Lax', path: '/' })
        setPreferredCurrency(userData.currency)
      }
      refreshCartRef.current()
      refreshFavoritesRef.current()
    },
    async loginWithTelegram(telegramData) {
      const res = await api.post('/users/telegram/login/', telegramData)
      const { tokens, user: userData } = res.data
      if (tokens?.access) Cookies.set('access', tokens.access, { sameSite: 'Lax', path: '/' })
      if (tokens?.refresh) Cookies.set('refresh', tokens.refresh, { sameSite: 'Lax', path: '/' })
      setUser({
        id: userData.id,
        email: userData.email,
        username: userData.username,
        first_name: userData.first_name,
        last_name: userData.last_name,
        phone_number: userData.phone_number,
        currency: userData.currency
      })
      if (userData.currency) {
        Cookies.set('currency', userData.currency, { sameSite: 'Lax', path: '/' })
        setPreferredCurrency(userData.currency)
      }
      refreshCartRef.current()
      refreshFavoritesRef.current()
    },
    async register(email, username, password) {
      const res = await api.post('/users/register/', { email, username, password, password_confirm: password })
      const { tokens, user } = res.data
      if (tokens?.access) Cookies.set('access', tokens.access, { sameSite: 'Lax', path: '/' })
      if (tokens?.refresh) Cookies.set('refresh', tokens.refresh, { sameSite: 'Lax', path: '/' })
      setUser({
        id: user.id,
        email: user.email,
        username: user.username,
        first_name: user.first_name,
        last_name: user.last_name,
        phone_number: user.phone_number,
        currency: user.currency
      })
      if (user.currency) {
        Cookies.set('currency', user.currency, { sameSite: 'Lax', path: '/' })
        setPreferredCurrency(user.currency)
      }
      // Обновляем корзину после регистрации для переноса товаров с анонимной сессии
      refreshCartRef.current()
      // Обновляем избранное после регистрации для загрузки избранного пользователя
      refreshFavoritesRef.current()
    },
    logout() {
      Cookies.remove('access', { path: '/' })
      Cookies.remove('refresh', { path: '/' })
      Cookies.remove('currency', { path: '/' })
      setPreferredCurrency(null)
      setUser(null)
      // Очищаем избранное при выходе
      refreshFavoritesRef.current()
    }
  }), [user, loading])

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
