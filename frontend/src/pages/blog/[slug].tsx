import { GetServerSideProps } from 'next'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

import SEO from '../../components/SEO'
import BlogArticleBody, { BlogArticle } from '../../components/BlogArticleBody'
import { getBlogArticle } from '../../content/blog/articles'
import { buildArticleSchemas } from '../../lib/blog'
import { formatIsoDate } from '../../lib/drugGroup'
import { SITE_NAME, SITE_URL } from '../../lib/siteMeta'

export default function BlogArticlePage({ slug }: { slug: string }) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const locale = router.locale || 'ru'
  const localePrefix = locale === router.defaultLocale ? '' : `/${locale}`
  const article = getBlogArticle(slug, locale) as BlogArticle
  const breadcrumbs = [
    { href: '/', label: t('breadcrumb_home', 'Главная') },
    { href: '/blog', label: t('blog_breadcrumb', 'Статьи') },
    { href: `/blog/${slug}`, label: article.title },
  ]

  return (
    <>
      <SEO
        title={article.metaTitle}
        description={article.description}
        canonical={`/blog/${slug}`}
        ogType="article"
        structuredData={buildArticleSchemas({ siteUrl: SITE_URL, siteName: SITE_NAME, localePrefix, article, locale, breadcrumbs })}
      />
      <main className="bg-page text-main min-h-screen">
        <article className="mx-auto max-w-3xl px-4 py-4 sm:px-6 sm:py-8">
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
          <header className="mb-6">
            <h1 className="text-3xl font-bold leading-tight text-main md:text-4xl">{article.title}</h1>
            <p className="mt-3 text-sm text-main/70">
              {t('blog_byline', 'Редакция {{site}} · обновлено {{date}}', { site: SITE_NAME, date: formatIsoDate(article.updatedAt) })}
            </p>
          </header>
          <BlogArticleBody article={article} />
        </article>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const slug = String(ctx.params?.slug || '')
  if (!getBlogArticle(slug, ctx.locale || 'ru')) return { notFound: true }
  return {
    props: {
      slug,
      ...(await serverSideTranslations(ctx.locale || ctx.defaultLocale || 'ru', ['common'])),
    },
  }
}
