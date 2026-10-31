// Страница «Доставка лекарств по Стамбулу» (TD-035): тексты RU/EN.
// Условия владельца (31.10.2026): доставка в течение дня, стоимость — от 1000 лир.
// Способы оплаты и ночная доставка не подтверждены и не обещаются: их называет менеджер.

export const ISTANBUL_DELIVERY_PATH = '/dostavka-lekarstv-stambul'
// Иллюстрация курьера (исходник — public/istanbul-courier.svg) и её копия для соцсетей
export const ISTANBUL_COURIER_IMAGE = { src: '/istanbul-courier.webp', width: 1200, height: 630 }
export const ISTANBUL_DELIVERY_OG_IMAGE = '/og-istanbul-delivery.jpg'

// Ограниченные вещества из справочника TD-024 (docs/CONTROLLED_SUBSTANCES.md), которые чаще
// всего спрашивают, и статья о нём.
const RULES_ARTICLE = '/blog/pravila-vvoza-lekarstv-iz-turcii'

export const ISTANBUL_DELIVERY = {
  ru: {
    metaTitle: 'Доставка лекарств по Стамбулу в отель и на дом',
    metaDescription:
      'Привезём лекарства и БАДы из аптек Стамбула в отель или домой — от Султанахмета до Бейликдюзю, Эсеньюрта и Башакшехира. В течение дня, от 1000 лир.',
    breadcrumb: 'Доставка лекарств по Стамбулу',
    h1: 'Доставка лекарств в Стамбуле — в отель и по адресу',
    lead:
      'Найдём нужное лекарство или БАД в аптеках Стамбула, купим и привезём курьером в отель, квартиру или офис. Общаемся на русском: не нужно знать турецкий, искать аптеку и объяснять фармацевту, что вам нужно.',
    badges: [
      'Менеджер на русском',
      'Европейская и азиатская сторона',
      'Отель, дом или офис',
      'Лекарства, БАДы, медизделия',
      'Доставка в течение дня',
      'Доставка от 1000 лир',
    ],
    ctaWhatsapp: 'Написать в WhatsApp',
    ctaTelegram: 'Написать в Telegram',
    ctaRequest: 'Оставить заявку',
    whatsappText: 'Здравствуйте! Нужна доставка лекарств по Стамбулу. Препарат: … Адрес или отель: …',
    heroCard: {
      title: 'Ваша заявка',
      rows: [
        ['Препарат', 'по фото упаковки'],
        ['Аптека', 'Бейоглу, рядом с вами'],
        ['Куда', 'отель в Султанахмете'],
      ],
      status: 'Курьер в пути',
    },
    painsTitle: 'Почему купить лекарство в Стамбуле непросто',
    painsSubtitle: 'Эти заботы мы берём на себя — от поиска препарата до двери вашего номера.',
    pains: [
      {
        icon: 'languages',
        pain: 'Фармацевт не говорит по-русски, а привычные препараты в Турции называются иначе.',
        solution: 'Напишите нам на русском или пришлите фото упаковки — найдём турецкий препарат с тем же действующим веществом и дозировкой.',
      },
      {
        icon: 'map',
        pain: 'Незнакомый город: где ближайшая аптека и какая работает ночью (nöbetçi eczane)?',
        solution: 'Аптеки и дежурные аптеки по районам ищем сами — вам не нужно никуда ехать.',
      },
      {
        icon: 'pill',
        pain: 'В одной аптеке нужного нет, часть препаратов отпускают только по рецепту.',
        solution: 'Проверяем наличие в нескольких аптеках. По рецептурным препаратам менеджер скажет, можно ли их купить, срок и цену.',
      },
      {
        icon: 'heart',
        pain: 'Плохо себя чувствуете, вы с ребёнком или восстанавливаетесь после процедуры в клинике.',
        solution: 'Курьер привезёт заказ к двери номера, на ресепшен отеля или домой.',
      },
    ],
    audienceTitle: 'Кому подходит доставка',
    audience: [
      { icon: 'hotel', title: 'Туристам в отелях', text: 'Простуда, аллергия, расстройство желудка или забытые дома лекарства — привезём в отель.' },
      { icon: 'stethoscope', title: 'Пациентам клиник Стамбула', text: 'После стоматологии, пересадки волос или пластики — препараты по назначению вашего врача.' },
      { icon: 'home', title: 'Жителям и экспатам', text: 'Не нужно искать аптеку и объясняться по-турецки — заказ на русском с доставкой домой или в офис.' },
      { icon: 'baby', title: 'Родителям и пожилым', text: 'Детские формы, витамины и привычные препараты — без поездок по городу.' },
    ],
    catalogTitle: 'Что привозим',
    catalog: [
      { icon: 'pill', title: 'Безрецептурные лекарства', text: 'От простуды и боли, от аллергии, для желудка, детские формы.' },
      { icon: 'file', title: 'Рецептурные препараты', text: 'По рецепту врача. Можно ли купить препарат, срок и цену подтвердит менеджер.' },
      { icon: 'leaf', title: 'БАДы и витамины', text: 'Витамины, минералы, пробиотики и другие добавки из аптек Турции.' },
      { icon: 'thermometer', title: 'Медицинские изделия', text: 'Термометры, тесты, перевязочные материалы, средства ухода после процедур.' },
    ],
    restrictedTitle: 'Что не привозим',
    restrictedText:
      'Препараты строгого учёта (наркотические и психотропные — красный и зелёный рецепт) и препараты с веществами из нашего списка ограниченных: кодеин, прегабалин, трамадол, псевдоэфедрин и другие.',
    restrictedLink: { href: RULES_ARTICLE, label: 'Подробнее о списке' },
    courierAlt: 'Курьер в шлеме на мопеде везёт лекарства из аптеки по Стамбулу',
    stepsTitle: 'Как заказать — 4 шага',
    steps: [
      { icon: 'message', title: 'Напишите нам', text: 'В WhatsApp, Telegram или через форму: название, фото упаковки или рецепт, адрес или название отеля.' },
      { icon: 'search', title: 'Проверим и посчитаем', text: 'Наличие в аптеках рядом, цену препарата и доставки, срок. Ответим на русском.' },
      { icon: 'check', title: 'Подтвердите заказ', text: 'Покупаем только после вашего подтверждения. Способ оплаты согласует менеджер.' },
      { icon: 'bike', title: 'Курьер привезёт', text: 'В номер или на ресепшен отеля, в квартиру или офис — в заводской упаковке.' },
    ],
    mapTitle: 'Доставляем по всему Стамбулу',
    mapText:
      'Европейская и азиатская сторона — от Султанахмета и Таксима до Бейликдюзю, Эсеньюрта и Башакшехира, Кадыкёя и Аташехира. Доставляем в течение дня, стоимость — от 1000 лир: точную цену для вашего района менеджер назовёт до покупки.',
    mapLegend: { pharmacy: 'Аптека', destination: 'Отель или адрес', route: 'Маршрут курьера' },
    map: {
      europe: 'Европейская сторона',
      asia: 'Азиатская сторона',
      bosphorus: 'Босфор',
      marmara: 'Мраморное море',
      blackSea: 'Чёрное море',
      goldenHorn: 'Золотой Рог',
    },
    districts: {
      sariyer: 'Сарыер',
      besiktas: 'Бешикташ',
      sisli: 'Шишли',
      taksim: 'Таксим',
      beyoglu: 'Бейоглу',
      sultanahmet: 'Султанахмет',
      fatih: 'Фатих',
      bakirkoy: 'Бакыркёй',
      basaksehir: 'Башакшехир',
      esenyurt: 'Эсеньюрт',
      beylikduzu: 'Бейликдюзю',
      uskudar: 'Ускюдар',
      kadikoy: 'Кадыкёй',
      atasehir: 'Аташехир',
      maltepe: 'Малтепе',
    },
    trustTitle: 'Почему нам доверяют',
    trust: [
      { icon: 'badge', title: 'Оригинальные препараты', text: 'Покупаем в лицензированных аптеках Турции — в заводской упаковке.' },
      { icon: 'wallet', title: 'Без сюрпризов', text: 'Цену препарата и доставки называем до покупки. Платите только согласованную сумму.' },
      { icon: 'languages', title: 'На вашем языке', text: 'Менеджер на русском поможет подобрать турецкий аналог по действующему веществу.' },
      { icon: 'shield', title: 'Конфиденциально', text: 'Данные заказа и рецепта видят только менеджер и курьер.' },
    ],
    analogNote: 'Замену препарата аналогом согласуйте с лечащим врачом.',
    usefulTitle: 'Полезно знать',
    useful: [
      { href: '/blog/tureckie-analogi-lekarstv', label: 'Турецкие аналоги российских лекарств' },
      { href: '/blog/kak-proverit-tureckoe-lekarstvo', label: 'Как проверить подлинность турецкого лекарства' },
      { href: '/categories/medicines', label: 'Каталог лекарств с ценами' },
    ],
    faqTitle: 'Вопросы и ответы',
    faq: [
      { q: 'Сколько стоит доставка лекарств по Стамбулу?', a: 'Доставка стоит от 1000 лир, точная цена зависит от района. Менеджер называет цену препарата и доставки до покупки — вы ничего не платите, пока не подтвердите заказ.' },
      { q: 'Как быстро привезёте лекарство?', a: 'Доставляем в течение дня. Менеджер подтвердит срок при расчёте, до покупки: он зависит от наличия препарата в аптеках и времени заказа.' },
      { q: 'Можно ли заказать рецептурное лекарство?', a: 'В Турции часть препаратов отпускается только по рецепту. Пришлите название и рецепт врача — менеджер скажет, можно ли купить препарат, срок и стоимость.' },
      { q: 'Какие препараты вы не доставляете?', a: 'Препараты строгого учёта (наркотические и психотропные — красный и зелёный рецепт) и препараты с веществами из нашего списка ограниченных: кодеин, прегабалин, трамадол, псевдоэфедрин и другие.' },
      { q: 'Доставляете в Бейликдюзю, Эсеньюрт и Башакшехир?', a: 'Да. Привозим не только в исторический центр, но и в западные районы европейской стороны — Бейликдюзю, Эсеньюрт, Башакшехир, Бакыркёй. Точную цену доставки в ваш район менеджер назовёт до покупки.' },
      { q: 'Привезёте лекарство в отель? Что указать?', a: 'Да. Укажите название отеля, номер комнаты и имя гостя. Заказ можно оставить на ресепшене.' },
      { q: 'Я не знаю, как лекарство называется в Турции', a: 'Пришлите фото упаковки, название из вашей страны или действующее вещество — подберём турецкий препарат с тем же веществом и дозировкой. Замену согласуйте с лечащим врачом.' },
      { q: 'Как оплатить заказ?', a: 'Способ оплаты менеджер согласует при расчёте. Оплачиваете только согласованную сумму.' },
      { q: 'Доставляете ли БАДы и витамины?', a: 'Да: БАДы, витамины, пробиотики и медицинские изделия — термометры, тесты, перевязочные материалы.' },
      { q: 'Можно ли получить лекарство ночью?', a: 'В Стамбуле ночью работают дежурные аптеки (nöbetçi eczane). Возможность ночной доставки уточните у менеджера.' },
    ],
    formTitle: 'Оставьте заявку на доставку по Стамбулу',
    formSubtitle: 'Напишите название препарата, адрес или отель. Менеджер проверит наличие, назовёт цену и срок и свяжется удобным способом.',
    formComment: 'Доставка по Стамбулу. Препарат: … Адрес или отель: …',
    finalTitle: 'Нужно лекарство прямо сейчас?',
    finalText: 'Напишите менеджеру — ответим на русском, найдём препарат и привезём.',
  },
  en: {
    metaTitle: 'Medicine delivery in Istanbul to your hotel or home',
    metaDescription:
      'Medicines and supplements from Istanbul pharmacies to your hotel or home — from Sultanahmet to Beylikdüzü, Esenyurt and Başakşehir. Same day, from 1,000 TRY.',
    breadcrumb: 'Medicine delivery in Istanbul',
    h1: 'Medicine delivery in Istanbul — to your hotel or address',
    lead:
      'We find the medicine or supplement you need in Istanbul pharmacies, buy it and send a courier to your hotel, flat or office. No Turkish needed: you do not have to look for a pharmacy or explain what you need to a pharmacist.',
    badges: [
      'No Turkish needed',
      'European and Asian side',
      'Hotel, home or office',
      'Medicines, supplements, medical supplies',
      'Same-day delivery',
      'Delivery from 1,000 TRY',
    ],
    ctaWhatsapp: 'Message on WhatsApp',
    ctaTelegram: 'Message on Telegram',
    ctaRequest: 'Send a request',
    whatsappText: 'Hello! I need medicine delivery in Istanbul. Medicine: … Address or hotel: …',
    heroCard: {
      title: 'Your request',
      rows: [
        ['Medicine', 'from a package photo'],
        ['Pharmacy', 'Beyoğlu, near you'],
        ['Deliver to', 'hotel in Sultanahmet'],
      ],
      status: 'Courier on the way',
    },
    painsTitle: 'Why buying medicine in Istanbul is not easy',
    painsSubtitle: 'We take care of it — from finding the product to your room door.',
    pains: [
      {
        icon: 'languages',
        pain: 'The pharmacist may not speak your language, and familiar medicines have other names in Turkey.',
        solution: 'Write to us or send a photo of the package — we will find the Turkish product with the same active ingredient and strength.',
      },
      {
        icon: 'map',
        pain: 'An unfamiliar city: where is the nearest pharmacy and which one is open at night (nöbetçi eczane)?',
        solution: 'We search pharmacies and on-duty pharmacies by district ourselves — you do not have to go anywhere.',
      },
      {
        icon: 'pill',
        pain: 'One pharmacy may not have it, and some medicines are sold only on prescription.',
        solution: 'We check several pharmacies. For prescription medicines, a manager tells you whether they can be bought, the time and the price.',
      },
      {
        icon: 'heart',
        pain: 'You feel unwell, travel with a child or are recovering after a clinic procedure.',
        solution: 'The courier brings the order to your room door, the hotel reception or your home.',
      },
    ],
    audienceTitle: 'Who it is for',
    audience: [
      { icon: 'hotel', title: 'Tourists in hotels', text: 'A cold, an allergy, an upset stomach or medicines left at home — we deliver to your hotel.' },
      { icon: 'stethoscope', title: 'Patients of Istanbul clinics', text: 'After dental work, hair transplant or plastic surgery — medicines prescribed by your doctor.' },
      { icon: 'home', title: 'Residents and expats', text: 'No need to look for a pharmacy or explain in Turkish — order online with delivery home or to the office.' },
      { icon: 'baby', title: 'Parents and older people', text: 'Children’s forms, vitamins and usual medicines — without trips across the city.' },
    ],
    catalogTitle: 'What we deliver',
    catalog: [
      { icon: 'pill', title: 'Over-the-counter medicines', text: 'For colds and pain, allergies, the stomach, children’s forms.' },
      { icon: 'file', title: 'Prescription medicines', text: 'With a doctor’s prescription. A manager confirms whether it can be bought, the time and the price.' },
      { icon: 'leaf', title: 'Supplements and vitamins', text: 'Vitamins, minerals, probiotics and other supplements from Turkish pharmacies.' },
      { icon: 'thermometer', title: 'Medical supplies', text: 'Thermometers, tests, dressings, aftercare products.' },
    ],
    restrictedTitle: 'What we do not deliver',
    restrictedText:
      'Controlled medicines (narcotic and psychotropic — red and green prescriptions) and medicines with substances from our restricted list: codeine, pregabalin, tramadol, pseudoephedrine and others.',
    restrictedLink: { href: RULES_ARTICLE, label: 'More about the list' },
    courierAlt: 'A courier in a helmet on a moped delivering medicines from a pharmacy across Istanbul',
    stepsTitle: 'How to order — 4 steps',
    steps: [
      { icon: 'message', title: 'Message us', text: 'On WhatsApp, Telegram or via the form: the name, a package photo or a prescription, your address or hotel.' },
      { icon: 'search', title: 'We check and price it', text: 'Availability in nearby pharmacies, the price of the medicine and delivery, the time.' },
      { icon: 'check', title: 'Confirm the order', text: 'We buy only after you confirm. A manager agrees the payment method with you.' },
      { icon: 'bike', title: 'The courier delivers', text: 'To your room or hotel reception, flat or office — in the original package.' },
    ],
    mapTitle: 'We deliver across Istanbul',
    mapText:
      'European and Asian side — from Sultanahmet and Taksim to Beylikdüzü, Esenyurt and Başakşehir, Kadıköy and Ataşehir. We deliver the same day, from 1,000 TRY: a manager confirms the exact price for your district before purchase.',
    mapLegend: { pharmacy: 'Pharmacy', destination: 'Hotel or address', route: 'Courier route' },
    map: {
      europe: 'European side',
      asia: 'Asian side',
      bosphorus: 'Bosphorus',
      marmara: 'Sea of Marmara',
      blackSea: 'Black Sea',
      goldenHorn: 'Golden Horn',
    },
    districts: {
      sariyer: 'Sarıyer',
      besiktas: 'Beşiktaş',
      sisli: 'Şişli',
      taksim: 'Taksim',
      beyoglu: 'Beyoğlu',
      sultanahmet: 'Sultanahmet',
      fatih: 'Fatih',
      bakirkoy: 'Bakırköy',
      basaksehir: 'Başakşehir',
      esenyurt: 'Esenyurt',
      beylikduzu: 'Beylikdüzü',
      uskudar: 'Üsküdar',
      kadikoy: 'Kadıköy',
      atasehir: 'Ataşehir',
      maltepe: 'Maltepe',
    },
    trustTitle: 'Why people trust us',
    trust: [
      { icon: 'badge', title: 'Original medicines', text: 'Bought from licensed Turkish pharmacies, in the original package.' },
      { icon: 'wallet', title: 'No surprises', text: 'We confirm the price of the medicine and delivery before purchase. You pay only the agreed amount.' },
      { icon: 'languages', title: 'No Turkish needed', text: 'A manager helps you find a Turkish equivalent by active ingredient.' },
      { icon: 'shield', title: 'Confidential', text: 'Order and prescription details are seen only by the manager and the courier.' },
    ],
    analogNote: 'Agree any replacement with your doctor.',
    usefulTitle: 'Good to know',
    useful: [
      { href: '/blog/tureckie-analogi-lekarstv', label: 'Turkish equivalents of common medicines' },
      { href: '/blog/kak-proverit-tureckoe-lekarstvo', label: 'How to check that a Turkish medicine is genuine' },
      { href: '/categories/medicines', label: 'Medicine catalogue with prices' },
    ],
    faqTitle: 'Questions and answers',
    faq: [
      { q: 'How much does medicine delivery in Istanbul cost?', a: 'Delivery starts from 1,000 TRY, the exact price depends on the district. A manager confirms the price of the medicine and delivery before purchase — you pay nothing until you confirm the order.' },
      { q: 'How fast will you deliver?', a: 'We deliver the same day. A manager confirms the time before purchase: it depends on availability in pharmacies and the time of your order.' },
      { q: 'Can I order a prescription medicine?', a: 'In Turkey some medicines are sold only on prescription. Send the name and your doctor’s prescription — a manager tells you whether it can be bought, the time and the price.' },
      { q: 'Which medicines do you not deliver?', a: 'Controlled medicines (narcotic and psychotropic — red and green prescriptions) and medicines with substances from our restricted list: codeine, pregabalin, tramadol, pseudoephedrine and others.' },
      { q: 'Do you deliver to Beylikdüzü, Esenyurt and Başakşehir?', a: 'Yes. We deliver not only to the historic centre but also to the western districts of the European side — Beylikdüzü, Esenyurt, Başakşehir, Bakırköy. A manager confirms the exact delivery price for your district before purchase.' },
      { q: 'Can you deliver to my hotel? What should I give you?', a: 'Yes. Give the hotel name, room number and guest name. The order can be left at the reception.' },
      { q: 'I do not know the Turkish name of my medicine', a: 'Send a photo of the package, the name used in your country or the active ingredient — we find the Turkish product with the same ingredient and strength. Agree any replacement with your doctor.' },
      { q: 'How do I pay?', a: 'A manager agrees the payment method when pricing the order. You pay only the agreed amount.' },
      { q: 'Do you deliver supplements and vitamins?', a: 'Yes: supplements, vitamins, probiotics and medical supplies — thermometers, tests, dressings.' },
      { q: 'Can I get medicine at night?', a: 'On-duty pharmacies (nöbetçi eczane) are open at night in Istanbul. Ask a manager whether night delivery is possible.' },
    ],
    formTitle: 'Send a request for delivery in Istanbul',
    formSubtitle: 'Write the medicine name and your address or hotel. A manager checks availability, confirms price and time and contacts you.',
    formComment: 'Delivery in Istanbul. Medicine: … Address or hotel: …',
    finalTitle: 'Need medicine right now?',
    finalText: 'Message a manager — we find the medicine and deliver it.',
  },
}

/** Тексты страницы для локали (неизвестная — RU). */
export function istanbulDeliveryContent(locale) {
  return ISTANBUL_DELIVERY[locale] || ISTANBUL_DELIVERY.ru
}

/** JSON-LD: Service с районами обслуживания и иллюстрацией, FAQPage по видимым вопросам, BreadcrumbList. */
export function buildIstanbulDeliverySchemas({ siteUrl, localePrefix, content, siteName }) {
  const pageUrl = `${siteUrl}${localePrefix}${ISTANBUL_DELIVERY_PATH}`
  return [
    {
      '@context': 'https://schema.org',
      '@type': 'Service',
      name: content.h1,
      serviceType: 'Medicine delivery',
      description: content.metaDescription,
      url: pageUrl,
      image: {
        '@type': 'ImageObject',
        url: `${siteUrl}${ISTANBUL_COURIER_IMAGE.src}`,
        width: ISTANBUL_COURIER_IMAGE.width,
        height: ISTANBUL_COURIER_IMAGE.height,
        caption: content.courierAlt,
      },
      areaServed: {
        '@type': 'City',
        name: 'Istanbul',
        containedInPlace: { '@type': 'Country', name: 'Türkiye' },
        containsPlace: Object.values(content.districts).map((name) => ({ '@type': 'Place', name })),
      },
      availableLanguage: ['ru', 'en'],
      provider: { '@type': 'Organization', name: siteName, url: siteUrl },
    },
    {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: content.faq.map(({ q, a }) => ({
        '@type': 'Question',
        name: q,
        acceptedAnswer: { '@type': 'Answer', text: a },
      })),
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: siteName, item: `${siteUrl}${localePrefix}` },
        { '@type': 'ListItem', position: 2, name: content.breadcrumb, item: pageUrl },
      ],
    },
  ]
}
