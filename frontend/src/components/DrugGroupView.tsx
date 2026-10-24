import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'

import CategoryLandingBlock from './CategoryLandingBlock'
import { formatIsoDate, splitParagraphs } from '../lib/drugGroup'
import { formatPrice } from '../lib/price'
import { buildProductUrl } from '../lib/urls'
import { DRUG_GROUP_ARTICLE_SLUGS, getBlogArticle } from '../content/blog/articles'

export interface DrugGroupTranslation {
  locale: string
  name: string
  active_ingredient: string
  indications: string
  usage_summary: string
  h1: string
  meta_title: string
  meta_description: string
  seo_text: string
}

export interface DrugGroup {
  slug: string
  name: string
  updated_at: string | null
  forms_count: number
  prescription: boolean
  cold_chain: boolean
  translations: DrugGroupTranslation[]
}

export interface DrugGroupForm {
  slug: string
  name: string
  active_ingredient: string
  price: string | number | null
  currency: string
  product_type: string
}

interface DrugGroupViewProps {
  group: DrugGroup
  forms: DrugGroupForm[]
  h1: string
  heading: string
  ingredient: string
  priceText: string
  indications: string
  usageSummary: string
  seoText: string
  breadcrumbs: Array<{ href: string; label: string }>
}

function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'warning' | 'info' }) {
  const toneClass =
    tone === 'warning'
      ? 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-500/40 dark:bg-amber-900/30 dark:text-amber-100'
      : tone === 'info'
        ? 'border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-500/40 dark:bg-sky-900/30 dark:text-sky-100'
        : 'border-[var(--border)] bg-[var(--surface)] text-main'
  return <span className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-medium ${toneClass}`}>{children}</span>
}

function TextSection({ title, text, children }: { title: string; text: string; children?: React.ReactNode }) {
  const paragraphs = splitParagraphs(text)
  if (paragraphs.length === 0) return null
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-6">
      <h2 className="mb-3 text-xl font-semibold text-main">{title}</h2>
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="mb-3 leading-relaxed text-main last:mb-0">
          {paragraph}
        </p>
      ))}
      {children}
    </section>
  )
}

/** Страница препарата: шапка с пометками, формы с ценами, показания, кратко о применении. */
export default function DrugGroupView({
  group,
  forms,
  h1,
  heading,
  ingredient,
  priceText,
  indications,
  usageSummary,
  seoText,
  breadcrumbs,
}: DrugGroupViewProps) {
  const { t } = useTranslation('common')
  const { locale = 'ru' } = useRouter()
  const updated = formatIsoDate(group.updated_at)
  const articles = DRUG_GROUP_ARTICLE_SLUGS.map((slug) => getBlogArticle(slug, locale)).filter(Boolean) as Array<{ slug: string; title: string }>

  return (
    <main className="bg-page text-main min-h-screen">
      <div className="mx-auto max-w-4xl px-4 py-4 sm:px-6 sm:py-8">
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

        <header className="mb-8">
          <h1 className="text-3xl font-bold leading-tight text-main md:text-4xl">{h1}</h1>
          {ingredient && (
            <p className="mt-3 text-lg text-main/80">
              {t('drug_group_active_ingredient', 'Действующее вещество')}: <span className="font-medium text-main">{ingredient}</span>
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {group.prescription && <Badge tone="warning">{t('prescription_required', 'Отпускается по рецепту')}</Badge>}
            {group.cold_chain && <Badge tone="info">{t('drug_group_cold_chain', 'Хранение и перевозка при 2–8 °C.')}</Badge>}
            <Badge>{t('drug_group_forms_count', 'Форм и дозировок: {{count}}', { count: forms.length })}</Badge>
            {priceText && <Badge>{t('drug_group_price_from', 'Цена от {{price}}', { price: priceText })}</Badge>}
          </div>
        </header>

        <div className="space-y-6">
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-6">
            <h2 className="mb-4 text-xl font-semibold text-main">
              {t('drug_group_forms_title', '{{heading}}: формы и дозировки', { heading })}
            </h2>
            <ul className="divide-y divide-[var(--border)]">
              {forms.map((form) => {
                const price = Number(form.price) > 0 ? `${formatPrice(form.price, form.currency, locale)} ${form.currency}` : null
                return (
                  <li key={form.slug} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                    <div className="min-w-0">
                      <Link
                        href={buildProductUrl(form.product_type, form.slug)}
                        className="font-medium text-main underline-offset-2 hover:text-[var(--accent)] hover:underline"
                      >
                        {form.name}
                      </Link>
                      {form.active_ingredient && <p className="text-sm text-main/70">{form.active_ingredient}</p>}
                    </div>
                    <span className="shrink-0 text-base font-semibold text-main">
                      {price || t('drug_group_price_on_request', 'Цена по запросу')}
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>

          <TextSection title={t('drug_group_indications_title', 'От чего помогает')} text={indications} />
          <TextSection title={t('drug_group_usage_title', 'Как применять — кратко')} text={usageSummary}>
            <p className="mt-3 text-sm text-main/70">
              {t('drug_group_usage_note', 'Дозы и схемы у каждой формы свои — смотрите полную инструкцию на странице формы и следуйте назначению врача.')}
            </p>
          </TextSection>

          <p className="text-sm text-main/70">
            {t('drug_group_source', 'Источник: инструкции производителей, зарегистрированные в Турции (TİTCK).')}
            {updated && <> {t('drug_group_updated', 'Обновлено: {{date}}.', { date: updated })}</>}
          </p>

          <div className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-4 text-xs leading-relaxed text-amber-900 dark:border-amber-500/40 dark:bg-amber-900/30 dark:text-amber-100 sm:px-5">
            <p className="mb-2 text-sm font-semibold">{t('important_information', 'Важная информация')}</p>
            <div className="space-y-1.5">
              <p>{t('medicine_disclaimer_line1', 'Наш сайт не продает лекарства.')}</p>
              <p>{t('medicine_disclaimer_line4', 'Указанные цены являются рекомендованными розничными ценами для аптек и могут меняться.')}</p>
              <p>{t('drug_group_doctor_note', 'Препарат применяют по назначению врача. Информация на странице не заменяет консультацию специалиста.')}</p>
            </div>
          </div>

          <CategoryLandingBlock
            linkGroups={[
              {
                title: t('drug_group_read_also', 'Читайте также'),
                links: articles.map((article) => ({ href: `/blog/${article.slug}`, label: article.title })),
              },
            ]}
            seoText={seoText}
          />
        </div>
      </div>
    </main>
  )
}
