import Head from 'next/head'
import Link from 'next/link'
import axios from 'axios'
import { useState } from 'react'
import { useRouter } from 'next/router'
import AddToCartButton from '../components/AddToCartButton'
// import Section from '../components/Section'
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
  totalCount,
  page,
  categories = [],
  brands = []
}: {
  products: Product[]
  totalCount: number
  page: number
  categories: Category[]
  brands: Brand[]
}) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)
  const [selectedBrand, setSelectedBrand] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState('name_asc')
  const [inStockOnly, setInStockOnly] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const productsPerPage = 24
  const currentPage = Number(page) || 1
  const totalPages = Math.max(1, Math.ceil((Number(totalCount) || 0) / productsPerPage))

  const goToPage = (nextPage: number) => {
    const p = Math.min(Math.max(1, nextPage), totalPages)
    router.push({ pathname: '/', query: { ...router.query, page: p } })
  }

  return (
    <>
      <Head>
        <title>PharmaTurk</title>
      </Head>
      <div className="mx-auto flex max-w-6xl gap-6 px-6">
        {/* Sidebar */}
        <div className="hidden md:block mt-6">
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
            isOpen={true}
            onToggle={() => {}}
          />
        </div>
        
        {/* Mobile Sidebar */}
        <div className="md:hidden">
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
        </div>
        
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

          {/* Banner */}
          <div className="relative mb-8 rounded-xl overflow-hidden shadow-lg">
            <div className="bg-gradient-to-r from-violet-600 via-purple-600 to-indigo-600 h-48 md:h-64 flex items-center justify-center">
              <div className="text-center text-white px-6">
                <h1 className="text-3xl md:text-5xl font-bold mb-4">
                  PharmaTurk
                </h1>
                <p className="text-lg md:text-xl opacity-90 mb-6">
                  Ваш надежный партнер в мире фармацевтики
                </p>
                <div className="space-x-4">
                  <button className="bg-white text-violet-600 px-6 py-3 rounded-lg font-semibold hover:bg-gray-100 transition-colors duration-200">
                    Каталог товаров
                  </button>
                  <button className="border-2 border-white text-white px-6 py-3 rounded-lg font-semibold hover:bg-white hover:text-violet-600 transition-colors duration-200">
                    Узнать больше
                  </button>
                </div>
              </div>
            </div>
          </div>
          
          <div className="mt-2 w-full">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 gap-7">
              {products.map((p) => (
                <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} imageUrl={p.main_image_url} />
              ))}
            </div>

            {totalPages > 1 && (
              <div className="flex justify-center mt-10">
                <div className="flex space-x-2">
                  <button
                    onClick={() => goToPage(currentPage - 1)}
                    disabled={currentPage <= 1}
                    className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                  >
                    Назад
                  </button>
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                    <button
                      key={p}
                      onClick={() => goToPage(p)}
                      className={`px-4 py-2 text-sm font-medium rounded-md transition-colors duration-200 ${currentPage === p ? 'bg-violet-600 text-white' : 'text-gray-700 bg-white border border-gray-300 hover:bg-gray-50'}`}
                    >
                      {p}
                    </button>
                  ))}
                  <button
                    onClick={() => goToPage(currentPage + 1)}
                    disabled={currentPage >= totalPages}
                    className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                  >
                    Вперед
                  </button>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </>
  )
}

export async function getServerSideProps(ctx: any) {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const page = Number(ctx.query?.page || 1)
    const pageSize = 24
    
    // Загружаем продукты с пагинацией
    const productsRes = await axios.get(`${base}/api/catalog/products`, { params: { page, page_size: pageSize } })
    const productsData = productsRes.data
    const products: Product[] = Array.isArray(productsData) ? productsData : (productsData.results || [])
    const totalCount: number = Array.isArray(productsData) ? productsData.length : (productsData.count ?? products.length)
    
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
        totalCount,
        page,
        categories,
        brands,
      },
    }
  } catch (e) {
    return { 
      props: { 
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), 
        products: [], totalCount: 0, page: 1,
        categories: [],
        brands: []
      } 
    }
  }
}
