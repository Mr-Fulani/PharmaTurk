import Head from 'next/head'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { GetServerSideProps } from 'next'
import axios from 'axios'
import { getInternalApiUrl } from '../lib/urls'
import { SITE_NAME, SITE_URL } from '../lib/siteMeta'
import ShareButton from '../components/ShareButton'

interface PageData {
  title: string
  content: string
  slug: string
  meta_title?: string
  meta_description?: string
  og_image?: string
}

interface GenericStaticPageProps {
  pageData: PageData | null
  pageLocale: string
}

const ABOUT_RICH_STYLES = `
  .about-rich {
    color: rgba(35, 61, 67, 0.92);
  }
  .about-rich h2 {
    margin: 0 0 1.5rem;
    text-align: center;
    font-size: clamp(2rem, 4vw, 3.25rem);
    line-height: 1.02;
    letter-spacing: -0.04em;
    color: #143f48;
  }
  .about-rich h3 {
    margin: 3rem 0 1rem;
    display: inline-flex;
    align-items: center;
    gap: 0.75rem;
    font-size: clamp(1.3rem, 2vw, 1.7rem);
    line-height: 1.2;
    color: #123d45;
  }
  .about-rich h3::before {
    content: '';
    width: 42px;
    height: 2px;
    border-radius: 999px;
    background: linear-gradient(90deg, #0f6973 0%, #d8aa63 100%);
    flex-shrink: 0;
  }
  .about-rich p {
    margin: 0 0 1.2rem;
    font-size: 1.08rem;
    line-height: 1.9;
    color: rgba(43, 78, 84, 0.92);
  }
  .about-rich p + p {
    margin-top: 1rem;
  }
  .about-rich ul {
    margin: 1.5rem 0 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 1rem;
  }
  .about-rich li {
    position: relative;
    padding: 1.15rem 1.2rem 1.15rem 3.2rem;
    border: 1px solid rgba(207, 231, 229, 0.95);
    border-radius: 1.35rem;
    background: linear-gradient(135deg, rgba(255,255,255,0.72), rgba(239,247,246,0.7));
    box-shadow: 0 18px 45px -35px rgba(19, 63, 72, 0.4);
  }
  .about-rich li::before {
    content: '';
    position: absolute;
    left: 1.2rem;
    top: 1.3rem;
    width: 1rem;
    height: 1rem;
    border-radius: 999px;
    background: linear-gradient(135deg, #0f6973 0%, #d8aa63 100%);
    box-shadow: 0 0 0 6px rgba(225, 242, 241, 0.95);
  }
  .about-rich strong {
    color: #173f47;
  }
  .about-rich em {
    display: block;
    margin-top: 2rem;
    padding: 1.4rem 1.5rem;
    border-left: 4px solid #0f6973;
    border-radius: 0 1.25rem 1.25rem 0;
    background: rgba(255,255,255,0.62);
    color: #1b5058;
    font-style: normal;
    font-weight: 600;
    box-shadow: 0 18px 45px -36px rgba(19, 63, 72, 0.38);
  }
  .about-rich :first-child {
    margin-top: 0;
  }
`

export default function GenericStaticPage({ pageData, pageLocale }: GenericStaticPageProps) {
  const { t } = useTranslation('common')

  if (!pageData) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <h1 className="text-2xl font-bold text-main">{t('page_not_found', 'Страница не найдена')}</h1>
      </div>
    )
  }

  const normalizedLocale = pageLocale === 'en' ? 'en' : 'ru'
  const localePrefix = normalizedLocale === 'en' ? '/en' : ''
  const seoTitle = pageData.meta_title || pageData.title
  const fullTitle = `${seoTitle} — ${SITE_NAME}`
  const isAboutPage = pageData.slug === 'about-us'
  const localizedAboutImage = isAboutPage ? `${SITE_URL}/og-about-us-${normalizedLocale}.png` : ''
  const canonicalUrl = `${SITE_URL}${localePrefix}/${pageData.slug}`
  const ruUrl = `${SITE_URL}/${pageData.slug}`
  const enUrl = `${SITE_URL}/en/${pageData.slug}`
  const ogImage = localizedAboutImage || pageData.og_image || `${SITE_URL}/og-default.png`
  const aboutHeroAlt =
    normalizedLocale === 'en'
      ? 'Mudaroba about us banner'
      : 'Баннер страницы О нас Mudaroba'
  const aboutHighlights = normalizedLocale === 'en'
    ? [
      {
        title: 'Authentic sourcing',
        text: 'Licensed pharmacies, official distributors, and curated Turkish brands.',
      },
      {
        title: 'Careful logistics',
        text: 'Thoughtful packing, safe routing, and attention to fragile or sensitive goods.',
      },
      {
        title: 'Human support',
        text: 'Live managers stay in touch and guide the order from request to delivery.',
      },
    ]
    : [
      {
        title: 'Проверенные поставки',
        text: 'Лицензированные аптеки, официальные дистрибьюторы и отобранные турецкие бренды.',
      },
      {
        title: 'Бережная логистика',
        text: 'Продуманная упаковка, безопасный маршрут и внимание к хрупким и чувствительным товарам.',
      },
      {
        title: 'Живая поддержка',
        text: 'Менеджеры остаются на связи и ведут заказ от запроса до доставки.',
      },
    ]

  return (
    <>
      <Head>
        <title>{fullTitle}</title>
        {pageData.meta_description && (
          <meta name="description" content={pageData.meta_description} />
        )}
        
        {/* Open Graph / Social Media */}
        <meta property="og:title" content={seoTitle} />
        {pageData.meta_description && (
          <meta property="og:description" content={pageData.meta_description} />
        )}
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="ru" href={ruUrl} />
        <link rel="alternate" hrefLang="en" href={enUrl} />
        <link rel="alternate" hrefLang="x-default" href={ruUrl} />
        <meta property="og:type" content="website" />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:image" content={ogImage} />
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:title" content={seoTitle} />
        {pageData.meta_description && (
          <meta property="twitter:description" content={pageData.meta_description} />
        )}
        <meta property="twitter:image" content={ogImage} />
      </Head>
      <main className="mx-auto max-w-5xl p-6 sm:p-10 min-h-screen">
        {isAboutPage && (
          <style dangerouslySetInnerHTML={{ __html: ABOUT_RICH_STYLES }} />
        )}

        <div className={`relative rounded-[2rem] border border-[var(--border)] bg-[var(--surface)] p-8 shadow-sm ${isAboutPage ? 'overflow-hidden shadow-[0_26px_90px_-48px_rgba(15,86,96,0.35)]' : ''}`}>
          {isAboutPage && (
            <>
              <div className="pointer-events-none absolute -right-24 top-24 h-56 w-56 rounded-full bg-[rgba(195,230,228,0.45)] blur-3xl" />
              <div className="pointer-events-none absolute -left-20 bottom-16 h-48 w-48 rounded-full bg-[rgba(231,209,170,0.24)] blur-3xl" />
            </>
          )}
          {isAboutPage && (
            <div
              className="absolute top-14 right-14 z-20 hidden md:block"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
              }}
            >
              <ShareButton
                title={seoTitle}
                description={pageData.meta_description}
                imageUrl={ogImage}
                slug={pageData.slug}
                pageUrl={canonicalUrl}
                cornerIcon={true}
              />
            </div>
          )}

          <h1 className="mb-4 text-3xl font-bold text-main md:mb-8 md:text-5xl text-center">
            {pageData.title}
          </h1>

          {isAboutPage && (
            <div className="mb-8 overflow-hidden rounded-[28px] border border-[var(--border)] bg-[linear-gradient(135deg,rgba(255,255,255,0.65),rgba(231,236,255,0.35))] p-2 shadow-[0_24px_60px_-28px_rgba(15,86,96,0.38)]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/about-us-hero-${normalizedLocale}.png`}
                alt={aboutHeroAlt}
                className="block w-full rounded-[22px] object-cover"
              />
            </div>
          )}

          {isAboutPage && (
            <div className="mb-10 grid gap-4 md:grid-cols-3">
              {aboutHighlights.map((item) => (
                <div
                  key={item.title}
                  className="rounded-[1.5rem] border border-[rgba(205,228,226,0.95)] bg-[linear-gradient(180deg,rgba(255,255,255,0.82),rgba(241,247,246,0.76))] px-5 py-5 shadow-[0_18px_50px_-36px_rgba(15,86,96,0.48)]"
                >
                  <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#0f6973,#d8aa63)] text-base font-bold text-white">
                    {item.title.charAt(0)}
                  </div>
                  <h2 className="mb-2 text-left text-xl font-semibold tracking-[-0.03em] text-[#153f48] md:text-[1.35rem]">
                    {item.title}
                  </h2>
                  <p className="mb-0 text-sm leading-7 text-[rgba(43,78,84,0.88)]">
                    {item.text}
                  </p>
                </div>
              ))}
            </div>
          )}

          {isAboutPage && (
            <div className="mb-8 flex justify-center md:hidden">
              <ShareButton
                title={seoTitle}
                description={pageData.meta_description}
                imageUrl={ogImage}
                slug={pageData.slug}
                pageUrl={canonicalUrl}
              />
            </div>
          )}

          <div 
            className={isAboutPage
              ? 'about-rich max-w-none mb-12'
              : 'prose prose-indigo max-w-none text-main/80 mb-12 dark:prose-invert'}
            dangerouslySetInnerHTML={{ __html: pageData.content }}
          />


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



  // Строим абсолютный URL для OG-картинки (мессенджеры требуют полный URL)
  // og_image из API уже может быть полным CDN URL (https://cdn.mudaroba.com/...)
  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mudaroba.com').replace(/\/$/, '')
  let ogImageAbsoluteUrl = `${siteUrl}/og-default.png` // глобальный fallback

  if (pageData.og_image) {
    const img = String(pageData.og_image)
    if (img.startsWith('http://') || img.startsWith('https://')) {
      // Уже полный URL (CDN) — используем as-is
      ogImageAbsoluteUrl = img
    } else if (img.startsWith('/')) {
      ogImageAbsoluteUrl = `${siteUrl}${img}`
    } else {
      ogImageAbsoluteUrl = `${siteUrl}/media/${img.replace(/^\//, '')}`
    }
  }

  return {
    props: {
      pageData: {
        ...pageData,
        og_image: ogImageAbsoluteUrl,
      },
      pageLocale: lang,

      ...(await serverSideTranslations(ctx.locale ?? 'ru', ['common'])),
    },
  }
}
