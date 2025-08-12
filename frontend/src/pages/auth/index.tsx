import { useState } from 'react'
import Head from 'next/head'
import { useAuth } from '../../context/AuthContext'
import { useRouter } from 'next/router'

export default function AuthIndexPage() {
  const router = useRouter()
  const tabParam = (router.query.tab as string) || 'login'
  const [tab, setTab] = useState<'login' | 'register'>(tabParam === 'register' ? 'register' : 'login')

  const switchTo = (nextTab: 'login' | 'register') => {
    setTab(nextTab)
    const q = { ...router.query, tab: nextTab }
    router.replace({ pathname: '/auth', query: q }, undefined, { shallow: true })
  }

  return (
    <>
      <Head>
        <title>{tab === 'login' ? 'Вход' : 'Регистрация'} — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-md p-6">
        <div className="mb-4 inline-flex rounded-md border border-gray-300 p-1">
          <button onClick={()=>switchTo('login')} className={`rounded px-3 py-1.5 text-sm ${tab==='login' ? 'bg-violet-600 text-white' : 'text-gray-700 hover:bg-gray-50'}`}>Войти</button>
          <button onClick={()=>switchTo('register')} className={`rounded px-3 py-1.5 text-sm ${tab==='register' ? 'bg-violet-600 text-white' : 'text-gray-700 hover:bg-gray-50'}`}>Регистрация</button>
        </div>
        {tab === 'login' ? <LoginForm /> : <RegisterForm />}
      </main>
    </>
  )
}

function LoginForm() {
  const { login } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      const next = router.query.next as string
      if (next && next.startsWith('/')) router.push(next)
      else router.push('/')
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

  return (
    <form onSubmit={submit} className="grid gap-3">
      <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder="Email" value={email} onChange={(e)=>setEmail(e.target.value)} required />
      <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder="Пароль" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} required />
      {error ? <div className="text-sm text-red-600">{error}</div> : null}
      <button type="submit" disabled={loading} className="rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-60">{loading ? 'Входим...' : 'Войти'}</button>
    </form>
  )
}

function RegisterForm() {
  const { register } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(email, username, password)
      const next = router.query.next as string
      if (next && next.startsWith('/')) router.push(next)
      else router.push('/')
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
    <form onSubmit={submit} className="grid gap-3">
      <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder="Email" value={email} onChange={(e)=>setEmail(e.target.value)} required />
      <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder="Имя пользователя" value={username} onChange={(e)=>setUsername(e.target.value)} required />
      <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder="Пароль (мин. 8 знаков, буквы и цифры)" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} required />
      {error ? <div className="text-sm text-red-600">{error}</div> : null}
      <button type="submit" disabled={loading} className="rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-60">{loading ? 'Регистрируем...' : 'Зарегистрироваться'}</button>
    </form>
  )
}


