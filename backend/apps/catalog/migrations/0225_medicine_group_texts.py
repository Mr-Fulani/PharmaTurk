"""Страницы препаратов из SEO-плана медикаментов (пункт 3, кластеры «Препарат: …»).

Тексты — кратко по инструкциям производителей, без доз: дозы и схемы у каждой формы
свои и есть в её инструкции. H1, title и description не заполнены — их строит шаблон
страницы (frontend/src/lib/drugGroup.js). TYLOLHOT не создан: все его формы содержат
псевдоэфедрин, ввоз которого в РФ и СНГ ограничен (docs/TECH_DEBT.md, TD-024).
Формы с такими веществами у других брендов (A-FERIN, AERIUS, KATARIN) страница не
показывает — их отсекает отметка TD-024 (``import_restricted_countries``). Сами страницы этих трёх
брендов созданы выключенными: по решению PR #165 бренды, в линейке которых есть такие формы,
не продвигаются (docs/MEDICINE_LANDING_PAGES.md, «Ограничения текстов»). Включить —
галочка «Активен» в админке, по решению владельца.
"""

from django.db import migrations

_NSAID_RU = (
    "Не применять при язве желудка или кишечника, желудочно-кишечном кровотечении, тяжёлой "
    "сердечной, печёночной или почечной недостаточности, в третьем триместре беременности и при "
    "аллергии на ацетилсалициловую кислоту и другие НПВП."
)
_NSAID_EN = (
    "Do not use with a stomach or intestinal ulcer, gastrointestinal bleeding, severe heart, liver or "
    "kidney failure, in the third trimester of pregnancy or with an allergy to aspirin or other NSAIDs."
)
_OSELTAMIVIR = {
    "ru": {
        "active_ingredient": "осельтамивир",
        "indications": (
            "Противовирусный препарат против вирусов гриппа A и B.\n\n"
            "Лечение гриппа у взрослых и детей — лечение начинают в первые 48 часов после появления "
            "симптомов. Профилактика гриппа после контакта с заболевшим.\n\n"
            "На другие ОРВИ и простуду не действует."
        ),
        "usage_summary": (
            "Капсулы принимают внутрь, во время еды или независимо от неё. Порошок и гранулы — "
            "для детей и тех, кому трудно глотать капсулы.\n\n"
            "Курс лечения обычно 5 дней, профилактики — дольше. Дозу для ребёнка рассчитывают по массе "
            "тела. Дозу и длительность определяет врач."
        ),
    },
    "en": {
        "active_ingredient": "oseltamivir",
        "indications": (
            "An antiviral medicine against influenza A and B viruses.\n\n"
            "Treatment of flu in adults and children, started within 48 hours of the first symptoms. "
            "Prevention of flu after contact with an infected person.\n\n"
            "It does not work against colds and other respiratory viruses."
        ),
        "usage_summary": (
            "Capsules are taken by mouth, with or without food. The powder and granules are for children "
            "and for people who cannot swallow capsules.\n\n"
            "Treatment usually lasts 5 days, prevention longer. A child's dose depends on body weight. "
            "The dose and duration are set by a doctor."
        ),
    },
}
_DEXKETOPROFEN = {
    "ru": {
        "active_ingredient": "декскетопрофен",
        "indications": (
            "Нестероидное противовоспалительное средство (НПВП) для кратковременного лечения боли.\n\n"
            "Таблетки — боль слабой и средней силы: в мышцах и суставах, зубная боль, болезненные "
            "менструации. Раствор для инъекций — острая боль средней и сильной интенсивности, в том "
            "числе после операций, когда приём внутрь невозможен."
        ),
        "usage_summary": (
            "Таблетки принимают внутрь, запивая водой; при сильной боли — за 30 минут до еды. Препарат "
            "предназначен для коротких курсов. Инъекции делает медицинский работник.\n\n" + _NSAID_RU
        ),
    },
    "en": {
        "active_ingredient": "dexketoprofen",
        "indications": (
            "A non-steroidal anti-inflammatory drug (NSAID) for short-term pain relief.\n\n"
            "Tablets: mild to moderate pain in muscles and joints, toothache, painful periods. Solution "
            "for injection: acute moderate to severe pain, including after surgery, when tablets cannot "
            "be taken."
        ),
        "usage_summary": (
            "Tablets are taken by mouth with water; for severe pain, 30 minutes before a meal. The medicine "
            "is meant for short courses. Injections are given by a healthcare professional.\n\n" + _NSAID_EN
        ),
    },
}

GROUPS = [
    {
        "slug": "majezik", "name": "MAJEZIK",
        "ru": {
            "name": "Мажезик",
            "active_ingredient": "флурбипрофен",
            "indications": (
                "Нестероидное противовоспалительное средство (НПВП): уменьшает боль и воспаление.\n\n"
                "Таблетки и капсулы — боль и воспаление при заболеваниях суставов и позвоночника "
                "(остеоартроз, ревматоидный артрит, анкилозирующий спондилит), боль в мышцах и связках, "
                "зубная и послеоперационная боль, болезненные менструации. MAJEZIK DUO с тиоколхикозидом "
                "дополнительно снимает мышечный спазм — при боли в спине.\n\n"
                "Спрей и раствор для полоскания — боль и воспаление в горле и полости рта: фарингит, "
                "тонзиллит, гингивит, после стоматологических процедур."
            ),
            "usage_summary": (
                "Таблетки и капсулы принимают внутрь во время или после еды, запивая водой, в наименьшей "
                "эффективной дозе и коротким курсом. Спрей распыляют на заднюю стенку горла, раствором "
                "полощут горло и рот, не проглатывая.\n\n" + _NSAID_RU
            ),
        },
        "en": {
            "name": "Majezik",
            "active_ingredient": "flurbiprofen",
            "indications": (
                "A non-steroidal anti-inflammatory drug (NSAID) that relieves pain and inflammation.\n\n"
                "Tablets and capsules: pain and inflammation in joint and spine conditions (osteoarthritis, "
                "rheumatoid arthritis, ankylosing spondylitis), muscle and ligament pain, dental and "
                "post-operative pain, painful periods. MAJEZIK DUO also contains thiocolchicoside, which "
                "relaxes muscle spasm in back pain.\n\n"
                "Spray and gargle: pain and inflammation in the throat and mouth — pharyngitis, tonsillitis, "
                "gingivitis, after dental procedures."
            ),
            "usage_summary": (
                "Tablets and capsules are taken by mouth with or after food, with water, at the lowest "
                "effective dose for a short course. The spray is directed at the back of the throat; the "
                "gargle is used to rinse the throat and mouth and is not swallowed.\n\n" + _NSAID_EN
            ),
        },
    },
    {"slug": "arveles", "name": "ARVELES", "ru": {"name": "Арвелес", **_DEXKETOPROFEN["ru"]}, "en": {"name": "Arveles", **_DEXKETOPROFEN["en"]}},
    {"slug": "dexofen", "name": "DEXOFEN", "ru": {"name": "Дексофен", **_DEXKETOPROFEN["ru"]}, "en": {"name": "Dexofen", **_DEXKETOPROFEN["en"]}},
    {"slug": "oseflu", "name": "OSEFLU", "ru": {"name": "Осефлю", **_OSELTAMIVIR["ru"]}, "en": {"name": "Oseflu", **_OSELTAMIVIR["en"]}},
    {"slug": "enfluvir", "name": "ENFLUVIR", "ru": {"name": "Энфлувир", **_OSELTAMIVIR["ru"]}, "en": {"name": "Enfluvir", **_OSELTAMIVIR["en"]}},
    {
        "slug": "expigment", "name": "EXPIGMENT",
        "ru": {
            "name": "Экспигмент",
            "active_ingredient": "гидрохинон",
            "indications": (
                "Крем для осветления участков гиперпигментации кожи: мелазма (хлоазма), веснушки, "
                "возрастные пигментные пятна, пятна после воспаления. Крем 4 % действует сильнее, чем 2 %."
            ),
            "usage_summary": (
                "Крем наносят тонким слоем только на пигментные пятна. Перед началом проверяют переносимость "
                "на небольшом участке кожи. На всё время лечения кожу защищают от солнца кремом с SPF: "
                "без этого пятна возвращаются.\n\n"
                "Не наносить на повреждённую кожу и около глаз. Если за 2 месяца пятна не посветлели, "
                "применение прекращают и обращаются к дерматологу."
            ),
        },
        "en": {
            "name": "Expigment",
            "active_ingredient": "hydroquinone",
            "indications": (
                "A cream that lightens areas of skin hyperpigmentation: melasma (chloasma), freckles, age spots "
                "and marks left after inflammation. The 4% cream is stronger than the 2% one."
            ),
            "usage_summary": (
                "Apply a thin layer to the dark spots only. Test the cream on a small patch of skin first. "
                "Protect the skin from the sun with an SPF cream for the whole course, otherwise the spots "
                "come back.\n\n"
                "Do not apply to broken skin or near the eyes. If the spots have not lightened after 2 months, "
                "stop and see a dermatologist."
            ),
        },
    },
    {
        "slug": "hametan", "name": "HAMETAN",
        "ru": {
            "name": "Хаметан",
            "active_ingredient": "дистиллят гамамелиса виргинского",
            "indications": (
                "Крем и мазь с дистиллятом гамамелиса — растительное средство при мелких повреждениях и "
                "раздражении кожи: ссадинах, потёртостях, лёгких солнечных ожогах, покраснении и зуде. "
                "Показания конкретной формы — в её инструкции."
            ),
            "usage_summary": (
                "Наносят тонким слоем на чистую кожу несколько раз в день. Если раздражение не проходит "
                "или появились признаки инфекции, обратитесь к врачу."
            ),
        },
        "en": {
            "name": "Hametan",
            "active_ingredient": "witch hazel distillate",
            "indications": (
                "A cream and ointment with witch hazel distillate, a herbal remedy for minor skin injuries and "
                "irritation: grazes, chafing, mild sunburn, redness and itching. See the leaflet of each form "
                "for its indications."
            ),
            "usage_summary": (
                "Apply a thin layer to clean skin several times a day. See a doctor if the irritation does not "
                "settle or the skin looks infected."
            ),
        },
    },
    {
        "slug": "kloroben", "name": "KLOROBEN",
        "ru": {
            "name": "Клоробен",
            "active_ingredient": "хлоргексидин + бензидамин",
            "indications": (
                "Антисептик (хлоргексидин) и противовоспалительное средство (бензидамин) для полости рта и "
                "горла: гингивит, стоматит, фарингит, тонзиллит, воспаление после стоматологических "
                "вмешательств."
            ),
            "usage_summary": (
                "Раствором полощут рот и горло, не проглатывая; спрей распыляют на воспалённые участки. "
                "После применения какое-то время не есть и не пить.\n\n"
                "Длительность — по рекомендации врача или стоматолога. При долгом применении хлоргексидин "
                "может окрашивать зубы и язык."
            ),
        },
        "en": {
            "name": "Kloroben",
            "active_ingredient": "chlorhexidine + benzydamine",
            "indications": (
                "An antiseptic (chlorhexidine) and an anti-inflammatory (benzydamine) for the mouth and throat: "
                "gingivitis, stomatitis, pharyngitis, tonsillitis, inflammation after dental treatment."
            ),
            "usage_summary": (
                "Rinse the mouth and throat with the solution without swallowing it; the spray is applied to "
                "the inflamed areas. Do not eat or drink for a while afterwards.\n\n"
                "Use for as long as a doctor or dentist recommends. With long use chlorhexidine can stain the "
                "teeth and tongue."
            ),
        },
    },
    {
        "slug": "crestor", "name": "CRESTOR",
        "ru": {
            "name": "Крестор",
            "active_ingredient": "розувастатин",
            "indications": (
                "Статин для снижения холестерина. Повышенный холестерин и смешанная дислипидемия — в "
                "дополнение к диете. Снижение риска инфаркта и инсульта у людей с высоким "
                "сердечно-сосудистым риском."
            ),
            "usage_summary": (
                "Таблетку принимают внутрь один раз в день в одно и то же время, независимо от еды. Дозу "
                "подбирает врач по анализу липидов и контролирует печёночные пробы.\n\n"
                "Не применять при болезнях печени в активной фазе, при беременности и кормлении грудью. "
                "О необъяснимой боли или слабости в мышцах сразу сообщите врачу."
            ),
        },
        "en": {
            "name": "Crestor",
            "active_ingredient": "rosuvastatin",
            "indications": (
                "A statin that lowers cholesterol. High cholesterol and mixed dyslipidaemia, together with diet. "
                "Lowering the risk of heart attack and stroke in people at high cardiovascular risk."
            ),
            "usage_summary": (
                "One tablet by mouth once a day at the same time, with or without food. The doctor sets the "
                "dose from lipid tests and checks liver tests.\n\n"
                "Do not use with active liver disease, in pregnancy or while breastfeeding. Report unexplained "
                "muscle pain or weakness to a doctor straight away."
            ),
        },
    },
    {
        "slug": "aerius", "is_active": False, "name": "AERIUS",
        "ru": {
            "name": "Эриус",
            "active_ingredient": "дезлоратадин",
            "indications": (
                "Антигистаминный препарат: аллергический ринит (сезонный и круглогодичный) — заложенность "
                "и зуд носа, чихание, слезотечение; крапивница — зуд и сыпь. Почти не вызывает сонливости."
            ),
            "usage_summary": (
                "Таблетку принимают один раз в день независимо от еды. Сироп — для детей, доза зависит "
                "от возраста и отмеряется мерной ложкой."
            ),
        },
        "en": {
            "name": "Aerius",
            "active_ingredient": "desloratadine",
            "indications": (
                "An antihistamine for allergic rhinitis (seasonal and year-round) — blocked, itchy nose, "
                "sneezing, watery eyes — and for urticaria (hives). It rarely causes drowsiness."
            ),
            "usage_summary": (
                "One tablet once a day, with or without food. The syrup is for children; the dose depends on "
                "age and is measured with the spoon in the pack."
            ),
        },
    },
    {
        "slug": "mirena", "name": "MIRENA",
        "ru": {
            "name": "Мирена",
            "active_ingredient": "левоноргестрел",
            "indications": (
                "Внутриматочная гормональная система: контрацепция; обильные менструальные кровотечения; "
                "защита эндометрия при заместительной гормональной терапии эстрогенами."
            ),
            "usage_summary": (
                "Систему устанавливает и удаляет только врач-гинеколог после осмотра. Срок использования "
                "указан в инструкции. Контрольный осмотр — через несколько недель после установки, "
                "затем по назначению врача."
            ),
        },
        "en": {
            "name": "Mirena",
            "active_ingredient": "levonorgestrel",
            "indications": (
                "A hormonal intrauterine system for contraception, heavy menstrual bleeding and protection of "
                "the womb lining during oestrogen replacement therapy."
            ),
            "usage_summary": (
                "The system is fitted and removed only by a gynaecologist after an examination. How long it "
                "can stay in place is stated in the leaflet. A check-up follows a few weeks after fitting, "
                "then as the doctor advises."
            ),
        },
    },
    {
        "slug": "tamoxifen", "name": "TAMOXIFEN",
        "ru": {
            "name": "Тамоксифен",
            "active_ingredient": "тамоксифен",
            "indications": (
                "Антиэстрогенный противоопухолевый препарат: лечение гормонозависимого рака молочной железы "
                "и снижение риска его рецидива. Назначает онколог."
            ),
            "usage_summary": (
                "Таблетки принимают внутрь ежедневно, длительно, под наблюдением онколога. Во время лечения "
                "нужны регулярные осмотры у гинеколога; о кровянистых выделениях, боли и отёке ноги сразу "
                "сообщите врачу."
            ),
        },
        "en": {
            "name": "Tamoxifen",
            "active_ingredient": "tamoxifen",
            "indications": (
                "An anti-oestrogen cancer medicine for hormone-sensitive breast cancer and for lowering the risk "
                "of its return. Prescribed by an oncologist."
            ),
            "usage_summary": (
                "Tablets are taken by mouth every day for a long period under an oncologist's supervision. "
                "Regular gynaecological check-ups are needed; report vaginal bleeding, leg pain or swelling to "
                "a doctor straight away."
            ),
        },
    },
    {
        "slug": "daflon", "name": "DAFLON",
        "ru": {
            "name": "Дафлон",
            "active_ingredient": "диосмин + гесперидин",
            "indications": (
                "Венотоник: очищенная микронизированная флавоноидная фракция того же производителя "
                "(Servier), что и Детралекс в России. Хроническая венозная недостаточность ног — тяжесть, "
                "боль, отёки, ночные судороги; острый и хронический геморрой."
            ),
            "usage_summary": (
                "Таблетки принимают внутрь во время еды. При обострении геморроя схема другая, чем при "
                "венозной недостаточности, — по инструкции и назначению врача."
            ),
        },
        "en": {
            "name": "Daflon",
            "active_ingredient": "diosmin + hesperidin",
            "indications": (
                "A venotonic: purified micronised flavonoid fraction by Servier, the maker of Detralex in "
                "Russia. Chronic venous insufficiency of the legs — heaviness, pain, swelling, night cramps; "
                "acute and chronic haemorrhoids."
            ),
            "usage_summary": (
                "Tablets are taken by mouth with meals. A haemorrhoid flare-up has a different schedule from "
                "venous insufficiency — follow the leaflet and the doctor's advice."
            ),
        },
    },
    {
        "slug": "methotrexate", "name": "METHOTREXATE",
        "ru": {
            "name": "Метотрексат",
            "active_ingredient": "метотрексат",
            "indications": (
                "Противоопухолевое и иммуносупрессивное средство: некоторые лейкозы, лимфомы и солидные "
                "опухоли; тяжёлый псориаз и ревматоидный артрит. Назначает онколог, ревматолог или "
                "дерматолог."
            ),
            "usage_summary": (
                "Растворы для инъекций вводит медицинский работник по схеме врача. При псориазе и "
                "ревматоидном артрите метотрексат применяют один раз в неделю, а не ежедневно: ошибка в "
                "схеме опасна для жизни.\n\n"
                "Во время лечения регулярно сдают анализы крови и печёночные пробы. При беременности "
                "противопоказан."
            ),
        },
        "en": {
            "name": "Methotrexate",
            "active_ingredient": "methotrexate",
            "indications": (
                "An anticancer and immunosuppressive medicine: some leukaemias, lymphomas and solid tumours; "
                "severe psoriasis and rheumatoid arthritis. Prescribed by an oncologist, rheumatologist or "
                "dermatologist."
            ),
            "usage_summary": (
                "Injections are given by a healthcare professional following the doctor's schedule. In "
                "psoriasis and rheumatoid arthritis methotrexate is used once a week, not daily: getting the "
                "schedule wrong is life-threatening.\n\n"
                "Blood and liver tests are needed regularly during treatment. It must not be used in pregnancy."
            ),
        },
    },
    {
        "slug": "migreout", "name": "MIGREOUT",
        "ru": {
            "name": "Мигреоут",
            "active_ingredient": "ризатриптан",
            "indications": (
                "Триптан для снятия приступа мигрени с аурой и без неё. Для профилактики приступов не "
                "применяется."
            ),
            "usage_summary": (
                "Шипучую таблетку растворяют в воде и выпивают в начале приступа. Повторный приём и "
                "наибольшая доза за сутки — по инструкции.\n\n"
                "Не применять при ишемической болезни сердца, неконтролируемом давлении и после инсульта; "
                "другие средства от мигрени в те же сутки — только по согласованию с врачом."
            ),
        },
        "en": {
            "name": "Migreout",
            "active_ingredient": "rizatriptan",
            "indications": (
                "A triptan that stops a migraine attack with or without aura. It is not used to prevent attacks."
            ),
            "usage_summary": (
                "Dissolve the effervescent tablet in water and drink it at the start of an attack. A repeat dose "
                "and the daily maximum are given in the leaflet.\n\n"
                "Do not use with coronary heart disease, uncontrolled blood pressure or after a stroke; do not "
                "take other migraine medicines on the same day unless a doctor agrees."
            ),
        },
    },
    {
        "slug": "katarin", "is_active": False, "name": "KATARIN",
        "ru": {
            "name": "Катарин",
            "active_ingredient": "парацетамол + хлорфенамин + оксоламин",
            "indications": (
                "Комбинированное средство от симптомов простуды и гриппа: жар, головная и мышечная боль, "
                "насморк и чихание, кашель."
            ),
            "usage_summary": (
                "Капсулы — для взрослых, сироп — для детей, доза по возрасту. Не сочетать с другими "
                "препаратами парацетамола и не превышать суточную дозу. Может вызывать сонливость — "
                "осторожно за рулём."
            ),
        },
        "en": {
            "name": "Katarin",
            "active_ingredient": "paracetamol + chlorphenamine + oxolamine",
            "indications": (
                "A combination medicine for cold and flu symptoms: fever, headache and muscle aches, runny nose "
                "and sneezing, cough."
            ),
            "usage_summary": (
                "Capsules are for adults, the syrup is for children with an age-based dose. Do not combine with "
                "other paracetamol medicines or exceed the daily dose. It may cause drowsiness — take care when "
                "driving."
            ),
        },
    },
    {
        "slug": "a-ferin", "is_active": False, "name": "A-FERIN",
        "ru": {
            "name": "А-ферин",
            "active_ingredient": "парацетамол; в части форм — с хлорфенамином",
            "indications": (
                "Жаропонижающее и обезболивающее: жар, головная, зубная и мышечная боль, симптомы простуды "
                "и гриппа. Формы с хлорфенамином дополнительно уменьшают насморк и чихание."
            ),
            "usage_summary": (
                "Сироп и суспензию для детей дозируют мерной ложкой по массе тела или возрасту. Не сочетать "
                "с другими препаратами парацетамола и не превышать суточную дозу: передозировка опасна для "
                "печени."
            ),
        },
        "en": {
            "name": "A-ferin",
            "active_ingredient": "paracetamol; some forms also contain chlorphenamine",
            "indications": (
                "Reduces fever and relieves headache, toothache, muscle pain and cold and flu symptoms. Forms "
                "with chlorphenamine also ease a runny nose and sneezing."
            ),
            "usage_summary": (
                "Children's syrup and suspension are dosed with the measuring spoon by body weight or age. Do "
                "not combine with other paracetamol medicines or exceed the daily dose: an overdose harms the "
                "liver."
            ),
        },
    },
    {
        "slug": "levotiron", "name": "LEVOTIRON",
        "ru": {
            "name": "Левотирон",
            "active_ingredient": "левотироксин натрия",
            "indications": (
                "Гормон щитовидной железы: гипотиреоз; профилактика повторного роста зоба после операции; "
                "эутиреоидный зоб; лечение после операции по поводу рака щитовидной железы."
            ),
            "usage_summary": (
                "Таблетку принимают утром натощак, за 30 минут до завтрака, запивая водой. Дозу подбирает "
                "эндокринолог по анализу ТТГ; менять её самостоятельно нельзя."
            ),
        },
        "en": {
            "name": "Levotiron",
            "active_ingredient": "levothyroxine sodium",
            "indications": (
                "A thyroid hormone: hypothyroidism; prevention of goitre regrowth after surgery; euthyroid goitre; "
                "treatment after thyroid cancer surgery."
            ),
            "usage_summary": (
                "Take the tablet in the morning on an empty stomach, 30 minutes before breakfast, with water. The "
                "endocrinologist sets the dose from TSH tests; do not change it yourself."
            ),
        },
    },
]


def create_groups(apps, schema_editor):
    MedicineGroup = apps.get_model("catalog", "MedicineGroup")
    MedicineGroupTranslation = apps.get_model("catalog", "MedicineGroupTranslation")
    for order, item in enumerate(GROUPS):
        group, _ = MedicineGroup.objects.get_or_create(
            slug=item["slug"],
            defaults={"name": item["name"], "sort_order": order, "is_active": item.get("is_active", True)},
        )
        for locale in ("ru", "en"):
            MedicineGroupTranslation.objects.get_or_create(group=group, locale=locale, defaults=item[locale])


def delete_groups(apps, schema_editor):
    apps.get_model("catalog", "MedicineGroup").objects.filter(slug__in=[item["slug"] for item in GROUPS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0224_medicine_groups"),
    ]

    operations = [
        migrations.RunPython(create_groups, delete_groups),
    ]
