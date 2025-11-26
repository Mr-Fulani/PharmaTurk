import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import axios from 'axios'

interface Brand {
  id: number
  name: string
  slug: string
  description: string
  logo?: string
  website?: string
  products_count?: number
}

interface CategoryBanner {
  id: string
  name: string
  slug: string
  description: string
  imageUrl: string
  bgColor: string
  textColor: string
}

interface HomePageProps {
  brands: Brand[]
}

export default function Home({ brands }: HomePageProps) {
  const { t } = useTranslation('common')
  const router = useRouter()

  // Функция для получения цветов баннера по бренду
  const getBrandColors = (brandName: string) => {
    const colorMap: { [key: string]: { bgColor: string; textColor: string } } = {
      'Zara': { bgColor: 'from-gray-900 to-gray-700', textColor: 'text-white' },
      'LC Waikiki': { bgColor: 'from-blue-600 to-blue-400', textColor: 'text-white' },
      'Koton': { bgColor: 'from-purple-600 to-purple-400', textColor: 'text-white' },
      'DeFacto': { bgColor: 'from-green-600 to-green-400', textColor: 'text-white' },
      'Mavi': { bgColor: 'from-indigo-600 to-indigo-400', textColor: 'text-white' },
      'Boyner': { bgColor: 'from-red-600 to-red-400', textColor: 'text-white' },
    }
    return colorMap[brandName] || { bgColor: 'from-gray-600 to-gray-400', textColor: 'text-white' }
  }

  const categoryBanners: CategoryBanner[] = [
    {
      id: 'medicines',
      name: 'Медикаменты',
      slug: 'medicines',
      description: 'Лекарственные препараты',
      imageUrl: '/category-medicines.jpg',
      bgColor: 'from-green-600 to-emerald-500',
      textColor: 'text-white'
    },
    {
      id: 'supplements',
      name: 'БАДы',
      slug: 'supplements',
      description: 'Биологически активные добавки',
      imageUrl: '/category-supplements.jpg',
      bgColor: 'from-amber-600 to-yellow-500',
      textColor: 'text-white'
    },
    {
      id: 'clothing',
      name: 'Одежда',
      slug: 'clothing',
      description: 'Модная одежда для всей семьи',
      imageUrl: '/category-clothing.jpg',
      bgColor: 'from-rose-600 to-pink-500',
      textColor: 'text-white'
    },
    {
      id: 'shoes',
      name: 'Обувь',
      slug: 'shoes',
      description: 'Качественная обувь для всей семьи',
      imageUrl: '/category-shoes.jpg',
      bgColor: 'from-blue-600 to-indigo-500',
      textColor: 'text-white'
    },
    {
      id: 'electronics',
      name: 'Электроника',
      slug: 'electronics',
      description: 'Современные гаджеты и техника',
      imageUrl: '/category-electronics.jpg',
      bgColor: 'from-slate-700 to-gray-600',
      textColor: 'text-white'
    },
    {
      id: 'tableware',
      name: 'Посуда',
      slug: 'tableware',
      description: 'Кухонная посуда и аксессуары',
      imageUrl: '/category-tableware.jpg',
      bgColor: 'from-orange-600 to-red-500',
      textColor: 'text-white'
    },
    {
      id: 'furniture',
      name: 'Мебель',
      slug: 'furniture',
      description: 'Мебель для дома и офиса',
      imageUrl: '/category-furniture.jpg',
      bgColor: 'from-amber-800 to-orange-700',
      textColor: 'text-white'
    },
    {
      id: 'medical-equipment',
      name: 'Медицинский инвентарь',
      slug: 'medical-equipment',
      description: 'Инструменты и оборудование для медицины',
      imageUrl: '/category-medical-equipment.jpg',
      bgColor: 'from-teal-600 to-cyan-500',
      textColor: 'text-white'
    }
  ]

  const handleBrandClick = (brand: Brand) => {
    // Направляем к товарам бренда через категорию одежды с фильтром по бренду
    router.push(`/categories/clothing?brand=${brand.slug}`)
  }

  const handleCategoryClick = (category: CategoryBanner) => {
    router.push(`/categories/${category.slug}`)
  }

  return (
    <>
      <Head>
        <title>PharmaTurk - Главная</title>
      </Head>
      
      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Hero Banner */}
        <div className="relative mb-12 rounded-xl overflow-hidden shadow-lg">
          <div className="bg-gradient-to-r from-violet-600 via-purple-600 to-indigo-600 h-48 md:h-64 flex items-center justify-center">
            <div className="text-center text-white px-6">
              <h1 className="text-3xl md:text-5xl font-bold mb-4">
                PharmaTurk
              </h1>
              <p className="text-lg md:text-xl opacity-90 mb-6">
                Ваш надежный партнер в мире товаров из Турции
              </p>
              <div className="space-x-4">
                <button 
                  onClick={() => router.push('/categories/medicines')}
                  className="bg-white text-violet-600 px-6 py-3 rounded-lg font-semibold hover:bg-gray-100 transition-colors duration-200"
                >
                  Медикаменты
                </button>
                <button 
                  onClick={() => router.push('/categories/clothing')}
                  className="border-2 border-white text-white px-6 py-3 rounded-lg font-semibold hover:bg-white hover:text-violet-600 transition-colors duration-200"
                >
                  Одежда
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Brands Section */}
        <section className="mb-12">
          <h2 className="text-2xl md:text-3xl font-bold text-gray-900 mb-8 text-center">
            Популярные бренды
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {brands.map((brand) => {
              const colors = getBrandColors(brand.name)
              return (
                <div
                  key={brand.id}
                  onClick={() => handleBrandClick(brand)}
                  className="relative h-48 rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl"
                >
                  <div className={`absolute inset-0 bg-gradient-to-r ${colors.bgColor} opacity-90`} />
                  <div className="absolute inset-0 flex items-center justify-center p-6">
                    <div className={`text-center ${colors.textColor}`}>
                      {brand.logo && (
                        <div className="mb-3 flex justify-center">
                          <img 
                            src={brand.logo} 
                            alt={brand.name}
                            className="h-12 w-auto object-contain filter brightness-0 invert"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none'
                            }}
                          />
                        </div>
                      )}
                      <h3 className="text-2xl md:text-3xl font-bold mb-2">
                        {brand.name}
                      </h3>
                      <p className="text-sm opacity-90 mb-2">
                        {brand.description}
                      </p>
                      {brand.products_count && (
                        <p className="text-xs opacity-75">
                          {brand.products_count} товаров
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* Categories Section */}
        <section>
          <h2 className="text-2xl md:text-3xl font-bold text-gray-900 mb-8 text-center">
            Категории товаров
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {categoryBanners.map((category) => (
              <div
                key={category.id}
                onClick={() => handleCategoryClick(category)}
                className="relative h-40 rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl"
              >
                <div className={`absolute inset-0 bg-gradient-to-r ${category.bgColor} opacity-90`} />
                <div className="absolute inset-0 flex items-center justify-center p-4">
                  <div className={`text-center ${category.textColor}`}>
                    <h3 className="text-xl font-bold mb-1">
                      {category.name}
                    </h3>
                    <p className="text-sm opacity-90">
                      {category.description}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (context) => {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    
    // Загружаем бренды из API
    const brandsRes = await axios.get(`${base}/api/catalog/brands`)
    const allBrands = brandsRes.data.results || []
    
    // Фильтруем только турецкие и популярные бренды
    const turkishBrands = ['Zara', 'LC Waikiki', 'Koton', 'DeFacto', 'Mavi', 'Boyner']
    const brands = allBrands.filter((brand: Brand) => 
      turkishBrands.includes(brand.name)
    ).slice(0, 6) // Показываем максимум 6 брендов
    
    console.log('Loaded brands for homepage:', brands.map((b: Brand) => b.name))
    
    return {
      props: {
        brands,
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  } catch (error) {
    console.error('Error loading brands for homepage:', error)
    
    return {
      props: {
        brands: [],
        ...(await serverSideTranslations(context.locale ?? 'en', ['common'])),
      },
    }
  }
}
