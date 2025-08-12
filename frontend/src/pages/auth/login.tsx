import { useState } from 'react'
import Head from 'next/head'
import { useAuth } from '../../context/AuthContext'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { t } = useTranslation('common')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      // Проверяем, есть ли параметр next для редиректа
      const next = router.query.next as string
      if (next && next.startsWith('/')) {
        router.push(next)
      } else {
        router.push('/')
      }
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
    <>
      <Head>
        <title>Вход — Turk-Export</title>
      </Head>
      <main className="mx-auto max-w-md p-6">
        <h1 className="text-2xl font-bold">{t('login')}</h1>
        <form onSubmit={submit} className="mt-4 grid gap-3">
          <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder={t('login_or_username')} value={email} onChange={(e)=>setEmail(e.target.value)} required />
          <input className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-gray-400" placeholder={t('password_placeholder')} type="password" value={password} onChange={(e)=>setPassword(e.target.value)} required />
          {error ? <div className="text-sm text-red-600">{error}</div> : null}
          <button type="submit" disabled={loading} className="rounded-md bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-60">{loading ? '...' : t('login')}</button>
        </form>
      </main>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  return { props: { ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])) } }
}
