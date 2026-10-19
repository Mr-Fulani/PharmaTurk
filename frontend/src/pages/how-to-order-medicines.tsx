import axios from 'axios'
import { GetServerSideProps } from 'next'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'
import { serverSideTranslations } from 'next-i18next/serverSideTranslations'
import { ArrowRightIcon } from '@heroicons/react/24/outline'

import SEO from '../components/SEO'
import BannerCarousel from '../components/BannerCarouselMedia'
import HowToOrderGuide, { HowToOrderContacts, getHowToOrderFaqs } from '../components/HowToOrderGuide'
import { buildHowToOrderSchemas } from '../lib/howToOrder'
import { SITE_URL } from '../lib/siteMeta'
import { getInternalApiUrl } from '../lib/urls'

const SourcingRequestForm = dynamic(() => import('../components/SourcingRequestForm'), { ssr: false })

const PAGE_PATH = '/how-to-order-medicines'

export default function HowToOrderMedicinesPage({ contacts, banners }: { contacts: HowToOrderContacts; banners: any[] }) {
  const { t } = useTranslation('common')
  const router = useRouter()
  const localePrefix = router.locale && router.locale !== router.defaultLocale ? `/${router.locale}` : ''

  const title = t('hto_h1', 'Как заказать лекарства из Турции и Европы')
  const faqs = getHowToOrderFaqs(t)
  const breadcrumbs = [
    { href: '/', label: t('breadcrumb_home', 'Главная') },
    { href: '/categories/medicines', label: t('hto_breadcrumb_medicines', 'Лекарства') },
    { href: PAGE_PATH, label: t('hto_breadcrumb', 'Как заказать') },
  ]

  return (
    <>
      <SEO
        title={t('hto_meta_title', 'Как заказать лекарства из Турции и Европы — заявка и доставка')}
        description={t('hto_meta_description', 'Заказ лекарств из Турции и Европы по заявке: подбор и проверка наличия, расчёт, оплата после расчёта, доставка. Стоматологические препараты для клиник.')}
        canonical={PAGE_PATH}
        structuredData={buildHowToOrderSchemas({ siteUrl: SITE_URL, localePrefix, faqs, breadcrumbs })}
      />
      <main className="bg-page text-main min-h-screen">
        <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6 sm:py-8">
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
            <h1 className="text-3xl font-bold leading-tight text-main md:text-5xl">{title}</h1>
            <p className="mt-4 text-base text-main/75 md:text-lg">
              {t('hto_lead', 'Подберём препарат, проверим наличие в аптеках и у поставщиков Турции и Европы, рассчитаем стоимость с доставкой. Для клиник — стоматологические препараты, которых нет в розничных аптеках.')}
            </p>
            <p className="mt-3 text-sm text-main/60">
              {t('hto_disclaimer', 'Сайт не продаёт лекарства: мы консультируем, подбираем и организуем доставку, оплата — только после согласованного расчёта.')}
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
              <a
                href="#sourcing"
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-6 py-3.5 text-base font-semibold text-white shadow-md transition-all hover:-translate-y-0.5 hover:bg-[var(--accent-strong)] hover:shadow-lg"
              >
                {t('hto_cta_request', 'Оставить заявку')}
                <ArrowRightIcon className="h-5 w-5" aria-hidden="true" />
              </a>
              <a
                href="#dental"
                className="inline-flex items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--surface)] px-6 py-3.5 text-base font-semibold text-main transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                {t('hto_cta_clinics', 'Для стоматологических клиник')}
              </a>
            </div>
          </header>

          {/* Баннеры позиции «Страница „Как заказать“» — включаются и заполняются в админке */}
          {banners.length > 0 && (
            <div className="mt-10">
              <BannerCarousel position="how_to_order" initialBanners={banners} />
            </div>
          )}

          <div className="mt-14 md:mt-20">
            <HowToOrderGuide faqs={faqs} contacts={contacts} />
          </div>

          <div className="mt-14 md:mt-20">
            <SourcingRequestForm
              placement="how_to_order"
              title={t('hto_form_title', 'Не нашли препарат в каталоге? Пришлите название, ссылку или фото')}
              subtitle={t('hto_form_subtitle', 'Менеджер проверит наличие в Турции и Европе, рассчитает стоимость с доставкой и свяжется с вами выбранным способом.')}
            />
          </div>
        </div>
      </main>
    </>
  )
}

export const getServerSideProps: GetServerSideProps = async (ctx) => {
  const locale = ctx.locale ?? 'ru'
  const langHeaders = { 'Accept-Language': locale, 'X-Language': locale }
  const [footerRes, bannersRes] = await Promise.allSettled([
    axios.get(getInternalApiUrl('settings/footer-settings'), { timeout: 3000 }),
    axios.get(getInternalApiUrl('catalog/banners'), { params: { position: 'how_to_order' }, headers: langHeaders, timeout: 3000 }),
  ])
  const footer = footerRes.status === 'fulfilled' ? footerRes.value.data || {} : {}
  const contacts: HowToOrderContacts = {
    phone: footer.phone || '',
    email: footer.email || '',
    telegram_url: footer.telegram_url || '',
    whatsapp_url: footer.whatsapp_url || '',
  }
  // Баннеры необязательны: ошибка API не ломает страницу
  const banners = bannersRes.status === 'fulfilled' && Array.isArray(bannersRes.value.data) ? bannersRes.value.data : []
  return {
    props: {
      contacts,
      banners,
      ...(await serverSideTranslations(locale, ['common'])),
    },
  }
}
