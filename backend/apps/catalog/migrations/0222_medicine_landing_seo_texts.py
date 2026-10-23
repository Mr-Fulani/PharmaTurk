"""SEO посадочных страниц «Медикаментов» и 17 подборок (SEO-задание 23.10.2026).

Тексты по ядру запросов: H1, title, description и SEO-текст RU/EN для корня
medicines и 14 подкатегорий, подборки с правилами отбора и своими текстами.
Пишет только пустые поля и только новые подборки — правки из админки не
перетирает. Нет категории (новая или тестовая база) — пропускает её.
"""

from django.db import migrations

SEO_FIELDS = ('h1', 'meta_title', 'meta_description', 'seo_text')

CATEGORY_FALLBACK_NAMES = {'medicines': {'ru': 'Медикаменты', 'en': 'Medicines'}}

CATEGORY_TEXTS = {'medicines': {'ru': {'h1': 'Лекарства из Турции',
                      'meta_title': 'Лекарства из Турции с доставкой в Россию, Казахстан, Узбекистан | '
                                    'Mudaroba',
                      'meta_description': 'Оригинальные препараты из турецких аптек: около 13 тысяч позиций '
                                          'с действующим веществом и инструкцией. Заявка, проверка наличия и '
                                          'расчёт менеджером, доставка 7–21 рабочий день.',
                      'seo_text': 'В этом разделе собраны лекарства из Турции — оригинальные препараты, '
                                  'которые поступают из турецких аптек и от турецких дистрибьюторов. Это те '
                                  'же средства, которые есть в аптеках Турции. В каталоге около 13 тысяч '
                                  'позиций: турецкие таблетки и капсулы, сиропы, капли, мази, спреи, '
                                  'растворы для инъекций.\n'
                                  '\n'
                                  '## Как устроен каталог\n'
                                  '\n'
                                  'Турецкие препараты распределены по разделам в соответствии с кодами АТХ — '
                                  'анатомо-терапевтико-химической классификации ВОЗ, то есть по системам '
                                  'организма. Есть разделы с обезболивающими и противовоспалительными '
                                  'средствами, препаратами от простуды и гриппа, для суставов и мышц, от '
                                  'кашля и для горла, для глаз, для кожи, для сердца и сосудов, для '
                                  'пищеварения и другие. Кроме разделов, есть тематические подборки — '
                                  'например, мази, кремы и гели, собранные из разных групп.\n'
                                  '\n'
                                  'Названия в каталоге турецкие, латиницей — так, как они напечатаны на '
                                  'упаковке. Чтобы турецкие лекарства было проще сопоставить с назначением '
                                  'врача, в каждой карточке указаны действующее вещество, лекарственная '
                                  'форма и дозировка, а также приведена инструкция. Если в Турции препарат '
                                  'выпускается под другим торговым названием, ориентируйтесь на действующее '
                                  'вещество. Рецептурные препараты отмечены отдельно.\n'
                                  '\n'
                                  '## Как оформить заказ\n'
                                  '\n'
                                  'Чтобы заказать лекарства из Турции, добавьте нужные позиции в список '
                                  'заявки и отправьте его. Менеджер проверит наличие, рассчитает стоимость '
                                  'вместе с доставкой и согласует с вами детали — оплаты на сайте нет. '
                                  'Доставка лекарств из Турции в Россию, Казахстан и Узбекистан занимает '
                                  '7–21 рабочий день.\n'
                                  '\n'
                                  'Для рецептурных препаратов может понадобиться рецепт врача: требования '
                                  'зависят от конкретного средства и страны доставки, и в обход этих правил '
                                  'препараты не отправляются. Любое лекарство принимайте только по '
                                  'назначению врача и после того, как внимательно прочитаете инструкцию.'},
               'en': {'h1': 'Medicines from Turkey',
                      'meta_title': 'Medicines from Turkey — delivery to Russia, Kazakhstan, Uzbekistan | '
                                    'Mudaroba',
                      'meta_description': 'Original medicines from Turkish pharmacies: about 13,000 items '
                                          'with active ingredient and leaflet. Send a request — we check '
                                          'availability and quote delivery in 7–21 business days.',
                      'seo_text': 'This section brings together medicines from Turkey — original products '
                                  'sourced from Turkish pharmacies and Turkish distributors, the same '
                                  'products you would find on pharmacy shelves in Turkey. The catalog lists '
                                  'about 13,000 items: tablets and capsules, syrups, drops, ointments, '
                                  'sprays and injectable solutions.\n'
                                  '\n'
                                  '## How the catalog is organised\n'
                                  '\n'
                                  'Turkish medicines are grouped by body system according to the WHO '
                                  'Anatomical Therapeutic Chemical (ATC) classification. There are sections '
                                  'for painkillers and anti-inflammatories, cold and flu remedies, bones, '
                                  'joints and muscles, cough and throat, eyes, skin, heart and blood '
                                  'vessels, digestion and more. Themed collections, such as ointments, '
                                  'creams and gels gathered from different groups, sit alongside the main '
                                  'categories.\n'
                                  '\n'
                                  'Product names are in Turkish, exactly as printed on the pack. To make '
                                  'them easy to match with what your doctor prescribed, every product page '
                                  'shows the active ingredient, dosage form and strength, plus the patient '
                                  'leaflet. If a medicine is marketed in Turkey under a different brand '
                                  'name, go by the active ingredient. Prescription-only medicines are '
                                  'clearly marked.\n'
                                  '\n'
                                  '## How ordering works\n'
                                  '\n'
                                  'Add the items you need to your request list and submit it. A manager '
                                  'checks availability, calculates the total cost including shipping and '
                                  'confirms the details with you; there is no online payment. International '
                                  'delivery to Russia, Kazakhstan and Uzbekistan takes 7–21 business days.\n'
                                  '\n'
                                  "Prescription medicines may require a doctor's prescription: the rules "
                                  'depend on the product and the destination country, and nothing is shipped '
                                  'in breach of local regulations. Always read the leaflet carefully and '
                                  'talk to your doctor before taking any medicine.'}},
 'painkillers': {'ru': {'h1': 'Турецкие обезболивающие и противовоспалительные препараты',
                        'meta_title': 'Турецкие обезболивающие: таблетки, гели, от мигрени | Mudaroba',
                        'meta_description': 'Турецкие обезболивающие таблетки, капсулы и гели: флурбипрофен, '
                                            'декскетопрофен, парацетамол, средства от мигрени. Заявка '
                                            'менеджеру, доставка 7–21 рабочий день.',
                        'seo_text': 'Раздел объединяет анальгетики и противовоспалительные средства из '
                                    'турецких аптек. Если вы ищете турецкое обезболивающее с определённым '
                                    'действующим веществом, здесь его удобно найти: в разделе три группы '
                                    'классификации АТХ.\n'
                                    '\n'
                                    'Нестероидные противовоспалительные средства (НПВП, коды M01A и M01B) — '
                                    'флурбипрофен, декскетопрофен, ибупрофен, диклофенак и другие вещества в '
                                    'таблетках, капсулах и растворах для инъекций. Средства для наружного '
                                    'применения (M02) — гели, кремы и мази, которые применяют при боли в '
                                    'мышцах и суставах. Анальгетики и противомигренозные средства (N02) — '
                                    'препараты на основе парацетамола, комбинированные таблетки от головной '
                                    'боли и средства, которые назначают при мигрени.\n'
                                    '\n'
                                    '## Примеры из каталога\n'
                                    '\n'
                                    'Среди позиций раздела — MAJEZIK (флурбипрофен) в таблетках и капсулах '
                                    'пролонгированного действия, ARVELES (декскетопрофен) в таблетках и '
                                    'ампулах и DEXOFEN (декскетопрофен) в таблетках. Названия даны '
                                    'латиницей, как на турецкой упаковке, а действующее вещество и дозировка '
                                    'указаны в каждой карточке — по ним удобно сопоставить турецкие таблетки '
                                    'от головной боли или от мигрени с привычными препаратами. Обратите '
                                    'внимание: MAJEZIK DUO с миорелаксантом находится в разделе «Кости, '
                                    'суставы и мышцы».\n'
                                    '\n'
                                    'Обезболивающие из Турции оформляются через менеджера: после заявки он '
                                    'сверит наличие и назовёт итоговую сумму с учётом пересылки, а доставка '
                                    'займёт 7–21 рабочий день.\n'
                                    '\n'
                                    'У НПВП и анальгетиков есть противопоказания, а у части препаратов — '
                                    'ограничения по длительности приёма. Прежде чем принимать любое турецкое '
                                    'обезболивающее, прочитайте инструкцию и обсудите выбор с врачом. Для '
                                    'позиций с пометкой о рецепте может понадобиться документ от врача — '
                                    'правила разных стран отличаются.'},
                 'en': {'h1': 'Turkish Painkillers and Anti-Inflammatories',
                        'meta_title': 'Turkish Painkillers: Tablets, Gels, Migraine Medicines | Mudaroba',
                        'meta_description': 'Turkish painkillers in tablets, capsules and gels: '
                                            'flurbiprofen, dexketoprofen, paracetamol and migraine '
                                            'medicines. Request a quote; delivery takes 7–21 business days.',
                        'seo_text': 'This category gathers pain relievers and anti-inflammatory medicines '
                                    'sourced from Turkish pharmacies. If you are looking for a Turkish '
                                    'painkiller with a particular active ingredient, this is the place to '
                                    'start: the category combines three groups of the ATC classification.\n'
                                    '\n'
                                    'Non-steroidal anti-inflammatory drugs (NSAIDs, ATC M01A and M01B) '
                                    'include flurbiprofen, dexketoprofen, ibuprofen, diclofenac and other '
                                    'substances in tablets, capsules and injectable solutions. Topical '
                                    'products (M02) are gels, creams and ointments applied for muscle and '
                                    'joint pain. Analgesics and migraine medicines (N02) cover '
                                    'paracetamol-based products, combination headache tablets and medicines '
                                    'prescribed for migraine.\n'
                                    '\n'
                                    '## Examples in the catalog\n'
                                    '\n'
                                    'You will find MAJEZIK (flurbiprofen) tablets and extended-release '
                                    'capsules, ARVELES (dexketoprofen) tablets and ampoules, and DEXOFEN '
                                    '(dexketoprofen) tablets. Names appear in Turkish, as printed on the '
                                    'pack, while every card shows the active ingredient and strength, so you '
                                    'can match Turkish headache or migraine tablets with the medicines you '
                                    'already know. Note that MAJEZIK DUO, which adds a muscle relaxant, is '
                                    'listed under Bones, Joints & Muscles.\n'
                                    '\n'
                                    'Painkillers from Turkey are ordered through a manager: once you send a '
                                    'request, they check stock and quote a final price with shipping. '
                                    'Parcels take 7–21 business days to arrive.\n'
                                    '\n'
                                    'NSAIDs and analgesics have contraindications, and some should only be '
                                    'taken for a limited time. Read the leaflet and discuss any Turkish '
                                    'painkiller with your doctor before use. For items flagged as '
                                    "prescription-only, a doctor's prescription may be needed; rules differ "
                                    'from country to country.'}},
 'musculoskeletal': {'ru': {'h1': 'Турецкие препараты для костей, суставов и мышц',
                            'meta_title': 'Турецкие препараты для суставов, костей и мышц | Mudaroba',
                            'meta_description': 'Турецкие препараты для суставов, костей и мышц: '
                                                'миорелаксанты с тиоколхикозидом, средства при подагре и '
                                                'остеопорозе. Заявка, проверка наличия, доставка 7–21 '
                                                'рабочий день.',
                            'seo_text': 'Здесь собраны препараты группы M классификации АТХ — для костей, '
                                        'суставов и мышц, кроме противовоспалительных и обезболивающих '
                                        'средств, у которых свой раздел. Если вы ищете средство для суставов '
                                        'из Турции, сначала посмотрите, какие группы входят в этот раздел.\n'
                                        '\n'
                                        'Миорелаксанты (M03) назначают при мышечном спазме, например при '
                                        'боли в спине. Средства группы M04 применяют при подагре. Препараты, '
                                        'влияющие на структуру и минерализацию костей (M05), назначают при '
                                        'остеопорозе. Кроме того, в раздел входят прочие средства группы '
                                        'M09.\n'
                                        '\n'
                                        '## Препараты в каталоге\n'
                                        '\n'
                                        'Миорелаксанты представлены, например, препаратом MUSCOFLEX '
                                        '(тиоколхикозид) в капсулах и растворе для инъекций, а также MAJEZIK '
                                        'DUO (тиоколхикозид + флурбипрофен) в таблетках, где миорелаксант '
                                        'сочетается с противовоспалительным веществом. В карточках указаны '
                                        'действующее вещество, форма выпуска, дозировка и инструкция; '
                                        'названия — турецкие, как на упаковке.\n'
                                        '\n'
                                        'Многие ищут турецкую мазь для суставов. Местные гели, кремы и мази '
                                        'от боли в суставах и мышцах собраны в разделе «Обезболивающие и '
                                        'противовоспалительные», а также в подборке «Мази, кремы и гели».\n'
                                        '\n'
                                        'Порядок заказа обычный для сайта: вы оставляете заявку, менеджер '
                                        'подтверждает, какие позиции доступны, и присылает расчёт с '
                                        'доставкой; в пути посылка находится 7–21 рабочий день. Препараты '
                                        'для суставов и костей подбирает врач с учётом диагноза, поэтому '
                                        'прежде чем начать приём, изучите инструкцию и получите консультацию '
                                        'специалиста. Для рецептурных позиций может потребоваться рецепт — в '
                                        'зависимости от страны получателя.'},
                     'en': {'h1': 'Turkish Medicines for Bones, Joints & Muscles',
                            'meta_title': 'Turkish Joint, Bone & Muscle Medicines | Mudaroba',
                            'meta_description': 'Turkish medicines for joints, bones and muscles: '
                                                'thiocolchicoside muscle relaxants, gout and osteoporosis '
                                                'medicines. Send a request; delivery takes 7–21 business '
                                                'days.',
                            'seo_text': 'This category covers ATC group M medicines for joints, bones and '
                                        'muscles, except anti-inflammatories and pain relievers, which have '
                                        'a section of their own. If you are looking for joint medicines from '
                                        'Turkey, here is what this page includes.\n'
                                        '\n'
                                        'Muscle relaxants (M03) are prescribed for muscle spasm, for example '
                                        'with back pain. Group M04 products are used for gout. Medicines '
                                        'affecting bone structure and mineralisation (M05) are prescribed '
                                        'for osteoporosis. The category also includes other group M09 '
                                        'products.\n'
                                        '\n'
                                        '## In the catalog\n'
                                        '\n'
                                        'Muscle relaxants are represented by MUSCOFLEX (thiocolchicoside) '
                                        'capsules and injectable solution and by MAJEZIK DUO '
                                        '(thiocolchicoside + flurbiprofen) tablets, which combine a muscle '
                                        'relaxant with an anti-inflammatory. Product pages show the active '
                                        'ingredient, dosage form, strength and leaflet, with names spelled '
                                        'as on the Turkish packaging.\n'
                                        '\n'
                                        'Many people search for a Turkish joint ointment. Topical gels, '
                                        'creams and ointments for joint and muscle pain are listed under '
                                        'Pain & Inflammation and in the Ointments, Creams & Gels '
                                        'collection.\n'
                                        '\n'
                                        'Ordering follows the usual routine: you leave a request, a manager '
                                        'confirms which items are available and sends a quote including '
                                        'delivery, and the parcel arrives within 7–21 business days. Joint '
                                        'and bone medicines should be chosen by a doctor based on your '
                                        'diagnosis, so read the leaflet and get medical advice before '
                                        'starting. Some items carry a prescription flag, and the destination '
                                        'country decides whether a prescription is required.'}},
 'respiratory-ent': {'ru': {'h1': 'Турецкие средства от кашля и боли в горле',
                            'meta_title': 'Турецкие средства от кашля, для горла и носа | Mudaroba',
                            'meta_description': 'Турецкие сиропы и таблетки от кашля, спреи для горла, капли '
                                                'в нос и ушные капли: ацетилцистеин, амброксол, '
                                                'флурбипрофен. Заявка менеджеру, доставка 7–21 рабочий день.',
                            'seo_text': 'В разделе — препараты для дыхательной системы и ЛОР-органов: '
                                        'муколитики и отхаркивающие, средства для горла и носа, '
                                        'ингаляционные препараты и ушные капли. Средства от кашля в Турции '
                                        'выпускают в виде сиропов, порошков в саше, гранул и таблеток; здесь '
                                        'они собраны вместе с другими группами классификации АТХ (R и S02).\n'
                                        '\n'
                                        '## Какие группы входят в раздел\n'
                                        '\n'
                                        'Группа R05 — отхаркивающие и муколитические препараты, а также '
                                        'комбинированные средства от простуды. Препараты для горла (R02) — '
                                        'спреи, растворы для полоскания и таблетки для рассасывания. '
                                        'Назальные средства (R01) — капли и спреи для носа. Отдельно — '
                                        'ингаляционные препараты (R03) и ушные капли (S02). Антигистаминные '
                                        'средства для приёма внутрь вынесены в раздел «Аллергия».\n'
                                        '\n'
                                        '## Примеры препаратов\n'
                                        '\n'
                                        'Турецкий сироп от кашля — это, например, SEKROL (амброксол) и '
                                        'MUKORAL (амброксол), оба есть и в детской дозировке, а также ASIST '
                                        '(ацетилцистеин) в саше и гранулах для приготовления сиропа. Среди '
                                        'турецких лекарств для горла — спрей MAJEZIK (флурбипрофен) и '
                                        'раствор для полоскания с тем же действующим веществом. Для удобства '
                                        'выделены подборки «От простуды и гриппа», «От насморка: капли и '
                                        'спреи» и «Ушные капли».\n'
                                        '\n'
                                        'Заказать средства от кашля из Турции можно, оставив заявку: '
                                        'менеджер выяснит наличие и пришлёт расчёт стоимости вместе с '
                                        'пересылкой. Международное отправление идёт 7–21 рабочий день.\n'
                                        '\n'
                                        'Кашель и боль в горле бывают разной природы, поэтому подбирать '
                                        'препарат должен врач. Перед применением прочитайте инструкцию: в '
                                        'ней указаны показания, противопоказания и возрастные ограничения. '
                                        'Нужен ли рецепт для отмеченных в карточке препаратов, зависит от '
                                        'страны, куда идёт посылка.'},
                     'en': {'h1': 'Turkish Cough and Sore Throat Medicines',
                            'meta_title': 'Turkish Cough, Throat & Nasal Medicines | Mudaroba',
                            'meta_description': 'Turkish cough syrups and tablets, throat sprays, nasal and '
                                                'ear drops: acetylcysteine, ambroxol, flurbiprofen. Send a '
                                                'request; delivery from Turkey takes 7–21 business days.',
                            'seo_text': 'This category covers medicines for the respiratory system and ENT: '
                                        'cough remedies, throat and nasal products, inhaled medicines and '
                                        'ear drops. Turkish cough medicines come as syrups, sachets of '
                                        'powder, granules and tablets, and here they sit alongside the other '
                                        'groups of ATC sections R and S02.\n'
                                        '\n'
                                        '## What is included\n'
                                        '\n'
                                        'Cough and cold preparations (R05) include expectorants and '
                                        'mucolytics as well as combination cold remedies. Throat products '
                                        '(R02) cover sprays, gargles and lozenges. Nasal preparations (R01) '
                                        'are drops and sprays for the nose. There are also inhaled medicines '
                                        '(R03) and ear drops (S02). Oral antihistamines are listed '
                                        'separately under Allergy.\n'
                                        '\n'
                                        '## Examples\n'
                                        '\n'
                                        'Among the Turkish cough syrups are SEKROL (ambroxol) and MUKORAL '
                                        '(ambroxol), both also available in paediatric strengths, and ASIST '
                                        '(acetylcysteine) in sachets and granules for oral syrup. For the '
                                        'throat there is MAJEZIK (flurbiprofen) oral spray and a gargle with '
                                        'the same active ingredient. The Cold & Flu, Nasal Drops & Sprays '
                                        'and Ear Drops collections make those groups easier to browse.\n'
                                        '\n'
                                        'To order cough medicines from Turkey, leave a request; a manager '
                                        'finds out whether the items are in stock and sends you a quote with '
                                        'shipping. The international shipment is in transit for 7–21 '
                                        'business days.\n'
                                        '\n'
                                        'A cough or sore throat can have many causes, so the choice of '
                                        'medicine should be made by a doctor. Read the leaflet first: it '
                                        'lists indications, contraindications and age limits. Whether a '
                                        'prescription is needed for a flagged product depends on the country '
                                        'the parcel is going to.'}},
 'ophthalmology': {'ru': {'h1': 'Капли для глаз из Турции и глазные мази',
                          'meta_title': 'Турецкие капли для глаз и глазные мази | Mudaroba',
                          'meta_description': 'Увлажняющие, противомикробные и противоглаукомные капли для '
                                              'глаз из Турции: SYSTANE, TOBRASED, XALATAN. Заявка, проверка '
                                              'наличия и доставка за 7–21 рабочий день.',
                          'seo_text': 'Раздел «Глаза» объединяет препараты группы S01 по классификации АТХ: '
                                      'глазные капли, гели и мази, которые применяют в офтальмологии. Капли '
                                      'для глаз из Турции собраны здесь по действующим веществам, а названия '
                                      'указаны латиницей, как на турецкой упаковке, — так проще сверить '
                                      'препарат с назначением врача.\n'
                                      '\n'
                                      '## Какие препараты есть в разделе\n'
                                      '\n'
                                      'Турецкие увлажняющие капли для глаз, или «искусственная слеза», — '
                                      'группа, которую чаще всего ищут: их применяют при сухости глаз, '
                                      'например SYSTANE (полиэтиленгликоль + пропиленгликоль). Тем, кто ищет '
                                      'турецкие капли от конъюнктивита, важно знать: причину воспаления '
                                      'определяет офтальмолог, и при бактериальной форме он может назначить '
                                      'противомикробные средства — например, TOBRASED (тобрамицин) в виде '
                                      'капель и мази или VIGAMOX (моксифлоксацин). Есть и '
                                      'противовоспалительные турецкие глазные капли, и препараты, снижающие '
                                      'внутриглазное давление при глаукоме, — например, XALATAN '
                                      '(латанопрост).\n'
                                      '\n'
                                      'Турецкие капли для глаз заказывают через заявку: менеджер проверяет, '
                                      'есть ли нужная концентрация и объём флакона, рассчитывает стоимость '
                                      'вместе с доставкой и согласует детали. Посылка в Россию, Казахстан '
                                      'или Узбекистан идёт 7–21 рабочий день.\n'
                                      '\n'
                                      'Часть препаратов рецептурная — это отмечено в карточке товара; '
                                      'требования к рецепту зависят от препарата и страны доставки, и в '
                                      'обход местных правил ничего не отправляется. Прежде чем использовать '
                                      'капли для глаз из Турции, прочитайте инструкцию и обсудите назначение '
                                      'с офтальмологом, особенно если вы носите контактные линзы.'},
                   'en': {'h1': 'Turkish Eye Drops and Eye Ointments',
                          'meta_title': 'Turkish Eye Drops & Eye Ointments | Mudaroba',
                          'meta_description': 'Lubricating, antibacterial and glaucoma eye drops from '
                                              'Turkey, including SYSTANE, TOBRASED and XALATAN. Send a '
                                              'request: we check availability and deliver in 7–21 working '
                                              'days.',
                          'seo_text': 'The Ophthalmology section brings together ATC group S01: eye drops, '
                                      'gels and ointments used in eye care. Product names appear in Latin '
                                      'letters exactly as on the Turkish pack, which makes it easy to match '
                                      'a medicine against what your doctor has recommended.\n'
                                      '\n'
                                      '## What you will find here\n'
                                      '\n'
                                      'The most searched group is lubricating eye drops, often called '
                                      'artificial tears, used for dry eyes — for example SYSTANE '
                                      '(polyethylene glycol + propylene glycol). Antibacterial eye drops and '
                                      'ointments are prescribed for bacterial conjunctivitis and other eye '
                                      'infections: TOBRASED (tobramycin) comes as drops and as an ointment, '
                                      'VIGAMOX (moxifloxacin) as drops. The section also covers '
                                      'anti-inflammatory drops and glaucoma medicines that lower intraocular '
                                      'pressure, such as XALATAN (latanoprost).\n'
                                      '\n'
                                      'Ordering Turkish eye drops works through a request: a manager '
                                      'confirms that the strength and bottle size you need are available, '
                                      'calculates the total including shipping and agrees the details with '
                                      'you. International delivery to Russia, Kazakhstan or Uzbekistan takes '
                                      '7–21 working days.\n'
                                      '\n'
                                      'Some items are prescription-only and are marked as such on the '
                                      'product page. Whether a prescription is needed depends on the '
                                      'medicine and the destination country, and nothing is shipped in '
                                      'breach of local rules. Read the leaflet and talk to an eye doctor '
                                      'before using any eye drops from Turkey, especially if you wear '
                                      'contact lenses.'}},
 'antibiotics': {'ru': {'h1': 'Антибиотики из Турции — только по назначению врача',
                        'meta_title': 'Антибиотики из Турции по назначению врача | Mudaroba',
                        'meta_description': 'Антибактериальные препараты из Турции группы J01: AUGMENTIN, '
                                            'KLACID, ZITROMAX. Все рецептурные — заказ через заявку по '
                                            'назначению врача, доставка 7–21 рабочий день.',
                        'seo_text': 'Антибиотики в Турции, как и в России, Казахстане или Узбекистане, '
                                    'относятся к рецептурным препаратам. В этом разделе собраны '
                                    'антибактериальные средства системного действия — группа J01 по '
                                    'классификации АТХ: таблетки, капсулы, порошки для приготовления '
                                    'суспензии и формы для инъекций. Каждый турецкий антибиотик в каталоге '
                                    'подписан латиницей, как на упаковке, а в карточке указаны действующее '
                                    'вещество, форма и дозировка.\n'
                                    '\n'
                                    '## Какие препараты представлены\n'
                                    '\n'
                                    'В разделе есть препараты разных классов, в том числе пенициллины и '
                                    'макролиды; среди них встречаются и турецкие антибиотики широкого '
                                    'спектра, и средства с более узкой направленностью — нужный определяет '
                                    'врач по диагнозу. Примеры из каталога: AUGMENTIN (амоксициллин + '
                                    'клавулановая кислота), KLACID (кларитромицин), ZITROMAX (азитромицин). '
                                    'У некоторых препаратов есть детские формы — порошки для приготовления '
                                    'суспензии; детский антибиотик подбирает только педиатр с учётом '
                                    'возраста и веса ребёнка.\n'
                                    '\n'
                                    '## Можно ли заказать антибиотик из Турции\n'
                                    '\n'
                                    'Заявку имеет смысл оставлять, когда препарат уже назначен врачом. '
                                    'Самостоятельный приём антибиотиков мы не поощряем: неподходящий '
                                    'препарат или неверная схема способствуют устойчивости бактерий. Получив '
                                    'заявку, менеджер сверит наличие нужной формы и дозировки, назовёт '
                                    'итоговую сумму с доставкой и обсудит с вами детали заказа. На '
                                    'международную отправку закладывайте 7–21 рабочий день.\n'
                                    '\n'
                                    'Все препараты раздела рецептурные, это указано в карточках. Требования '
                                    'к рецепту зависят от конкретного средства и страны доставки, в обход '
                                    'правил страны препараты не отправляются. Перед приёмом обязательно '
                                    'прочитайте инструкцию и следуйте назначению врача — турецкие названия '
                                    'на упаковке помогут сверить препарат с рецептом.'},
                 'en': {'h1': 'Turkish Antibiotics — Prescribed by a Doctor',
                        'meta_title': 'Turkish Antibiotics on Prescription | Mudaroba',
                        'meta_description': 'Systemic antibacterials from Turkey (ATC J01) such as '
                                            'AUGMENTIN, KLACID and ZITROMAX. All are prescription-only: send '
                                            'a request for the one your doctor prescribed; delivery in 7–21 '
                                            'working days.',
                        'seo_text': 'Antibiotics in Turkey are prescription medicines, just as they are in '
                                    'Russia, Kazakhstan and Uzbekistan. This section lists systemic '
                                    'antibacterial drugs, ATC group J01: tablets, capsules, powders for oral '
                                    'suspension and injectable forms. Each product carries its Turkish name '
                                    'in Latin letters, together with the active ingredient, form and '
                                    'strength.\n'
                                    '\n'
                                    '## What the section contains\n'
                                    '\n'
                                    'The catalogue covers several classes, including penicillins and '
                                    'macrolides, with both broad-spectrum and more targeted Turkish '
                                    'antibiotics — which one is needed is decided by a doctor based on the '
                                    'diagnosis. Examples: AUGMENTIN (amoxicillin + clavulanic acid), KLACID '
                                    '(clarithromycin) and ZITROMAX (azithromycin). Some come in paediatric '
                                    'forms such as powders for suspension; an antibiotic for a child is '
                                    'chosen only by a paediatrician, based on age and weight.\n'
                                    '\n'
                                    '## Can you order an antibiotic from Turkey?\n'
                                    '\n'
                                    'A request makes sense once a doctor has prescribed the medicine. We do '
                                    'not encourage self-medication: the wrong drug or the wrong course '
                                    'contributes to bacterial resistance. Once your request arrives, a '
                                    'manager confirms that the form and strength are in stock, gives you the '
                                    'total with delivery and talks through the details. Allow 7–21 working '
                                    'days for international shipping.\n'
                                    '\n'
                                    'Every medicine here is prescription-only, as shown on each product '
                                    'page. What is required depends on the drug and the destination country, '
                                    'and medicines are never sent in a way that bypasses local rules. Read '
                                    "the leaflet and follow your doctor's instructions."}},
 'gastro': {'ru': {'h1': 'Турецкие препараты для желудка, печени и кишечника',
                   'meta_title': 'Турецкие препараты для желудка и печени | Mudaroba',
                   'meta_description': 'Средства от изжоги, спазмолитики, препараты для печени, '
                                       'слабительные, противодиарейные средства и ферменты из Турции. '
                                       'Заявка, проверка наличия, доставка 7–21 рабочий день.',
                   'seo_text': 'Раздел «Пищеварение и обмен веществ» собран по группе A классификации АТХ: '
                               'здесь турецкие препараты для желудка и печени, кишечника и поджелудочной '
                               'железы. Средства при диабете вынесены в отдельный раздел «Гормоны и диабет». '
                               'В карточках указаны действующее вещество, форма и дозировка, а названия '
                               'написаны латиницей, как на упаковке в Турции.\n'
                               '\n'
                               '## Группы препаратов\n'
                               '\n'
                               'Средства от изжоги и при повышенной кислотности (A02) — турецкие таблетки от '
                               'изжоги, жевательные таблетки и суспензии, например GAVISCON (альгинат натрия '
                               'с гидрокарбонатом). Спазмолитики и средства при вздутии (A03) — например, '
                               'BUSCOPAN (гиосцина бутилбромид). Противорвотные препараты (A04) применяют '
                               'при тошноте, в том числе при укачивании. Турецкие лекарства для печени и '
                               'желчевыводящих путей (A05) представлены, в частности, препаратом URSACTIVE '
                               '(урсодезоксихолевая кислота). Слабительные (A06) — например, DUPHALAC '
                               '(лактулоза). Противодиарейные и адсорбирующие средства (A07) применяют при '
                               'диарее и отравлениях, а ферментные препараты (A09) — это, например, KREON '
                               '(панкреатин). Средства группы A08 собраны также в подборке «Для похудения».\n'
                               '\n'
                               'Нужный препарат заказывают через заявку: менеджер уточнит, есть ли '
                               'подходящая форма — таблетки, суспензия или капсулы, — посчитает стоимость с '
                               'доставкой и подтвердит детали. Международная доставка в Россию, Казахстан и '
                               'Узбекистан занимает 7–21 рабочий день.\n'
                               '\n'
                               'Рецептурные препараты отмечены в карточке; нужен ли рецепт, зависит от '
                               'средства и страны доставки. Сильная боль в животе, кровь в стуле, затяжная '
                               'рвота или диарея — повод сразу обратиться к врачу, а не подбирать турецкие '
                               'препараты для желудка самостоятельно. Перед приёмом любого средства '
                               'прочитайте инструкцию и проконсультируйтесь со специалистом, особенно при '
                               'беременности, хронических заболеваниях или если препарат нужен ребёнку.'},
            'en': {'h1': 'Turkish Medicines for Stomach, Liver and Digestion',
                   'meta_title': 'Turkish Stomach & Liver Medicines | Mudaroba',
                   'meta_description': 'Heartburn and acid medicines, antispasmodics, liver products, '
                                       'laxatives, antidiarrhoeals and digestive enzymes from Turkey. Send a '
                                       'request; delivery in 7–21 working days.',
                   'seo_text': 'Digestion & Metabolism is built on ATC group A and covers Turkish medicines '
                               'for the stomach, liver, bowel and pancreas. Diabetes medicines sit '
                               'separately under Hormones & Diabetes. Each product page lists the active '
                               'ingredient, form and strength, with the name spelled as on the Turkish '
                               'pack.\n'
                               '\n'
                               '## Groups in this section\n'
                               '\n'
                               'Heartburn and acid-related products (A02) include Turkish heartburn tablets, '
                               'chewable tablets and suspensions such as GAVISCON (sodium alginate with '
                               'bicarbonate). Antispasmodics and products for bloating (A03) include '
                               'BUSCOPAN (hyoscine butylbromide). Antiemetics (A04) are used for nausea, '
                               'including motion sickness. Liver and bile medicines (A05) include URSACTIVE '
                               '(ursodeoxycholic acid), and laxatives (A06) include DUPHALAC (lactulose). '
                               'Antidiarrhoeals and adsorbents (A07) are used for diarrhoea and food '
                               'poisoning, while digestive enzymes (A09) include KREON (pancreatin).\n'
                               '\n'
                               'To order, send a request: a manager checks whether the form you need — '
                               'tablets, suspension or capsules — is available, calculates the price with '
                               'shipping and confirms the details. Parcels to Russia, Kazakhstan and '
                               'Uzbekistan take 7–21 working days.\n'
                               '\n'
                               'Prescription-only medicines are flagged on the product page, and whether a '
                               'prescription is needed depends on the medicine and the destination country. '
                               'Severe abdominal pain, blood in the stool or prolonged vomiting or diarrhoea '
                               'call for a doctor straight away. Always read the leaflet and check with a '
                               'doctor or pharmacist before taking any digestive medicine from Turkey, '
                               'especially during pregnancy or for a child.'}},
 'allergy': {'ru': {'h1': 'Турецкие таблетки от аллергии и антигистаминные сиропы',
                    'meta_title': 'Турецкие таблетки от аллергии | Mudaroba',
                    'meta_description': 'Антигистаминные препараты из Турции: AERIUS (дезлоратадин), ZYRTEC '
                                        '(цетиризин), XYZAL (левоцетиризин) — таблетки, сиропы, капли. '
                                        'Заявка и доставка 7–21 рабочий день.',
                    'seo_text': 'Раздел «Аллергия» включает две группы АТХ: R06 — антигистаминные средства '
                                'системного действия и V01 — аллергены. Здесь собраны турецкие таблетки от '
                                'аллергии, а также сиропы, растворы и капли для приёма внутрь; названия '
                                'указаны латиницей, как на упаковке в Турции.\n'
                                '\n'
                                '## Антигистаминные препараты\n'
                                '\n'
                                'Среди турецких антигистаминных препаратов в каталоге — средства второго '
                                'поколения: AERIUS (дезлоратадин) в таблетках и сиропе, ZYRTEC (цетиризин) в '
                                'таблетках, сиропе и каплях, XYZAL (левоцетиризин) в таблетках, растворе и '
                                'каплях. Их применяют при аллергическом рините, крапивнице и других '
                                'аллергических реакциях по показаниям из инструкции. Если вам нужны турецкие '
                                'капли от аллергии, учтите: здесь речь о каплях для приёма внутрь, глазные '
                                'капли находятся в разделе «Глаза», назальные спреи — в подборке «От '
                                'насморка», а наружные средства для кожи — в разделе «Кожа».\n'
                                '\n'
                                'Препараты аллергенов (группа V01) применяют для диагностики и '
                                'аллерген-специфической иммунотерапии только под контролем аллерголога. '
                                'Чтобы заказать турецкий препарат от аллергии, достаточно заявки: менеджер '
                                'свяжется с вами, подтвердит наличие и рассчитает, во сколько обойдутся '
                                'препарат и доставка. Доставка занимает 7–21 рабочий день, поэтому лекарство '
                                'от аллергии из Турции разумно заказать до сезона цветения.\n'
                                '\n'
                                'Рецептурные препараты отмечены в карточке; потребуется ли рецепт, зависит '
                                'от средства и страны доставки. Антигистаминные могут вызывать сонливость и '
                                'взаимодействовать с другими лекарствами, поэтому даже привычные турецкие '
                                'таблетки от аллергии принимайте только после чтения инструкции и '
                                'консультации с врачом — особенно если препарат нужен ребёнку.'},
             'en': {'h1': 'Turkish Allergy Tablets and Antihistamine Syrups',
                    'meta_title': 'Turkish Allergy Tablets & Antihistamines | Mudaroba',
                    'meta_description': 'Antihistamines from Turkey: AERIUS (desloratadine), ZYRTEC '
                                        '(cetirizine) and XYZAL (levocetirizine) as tablets, syrups and oral '
                                        'drops. Send a request; delivery in 7–21 working days.',
                    'seo_text': 'The Allergy section covers two ATC groups: R06, systemic antihistamines, '
                                'and V01, allergens. It brings together Turkish allergy tablets as well as '
                                'syrups, oral solutions and drops, listed under the names printed on the '
                                'Turkish pack.\n'
                                '\n'
                                '## Antihistamines\n'
                                '\n'
                                'Turkish antihistamines in the catalogue include second-generation products '
                                'such as AERIUS (desloratadine) in tablets and syrup, ZYRTEC (cetirizine) in '
                                'tablets, syrup and drops, and XYZAL (levocetirizine) in tablets, oral '
                                'solution and drops. They are used for allergic rhinitis, hives and other '
                                'allergic reactions according to the leaflet. Looking for allergy eye drops? '
                                'Those are in the Ophthalmology section, nasal sprays have a separate '
                                'runny-nose collection, and products applied to the skin belong to '
                                'Dermatology.\n'
                                '\n'
                                'Allergen products (V01) are used for diagnosis and allergen immunotherapy '
                                "under an allergist's supervision only. To order an allergy medicine from "
                                'Turkey, a request is all it takes: a manager gets back to you to confirm '
                                'availability and work out what the medicine and delivery will cost. '
                                'Delivery takes 7–21 working days, so it is worth planning ahead of the '
                                'pollen season.\n'
                                '\n'
                                'Prescription-only items are marked on the product page; whether you need a '
                                'prescription depends on the medicine and the destination country. '
                                'Antihistamines can cause drowsiness and interact with other drugs, so read '
                                'the leaflet and ask your doctor before use, especially for a child.'}},
 'cardio': {'ru': {'h1': 'Турецкие таблетки от давления и препараты для сердца',
                   'meta_title': 'Турецкие таблетки от давления и холестерина | Mudaroba',
                   'meta_description': 'Сердечно-сосудистые препараты из Турции: от давления и холестерина, '
                                       'для сердца и вен — CONCOR, NORVASC, CRESTOR. Заказ через заявку по '
                                       'назначению врача, доставка 7–21 рабочий день.',
                   'seo_text': 'Раздел «Сердечно-сосудистые препараты» собран по группе C классификации АТХ. '
                               'Здесь турецкие таблетки от давления, средства для снижения холестерина, '
                               'препараты для сердца и вен. Почти все они рецептурные: препарат и дозировку '
                               'назначает и подбирает врач по результатам обследования.\n'
                               '\n'
                               '## Группы препаратов\n'
                               '\n'
                               'Турецкие препараты от давления относятся к нескольким группам: мочегонные '
                               '(C03), бета-адреноблокаторы (C07), блокаторы кальциевых каналов (C08), '
                               'средства, влияющие на ренин-ангиотензиновую систему (C09), и другие '
                               'антигипертензивные препараты (C02). Примеры — CONCOR (бисопролол) и NORVASC '
                               '(амлодипин). Турецкие таблетки от холестерина входят в группу '
                               'гиполипидемических средств (C10), среди них статины — например, CRESTOR '
                               '(розувастатин). Также в разделе есть препараты для сердца (C01) и для вен '
                               '(C05); средства при варикозе вынесены в отдельную подборку «Для вен: '
                               'варикоз».\n'
                               '\n'
                               'Таблетки от давления из Турции заказывают через заявку: менеджер проверит, '
                               'есть ли нужная дозировка и количество таблеток в упаковке, посчитает '
                               'стоимость с доставкой и согласует детали. Отправка в Россию, Казахстан или '
                               'Узбекистан занимает 7–21 рабочий день — если вы принимаете препарат '
                               'постоянно, учитывайте этот срок, чтобы не остаться без лекарства.\n'
                               '\n'
                               'Рецептурный статус указан в карточке, а необходимость рецепта определяется '
                               'самим препаратом и законодательством страны доставки; в обход этих правил '
                               'препараты не отправляются. Не меняйте и не отменяйте назначенные турецкие '
                               'таблетки от давления самостоятельно: перед применением прочитайте инструкцию '
                               'и согласуйте любые изменения с кардиологом или терапевтом.'},
            'en': {'h1': 'Turkish Blood Pressure Tablets and Heart Medicines',
                   'meta_title': 'Turkish Blood Pressure & Cholesterol Tablets | Mudaroba',
                   'meta_description': 'Cardiovascular medicines from Turkey for blood pressure, '
                                       'cholesterol, the heart and veins, including CONCOR, NORVASC and '
                                       'CRESTOR. Ordered on prescription; delivery in 7–21 working days.',
                   'seo_text': 'The Cardiovascular section is built on ATC group C. It covers Turkish blood '
                               'pressure tablets, cholesterol-lowering medicines and drugs for the heart and '
                               'veins. Almost all of them are prescription-only, and the choice of drug and '
                               'dose is made by a doctor after an examination.\n'
                               '\n'
                               '## Groups in this section\n'
                               '\n'
                               'Blood pressure medicines come from several groups: diuretics (C03), beta '
                               'blockers (C07), calcium channel blockers (C08), agents acting on the '
                               'renin–angiotensin system (C09) and other antihypertensives (C02). Examples '
                               'include CONCOR (bisoprolol) and NORVASC (amlodipine). Turkish cholesterol '
                               'tablets belong to the lipid-modifying agents (C10), among them statins such '
                               'as CRESTOR (rosuvastatin). The section also includes cardiac medicines (C01) '
                               'and vein products (C05); medicines for varicose veins have their own '
                               'collection.\n'
                               '\n'
                               'Blood pressure tablets from Turkey are ordered through a request: a manager '
                               'checks the strength and pack size, calculates the cost with shipping and '
                               'confirms the details. Delivery to Russia, Kazakhstan or Uzbekistan takes '
                               '7–21 working days, so if you take a medicine every day, allow for that '
                               'time.\n'
                               '\n'
                               'Prescription status is shown on each product page; whether a prescription is '
                               'needed is set by the drug itself and the law of the destination country, and '
                               'shipments always follow those rules. Never change or stop a prescribed '
                               'medicine on your own: read the leaflet and agree any changes with your '
                               'cardiologist or GP.'}},
 'dermatology': {'ru': {'h1': 'Турецкая мазь от герпеса и другие препараты для кожи',
                        'meta_title': 'Турецкие средства для кожи: мазь от герпеса | Mudaroba',
                        'meta_description': 'Дерматологические препараты из Турции: кремы с ацикловиром, '
                                            'гели при акне, средства от пигментных пятен, для ран и рубцов. '
                                            'Заявка менеджеру, доставка 7–21 рабочий день.',
                        'seo_text': 'Раздел «Кожа» объединяет дерматологические препараты из турецких аптек '
                                    '— группу D по классификации АТХ: кремы, мази, гели, растворы, шампуни и '
                                    'таблетки. Один из самых частых запросов — турецкая мазь от герпеса: '
                                    'кремы с ацикловиром для губ и кожи находятся именно здесь.\n'
                                    '\n'
                                    '## Что входит в раздел\n'
                                    '\n'
                                    'Противогрибковые средства для кожи и ногтей (D01), препараты для ран, '
                                    'ожогов и рубцов (D03), средства от зуда (D04), антипсориатические '
                                    '(D05), антибиотики и противовирусные для наружного применения (D06), '
                                    'кортикостероиды, которые назначают при дерматите и экземе (D07), '
                                    'антисептики (D08), препараты при акне (D10) и прочие дерматологические '
                                    'средства, в том числе от пигментации (D11).\n'
                                    '\n'
                                    'Примеры из каталога: ASIVIRAL (ацикловир) — крем, который по инструкции '
                                    'применяют при герпесе на губах и коже; DIFFERIN (адапален) — гель, '
                                    'который назначают при акне и прыщах; EXPIGMENT (гидрохинон) — крем, '
                                    'применяемый при пигментных пятнах; MADECASSOL (экстракт центеллы '
                                    'азиатской) — мазь для ран и рубцов. Если нужна не турецкая мазь от '
                                    'герпеса, а таблетки, загляните в раздел противоинфекционных средств: '
                                    'системные противовирусные, например валацикловир, собраны там.\n'
                                    '\n'
                                    'Чтобы заказать препарат, оставьте заявку — менеджер уточнит наличие, '
                                    'посчитает стоимость с доставкой и согласует детали. Посылка в Россию, '
                                    'Казахстан или Узбекистан идёт 7–21 рабочий день.\n'
                                    '\n'
                                    'Если препарат рецептурный, это видно в карточке; нужен ли рецепт для '
                                    'отправки, зависит от конкретного средства и страны получателя. Наружные '
                                    'кортикостероиды и кремы с гидрохиноном применяют только по назначению '
                                    'врача. Прежде чем использовать любое средство для кожи, прочитайте '
                                    'инструкцию и посоветуйтесь с дерматологом.'},
                 'en': {'h1': 'Turkish Skin Medicines: Herpes Cream, Acne Gel and More',
                        'meta_title': 'Turkish Skin Medicines & Herpes Cream | Mudaroba',
                        'meta_description': 'Skin medicines from Turkey: aciclovir creams for cold sores, '
                                            'acne gels, creams for dark spots, ointments for wounds and '
                                            'scars. Send a request; delivery takes 7–21 working days.',
                        'seo_text': 'The Dermatology section brings together skin medicines from Turkish '
                                    'pharmacies, ATC group D: creams, ointments, gels, solutions, shampoos '
                                    'and tablets. One of the most frequent requests is a Turkish herpes '
                                    'cream, and aciclovir creams for cold sores and skin lesions are listed '
                                    'right here.\n'
                                    '\n'
                                    '## What the section covers\n'
                                    '\n'
                                    'Antifungals for skin and nails (D01), products for wounds, burns and '
                                    'scars (D03), anti-itch preparations (D04), antipsoriatics (D05), '
                                    'topical antibiotics and antivirals (D06), corticosteroids prescribed '
                                    'for dermatitis and eczema (D07), antiseptics (D08), acne preparations '
                                    '(D10) and other dermatologicals, including products for '
                                    'hyperpigmentation (D11).\n'
                                    '\n'
                                    'Examples from the catalog: ASIVIRAL (aciclovir), a cream indicated for '
                                    'herpes on the lips and skin; DIFFERIN (adapalene), a gel prescribed for '
                                    'acne and pimples; EXPIGMENT (hydroquinone), a cream used for dark '
                                    'spots; MADECASSOL (Centella asiatica extract), an ointment for wounds '
                                    'and scars. If you need antiviral tablets rather than a Turkish herpes '
                                    'cream, look in the anti-infectives section, where systemic antivirals '
                                    'such as valaciclovir are listed.\n'
                                    '\n'
                                    'To order, send a request for the product you need. A manager checks '
                                    'stock in Turkey, calculates the cost with shipping and confirms the '
                                    'details. Delivery to Russia, Kazakhstan or Uzbekistan takes 7–21 '
                                    'working days.\n'
                                    '\n'
                                    'If a product is prescription-only, the product page says so; whether a '
                                    'prescription is needed for shipping depends on the medicine and the '
                                    "recipient's country. Topical corticosteroids and hydroquinone creams "
                                    'should be used only as directed by a doctor. Read the leaflet and '
                                    'consult a dermatologist before applying any skin medicine.'}},
 'urology-gynecology': {'ru': {'h1': 'Урология и гинекология: препараты от цистита из Турции',
                               'meta_title': 'Урология и гинекология из Турции: от цистита | Mudaroba',
                               'meta_description': 'Урологические и гинекологические препараты из Турции: '
                                                   'спазмолитики мочевых путей, средства при заболеваниях '
                                                   'простаты, вагинальные формы, контрацепция. Расчёт по '
                                                   'заявке, доставка 7–21 рабочий день.',
                               'seo_text': 'Раздел объединяет урологические и гинекологические препараты из '
                                           'турецких аптек — группу G по классификации АТХ. Сюда приходят, '
                                           'когда выясняют, что можно заказать от цистита в Турции, какие '
                                           'турецкие препараты для мужчин назначают при заболеваниях '
                                           'простаты и какие гормональные и вагинальные средства выпускаются '
                                           'для женщин.\n'
                                           '\n'
                                           '## Что входит в раздел\n'
                                           '\n'
                                           'Гинекологические противомикробные и антисептики — вагинальные '
                                           'таблетки, свечи и кремы (G01); прочие гинекологические средства, '
                                           'включая внутриматочные и вагинальные системы (G02); половые '
                                           'гормоны, в том числе контрацептивы и препараты при климаксе '
                                           '(G03); урологические средства (G04): спазмолитики мочевых путей, '
                                           'препараты при доброкачественной гиперплазии простаты и средства '
                                           'при эректильной дисфункции, которые назначает уролог.\n'
                                           '\n'
                                           'Примеры из каталога. URISPAS (флавоксат) — спазмолитик мочевых '
                                           'путей: по инструкции его назначают при болезненном и учащённом '
                                           'мочеиспускании, в том числе на фоне цистита и простатита. При '
                                           'гиперплазии простаты урологи назначают, например, UROMAX '
                                           '(тамсулозин) или XALFU (альфузозин). CLEOCIN (клиндамицин) — '
                                           'вагинальный крем из группы G01. Антибиотики, которые врач может '
                                           'назначить при цистите, например фосфомицин, находятся в разделе '
                                           '«Антибиотики».\n'
                                           '\n'
                                           'Если вы ищете турецкие лекарства от простатита или лекарство от '
                                           'цистита в Турции, оформите заявку на нужную позицию. Оплаты на '
                                           'сайте нет: сначала менеджер убедится, что препарат есть в '
                                           'наличии, назовёт стоимость с учётом доставки и обсудит с вами '
                                           'детали. Срок доставки — 7–21 рабочий день.\n'
                                           '\n'
                                           'Многие препараты раздела рецептурные — смотрите отметку в '
                                           'карточке; рецепт может понадобиться, и правила здесь у каждой '
                                           'страны свои. Урологические и гормональные средства подбирает '
                                           'врач, поэтому до начала приёма нужны консультация уролога или '
                                           'гинеколога и знакомство с инструкцией.'},
                        'en': {'h1': 'Urology & Gynecology: Cystitis Medicines from Turkey',
                               'meta_title': 'Turkish Urology & Gynecology Medicines | Mudaroba',
                               'meta_description': 'Urological and gynecological medicines from Turkey: '
                                                   'urinary antispasmodics, prostate medicines, vaginal '
                                                   'creams and contraceptives. A manager confirms '
                                                   'availability; delivery takes 7–21 working days.',
                               'seo_text': 'This section brings together urological and gynecological '
                                           'medicines from Turkish pharmacies, ATC group G. People come here '
                                           'to see which cystitis medicines from Turkey can be ordered, '
                                           'which Turkish medicines for men are prescribed for prostate '
                                           'conditions, and which hormonal and vaginal products are '
                                           'available for women.\n'
                                           '\n'
                                           '## What the section covers\n'
                                           '\n'
                                           'Gynecological anti-infectives and antiseptics such as vaginal '
                                           'tablets, pessaries and creams (G01); other gynecologicals, '
                                           'including intrauterine and vaginal systems (G02); sex hormones, '
                                           'including contraceptives and menopause medicines (G03); and '
                                           'urologicals (G04): urinary antispasmodics, medicines for benign '
                                           'prostatic hyperplasia and erectile dysfunction medicines '
                                           'prescribed by a urologist.\n'
                                           '\n'
                                           'Examples from the catalog: URISPAS (flavoxate), a urinary '
                                           'antispasmodic indicated for painful and frequent urination, '
                                           'including symptoms associated with cystitis and prostatitis. For '
                                           'prostatic hyperplasia, urologists prescribe medicines such as '
                                           'UROMAX (tamsulosin) or XALFU (alfuzosin). CLEOCIN (clindamycin) '
                                           'is a vaginal cream from group G01. Antibiotics a doctor may '
                                           'prescribe for cystitis, such as fosfomycin, are listed in the '
                                           'Antibiotics section.\n'
                                           '\n'
                                           'There is no payment on the site: you send a request for the '
                                           'item, a manager first confirms it is in stock, then quotes the '
                                           'cost including shipping and agrees the details with you. '
                                           'Delivery takes 7–21 working days.\n'
                                           '\n'
                                           'Many products here are prescription-only, as marked on the '
                                           'product page, and prescription requirements vary from country to '
                                           'country. Urological and hormonal medicines should be chosen by a '
                                           'doctor, so a consultation with a urologist or gynecologist and a '
                                           'careful look at the leaflet should come first.'}},
 'blood-hematology': {'ru': {'h1': 'Кровь и кроветворение: турецкие препараты железа',
                             'meta_title': 'Турецкие препараты железа и средства для крови | Mudaroba',
                             'meta_description': 'Препараты железа из Турции — капли, сироп, капсулы и '
                                                 'таблетки, а также антиагреганты, антикоагулянты, '
                                                 'гемостатики и растворы для инфузий. Проверка наличия по '
                                                 'заявке, доставка 7–21 рабочий день.',
                             'seo_text': 'Раздел «Кровь и кроветворение» — это группа B по классификации '
                                         'АТХ: препараты железа, средства, влияющие на свёртываемость крови, '
                                         'и растворы для инфузий из турецких аптек. Чаще всего здесь ищут '
                                         'турецкий препарат железа — такие средства собраны в группе B03A и '
                                         'выпускаются в разных формах.\n'
                                         '\n'
                                         '## Препараты железа\n'
                                         '\n'
                                         'Железо в каталоге представлено каплями, сиропом, капсулами и '
                                         'таблетками для приёма внутрь, а также растворами для инъекций, '
                                         'которые вводят только в медицинском учреждении. Примеры: FERRUM '
                                         'HAUSMANN (железа (III) гидроксид полимальтозат) — капли и сироп; '
                                         'FERRO SANOL DUODENAL (железа (II) глицинсульфат) — капсулы. '
                                         'Препараты железа назначают при подтверждённом дефиците железа и '
                                         'железодефицитной анемии по результатам анализа крови, поэтому '
                                         'турецкий препарат железа, как и любой другой, подбирает врач.\n'
                                         '\n'
                                         '## Другие группы\n'
                                         '\n'
                                         'Антиагреганты и антикоагулянты (B01) — например, ECOPIRIN '
                                         '(ацетилсалициловая кислота) и прасугрел; гемостатики (B02), '
                                         'которые применяют при кровотечениях и нарушениях свёртываемости; '
                                         'растворы (B05) — натрия хлорид, раствор Рингера, декстроза.\n'
                                         '\n'
                                         'Препараты железа из Турции и другие средства раздела доступны для '
                                         'заказа через менеджера: вы оставляете заявку, он подтверждает '
                                         'наличие и присылает расчёт с доставкой, после согласования посылка '
                                         'отправляется. Доставка в Россию, Казахстан или Узбекистан — 7–21 '
                                         'рабочий день.\n'
                                         '\n'
                                         'Рецептурный статус указан на странице товара; для рецептурных '
                                         'позиций может потребоваться рецепт врача, и в обход правил страны '
                                         'доставки препараты не отправляются. Средства этого раздела влияют '
                                         'на состав и свёртываемость крови, поэтому применять их можно '
                                         'только после консультации с врачом и чтения инструкции.'},
                      'en': {'h1': 'Blood & Blood Formation: Iron Medicines from Turkey',
                             'meta_title': 'Turkish Iron Medicines & Blood Products | Mudaroba',
                             'meta_description': 'Iron medicines from Turkey in drops, syrup, capsules and '
                                                 'tablets, plus antiplatelets, anticoagulants, hemostatics '
                                                 'and infusion solutions. Stock checked on request, delivery '
                                                 'in 7–21 working days.',
                             'seo_text': 'The Blood & Blood Formation section covers ATC group B: iron '
                                         'preparations, medicines that affect blood clotting and infusion '
                                         'solutions from Turkish pharmacies. The most common search here is '
                                         'for a Turkish iron medicine; these products belong to group B03A '
                                         'and come in several forms.\n'
                                         '\n'
                                         '## Iron preparations\n'
                                         '\n'
                                         'Oral iron is available as drops, syrup, capsules and tablets, and '
                                         'there are injectable forms that are given only in a clinical '
                                         'setting. Examples: FERRUM HAUSMANN (iron(III) hydroxide '
                                         'polymaltose complex) drops and syrup, and FERRO SANOL DUODENAL '
                                         '(ferrous glycine sulfate) capsules. Iron preparations are '
                                         'prescribed for confirmed iron deficiency and iron-deficiency '
                                         'anemia based on blood tests, so any Turkish iron medicine should '
                                         'be chosen by a doctor.\n'
                                         '\n'
                                         '## Other groups\n'
                                         '\n'
                                         'Antiplatelets and anticoagulants (B01), for example ECOPIRIN '
                                         '(acetylsalicylic acid) and prasugrel; hemostatics (B02), used for '
                                         'bleeding and clotting disorders; and solutions (B05) such as '
                                         "sodium chloride, Ringer's solution and dextrose.\n"
                                         '\n'
                                         'Iron medicines from Turkey and other products in this section are '
                                         'ordered through a manager: you leave a request, the manager '
                                         'confirms availability and sends a quote including shipping, and '
                                         'once you agree the parcel is dispatched. Delivery to Russia, '
                                         'Kazakhstan or Uzbekistan takes 7–21 working days.\n'
                                         '\n'
                                         'Prescription status is shown on the product page, and '
                                         "prescription-only items may require a doctor's prescription, and "
                                         "medicines are never sent around the destination country's rules. "
                                         'These medicines affect blood composition and clotting, so use them '
                                         'only after speaking to your doctor and reading the leaflet.'}},
 'nervous-system': {'ru': {'h1': 'Нервная система: успокоительные и другие препараты из Турции',
                           'meta_title': 'Нервная система: успокоительные из Турции | Mudaroba',
                           'meta_description': 'Препараты для нервной системы из Турции: мелатонин для сна, '
                                               'ноотропы, средства для отказа от курения, антидепрессанты по '
                                               'назначению врача. Заказ через менеджера, доставка 7–21 '
                                               'рабочий день.',
                           'seo_text': 'Раздел «Нервная система» — группа N по классификации АТХ, кроме '
                                       'анальгетиков: они вынесены в отдельный раздел обезболивающих. Здесь '
                                       'собраны снотворные и успокоительные (N05), антидепрессанты и '
                                       'ноотропы (N06), противоэпилептические (N03), противопаркинсонические '
                                       '(N04), местные анестетики (N01) и средства для отказа от курения '
                                       '(N07). Если вы ищете успокоительные в Турции, учтите: большинство '
                                       'препаратов этого раздела рецептурные, и подбирает их врач.\n'
                                       '\n'
                                       '## Сон, ноотропы, отказ от курения\n'
                                       '\n'
                                       'Для сна в каталоге есть мелатонин в таблетках и жидких формах — '
                                       'например, INSOVEF (мелатонин), раствор для приёма внутрь; его часто '
                                       'ищут как турецкий сироп для сна. Среди ноотропов — OPEMIN '
                                       '(пирацетам), который назначают по показаниям из инструкции. Турецкие '
                                       'таблетки от курения представлены, например, CHAMPIX (варениклин) — '
                                       'препарат, курс которого назначает врач. Антидепрессанты в Турции — '
                                       'рецептурные препараты, как и большинство турецких успокоительных '
                                       'лекарств: их подбирает специалист индивидуально.\n'
                                       '\n'
                                       'Заказ оформляется заявкой без оплаты на сайте: менеджер сверит '
                                       'наличие, рассчитает итоговую стоимость с доставкой и согласует '
                                       'условия. Международная доставка — 7–21 рабочий день.\n'
                                       '\n'
                                       'Рецептурность каждого препарата отмечена в карточке. Может '
                                       'потребоваться рецепт врача, а правила ввоза в Россию, Казахстан и '
                                       'Узбекистан различаются — отправка выполняется только с их '
                                       'соблюдением. Перед применением прочитайте инструкцию и обязательно '
                                       'проконсультируйтесь с неврологом или психиатром.'},
                    'en': {'h1': 'Nervous System: Sedatives and Other Medicines from Turkey',
                           'meta_title': 'Turkish Sedatives & Nervous System Medicines | Mudaroba',
                           'meta_description': 'Nervous system medicines from Turkey: melatonin for sleep, '
                                               'nootropics, stop-smoking tablets and antidepressants '
                                               'prescribed by a doctor. Order through a manager; shipping '
                                               'takes 7–21 working days.',
                           'seo_text': 'The Nervous System section covers ATC group N, except analgesics, '
                                       'which have their own section. It includes hypnotics and sedatives '
                                       '(N05), antidepressants and nootropics (N06), antiepileptics (N03), '
                                       'anti-Parkinson medicines (N04), local anesthetics (N01) and smoking '
                                       'cessation medicines (N07). If you are looking for sedatives from '
                                       'Turkey, keep in mind that most products here are prescription-only '
                                       'and are chosen by a doctor.\n'
                                       '\n'
                                       '## Sleep, nootropics and quitting smoking\n'
                                       '\n'
                                       'For sleep, the catalog lists melatonin as tablets and liquids, for '
                                       'example INSOVEF (melatonin) oral solution, often searched for as a '
                                       'Turkish sleep syrup. Nootropics include OPEMIN (piracetam), used '
                                       'according to the indications in its leaflet. Turkish stop-smoking '
                                       'tablets include CHAMPIX (varenicline), whose course is set by a '
                                       'doctor. Antidepressants and most sedatives from Turkey are '
                                       'prescription medicines selected individually by a specialist.\n'
                                       '\n'
                                       'Orders are placed by request, with no payment on the site: a manager '
                                       'looks up availability, sends you the full cost with delivery and '
                                       'settles the terms. International delivery takes 7–21 working days.\n'
                                       '\n'
                                       "Each product page states its prescription status. A doctor's "
                                       'prescription may be required, and import rules differ between '
                                       'Russia, Kazakhstan and Uzbekistan; shipments always follow them. '
                                       'Read the leaflet and be sure to consult a neurologist or '
                                       'psychiatrist before use.'}},
 'endocrinology-diabetes': {'ru': {'h1': 'Турецкие лекарства от диабета и гормональные препараты',
                                   'meta_title': 'Турецкие лекарства от диабета и гормоны | Mudaroba',
                                   'meta_description': 'Препараты при диабете и гормональные средства из '
                                                       'Турции: метформин, гликлазид, инсулины, LEVOTIRON. '
                                                       'Заявка, проверка наличия и расчёт доставки через '
                                                       'менеджера.',
                                   'seo_text': 'Раздел «Гормоны и диабет» объединяет две группы АТХ: A10 — '
                                               'препараты при сахарном диабете — и H — системные '
                                               'гормональные средства. Здесь собраны турецкие таблетки от '
                                               'диабета, инсулины и другие инъекционные препараты, а также '
                                               'средства для щитовидной железы и кортикостероиды. Названия '
                                               'указаны латиницей, как на упаковке.\n'
                                               '\n'
                                               '## Препараты при диабете\n'
                                               '\n'
                                               'Среди таблетированных форм — метформин, производные '
                                               'сульфонилмочевины, ингибиторы ДПП-4 и их комбинации. '
                                               'Примеры: GLUFORCE (метформин), DIAMICRON MR (гликлазид), '
                                               'JASITA MET (ситаглиптин + метформин). Агонисты ГПП-1 и '
                                               'инсулины выпускаются в шприц-ручках и картриджах, например '
                                               'LANTUS SOLOSTAR (инсулин гларгин). Турецкие таблетки от '
                                               'сахарного диабета одного бренда часто представлены в '
                                               'нескольких дозировках, поэтому карточку стоит сверить с '
                                               'назначением врача. Если вы ищете турецкое лекарство от '
                                               'сахара по названию с упаковки, удобнее начать поиск с '
                                               'действующего вещества.\n'
                                               '\n'
                                               '## Щитовидная железа и кортикостероиды\n'
                                               '\n'
                                               'Левотироксин представлен препаратом LEVOTIRON (левотироксин) '
                                               'в разных дозировках; в разделе также есть системные '
                                               'кортикостероиды.\n'
                                               '\n'
                                               '## Заявка и доставка\n'
                                               '\n'
                                               'Отправьте заявку — менеджер проверит наличие, рассчитает '
                                               'стоимость и доставку, согласует с вами детали. Срок доставки '
                                               '— 7–21 рабочий день. Инсулины и шприц-ручки требуют особых '
                                               'условий хранения, поэтому возможность их отправки менеджер '
                                               'уточняет отдельно по каждой заявке.\n'
                                               '\n'
                                               'Почти все турецкие таблетки от диабета и гормональные '
                                               'средства рецептурные: статус отмечен в карточке, а '
                                               'требования зависят от препарата и страны доставки. В обход '
                                               'правил страны препараты не отправляются. Перед применением '
                                               'прочитайте инструкцию и согласуйте любые изменения с '
                                               'эндокринологом.'},
                            'en': {'h1': 'Turkish Diabetes Medicines and Hormones',
                                   'meta_title': 'Turkish Diabetes Medicines & Hormones | Mudaroba',
                                   'meta_description': 'Diabetes medicines and systemic hormones from '
                                                       'Turkey: metformin, gliclazide, insulins and '
                                                       'LEVOTIRON. Send a request and a manager checks '
                                                       'availability, cost and delivery.',
                                   'seo_text': 'The Hormones & Diabetes section combines two ATC groups: '
                                               'A10, drugs used in diabetes, and H, systemic hormonal '
                                               'preparations. It includes Turkish diabetes tablets, insulins '
                                               'and other injectables, as well as thyroid medicines and '
                                               'corticosteroids. Names appear in Turkish, as on the pack.\n'
                                               '\n'
                                               '## Diabetes medicines\n'
                                               '\n'
                                               'Oral options include metformin, sulfonylureas, DPP-4 '
                                               'inhibitors and their combinations, for example GLUFORCE '
                                               '(metformin), DIAMICRON MR (gliclazide) and JASITA MET '
                                               '(sitagliptin + metformin). GLP-1 agonists and insulins come '
                                               'in pre-filled pens and cartridges, such as LANTUS SOLOSTAR '
                                               '(insulin glargine). One brand is often available in several '
                                               "strengths, so compare the card with your doctor's "
                                               'prescription.\n'
                                               '\n'
                                               '## Thyroid hormones and corticosteroids\n'
                                               '\n'
                                               'Levothyroxine is available as LEVOTIRON (levothyroxine) in a '
                                               'range of strengths, and the section also lists systemic '
                                               'corticosteroids.\n'
                                               '\n'
                                               '## Requests and delivery\n'
                                               '\n'
                                               'Send a request and a manager will check availability, '
                                               'calculate the cost and shipping and agree the details with '
                                               'you. Delivery takes 7–21 business days. Insulins and pens '
                                               'need special storage conditions, so whether they can be '
                                               'shipped is clarified separately for each request.\n'
                                               '\n'
                                               'Almost everything here is prescription-only. The status is '
                                               'marked on the card, requirements depend on the medicine and '
                                               'the destination country, and nothing is sent in breach of '
                                               'local rules. Read the leaflet and discuss any change with '
                                               'your endocrinologist.'}},
 'antiinfectives-vaccines': {'ru': {'h1': 'Противоинфекционные средства и вакцины из Турции',
                                    'meta_title': 'Противоинфекционные средства и вакцины из Турции | '
                                                  'Mudaroba',
                                    'meta_description': 'Противовирусные, противогрибковые и '
                                                        'противопаразитарные препараты из Турции, в том '
                                                        'числе таблетки от глистов, и вакцины. Заявка, '
                                                        'проверка наличия и доставка через менеджера.',
                                    'seo_text': 'В разделе собраны противоинфекционные средства из Турции, '
                                                'кроме антибиотиков (для них есть отдельный раздел), и '
                                                'противопаразитарные препараты, в том числе турецкие '
                                                'таблетки от глистов. По АТХ это группа J без J01 и группа '
                                                'P. Названия даны латиницей, как на турецкой упаковке; '
                                                'действующее вещество, форма и инструкция — в карточке.\n'
                                                '\n'
                                                '## Что входит в раздел\n'
                                                '\n'
                                                'Турецкие противовирусные препараты (J05) — например, OSEFLU '
                                                '(осельтамивир) в капсулах и гранулах. Противогрибковые '
                                                'средства системного действия (J02) — KANDIZOL (флуконазол) '
                                                'и другие препараты флуконазола. Вакцины (J07) требуют '
                                                'особых условий хранения и транспортировки, поэтому '
                                                'возможность их отправки менеджер уточняет по каждой '
                                                'заявке.\n'
                                                '\n'
                                                'Отдельная группа — противопаразитарные средства. Турецкие '
                                                'таблетки от глистов в каталоге содержат мебендазол или '
                                                'альбендазол: VERMAZOL (мебендазол) — жевательные таблетки, '
                                                'RABIDOL (альбендазол) — таблетки в плёночной оболочке.\n'
                                                '\n'
                                                '## Как оформить заявку\n'
                                                '\n'
                                                'Выберите препарат и отправьте заявку. Менеджер проверит '
                                                'наличие, рассчитает стоимость с доставкой и согласует '
                                                'детали. Доставка в Россию, Казахстан и Узбекистан занимает '
                                                '7–21 рабочий день.\n'
                                                '\n'
                                                'Рецептурные препараты отмечены в карточке, требования к '
                                                'рецепту зависят от препарата и страны доставки, и правила '
                                                'страны соблюдаются. Перед применением прочитайте инструкцию '
                                                'и проконсультируйтесь с врачом — это касается и средств от '
                                                'глистов, у которых есть противопоказания и возрастные '
                                                'ограничения.'},
                             'en': {'h1': 'Antiinfectives and Vaccines from Turkey',
                                    'meta_title': 'Turkish Antivirals, Dewormers & Vaccines | Mudaroba',
                                    'meta_description': 'Antiviral, systemic antifungal and antiparasitic '
                                                        'medicines from Turkey, including deworming tablets, '
                                                        'plus vaccines. Send a request and a manager checks '
                                                        'stock, cost and delivery.',
                                    'seo_text': 'This section covers anti-infective medicines from Turkey '
                                                'other than antibiotics, which have their own section, '
                                                'together with antiparasitic products, including Turkish '
                                                'deworming tablets. In ATC terms that means group J without '
                                                'J01, plus group P. Names are printed in Turkish as on the '
                                                'pack, and the card shows the active ingredient, dosage form '
                                                'and patient leaflet.\n'
                                                '\n'
                                                '## What the section includes\n'
                                                '\n'
                                                'Antivirals (J05) include OSEFLU (oseltamivir) as capsules '
                                                'and granules. Systemic antifungals (J02) include KANDIZOL '
                                                '(fluconazole) and other fluconazole products. Vaccines '
                                                '(J07) need special storage and transport conditions, so '
                                                'whether they can be shipped is clarified for each request.\n'
                                                '\n'
                                                'Antiparasitic medicines form a separate group. Turkish '
                                                'tablets for worms in the catalogue contain mebendazole or '
                                                'albendazole: VERMAZOL (mebendazole) chewable tablets and '
                                                'RABIDOL (albendazole) film-coated tablets.\n'
                                                '\n'
                                                '## How to place a request\n'
                                                '\n'
                                                'Choose a product and send a request. A manager checks '
                                                'availability, calculates the cost including delivery and '
                                                'confirms the details. Shipping to Russia, Kazakhstan and '
                                                'Uzbekistan takes 7–21 business days.\n'
                                                '\n'
                                                'Prescription-only medicines are marked on the card, '
                                                'requirements depend on the product and the destination '
                                                'country, and local rules are respected. Read the leaflet '
                                                'and consult a doctor before use; this applies to deworming '
                                                'tablets too, which have contraindications and age '
                                                'restrictions.'}}}

COLLECTIONS = [{'slug': 'ot-prostudy-i-grippa',
  'parent': 'medicines',
  'sort_order': 10,
  'atc_prefixes': 'R05X, J05AH',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''},
 {'slug': 'mazi-i-kremy',
  'parent': 'medicines',
  'sort_order': 20,
  'atc_prefixes': '',
  'name_keywords': '',
  'dosage_forms': 'ointment, cream, gel',
  'exclude_atc_prefixes': ''},
 {'slug': 'detskie-lekarstva',
  'parent': 'medicines',
  'sort_order': 30,
  'atc_prefixes': '',
  'name_keywords': 'PEDIATRIK, PEDIYATRIK, COCUK, ÇOCUK, BEBE, детск',
  'dosage_forms': '',
  'exclude_atc_prefixes': 'V06, J07, B05'},
 {'slug': 'dlya-pohudeniya',
  'parent': 'medicines',
  'sort_order': 40,
  'atc_prefixes': 'A08',
  'name_keywords': 'SAXENDA, WEGOVY',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''},
 {'slug': 'ukoly',
  'parent': 'medicines',
  'sort_order': 50,
  'atc_prefixes': '',
  'name_keywords': '',
  'dosage_forms': 'injection',
  'exclude_atc_prefixes': 'G03B, A14'},
 {'slug': 'ot-gemorroya',
  'parent': 'medicines',
  'sort_order': 60,
  'atc_prefixes': 'C05A',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''},
 {'slug': 'spreyi',
  'parent': 'medicines',
  'sort_order': 70,
  'atc_prefixes': '',
  'name_keywords': '',
  'dosage_forms': 'spray',
  'exclude_atc_prefixes': ''},
 {'slug': 'kapli',
  'parent': 'medicines',
  'sort_order': 80,
  'atc_prefixes': '',
  'name_keywords': '',
  'dosage_forms': 'drops',
  'exclude_atc_prefixes': ''},
 {'slug': 'siropy',
  'parent': 'medicines',
  'sort_order': 90,
  'atc_prefixes': '',
  'name_keywords': '',
  'dosage_forms': 'syrup',
  'exclude_atc_prefixes': ''},
 {'slug': 'svechi',
  'parent': 'medicines',
  'sort_order': 100,
  'atc_prefixes': '',
  'name_keywords': '',
  'dosage_forms': 'suppository',
  'exclude_atc_prefixes': ''},
 {'slug': 'ot-nasmorka',
  'parent': 'respiratory-ent',
  'sort_order': 110,
  'atc_prefixes': 'R01',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''},
 {'slug': 'ushnye-kapli',
  'parent': 'respiratory-ent',
  'sort_order': 120,
  'atc_prefixes': 'S02',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''},
 {'slug': 'varikoz',
  'parent': 'cardio',
  'sort_order': 130,
  'atc_prefixes': 'C05B, C05C',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''},
 {'slug': 'ot-psoriaza',
  'parent': 'dermatology',
  'sort_order': 140,
  'atc_prefixes': 'D05',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''},
 {'slug': 'protivogribkovye',
  'parent': 'dermatology',
  'sort_order': 150,
  'atc_prefixes': 'D01',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''},
 {'slug': 'ginekologiya',
  'parent': 'urology-gynecology',
  'sort_order': 160,
  'atc_prefixes': 'G01, G02, G03',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': 'G03B'},
 {'slug': 'ot-podagry',
  'parent': 'musculoskeletal',
  'sort_order': 170,
  'atc_prefixes': 'M04',
  'name_keywords': '',
  'dosage_forms': '',
  'exclude_atc_prefixes': ''}]

COLLECTION_TEXTS = {'ot-prostudy-i-grippa': {'ru': {'name': 'От простуды и гриппа',
                                 'h1': 'Турецкие противовирусные и средства от простуды и гриппа',
                                 'meta_title': 'Турецкие противовирусные и порошки от простуды | Mudaroba',
                                 'meta_description': 'Турецкие средства от простуды и гриппа: '
                                                     'комбинированные порошки, таблетки и сиропы с '
                                                     'парацетамолом, противовирусные с осельтамивиром. '
                                                     'Заявка, расчёт, доставка 7–21 рабочий день.',
                                 'seo_text': 'В подборке собраны турецкие противовирусные препараты и '
                                             'комбинированные средства от простуды и гриппа. В классификации '
                                             'АТХ это две разные группы, но ищут их обычно в один и тот же '
                                             'сезон, поэтому они показаны вместе.\n'
                                             '\n'
                                             '## Комбинированные средства от простуды\n'
                                             '\n'
                                             'Первая группа — комбинированные средства от простуды с кодом '
                                             'АТХ R05X. Как правило, в составе — парацетамол в сочетании с '
                                             'антигистаминным компонентом, иногда также с сосудосуживающим. '
                                             'Выпускаются они в виде порошков в саше, из которых готовят '
                                             'горячий напиток, а также таблеток, капсул и сиропов, в том '
                                             'числе детских. Именно такие саше часто называют турецким '
                                             'порошком от простуды. Пример из каталога — PEDITUS HOT C '
                                             '(парацетамол + хлорфенирамин + аскорбиновая кислота).\n'
                                             '\n'
                                             '## Противовирусные при гриппе\n'
                                             '\n'
                                             'Вторая группа — противовирусные препараты из Турции из класса '
                                             'ингибиторов нейраминидазы (J05AH), которые назначают при '
                                             'гриппе. В каталоге это OSEFLU (осельтамивир) в капсулах и '
                                             'гранулах и ENFLUVIR (осельтамивир) в капсулах и в виде порошка '
                                             'для приготовления суспензии; гранулы и суспензия предусмотрены '
                                             'и для детей.\n'
                                             '\n'
                                             'Чтобы получить нужные позиции, отправьте заявку: менеджер '
                                             'уточнит наличие, рассчитает стоимость и доставку, затем '
                                             'согласует заказ с вами. Посылка из Турции идёт 7–21 рабочий '
                                             'день — учитывайте этот срок при планировании.\n'
                                             '\n'
                                             'Турецкие противовирусные средства от гриппа назначает врач, а '
                                             'у комбинированных средств от простуды есть противопоказания и '
                                             'возрастные ограничения. Перед применением сверьтесь с '
                                             'инструкцией и посоветуйтесь со специалистом. Если препарат '
                                             'отмечен в карточке как рецептурный, может потребоваться рецепт '
                                             '— это зависит от страны доставки.'},
                          'en': {'name': 'Cold & Flu',
                                 'h1': 'Turkish Cold & Flu Remedies and Antivirals',
                                 'meta_title': 'Turkish Cold and Flu Remedies & Antivirals | Mudaroba',
                                 'meta_description': 'Turkish cold and flu powders, tablets and syrups with '
                                                     'paracetamol, plus oseltamivir antivirals. Send a '
                                                     'request: we check availability and quote delivery in '
                                                     '7–21 business days.',
                                 'seo_text': 'This collection covers Turkish cold and flu remedies and '
                                             'antiviral medicines. In the ATC classification they belong to '
                                             'two different groups, but people tend to look for them in the '
                                             'same season, so they are shown together.\n'
                                             '\n'
                                             '## Combination cold remedies\n'
                                             '\n'
                                             'The first group is combination cold remedies (ATC R05X). They '
                                             'typically pair paracetamol with an antihistamine and sometimes '
                                             'a decongestant. They come as sachets of powder dissolved in '
                                             'hot water to make a drink, the well-known Turkish cold powder, '
                                             "as well as tablets, capsules and syrups, including children's "
                                             'formulations. One example in the catalog is PEDITUS HOT C '
                                             '(paracetamol + chlorphenamine + ascorbic acid).\n'
                                             '\n'
                                             '## Flu antivirals\n'
                                             '\n'
                                             'The second group is neuraminidase inhibitors (ATC J05AH), '
                                             'antivirals from Turkey prescribed for influenza. Here you will '
                                             'find OSEFLU (oseltamivir) capsules and granules and ENFLUVIR '
                                             '(oseltamivir) capsules and powder for oral suspension; the '
                                             "granules and suspension also come in children's forms.\n"
                                             '\n'
                                             'Add what you need to your list and submit a request. A manager '
                                             'confirms availability, works out the cost with shipping and '
                                             'agrees the order with you. Delivery from Turkey takes 7–21 '
                                             'business days, so allow for that when planning.\n'
                                             '\n'
                                             'Flu antivirals are prescribed by a doctor, and combination '
                                             'cold remedies have contraindications and age limits. Read the '
                                             'leaflet and check with your doctor first. If a product page '
                                             'marks a medicine as prescription-only, you may need a '
                                             'prescription, depending on the destination country.'}},
 'mazi-i-kremy': {'ru': {'name': 'Мази, кремы и гели',
                         'h1': 'Турецкие мази, кремы и гели',
                         'meta_title': 'Турецкие мази, кремы и гели из аптек Турции | Mudaroba',
                         'meta_description': 'Турецкие мази, кремы и гели из разных разделов: обезболивающие '
                                             'гели, дерматологические и противогрибковые средства, от '
                                             'геморроя, ранозаживляющие. Заявка, доставка 7–21 рабочий день.',
                         'seo_text': 'Подборка объединяет мази, кремы и гели для наружного применения из '
                                     'разных разделов каталога. Если вы ищете турецкую мазь, но не знаете, к '
                                     'какой группе она относится, удобнее начать с этой подборки: в неё '
                                     'попадают все препараты, у которых в карточке указана форма «мазь», '
                                     '«крем» или «гель».\n'
                                     '\n'
                                     'На турецких упаковках мазь обозначается словом merhem (или pomad), '
                                     'крем — krem, гель — jel. Эти слова входят в название товара, поэтому '
                                     'по ним легко понять форму выпуска.\n'
                                     '\n'
                                     '## Какие группы здесь есть\n'
                                     '\n'
                                     'Есть обезболивающие и противовоспалительные гели, например SERODIFEN '
                                     '(диклофенак) и SULJEL (нимесулид). Дерматологические средства '
                                     'представлены кремами и мазями с антибактериальными веществами, такими '
                                     'как BACODERM (мупироцин), и с кортикостероидами, например KLOBATE '
                                     '(клобетазол). Среди ранозаживляющих — крем FITO (экстракт пшеницы). '
                                     'Также в подборке есть противогрибковые кремы, мази от геморроя и '
                                     'другие средства местного действия. Действующее вещество, концентрация '
                                     'и инструкция приведены в каждой карточке.\n'
                                     '\n'
                                     'Мази из Турции заказывают так же, как другие позиции: вы отправляете '
                                     'заявку, менеджер проверяет наличие, считает стоимость с доставкой и '
                                     'согласовывает детали. Посылка приходит за 7–21 рабочий день.\n'
                                     '\n'
                                     'У наружных средств тоже есть противопоказания, а у кремов с '
                                     'кортикостероидами — ограничения по применению, указанные в инструкции. '
                                     'Прежде чем использовать любую турецкую мазь, ознакомьтесь с '
                                     'инструкцией и проконсультируйтесь со специалистом; рецептурные кремы и '
                                     'мази могут потребовать рецепта врача.'},
                  'en': {'name': 'Ointments, Creams & Gels',
                         'h1': 'Turkish Ointments, Creams and Gels',
                         'meta_title': 'Turkish Ointments, Creams & Gels | Mudaroba',
                         'meta_description': 'Turkish ointments, creams and gels from across the catalog: '
                                             'pain gels, skin creams, antifungals, haemorrhoid and '
                                             'wound-care products. Request a quote; delivery in 7–21 '
                                             'business days.',
                         'seo_text': 'This collection brings together Turkish ointments, creams and gels for '
                                     'external use from different sections of the catalog. It includes every '
                                     'product whose dosage form is listed as an ointment, cream or gel, so '
                                     'it is a handy starting point when you know the form you want but not '
                                     'the category.\n'
                                     '\n'
                                     'On Turkish packs, an ointment is labelled merhem (or pomad), a cream '
                                     'is krem and a gel is jel. These words are part of the product name, '
                                     'which makes the form easy to spot.\n'
                                     '\n'
                                     '## What you will find\n'
                                     '\n'
                                     'There are anti-inflammatory gels for pain, such as SERODIFEN '
                                     '(diclofenac) and SULJEL (nimesulide). Skin products include '
                                     'antibacterial creams and ointments like BACODERM (mupirocin) and '
                                     'corticosteroid preparations such as KLOBATE (clobetasol). For wound '
                                     'care there is FITO (wheat extract) cream. You will also find '
                                     'antifungal creams, haemorrhoid ointments and other topical products. '
                                     'Each product page lists the active ingredient, concentration and '
                                     'leaflet.\n'
                                     '\n'
                                     'These products are ordered like anything else on the site: your '
                                     'request goes to a manager, who verifies stock and comes back with a '
                                     'price that includes postage. Expect the parcel in 7–21 business days.\n'
                                     '\n'
                                     'Topical medicines have contraindications too, and corticosteroid '
                                     'creams come with usage limits set out in the leaflet. Read the leaflet '
                                     'and ask your doctor before using any of these products; prescription '
                                     "creams and ointments may need a doctor's prescription."}},
 'ot-nasmorka': {'ru': {'name': 'От насморка: капли и спреи',
                        'h1': 'Турецкие капли и спреи для носа от насморка',
                        'meta_title': 'Турецкие капли в нос и спреи для носа | Mudaroba',
                        'meta_description': 'Турецкие капли в нос и назальные спреи: сосудосуживающие с '
                                            'ксилометазолином и оксиметазолином, кортикостероидные и '
                                            'противоаллергические. Заявка, доставка 7–21 рабочий день.',
                        'seo_text': 'В подборке собраны турецкие капли в нос и назальные спреи — препараты '
                                    'группы R01 по классификации АТХ. Если вам нужен спрей для носа из '
                                    'Турции, здесь его удобно найти по действующему веществу и форме '
                                    'выпуска.\n'
                                    '\n'
                                    '## Группы препаратов\n'
                                    '\n'
                                    'Турецкие сосудосуживающие капли и спреи (деконгестанты) на основе '
                                    'ксилометазолина и оксиметазолина применяют при заложенности носа. '
                                    'Назальные кортикостероиды, например беклометазон, и '
                                    'противоаллергические спреи с азеластином назначают при аллергическом '
                                    'рините. В подборку входят и другие назальные средства из той же '
                                    'группы.\n'
                                    '\n'
                                    'Из сосудосуживающих в каталоге есть OTRIVINE (ксилометазолин) — '
                                    'дозированные спреи, в том числе детский вариант, — и ILIADIN '
                                    '(оксиметазолин) в виде капель и спрея, тоже с детской концентрацией. '
                                    'Среди кортикостероидных — NAZOBEC (беклометазон), среди '
                                    'противоаллергических — NAZALASTIN (азеластин). В карточках указаны '
                                    'дозировка, объём флакона и инструкция; названия написаны по-турецки, '
                                    'как на упаковке (burun spreyi — спрей для носа, damla — капли).\n'
                                    '\n'
                                    'Турецкие спреи для носа и капли заказывают так: вы отмечаете нужные '
                                    'флаконы в списке заявки, менеджер связывается с вами и подтверждает '
                                    'наличие и сумму с доставкой. Ожидание посылки — 7–21 рабочий день.\n'
                                    '\n'
                                    'У сосудосуживающих средств есть ограничения по длительности применения '
                                    'и возрасту, а гормональные спреи назначает врач. Перед использованием '
                                    'обязательно прочитайте инструкцию и посоветуйтесь с врачом, особенно '
                                    'если средство нужно ребёнку. Рецептурный статус указан в карточке: от '
                                    'него и от страны доставки зависит, понадобится ли рецепт.'},
                 'en': {'name': 'Nasal Drops & Sprays',
                        'h1': 'Turkish Nasal Sprays and Nose Drops',
                        'meta_title': 'Turkish Nasal Sprays & Nose Drops | Mudaroba',
                        'meta_description': 'Turkish nasal sprays and nose drops: xylometazoline and '
                                            'oxymetazoline decongestants, corticosteroid and antiallergic '
                                            'sprays. Send a request; delivery takes 7–21 business days.',
                        'seo_text': 'This collection brings together Turkish nasal sprays and nose drops, '
                                    'the products in ATC group R01. If you are after a nasal spray from '
                                    'Turkey, you can browse them here by active ingredient and form.\n'
                                    '\n'
                                    '## Groups of products\n'
                                    '\n'
                                    'Decongestant drops and sprays based on xylometazoline or oxymetazoline '
                                    'are used for a blocked nose. Nasal corticosteroids such as '
                                    'beclometasone and antiallergic sprays with azelastine are prescribed '
                                    'for allergic rhinitis. Other nasal preparations from the same group are '
                                    'included as well.\n'
                                    '\n'
                                    'Decongestants in the catalog include OTRIVINE (xylometazoline) metered '
                                    'sprays, with a paediatric version, and ILIADIN (oxymetazoline) drops '
                                    "and sprays, also in a children's strength. Corticosteroids are "
                                    'represented by NAZOBEC (beclometasone), and antiallergic sprays by '
                                    'NAZALASTIN (azelastine). Product pages show the strength, bottle size '
                                    'and leaflet; names are in Turkish as on the pack (burun spreyi means '
                                    'nasal spray, damla means drops).\n'
                                    '\n'
                                    'Mark the bottles you need in your request list; a manager then gets in '
                                    'touch to confirm availability and the total with delivery. Allow 7–21 '
                                    'business days for the parcel to arrive.\n'
                                    '\n'
                                    'Decongestants have limits on how long and at what age they can be used, '
                                    'and steroid sprays are prescribed by a doctor. Go through the leaflet '
                                    'and consult a doctor before use, especially for children. The '
                                    'prescription status is shown on each product page, and together with '
                                    'the destination country it determines whether a prescription is '
                                    'needed.'}},
 'ushnye-kapli': {'ru': {'name': 'Ушные капли',
                         'h1': 'Турецкие ушные капли',
                         'meta_title': 'Турецкие ушные капли: обезболивающие и комбинированные | Mudaroba',
                         'meta_description': 'Турецкие ушные капли: OTIPAX (феназон + лидокаин), OTIKAIN '
                                             '(лидокаин) и комбинированные капли с антибиотиком и '
                                             'кортикостероидом. Заявка менеджеру, доставка 7–21 рабочий '
                                             'день.',
                         'seo_text': 'В подборке — турецкие ушные капли, то есть препараты группы S02 по '
                                     'классификации АТХ; она входит в раздел «Дыхательная система и ЛОР». '
                                     'Сюда входят капли с местным анестетиком, которые применяют при боли в '
                                     'ухе, и комбинированные средства с антибактериальным и '
                                     'противовоспалительным компонентами — их назначают, например, при '
                                     'отите.\n'
                                     '\n'
                                     '## Препараты в каталоге\n'
                                     '\n'
                                     'OTIPAX (феназон + лидокаин) и OTIKAIN (лидокаин) — капли с '
                                     'обезболивающим действием. Есть и комбинированные капли, в которых '
                                     'антибиотик сочетается с кортикостероидом, — их назначает только врач. '
                                     'На турецкой упаковке капли для ушей подписаны как kulak damlası. В '
                                     'карточке указаны действующие вещества, концентрация, объём флакона и '
                                     'инструкция, так что легко проверить, совпадает ли состав с тем, что '
                                     'назвал врач.\n'
                                     '\n'
                                     'Турецкие ушные капли можно добавить в заявку: после проверки наличия '
                                     'нужной позиции менеджер сообщит стоимость с доставкой, срок которой — '
                                     '7–21 рабочий день.\n'
                                     '\n'
                                     'У ушных капель есть противопоказания, например нарушение целостности '
                                     'барабанной перепонки, поэтому перед применением нужен осмотр у '
                                     'ЛОР-врача: он определяет причину боли в ухе и подбирает средство. '
                                     'Прочитайте инструкцию до начала применения. Если капли отмечены в '
                                     'карточке как рецептурные, потребуется ли рецепт, зависит от страны '
                                     'доставки.'},
                  'en': {'name': 'Ear Drops',
                         'h1': 'Turkish Ear Drops',
                         'meta_title': 'Turkish Ear Drops: Lidocaine and Combination Drops | Mudaroba',
                         'meta_description': 'Turkish ear drops: OTIPAX (phenazone + lidocaine), OTIKAIN '
                                             '(lidocaine) and combination drops with an antibiotic and a '
                                             'corticosteroid. Send a request; delivery takes 7–21 business '
                                             'days.',
                         'seo_text': 'This collection gathers Turkish ear drops (ATC group S02) and sits '
                                     'within the Respiratory & ENT section. It includes drops with a local '
                                     'anaesthetic used for ear pain and combination products with '
                                     'antibacterial and anti-inflammatory components, which doctors '
                                     'prescribe for conditions such as otitis.\n'
                                     '\n'
                                     '## In the catalog\n'
                                     '\n'
                                     'OTIPAX (phenazone + lidocaine) and OTIKAIN (lidocaine) are drops for '
                                     'ear pain. There are also combination drops pairing an antibiotic with '
                                     'a corticosteroid, which only a doctor can prescribe. On Turkish packs '
                                     'ear drops are labelled kulak damlası, and the product card gives the '
                                     'active ingredients, concentration, bottle size and leaflet.\n'
                                     '\n'
                                     'Ear drops can be added to a request; after checking stock, a manager '
                                     'lets you know the cost with delivery, and shipping time is 7–21 '
                                     'business days.\n'
                                     '\n'
                                     'Ear drops have contraindications, such as a damaged eardrum, so the '
                                     'ear should be examined by an ENT doctor first; the same doctor '
                                     'establishes the cause of the pain and decides which drops are '
                                     'appropriate. Read the leaflet before use; a prescription may be '
                                     'requested for prescription-only drops.'}},
 'dlya-pohudeniya': {'ru': {'name': 'Для похудения',
                            'h1': 'Турецкие препараты для похудения по назначению врача',
                            'meta_title': 'Турецкие препараты для похудения | Mudaroba',
                            'meta_description': 'XENICAL (орлистат), SAXENDA (лираглутид) и WEGOVY '
                                                '(семаглутид) из Турции — рецептурные средства при ожирении. '
                                                'Заявка, расчёт стоимости, доставка 7–21 рабочий день.',
                            'seo_text': 'В подборке собраны рецептурные турецкие препараты для похудения, '
                                        'которые врач может назначить при ожирении или избыточной массе тела '
                                        'по показаниям инструкции. Это не средства для самостоятельного '
                                        'применения: решение принимает врач после обследования, и обычно '
                                        'такие препараты назначают в дополнение к питанию с пониженной '
                                        'калорийностью и физической активности.\n'
                                        '\n'
                                        '## Что входит в подборку\n'
                                        '\n'
                                        'Если вы ищете турецкие таблетки для похудения, учтите: в подборке '
                                        'только рецептурные лекарственные препараты — капсулы и инъекционные '
                                        'средства. Капсулы для похудения — XENICAL (орлистат) из группы A08 '
                                        'по АТХ: он уменьшает всасывание жиров из пищи. Инъекционные '
                                        'средства — SAXENDA (лираглутид) и WEGOVY (семаглутид) в '
                                        'шприц-ручках для подкожного введения; это агонисты рецепторов '
                                        'ГПП-1, которые назначают для длительного контроля массы тела. Для '
                                        'таких турецких уколов для похудения важны условия хранения, они '
                                        'описаны в инструкции.\n'
                                        '\n'
                                        'Чтобы заказать препарат, оставьте заявку: менеджер подтвердит, есть '
                                        'ли нужная дозировка, подготовит расчёт с учётом доставки в Россию, '
                                        'Казахстан или Узбекистан и согласует условия заказа. По '
                                        'шприц-ручкам он при заявке отдельно уточнит вопросы хранения во '
                                        'время перевозки. Срок международной доставки — 7–21 рабочий день.\n'
                                        '\n'
                                        'Все турецкие препараты для похудения в этой подборке рецептурные — '
                                        'это отмечено в карточках, а нужен ли рецепт для отправки, '
                                        'определяется самим препаратом и правилами страны получателя. У '
                                        'каждого средства есть противопоказания и ограничения, поэтому перед '
                                        'применением внимательно прочитайте инструкцию и обсудите назначение '
                                        'с врачом. Отзывы знакомых не заменяют консультацию специалиста.'},
                     'en': {'name': 'Weight Management',
                            'h1': 'Turkish Weight-Loss Medicines on Prescription',
                            'meta_title': 'Turkish Weight-Loss Medicines | Mudaroba',
                            'meta_description': 'XENICAL (orlistat), SAXENDA (liraglutide) and WEGOVY '
                                                '(semaglutide) from Turkey — prescription medicines for '
                                                'obesity. Send a request; delivery in 7–21 working days.',
                            'seo_text': 'This collection groups prescription weight-loss medicines from '
                                        'Turkey that a doctor may prescribe for obesity or overweight, '
                                        'following the indications in the leaflet. They are not meant for '
                                        'self-use: the decision rests with a physician, and these medicines '
                                        'are usually prescribed alongside a reduced-calorie diet and regular '
                                        'physical activity.\n'
                                        '\n'
                                        '## What the collection includes\n'
                                        '\n'
                                        'If you are looking for Turkish weight-loss pills, note that this '
                                        'collection contains prescription medicines only, in the form of '
                                        'capsules and injections. XENICAL (orlistat), ATC group A08, is a '
                                        'capsule that reduces the absorption of dietary fat. SAXENDA '
                                        '(liraglutide) and WEGOVY (semaglutide) are GLP-1 receptor agonists '
                                        'supplied in prefilled pens for subcutaneous injection and '
                                        'prescribed for long-term weight management. Storage conditions '
                                        'matter for the pens and are set out in the leaflet.\n'
                                        '\n'
                                        'To order, leave a request: a manager checks that the strength you '
                                        'need is available, calculates the cost including delivery to '
                                        'Russia, Kazakhstan or Uzbekistan and confirms the details. For '
                                        'injection pens, the manager will go over storage during transit '
                                        'when processing your request. International delivery takes 7–21 '
                                        'working days.\n'
                                        '\n'
                                        'Every product in this collection is prescription-only, as marked on '
                                        'the product page, and requirements depend on the medicine and the '
                                        'destination country. Each one has contraindications and '
                                        'limitations, so read the leaflet carefully and discuss it with your '
                                        'doctor first. Online reviews are no substitute for medical '
                                        'advice.'}},
 'detskie-lekarstva': {'ru': {'name': 'Детские лекарства',
                              'h1': 'Турецкие лекарства для детей: сиропы и суспензии',
                              'meta_title': 'Турецкие лекарства для детей | Mudaroba',
                              'meta_description': 'Детские сиропы, суспензии и другие педиатрические формы '
                                                  'из Турции: GRIPIN BEBE, SEKROL PEDIYATRIK, MUKOTIK. '
                                                  'Заявка, проверка наличия, доставка 7–21 рабочий день.',
                              'seo_text': 'В подборку входят турецкие лекарства для детей, в названии '
                                          'которых указана детская форма: PEDIATRIK или PEDIYATRIK, COCUK '
                                          '(«детский», «для детей») и BEBE. Чаще всего это сиропы и оральные '
                                          'суспензии, встречаются также гранулы в саше и назальные спреи. '
                                          'Детское питание в подборку не входит.\n'
                                          '\n'
                                          '## Примеры препаратов\n'
                                          '\n'
                                          'Турецкий сироп для детей — самая частая форма в подборке. GRIPIN '
                                          'BEBE (парацетамол) — жаропонижающий и обезболивающий сироп. '
                                          'SEKROL PEDIYATRIK (амброксол) и детский сироп MUKOTIK '
                                          '(карбоцистеин) — муколитики, их назначают при кашле с вязкой '
                                          'мокротой. В карточке каждого препарата указаны действующее '
                                          'вещество, концентрация и объём флакона.\n'
                                          '\n'
                                          'Вместо того чтобы просить знакомых привезти лекарства из Турции '
                                          'для детей, можно оставить заявку — менеджер выяснит, есть ли '
                                          'препарат в нужном объёме флакона, сообщит стоимость вместе с '
                                          'доставкой и обсудит детали. Посылка будет в пути 7–21 рабочий '
                                          'день, поэтому о детских лекарствах из Турции стоит позаботиться '
                                          'заранее.\n'
                                          '\n'
                                          'Дозировку для ребёнка определяет педиатр по инструкции — с учётом '
                                          'возраста и веса. Часть турецких лекарств для детей рецептурная, '
                                          'это отмечено в карточке; правила для таких средств различаются в '
                                          'зависимости от препарата и страны. Прежде чем дать ребёнку любое '
                                          'средство, прочитайте инструкцию и проконсультируйтесь с '
                                          'педиатром.'},
                       'en': {'name': "Children's Medicines",
                              'h1': 'Turkish Medicines for Children: Syrups and Suspensions',
                              'meta_title': 'Turkish Medicines for Children | Mudaroba',
                              'meta_description': "Children's syrups, suspensions and other paediatric forms "
                                                  'from Turkey, including GRIPIN BEBE, SEKROL PEDIYATRIK and '
                                                  'MUKOTIK. Send a request; delivery in 7–21 working days.',
                              'seo_text': 'This collection brings together Turkish medicines for children '
                                          'whose names carry a paediatric label: PEDIATRIK or PEDIYATRIK, '
                                          'COCUK (Turkish for children) and BEBE. Most are syrups and oral '
                                          'suspensions, along with some granules in sachets and nasal '
                                          'sprays. Baby food is not part of this collection.\n'
                                          '\n'
                                          '## Examples from the catalogue\n'
                                          '\n'
                                          "Children's syrup is the most common form here. GRIPIN BEBE "
                                          '(paracetamol) is a syrup for fever and pain. SEKROL PEDIYATRIK '
                                          "(ambroxol) and MUKOTIK children's syrup (carbocisteine) are "
                                          'mucolytics prescribed for a cough with thick mucus. Each product '
                                          'page shows the active ingredient, concentration and bottle size.\n'
                                          '\n'
                                          "Instead of asking friends to bring children's medicines back from "
                                          'Turkey, you can leave a request: a manager finds out whether the '
                                          'bottle size you need is available, quotes the cost with delivery '
                                          'and agrees the details. A parcel spends 7–21 working days in '
                                          'transit, so it makes sense to plan ahead.\n'
                                          '\n'
                                          'A paediatrician decides the dose for a child according to the '
                                          'leaflet, taking age and weight into account. Some products are '
                                          'prescription-only, as marked on the product page, and the rules '
                                          'for them vary by medicine and country. Read the leaflet and '
                                          'consult a paediatrician before giving any medicine to a child.'}},
 'varikoz': {'ru': {'name': 'Для вен: варикоз',
                    'h1': 'Турецкие препараты для вен: таблетки, кремы и гели',
                    'meta_title': 'Турецкие препараты для вен и при варикозе | Mudaroba',
                    'meta_description': 'Средства при варикозе из Турции: таблетки DAFLON (диосмин + '
                                        'гесперидин), крем и гель HIRUDOID FORTE. Заявка, проверка наличия, '
                                        'доставка 7–21 рабочий день.',
                    'seo_text': 'Подборка входит в раздел сердечно-сосудистых препаратов и объединяет две '
                                'группы АТХ: C05B — средства при варикозном расширении вен для наружного и '
                                'системного применения и C05C — капилляростабилизирующие препараты. Здесь '
                                'собраны турецкие препараты для вен в таблетках, кремах и гелях.\n'
                                '\n'
                                'Среди турецких таблеток для вен — DAFLON (диосмин + гесперидин): его '
                                'назначают при хронической венозной недостаточности, когда беспокоят тяжесть '
                                'и отёки ног, по показаниям из инструкции. Наружные формы представлены, '
                                'например, HIRUDOID FORTE (мукополисахарида полисульфат) — это крем и гель, '
                                'которые часто ищут как турецкую мазь от вен. В карточке каждого препарата '
                                'указаны действующее вещество, форма и объём упаковки.\n'
                                '\n'
                                'Турецкое лекарство для вен заказывают через заявку: менеджер уточнит '
                                'наличие таблеток, крема или геля и сообщит расчёт с доставкой в Россию, '
                                'Казахстан или Узбекистан. Срок международной отправки — 7–21 рабочий день.\n'
                                '\n'
                                'Часть препаратов рецептурная, это указано в карточке; что потребуется для '
                                'отправки, зависит от препарата и страны, куда идёт посылка. Причину отёков '
                                'и состояние вен оценивает врач, поэтому перед применением любого турецкого '
                                'препарата для вен прочитайте инструкцию и обсудите назначение с '
                                'флебологом.'},
             'en': {'name': 'Veins & Varicose',
                    'h1': 'Turkish Vein Medicines: Tablets, Creams and Gels',
                    'meta_title': 'Turkish Vein & Varicose Medicines | Mudaroba',
                    'meta_description': 'Medicines for varicose veins from Turkey: DAFLON tablets (diosmin + '
                                        'hesperidin) and HIRUDOID FORTE cream and gel. Send a request; '
                                        'delivery in 7–21 working days.',
                    'seo_text': 'This collection is part of the Cardiovascular section and covers two ATC '
                                'groups: C05B, products for varicose veins for topical and systemic use, and '
                                'C05C, capillary-stabilising agents. It brings together Turkish vein '
                                'medicines as tablets, creams and gels.\n'
                                '\n'
                                'Turkish vein tablets include DAFLON (diosmin + hesperidin), prescribed for '
                                'chronic venous insufficiency with heavy, swollen legs according to the '
                                'indications in the leaflet. Topical options include HIRUDOID FORTE '
                                '(mucopolysaccharide polysulfate), available as a cream and as a gel.\n'
                                '\n'
                                'To order, leave a request: a manager checks whether the tablets, cream or '
                                'gel are available and works out the cost with delivery to Russia, '
                                'Kazakhstan or Uzbekistan. International shipping takes 7–21 working days.\n'
                                '\n'
                                'Some products are prescription-only, as marked on the product page, and '
                                'what is needed for shipping depends on the medicine and the destination '
                                'country. Leg swelling can have different causes, and only a doctor can '
                                'assess the state of your veins, so read the leaflet and talk to a vein '
                                'specialist before using any of these medicines.'}},
 'ot-psoriaza': {'ru': {'name': 'От псориаза',
                        'h1': 'Турецкая мазь от псориаза и другие средства',
                        'meta_title': 'Турецкая мазь от псориаза с кальципотриолом | Mudaroba',
                        'meta_description': 'Антипсориатические препараты из Турции: мазь, крем и раствор '
                                            'для кожи головы с кальципотриолом, комбинации с бетаметазоном, '
                                            'капсулы. Заявка и доставка 7–21 рабочий день.',
                        'seo_text': 'В подборке — антипсориатические препараты из турецких аптек, группа D05 '
                                    'по классификации АТХ. Если вы ищете, какая турецкая мазь от псориаза '
                                    'есть в каталоге, здесь собраны наружные средства с кальципотриолом, его '
                                    'комбинации с кортикостероидом бетаметазоном, а также системный препарат '
                                    'для приёма внутрь.\n'
                                    '\n'
                                    '## Мази, крем и капсулы\n'
                                    '\n'
                                    'Кальципотриол выпускается в нескольких формах: мазь, крем и раствор для '
                                    'кожи головы — например, PSORCUTAN (кальципотриол). В комбинированных '
                                    'мазях он сочетается с бетаметазоном: PSORCUTAN BETA и PSOCAL BETA '
                                    '(кальципотриол + бетаметазон). Капсулы NEOTIGASON (ацитретин) — '
                                    'системный ретиноид, его назначает только дерматолог. Каждая турецкая '
                                    'мазь от псориаза подписана латиницей, как на упаковке в аптеках Турции, '
                                    'а в карточке товара указаны действующее вещество, форма, дозировка и '
                                    'инструкция.\n'
                                    '\n'
                                    'Турецкие препараты от псориаза заказывают через заявку на сайте. '
                                    'Менеджер проверяет наличие у турецких поставщиков, рассчитывает '
                                    'стоимость вместе с доставкой и согласует с вами детали. Международная '
                                    'посылка идёт 7–21 рабочий день — в Россию, Казахстан и Узбекистан.\n'
                                    '\n'
                                    'Крем или мазь от псориаза из Турции — такое же лекарственное средство, '
                                    'как и капсулы, со своими противопоказаниями. Рецептурные позиции '
                                    'отмечены в карточке: для них может потребоваться рецепт врача, '
                                    'требования зависят от препарата и страны доставки. Перед применением '
                                    'внимательно прочитайте инструкцию и обсудите препарат с дерматологом.'},
                 'en': {'name': 'Psoriasis',
                        'h1': 'Turkish Psoriasis Ointments, Creams and Capsules',
                        'meta_title': 'Turkish Psoriasis Ointment with Calcipotriol | Mudaroba',
                        'meta_description': 'Psoriasis medicines from Turkey: calcipotriol ointment, cream '
                                            'and scalp solution, combinations with betamethasone and oral '
                                            'capsules. Order by request, delivery in 7–21 working days.',
                        'seo_text': 'This collection brings together antipsoriatic medicines from Turkish '
                                    'pharmacies, ATC group D05. If you are looking for a Turkish psoriasis '
                                    'ointment, here you will find topical calcipotriol products, '
                                    'calcipotriol combined with the corticosteroid betamethasone, and one '
                                    'oral option.\n'
                                    '\n'
                                    '## Ointments, cream and capsules\n'
                                    '\n'
                                    'Calcipotriol comes as an ointment, a cream and a scalp solution, for '
                                    'example PSORCUTAN (calcipotriol). Combination ointments pair it with '
                                    'betamethasone: PSORCUTAN BETA and PSOCAL BETA (calcipotriol + '
                                    'betamethasone). NEOTIGASON (acitretin) capsules are a systemic retinoid '
                                    'prescribed only by a dermatologist. Every Turkish psoriasis ointment in '
                                    'the collection keeps its Turkish name exactly as printed on the pack, '
                                    'and the product page shows the active ingredient, form, strength and '
                                    'patient leaflet.\n'
                                    '\n'
                                    'Psoriasis medicines from Turkey are ordered through a request rather '
                                    'than a checkout. A manager confirms availability with Turkish '
                                    'suppliers, calculates the total cost including shipping and agrees the '
                                    'details with you. International delivery takes 7–21 working days, with '
                                    'shipping to Russia, Kazakhstan and Uzbekistan.\n'
                                    '\n'
                                    'Creams and ointments are medicines just like capsules and have their '
                                    'own contraindications. Prescription-only items are marked on the '
                                    "product page; a doctor's prescription may be required depending on the "
                                    'medicine and the destination country, and nothing is shipped in breach '
                                    'of local rules. Read the leaflet carefully and discuss any product with '
                                    'your dermatologist before use.'}},
 'protivogribkovye': {'ru': {'name': 'Противогрибковые',
                             'h1': 'Противогрибковые из Турции: от грибка ногтей и кожи',
                             'meta_title': 'Противогрибковые из Турции: от грибка ногтей | Mudaroba',
                             'meta_description': 'Противогрибковые препараты из Турции для ногтей и кожи: '
                                                 'лаки с аморолфином и циклопироксом, крем с клотримазолом, '
                                                 'таблетки с тербинафином. Оформление через заявку, доставка '
                                                 'за 7–21 рабочий день.',
                             'seo_text': 'Подборка противогрибковых препаратов для кожи и ногтей из турецких '
                                         'аптек — группа D01 по классификации АТХ. Если вам нужно средство '
                                         'от грибка ногтей из Турции, здесь собраны лаки для ногтей, кремы, '
                                         'спреи, шампуни и таблетки с разными действующими веществами: '
                                         'аморолфином, циклопироксом, тербинафином, клотримазолом и '
                                         'другими.\n'
                                         '\n'
                                         '## Лаки, кремы и таблетки\n'
                                         '\n'
                                         'Лак от грибка ногтей из Турции представлен, например, LOCERYL '
                                         '(аморолфин) и MICLAST (циклопирокс). Для кожи есть крем CANESTEN '
                                         '(клотримазол) и другие наружные формы — спреи, растворы, шампуни. '
                                         'Таблетки TERBISIL (тербинафин) — системное средство, его назначает '
                                         'врач. Турецкая мазь от грибка или крем в каталоге сопровождаются '
                                         'карточкой с действующим веществом, формой, дозировкой и '
                                         'инструкцией.\n'
                                         '\n'
                                         'Препараты от грибка ногтей из Турции заказывают через заявку: '
                                         'менеджер проверит, есть ли нужная позиция у поставщиков, сообщит '
                                         'итоговую сумму с доставкой и свяжется с вами для согласования. '
                                         'Срок международной доставки — 7–21 рабочий день.\n'
                                         '\n'
                                         'Отметка о рецептурном статусе есть в карточке товара, а '
                                         'потребуется ли рецепт, определяется препаратом и правилами страны '
                                         'доставки. Изучите инструкцию и покажите кожу или ногти врачу: '
                                         'грибковое поражение важно подтвердить до начала применения любого '
                                         'средства.'},
                      'en': {'name': 'Antifungals',
                             'h1': 'Turkish Antifungals for Nail and Skin Fungus',
                             'meta_title': 'Turkish Nail Fungus Lacquers & Antifungals | Mudaroba',
                             'meta_description': 'Antifungal medicines from Turkey for nails and skin: '
                                                 'amorolfine and ciclopirox nail lacquers, clotrimazole '
                                                 'cream, terbinafine tablets. Request-based ordering with '
                                                 'delivery in 7–21 working days.',
                             'seo_text': 'This collection covers antifungal medicines for skin and nails '
                                         'from Turkish pharmacies, ATC group D01. If you need a nail fungus '
                                         'product from Turkey, you will find medicated nail lacquers, '
                                         'creams, sprays, shampoos and tablets based on amorolfine, '
                                         'ciclopirox, terbinafine, clotrimazole and other active '
                                         'ingredients.\n'
                                         '\n'
                                         '## Lacquers, creams and tablets\n'
                                         '\n'
                                         'Turkish nail fungus lacquers include LOCERYL (amorolfine) and '
                                         'MICLAST (ciclopirox). For the skin there is CANESTEN '
                                         '(clotrimazole) cream, along with sprays, solutions and shampoos. '
                                         'TERBISIL (terbinafine) tablets act systemically and are prescribed '
                                         'by a doctor. Each antifungal cream or ointment has a product page '
                                         'listing the active ingredient, form, strength and leaflet.\n'
                                         '\n'
                                         'Antifungals from Turkey are ordered through a request: a manager '
                                         'checks whether the item is available from suppliers, works out the '
                                         'cost including shipping and contacts you to agree the details. '
                                         'International delivery takes 7–21 working days.\n'
                                         '\n'
                                         'The product page shows whether an item is prescription-only, and '
                                         'whether a prescription will be needed depends on the medicine and '
                                         'the rules of the destination country. Read the leaflet and have '
                                         'your nails or skin examined by a doctor before use, since a fungal '
                                         'infection should be confirmed first.'}},
 'ginekologiya': {'ru': {'name': 'Гинекология и контрацепция',
                         'h1': 'Турецкие свечи от молочницы, контрацепция, средства при климаксе',
                         'meta_title': 'Турецкие свечи от молочницы и контрацепция | Mudaroba',
                         'meta_description': 'Гинекологические препараты из Турции: вагинальные свечи при '
                                             'молочнице, противозачаточные таблетки, внутриматочная система, '
                                             'средства при климаксе. Подбор через менеджера, доставка 7–21 '
                                             'рабочий день.',
                         'seo_text': 'В подборке — гинекологические и гормональные препараты из турецких '
                                     'аптек, группы G01, G02 и G03 по классификации АТХ. Здесь можно найти '
                                     'турецкие свечи от молочницы и другие вагинальные формы, '
                                     'противозачаточные таблетки и внутриматочные системы, а также '
                                     'препараты, которые назначают при климаксе.\n'
                                     '\n'
                                     '## Вагинальные формы и гормональные средства\n'
                                     '\n'
                                     'Турецкие вагинальные свечи (овули) представлены, например, '
                                     'MIKO-PENOTRAN (миконазол) — противогрибковым средством, которое по '
                                     'инструкции применяют при вагинальном кандидозе, — и NEO-PENOTRAN '
                                     '(метронидазол + миконазол) с комбинированным составом. '
                                     'Противозачаточные таблетки в Турции выпускаются с разными сочетаниями '
                                     'эстрогена и прогестагена, например MICROGYNON (этинилэстрадиол + '
                                     'левоноргестрел). Есть и внутриматочная система MIRENA '
                                     '(левоноргестрел). При климаксе гинеколог может назначить '
                                     'заместительную гормональную терапию — к ней относится, например, гель '
                                     'FEMIJEL (эстрадиол).\n'
                                     '\n'
                                     'Когда нужны турецкие свечи от молочницы или таблетки при климаксе, '
                                     'достаточно отправить заявку. Дальше менеджер выясняет наличие у '
                                     'турецких дистрибьюторов, готовит расчёт стоимости и доставки и '
                                     'согласует детали; в пути посылка 7–21 рабочий день.\n'
                                     '\n'
                                     'Гормональные контрацептивы и средства при климаксе подбирает только '
                                     'врач с учётом противопоказаний. Для рецептурных средств (они помечены '
                                     'в карточке) может понадобиться рецепт — это зависит от препарата и '
                                     'страны, куда идёт посылка. Внимательно изучите инструкцию и обсудите '
                                     'применение с гинекологом.'},
                  'en': {'name': 'Gynaecology & Contraception',
                         'h1': 'Turkish Thrush Pessaries, Contraceptives and Menopause Medicines',
                         'meta_title': 'Turkish Thrush Pessaries & Contraception | Mudaroba',
                         'meta_description': 'Gynaecological medicines from Turkey: vaginal pessaries for '
                                             'thrush, contraceptive pills, a hormonal intrauterine system '
                                             'and menopause medicines. Ordered via a manager, delivered in '
                                             '7–21 working days.',
                         'seo_text': 'This collection gathers gynaecological and hormonal medicines from '
                                     'Turkish pharmacies, ATC groups G01, G02 and G03. It includes Turkish '
                                     'thrush pessaries and other vaginal forms, contraceptive pills and '
                                     'intrauterine systems, as well as medicines prescribed during '
                                     'menopause.\n'
                                     '\n'
                                     '## Vaginal forms and hormonal products\n'
                                     '\n'
                                     'Vaginal pessaries include MIKO-PENOTRAN (miconazole), an antifungal '
                                     'indicated for vaginal candidiasis, and NEO-PENOTRAN (metronidazole + '
                                     'miconazole) with a combined formula. Contraceptive pills from Turkey '
                                     'come with different estrogen and progestogen combinations, for example '
                                     'MICROGYNON (ethinylestradiol + levonorgestrel). The catalogue also '
                                     'lists the MIRENA intrauterine system (levonorgestrel). For menopause '
                                     'symptoms a gynaecologist may prescribe hormone replacement therapy '
                                     'such as FEMIJEL (estradiol) gel.\n'
                                     '\n'
                                     'When you need Turkish thrush pessaries or menopause tablets, simply '
                                     'send a request. A manager then checks availability with Turkish '
                                     'distributors, prepares a quote for the medicine and shipping, and '
                                     'agrees the details; the parcel spends 7–21 working days in transit.\n'
                                     '\n'
                                     'Hormonal contraceptives and menopause medicines are chosen only by a '
                                     'doctor, taking contraindications into account. Prescription-only items '
                                     'are flagged on the product page and may require a prescription, '
                                     'depending on the medicine and the country the parcel is going to. Go '
                                     'through the leaflet and talk to your gynaecologist before starting any '
                                     'of these products.'}},
 'ukoly': {'ru': {'name': 'Уколы и ампулы',
                  'h1': 'Уколы и ампулы из Турции: D3, диклофенак, мелоксикам',
                  'meta_title': 'Уколы и ампулы из Турции: D3, диклофенак | Mudaroba',
                  'meta_description': 'Инъекционные препараты из Турции: колекальциферол (D3) в ампулах, '
                                      'диклофенак и мелоксикам в уколах, растворы во флаконах, шприц-ручки. '
                                      'Заявка, расчёт стоимости, доставка 7–21 рабочий день.',
                  'seo_text': 'В подборке собраны препараты для инъекций из разных разделов каталога: '
                              'ампулы, флаконы, картриджи и шприц-ручки. Сюда входят противовоспалительные и '
                              'обезболивающие, антибиотики, инсулины, ноотропы и другие средства из турецких '
                              'аптек — их объединяет только способ введения. Один из частых запросов — '
                              'колекальциферол (D3) в ампулах.\n'
                              '\n'
                              '## D3 в уколах и другие примеры\n'
                              '\n'
                              'Турецкий укол D3 — это, например, DEVIT-3 (колекальциферол): раствор в '
                              'ампулах для внутримышечного введения и приёма внутрь. Диклофенак в уколах '
                              'представлен препаратом DIKLORON (диклофенак) в ампулах для внутримышечного '
                              'введения. Мелоксикам в ампулах — ZELOXIM и LOXIDOL (мелоксикам). Также в '
                              'подборке есть шприц-ручки и картриджи с инсулином, антибиотики во флаконах и '
                              'растворы для инфузий. В карточке каждого товара указаны действующее вещество, '
                              'дозировка, способ введения и инструкция.\n'
                              '\n'
                              'Чтобы получить препарат для инъекций, отправьте заявку. Менеджер уточнит, '
                              'есть ли нужная дозировка и упаковка, подготовит расчёт стоимости и доставки и '
                              'согласует с вами отправку; срок в пути — 7–21 рабочий день, доставка возможна '
                              'в Россию, Казахстан и Узбекистан.\n'
                              '\n'
                              'Инъекции назначает врач, а выполняет, как правило, медицинский работник. '
                              'Многие инъекционные позиции рецептурные — это отмечено в карточке, а '
                              'требования к рецепту зависят от препарата и страны. Инструкцию к любому '
                              'препарату, в том числе к колекальциферолу в ампулах, стоит прочитать заранее, '
                              'а назначение — обсудить с врачом.'},
           'en': {'name': 'Injections & Ampoules',
                  'h1': 'Injections and Ampoules from Turkey: D3, Diclofenac, Meloxicam',
                  'meta_title': 'Turkish Injections & Ampoules: D3, Diclofenac | Mudaroba',
                  'meta_description': 'Injectable medicines from Turkey: cholecalciferol (D3) ampoules, '
                                      'diclofenac and meloxicam injections, vials and pre-filled pens. '
                                      'Request, quote and delivery in 7–21 working days.',
                  'seo_text': 'This collection brings together injectable medicines from different sections '
                              'of the catalog: ampoules, vials, cartridges and pre-filled pens. It includes '
                              'anti-inflammatory and pain medicines, antibiotics, insulins, nootropics and '
                              'other products from Turkish pharmacies; what they share is the route of '
                              'administration. A frequent request is cholecalciferol (D3) in ampoules.\n'
                              '\n'
                              '## D3 injections and other examples\n'
                              '\n'
                              'A Turkish D3 injection is, for example, DEVIT-3 (cholecalciferol), a solution '
                              'in ampoules for intramuscular or oral use. Diclofenac injections include '
                              'DIKLORON (diclofenac) ampoules for intramuscular use. Meloxicam ampoules are '
                              'represented by ZELOXIM and LOXIDOL (meloxicam). The collection also includes '
                              'insulin pens and cartridges, antibiotics in vials and infusion solutions. '
                              'Each product page lists the active ingredient, strength, route of '
                              'administration and leaflet.\n'
                              '\n'
                              'To get an injectable medicine, send a request. A manager checks whether the '
                              'required strength and pack size are available, prepares a quote for the '
                              'medicine and shipping and agrees the dispatch with you; transit takes 7–21 '
                              'working days, with delivery to Russia, Kazakhstan and Uzbekistan.\n'
                              '\n'
                              'Injections are prescribed by a doctor and are usually given by a nurse or '
                              'another medical professional. Many injectables are prescription-only (look '
                              'for the mark on the product page), and prescription requirements depend on '
                              'the medicine and the country. Check the leaflet in advance and discuss the '
                              'prescription with your doctor, including for cholecalciferol ampoules.'}},
 'ot-gemorroya': {'ru': {'name': 'От геморроя',
                         'h1': 'Турецкие свечи и мази от геморроя',
                         'meta_title': 'Турецкие свечи и мази от геморроя | Mudaroba',
                         'meta_description': 'Свечи, мази и кремы от геморроя из турецких аптек: PROCTOLOG, '
                                             'PROCTO-GLYVENOL, ULTRAPROCT. Оставьте заявку — менеджер '
                                             'проверит наличие и рассчитает доставку.',
                         'seo_text': 'В подборке собраны турецкие свечи от геморроя, а также мази и кремы, '
                                     'которые применяют местно — наружно или ректально. По классификации АТХ '
                                     'это группа C05A. Названия в каталоге турецкие, латиницей — так, как '
                                     'они напечатаны на упаковке.\n'
                                     '\n'
                                     '## Что входит в подборку\n'
                                     '\n'
                                     'Составы различаются: в одних препаратах местный анестетик сочетается с '
                                     'веществом, влияющим на тонус вен, в других — с кортикостероидом. '
                                     'Примеры из каталога: PROCTOLOG (рускогенины + тримебутин) — свечи и '
                                     'ректальный крем; PROCTO-GLYVENOL (трибенозид + лидокаин) — '
                                     'суппозитории и крем; ULTRAPROCT (флуокортолон + цинхокаин) — свечи и '
                                     'мазь. Турецкая мазь от геморроя и свечи одного бренда часто стоят '
                                     'рядом, поэтому форму выпуска удобно сверить в карточке: там же указаны '
                                     'действующее вещество, дозировка и инструкция.\n'
                                     '\n'
                                     '## Как оформить заказ\n'
                                     '\n'
                                     'Выберите препарат и отправьте заявку. Менеджер проверит, есть ли он в '
                                     'турецких аптеках или у дистрибьюторов, рассчитает стоимость вместе с '
                                     'доставкой и согласует детали. Посылки в Россию, Казахстан и Узбекистан '
                                     'идут 7–21 рабочий день.\n'
                                     '\n'
                                     'Если турецкий препарат от геморроя рецептурный, это отмечено в '
                                     'карточке. Требования к рецепту зависят от препарата и страны '
                                     'получателя, а правила страны при отправке не обходятся. Перед '
                                     'применением прочитайте инструкцию и обсудите средство с врачом: '
                                     'турецкие свечи от геморроя, как и другие местные средства, имеют '
                                     'противопоказания.'},
                  'en': {'name': 'Haemorrhoids',
                         'h1': 'Turkish Haemorrhoid Suppositories and Ointments',
                         'meta_title': 'Turkish Haemorrhoid Suppositories & Ointments | Mudaroba',
                         'meta_description': 'Haemorrhoid suppositories, ointments and creams from Turkish '
                                             'pharmacies, including PROCTOLOG, PROCTO-GLYVENOL and '
                                             'ULTRAPROCT. A manager checks availability and delivery.',
                         'seo_text': 'This collection brings together Turkish haemorrhoid suppositories, '
                                     'ointments and creams for local use, classified under ATC group C05A. '
                                     'Product names are shown in Turkish, exactly as printed on the pack, '
                                     'and each card lists the active ingredient, strength, dosage form and '
                                     'patient leaflet.\n'
                                     '\n'
                                     '## What you will find here\n'
                                     '\n'
                                     'Formulations vary: some combine a local anaesthetic with a venotonic '
                                     'substance, others pair it with a corticosteroid. Examples from the '
                                     'catalogue include PROCTOLOG (ruscogenins + trimebutine) as '
                                     'suppositories and a rectal cream, PROCTO-GLYVENOL (tribenoside + '
                                     'lidocaine) as suppositories and a cream, and ULTRAPROCT (fluocortolone '
                                     '+ cinchocaine) as suppositories and an ointment. The same brand often '
                                     'comes in more than one form, so check the card before you send a '
                                     'request.\n'
                                     '\n'
                                     '## Ordering from Turkey\n'
                                     '\n'
                                     'Submit a request for the product you need. A manager confirms '
                                     'availability with Turkish pharmacies or distributors, calculates the '
                                     'cost including shipping and agrees the details with you. International '
                                     'delivery takes 7–21 business days.\n'
                                     '\n'
                                     'Prescription-only items are marked on the product card. Whether a '
                                     'prescription is needed depends on the medicine and the destination '
                                     'country, and nothing is shipped against local rules. Please read the '
                                     'leaflet and talk to your doctor before using any of these products.'}},
 'spreyi': {'ru': {'name': 'Спреи',
                   'h1': 'Турецкие спреи: назальные, для горла и для кожи',
                   'meta_title': 'Турецкие спреи: назальные, для горла и кожи | Mudaroba',
                   'meta_description': 'Назальные спреи, спреи для горла и полости рта, для кожи из турецких '
                                       'аптек: TANTUM VERDE, MOMECON, DYMISTA. Заявка, проверка наличия и '
                                       'доставка через менеджера.',
                   'seo_text': 'В этой подборке собраны турецкие спреи из разных групп АТХ — объединяет их '
                               'только форма выпуска. Здесь есть назальные спреи, спреи для горла и полости '
                               'рта, а также растворы для нанесения на кожу. Название каждого товара '
                               'приведено латиницей, как на турецкой упаковке, а в карточке указаны '
                               'действующее вещество, дозировка и инструкция.\n'
                               '\n'
                               '## Какие спреи есть в каталоге\n'
                               '\n'
                               'Для полости рта и горла — TANTUM VERDE (бензидамин): турецкий спрей Тантум '
                               'Верде представлен в виде орального спрея, рядом есть и раствор для '
                               'полоскания. Назальные спреи с глюкокортикостероидами выпускают несколько '
                               'турецких производителей, например MOMECON (мометазон); если нужен турецкий '
                               'спрей с мометазоном, ориентируйтесь на действующее вещество в карточке. Есть '
                               'и комбинированный назальный спрей DYMISTA (азеластин + флутиказон). Для кожи '
                               '— CANOLEN (циклопирокс), противогрибковый раствор в форме спрея.\n'
                               '\n'
                               '## Заявка и доставка\n'
                               '\n'
                               'Спрей добавляется в заявку, после чего менеджер уточняет наличие в Турции, '
                               'считает стоимость вместе с доставкой и связывается с вами. Отправления в '
                               'Россию, Казахстан и Узбекистан доставляются за 7–21 рабочий день.\n'
                               '\n'
                               'Если препарат рецептурный, об этом сказано в карточке; нужен ли рецепт, '
                               'зависит от препарата и страны доставки, и правила этой страны соблюдаются. '
                               'Турецкие спреи, даже привычные по названию, могут отличаться составом от '
                               'знакомых аналогов, поэтому перед применением изучите инструкцию и '
                               'посоветуйтесь с врачом.'},
            'en': {'name': 'Sprays',
                   'h1': 'Turkish Sprays: Nasal, Throat and Skin',
                   'meta_title': 'Turkish Nasal, Throat & Skin Sprays | Mudaroba',
                   'meta_description': 'Nasal, throat and skin sprays from Turkish pharmacies, including '
                                       'TANTUM VERDE, MOMECON and DYMISTA. Send a request: a manager checks '
                                       'availability, cost and delivery.',
                   'seo_text': 'Turkish sprays from several ATC groups are gathered here because they share '
                               'one dosage form: nasal sprays, throat and mouth sprays, and solutions '
                               'applied to the skin. Every product card shows the active ingredient, '
                               'strength and patient leaflet, with the name printed in Turkish as on the '
                               'box.\n'
                               '\n'
                               '## Sprays in the catalogue\n'
                               '\n'
                               'For the mouth and throat there is TANTUM VERDE (benzydamine), available as '
                               'an oral spray alongside a gargle. Corticosteroid nasal sprays come from '
                               'several Turkish manufacturers: MOMECON (mometasone) is one example, and '
                               'searching by active ingredient makes other mometasone sprays easy to find. '
                               'DYMISTA (azelastine + fluticasone) is a combined nasal spray, while CANOLEN '
                               '(ciclopirox) is an antifungal spray solution for the skin.\n'
                               '\n'
                               '## How ordering works\n'
                               '\n'
                               'Send a request with the spray you need. A manager checks whether it is in '
                               'stock in Turkey, works out the price with shipping and gets back to you. '
                               'Parcels to Russia, Kazakhstan and Uzbekistan arrive in 7–21 business days.\n'
                               '\n'
                               'Prescription status is shown on each card, and requirements depend on the '
                               'medicine and the destination country; nothing is sent in breach of local '
                               'rules. A familiar brand name may hide a different formulation in Turkey, so '
                               'read the leaflet and check with your doctor before use.'}},
 'kapli': {'ru': {'name': 'Капли',
                  'h1': 'Турецкие капли: глазные, назальные, ушные и для приёма внутрь',
                  'meta_title': 'Турецкие капли: глазные, ушные, назальные, оральные | Mudaroba',
                  'meta_description': 'Глазные, ушные, назальные и оральные капли из турецких аптек: AZOPT, '
                                      'OTIPAX, ZYRTEC, VALIDOL. Оформите заявку — менеджер проверит наличие '
                                      'и посчитает доставку.',
                  'seo_text': 'Турецкие капли в этой подборке объединены по форме выпуска, а не по '
                              'назначению: здесь глазные, ушные и назальные капли, а также растворы для '
                              'приёма внутрь. Среди глазных капель — средства при повышенном внутриглазном '
                              'давлении, противовоспалительные и антибактериальные растворы; среди ушных — '
                              'комбинации антибиотика с кортикостероидом. Действующее вещество, дозировка и '
                              'инструкция указаны в карточке каждого товара.\n'
                              '\n'
                              'Примеры из каталога: AZOPT (бринзоламид) — глазные капли; OTIPAX (феназон + '
                              'лидокаин) — ушные капли; ZYRTEC (цетиризин) — капли для приёма внутрь. Есть и '
                              'VALIDOL (гидроксизин): обратите внимание, что состав турецкого VALIDOL '
                              'отличается от одноимённого средства, привычного в России и СНГ.\n'
                              '\n'
                              '## Как заказать капли из Турции\n'
                              '\n'
                              'Отправьте заявку на нужный флакон. Менеджер уточнит наличие, рассчитает '
                              'стоимость и доставку, а затем согласует с вами детали. Международная доставка '
                              'в Россию, Казахстан и Узбекистан длится 7–21 рабочий день.\n'
                              '\n'
                              'Рецептурные турецкие капли отмечены в карточке; потребуется ли рецепт, '
                              'зависит от препарата и страны получения. Условия хранения и срок годности '
                              'после вскрытия флакона приведены в инструкции. Прочитайте её перед '
                              'применением и проконсультируйтесь с врачом.'},
           'en': {'name': 'Drops',
                  'h1': 'Turkish Drops: Eye, Ear, Nasal and Oral',
                  'meta_title': 'Turkish Eye, Ear, Nasal & Oral Drops | Mudaroba',
                  'meta_description': 'Eye, ear, nasal and oral drops from Turkish pharmacies, such as '
                                      'AZOPT, OTIPAX, ZYRTEC and VALIDOL. Request a product and a manager '
                                      'checks availability and shipping.',
                  'seo_text': 'This collection groups Turkish drops by dosage form rather than by use: eye '
                              'drops, ear drops, nasal drops and oral solutions all sit here together. Each '
                              'card lists the active ingredient, strength and patient leaflet.\n'
                              '\n'
                              'Examples from the catalogue: AZOPT (brinzolamide) eye drops, OTIPAX '
                              '(phenazone + lidocaine) ear drops and ZYRTEC (cetirizine) oral drops. The '
                              'Turkish VALIDOL (hydroxyzine) is listed too; note that its composition '
                              'differs from the product known by the same name in Russia and other CIS '
                              'countries.\n'
                              '\n'
                              '## Ordering drops from Turkey\n'
                              '\n'
                              'Send a request for the bottle you need. A manager checks availability, '
                              'calculates the price and delivery, then confirms the details with you. '
                              'International shipping takes 7–21 business days.\n'
                              '\n'
                              'Prescription-only drops are marked on the card, and whether a prescription is '
                              'required depends on the product and the destination country. Storage '
                              'conditions and shelf life after opening are given in the leaflet; read it '
                              'carefully and consult a doctor before use.'}},
 'siropy': {'ru': {'name': 'Сиропы',
                   'h1': 'Турецкие сиропы для детей и взрослых',
                   'meta_title': 'Турецкие сиропы: ибупрофен, от кашля и простуды | Mudaroba',
                   'meta_description': 'Детские и взрослые сиропы из Турции: PEDITUS, PEDIFEN и IBUFEN с '
                                       'ибупрофеном, ASIST. Отправьте заявку — менеджер проверит наличие, '
                                       'рассчитает стоимость и доставку.',
                   'seo_text': 'Турецкие сиропы собраны здесь по форме выпуска. Жидкую форму выбирают, когда '
                               'таблетку проглотить сложно, поэтому многие позиции выпускаются в '
                               'педиатрической концентрации. В подборке — жаропонижающие и обезболивающие '
                               'сиропы, средства при кашле и комбинированные препараты от простуды. Названия '
                               'даны латиницей, как на упаковке, а в карточке указаны действующее вещество, '
                               'концентрация и инструкция.\n'
                               '\n'
                               '## Примеры из каталога\n'
                               '\n'
                               'Турецкий сироп с ибупрофеном представлен несколькими брендами — например, '
                               'PEDIFEN (ибупрофен) и IBUFEN (ибупрофен) в педиатрической форме. PEDITUS — '
                               'комбинированный сироп от простуды (парацетамол, гвайфенезин, фенилэфрин и '
                               'другие компоненты); полный состав и показания приведены в карточке и '
                               'инструкции. ASIST (ацетилцистеин) выпускается в том числе в виде гранул для '
                               'приготовления сиропа.\n'
                               '\n'
                               '## Как оформить заявку\n'
                               '\n'
                               'Добавьте сироп в заявку — менеджер проверит наличие у турецких '
                               'дистрибьюторов, рассчитает стоимость с доставкой и согласует с вами детали '
                               'заказа. Доставка в Россию, Казахстан и Узбекистан занимает 7–21 рабочий '
                               'день.\n'
                               '\n'
                               'Рецептурные препараты отмечены в карточке, а необходимость рецепта зависит '
                               'от препарата и страны доставки. Детские турецкие сиропы различаются '
                               'концентрацией действующего вещества даже внутри одного бренда, поэтому перед '
                               'применением прочитайте инструкцию и проконсультируйтесь с педиатром или '
                               'терапевтом.'},
            'en': {'name': 'Syrups',
                   'h1': 'Turkish Syrups for Children and Adults',
                   'meta_title': 'Turkish Syrups: Ibuprofen, Cough & Cold | Mudaroba',
                   'meta_description': "Children's and adult syrups from Turkey, including PEDITUS, "
                                       'ibuprofen syrups PEDIFEN and IBUFEN, and ASIST. Send a request and a '
                                       'manager checks stock, cost and delivery.',
                   'seo_text': 'Turkish syrups are grouped here by dosage form. A liquid is often chosen '
                               'when tablets are hard to swallow, which is why many of these products come '
                               'in paediatric strengths. The collection covers fever and pain syrups, cough '
                               'remedies and combined cold medicines. Names appear in Turkish as on the '
                               'pack, and each card lists the active ingredient, concentration and patient '
                               'leaflet.\n'
                               '\n'
                               '## Examples from the catalogue\n'
                               '\n'
                               'Ibuprofen syrup from Turkey is available under several brands, such as '
                               'PEDIFEN (ibuprofen) and IBUFEN (ibuprofen) in paediatric form. PEDITUS is a '
                               'combined cold syrup (paracetamol, guaifenesin, phenylephrine and other '
                               'components); the full composition and indications are on the card and in the '
                               'leaflet. ASIST (acetylcysteine) is also offered as granules for preparing a '
                               'syrup.\n'
                               '\n'
                               '## Placing a request\n'
                               '\n'
                               'Add the syrup to your request and a manager will check availability with '
                               'Turkish distributors, calculate the cost including delivery and confirm the '
                               'order details. Delivery to Russia, Kazakhstan and Uzbekistan takes 7–21 '
                               'business days.\n'
                               '\n'
                               'Prescription-only items are flagged on the card, and requirements depend on '
                               'the medicine and the destination country. Concentrations can differ even '
                               'within one brand, so read the leaflet and consult a paediatrician or GP '
                               'before use.'}},
 'svechi': {'ru': {'name': 'Свечи',
                   'h1': 'Турецкие свечи: ректальные и вагинальные суппозитории',
                   'meta_title': 'Турецкие свечи — ректальные и вагинальные | Mudaroba',
                   'meta_description': 'Ректальные и вагинальные свечи из турецких аптек: с ибупрофеном, '
                                       'парацетамолом, от геморроя. Заявка через менеджера: проверка '
                                       'наличия, расчёт стоимости и доставка.',
                   'seo_text': 'Турецкие свечи (суппозитории) собраны в одну подборку по форме выпуска. '
                               'Ректальные свечи встречаются среди жаропонижающих, обезболивающих и '
                               'слабительных средств, а также препаратов от геморроя; вагинальные — среди '
                               'антисептиков. Ректальную форму нередко назначают маленьким детям или в '
                               'ситуациях, когда приём таблеток затруднён. Состав, дозировка и инструкция '
                               'указаны в карточке каждого товара.\n'
                               '\n'
                               'Примеры из каталога: IBU-BABY (ибупрофен) — турецкие свечи с ибупрофеном для '
                               'детей; PARANOX S (парацетамол); PROCTOLOG (рускогенины + тримебутин) и '
                               'ULTRAPROCT (флуокортолон + цинхокаин) — свечи от геморроя; BIOKADIN VAG '
                               '(повидон-йод) — вагинальные суппозитории. Одно и то же действующее вещество '
                               'может выпускаться в свечах разной дозировки, поэтому сверяйте данные в '
                               'карточке.\n'
                               '\n'
                               '## Заказ через менеджера\n'
                               '\n'
                               'Оставьте заявку на нужные свечи: менеджер проверит наличие, рассчитает '
                               'стоимость и доставку, согласует детали. Отправка в Россию, Казахстан или '
                               'Узбекистан займёт 7–21 рабочий день.\n'
                               '\n'
                               'Рецептурные позиции отмечены в карточке; требования к рецепту определяются '
                               'препаратом и страной доставки. Суппозитории чувствительны к температуре, '
                               'поэтому условия хранения приведены в инструкции. Ознакомьтесь с ней до '
                               'применения и посоветуйтесь с врачом, особенно если свечи нужны ребёнку.'},
            'en': {'name': 'Suppositories',
                   'h1': 'Turkish Suppositories: Rectal and Vaginal',
                   'meta_title': 'Turkish Rectal & Vaginal Suppositories | Mudaroba',
                   'meta_description': 'Rectal and vaginal suppositories from Turkish pharmacies, including '
                                       'ibuprofen, paracetamol and haemorrhoid products. A manager checks '
                                       'availability, cost and delivery.',
                   'seo_text': 'This collection brings together Turkish suppositories of every kind. Rectal '
                               'forms appear among fever and pain medicines, laxatives and haemorrhoid '
                               'products, while vaginal suppositories are mostly antiseptics. The card for '
                               'each item lists the composition, strength and patient leaflet.\n'
                               '\n'
                               'Examples from the catalogue: IBU-BABY (ibuprofen) suppositories for '
                               'children, PARANOX S (paracetamol), PROCTOLOG (ruscogenins + trimebutine) and '
                               'ULTRAPROCT (fluocortolone + cinchocaine) for haemorrhoids, and BIOKADIN VAG '
                               '(povidone-iodine) vaginal suppositories.\n'
                               '\n'
                               '## Ordering through a manager\n'
                               '\n'
                               'Submit a request for the suppositories you need. A manager checks '
                               'availability, calculates the price and shipping and confirms the details. '
                               'Delivery to Russia, Kazakhstan or Uzbekistan takes 7–21 business days.\n'
                               '\n'
                               'Prescription-only items are marked on the card, and requirements depend on '
                               'the medicine and the destination country. Suppositories are sensitive to '
                               'heat, so storage conditions are given in the leaflet. Read it before use and '
                               'talk to a doctor, especially when the product is meant for a child.'}},
 'ot-podagry': {'ru': {'name': 'От подагры',
                       'h1': 'Турецкие таблетки от подагры',
                       'meta_title': 'Турецкие таблетки от подагры: аллопуринол, колхицин | Mudaroba',
                       'meta_description': 'Противоподагрические препараты из Турции: ALLOPURINOL, ADENURIC, '
                                           'COLCHICUM DISPERT. Отправьте заявку — менеджер проверит наличие, '
                                           'рассчитает стоимость и доставку.',
                       'seo_text': 'В подборке — турецкие таблетки от подагры из группы АТХ M04, '
                                   'противоподагрические средства. Её основу составляют препараты двух '
                                   'типов: одни снижают образование мочевой кислоты, другие применяют при '
                                   'приступах подагрического артрита. Какой из них нужен, определяет врач по '
                                   'результатам обследования. Названия приведены латиницей, как на турецкой '
                                   'упаковке.\n'
                                   '\n'
                                   'Ингибиторы ксантиноксидазы представлены препаратами ALLOPURINOL и '
                                   'URIKOLIZ (оба — аллопуринол), а также ADENURIC (фебуксостат); их ищут и '
                                   'как турецкие таблетки от мочевой кислоты. Колхицин есть в виде COLCHICUM '
                                   'DISPERT (колхицин); кроме таблеток, в каталоге встречаются капли '
                                   'колхицина для приёма внутрь. В карточке каждого препарата указаны '
                                   'действующее вещество, дозировка и инструкция.\n'
                                   '\n'
                                   '## Как заказать\n'
                                   '\n'
                                   'Турецкое лекарство от подагры оформляется через заявку: менеджер '
                                   'проверит наличие у дистрибьюторов, рассчитает стоимость с доставкой и '
                                   'согласует детали. Доставка в Россию, Казахстан и Узбекистан — 7–21 '
                                   'рабочий день.\n'
                                   '\n'
                                   'Турецкие таблетки от подагры, как правило, рецептурные: статус указан в '
                                   'карточке, а требования к рецепту зависят от препарата и страны '
                                   'получения. Перед применением прочитайте инструкцию и проконсультируйтесь '
                                   'с ревматологом или терапевтом, особенно если вы уже принимаете другие '
                                   'препараты.'},
                'en': {'name': 'Gout',
                       'h1': 'Turkish Gout Medicines',
                       'meta_title': 'Turkish Gout Tablets: Allopurinol, Colchicine | Mudaroba',
                       'meta_description': 'Antigout medicines from Turkey, including ALLOPURINOL, ADENURIC '
                                           'and COLCHICUM DISPERT. Send a request and a manager checks '
                                           'availability, cost and delivery time.',
                       'seo_text': 'This collection covers Turkish gout tablets from ATC group M04, antigout '
                                   'preparations. They fall into two main types: medicines that reduce uric '
                                   'acid production and medicines used during acute gout flares. Names are '
                                   'shown in Turkish, as printed on the pack.\n'
                                   '\n'
                                   'Xanthine oxidase inhibitors are represented by ALLOPURINOL and URIKOLIZ '
                                   '(both allopurinol) and by ADENURIC (febuxostat). Colchicine is available '
                                   'as COLCHICUM DISPERT (colchicine). Each product card lists the active '
                                   'ingredient, strength and patient leaflet.\n'
                                   '\n'
                                   '## How to order\n'
                                   '\n'
                                   'Send a request for the medicine you need. A manager checks availability '
                                   'with Turkish distributors, calculates the price including shipping and '
                                   'confirms the details. Delivery to Russia, Kazakhstan and Uzbekistan '
                                   'takes 7–21 business days.\n'
                                   '\n'
                                   'Antigout medicines are usually prescription-only; the status is shown on '
                                   'the card, and requirements depend on the destination country. Read the '
                                   'leaflet and consult a rheumatologist or GP before use.'}}}


def fill_landing_seo(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    CategoryTranslation = apps.get_model("catalog", "CategoryTranslation")
    CategoryCollection = apps.get_model("catalog", "CategoryCollection")
    CategoryCollectionTranslation = apps.get_model("catalog", "CategoryCollectionTranslation")

    slugs = set(CATEGORY_TEXTS) | {row["parent"] for row in COLLECTIONS}
    categories = {category.slug: category for category in Category.objects.filter(slug__in=slugs)}

    for slug, texts in CATEGORY_TEXTS.items():
        category = categories.get(slug)
        if category is None:
            continue
        for locale, values in texts.items():
            translation = CategoryTranslation.objects.filter(category=category, locale=locale).first()
            if translation is None:
                name = CATEGORY_FALLBACK_NAMES.get(slug, {}).get(locale) or category.name
                translation = CategoryTranslation(category=category, locale=locale, name=name)
            changed = [field for field in SEO_FIELDS if values.get(field) and not getattr(translation, field)]
            if translation.pk is None:
                for field in changed:
                    setattr(translation, field, values[field])
                translation.save()
            elif changed:
                for field in changed:
                    setattr(translation, field, values[field])
                translation.save(update_fields=[*changed, "updated_at"])

    for row in COLLECTIONS:
        parent = categories.get(row["parent"])
        if parent is None or CategoryCollection.objects.filter(slug=row["slug"]).exists():
            continue
        texts = COLLECTION_TEXTS[row["slug"]]
        collection = CategoryCollection.objects.create(
            parent=parent,
            name=texts["ru"]["name"],
            slug=row["slug"],
            sort_order=row["sort_order"],
            atc_prefixes=row["atc_prefixes"],
            name_keywords=row["name_keywords"],
            dosage_forms=row["dosage_forms"],
            exclude_atc_prefixes=row["exclude_atc_prefixes"],
        )
        for locale, values in texts.items():
            CategoryCollectionTranslation.objects.create(collection=collection, locale=locale, **values)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0221_category_landing_seo_and_collections"),
    ]

    operations = [
        migrations.RunPython(fill_landing_seo, migrations.RunPython.noop),
    ]
