import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { useTranslation } from 'next-i18next'

interface BrandBanner {
  id: string
  name: string
  slug: string
  description: string
  imageUrl: string
  bgColor: string
  textColor: string
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

export default function Home() {
  const { t } = useTranslation('common')
  const router = useRouter()

  // Данные брендов и категорий для баннеров
  const brandBanners: BrandBanner[] = [
    {
      id: 'zara',
      name: 'Zara',
      slug: 'zara',
      description: 'Модная одежда и аксессуары',
      imageUrl: '/brand-zara.jpg',
      bgColor: 'from-gray-900 to-gray-700',
      textColor: 'text-white'
    },
    {
      id: 'wikiki',
      name: 'Wikiki',
      slug: 'wikiki', 
      description: 'Стильная молодежная одежда',
      imageUrl: '/brand-wikiki.jpg',
      bgColor: 'from-pink-500 to-rose-400',
      textColor: 'text-white'
    }
  ]

  const categoryBanners: CategoryBanner[] = [
    {
      id: 'medicines',
      name: 'Медикаменты',
      slug: 'medicines',
      description: 'Лекарственные препараты и БАДы',
      imageUrl: '/category-medicines.jpg',
      bgColor: 'from-green-600 to-emerald-500',
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
    }
  ]

  const handleBrandClick = (brand: BrandBanner) => {
    router.push(`/brand/${brand.slug}`)
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {brandBanners.map((brand) => (
              <div
                key={brand.id}
                onClick={() => handleBrandClick(brand)}
                className="relative h-48 rounded-xl overflow-hidden cursor-pointer transform hover:scale-105 transition-transform duration-300 shadow-lg hover:shadow-xl"
              >
                <div className={`absolute inset-0 bg-gradient-to-r ${brand.bgColor} opacity-90`} />
                <div className="absolute inset-0 flex items-center justify-center p-6">
                  <div className={`text-center ${brand.textColor}`}>
                    <h3 className="text-2xl md:text-3xl font-bold mb-2">
                      {brand.name}
                    </h3>
                    <p className="text-lg opacity-90">
                      {brand.description}
                    </p>
                  </div>
                </div>
              </div>
            ))}
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

export async function getServerSideProps(ctx: any) {
  return {
    props: {
      ...(await serverSideTranslations(ctx.locale ?? 'en', ['common'])),
    },
  }
}
