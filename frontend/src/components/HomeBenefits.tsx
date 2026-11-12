import Link from 'next/link'
import { useTranslation } from 'next-i18next'
import type { ReactNode } from 'react'

const ICON = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' } as const

function Benefit({ href, icon, title, text }: { href: string; icon: ReactNode; title: string; text: string }) {
  return (
    <Link href={href} className="group flex gap-2.5 py-3 sm:gap-3 sm:py-4 lg:px-5 lg:first:pl-0 lg:last:pr-0">
      <svg aria-hidden="true" className="mt-0.5 h-5 w-5 flex-none text-[var(--accent)] sm:h-6 sm:w-6" {...ICON}>{icon}</svg>
      <span className="min-w-0">
        <span className="block text-sm font-semibold leading-snug text-[var(--text-strong)] group-hover:text-[var(--accent)]">{title}</span>
        {/* На телефоне — только заголовки в два столбца: строка не должна отодвигать товары на экран ниже. */}
        <span className="mt-0.5 hidden text-[13px] leading-snug text-main opacity-80 sm:block">{text}</span>
      </span>
    </Link>
  )
}

/**
 * Строка преимуществ под главным баннером (блок главной `benefits`): как устроен
 * заказ, сроки, поиск по ссылке, возврат. Сроки — как на всём сайте
 * (DEVELOPMENT_RULES §5.10); оплата на сайте не обещается.
 */
export default function HomeBenefits({ sourcingHref }: { sourcingHref: string }) {
  const { t } = useTranslation('common')

  return (
    <section
      aria-label={t('home_benefits_label', 'Как мы работаем')}
      className="mb-12 grid grid-cols-2 gap-x-4 border-y border-[var(--border)] py-1 sm:gap-x-6 sm:py-0 lg:grid-cols-4 lg:gap-x-0 lg:divide-x lg:divide-[var(--border)]"
    >
      <Benefit
        href="/how-to-order-medicines"
        icon={<><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4h6v3H9zM9 12h6M9 16h4" /></>}
        title={t('home_benefit_request_title', 'Заявка вместо оплаты')}
        text={t('home_benefit_request_text', 'Онлайн-оплаты нет: менеджер сначала проверит наличие и цену')}
      />
      <Benefit
        href="/delivery"
        icon={<><path d="M3 6h11v10H3zM14 10h4l3 3v3h-7z" /><circle cx="7.5" cy="17.5" r="1.8" /><circle cx="17.5" cy="17.5" r="1.8" /></>}
        title={t('home_benefit_delivery_title', 'Доставка из Турции')}
        text={t('home_benefit_delivery_text', 'Лекарства и БАДы — 3–14 дней, остальные товары — 7–14 дней')}
      />
      <Benefit
        href={sourcingHref}
        icon={<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />}
        title={t('home_benefit_sourcing_title', 'Найдём товар по ссылке')}
        text={t('home_benefit_sourcing_text', 'Пришлите ссылку или фото с любого турецкого сайта')}
      />
      <Benefit
        href="/returns"
        icon={<><path d="M4 9h11a5 5 0 0 1 0 10H8" /><path d="m8 5-4 4 4 4" /></>}
        title={t('home_benefit_returns_title', 'Возврат 14 дней')}
        text={t('home_benefit_returns_text', 'Если товар не подошёл — по правилам возврата')}
      />
    </section>
  )
}
