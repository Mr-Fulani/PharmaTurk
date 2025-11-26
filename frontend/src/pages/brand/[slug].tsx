import Head from 'next/head'
import Link from 'next/link'
import axios from 'axios'
import { useState } from 'react'
import { useRouter } from 'next/router'
import ProductCard from '../../components/ProductCard'
import Sidebar from '../../components/Sidebar'
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

interface BrandData {
  name: string
  description: string
  products: Product[]
  totalCount: number
}

export default function BrandPage({
  brandData,
  page,
  categories = [],
  brands = []
}: {
  brandData: BrandData
  page: number
  categories: Category[]
  brands: Brand[]
}) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const { slug } = router.query
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null)
  const [selectedBrand, setSelectedBrand] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState('name_asc')
  const [inStockOnly, setInStockOnly] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const productsPerPage = 24
  const currentPage = Number(page) || 1
  const totalPages = Math.max(1, Math.ceil((Number(brandData?.totalCount) || 0) / productsPerPage))

  const goToPage = (nextPage: number) => {
    const p = Math.min(Math.max(1, nextPage), totalPages)
    router.push({ pathname: `/brand/${slug}`, query: { ...router.query, page: p } })
  }

  if (!brandData) {
    return <div>Бренд не найден</div>
  }

  return (
    <>
      <Head>
        <title>{brandData.name} - PharmaTurk</title>
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

          {/* Brand Header */}
          <div className="mb-8">
            <nav className="mb-4">
              <Link href="/" className="text-violet-600 hover:text-violet-800 text-sm">
                Главная
              </Link>
              <span className="mx-2 text-gray-400">/</span>
              <span className="text-gray-600 text-sm">{brandData.name}</span>
            </nav>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">{brandData.name}</h1>
            <p className="text-gray-600">{brandData.description}</p>
          </div>
          
          <div className="mt-2 w-full">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 gap-7">
              {brandData.products.map((p) => (
                <ProductCard
                  key={p.id}
                  id={p.id}
                  name={p.name}
                  slug={p.slug}
                  price={p.price}
                  currency={p.currency}
                  imageUrl={p.main_image_url}
                  productType="medicines"
                  isBaseProduct
                />
              ))}
            </div>

            {brandData.products.length === 0 && (
              <div className="text-center py-16">
                <h3 className="text-xl font-medium text-gray-900 mb-2">Товары не найдены</h3>
                <p className="text-gray-600">В данный момент товары этого бренда недоступны</p>
              </div>
            )}

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
    const { slug } = ctx.params
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    const page = Number(ctx.query?.page || 1)
    const pageSize = 24

    // Генерируем тестовые данные для брендов с контекстными сайтбарами
    const mockBrandData: Record<string, BrandData & { categories: Category[], brands: Brand[] }> = {
      'zara': {
        name: 'Zara',
        description: 'Модная одежда и аксессуары от испанского бренда',
        products: [
          {
            id: 101,
            name: 'Платье Zara весеннее',
            slug: 'zara-dress-spring',
            price: '2999',
            currency: 'RUB',
            main_image_url: '/product-placeholder.svg'
          },
          {
            id: 102,
            name: 'Джинсы Zara классик',
            slug: 'zara-jeans-classic',
            price: '3999',
            currency: 'RUB',
            main_image_url: '/product-placeholder.svg'
          },
          {
            id: 103,
            name: 'Блузка Zara офисная',
            slug: 'zara-blouse-office',
            price: '2499',
            currency: 'RUB',
            main_image_url: '/product-placeholder.svg'
          }
        ],
        totalCount: 3,
        categories: [
          { id: 1, name: 'Платья', slug: 'dresses', count: 156 },
          { id: 2, name: 'Джинсы', slug: 'jeans', count: 89 },
          { id: 3, name: 'Блузки и рубашки', slug: 'blouses', count: 134 },
          { id: 4, name: 'Юбки', slug: 'skirts', count: 67 },
          { id: 5, name: 'Пиджаки', slug: 'blazers', count: 45 },
          { id: 6, name: 'Аксессуары', slug: 'accessories', count: 98 },
          { id: 7, name: 'Обувь', slug: 'shoes', count: 87 }
        ],
        brands: [
          { id: 1, name: 'Zara', count: 234 },
          { id: 2, name: 'Massimo Dutti', count: 89 },
          { id: 3, name: 'Pull & Bear', count: 156 },
          { id: 4, name: 'Bershka', count: 178 },
          { id: 5, name: 'Stradivarius', count: 134 },
          { id: 6, name: 'Oysho', count: 67 },
          { id: 7, name: 'Uterqüe', count: 45 }
        ]
      },
      'wikiki': {
        name: 'Wikiki',
        description: 'Стильная молодежная одежда',
        products: [
          {
            id: 201,
            name: 'Футболка Wikiki молодежная',
            slug: 'wikiki-tshirt-youth',
            price: '1299',
            currency: 'RUB',
            main_image_url: '/product-placeholder.svg'
          },
          {
            id: 202,
            name: 'Шорты Wikiki летние',
            slug: 'wikiki-shorts-summer',
            price: '1599',
            currency: 'RUB',
            main_image_url: '/product-placeholder.svg'
          }
        ],
        totalCount: 2,
        categories: [
          { id: 1, name: 'Футболки', slug: 'tshirts', count: 89 },
          { id: 2, name: 'Шорты', slug: 'shorts', count: 67 },
          { id: 3, name: 'Толстовки', slug: 'hoodies', count: 54 },
          { id: 4, name: 'Джинсы', slug: 'jeans', count: 43 },
          { id: 5, name: 'Платья', slug: 'dresses', count: 32 },
          { id: 6, name: 'Аксессуары', slug: 'accessories', count: 28 }
        ],
        brands: [
          { id: 1, name: 'Wikiki', count: 156 },
          { id: 2, name: 'H&M', count: 134 },
          { id: 3, name: 'Forever 21', count: 89 },
          { id: 4, name: 'Uniqlo', count: 76 },
          { id: 5, name: 'C&A', count: 54 },
          { id: 6, name: 'Mango', count: 67 }
        ]
      }
    }

    const brandData = mockBrandData[slug as string]
    
    return {
      props: {
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
        brandData: brandData ? {
          name: brandData.name,
          description: brandData.description,
          products: brandData.products,
          totalCount: brandData.totalCount
        } : null,
        page,
        categories: brandData?.categories || [],
        brands: brandData?.brands || [],
      },
    }
  } catch (e) {
    return { 
      props: { 
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), 
        brandData: null,
        page: 1,
        categories: [],
        brands: []
      } 
    }
  }
}
