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
  // Базовый API-URL берём из окружения, но при SSR внутри Docker-контейнера
  // 'localhost:8000' указывает на сам контейнер frontend, поэтому пробуем несколько хостов.
  const envApi = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || ''
  const candidateHosts = []
  if (envApi) candidateHosts.push(envApi.replace(/\/$/, ''))
  candidateHosts.push('http://backend:8000') // docker service name
  candidateHosts.push('http://127.0.0.1:8000')
  candidateHosts.push('http://host.docker.internal:8000')

  let page = null
  for (const host of candidateHosts) {
    try {
      const url = `${host}/api/pages/${slug}/?lang=${lang}`
      const res = await fetch(url)
      if (!res.ok) {
        // пробуем следующий хост
        continue
      }
      page = await res.json()
      if (page) break
    } catch (e) {
      // игнорируем и пробуем следующий
      continue
    }
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
