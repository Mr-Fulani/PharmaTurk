import axios from 'axios'
import { GetServerSideProps } from 'next'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'

import SEO from '../../components/SEO'
import DrugGroupView, { DrugGroup, DrugGroupForm } from '../../components/DrugGroupView'
import {
  buildDrugGroupSchemas,
  drugGroupHeading,
  drugGroupTranslation,
  joinSentencesWithin,
  lowestPrice,
} from '../../lib/drugGroup'
import { formatPrice } from '../../lib/price'
import { defaultCurrencyForLocale } from '../../lib/requestCurrency'
import { limitTitle } from '../../lib/seoText'
import { SITE_NAME, SITE_URL } from '../../lib/siteMeta'
import { getInternalApiUrl } from '../../lib/urls'

// SEO.tsx дописывает « — Mudaroba»: вместе title не длиннее 80 символов (DEVELOPMENT_RULES §1.10)
const META_TITLE_MAX = 80 - ` — ${SITE_NAME}`.length
const META_DESCRIPTION_MAX = 200

interface DrugGroupPageProps {
  group: DrugGroup
  forms: DrugGroupForm[]
}

export default function DrugGroupPage({ group, forms }: DrugGroupPageProps) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const locale = router.locale || 'ru'
  const localePrefix = locale === router.defaultLocale ? '' : `/${locale}`
  const path = `/drugs/${group.slug}`

  const tr = drugGroupTranslation(group, locale)
  const heading = drugGroupHeading({ name: tr.name, latin: group.name })
  const ingredient = tr.active_ingredient || ''
  const minPrice = lowestPrice(forms)
  const priceText = minPrice ? `${formatPrice(minPrice.price, minPrice.currency, locale)} ${minPrice.currency}` : ''
  const h1 = tr.h1 || heading

  // С веществом — если помещается; длинное вещество («парацетамол; в части форм…») не режем многоточием
  const fullTitle = ingredient
    ? t('drug_group_meta_title', '{{heading}} — {{ingredient}}: формы, цена, инструкция', { heading, ingredient })
    : ''
  const metaTitle = limitTitle(
    tr.meta_title ||
      (fullTitle && fullTitle.length <= META_TITLE_MAX
        ? fullTitle
        : t('drug_group_meta_title_short', '{{heading}}: формы, цена, инструкция', { heading })),
    META_TITLE_MAX,
  )
  const metaDescription =
    tr.meta_description ||
    joinSentencesWithin(
      [
        ingredient
          ? t('drug_group_meta_lead', '{{heading}} ({{ingredient}}) из Турции: формы и дозировки, цены, краткая инструкция на русском.', { heading, ingredient })
          : t('drug_group_meta_lead_short', '{{heading}} из Турции: формы и дозировки, цены, краткая инструкция на русском.', { heading }),
        group.prescription ? t('drug_group_prescription', 'Отпускается по рецепту.') : '',
        group.cold_chain ? t('drug_group_cold_chain', 'Хранение и перевозка при 2–8 °C.') : '',
        priceText ? t('drug_group_meta_price', 'Цена от {{price}}.', { price: priceText }) : '',
        t('drug_group_meta_order', 'Заявка менеджеру, доставка 7–21 рабочий день.'),
      ],
      META_DESCRIPTION_MAX,
    )

  const breadcrumbs = [
    { href: '/', label: t('breadcrumb_home', 'Главная') },
    { href: '/categories/medicines', label: t('hto_breadcrumb_medicines', 'Лекарства') },
    { href: path, label: heading },
  ]

  return (
    <>
      <SEO
        title={metaTitle}
        description={metaDescription}
        canonical={path}
        structuredData={buildDrugGroupSchemas({
          siteUrl: SITE_URL,
          localePrefix,
          path,
          heading,
          latin: group.name,
          ingredient,
          description: metaDescription,
          prescription: group.prescription,
          breadcrumbs,
        })}
      />
      <DrugGroupView
        group={group}
        forms={forms}
        h1={h1}
        heading={heading}
        ingredient={ingredient}
        priceText={priceText}
        indications={tr.indications || ''}
        usageSummary={tr.usage_summary || ''}
        seoText={tr.seo_text || ''}
        breadcrumbs={breadcrumbs}
      />
    </>
  )
}

const pickLocalized = (translations: any[] | undefined, locale: string, field: string): string => {
  const item = (translations || []).find((tr) => tr?.locale === locale)
  return String(item?.[field] || '').trim()
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const slug = String(ctx.params?.slug || '')
  const locale = ctx.locale || ctx.defaultLocale || 'ru'
  const langHeaders = { 'Accept-Language': locale, 'X-Language': locale }
  // Цены зависят от валюты из cookie — в CDN кэшируем только вариант без неё (как у категорий)
  const cookieHeader = ctx.req.headers.cookie || ''
  const currencyMatch = cookieHeader.match(/(?:^|;\s*)currency=([^;]+)/)
  const currency = currencyMatch ? currencyMatch[1] : defaultCurrencyForLocale(locale)
  ctx.res.setHeader('Vary', 'Cookie, Accept-Language')
  ctx.res.setHeader('Cache-Control', currencyMatch ? 'private, no-store' : 'public, s-maxage=300, stale-while-revalidate=86400')

  try {
    const [groupRes, formsRes] = await Promise.all([
      axios.get(getInternalApiUrl(`catalog/medicine-groups/${encodeURIComponent(slug)}`), { headers: langHeaders, timeout: 5000 }),
      axios.get(getInternalApiUrl('catalog/medicines/products'), {
        params: { drug_group: slug, page_size: 50, ordering: 'price_asc' },
        headers: { ...langHeaders, 'X-Currency': currency },
        timeout: 8000,
      }),
    ])
    const rawForms: any[] = formsRes.data?.results || []
    // В props — только то, что показывает страница: полный ответ с инструкциями весит сотни КБ
    const forms: DrugGroupForm[] = rawForms.map((item) => ({
      slug: item.slug,
      name: pickLocalized(item.translations, locale, 'name') || item.name,
      active_ingredient: pickLocalized(item.translations, locale, 'active_ingredient') || item.active_ingredient || '',
      price: item.price ?? null,
      currency: item.currency || '',
      product_type: item.product_type || 'medicines',
    }))
    return {
      props: {
        group: groupRes.data,
        forms,
        ...(await serverSideTranslations(locale, ['common'])),
      },
    }
  } catch (err) {
    // 404 только по явному ответу API (DEVELOPMENT_RULES §1.5)
    if (axios.isAxiosError(err) && err.response?.status === 404) {
      return { notFound: true }
    }
    throw err
  }
}
