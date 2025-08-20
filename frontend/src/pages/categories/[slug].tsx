import Head from 'next/head'
import { useRouter } from 'next/router'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getApiForCategory } from '../../lib/api'
import ProductCard from '../../components/ProductCard'

interface Product {
  id: number
  name: string
  slug: string
  description: string
  price: number
  price_formatted: string
  old_price?: number
  old_price_formatted?: string
  currency: string
  main_image?: string
  main_image_url?: string
  is_available: boolean
  is_featured: boolean
  category?: {
    id: number
    name: string
    slug: string
  }
  brand?: {
    id: number
    name: string
    slug: string
  }
  // Специфичные для одежды поля
  size?: string
  color?: string
  material?: string
  season?: string
  // Специфичные для обуви поля
  heel_height?: string
  sole_type?: string
  // Специфичные для электроники поля
  model?: string
  specifications?: any
  warranty?: string
  power_consumption?: string
}

interface Category {
  id: number
  name: string
  slug: string
  description: string
  children_count: number
  // Специфичные для одежды/обуви поля
  gender?: string
  gender_display?: string
  clothing_type?: string
  shoe_type?: string
  // Специфичные для электроники поля
  device_type?: string
}

interface Brand {
  id: number
  name: string
  slug: string
  description: string
  logo?: string
}

interface CategoryPageProps {
  products: Product[]
  categories: Category[]
  brands: Brand[]
  categoryName: string
  totalCount: number
  currentPage: number
  totalPages: number
  categoryType: 'medicines' | 'clothing' | 'shoes' | 'electronics'
}

export default function CategoryPage({
  products,
  categories,
  brands,
  categoryName,
  totalCount,
  currentPage,
  totalPages,
  categoryType
}: CategoryPageProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const { slug } = router.query



  const handleCategoryClick = (category: Category) => {
    router.push(`/categories/${category.slug}`)
  }

  const handleBrandClick = (brand: Brand) => {
    router.push(`/brand/${brand.slug}`)
  }

  const handlePageChange = (page: number) => {
    router.push({
      pathname: router.pathname,
      query: { ...router.query, page }
    })
  }

  return (
    <>
      <Head>
        <title>{categoryName} - PharmaTurk</title>
      </Head>
      
      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
            {categoryName}
          </h1>
          <p className="text-gray-600">
            Найдено товаров: {totalCount}
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          {/* Sidebar */}
          <div className="lg:w-1/4">
            {/* Categories */}
            <div className="bg-white rounded-lg shadow-md p-6 mb-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Категории
              </h3>
              <div className="space-y-2">
                {categories.map((category) => (
                  <button
                    key={category.id}
                    onClick={() => handleCategoryClick(category)}
                    className="block w-full text-left px-3 py-2 rounded-md hover:bg-gray-100 transition-colors duration-200"
                  >
                    <div className="font-medium text-gray-900">
                      {category.name}
                    </div>
                    {category.children_count > 0 && (
                      <div className="text-sm text-gray-500">
                        {category.children_count} подкатегорий
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Brands */}
            <div className="bg-white rounded-lg shadow-md p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Бренды
              </h3>
              <div className="space-y-2">
                {brands.map((brand) => (
                  <button
                    key={brand.id}
                    onClick={() => handleBrandClick(brand)}
                    className="block w-full text-left px-3 py-2 rounded-md hover:bg-gray-100 transition-colors duration-200"
                  >
                    <div className="font-medium text-gray-900">
                      {brand.name}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Products Grid */}
          <div className="lg:w-3/4">
            {products.length > 0 ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
                  {products.map((product) => (
                    <ProductCard
                      key={product.id}
                      id={product.id}
                      name={product.name}
                      slug={product.slug}
                      price={product.price ? String(product.price) : null}
                      currency={product.currency}
                      oldPrice={product.old_price ? String(product.old_price) : null}
                      imageUrl={product.main_image || product.main_image_url}
                    />
                  ))}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex justify-center">
                    <div className="flex space-x-2">
                      {currentPage > 1 && (
                        <button
                          onClick={() => handlePageChange(currentPage - 1)}
                          className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
                        >
                          Назад
                        </button>
                      )}
                      
                      {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                        <button
                          key={page}
                          onClick={() => handlePageChange(page)}
                          className={`px-4 py-2 border rounded-md ${
                            page === currentPage
                              ? 'bg-blue-600 text-white border-blue-600'
                              : 'border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          {page}
                        </button>
                      ))}
                      
                      {currentPage < totalPages && (
                        <button
                          onClick={() => handlePageChange(currentPage + 1)}
                          className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
                        >
                          Вперед
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-12">
                <div className="text-6xl mb-4">😔</div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  Товары не найдены
                </h3>
                <p className="text-gray-600">
                  Попробуйте изменить параметры поиска или выберите другую категорию
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (context) => {
  const { slug, page = 1, brand } = context.query
  const pageSize = 12

  try {
    // Определяем тип категории по slug
    let categoryType: 'medicines' | 'clothing' | 'shoes' | 'electronics' = 'medicines'
    
    // Более гибкая логика определения типа категории
    const clothingCategories = ['clothing', 'women-clothing', 'men-clothing', 'kids-clothing', 'dresses', 'blouses', 'shirts', 'pants', 'zara-clothing']
    const shoeCategories = ['shoes', 'women-shoes', 'men-shoes', 'kids-shoes', 'sneakers', 'boots', 'heels', 'sandals']
    const electronicsCategories = ['electronics', 'smartphones', 'laptops', 'tablets', 'computers', 'phones', 'accessories']
    
    // Проверяем по slug'у
    if (clothingCategories.includes(slug as string)) {
      categoryType = 'clothing'
    } else if (shoeCategories.includes(slug as string)) {
      categoryType = 'shoes'  
    } else if (electronicsCategories.includes(slug as string)) {
      categoryType = 'electronics'
    }
    
    console.log('=== CATEGORY TYPE DETECTION ===')
    console.log('Slug:', slug)
    console.log('Detected category type:', categoryType)

    // Получаем соответствующий API
    const api = getApiForCategory(categoryType)
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'

    // Загружаем данные в зависимости от типа категории
    if (categoryType === 'medicines') {
      // Для медикаментов используем старый API
      console.log('Fetching medicines from:', `${base}/api/catalog/products`)
      const prodRes = await axios.get(`${base}/api/catalog/products`, { 
        params: { page, page_size: pageSize } 
      })
      const productsData = prodRes.data
      let products = Array.isArray(productsData) ? productsData : (productsData.results || [])
      
      // Используем правильный totalCount из API
      const totalCount = prodRes.data.count || products.length
      
      console.log('Medicines API response:', {
        totalFromAPI: prodRes.data.count,
        productsLength: products.length,
        actualTotalCount: totalCount,
        expectedPages: Math.ceil(totalCount / pageSize)
      })
      
      // Моковые данные для категорий и брендов
      const categories = [
        { id: 1, name: 'Обезболивающие', slug: 'painkillers', children_count: 0 },
        { id: 2, name: 'Антибиотики', slug: 'antibiotics', children_count: 0 },
        { id: 3, name: 'Витамины', slug: 'vitamins', children_count: 0 },
        { id: 4, name: 'БАДы', slug: 'supplements', children_count: 0 }
      ]
      
      const brands = [
        { id: 1, name: 'Bayer', slug: 'bayer', description: 'Немецкий фармацевтический концерн' },
        { id: 2, name: 'Pfizer', slug: 'pfizer', description: 'Американская фармацевтическая компания' },
        { id: 3, name: 'Novartis', slug: 'novartis', description: 'Швейцарская фармацевтическая компания' }
      ]

      return {
        props: {
          products,
          categories,
          brands,
          categoryName: 'Медикаменты',
          totalCount,
          currentPage: Number(page),
          totalPages: Math.ceil(totalCount / pageSize),
          categoryType,
          ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
        },
      }
    } else {
      // Для новых категорий используем соответствующие API
      console.log('=== FETCHING CLOTHING DATA ===')
      console.log('Category type:', categoryType)
      console.log('Base URL:', base)
      console.log('Full URL:', `${base}/api/catalog/${categoryType}/products`)
      console.log('Params:', { page, page_size: pageSize })
      
      // Параметры для запроса товаров
      const productParams: any = { page, page_size: pageSize }
      if (brand) {
        // Находим ID бренда по slug
        const brandRes = await axios.get(`${base}/api/catalog/brands`)
        const allBrands = brandRes.data.results || []
        const selectedBrand = allBrands.find((b: any) => b.slug === brand)
        if (selectedBrand) {
          productParams.brand_id = selectedBrand.id
        }
      }

      const [prodRes, catRes, brandRes] = await Promise.all([
        axios.get(`${base}/api/catalog/${categoryType}/products`, { 
          params: productParams
        }),
        axios.get(`${base}/api/catalog/${categoryType}/categories`),
        axios.get(`${base}/api/catalog/brands`)
      ])
      
      console.log('API Response received:', {
        productsCount: prodRes.data.count || 0,
        categoriesLength: catRes.data.results?.length || 0,
        brandsLength: brandRes.data.results?.length || 0
      })

      const productsData = prodRes.data
      const products = Array.isArray(productsData) ? productsData : (productsData.results || [])
      const categories = catRes.data.results || []
      const brands = brandRes.data.results || []
      const totalCount = productsData.count || products.length
      
      console.log('Final data:', {
        totalCount,
        productsLength: products.length,
        categoriesLength: categories.length,
        brandsLength: brands.length
      })

      // Определяем название категории
      let categoryName = 'Товары'
      if (categoryType === 'clothing') categoryName = 'Одежда'
      else if (categoryType === 'shoes') categoryName = 'Обувь'
      else if (categoryType === 'electronics') categoryName = 'Электроника'

      return {
        props: {
          products,
          categories,
          brands,
          categoryName,
          totalCount,
          currentPage: Number(page),
          totalPages: Math.ceil(totalCount / pageSize),
          categoryType,
          ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
        },
      }
    }
  } catch (error) {
    console.error('=== ERROR FETCHING DATA ===')
    console.error('Error details:', error)
    if (axios.isAxiosError(error)) {
      console.error('Axios error:', {
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        config: {
          url: error.config?.url,
          method: error.config?.method,
          params: error.config?.params
        }
      })
    }
    
    return {
      props: {
        products: [],
        categories: [],
        brands: [],
        categoryName: 'Товары',
        totalCount: 0,
        currentPage: 1,
        totalPages: 1,
        categoryType: 'medicines',
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  }
}
