import { GetServerSideProps } from 'next'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

import SEO from '../../components/SEO'
import { BLOG_ARTICLES, getBlogArticle } from '../../content/blog/articles'
import { buildBreadcrumbSchema } from '../../lib/blog'
import { SITE_URL } from '../../lib/siteMeta'

export default function BlogIndexPage() {
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
        <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-10">
          <h1 className="mb-6 text-3xl font-bold text-main md:text-4xl">{t('blog_h1', 'Статьи о лекарствах из Турции')}</h1>
          <ul className="space-y-4">
            {articles.map((article) => (
              <li key={article.slug} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 transition-colors hover:border-[var(--accent)]">
                <Link href={`/blog/${article.slug}`} className="block">
                  <h2 className="text-xl font-semibold text-main">{article.title}</h2>
                  <p className="mt-2 text-main/75">{article.description}</p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => ({
  props: {
    ...(await serverSideTranslations(ctx.locale || ctx.defaultLocale || 'ru', ['common'])),
  },
})
