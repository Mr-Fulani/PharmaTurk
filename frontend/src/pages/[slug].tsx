import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../lib/urls'
import { SITE_NAME } from '../lib/siteMeta'

interface PageData {
  title: string
  content: string
  slug: string
}

export default function GenericStaticPage({ pageData, formattedDate }: { pageData: PageData | null; formattedDate: string }) {
  const { t } = useTranslation('common')

  if (!pageData) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <h1 className="text-2xl font-bold text-main">{t('page_not_found', 'Страница не найдена')}</h1>
      </div>
    )
  }

  return (
    <>
      <Head>
        <title>{`${pageData.title} — ${SITE_NAME}`}</title>
      </Head>
      <main className="mx-auto max-w-5xl p-6 sm:p-10 min-h-screen">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8 shadow-sm">
          <h1 className="mb-8 text-3xl font-bold text-main md:text-5xl text-center">
            {pageData.title}
          </h1>

          <div 
            className="prose prose-indigo max-w-none text-main/80 mb-12 dark:prose-invert"
            dangerouslySetInnerHTML={{ __html: pageData.content }}
          />

          <div className="h-px w-full bg-gradient-to-r from-transparent via-gray-200 to-transparent dark:via-gray-700 mb-8"></div>
          
          <div className="text-center text-sm text-main/60">
            {t('last_updated', 'Последнее обновление')}: {formattedDate}
          </div>
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const { slug } = ctx.params as { slug: string }
  let pageData = null
  const lang = ctx.locale || 'ru'

  try {
    const res = await axios.get(getInternalApiUrl(`pages/${slug}/`) + `?lang=${lang}`)
    pageData = res.data
  } catch (error) {
    console.error(`Failed to fetch static page: ${slug}`)
  }

  if (!pageData) {
    return {
      notFound: true,
    }
  }

  // Форматируем дату на сервере, чтобы избежать Hydration Error (несовпадения локалей сервера и клиента)
  const formattedDate = new Date().toLocaleDateString(lang === 'ru' ? 'ru-RU' : 'en-US')

  return {
    props: {
      pageData,
      formattedDate,
      ...(await serverSideTranslations(ctx.locale ?? 'ru', ['common'])),
    },
  }
}
