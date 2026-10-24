/**
 * Статьи блога (SEO-план медикаментов, пункт 4: кластеры 138–141).
 *
 * Тексты лежат в коде, а не в админке: правила плана (не писать «без рецепта», не называть
 * препараты, запрещённые к ввозу в РФ и СНГ, не обещать продажу) проверяет тест
 * src/lib/blog.test.mjs. Абзац — массив частей: строка или ссылка { href, text }.
 * Ссылки ведут на страницы препаратов (/drugs/<slug>) и карточки (/product/<slug>).
 */

const UPDATED = '2026-10-24'

const SOURCES_IMPORT = {
  ru: [
    { label: 'ФТС России: ввоз и пересылка лекарств для личного пользования', url: 'https://customs.gov.ru' },
    { label: 'Решение Совета ЕЭК от 20.12.2017 № 107 о товарах для личного пользования', url: 'https://eec.eaeunion.org' },
    { label: 'Постановления Правительства РФ № 681 (наркотические и психотропные вещества) и № 964 (сильнодействующие вещества)', url: 'https://publication.pravo.gov.ru' },
  ],
  en: [
    { label: 'Federal Customs Service of Russia: importing and mailing medicines for personal use', url: 'https://customs.gov.ru' },
    { label: 'Eurasian Economic Commission Council Decision No. 107 of 20 December 2017 on goods for personal use', url: 'https://eec.eaeunion.org' },
    { label: 'Russian Government Decrees No. 681 (narcotic and psychotropic substances) and No. 964 (potent substances)', url: 'https://publication.pravo.gov.ru' },
  ],
}

const SOURCES_TITCK = {
  ru: [
    { label: 'TİTCK — Агентство по лекарственным средствам и медицинским изделиям Турции', url: 'https://www.titck.gov.tr' },
    { label: 'Приложение «İlaç Takip Sistemi (İTS) Mobil» Минздрава Турции', url: 'https://apps.apple.com/app/id1530795592' },
  ],
  en: [
    { label: 'TİTCK — Turkish Medicines and Medical Devices Agency', url: 'https://www.titck.gov.tr' },
    { label: '“İlaç Takip Sistemi (İTS) Mobil” app by the Turkish Ministry of Health', url: 'https://apps.apple.com/app/id1530795592' },
  ],
}

const link = (href, text) => ({ href, text })

const IMPORT_FAQ = {
  ru: [
    {
      q: 'Можно ли получить лекарства из Турции в Россию?',
      a: 'Да, для личного пользования. Лицензия и разрешение Росздравнадзора физическому лицу не нужны, даже если препарат не зарегистрирован в России. Исключение — препараты с наркотическими, психотропными и сильнодействующими веществами: для них действуют отдельные правила.',
    },
    {
      q: 'Какие лекарства нельзя пересылать?',
      a: 'Препараты с наркотическими средствами и психотропными веществами пересылать в международных отправлениях запрещено Всемирной почтовой конвенцией. Препараты с сильнодействующими веществами ввозят только с документом о назначении. Проверить состав можно по перечням из постановлений Правительства РФ № 681 и № 964 или спросить менеджера.',
    },
    {
      q: 'Нужен ли рецепт, чтобы ввезти лекарство?',
      a: 'Рецепт или выписка из медицинской карты с названием и количеством препарата обязательны, если в составе есть наркотические, психотропные или сильнодействующие вещества. Документ на иностранном языке нужен с нотариальным переводом на русский. Для остальных препаратов таможня документов не требует, но рецептурный препарат применяют только по назначению врача.',
    },
    {
      q: 'Сколько лекарств можно получить в одной посылке?',
      a: 'Количество должно соответствовать личному пользованию. Беспошлинно в одной посылке можно получить товары стоимостью до 200 евро и весом до 31 кг; сверх нормы платится пошлина 15 % от превышения, но не меньше 2 евро за килограмм превышения.',
    },
    {
      q: 'Действуют ли эти правила в Казахстане и Узбекистане?',
      a: 'Казахстан, Кыргызстан, Армения и Беларусь вместе с Россией входят в ЕАЭС: общие нормы для товаров личного пользования у них одинаковые, но перечни контролируемых веществ национальные. В Узбекистане свои правила. Перед заказом уточните требования страны получателя.',
    },
  ],
  en: [
    {
      q: 'Can medicines from Turkey be sent to Russia?',
      a: 'Yes, for personal use. A private person needs no licence or Roszdravnadzor permit, even for a medicine not registered in Russia. Medicines with narcotic, psychotropic or potent substances are the exception: separate rules apply to them.',
    },
    {
      q: 'Which medicines cannot be mailed?',
      a: 'The Universal Postal Convention prohibits narcotic and psychotropic substances in international mail. Medicines with potent substances may only be imported with a document showing they were prescribed. Check the composition against the lists in Russian Government Decrees No. 681 and No. 964, or ask a manager.',
    },
    {
      q: 'Do I need a prescription to import a medicine?',
      a: 'A prescription or a medical record extract with the name and quantity of the medicine is required if it contains narcotic, psychotropic or potent substances. A document in a foreign language needs a notarised Russian translation. Customs asks for no documents for other medicines, but a prescription medicine should only be used as a doctor prescribes.',
    },
    {
      q: 'How much medicine can one parcel contain?',
      a: 'The amount must match personal use. One parcel is duty-free up to EUR 200 and 31 kg; above that a duty of 15% of the excess is charged, but at least EUR 2 per kilogram of excess.',
    },
    {
      q: 'Do the same rules apply in Kazakhstan and Uzbekistan?',
      a: 'Kazakhstan, Kyrgyzstan, Armenia and Belarus are in the Eurasian Economic Union with Russia: their personal-use rules are shared, but the lists of controlled substances are national. Uzbekistan has its own rules. Check the recipient country’s requirements before ordering.',
    },
  ],
}

export const BLOG_ARTICLES = [
  {
    slug: 'top-tureckih-lekarstv',
    publishedAt: UPDATED,
    updatedAt: UPDATED,
    ru: {
      title: 'Какие лекарства заказать из Турции: популярные препараты по разделам',
      metaTitle: 'Какие лекарства заказать из Турции: популярные препараты',
      description: 'Популярные турецкие лекарства по разделам: от боли, гриппа, аллергии, для вен, кожи и щитовидной железы. Формы, цены и инструкции на русском, что учесть перед заказом.',
      lead: 'Турецкие аптеки продают оригинальные препараты крупных производителей, часто дешевле, чем в России, а некоторых форм в российских аптеках нет совсем. Ниже — препараты, о которых чаще всего спрашивают, по разделам, и что учесть перед заказом.',
      sections: [
        {
          heading: 'Боль и воспаление',
          blocks: [
            { type: 'p', parts: [link('/drugs/majezik', 'Мажезик (MAJEZIK)'), ' с флурбипрофеном — один из самых известных турецких препаратов: таблетки, капсулы SR, спрей и раствор для горла. ', link('/drugs/arveles', 'Арвелес (ARVELES)'), ' и ', link('/drugs/dexofen', 'Дексофен (DEXOFEN)'), ' содержат декскетопрофен, как Дексалгин. Все они — нестероидные противовоспалительные средства для коротких курсов.'] },
          ],
        },
        {
          heading: 'Грипп и простуда',
          blocks: [
            { type: 'p', parts: [link('/drugs/oseflu', 'Осефлю (OSEFLU)'), ' и ', link('/drugs/enfluvir', 'Энфлувир (ENFLUVIR)'), ' — осельтамивир, как Тамифлю: лечение и профилактика гриппа, капсулы и формы для детей. При боли в горле — ', link('/drugs/kloroben', 'Клоробен (KLOROBEN)'), ' и спрей ', link('/drugs/majezik', 'Мажезик (MAJEZIK)'), '.'] },
            { type: 'p', parts: ['Многие комбинированные средства от простуды содержат вещества, ввоз которых в Россию и страны СНГ ограничен, поэтому мы их не советуем. Если сомневаетесь в составе, спросите менеджера.'] },
          ],
        },
        {
          heading: 'Аллергия',
          blocks: [
            { type: 'p', parts: ['Левоцетиризин — ', link('/product/xyzal-5-mg-20-film-tablet-xyzal-5-mg-20-film-tablet-2', 'XYZAL'), ': таблетки, капли и раствор для детей. Подбор средства от аллергии лучше согласовать с врачом.'] },
          ],
        },
        {
          heading: 'Вены, сердце, щитовидная железа',
          blocks: [
            { type: 'ul', items: [
              [link('/drugs/daflon', 'Дафлон (DAFLON)'), ' — диосмин и гесперидин того же производителя, что Детралекс: при варикозе и геморрое.'],
              [link('/drugs/crestor', 'Крестор (CRESTOR)'), ' — розувастатин для снижения холестерина, дозировки от 5 до 40 мг.'],
              [link('/drugs/levotiron', 'Левотирон (LEVOTIRON)'), ' — левотироксин при гипотиреозе, все дозировки от 25 до 200 мкг.'],
            ] },
          ],
        },
        {
          heading: 'Кожа',
          blocks: [
            { type: 'p', parts: [link('/drugs/expigment', 'Экспигмент (EXPIGMENT)'), ' — крем с гидрохиноном 2 % и 4 % от пигментных пятен; ', link('/drugs/hametan', 'Хаметан (HAMETAN)'), ' — крем и мазь с гамамелисом при раздражении кожи; ', link('/product/fucidin-2-20-gr-krem', 'FUCIDIN'), ' — крем с фузидовой кислотой.'] },
          ],
        },
        {
          heading: 'По назначению специалиста',
          blocks: [
            { type: 'p', parts: ['Мигрень — ', link('/drugs/migreout', 'Мигреоут (MIGREOUT)'), ' с ризатриптаном. Гинекология — ', link('/drugs/mirena', 'Мирена (MIRENA)'), '. Онкология и ревматология — ', link('/drugs/tamoxifen', 'Тамоксифен (TAMOXIFEN)'), ' и ', link('/drugs/methotrexate', 'Метотрексат (METHOTREXATE)'), '. Эти препараты применяют только по назначению и под наблюдением врача.'] },
          ],
        },
        {
          heading: 'Что учесть перед заказом',
          blocks: [
            { type: 'ul', items: [
              ['Рецептурный препарат применяют по назначению врача. Пометка «Отпускается по рецепту» есть на странице каждой формы.'],
              ['Оземпик, Мунджаро, Саксенда, инсулины и вакцины хранят и перевозят при 2–8 °C. Возможность доставки с соблюдением холодовой цепи и её стоимость уточнит менеджер.'],
              ['Препараты с наркотическими, психотропными и сильнодействующими веществами ввозить ограничено — подробнее в статье ', link('/blog/pravila-vvoza-lekarstv-iz-turcii', 'о правилах ввоза'), '.'],
              ['Российские названия и их турецкие аналоги собраны в ', link('/blog/tureckie-analogi-lekarstv', 'таблице аналогов'), '.'],
              ['Сайт не продаёт лекарства: вы оставляете заявку, менеджер проверяет наличие и рассчитывает стоимость, доставка — 7–21 рабочий день. Как это устроено — на странице ', link('/how-to-order-medicines', '«Как заказать»'), '.'],
            ] },
          ],
        },
      ],
      faq: [
        { q: 'Какие турецкие лекарства заказывают чаще всего?', a: 'Обезболивающие (Мажезик, Арвелес, Дексофен), противовирусные от гриппа (Осефлю, Энфлувир), Дафлон для вен, Крестор, Левотирон и кремы для кожи — Экспигмент и Хаметан.' },
        { q: 'Нужен ли рецепт?', a: 'Рецептурные препараты применяют только по назначению врача. Для ввоза в Россию рецепт или выписка обязательны, если в составе есть наркотические, психотропные или сильнодействующие вещества.' },
        { q: 'Сколько идёт доставка?', a: 'Обычно 7–21 рабочий день после подтверждения заявки. Точный срок менеджер называет вместе с расчётом стоимости.' },
        { q: 'Можно ли заказать препарат, которому нужен холод?', a: 'Препараты, которые хранят при 2–8 °C, везут только с соблюдением холодовой цепи. Возможность такой доставки и её стоимость уточнит менеджер.' },
      ],
      sources: SOURCES_TITCK.ru,
    },
    en: {
      title: 'Which medicines to order from Turkey: popular products by category',
      metaTitle: 'Which medicines to order from Turkey: popular products',
      description: 'Popular Turkish medicines by category: pain, flu, allergy, veins, skin and thyroid. Forms, prices and patient leaflets, and what to check before ordering.',
      lead: 'Turkish pharmacies sell original medicines from major manufacturers, often cheaper than elsewhere, and some forms are hard to find abroad. Here are the medicines people ask about most, by category, and what to check before ordering.',
      sections: [
        {
          heading: 'Pain and inflammation',
          blocks: [
            { type: 'p', parts: [link('/drugs/majezik', 'MAJEZIK'), ' with flurbiprofen is one of the best-known Turkish medicines: tablets, SR capsules, a throat spray and a gargle. ', link('/drugs/arveles', 'ARVELES'), ' and ', link('/drugs/dexofen', 'DEXOFEN'), ' contain dexketoprofen. All of them are NSAIDs for short courses.'] },
          ],
        },
        {
          heading: 'Flu and colds',
          blocks: [
            { type: 'p', parts: [link('/drugs/oseflu', 'OSEFLU'), ' and ', link('/drugs/enfluvir', 'ENFLUVIR'), ' contain oseltamivir, like Tamiflu: flu treatment and prevention, capsules and children’s forms. For a sore throat — ', link('/drugs/kloroben', 'KLOROBEN'), ' and the ', link('/drugs/majezik', 'MAJEZIK'), ' spray.'] },
            { type: 'p', parts: ['Many combination cold medicines contain substances whose import into Russia and other CIS countries is restricted, so we do not recommend them. If in doubt about the composition, ask a manager.'] },
          ],
        },
        {
          heading: 'Allergy',
          blocks: [
            { type: 'p', parts: ['Levocetirizine — ', link('/product/xyzal-5-mg-20-film-tablet-xyzal-5-mg-20-film-tablet-2', 'XYZAL'), ': tablets, drops and an oral solution for children. Agree the choice of an allergy medicine with a doctor.'] },
          ],
        },
        {
          heading: 'Veins, heart, thyroid',
          blocks: [
            { type: 'ul', items: [
              [link('/drugs/daflon', 'DAFLON'), ' — diosmin and hesperidin by the maker of Detralex, for varicose veins and haemorrhoids.'],
              [link('/drugs/crestor', 'CRESTOR'), ' — rosuvastatin to lower cholesterol, 5 to 40 mg.'],
              [link('/drugs/levotiron', 'LEVOTIRON'), ' — levothyroxine for hypothyroidism, every strength from 25 to 200 mcg.'],
            ] },
          ],
        },
        {
          heading: 'Skin',
          blocks: [
            { type: 'p', parts: [link('/drugs/expigment', 'EXPIGMENT'), ' — 2% and 4% hydroquinone cream for dark spots; ', link('/drugs/hametan', 'HAMETAN'), ' — witch hazel cream and ointment for irritated skin; ', link('/product/fucidin-2-20-gr-krem', 'FUCIDIN'), ' — fusidic acid cream.'] },
          ],
        },
        {
          heading: 'Prescribed by a specialist',
          blocks: [
            { type: 'p', parts: ['Migraine — ', link('/drugs/migreout', 'MIGREOUT'), ' with rizatriptan. Gynaecology — ', link('/drugs/mirena', 'MIRENA'), '. Oncology and rheumatology — ', link('/drugs/tamoxifen', 'TAMOXIFEN'), ' and ', link('/drugs/methotrexate', 'METHOTREXATE'), '. These are used only as prescribed and under a doctor’s supervision.'] },
          ],
        },
        {
          heading: 'Before you order',
          blocks: [
            { type: 'ul', items: [
              ['A prescription medicine is used as a doctor prescribes. Every form page shows whether it is a prescription medicine.'],
              ['Ozempic, Mounjaro, Saxenda, insulins and vaccines are stored and shipped at 2–8 °C. A manager will tell you whether cold-chain delivery is possible and what it costs.'],
              ['Importing medicines with narcotic, psychotropic or potent substances is restricted — see the article ', link('/blog/pravila-vvoza-lekarstv-iz-turcii', 'on import rules'), '.'],
              ['Russian brand names and their Turkish equivalents are in the ', link('/blog/tureckie-analogi-lekarstv', 'equivalents table'), '.'],
              ['The site does not sell medicines: you send a request, a manager checks availability and prices it, delivery takes 7–21 business days. See ', link('/how-to-order-medicines', 'How to order'), '.'],
            ] },
          ],
        },
      ],
      faq: [
        { q: 'Which Turkish medicines are ordered most often?', a: 'Painkillers (MAJEZIK, ARVELES, DEXOFEN), flu antivirals (OSEFLU, ENFLUVIR), DAFLON for veins, CRESTOR, LEVOTIRON and skin creams such as EXPIGMENT and HAMETAN.' },
        { q: 'Do I need a prescription?', a: 'Prescription medicines are used only as a doctor prescribes. To import into Russia, a prescription or medical extract is required if the medicine contains narcotic, psychotropic or potent substances.' },
        { q: 'How long does delivery take?', a: 'Usually 7–21 business days after the request is confirmed. The manager gives the exact time together with the price.' },
        { q: 'Can I order a medicine that must be kept cold?', a: 'Medicines stored at 2–8 °C travel only in a cold chain. A manager will confirm whether such delivery is possible and what it costs.' },
      ],
      sources: SOURCES_TITCK.en,
    },
  },
  {
    slug: 'tureckie-analogi-lekarstv',
    publishedAt: UPDATED,
    updatedAt: UPDATED,
    ru: {
      title: 'Турецкие аналоги российских лекарств: таблица',
      metaTitle: 'Турецкие аналоги лекарств: таблица по действующему веществу',
      description: 'Таблица турецких аналогов: Детралекс — Дафлон, Тамифлю — Осефлю, Дексалгин — Арвелес, Эутирокс — Левотирон и другие. Действующее вещество и ссылки на препараты.',
      lead: 'В Турции многие препараты продаются под другими названиями. Аналог — препарат с тем же действующим веществом; дозировка, форма и вспомогательные вещества могут отличаться. В таблице — российское название, вещество и турецкий препарат из каталога.',
      sections: [
        {
          heading: 'Таблица аналогов',
          blocks: [
            {
              type: 'table',
              head: ['В России', 'Действующее вещество', 'В Турции'],
              rows: [
                [['Детралекс'], ['диосмин + гесперидин'], [link('/drugs/daflon', 'Дафлон (DAFLON)'), ' — тот же производитель']],
                [['Тамифлю'], ['осельтамивир'], [link('/drugs/oseflu', 'Осефлю (OSEFLU)'), ', ', link('/drugs/enfluvir', 'Энфлувир (ENFLUVIR)')]],
                [['Дексалгин'], ['декскетопрофен'], [link('/drugs/arveles', 'Арвелес (ARVELES)'), ', ', link('/drugs/dexofen', 'Дексофен (DEXOFEN)')]],
                [['Эутирокс, L-тироксин'], ['левотироксин натрия'], [link('/drugs/levotiron', 'Левотирон (LEVOTIRON)')]],
                [['Мертенил, Розукард'], ['розувастатин'], [link('/drugs/crestor', 'Крестор (CRESTOR)')]],
                [['Мовалис, Амелотекс'], ['мелоксикам'], [link('/product/melox-75-mg-10-tablet', 'MELOX')]],
                [['Нурофен для детей'], ['ибупрофен'], [link('/product/pedifen-100-mg-100-ml-surup', 'PEDIFEN, сироп')]],
                [['Супракс'], ['цефиксим'], [link('/product/zimaks-400-mg-10-tablet', 'ZIMAKS')]],
                [['Амоксиклав, Флемоклав'], ['амоксициллин + клавулановая кислота'], [link('/product/augmentin-875-mg125-mg-film-kapli-tabletki-10-sht', 'AUGMENTIN')]],
                [['Ацикловир'], ['ацикловир'], [link('/product/aklovir-200-mg-25-tablet', 'AKLOVIR'), ', ', link('/product/zovirax-5-krem-2-gr', 'ZOVIRAX')]],
                [['Дифлюкан'], ['флуконазол'], [link('/product/triflucan-100-mg-7-kapsul-triflucan-100-mg-7-kapsul-2', 'TRIFLUCAN')]],
                [['Утрожестан'], ['прогестерон'], [link('/product/progestan-100-mg-30-yumusak-kapsul', 'PROGESTAN, капсулы')]],
                [['Ксимелин, Отривин'], ['ксилометазолин'], [link('/product/nasovine-nazal-sprey-nasovine-nazal-sprey-2', 'NASOVINE'), ', ', link('/product/otrivine-doz-ayarli-1-mgml-burun-spreyi-otrivine-doz-ayarli-1-mg-ml-bu', 'OTRIVINE')]],
              ],
            },
          ],
        },
        {
          heading: 'Те же бренды, что в России',
          blocks: [
            { type: 'p', parts: ['Эти препараты продаются в Турции под тем же названием: ', link('/drugs/crestor', 'Крестор (CRESTOR)'), ', ', link('/drugs/mirena', 'Мирена (MIRENA)'), ', ', link('/product/nexium-40-mg-enterik-kapli-28-pellet-tablet', 'Нексиум (NEXIUM)'), ', ', link('/product/sinecod-75-mg-100-ml-surup', 'Синекод (SINECOD)'), ', ', link('/product/rennie-duo-100-ml-suspansiyon', 'Ренни (RENNIE)'), ', ', link('/product/fucidin-500-mg-15-film-tablet', 'Фуцидин (FUCIDIN)'), ', ', link('/product/tobradex-steril-oftalmik-suspansiyon', 'Тобрадекс (TOBRADEX)'), ', ', link('/product/concor-5-mg-film-kapli-tablet', 'Конкор (CONCOR)'), ', ', link('/product/augmentin-875-mg125-mg-film-kapli-tabletki-10-sht', 'Аугментин (AUGMENTIN)'), '.'] },
          ],
        },
        {
          heading: 'Как пользоваться таблицей',
          blocks: [
            { type: 'ul', items: [
              ['Сверяйте действующее вещество и дозировку на странице формы: у турецкого препарата их может быть больше или меньше, чем у привычного.'],
              ['Заменять назначенный препарат аналогом стоит только после разговора с врачом — особенно антибиотики, гормоны и препараты для сердца.'],
              ['Нет нужного препарата в таблице — ищите по действующему веществу в ', link('/categories/medicines', 'каталоге лекарств'), ' или пришлите название менеджеру.'],
            ] },
          ],
        },
      ],
      faq: [
        { q: 'Чем аналог отличается от оригинала?', a: 'У аналога то же действующее вещество, но может быть другой производитель, другие вспомогательные вещества и дозировки. Дафлон и Детралекс выпускает один производитель — Servier.' },
        { q: 'Можно ли самому заменить препарат турецким аналогом?', a: 'Замену лучше согласовать с врачом: даже при одинаковом веществе дозировка и форма могут отличаться.' },
        { q: 'Что делать, если аналога нет в таблице?', a: 'Найдите препарат по действующему веществу в каталоге или пришлите менеджеру название, ссылку или фото упаковки — он подберёт турецкий вариант.' },
      ],
      sources: SOURCES_TITCK.ru,
    },
    en: {
      title: 'Turkish equivalents of Russian medicines: a table',
      metaTitle: 'Turkish equivalents of medicines by active ingredient',
      description: 'Turkish equivalents table: Detralex — Daflon, Tamiflu — Oseflu, Dexalgin — Arveles, Euthyrox — Levotiron and more, with the active ingredient and links to products.',
      lead: 'Many medicines are sold in Turkey under different names. An equivalent has the same active ingredient; strength, form and excipients may differ. The table lists the Russian name, the ingredient and the Turkish product in our catalogue.',
      sections: [
        {
          heading: 'Equivalents table',
          blocks: [
            {
              type: 'table',
              head: ['In Russia', 'Active ingredient', 'In Turkey'],
              rows: [
                [['Detralex'], ['diosmin + hesperidin'], [link('/drugs/daflon', 'DAFLON'), ' — same manufacturer']],
                [['Tamiflu'], ['oseltamivir'], [link('/drugs/oseflu', 'OSEFLU'), ', ', link('/drugs/enfluvir', 'ENFLUVIR')]],
                [['Dexalgin'], ['dexketoprofen'], [link('/drugs/arveles', 'ARVELES'), ', ', link('/drugs/dexofen', 'DEXOFEN')]],
                [['Euthyrox, L-thyroxine'], ['levothyroxine sodium'], [link('/drugs/levotiron', 'LEVOTIRON')]],
                [['Mertenil, Rosucard'], ['rosuvastatin'], [link('/drugs/crestor', 'CRESTOR')]],
                [['Movalis, Amelotex'], ['meloxicam'], [link('/product/melox-75-mg-10-tablet', 'MELOX')]],
                [['Nurofen for children'], ['ibuprofen'], [link('/product/pedifen-100-mg-100-ml-surup', 'PEDIFEN syrup')]],
                [['Suprax'], ['cefixime'], [link('/product/zimaks-400-mg-10-tablet', 'ZIMAKS')]],
                [['Amoxiclav, Flemoclav'], ['amoxicillin + clavulanic acid'], [link('/product/augmentin-875-mg125-mg-film-kapli-tabletki-10-sht', 'AUGMENTIN')]],
                [['Acyclovir'], ['aciclovir'], [link('/product/aklovir-200-mg-25-tablet', 'AKLOVIR'), ', ', link('/product/zovirax-5-krem-2-gr', 'ZOVIRAX')]],
                [['Diflucan'], ['fluconazole'], [link('/product/triflucan-100-mg-7-kapsul-triflucan-100-mg-7-kapsul-2', 'TRIFLUCAN')]],
                [['Utrogestan'], ['progesterone'], [link('/product/progestan-100-mg-30-yumusak-kapsul', 'PROGESTAN capsules')]],
                [['Xymelin, Otrivin'], ['xylometazoline'], [link('/product/nasovine-nazal-sprey-nasovine-nazal-sprey-2', 'NASOVINE'), ', ', link('/product/otrivine-doz-ayarli-1-mgml-burun-spreyi-otrivine-doz-ayarli-1-mg-ml-bu', 'OTRIVINE')]],
              ],
            },
          ],
        },
        {
          heading: 'Same brands as in Russia',
          blocks: [
            { type: 'p', parts: ['These are sold in Turkey under the same name: ', link('/drugs/crestor', 'CRESTOR'), ', ', link('/drugs/mirena', 'MIRENA'), ', ', link('/product/nexium-40-mg-enterik-kapli-28-pellet-tablet', 'NEXIUM'), ', ', link('/product/sinecod-75-mg-100-ml-surup', 'SINECOD'), ', ', link('/product/rennie-duo-100-ml-suspansiyon', 'RENNIE'), ', ', link('/product/fucidin-500-mg-15-film-tablet', 'FUCIDIN'), ', ', link('/product/tobradex-steril-oftalmik-suspansiyon', 'TOBRADEX'), ', ', link('/product/concor-5-mg-film-kapli-tablet', 'CONCOR'), ', ', link('/product/augmentin-875-mg125-mg-film-kapli-tabletki-10-sht', 'AUGMENTIN'), '.'] },
          ],
        },
        {
          heading: 'How to use the table',
          blocks: [
            { type: 'ul', items: [
              ['Check the active ingredient and strength on the form page: the Turkish product may be stronger or weaker than the one you know.'],
              ['Switch a prescribed medicine to an equivalent only after talking to a doctor — especially antibiotics, hormones and heart medicines.'],
              ['Not in the table? Search by active ingredient in the ', link('/categories/medicines', 'medicines catalogue'), ' or send the name to a manager.'],
            ] },
          ],
        },
      ],
      faq: [
        { q: 'How does an equivalent differ from the original?', a: 'It has the same active ingredient but may have a different maker, excipients and strengths. Daflon and Detralex are both made by Servier.' },
        { q: 'Can I switch to a Turkish equivalent myself?', a: 'Agree the switch with a doctor: even with the same ingredient the strength and form may differ.' },
        { q: 'What if the equivalent is not in the table?', a: 'Search the catalogue by active ingredient or send a manager the name, a link or a photo of the pack — they will find the Turkish option.' },
      ],
      sources: SOURCES_TITCK.en,
    },
  },
  {
    slug: 'pravila-vvoza-lekarstv-iz-turcii',
    publishedAt: UPDATED,
    updatedAt: UPDATED,
    ru: {
      title: 'Правила ввоза лекарств из Турции в Россию и СНГ',
      metaTitle: 'Правила ввоза лекарств из Турции: что можно, документы, лимиты',
      description: 'Можно ли ввозить лекарства из Турции: личное пользование, препараты с контролируемыми веществами, рецепт и перевод, лимит посылки 200 евро и 31 кг, Казахстан и Узбекистан.',
      lead: 'Лекарства для личного пользования можно ввозить в Россию и получать в посылках. Ограничения касаются препаратов с наркотическими, психотропными и сильнодействующими веществами. Ниже — основные правила по данным ФТС России и решениям ЕАЭС на октябрь 2026 года.',
      sections: [
        {
          heading: 'Обычные лекарства',
          blocks: [
            { type: 'p', parts: ['Препараты без контролируемых веществ физическое лицо ввозит и получает для личного пользования без разрешительных документов. Лицензия Минпромторга и разрешение Росздравнадзора не нужны, даже если препарат не зарегистрирован в России. Количество должно соответствовать личному, а не коммерческому использованию.'] },
          ],
        },
        {
          heading: 'Препараты с контролируемыми веществами',
          blocks: [
            { type: 'ul', items: [
              ['Наркотические средства и психотропные вещества (перечень — постановление Правительства РФ № 681) пересылать в международных почтовых отправлениях запрещено Всемирной почтовой конвенцией. Лично их ввозят в ограниченном количестве по медицинским показаниям — с рецептом или выпиской из медицинской карты и декларацией.'],
              ['Сильнодействующие и ядовитые вещества (постановление № 964) ввозят при наличии документа о назначении препарата конкретному человеку.'],
              ['В документе указывают название и количество препарата. Если он на иностранном языке, нужен нотариальный перевод на русский.'],
              ['Такие вещества встречаются не только в сильных обезболивающих: их содержат некоторые комбинированные средства от простуды и кашля, противосудорожные и снотворные. Поэтому перед заказом стоит проверить состав.'],
            ] },
            { type: 'p', parts: ['На страницах препаратов Mudaroba формы с такими веществами не показываются. Если сомневаетесь в составе, пришлите название ', link('/how-to-order-medicines', 'менеджеру'), ' — он подскажет.'] },
          ],
        },
        {
          heading: 'Лимиты для посылок',
          blocks: [
            { type: 'p', parts: ['По решению Совета ЕЭК № 107 беспошлинно в одной посылке можно получить товары стоимостью до 200 евро и весом до 31 кг. Сверх нормы платится пошлина 15 % от превышения, но не меньше 2 евро за килограмм превышения. Получатель указывает ИНН.'] },
          ],
        },
        {
          heading: 'Казахстан, Узбекистан и другие страны',
          blocks: [
            { type: 'p', parts: ['Казахстан, Кыргызстан, Армения и Беларусь вместе с Россией входят в ЕАЭС: общие правила для товаров личного пользования у них одинаковые, а перечни контролируемых веществ — национальные. Узбекистан в ЕАЭС не входит, правила там свои. Перед заказом уточните требования страны получателя.'] },
          ],
        },
        {
          heading: 'Препараты, которым нужен холод',
          blocks: [
            { type: 'p', parts: ['Оземпик, Мунджаро, Саксенда, инсулины и вакцины хранят и перевозят при 2–8 °C. Возможность доставки с соблюдением холодовой цепи и её стоимость уточнит менеджер. Условия ', link('/delivery', 'доставки'), ' — на отдельной странице.'] },
          ],
        },
      ],
      faq: IMPORT_FAQ.ru,
      sources: SOURCES_IMPORT.ru,
    },
    en: {
      title: 'Rules for importing medicines from Turkey to Russia and the CIS',
      metaTitle: 'Importing medicines from Turkey: what is allowed, documents, limits',
      description: 'Can you import medicines from Turkey: personal use, controlled substances, prescriptions and translations, the EUR 200 / 31 kg parcel limit, Kazakhstan and Uzbekistan.',
      lead: 'Medicines for personal use may be brought into Russia and received by mail. Restrictions apply to medicines with narcotic, psychotropic and potent substances. Below are the main rules according to the Russian Federal Customs Service and Eurasian Economic Union decisions as of October 2026.',
      sections: [
        {
          heading: 'Ordinary medicines',
          blocks: [
            { type: 'p', parts: ['A private person may import and receive medicines without controlled substances for personal use with no permits. No licence or Roszdravnadzor permit is needed, even for a medicine not registered in Russia. The amount must match personal, not commercial, use.'] },
          ],
        },
        {
          heading: 'Medicines with controlled substances',
          blocks: [
            { type: 'ul', items: [
              ['The Universal Postal Convention prohibits narcotic and psychotropic substances (listed in Russian Government Decree No. 681) in international mail. In person they may be brought in limited amounts for medical reasons, with a prescription or medical record extract and a customs declaration.'],
              ['Potent and toxic substances (Decree No. 964) may be imported with a document showing the medicine was prescribed to that person.'],
              ['The document states the name and quantity of the medicine. A foreign-language document needs a notarised Russian translation.'],
              ['Such substances are found not only in strong painkillers: some combination cold and cough medicines, anticonvulsants and sleeping pills contain them too, so check the composition before ordering.'],
            ] },
            { type: 'p', parts: ['Mudaroba drug pages do not show forms with such substances. If you are unsure about the composition, send the name to a ', link('/how-to-order-medicines', 'manager'), '.'] },
          ],
        },
        {
          heading: 'Parcel limits',
          blocks: [
            { type: 'p', parts: ['Under EEC Council Decision No. 107, one parcel is duty-free up to EUR 200 and 31 kg. Above that a duty of 15% of the excess is charged, but at least EUR 2 per kilogram of excess. The recipient provides a taxpayer number (INN).'] },
          ],
        },
        {
          heading: 'Kazakhstan, Uzbekistan and other countries',
          blocks: [
            { type: 'p', parts: ['Kazakhstan, Kyrgyzstan, Armenia and Belarus are in the Eurasian Economic Union with Russia: personal-use rules are shared, while lists of controlled substances are national. Uzbekistan is not in the union and has its own rules. Check the recipient country’s requirements before ordering.'] },
          ],
        },
        {
          heading: 'Medicines that must be kept cold',
          blocks: [
            { type: 'p', parts: ['Ozempic, Mounjaro, Saxenda, insulins and vaccines are stored and shipped at 2–8 °C. A manager will tell you whether cold-chain delivery is possible and what it costs. See the ', link('/delivery', 'delivery'), ' page for terms.'] },
          ],
        },
      ],
      faq: IMPORT_FAQ.en,
      sources: SOURCES_IMPORT.en,
    },
  },
  {
    slug: 'kak-proverit-tureckoe-lekarstvo',
    publishedAt: UPDATED,
    updatedAt: UPDATED,
    ru: {
      title: 'Как проверить подлинность турецкого лекарства',
      metaTitle: 'Как проверить турецкое лекарство: код İTS и признаки подделки',
      description: 'Как проверить подлинность лекарства из Турции: код DataMatrix и приложение İTS Mobil, штрихкод 869, что должно быть на упаковке и признаки подделки.',
      lead: 'В Турции каждую упаковку лекарства отслеживает государственная система İTS (İlaç Takip Sistemi) — от производителя до аптеки. Поэтому проверить подлинность препарата может любой человек со смартфоном.',
      sections: [
        {
          heading: 'Код DataMatrix (karekod) на упаковке',
          blocks: [
            { type: 'p', parts: ['На каждой коробке есть квадратный код DataMatrix — по-турецки karekod. В нём записаны код товара (GTIN), серийный номер упаковки, номер партии и срок годности. С 2010 года по этому коду система İTS Минздрава Турции фиксирует каждое движение упаковки, и одну и ту же упаковку нельзя продать дважды.'] },
          ],
        },
        {
          heading: 'Как проверить код',
          blocks: [
            { type: 'ul', items: [
              ['Установите приложение «İlaç Takip Sistemi (İTS) Mobil» Минздрава Турции и отсканируйте karekod. Приложение покажет, зарегистрирован ли препарат, не отозван ли он и не истёк ли срок годности.'],
              ['Если код не сканируется, номер и серийный номер можно ввести вручную.'],
              ['Штрихкод турецких препаратов обычно начинается с 869 — это префикс GS1 Турции.'],
            ] },
          ],
        },
        {
          heading: 'Что должно быть на упаковке',
          blocks: [
            { type: 'ul', items: [
              ['Название препарата, дозировка, форма и количество, действующее вещество и производитель.'],
              ['Номер партии (Seri / Parti No) и срок годности (SKT) — одинаковые на коробке и на блистере или флаконе.'],
              ['Листок-вкладыш на турецком языке (KULLANMA TALİMATI). Кратко на русском — на страницах препаратов на сайте, у многих форм есть и полная инструкция.'],
              ['Целая упаковка: без следов вскрытия, с чёткой печатью.'],
            ] },
          ],
        },
        {
          heading: 'Признаки подделки',
          blocks: [
            { type: 'ul', items: [
              ['Нет karekod, он не сканируется или приложение не находит препарат.'],
              ['Разные номера партии или сроки годности на коробке и блистере.'],
              ['Размытая печать, ошибки в тексте, непривычный цвет таблеток.'],
              ['Цена намного ниже аптечной. Справочные цены на сайте взяты из списков Минздрава Турции и TİTCK.'],
            ] },
            { type: 'p', parts: ['Если препарат вызывает сомнения, не применяйте его и свяжитесь с менеджером. Как устроен заказ — на странице ', link('/how-to-order-medicines', '«Как заказать»'), '. Популярные препараты собраны в статье ', link('/blog/top-tureckih-lekarstv', '«Какие лекарства заказать из Турции»'), '.'] },
          ],
        },
      ],
      faq: [
        { q: 'Как проверить, что турецкое лекарство не поддельное?', a: 'Отсканируйте код DataMatrix (karekod) на упаковке в приложении «İTS Mobil» Минздрава Турции: оно покажет, зарегистрирован ли препарат, не отозван ли он и не истёк ли срок годности.' },
        { q: 'Где на упаковке срок годности?', a: 'Он обозначен SKT и записан в karekod. Срок и номер партии (Seri / Parti No) на коробке и блистере должны совпадать.' },
        { q: 'Будет ли инструкция на русском?', a: 'На упаковке листок-вкладыш на турецком. Кратко на русском — на страницах препаратов на сайте, у многих форм есть и полная инструкция.' },
      ],
      sources: SOURCES_TITCK.ru,
    },
    en: {
      title: 'How to check that a Turkish medicine is genuine',
      metaTitle: 'How to check a Turkish medicine: İTS code, pack, signs of fakes',
      description: 'How to verify a medicine from Turkey: the DataMatrix code and the İTS Mobil app, the 869 barcode, what the pack must show and signs of a counterfeit.',
      lead: 'In Turkey every medicine pack is tracked by the state İTS system (İlaç Takip Sistemi) from the manufacturer to the pharmacy. So anyone with a smartphone can check whether a medicine is genuine.',
      sections: [
        {
          heading: 'The DataMatrix code (karekod) on the pack',
          blocks: [
            { type: 'p', parts: ['Every box carries a square DataMatrix code, called karekod in Turkish. It holds the product code (GTIN), the pack’s serial number, the batch number and the expiry date. Since 2010 the Turkish Ministry of Health’s İTS system has logged every movement of each pack by this code, so the same pack cannot be sold twice.'] },
          ],
        },
        {
          heading: 'How to check the code',
          blocks: [
            { type: 'ul', items: [
              ['Install the “İlaç Takip Sistemi (İTS) Mobil” app by the Turkish Ministry of Health and scan the karekod. It shows whether the medicine is registered, has not been recalled and has not expired.'],
              ['If the code does not scan, the product and serial numbers can be typed in.'],
              ['Turkish medicine barcodes usually start with 869, the GS1 Turkey prefix.'],
            ] },
          ],
        },
        {
          heading: 'What the pack must show',
          blocks: [
            { type: 'ul', items: [
              ['Name, strength, form and quantity, active ingredient and manufacturer.'],
              ['Batch number (Seri / Parti No) and expiry date (SKT), matching on the box and on the blister or bottle.'],
              ['A patient leaflet in Turkish (KULLANMA TALİMATI). Drug pages on the site summarise it in English, and many forms have the full leaflet.'],
              ['An intact pack with no signs of opening and sharp printing.'],
            ] },
          ],
        },
        {
          heading: 'Signs of a counterfeit',
          blocks: [
            { type: 'ul', items: [
              ['No karekod, it does not scan, or the app cannot find the medicine.'],
              ['Different batch numbers or expiry dates on the box and the blister.'],
              ['Blurred print, spelling mistakes, tablets of an unusual colour.'],
              ['A price far below the pharmacy price. Reference prices on the site come from lists published by the Turkish Ministry of Health and TİTCK.'],
            ] },
            { type: 'p', parts: ['If a medicine looks suspicious, do not use it and contact a manager. See ', link('/how-to-order-medicines', 'How to order'), ' and the article on ', link('/blog/top-tureckih-lekarstv', 'popular Turkish medicines'), '.'] },
          ],
        },
      ],
      faq: [
        { q: 'How do I check that a Turkish medicine is not fake?', a: 'Scan the DataMatrix code (karekod) on the pack with the Turkish Ministry of Health’s “İTS Mobil” app: it shows whether the medicine is registered, has not been recalled and has not expired.' },
        { q: 'Where is the expiry date on the pack?', a: 'It is marked SKT and is also encoded in the karekod. The expiry date and batch number (Seri / Parti No) must match on the box and the blister.' },
        { q: 'Is there a leaflet in English?', a: 'The pack contains a Turkish leaflet. Drug pages on the site summarise it in English, and many forms have the full leaflet.' },
      ],
      sources: SOURCES_TITCK.en,
    },
  },
]

/** Статьи, на которые ссылаются страницы препаратов («Читайте также»). */
export const DRUG_GROUP_ARTICLE_SLUGS = ['kak-proverit-tureckoe-lekarstvo', 'pravila-vvoza-lekarstv-iz-turcii', 'tureckie-analogi-lekarstv']

/** Вопросы о ввозе — и в статье о правилах ввоза, и на странице доставки. */
export const IMPORT_FAQ_BY_LOCALE = IMPORT_FAQ
export const IMPORT_ARTICLE_SLUG = 'pravila-vvoza-lekarstv-iz-turcii'

/** Статья на языке страницы: { slug, publishedAt, updatedAt, ...тексты } или null. */
export function getBlogArticle(slug, locale) {
  const article = BLOG_ARTICLES.find((item) => item.slug === slug)
  if (!article) return null
  const texts = article[locale] || article.ru
  return { slug: article.slug, publishedAt: article.publishedAt, updatedAt: article.updatedAt, ...texts }
}
