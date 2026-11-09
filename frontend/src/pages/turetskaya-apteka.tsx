import Link from 'next/link'
import { GetServerSideProps } from 'next'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { ArrowRight, Info, Mail, MessageCircle, Search, Send } from 'lucide-react'

import SEO from '../components/SEO'
import { ArticleBlock, Block, FaqList } from '../components/BlogArticleBody'
import { getBlogArticle } from '../content/blog/articles'
import {
  TURKISH_PHARMACY_BLOG_SLUGS,
  TURKISH_PHARMACY_PATH,
  buildTurkishPharmacySchemas,
  turkishPharmacyBreadcrumbs,
  turkishPharmacyContent,
} from '../content/turkishPharmacy'
import { fetchFooterSettings } from '../lib/footerSettings'
import { SITE_URL } from '../lib/siteMeta'

type UsefulLink = { href: string; text: string }
type Contacts = { email: string; whatsapp_url: string; telegram_url: string; vk_url: string; instagram_url: string }

const card = 'rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-sm sm:p-6'
const ctaPrimary =
  'inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-6 py-3.5 text-base font-semibold text-white shadow-md transition-all hover:-translate-y-0.5 hover:bg-[var(--accent-strong)] hover:shadow-lg'
const ctaSecondary =
  'inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-6 py-3.5 text-base font-semibold text-main transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]'

export default function TurkishPharmacyPage({ contacts, articles }: { contacts: Contacts; articles: UsefulLink[] }) {
  const { t } = useTranslation('common')
  const { locale = 'ru', defaultLocale = 'ru' } = useRouter()
  const localePrefix = locale === defaultLocale ? '' : `/${locale}`
  const content = turkishPharmacyContent(locale)
  const breadcrumbs = turkishPharmacyBreadcrumbs(content, t('breadcrumb_home', 'Главная'))
  const socials = [
    { href: contacts.whatsapp_url, label: 'WhatsApp', icon: MessageCircle },
    { href: contacts.telegram_url, label: 'Telegram', icon: Send },
    { href: contacts.vk_url, label: content.vkLabel, icon: null },
    { href: contacts.instagram_url, label: 'Instagram', icon: null },
  ].filter((item) => item.href)

  return (
    <>
      <SEO
        title={content.metaTitle}
        description={content.metaDescription}
        canonical={TURKISH_PHARMACY_PATH}
        structuredData={buildTurkishPharmacySchemas({ siteUrl: SITE_URL, localePrefix, content, breadcrumbs })}
      />
      <main className="min-h-screen bg-page text-main">
        <div className="mx-auto max-w-5xl px-4 py-4 sm:px-6 sm:py-8">
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

          <header className="mx-auto max-w-3xl text-center">
            <h1 className="text-3xl font-bold leading-tight text-main md:text-5xl">{content.h1}</h1>
            <p className="mt-4 text-base leading-relaxed text-main/75 md:text-lg">{content.lead}</p>
            <p className="mt-4 flex items-start gap-2 rounded-xl bg-[var(--accent)]/10 p-3 text-left text-sm leading-relaxed text-main">
              <Info className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent)]" aria-hidden="true" />
              <span>{content.notice}</span>
            </p>
          </header>

          {/* Поиск по каталогу: обычная GET-форма на страницу поиска сайта, работает и без JS */}
          <form
            action={`${localePrefix}/search`}
            method="get"
            role="search"
            className={`${card} mx-auto mt-8 max-w-3xl`}
          >
            <label htmlFor="pharmacy-search" className="text-lg font-semibold text-main">{content.searchLabel}</label>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row">
              <input
                id="pharmacy-search"
                type="search"
                name="query"
                required
                aria-describedby="pharmacy-search-hint"
                placeholder={content.searchPlaceholder}
                className="min-w-0 flex-1 rounded-xl border border-[var(--border)] bg-[var(--bg)] px-4 py-3 text-base text-main outline-none focus:border-[var(--accent)]"
              />
              <button type="submit" className={ctaPrimary}>
                <Search className="h-5 w-5" aria-hidden="true" />
                {content.searchButton}
              </button>
            </div>
            <p id="pharmacy-search-hint" className="mt-2 text-sm text-main/60">{content.searchHint}</p>
          </form>
          <div className="mx-auto mt-4 flex max-w-3xl flex-col gap-3 sm:flex-row sm:justify-center">
            <Link href="/categories/medicines" className={ctaSecondary}>
              {content.ctaCatalog}
              <ArrowRight className="h-5 w-5" aria-hidden="true" />
            </Link>
            <Link href="/how-to-order-medicines" className={ctaSecondary}>
              {content.ctaHowTo}
              <ArrowRight className="h-5 w-5" aria-hidden="true" />
            </Link>
          </div>

          <div className="mt-10 space-y-6">
            {content.sections.map((section) => (
              <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`} className={`${card} scroll-mt-24`}>
                <h2 id={`${section.id}-title`} className="mb-4 text-2xl font-bold text-main">{section.heading}</h2>
                {section.blocks.map((block, index) => (
                  <ArticleBlock key={index} block={block as Block} />
                ))}
              </section>
            ))}
          </div>

          <div className="mt-10 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            <FaqList title={content.faqTitle} faq={content.faq} />
            <aside className={`${card} h-fit`}>
              <h2 className="text-xl font-semibold text-main">{content.usefulTitle}</h2>
              <ul className="mt-4 space-y-3">
                {[...content.useful, ...articles].map((item) => (
                  <li key={item.href}>
                    <Link href={item.href} className="group flex items-center justify-between gap-3 text-main transition-colors hover:text-[var(--accent)]">
                      <span>{item.text}</span>
                      <ArrowRight className="h-4 w-4 shrink-0 transition-transform group-hover:translate-x-1" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            </aside>
          </div>

          {(socials.length > 0 || contacts.email) && (
            <section aria-labelledby="pharmacy-contacts" className={`${card} mt-10 text-center`}>
              <h2 id="pharmacy-contacts" className="text-2xl font-bold text-main">{content.contactsTitle}</h2>
              <p className="mx-auto mt-2 max-w-xl text-main/75">{content.contactsText}</p>
              <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:justify-center">
                {socials.map(({ href, label, icon: Icon }) => (
                  <a key={label} href={href} target="_blank" rel="noopener noreferrer" className={ctaSecondary}>
                    {Icon && <Icon className="h-5 w-5" aria-hidden="true" />}
                    {label}
                  </a>
                ))}
                {contacts.email && (
                  <a href={`mailto:${contacts.email}`} className={ctaSecondary}>
                    <Mail className="h-5 w-5" aria-hidden="true" />
                    {contacts.email}
                  </a>
                )}
              </div>
            </section>
          )}
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const locale = ctx.locale ?? 'ru'
  // Контакты — из настроек футера (админка); пустые не выводятся, ошибка API страницу не ломает
  const footer = await fetchFooterSettings()
  const lang = locale === 'en' ? 'en' : 'ru'
  const articles: UsefulLink[] = TURKISH_PHARMACY_BLOG_SLUGS.flatMap((slug) => {
    const article = getBlogArticle(slug, lang)
    return article ? [{ href: `/blog/${article.slug}`, text: article.title }] : []
  })
  return {
    props: {
      articles,
      contacts: {
        email: footer.email || '',
        whatsapp_url: footer.whatsapp_url || '',
        telegram_url: footer.telegram_url || '',
        vk_url: footer.vk_url || '',
        instagram_url: footer.instagram_url || '',
      },
      ...(await serverSideTranslations(locale, ['common'])),
    },
  }
}
