import { useState } from 'react'
import Head from 'next/head'
import { useAuth } from '../../context/AuthContext'
import { useRouter } from 'next/router'

export default function RegisterPage() {
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
      // Проверяем, есть ли параметр next для редиректа
      const next = router.query.next as string
      if (next && next.startsWith('/')) {
        router.push(next)
      } else {
        router.push('/')
      }
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
    <>
      <Head>
        <title>Регистрация — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-md p-6">
        <h1 className="text-2xl font-bold">Регистрация</h1>
        <form onSubmit={submit} className="mt-4 grid gap-3">
          <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder="Email" value={email} onChange={(e)=>setEmail(e.target.value)} required />
          <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder="Имя пользователя" value={username} onChange={(e)=>setUsername(e.target.value)} required />
          <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder="Пароль (мин. 8 знаков, буквы и цифры)" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} required />
          {error ? <div className="text-sm text-red-600">{error}</div> : null}
          <button type="submit" disabled={loading} className="rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-60">{loading ? 'Регистрируем...' : 'Зарегистрироваться'}</button>
        </form>
      </main>
    </>
  )
}
