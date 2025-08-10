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
      router.push('/')
    } catch (e: any) {
      setError('Ошибка регистрации')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Head>
        <title>Регистрация — Turk-Export</title>
      </Head>
      <main style={{ maxWidth: 420, margin: '40px auto', padding: 24 }}>
        <h1>Регистрация</h1>
        <form onSubmit={submit} style={{ display: 'grid', gap: 12 }}>
          <input placeholder="Email" value={email} onChange={(e)=>setEmail(e.target.value)} required />
          <input placeholder="Имя пользователя" value={username} onChange={(e)=>setUsername(e.target.value)} required />
          <input placeholder="Пароль" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} required />
          {error ? <div style={{ color: 'red' }}>{error}</div> : null}
          <button type="submit" disabled={loading}>{loading ? 'Регистрируем...' : 'Зарегистрироваться'}</button>
        </form>
      </main>
    </>
  )
}
