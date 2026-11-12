import axios from 'axios'
import { GetServerSideProps } from 'next'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

import BannerCarousel from '../../components/BannerCarouselMedia'
import SEO from '../../components/SEO'
import { BLOG_ARTICLES, getBlogArticle } from '../../content/blog/articles'
import { buildBreadcrumbSchema } from '../../lib/blog'
import { SITE_URL } from '../../lib/siteMeta'
import { getInternalApiUrl } from '../../lib/urls'

export default function BlogIndexPage({ banners = [] }: { banners?: any[] }) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const locale = router.locale || 'ru'
  const localePrefix = locale === router.defaultLocale ? '' : `/${locale}`
  const articles = BLOG_ARTICLES.map((item) => getBlogArticle(item.slug, locale)).filter(Boolean) as Array<{ slug: string; title: string; description: string }>
  const breadcrumbs = [
    { href: '/', label: t('breadcrumb_home', 'Главная') },
    { href: '/blog', label: t('blog_breadcrumb', 'Статьи') },
  ]

  return (
    <>
      <SEO
        title={t('blog_meta_title', 'Статьи о лекарствах из Турции: аналоги, ввоз, проверка')}
        description={t('blog_meta_description', 'Какие лекарства заказать из Турции, турецкие аналоги российских препаратов, правила ввоза и как проверить подлинность лекарства.')}
        canonical="/blog"
        structuredData={buildBreadcrumbSchema({ siteUrl: SITE_URL, localePrefix, breadcrumbs })}
      />
      <main className="bg-page text-main min-h-screen">
        <div className="mx-auto max-w-page px-4 py-4 sm:px-6 sm:py-8">
          <nav aria-label={t('breadcrumbs', 'Хлебные крошки')} className="mb-6 flex flex-wrap items-center gap-2 text-sm text-main">
            {breadcrumbs.map((item, idx) => {
              const isLast = idx === breadcrumbs.length - 1
              return (
                <span key={item.href} className="flex items-center gap-2">
                  {isLast ? (
                    <span className="font-medium">{item.label}</span>
                  ) : (
                    <Link href={item.href} className="transition-colors hover:text-[var(--accent)]">{item.label}</Link>
                  )}
                  {!isLast && <span className="text-main/60">/</span>}
                </span>
              )
            })}
          </nav>
          <h1 className="text-3xl font-bold text-main md:text-4xl">{t('blog_h1', 'Статьи о лекарствах из Турции')}</h1>
          <p className="mt-3 max-w-3xl text-main/75">{t('blog_meta_description', 'Какие лекарства заказать из Турции, турецкие аналоги российских препаратов, правила ввоза и как проверить подлинность.')}</p>
          {/* Первая статья — на всю ширину, остальные по три в ряд: при малом числе статей список не выглядит обрубком. */}
          <ul className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {articles.map((article, idx) => (
              <li key={article.slug} className={idx === 0 ? 'sm:col-span-2 lg:col-span-3' : ''}>
                <Link
                  href={`/blog/${article.slug}`}
                  className={`group flex h-full flex-col rounded-2xl bg-[var(--surface)] transition-shadow duration-200 hover:shadow-md ${idx === 0 ? 'p-6 md:p-8' : 'p-5'}`}
                >
                  <h2 className={`font-semibold text-[var(--text-strong)] group-hover:text-[var(--accent)] ${idx === 0 ? 'text-2xl md:text-3xl' : 'text-xl'}`}>{article.title}</h2>
                  <p className={`mt-2 text-main/75 ${idx === 0 ? 'max-w-3xl md:text-lg' : ''}`}>{article.description}</p>
                  <span className="mt-auto pt-4 text-sm font-semibold text-[var(--accent)]">{t('blog_read_article', 'Читать статью')} →</span>
                </Link>
              </li>
            ))}
          </ul>
          {/* Баннер из админки (место «после брендов» — медицинская тема), тот же компонент, что на главной:
              картинки через next/image, ролики грузятся только рядом с экраном. Баннер выключен — блока нет. */}
          {banners.length > 0 && (
            <div className="mt-10">
              <BannerCarousel position="after_brands" initialBanners={banners} />
            </div>
          )}
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const locale = ctx.locale || ctx.defaultLocale || 'ru'
  // Баннер необязателен: ошибка API не ломает страницу
  const banners = await axios
    .get(getInternalApiUrl('catalog/banners'), { params: { position: 'after_brands' }, headers: { 'Accept-Language': locale, 'X-Language': locale }, timeout: 3000 })
    .then((res) => (Array.isArray(res.data) ? res.data : []))
    .catch(() => [])
  return {
    props: {
      banners,
      ...(await serverSideTranslations(locale, ['common'])),
    },
  }
}
