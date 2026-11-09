import Link from 'next/link'
import { useRouter } from 'next/router'
import { useTranslation } from 'next-i18next'

import { formatCount } from '../lib/homeFacts'

interface HomeFactsBlockProps {
  /** Позиций в каталоге (товары и справочник лекарств), вниз до тысяч; 0 — фраза без чисел */
  productsCount: number
  /** Брендов с товарами; 0 — фраза без чисел */
  brandsCount: number
}

/**
 * «Как работает Mudaroba» — короткие факты о сайте простыми предложениями, чтобы
 * поисковикам и ИИ-ассистентам было что цитировать на вопрос «что такое Mudaroba».
 * Рендерится на сервере (не в DeferredSection), стоит в конце главной — первый экран не меняется.
 *
 * TODO(owner): все тексты блока (ключи home_facts_* в public/locales/{ru,en}/common.json) —
 * черновик на согласование. Отдельно подтвердить: сроки (товары 7–14 дней от 5 $ — как на карточках,
 * лекарства 7–21 рабочий день), «доставляем в Россию и страны СНГ», «команда работает в Стамбуле».
 */
export default function HomeFactsBlock({ productsCount, brandsCount }: HomeFactsBlockProps) {
  const { t } = useTranslation('common')
  const { locale = 'ru' } = useRouter()
  const hasCounts = productsCount > 0 && brandsCount > 0

  const facts = [
    {
      title: t('home_facts_catalog_title', 'Что продаётся'),
      text: hasCounts
        ? t('home_facts_catalog_text', 'Mudaroba — интернет-магазин товаров из Турции. В каталоге больше {{products}} позиций, брендов — {{brands}}: одежда и обувь, мебель, косметика и парфюмерия, БАДы и витамины, а также справочник лекарств из турецких аптек.', {
            products: formatCount(productsCount, locale),
            brands: formatCount(brandsCount, locale),
          })
        : t('home_facts_catalog_text_short', 'Mudaroba — интернет-магазин товаров из Турции: одежда и обувь, мебель, косметика и парфюмерия, БАДы и витамины, а также справочник лекарств из турецких аптек.'),
    },
    {
      title: t('home_facts_order_title', 'Как заказать'),
      text: t('home_facts_order_text', 'Онлайн-оплаты на сайте нет. Добавьте товары в заявку и отправьте её или напишите менеджеру в Telegram или WhatsApp. Менеджер проверит наличие и цену у продавца в Турции, назовёт итоговую сумму с доставкой и согласует способ оплаты. Платить нужно только после подтверждения заказа.'),
    },
    {
      title: t('home_facts_medicines_title', 'Лекарства'),
      text: t('home_facts_medicines_text', 'Сайт не продаёт лекарства: цены в карточках — справочные цены турецких аптек. По заявке менеджер подбирает препарат, проверяет наличие и рассчитывает стоимость с доставкой. Рецептурные препараты применяют только по назначению врача.'),
    },
    {
      title: t('home_facts_delivery_title', 'Доставка'),
      text: t('home_facts_delivery_text', 'Доставляем в Россию и страны СНГ. Товары из Турции идут 7–14 дней, доставка — от 5 $; лекарства — 7–21 рабочий день. Точные срок и сумму менеджер называет в расчёте. По Стамбулу курьер привозит лекарства и БАДы в отель или домой в течение дня, заказ — от 1000 лир. Команда работает в Стамбуле.'),
    },
  ]

  const links = [
    { href: '/how-to-order-medicines', label: t('home_facts_link_how_to_order', 'Как заказать лекарства из Турции') },
    { href: '/delivery', label: t('footer_delivery_payment', 'Доставка и оплата') },
    { href: '/dostavka-lekarstv-stambul', label: t('footer_istanbul_delivery', 'Доставка лекарств по Стамбулу') },
  ]

  return (
    <section className="mb-12" aria-labelledby="home-facts-title">
      <h2 id="home-facts-title" className="text-2xl md:text-3xl font-bold text-main mb-8 text-center">
        {t('home_facts_title', 'Как работает Mudaroba')}
      </h2>
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-6">
        <div className="grid gap-6 md:grid-cols-2">
          {facts.map((fact) => (
            <div key={fact.title}>
              <h3 className="mb-2 text-lg font-semibold text-main">{fact.title}</h3>
              <p className="leading-relaxed text-main">{fact.text}</p>
            </div>
          ))}
        </div>
        <ul className="mt-6 flex flex-wrap gap-2">
          {links.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="inline-flex min-h-11 items-center rounded-full border border-[var(--border)] bg-[var(--bg)] px-4 py-2 text-sm text-main transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
