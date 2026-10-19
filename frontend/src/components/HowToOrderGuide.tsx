import Link from 'next/link'
import type { TFunction } from 'i18next'
import { useTranslation } from 'next-i18next'
import {
  ArrowRightIcon,
  BuildingOffice2Icon,
  CalculatorIcon,
  ChatBubbleLeftRightIcon,
  CheckCircleIcon,
  ClockIcon,
  CreditCardIcon,
  DocumentTextIcon,
  EnvelopeIcon,
  GlobeEuropeAfricaIcon,
  MagnifyingGlassIcon,
  MapPinIcon,
  PhoneIcon,
  ShieldCheckIcon,
  TruckIcon,
  UserIcon,
} from '@heroicons/react/24/outline'

export type HowToOrderContacts = {
  phone?: string | null
  email?: string | null
  telegram_url?: string | null
  whatsapp_url?: string | null
}

export type HowToOrderFaq = { q: string; a: string }

/** Вопросы FAQ — общие для видимого блока и FAQPage JSON-LD (ответы в разметке должны совпадать с текстом на странице). */
export function getHowToOrderFaqs(t: TFunction): HowToOrderFaq[] {
  return [
    { q: t('hto_faq_q1', 'Можно ли купить лекарства прямо на сайте?'), a: t('hto_faq_a1', 'Нет, сайт не продаёт лекарства. Мы — сервис-посредник: консультируем по наличию и ценам, подбираем препарат по вашей заявке, рассчитываем стоимость и организуем доставку из Турции и Европы.') },
    { q: t('hto_faq_q2', 'Какие данные нужны для заявки?'), a: t('hto_faq_a2', 'Название препарата, форма выпуска, дозировка, количество и страна доставки. Если не уверены — пришлите фото упаковки или ссылку, менеджер уточнит детали.') },
    { q: t('hto_faq_q3', 'Нужен ли рецепт?'), a: t('hto_faq_a3', 'Для безрецептурных препаратов — нет. Для рецептурных может потребоваться рецепт врача: требования зависят от препарата и страны доставки, менеджер подскажет их до расчёта.') },
    { q: t('hto_faq_q4', 'Можно ли заказать препараты из Европы?'), a: t('hto_faq_a4', 'Да. Если нужного препарата нет в Турции или нужен конкретный производитель, проверим наличие у поставщиков в странах Европы и сообщим срок и стоимость.') },
    { q: t('hto_faq_q5', 'Как заказать стоматологические препараты для клиники?'), a: t('hto_faq_a5', 'Отправьте заявку от клиники: список препаратов, фото или ссылки и контакты. Такие препараты не продаются в розничных аптеках — подбираем их у профильных поставщиков и рассчитываем под объём клиники.') },
    { q: t('hto_faq_q6', 'Когда нужно платить?'), a: t('hto_faq_a6', 'Только после расчёта: менеджер подтверждает наличие, итоговую сумму с доставкой и согласует удобный способ оплаты. Вводить данные карты на сайте не нужно.') },
    { q: t('hto_faq_q7', 'Сколько идёт доставка?'), a: t('hto_faq_a7', 'Авиадоставка — обычно от 3 до 7 дней, наземная — от 7 до 14 дней в зависимости от страны. Для препаратов из Европы добавляется время на закупку; точный срок указываем в расчёте.') },
    { q: t('hto_faq_q8', 'Как узнать актуальную цену?'), a: t('hto_faq_a8', 'Откройте карточку препарата и нажмите «Узнать актуальную цену» — обновлённая справочная цена появится прямо в карточке. Итоговую сумму с доставкой менеджер подтвердит в расчёте.') },
    { q: t('hto_faq_q9', 'Можно ли оформить одну заявку на несколько препаратов?'), a: t('hto_faq_a9', 'Да. Добавьте препараты в заявку кнопкой «В заявку» на карточках или перечислите их в форме — менеджер проверит наличие всех позиций и сделает общий расчёт.') },
    { q: t('hto_faq_q10', 'Что, если препарата нет в наличии?'), a: t('hto_faq_a10', 'Сообщим сразу и предложим варианты: другой срок поставки, другая страна или препарат с тем же действующим веществом. Решение о замене принимает ваш лечащий врач.') },
  ]
}

const sectionTitle = 'text-2xl md:text-3xl font-bold text-main'
const card = 'rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 md:p-6 shadow-sm'
const ctaPrimary =
  'inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:-translate-y-0.5 hover:bg-[var(--accent-strong)] hover:shadow-md'
const ctaSecondary =
  'inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg)] px-5 py-3 text-sm font-semibold text-main transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)]'

function ToothIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 3.5c-2.2 0-4 1.8-4 4.3 0 2.3 1 3.6 1.6 5.5.5 1.6.7 3.4 1.2 5 .3 1 .8 2.2 1.8 2.2 1.4 0 1.5-2 1.8-3.4.3-1.4.8-2.6 2.1-2.6s1.8 1.2 2.1 2.6c.3 1.4.4 3.4 1.8 3.4 1 0 1.5-1.2 1.8-2.2.5-1.6.7-3.4 1.2-5 .6-1.9 1.6-3.2 1.6-5.5 0-2.5-1.8-4.3-4-4.3-1.8 0-2.7 1-4.5 1s-2.7-1-4.5-1z" />
    </svg>
  )
}

function CheckList({ items }: { items: string[] }) {
  return (
    <ul className="mt-3 space-y-2">
      {items.map((item) => (
        <li key={item} className="flex gap-2 text-sm leading-relaxed text-main/80">
          <CheckCircleIcon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent)]" aria-hidden="true" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * Содержимое страницы «Как заказать»: шаги, источники (Турция, Европа),
 * стоматология для клиник, рецептурные/безрецептурные, сроки, документы, FAQ и контакты.
 * Формулировки — только консультация, подбор, заявка и доставка: сайт лекарства не продаёт.
 */
export default function HowToOrderGuide({ faqs, contacts }: { faqs: HowToOrderFaq[]; contacts: HowToOrderContacts }) {
  const { t } = useTranslation('common')

  const steps = [
    { Icon: ChatBubbleLeftRightIcon, title: t('hto_step1_title', 'Заявка'), text: t('hto_step1_text', 'Пришлите название, фото упаковки или ссылку — через форму, мессенджер или кнопку «В заявку» в карточке препарата.') },
    { Icon: MagnifyingGlassIcon, title: t('hto_step2_title', 'Подбор и проверка наличия'), text: t('hto_step2_text', 'Проверяем наличие в аптеках и у поставщиков Турции и Европы, сверяем форму выпуска, дозировку и срок годности.') },
    { Icon: CalculatorIcon, title: t('hto_step3_title', 'Расчёт'), text: t('hto_step3_text', 'Сообщаем итоговую стоимость с доставкой и срок. Расчёт ни к чему не обязывает.') },
    { Icon: CreditCardIcon, title: t('hto_step4_title', 'Оплата после расчёта'), text: t('hto_step4_text', 'Оплачиваете только согласованную сумму удобным способом — менеджер подскажет варианты.') },
    { Icon: TruckIcon, title: t('hto_step5_title', 'Доставка'), text: t('hto_step5_text', 'Упаковываем с учётом условий хранения, отправляем и держим вас в курсе статуса посылки.') },
  ]

  const sources = [
    { Icon: MapPinIcon, title: t('hto_source_turkey_title', 'Турция'), text: t('hto_source_turkey_text', 'Оригинальные препараты турецких и международных производителей из аптек и от дистрибьюторов Турции.'), href: '/categories/medicines', link: t('hto_source_turkey_link', 'Каталог лекарств') },
    { Icon: GlobeEuropeAfricaIcon, title: t('hto_source_europe_title', 'Европа'), text: t('hto_source_europe_text', 'Препараты, зарегистрированные в странах ЕС, — когда нужного нет в Турции или важен конкретный производитель.'), href: '#sourcing', link: t('hto_source_europe_link', 'Запросить подбор') },
    { Icon: ToothIcon, title: t('hto_source_dental_title', 'Стоматология для клиник'), text: t('hto_source_dental_text', 'Препараты и материалы для стоматологических клиник, которых нет в розничных аптеках.'), href: '#dental', link: t('hto_source_dental_link', 'Подробнее для клиник') },
  ]

  const hasPhone = Boolean((contacts.phone || '').trim())
  const hasEmail = Boolean((contacts.email || '').trim())
  const hasWhatsapp = Boolean((contacts.whatsapp_url || '').trim())
  const hasTelegram = Boolean((contacts.telegram_url || '').trim())

  return (
    <div className="space-y-14 md:space-y-20">
      {/* Шаги заказа */}
      <section aria-labelledby="hto-steps">
        <h2 id="hto-steps" className={`${sectionTitle} text-center`}>
          {t('hto_steps_title', 'Как проходит заказ — 5 шагов')}
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-center text-sm md:text-base text-main/70">
          {t('hto_steps_subtitle', 'От заявки до доставки вас ведёт один менеджер. Оплата — только после того, как вы согласовали расчёт.')}
        </p>
        <ol className="mt-8 grid gap-4 md:grid-cols-5">
          {steps.map(({ Icon, title, text }, index) => (
            <li key={title} className={`${card} relative flex gap-4 md:flex-col md:gap-3`}>
              <div className="flex shrink-0 flex-col items-center gap-2 md:flex-row">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent)] text-base font-bold text-white">
                  {index + 1}
                </span>
                <Icon className="h-6 w-6 text-[var(--accent)]" aria-hidden="true" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-main">{title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-main/70">{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Откуда препараты */}
      <section aria-labelledby="hto-sources">
        <h2 id="hto-sources" className={`${sectionTitle} text-center`}>
          {t('hto_sources_title', 'Откуда мы привозим препараты')}
        </h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {sources.map(({ Icon, title, text, href, link }) => (
            <div key={title} className={`${card} flex flex-col`}>
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)]">
                <Icon className="h-6 w-6" />
              </span>
              <h3 className="mt-4 text-lg font-semibold text-main">{title}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-main/70">{text}</p>
              {href.startsWith('#') ? (
                <a href={href} className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-[var(--accent)] hover:underline">
                  {link} <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
                </a>
              ) : (
                <Link href={href} className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-[var(--accent)] hover:underline">
                  {link} <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Стоматологические препараты для клиник */}
      <section id="dental" aria-labelledby="hto-dental" className="scroll-mt-24 overflow-hidden rounded-3xl border border-[var(--accent-muted)] bg-gradient-to-br from-[var(--accent-soft)] via-[var(--bg)] to-[var(--surface)] p-6 md:p-10">
        <div className="grid gap-8 lg:grid-cols-5 lg:items-center">
          <div className="lg:col-span-3">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[var(--accent-strong)]">
              <ToothIcon className="h-4 w-4" />
              {t('hto_dental_badge', 'Только для клиник и врачей')}
            </span>
            <h2 id="hto-dental" className={`${sectionTitle} mt-4`}>
              {t('hto_dental_title', 'Стоматологические препараты для клиник')}
            </h2>
            <p className="mt-3 text-sm md:text-base leading-relaxed text-main/80">
              {t('hto_dental_text', 'Анестетики, материалы и препараты для стоматологии, которых нет в розничных аптеках, — подбираем у профильных поставщиков Турции и Европы по заявке клиники.')}
            </p>
            <CheckList
              items={[
                t('hto_dental_point1', 'Подбор по списку, артикулу, фото упаковки или ссылке'),
                t('hto_dental_point2', 'Проверка наличия, производителя и сроков годности до оплаты'),
                t('hto_dental_point3', 'Расчёт под объём клиники и регулярные поставки'),
                t('hto_dental_point4', 'Доставка с соблюдением условий хранения'),
              ]}
            />
          </div>
          <div className="lg:col-span-2">
            <div className="rounded-2xl bg-white/85 p-6 text-center shadow-sm">
              <BuildingOffice2Icon className="mx-auto h-10 w-10 text-[var(--accent)]" aria-hidden="true" />
              <p className="mt-3 text-base font-semibold text-gray-900">
                {t('hto_dental_cta_title', 'Работаете в клинике?')}
              </p>
              <p className="mt-1 text-sm text-gray-600">
                {t('hto_dental_cta_text', 'Пришлите список препаратов — менеджер рассчитает стоимость и сроки поставки.')}
              </p>
              <a href="#sourcing" className={`${ctaPrimary} mt-4 w-full`}>
                {t('hto_dental_cta', 'Отправить заявку от клиники')}
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Рецептурные и безрецептурные */}
      <section aria-labelledby="hto-rx">
        <h2 id="hto-rx" className={`${sectionTitle} text-center`}>
          {t('hto_rx_title', 'Рецептурные и безрецептурные препараты')}
        </h2>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <div className={card}>
            <h3 className="text-lg font-semibold text-main">{t('hto_otc_title', 'Безрецептурные')}</h3>
            <p className="mt-2 text-sm leading-relaxed text-main/70">
              {t('hto_otc_text', 'Достаточно названия, дозировки и количества — проверим наличие и пришлём расчёт.')}
            </p>
          </div>
          <div className={card}>
            <h3 className="text-lg font-semibold text-main">{t('hto_prescription_title', 'Рецептурные')}</h3>
            <p className="mt-2 text-sm leading-relaxed text-main/70">
              {t('hto_prescription_text', 'Может потребоваться рецепт врача. Требования зависят от препарата и страны доставки — мы заранее подскажем, что нужно, и не отправляем препараты в обход правил страны получателя.')}
            </p>
          </div>
        </div>
      </section>

      {/* Частным лицам и клиникам */}
      <section aria-labelledby="hto-audience">
        <h2 id="hto-audience" className={`${sectionTitle} text-center`}>
          {t('hto_audience_title', 'Частным лицам и клиникам')}
        </h2>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <div className={card}>
            <div className="flex items-center gap-3">
              <UserIcon className="h-7 w-7 text-[var(--accent)]" aria-hidden="true" />
              <h3 className="text-lg font-semibold text-main">{t('hto_private_title', 'Для частных лиц')}</h3>
            </div>
            <CheckList
              items={[
                t('hto_private_point1', 'Консультация по наличию и ценам в Турции и Европе'),
                t('hto_private_point2', 'Одна заявка на несколько препаратов'),
                t('hto_private_point3', 'Оплата после расчёта, без ввода карты на сайте'),
                t('hto_private_point4', 'Доставка до двери в вашей стране'),
              ]}
            />
          </div>
          <div className={card}>
            <div className="flex items-center gap-3">
              <BuildingOffice2Icon className="h-7 w-7 text-[var(--accent)]" aria-hidden="true" />
              <h3 className="text-lg font-semibold text-main">{t('hto_clinic_title', 'Для клиник')}</h3>
            </div>
            <CheckList
              items={[
                t('hto_clinic_point1', 'Стоматологические препараты, которых нет в аптеках'),
                t('hto_clinic_point2', 'Подбор по списку и расчёт под объём'),
                t('hto_clinic_point3', 'Персональный менеджер для повторных заказов'),
                t('hto_clinic_point4', 'Счёт и документы поставки для бухгалтерии — по запросу'),
              ]}
            />
          </div>
        </div>
      </section>

      {/* Сроки и документы */}
      <section className="grid gap-4 md:grid-cols-2">
        <div className={card}>
          <div className="flex items-center gap-3">
            <ClockIcon className="h-7 w-7 text-[var(--accent)]" aria-hidden="true" />
            <h2 className="text-xl md:text-2xl font-bold text-main">{t('hto_timing_title', 'Сроки')}</h2>
          </div>
          <CheckList
            items={[
              t('hto_timing_point1', 'Проверка наличия и расчёт — после получения заявки, без предоплаты'),
              t('hto_timing_point2', 'Авиадоставка — обычно от 3 до 7 дней'),
              t('hto_timing_point3', 'Наземная доставка — от 7 до 14 дней в зависимости от страны'),
              t('hto_timing_point4', 'Препараты из Европы — плюс время на закупку, точный срок указываем в расчёте'),
            ]}
          />
        </div>
        <div className={card}>
          <div className="flex items-center gap-3">
            <DocumentTextIcon className="h-7 w-7 text-[var(--accent)]" aria-hidden="true" />
            <h2 className="text-xl md:text-2xl font-bold text-main">{t('hto_documents_title', 'Документы')}</h2>
          </div>
          <CheckList
            items={[
              t('hto_documents_point1', 'Для рецептурных препаратов — рецепт врача, если его требует страна доставки'),
              t('hto_documents_point2', 'Для клиник — реквизиты организации для расчёта и счёта'),
              t('hto_documents_point3', 'От нас — расчёт с составом заказа, производителем и сроком годности'),
              t('hto_documents_point4', 'Данные для отслеживания отправления после передачи перевозчику'),
            ]}
          />
        </div>
      </section>

      {/* FAQ */}
      <section aria-labelledby="hto-faq">
        <h2 id="hto-faq" className={`${sectionTitle} text-center`}>
          {t('hto_faq_title', 'Частые вопросы о заказе препаратов')}
        </h2>
        <div className="mx-auto mt-8 max-w-3xl space-y-3">
          {faqs.map((item) => (
            <details key={item.q} className="group rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 shadow-sm">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm md:text-base font-semibold text-main">
                <h3 className="text-sm md:text-base font-semibold">{item.q}</h3>
                <span className="text-xl leading-none text-[var(--accent)] transition-transform group-open:rotate-45" aria-hidden="true">+</span>
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-main/75">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* Контакты */}
      <section aria-labelledby="hto-contacts" className={`${card} text-center`}>
        <ShieldCheckIcon className="mx-auto h-10 w-10 text-[var(--accent)]" aria-hidden="true" />
        <h2 id="hto-contacts" className="mt-3 text-2xl font-bold text-main">
          {t('hto_contacts_title', 'Остались вопросы? Напишите менеджеру')}
        </h2>
        <p className="mx-auto mt-2 max-w-2xl text-sm text-main/70">
          {t('hto_contacts_text', 'Консультация бесплатна и ни к чему не обязывает. Ответим, есть ли препарат, сколько он стоит с доставкой и какие документы понадобятся.')}
        </p>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:justify-center">
          <a href="#sourcing" className={ctaPrimary}>
            {t('hto_cta_request', 'Оставить заявку')}
            <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
          </a>
          {hasWhatsapp && (
            <a href={contacts.whatsapp_url || ''} target="_blank" rel="noopener noreferrer" className={ctaSecondary}>
              <img src="/whatsapp-icon.png" alt="" width="18" height="18" />
              WhatsApp
            </a>
          )}
          {hasTelegram && (
            <a href={contacts.telegram_url || ''} target="_blank" rel="noopener noreferrer" className={ctaSecondary}>
              <img src="/telegram-icon.png" alt="" width="18" height="18" />
              Telegram
            </a>
          )}
          {hasPhone && (
            <a href={`tel:${(contacts.phone || '').replace(/[^\d+]/g, '')}`} className={ctaSecondary}>
              <PhoneIcon className="h-4 w-4" aria-hidden="true" />
              {contacts.phone}
            </a>
          )}
          {hasEmail && (
            <a href={`mailto:${contacts.email}`} className={ctaSecondary}>
              <EnvelopeIcon className="h-4 w-4" aria-hidden="true" />
              {contacts.email}
            </a>
          )}
        </div>
        <nav aria-label={t('hto_links_label', 'Полезные разделы')} className="mt-6 flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm">
          <Link href="/categories/medicines" className="font-medium text-[var(--accent)] hover:underline">{t('hto_link_medicines', 'Каталог лекарств')}</Link>
          <Link href="/categories/supplements" className="font-medium text-[var(--accent)] hover:underline">{t('hto_link_supplements', 'БАДы и витамины')}</Link>
          <Link href="/delivery" className="font-medium text-[var(--accent)] hover:underline">{t('hto_link_delivery', 'Доставка и оплата')}</Link>
          <Link href="/testimonials" className="font-medium text-[var(--accent)] hover:underline">{t('hto_link_testimonials', 'Отзывы клиентов')}</Link>
        </nav>
      </section>
    </div>
  )
}
