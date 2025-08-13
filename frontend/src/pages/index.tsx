import Head from 'next/head'
import Link from 'next/link'
import axios from 'axios'
import { useState } from 'react'
import AddToCartButton from '../components/AddToCartButton'
import Section from '../components/Section'
import ProductCard from '../components/ProductCard'
import Sidebar from '../components/Sidebar'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'

interface Product {
  id: number
  name: string
  slug: string
  price: string | null
  currency: string
  main_image_url?: string | null
}

interface Category {
  id: number
  name: string
  slug: string
  count?: number
}

interface Brand {
  id: number
  name: string
  count?: number
}

export default function Home({ 
  products, 
  categories = [], 
  brands = [] 
}: { 
  products: Product[]
  categories: Category[]
  brands: Brand[]
}) {
  const { t } = useTranslation('common')
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)
  const [selectedBrand, setSelectedBrand] = useState<number | null>(null)
  const [priceRange, setPriceRange] = useState<{ min: number | null; max: number | null }>({ min: null, max: null })
  const [sortBy, setSortBy] = useState('name_asc')
  const [inStockOnly, setInStockOnly] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handlePriceChange = (min: number | null, max: number | null) => {
    setPriceRange({ min, max })
  }

  return (
    <>
      <Head>
        <title>PharmaTurk</title>
      </Head>
      <div className="flex">
        {/* Sidebar */}
        <Sidebar
          categories={categories}
          brands={brands}
          onCategoryChange={setSelectedCategory}
          onBrandChange={setSelectedBrand}
          onPriceChange={handlePriceChange}
          onSortChange={setSortBy}
          onAvailabilityChange={setInStockOnly}
          selectedCategory={selectedCategory}
          selectedBrand={selectedBrand}
          priceRange={priceRange}
          sortBy={sortBy}
          inStockOnly={inStockOnly}
          isOpen={sidebarOpen}
          onToggle={() => setSidebarOpen(!sidebarOpen)}
        />
        
        {/* Main Content */}
        <main className="flex-1">
          {/* Mobile sidebar toggle */}
          <div className="md:hidden p-4">
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex items-center space-x-2 px-4 py-2 bg-violet-600 text-white rounded-md hover:bg-violet-700 transition-colors duration-200"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
              <span>Фильтры</span>
            </button>
          </div>
          <Section title={t('section_daily_deals', 'Товары дня')}>
            <div className="no-scrollbar mt-2 grid grid-flow-col gap-4 overflow-x-auto px-1 [grid-auto-columns:minmax(240px,1fr)]">
              {products.slice(0, 8).map((p) => (
                <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} imageUrl={p.main_image_url} />
              ))}
            </div>
          </Section>
          <Section title={t('section_best_sellers', 'Хиты продаж')}>
            <div className="no-scrollbar mt-2 grid grid-flow-col gap-4 overflow-x-auto px-1 [grid-auto-columns:minmax(240px,1fr)]">
              {products.slice(8, 16).map((p) => (
                <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} imageUrl={p.main_image_url} />
              ))}
            </div>
          </Section>
        </main>
      </div>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    
    // Загружаем продукты
    const productsRes = await axios.get(`${base}/api/catalog/products`)
    const productsData = productsRes.data
    const products: Product[] = Array.isArray(productsData) ? productsData : (productsData.results || [])
    
    // Загружаем категории
    let categories: Category[] = []
    try {
      const categoriesRes = await axios.get(`${base}/api/catalog/categories`)
      const categoriesData = categoriesRes.data
      categories = Array.isArray(categoriesData) ? categoriesData : (categoriesData.results || [])
    } catch (e) {
      console.log('Failed to load categories:', e)
    }
    
    // Загружаем бренды
    let brands: Brand[] = []
    try {
      const brandsRes = await axios.get(`${base}/api/catalog/brands`)
      const brandsData = brandsRes.data
      brands = Array.isArray(brandsData) ? brandsData : (brandsData.results || [])
    } catch (e) {
      console.log('Failed to load brands:', e)
    }
    
    return { 
      props: { 
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), 
        products,
        categories,
        brands
      } 
    }
  } catch (e) {
    return { 
      props: { 
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), 
        products: [],
        categories: [],
        brands: []
      } 
    }
  }
}
