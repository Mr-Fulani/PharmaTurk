import { GetServerSideProps } from 'next'
import Head from 'next/head'
import axios from 'axios'
import Link from 'next/link'
import { useState } from 'react'
import { useRouter } from 'next/router'
import ProductCard from '../../components/ProductCard'
import Sidebar from '../../components/Sidebar'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

interface Product {
  id: number
  name: string
  slug: string
  price: string | null
  currency: string
  main_image_url?: string | null
  main_image?: string | null
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

export default function CategoryPage({ 
  name, 
  products, 
  totalCount, 
  page,
  categories = [],
  brands = []
}: { 
  name: string
  products: Product[]
  totalCount: number
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
  const totalPages = Math.max(1, Math.ceil((Number(totalCount) || 0) / productsPerPage))

  const goToPage = (nextPage: number) => {
    const p = Math.min(Math.max(1, nextPage), totalPages)
    router.push({ pathname: `/categories/${slug}`, query: { ...router.query, page: p } })
  }

  return (
    <>
      <Head>
        <title>{name} — PharmaTurk</title>
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

          {/* Category Header */}
          <div className="mb-8">
            <nav className="mb-4">
              <Link href="/" className="text-violet-600 hover:text-violet-800 text-sm">
                Главная
              </Link>
              <span className="mx-2 text-gray-400">/</span>
              <span className="text-gray-600 text-sm">{name}</span>
            </nav>
            <h1 className="text-3xl font-bold text-gray-900">{name}</h1>
          </div>
          
          <div className="mt-2 w-full">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 gap-7">
              {products.map((p) => (
                <ProductCard key={p.id} id={p.id} name={p.name} slug={p.slug} price={p.price} currency={p.currency} imageUrl={p.main_image_url || p.main_image} />
              ))}
            </div>

            {products.length === 0 && (
              <div className="text-center py-16">
                <h3 className="text-xl font-medium text-gray-900 mb-2">Товары не найдены</h3>
                <p className="text-gray-600">В данной категории пока нет товаров</p>
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

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const { slug } = ctx.params as { slug: string }
  const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
  const page = Number(ctx.query?.page || 1)
  const pageSize = 24

  try {
    // Для медикаментов используем реальные данные API, для остальных - моковые данные
    if (slug === 'medicines') {
      // Загружаем продукты (медикаменты)
      const prodRes = await axios.get(`${base}/api/catalog/products`, { params: { page, page_size: pageSize } })
      const productsData = prodRes.data
      const products = Array.isArray(productsData) ? productsData : (productsData.results || [])
      const totalCount = Array.isArray(productsData) ? productsData.length : (productsData.count ?? products.length)

      // Для медикаментов создаем специфические категории и бренды
      const medicineCategories = [
        { id: 1, name: 'Обезболивающие', slug: 'painkillers', count: 45 },
        { id: 2, name: 'Антибиотики', slug: 'antibiotics', count: 32 },
        { id: 3, name: 'Витамины и БАДы', slug: 'vitamins', count: 67 },
        { id: 4, name: 'Противовирусные', slug: 'antiviral', count: 23 },
        { id: 5, name: 'Сердечно-сосудистые', slug: 'cardiovascular', count: 41 },
        { id: 6, name: 'Желудочно-кишечные', slug: 'gastrointestinal', count: 38 },
        { id: 7, name: 'Дерматологические', slug: 'dermatological', count: 29 },
        { id: 8, name: 'Респираторные', slug: 'respiratory', count: 34 }
      ]

      const medicineBrands = [
        { id: 1, name: 'Pfizer', count: 15 },
        { id: 2, name: 'Bayer', count: 22 },
        { id: 3, name: 'Novartis', count: 18 },
        { id: 4, name: 'Roche', count: 12 },
        { id: 5, name: 'Johnson & Johnson', count: 20 },
        { id: 6, name: 'Merck', count: 16 },
        { id: 7, name: 'GSK', count: 14 },
        { id: 8, name: 'Sanofi', count: 19 },
        { id: 9, name: 'AbbVie', count: 11 },
        { id: 10, name: 'Bristol Myers', count: 13 }
      ]

      return { 
        props: { 
          ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), 
          name: 'Медикаменты', 
          products,
          totalCount,
          page,
          categories: medicineCategories,
          brands: medicineBrands
        } 
      }
    } else {
      // Моковые данные для других категорий с контекстными сайтбарами
      const mockCategoryData: Record<string, { 
        name: string, 
        products: any[], 
        categories: any[], 
        brands: any[] 
      }> = {
        'shoes': {
          name: 'Обувь',
          products: [
            { id: 301, name: 'Кроссовки спортивные', slug: 'sneakers-sport', price: '4999', currency: 'RUB', main_image_url: '/product-placeholder.svg' },
            { id: 302, name: 'Ботинки зимние', slug: 'boots-winter', price: '6999', currency: 'RUB', main_image_url: '/product-placeholder.svg' },
            { id: 303, name: 'Туфли классические', slug: 'shoes-classic', price: '5999', currency: 'RUB', main_image_url: '/product-placeholder.svg' }
          ],
          categories: [
            { id: 1, name: 'Кроссовки', slug: 'sneakers', count: 124 },
            { id: 2, name: 'Ботинки', slug: 'boots', count: 87 },
            { id: 3, name: 'Туфли', slug: 'shoes', count: 96 },
            { id: 4, name: 'Сандалии', slug: 'sandals', count: 45 },
            { id: 5, name: 'Сапоги', slug: 'high-boots', count: 63 },
            { id: 6, name: 'Мокасины', slug: 'loafers', count: 34 },
            { id: 7, name: 'Балетки', slug: 'flats', count: 52 }
          ],
          brands: [
            { id: 1, name: 'Nike', count: 67 },
            { id: 2, name: 'Adidas', count: 54 },
            { id: 3, name: 'Puma', count: 43 },
            { id: 4, name: 'Reebok', count: 29 },
            { id: 5, name: 'New Balance', count: 35 },
            { id: 6, name: 'Converse', count: 28 },
            { id: 7, name: 'Vans', count: 32 }
          ]
        },
        'cosmetics': {
          name: 'Косметика',
          products: [
            { id: 401, name: 'Крем для лица увлажняющий', slug: 'face-cream-moisture', price: '1999', currency: 'RUB', main_image_url: '/product-placeholder.svg' },
            { id: 402, name: 'Помада стойкая', slug: 'lipstick-long-lasting', price: '899', currency: 'RUB', main_image_url: '/product-placeholder.svg' }
          ],
          categories: [
            { id: 1, name: 'Уход за лицом', slug: 'face-care', count: 89 },
            { id: 2, name: 'Декоративная косметика', slug: 'makeup', count: 156 },
            { id: 3, name: 'Парфюмерия', slug: 'perfume', count: 73 },
            { id: 4, name: 'Уход за волосами', slug: 'hair-care', count: 94 },
            { id: 5, name: 'Уход за телом', slug: 'body-care', count: 67 },
            { id: 6, name: 'Мужская косметика', slug: 'mens-cosmetics', count: 42 }
          ],
          brands: [
            { id: 1, name: 'L\'Oréal', count: 45 },
            { id: 2, name: 'Maybelline', count: 38 },
            { id: 3, name: 'MAC', count: 29 },
            { id: 4, name: 'Estée Lauder', count: 22 },
            { id: 5, name: 'Clinique', count: 31 },
            { id: 6, name: 'Nivea', count: 56 },
            { id: 7, name: 'Garnier', count: 41 }
          ]
        },
        'electronics': {
          name: 'Электроника',
          products: [
            { id: 501, name: 'Наушники беспроводные', slug: 'headphones-wireless', price: '2999', currency: 'RUB', main_image_url: '/product-placeholder.svg' },
            { id: 502, name: 'Смартфон бюджетный', slug: 'smartphone-budget', price: '15999', currency: 'RUB', main_image_url: '/product-placeholder.svg' }
          ],
          categories: [
            { id: 1, name: 'Смартфоны', slug: 'smartphones', count: 234 },
            { id: 2, name: 'Наушники', slug: 'headphones', count: 156 },
            { id: 3, name: 'Планшеты', slug: 'tablets', count: 87 },
            { id: 4, name: 'Ноутбуки', slug: 'laptops', count: 112 },
            { id: 5, name: 'Умные часы', slug: 'smartwatches', count: 67 },
            { id: 6, name: 'Аксессуары', slug: 'accessories', count: 198 }
          ],
          brands: [
            { id: 1, name: 'Apple', count: 89 },
            { id: 2, name: 'Samsung', count: 134 },
            { id: 3, name: 'Xiaomi', count: 156 },
            { id: 4, name: 'Huawei', count: 78 },
            { id: 5, name: 'Sony', count: 67 },
            { id: 6, name: 'LG', count: 45 },
            { id: 7, name: 'OnePlus', count: 34 }
          ]
        }
      }

      const categoryData = mockCategoryData[slug] || { 
        name: 'Категория', 
        products: [],
        categories: [],
        brands: []
      }

      return { 
        props: { 
          ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), 
          name: categoryData.name, 
          products: categoryData.products,
          totalCount: categoryData.products.length,
          page: 1,
          categories: categoryData.categories,
          brands: categoryData.brands
        } 
      }
    }
  } catch (e) {
    return { 
      notFound: false, 
      props: { 
        ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])), 
        name: 'Категория', 
        products: [],
        totalCount: 0,
        page: 1,
        categories: [],
        brands: []
      } 
    }
  }
}
