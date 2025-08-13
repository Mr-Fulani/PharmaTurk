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
  const [sortBy, setSortBy] = useState('name_asc')
  const [inStockOnly, setInStockOnly] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const productsPerPage = 12

  return (
    <>
      <Head>
        <title>PharmaTurk</title>
      </Head>
      <div className="flex gap-6">
        {/* Sidebar */}
        <Sidebar
          categories={categories}
          brands={brands}
          onCategoryChange={setSelectedCategory}
          onBrandChange={setSelectedBrand}
          onSortChange={setSortBy}
          onAvailabilityChange={setInStockOnly}
          selectedCategory={selectedCategory}
          selectedBrand={selectedBrand}
          sortBy={sortBy}
          inStockOnly={inStockOnly}
          isOpen={sidebarOpen}
          onToggle={() => setSidebarOpen(!sidebarOpen)}
        />
        
        {/* Main Content */}
        <main className="flex-1 p-6">
          {/* Mobile sidebar toggle */}
          <div className="md:hidden mb-4">
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
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 mt-4">
              {products
                .slice((currentPage - 1) * productsPerPage, currentPage * productsPerPage)
                .map((p) => (
                  <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} imageUrl={p.main_image_url} />
                ))}
            </div>
            
            {/* Пагинация */}
            {products.length > productsPerPage && (
              <div className="flex justify-center mt-8">
                <div className="flex space-x-2">
                  <button
                    onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                    disabled={currentPage === 1}
                    className="px-4 py-2 text-sm font-medium text-gray-500 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                  >
                    Назад
                  </button>
                  
                  {Array.from({ length: Math.ceil(products.length / productsPerPage) }, (_, i) => i + 1).map((page) => (
                    <button
                      key={page}
                      onClick={() => setCurrentPage(page)}
                      className={`px-4 py-2 text-sm font-medium rounded-md transition-colors duration-200 ${
                        currentPage === page
                          ? 'bg-violet-600 text-white'
                          : 'text-gray-700 bg-white border border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      {page}
                    </button>
                  ))}
                  
                  <button
                    onClick={() => setCurrentPage(Math.min(Math.ceil(products.length / productsPerPage), currentPage + 1))}
                    disabled={currentPage === Math.ceil(products.length / productsPerPage)}
                    className="px-4 py-2 text-sm font-medium text-gray-500 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                  >
                    Вперед
                  </button>
                </div>
              </div>
            )}
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
