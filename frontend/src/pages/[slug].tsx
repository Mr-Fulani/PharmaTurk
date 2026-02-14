import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

/**
 * Динамическая страница для отображения статических страниц (delivery, returns, privacy и т.д.).
 *
 * Используем getServerSideProps для SSR: сервер получает локализованный контент с бэкенда
 * и передаёт его в компонент. Locale берётся из `context.locale` (next.js) и передаётся
 * в GET-параметре `lang` к API. Также загружаем переводы через serverSideTranslations,
 * чтобы t('...') в Header/other components совпадали на сервере и клиенте.
 */

import React from 'react'
import { GetServerSideProps } from 'next'
const nextI18NextConfig = require('../../next-i18next.config.js')

type PageProps = {
  page: {
    slug: string
    title: string
    content: string
  } | null
}

const Page: React.FC<PageProps> = ({ page }) => {
  if (!page) return <div>Page not found</div>
  return (
    <div className="container mx-auto py-8">
      <h1 className="text-2xl font-bold mb-4">{page.title}</h1>
      {/* Контент сервера считается безопасным: админ контролирует HTML. При необходимости можно очистить его дополнительно. */}
      <div dangerouslySetInnerHTML={{ __html: page.content }} />
    </div>
  )
}

export const getServerSideProps: GetServerSideProps = async (context) => {
  const { params, locale } = context
  const slug = params?.slug
  if (!slug) return { notFound: true }
  const lang = locale || nextI18NextConfig.i18n.defaultLocale || 'ru'
  const { getInternalApiUrl } = await import('../lib/urls')
  const url = `${getInternalApiUrl('pages/' + slug)}/?lang=${lang}`

  let page = null
  try {
    const res = await fetch(url)
    if (res.ok) {
      page = await res.json()
    }
  } catch (e) {
    // ignore
  }

  if (!page) {
    // подстраховка: если ничего не нашлось, возвращаем props с page=null
    // это сохранит поведение текущего приложения и покажет Page not found.
    const i18nProps = await serverSideTranslations(lang, ['common'])
    return { props: { page: null, ...i18nProps } }
  }

  // Подгружаем переводы на сервере для namespace 'common' (Header/Footer и т.д.)
  const i18nProps = await serverSideTranslations(lang, ['common'])

  return { props: { page, ...i18nProps } }
}

export default Page
