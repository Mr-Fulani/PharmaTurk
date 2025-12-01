import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getApiForCategory } from '../lib/api'
import BannerCarousel from '../components/BannerCarousel'
import PopularProductsCarousel from '../components/PopularProductsCarousel'
import TestimonialsCarousel from '../components/TestimonialsCarousel'
import Footer from '../components/Footer'

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
    // Определяем тип товаров бренда на основе названия и данных из seed
    // Турецкие бренды одежды
    const clothingBrands = [
      'Zara', 'LC Waikiki', 'Koton', 'DeFacto', 'Mavi', 'Boyner', 'Beymen', 
      'Network', 'Colin\'s', 'Kigili', 'Altınyıldız', 'Damat', 'Tween', 
      'Sarar', 'İpekyol', 'Mango', 'H&M', 'Pull & Bear', 'Bershka', 
      'Stradivarius', 'Massimo Dutti', 'Oysho', 'Zara Home', 'Uterqüe',
      'Vakko', 'Penti'
    ]
    // Турецкие бренды обуви
    const shoesBrands = [
      'Hotiç', 'FLO', 'Greyder', 'Polaris', 'İnci', 'Derimod', 'Lescon', 'Hammer Jack'
    ]
    // Турецкие бренды электроники
    const electronicsBrands = [
      'Vestel', 'Arçelik', 'Beko', 'Casper', 'Reeder', 'General Mobile', 'Profilo', 'Sunny'
    ]
    // Бренды медикаментов
    const medicinesBrands = [
      'Bayer', 'Pfizer', 'Novartis', 'Roche', 'Sanofi', 'GlaxoSmithKline', 
      'Merck', 'Johnson & Johnson', 'Eli Lilly', 'AstraZeneca', 'Apple', 'Samsung',
      'Abdi İbrahim', 'Deva Holding', 'Nobel İlaç', 'Santa Farma', 'Bilim İlaç',
      'Atabay İlaç', 'İ.E. Ulagay', 'Centurion Pharma'
    ]
    // Бренды посуды
    const tablewareBrands = [
      'Karaca', 'Paşabahçe', 'Kütahya Porselen', 'Güral Porselen', 'Porland', 
      'Hisar', 'Emsan', 'Tantitoni'
    ]
    // Бренды мебели
    const furnitureBrands = [
      'Enza Home', 'Yataş', 'Doğtaş', 'Kelebek', 'Bellona', 'Lazzoni', 'Nill\'s', 'İder'
    ]
    // Бренды медицинского оборудования
    const medicalEquipmentBrands = [
      'Alvimedica', 'Bıçakcılar', 'Turkuaz Healthcare', 'Tıpsan', 'Ankara Healthcare'
    ]
    
    let categoryType = 'clothing' // По умолчанию одежда
    
    if (clothingBrands.includes(brand.name)) {
      categoryType = 'clothing'
    } else if (shoesBrands.includes(brand.name)) {
      categoryType = 'shoes'
    } else if (electronicsBrands.includes(brand.name)) {
      categoryType = 'electronics'
    } else if (medicinesBrands.includes(brand.name)) {
      categoryType = 'medicines'
    } else if (tablewareBrands.includes(brand.name)) {
      categoryType = 'tableware'
    } else if (furnitureBrands.includes(brand.name)) {
      categoryType = 'furniture'
    } else if (medicalEquipmentBrands.includes(brand.name)) {
      categoryType = 'medical-equipment'
    }
    
    // Открываем категорию с фильтром по brand_id
    router.push(`/categories/${categoryType}?brand_id=${brand.id}`)
  }

  const handleCategoryClick = (category: CategoryBanner) => {
    router.push(`/categories/${category.slug}`)
  }

  return (
    <>
      <Head>
        <title>PharmaTurk - Главная</title>
      </Head>
      
      <main>
      <div className="mx-auto max-w-6xl px-6 py-8">
          {/* Главный баннер */}
          <div className="mb-12">
            <BannerCarousel position="main" />
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

          {/* Баннер после брендов */}
          <div className="mb-12">
            <BannerCarousel position="after_brands" />
          </div>

        {/* Categories Section */}
          <section className="mb-12">
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

          {/* Баннер перед футером */}
          <div className="mb-12">
            <BannerCarousel position="before_footer" />
          </div>

          {/* Популярные товары */}
          <PopularProductsCarousel />
          
          {/* Баннер после популярных товаров */}
          <div className="mb-12">
            <BannerCarousel position="after_popular_products" />
          </div>
          
          {/* Отзывы клиентов */}
          <TestimonialsCarousel />
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (context) => {
  try {
    const base = process.env.INTERNAL_API_BASE || 'http://backend:8000'
    
    // Загружаем все бренды из API с пагинацией
    let allBrands: Brand[] = []
    let nextUrl: string | null = `${base}/api/catalog/brands`
    
    // Собираем все бренды (обходим пагинацию)
    while (nextUrl) {
      try {
        const brandsRes = await axios.get(nextUrl)
        const data = brandsRes.data
        const pageBrands = Array.isArray(data) ? data : (data.results || [])
        allBrands = [...allBrands, ...pageBrands]
        
        // Проверяем наличие следующей страницы
        nextUrl = data.next || null
      } catch (err) {
        console.error('Error loading brands page:', err)
        break
      }
    }
    
    // Фильтруем бренды с товарами и сортируем по количеству товаров (популярность)
    const brandsWithProducts = allBrands.filter((brand: Brand) => 
      brand.products_count && brand.products_count > 0
    )
    
    // Сортируем по количеству товаров (по убыванию) - самые популярные первыми
    brandsWithProducts.sort((a: Brand, b: Brand) => {
      const countA = a.products_count || 0
      const countB = b.products_count || 0
      return countB - countA
    })
    
    // Берем топ-6 самых популярных брендов
    const brands = brandsWithProducts.slice(0, 6)
    
    console.log('Loaded popular brands for homepage:', brands.map((b: Brand) => `${b.name} (${b.products_count} товаров)`))
    
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
