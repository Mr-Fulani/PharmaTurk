import Head from 'next/head'
import Link from 'next/link'
import axios from 'axios'

interface Product {
  id: number
  name: string
  slug: string
  price: string | null
  currency: string
  main_image_url?: string | null
}

export default function Home({ products }: { products: Product[] }) {
  return (
    <>
      <Head>
        <title>Turk-Export</title>
      </Head>
      <main style={{ maxWidth: 960, margin: '0 auto', padding: 24 }}>
        <h1>Turk-Export</h1>
        <p>Каталог товаров</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          {products.map((p) => (
            <div key={p.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
              {p.main_image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={p.main_image_url} alt={p.name} style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 6 }} />
              ) : null}
              <h3 style={{ marginTop: 8 }}>{p.name}</h3>
              <div style={{ fontWeight: 600 }}>{p.price ? `${p.price} ${p.currency}` : 'Цена по запросу'}</div>
              <Link href={`/product/${p.slug}`} style={{ display: 'inline-block', marginTop: 8 }}>Подробнее</Link>
            </div>
          ))}
        </div>
      </main>
    </>
  )
}

export async function getServerSideProps() {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const res = await axios.get(`${base}/api/catalog/products/`)
    const data = res.data
    const products: Product[] = Array.isArray(data) ? data : (data.results || [])
    return { props: { products } }
  } catch (e) {
    return { props: { products: [] } }
  }
}
