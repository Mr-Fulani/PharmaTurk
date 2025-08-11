import Head from 'next/head'
import { useRouter } from 'next/router'

export default function CheckoutSuccess() {
  const router = useRouter()
  const number = (router.query?.number as string) || ''
  return (
    <>
      <Head><title>Заказ оформлен — Turk-Export</title></Head>
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
        <h1>Спасибо за заказ!</h1>
        {number ? (
          <p>Номер вашего заказа: <b>{number}</b></p>
        ) : (
          <p>Заказ успешно создан.</p>
        )}
        <a href="/" style={{ display: 'inline-block', marginTop: 12 }}>На главную</a>
      </main>
    </>
  )
}


