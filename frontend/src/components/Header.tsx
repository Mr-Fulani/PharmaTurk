import Link from 'next/link'
import { useRouter } from 'next/router'
import { useAuth } from '../context/AuthContext'

export default function Header() {
  const router = useRouter()
  const path = router.pathname
  const { user, logout } = useAuth()

  return (
    <header style={{
      borderBottom: '1px solid #eee',
      background: '#fff',
      position: 'sticky',
      top: 0,
      zIndex: 10
    }}>
      <div style={{
        maxWidth: 960,
        margin: '0 auto',
        padding: '12px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <Link href="/" style={{
          fontWeight: 700,
          fontSize: 18,
          textDecoration: 'none',
          color: '#111'
        }}>
          Turk-Export
        </Link>
        <nav style={{ display: 'flex', gap: 16 }}>
          <Link href="/" style={{
            color: path === '/' ? '#111' : '#555',
            textDecoration: 'none'
          }}>Главная</Link>
          <Link href="/categories" style={{
            color: path.startsWith('/categories') ? '#111' : '#555',
            textDecoration: 'none'
          }}>Категории</Link>
          <Link href="/cart" style={{
            color: path.startsWith('/cart') ? '#111' : '#555',
            textDecoration: 'none'
          }}>Корзина</Link>
          {user ? (
            <button onClick={logout} style={{ border: '1px solid #ddd', borderRadius: 6, padding: '6px 10px', background: '#fafafa', cursor: 'pointer' }}>Выйти</button>
          ) : (
            <>
              <Link href="/auth/login" style={{ color: path.startsWith('/auth/login') ? '#111' : '#555', textDecoration: 'none' }}>Войти</Link>
              <Link href="/auth/register" style={{ color: path.startsWith('/auth/register') ? '#111' : '#555', textDecoration: 'none' }}>Регистрация</Link>
            </>
          )}
        </nav>
      </div>
    </header>
  )
}
