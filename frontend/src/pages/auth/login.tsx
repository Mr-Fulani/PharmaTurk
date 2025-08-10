import { useState } from 'react'
import Head from 'next/head'
import { useAuth } from '../../context/AuthContext'
import { useRouter } from 'next/router'

export default function LoginPage() {
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
      router.push('/')
    } catch (e: any) {
      setError('Неверные учетные данные')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Head>
        <title>Вход — Turk-Export</title>
      </Head>
      <main style={{ maxWidth: 420, margin: '40px auto', padding: 24 }}>
        <h1>Вход</h1>
        <form onSubmit={submit} style={{ display: 'grid', gap: 12 }}>
          <input placeholder="Email" value={email} onChange={(e)=>setEmail(e.target.value)} required />
          <input placeholder="Пароль" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} required />
          {error ? <div style={{ color: 'red' }}>{error}</div> : null}
          <button type="submit" disabled={loading}>{loading ? 'Входим...' : 'Войти'}</button>
        </form>
      </main>
    </>
  )
}
