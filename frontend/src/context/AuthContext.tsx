import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import Cookies from 'js-cookie'
import api from '../lib/api'

interface User {
  id: number
  email: string
  username: string
}

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Попытка получить профиль по access
    const access = Cookies.get('access')
    if (!access) {
      setLoading(false)
      return
    }
    api.get('/users/profile/').then((r) => {
      const profile = r.data?.[0]
      if (profile) {
        setUser({ id: profile.id, email: profile.user_email, username: profile.user_username })
      }
    }).finally(() => setLoading(false))
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    async login(email, password) {
      const res = await api.post('/users/login/', { email, password })
      const { tokens, user } = res.data
      if (tokens?.access) Cookies.set('access', tokens.access, { sameSite: 'Lax' })
      if (tokens?.refresh) Cookies.set('refresh', tokens.refresh, { sameSite: 'Lax' })
      setUser({ id: user.id, email: user.email, username: user.username })
    },
    async register(email, username, password) {
      const res = await api.post('/users/register/', { email, username, password, password_confirm: password })
      const { tokens, user } = res.data
      if (tokens?.access) Cookies.set('access', tokens.access, { sameSite: 'Lax' })
      if (tokens?.refresh) Cookies.set('refresh', tokens.refresh, { sameSite: 'Lax' })
      setUser({ id: user.id, email: user.email, username: user.username })
    },
    logout() {
      Cookies.remove('access')
      Cookies.remove('refresh')
      setUser(null)
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
