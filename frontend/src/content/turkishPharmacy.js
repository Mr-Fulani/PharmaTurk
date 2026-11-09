// Страница «Аптеки Турции» (/turetskaya-apteka): кластер 2 SEO-ядра медикаментов
// («аптека в турции», «турецкая аптека», «цены в аптеках турции», ≈ 46 000 запросов в месяц).
// TODO(owner): все тексты — черновик на согласование. Проверить факты о системе аптек Турции
// (частные, без государственных сетей, единые цены на лекарства).
// Решения владельца 09.11.2026: доставка по всему миру, в первую очередь Россия и СНГ; лекарства —
// авиа 3–7, наземная 7–14, морем 20–45 дней (решение владельца 09.11.2026); способ оплаты не обещаем — согласуется с менеджером.
// Mudaroba — не аптека: не писать «аптека онлайн», «без рецепта», «купить» (тест turkishPharmacy.test.mjs).

import { buildBreadcrumbSchema, buildFaqSchema } from '../lib/blog.js'

export const TURKISH_PHARMACY_PATH = '/turetskaya-apteka'

const link = (href, text) => ({ href, text })

// Статьи блога в «Полезных ссылках»: заголовки берёт getServerSideProps (тексты статей не идут в бандл)
export const TURKISH_PHARMACY_BLOG_SLUGS = ['top-tureckih-lekarstv', 'tureckie-analogi-lekarstv', 'pravila-vvoza-lekarstv-iz-turcii', 'kak-proverit-tureckoe-lekarstvo']

export const TURKISH_PHARMACY = {
  ru: {
    metaTitle: 'Аптека в Турции: цены на лекарства, поиск и заказ препаратов',
    metaDescription:
      'Аптеки Турции (eczane, nöbetçi), цены TİTCK, каталог 12 тысяч лекарств. Заказ из турецкой аптеки без регистрации, доставка в Россию и СНГ: авиа 3–7, наземная 7–14, морем 20–45 дней.',
    breadcrumbMedicines: 'Лекарства',
    breadcrumb: 'Аптеки Турции',
    h1: 'Аптеки Турции: как устроены, цены на лекарства и как заказать',
    lead:
      'Турецкая аптека — eczane. Цены на лекарства в Турции регулирует государство, а часть препаратов отпускают только по рецепту. Рассказываем, как устроены аптеки в Турции, откуда берутся цены и как заказать лекарство из турецкой аптеки, если вы не в Турции.',
    notice:
      'Mudaroba — не аптека и лекарства не продаёт. На сайте собраны справочные цены турецких аптек, а заказ идёт через заявку менеджеру: он проверяет наличие, цену и возможность доставки.',
    searchLabel: 'Найти лекарство на сайте',
    searchPlaceholder: 'Например, MAJEZIK, мажезик или ибупрофен',
    searchButton: 'Найти',
    searchHint: 'Поиск по каталогу сайта: латиницей, кириллицей или по действующему веществу.',
    ctaCatalog: 'Каталог лекарств',
    ctaHowTo: 'Как заказать',
    sections: [
      {
        id: 'eczane',
        heading: 'Как называется аптека в Турции и как она устроена',
        blocks: [
          { type: 'p', parts: ['Аптека по-турецки — eczane (эджзане), фармацевт — eczacı. Аптеку легко узнать по вывеске с красной буквой «E».'] },
          { type: 'p', parts: ['Аптеки в Турции частные: открыть аптеку может только фармацевт, и больших аптечных сетей, как в России, нет. Государственных аптек для всех покупателей тоже нет — аптеки при государственных больницах, как правило, обслуживают пациентов самой больницы. Поэтому аптеки различаются не столько ценами на лекарства, сколько наличием препаратов.'] },
          { type: 'p', parts: ['Ночью, в воскресенье и в праздники работает дежурная аптека — nöbetçi eczane. Её адрес вывешивают на двери закрытых аптек района и публикуют на сайтах палат фармацевтов (Eczacı Odası).'] },
        ],
      },
      {
        id: 'prices',
        heading: 'Цены в аптеках Турции',
        blocks: [
          { type: 'p', parts: ['Цены на лекарства в Турции регулирует государство. Агентство по лекарственным средствам и медицинским изделиям TİTCK публикует списки цен, поэтому один и тот же препарат в разных аптеках обычно стоит одинаково. «Дешёвых аптек» почти нет — заметнее различаются цены на косметику, БАДы и товары для ухода.'] },
          { type: 'p', parts: ['Цены на сайте — справочные. Они взяты из еженедельных списков Министерства здравоохранения Турции и TİTCK: это рекомендованные розничные цены для аптек, они могут меняться и быть неактуальными. Обновлённую справочную цену покажет кнопка «Узнать актуальную цену» на странице лекарства, итоговую сумму менеджер назовёт в расчёте.'] },
        ],
      },
      {
        id: 'search',
        heading: 'Как найти турецкое лекарство на сайте',
        blocks: [
          {
            type: 'ul',
            items: [
              ['По названию латиницей, как на упаковке: ', link('/drugs/majezik', 'MAJEZIK'), ', ARVELES, DAFLON.'],
              ['По названию кириллицей или по действующему веществу: «мажезик», «ибупрофен», «декскетопрофен».'],
              ['По фото упаковки — кнопкой с камерой в поиске сайта.'],
              ['По разделам ', link('/categories/medicines', 'каталога лекарств'), ': обезболивающие, от простуды, для сердца, кожи и другие.'],
              ['Ищете замену привычному препарату? Посмотрите ', link('/blog/tureckie-analogi-lekarstv', 'таблицу турецких аналогов'), ' — препараты с тем же действующим веществом.'],
            ],
          },
          { type: 'p', parts: ['Не нашли препарат — пришлите менеджеру название, ссылку или фото упаковки через ', link('/how-to-order-medicines#sourcing', 'форму заявки'), ': проверим наличие в аптеках Турции.'] },
        ],
      },
      {
        id: 'order',
        heading: 'Как заказать лекарство из турецкой аптеки',
        blocks: [
          {
            type: 'ul',
            items: [
              ['Найдите препарат на сайте и нажмите «В заявку» — или напишите менеджеру.'],
              ['Менеджер проверит наличие в аптеках, актуальную цену, требования к рецепту и можно ли доставить препарат в вашу страну.'],
              ['Вы получите расчёт: цена препарата, доставка и срок. Способ оплаты согласуете с менеджером, оплата — только после расчёта.'],
              ['Менеджер организует покупку препарата в турецкой аптеке и доставку к вам.'],
            ],
          },
          { type: 'p', parts: ['Подробно — на странице ', link('/how-to-order-medicines', '«Как заказать лекарства из Турции»'), '.'] },
        ],
      },
      {
        id: 'prescription',
        heading: 'Рецептурные препараты',
        blocks: [
          { type: 'p', parts: ['Часть лекарств в Турции отпускают только по рецепту врача — у таких препаратов на сайте есть пометка «Отпускается по рецепту». Рецептурный препарат применяют только по назначению врача. Требования зависят от препарата и страны доставки — менеджер расскажет о них до расчёта.'] },
        ],
      },
      {
        id: 'delivery',
        heading: 'Доставка лекарств из Турции',
        blocks: [
          {
            type: 'ul',
            items: [
              ['Доставка — по всему миру, в первую очередь в Россию и страны СНГ, включая Казахстан и Узбекистан.'],
              ['Срок доставки лекарств: авиа 3–7, наземная 7–14, морем 20–45 дней; стоимость менеджер называет в расчёте.'],
              ['Препараты строгого учёта (наркотические и психотропные) мы не доставляем. У препаратов, ввоз которых в отдельные страны запрещён или ограничен законом, на сайте есть метка «Ввоз ограничен»: в эти страны доставку без согласования с менеджером не выполняем. Что можно ввозить — в статье ', link('/blog/pravila-vvoza-lekarstv-iz-turcii', 'о правилах ввоза лекарств'), '.'],
              ['Если вы в Стамбуле — ', link('/dostavka-lekarstv-stambul', 'привезём лекарство из аптеки в отель или домой'), ' в течение дня.'],
            ],
          },
        ],
      },
    ],
    faqTitle: 'Вопросы и ответы',
    faq: [
      {
        q: 'Как называется аптека в Турции?',
        a: 'Аптека по-турецки — eczane (эджзане), фармацевт — eczacı. Аптеку узнают по вывеске с красной буквой «E». Дежурная аптека, которая работает ночью, в воскресенье и в праздники, называется nöbetçi eczane.',
      },
      {
        q: 'Есть ли в Турции государственные аптеки?',
        a: 'Для обычных покупателей — нет. Аптеки в Турции частные, открыть аптеку может только фармацевт. Аптеки при государственных больницах, как правило, обслуживают пациентов больницы.',
      },
      {
        q: 'Одинаковые ли цены на лекарства в разных аптеках Турции?',
        a: 'Да, на лекарства цены обычно одинаковые: их регулирует государство, а TİTCK публикует списки цен. Различаться могут цены на косметику, БАДы и товары для ухода.',
      },
      {
        q: 'Mudaroba — это турецкая аптека?',
        a: 'Нет. Mudaroba не аптека и лекарства не продаёт. На сайте — каталог турецких лекарств со справочными ценами TİTCK и инструкциями на русском, а заказ идёт через заявку менеджеру: он проверяет наличие и цену и организует доставку.',
      },
      {
        q: 'Можно ли заказать лекарство из турецкой аптеки с доставкой в Россию?',
        a: 'Да, через заявку менеджеру. Доставка — по всему миру, в первую очередь в Россию и страны СНГ, срок для лекарств: авиа 3–7, наземная 7–14, морем 20–45 дней. Препараты строгого учёта не доставляем, а препараты с меткой «Ввоз ограничен» — только после согласования с менеджером.',
      },
      {
        q: 'Как найти дежурную аптеку в Турции ночью?',
        a: 'Ищите дежурную аптеку — nöbetçi eczane. Её адрес вывешивают на двери закрытых аптек района и публикуют на сайтах палат фармацевтов.',
      },
      {
        q: 'Есть ли турецкая аптека в Москве, Алматы или Ташкенте?',
        a: 'Своих аптек и пунктов выдачи у Mudaroba нет. Турецкое лекарство можно заказать через заявку: менеджер найдёт его в аптеке в Турции и организует доставку в ваш город.',
      },
      {
        q: 'Как найти турецкий аналог привычного лекарства?',
        a: 'Ищите по действующему веществу — оно указано в инструкции. На сайте есть таблица турецких аналогов российских препаратов, а по фото упаковки аналог подберёт менеджер. Заменять препарат стоит после консультации с врачом.',
      },
    ],
    usefulTitle: 'Полезные ссылки',
    useful: [
      link('/categories/medicines', 'Каталог лекарств из Турции'),
      link('/how-to-order-medicines', 'Как заказать лекарства из Турции'),
      link('/dostavka-lekarstv-stambul', 'Доставка лекарств по Стамбулу'),
    ],
    contactsTitle: 'Остались вопросы? Напишите менеджеру',
    contactsText: 'Ответим, есть ли препарат в аптеках Турции, сколько он стоит и как его доставить.',
    vkLabel: 'ВКонтакте',
  },
  en: {
    metaTitle: 'Pharmacy in Turkey: Medicine Prices, Search and Ordering',
    metaDescription:
      'Pharmacies in Turkey (eczane, nöbetçi), TİTCK prices, a catalog of 12,000 medicines. Order from a Turkish pharmacy, no sign-up; delivery to Russia and the CIS: air 3–7, ground 7–14, sea 20–45 days.',
    breadcrumbMedicines: 'Medicines',
    breadcrumb: 'Pharmacies in Turkey',
    h1: 'Pharmacies in Turkey: How They Work, Medicine Prices and Ordering',
    lead:
      'A Turkish pharmacy is called an eczane. Medicine prices in Turkey are regulated by the state, and some medicines are dispensed only on prescription. Here is how pharmacies in Turkey work, where the prices come from and how to order a medicine from a Turkish pharmacy if you are not in Turkey.',
    notice:
      'Mudaroba is not a pharmacy and does not sell medicines. The site lists reference prices of Turkish pharmacies, and orders go through a request to a manager who checks availability, the price and whether delivery is possible.',
    searchLabel: 'Find a medicine on the site',
    searchPlaceholder: 'For example, MAJEZIK or ibuprofen',
    searchButton: 'Search',
    searchHint: 'Searches the site catalog by brand name or active substance.',
    ctaCatalog: 'Medicine catalog',
    ctaHowTo: 'How to order',
    sections: [
      {
        id: 'eczane',
        heading: 'What a pharmacy is called in Turkey and how it works',
        blocks: [
          { type: 'p', parts: ['A pharmacy in Turkish is an eczane, and a pharmacist is an eczacı. Pharmacies are easy to spot by the sign with a red letter “E”.'] },
          { type: 'p', parts: ['Pharmacies in Turkey are private: only a pharmacist can open one, and there are no large pharmacy chains. There are no state pharmacies for the general public either — pharmacies in state hospitals usually serve the hospital’s own patients. So pharmacies differ less in medicine prices than in what they have in stock.'] },
          { type: 'p', parts: ['At night, on Sundays and on holidays a duty pharmacy is open — a nöbetçi eczane. Its address is posted on the doors of closed pharmacies in the area and on the websites of the chambers of pharmacists (Eczacı Odası).'] },
        ],
      },
      {
        id: 'prices',
        heading: 'Prices in Turkish pharmacies',
        blocks: [
          { type: 'p', parts: ['Medicine prices in Turkey are regulated by the state. The Turkish Medicines and Medical Devices Agency (TİTCK) publishes price lists, so the same medicine usually costs the same in every pharmacy. There are hardly any “cheap pharmacies” — prices differ more for cosmetics, supplements and personal care products.'] },
          { type: 'p', parts: ['Prices on the site are for reference. They come from the weekly lists of the Turkish Ministry of Health and TİTCK: these are recommended retail prices for pharmacies, they change and may be out of date. The “Check current price” button on a medicine page shows the updated reference price, and the manager gives the final amount in the quote.'] },
        ],
      },
      {
        id: 'search',
        heading: 'How to find a Turkish medicine on the site',
        blocks: [
          {
            type: 'ul',
            items: [
              ['By the brand name as printed on the pack: ', link('/drugs/majezik', 'MAJEZIK'), ', ARVELES, DAFLON.'],
              ['By the active substance: “ibuprofen”, “dexketoprofen”.'],
              ['By a photo of the pack — with the camera button in the site search.'],
              ['By sections of the ', link('/categories/medicines', 'medicine catalog'), ': painkillers, cold and flu, heart, skin and more.'],
              ['Looking for a replacement for a familiar medicine? See the ', link('/blog/tureckie-analogi-lekarstv', 'table of Turkish equivalents'), ' — medicines with the same active substance.'],
            ],
          },
          { type: 'p', parts: ['Can’t find it? Send the name, a link or a photo of the pack to a manager via the ', link('/how-to-order-medicines#sourcing', 'request form'), ': we will check availability in Turkish pharmacies.'] },
        ],
      },
      {
        id: 'order',
        heading: 'How to order a medicine from a Turkish pharmacy',
        blocks: [
          {
            type: 'ul',
            items: [
              ['Find the medicine on the site and press “Add to request” — or message a manager.'],
              ['The manager checks availability in pharmacies, the current price, prescription requirements and whether the medicine can be delivered to your country.'],
              ['You get a quote: the medicine, delivery and timing. You agree the payment method with the manager; payment only after the quote.'],
              ['The manager arranges the purchase from a Turkish pharmacy and delivery to you.'],
            ],
          },
          { type: 'p', parts: ['More details on the ', link('/how-to-order-medicines', '“How to order medicines from Turkey”'), ' page.'] },
        ],
      },
      {
        id: 'prescription',
        heading: 'Prescription medicines',
        blocks: [
          { type: 'p', parts: ['Some medicines in Turkey are dispensed only on a doctor’s prescription — such medicines are marked “Prescription Required” on the site. A prescription medicine should only be used as a doctor prescribes. Requirements depend on the medicine and the destination country — the manager explains them before the quote.'] },
        ],
      },
      {
        id: 'delivery',
        heading: 'Delivery of medicines from Turkey',
        blocks: [
          {
            type: 'ul',
            items: [
              ['Delivery is worldwide, primarily to Russia and the CIS countries, including Kazakhstan and Uzbekistan.'],
              ['Medicine delivery: air 3–7, ground 7–14, sea 20–45 days; the manager gives the delivery cost in the quote.'],
              ['We do not deliver strictly controlled medicines (narcotic and psychotropic). Medicines whose import to some countries is prohibited or restricted by law are marked “Import restricted” on the site: we do not ship them to those countries without agreement with a manager. What may be imported — see the article on ', link('/blog/pravila-vvoza-lekarstv-iz-turcii', 'rules for importing medicines'), '.'],
              ['If you are in Istanbul, ', link('/dostavka-lekarstv-stambul', 'we deliver medicines from a pharmacy to your hotel or home'), ' the same day.'],
            ],
          },
        ],
      },
    ],
    faqTitle: 'Questions and answers',
    faq: [
      {
        q: 'What is a pharmacy called in Turkey?',
        a: 'A pharmacy in Turkish is an eczane, and a pharmacist is an eczacı. Pharmacies have a sign with a red letter “E”. A duty pharmacy that is open at night, on Sundays and on holidays is called a nöbetçi eczane.',
      },
      {
        q: 'Are there state pharmacies in Turkey?',
        a: 'Not for the general public. Pharmacies in Turkey are private, and only a pharmacist can open one. Pharmacies in state hospitals usually serve the hospital’s patients.',
      },
      {
        q: 'Are medicine prices the same in all Turkish pharmacies?',
        a: 'Yes, medicine prices are usually the same: they are regulated by the state, and TİTCK publishes price lists. Prices may differ for cosmetics, supplements and personal care products.',
      },
      {
        q: 'Is Mudaroba a Turkish pharmacy?',
        a: 'No. Mudaroba is not a pharmacy and does not sell medicines. The site is a catalog of Turkish medicines with reference TİTCK prices and leaflets in English, and orders go through a request to a manager who checks availability and the price and arranges delivery.',
      },
      {
        q: 'Can I order a medicine from a Turkish pharmacy with delivery abroad?',
        a: 'Yes, through a request to a manager. Delivery is worldwide, primarily to Russia and the CIS; medicines take air 3–7, ground 7–14, sea 20–45 days. We do not deliver strictly controlled medicines, and medicines marked “Import restricted” only after agreement with a manager.',
      },
      {
        q: 'How do I find a duty pharmacy in Turkey at night?',
        a: 'Look for a duty pharmacy — a nöbetçi eczane. Its address is posted on the doors of closed pharmacies in the area and on the websites of the chambers of pharmacists.',
      },
      {
        q: 'Is there a Turkish pharmacy in Moscow, Almaty or Tashkent?',
        a: 'Mudaroba has no pharmacies or pick-up points of its own. You can order a Turkish medicine through a request: the manager finds it in a pharmacy in Turkey and arranges delivery to your city.',
      },
      {
        q: 'How do I find a Turkish equivalent of a familiar medicine?',
        a: 'Search by the active substance — it is listed in the leaflet. The site has a table of Turkish equivalents of Russian medicines, and the manager can match an equivalent from a photo of the pack. Switch medicines only after talking to a doctor.',
      },
    ],
    usefulTitle: 'Useful links',
    useful: [
      link('/categories/medicines', 'Catalog of medicines from Turkey'),
      link('/how-to-order-medicines', 'How to order medicines from Turkey'),
      link('/dostavka-lekarstv-stambul', 'Medicine delivery in Istanbul'),
    ],
    contactsTitle: 'Still have questions? Message a manager',
    contactsText: 'We will tell you whether the medicine is available in Turkish pharmacies, how much it costs and how to deliver it.',
    vkLabel: 'VK',
  },
}

/** Тексты страницы для локали (неизвестная — RU). */
export function turkishPharmacyContent(locale) {
  return TURKISH_PHARMACY[locale] || TURKISH_PHARMACY.ru
}

/** Хлебные крошки: Главная → Лекарства → Аптеки Турции (те же, что видны на странице). */
export function turkishPharmacyBreadcrumbs(content, homeLabel) {
  return [
    { href: '/', label: homeLabel },
    { href: '/categories/medicines', label: content.breadcrumbMedicines },
    { href: TURKISH_PHARMACY_PATH, label: content.breadcrumb },
  ]
}

/** JSON-LD: FAQPage по видимым вопросам и BreadcrumbList. Pharmacy/Offer нет — сайт не аптека. */
export function buildTurkishPharmacySchemas({ siteUrl, localePrefix, content, breadcrumbs }) {
  return [buildFaqSchema(content.faq), buildBreadcrumbSchema({ siteUrl, localePrefix, breadcrumbs })]
}
