"""
Единый источник правды для категорий и брендов каталога.
Используется seed_catalog_data и get_or_create_root_category.
"""

# Корневые категории: (slug, name_ru, name_en, description_ru, description_en, category_type_slug)
ROOT_CATEGORIES = [
    ("medicines", "Медицина", "Medicine",
     "Лекарственные препараты и медикаменты", "Medicines and pharmaceutical products", "medicines"),
    ("supplements", "БАДы", "Supplements",
     "Биологически активные добавки", "Dietary supplements", "supplements"),
    ("medical-equipment", "Медтехника", "Medical Equipment",
     "Медицинское оборудование и техника", "Medical equipment and devices", "medical-equipment"),
    ("clothing", "Одежда", "Clothing",
     "Одежда для мужчин, женщин и детей", "Clothing for men, women and children", "clothing"),
    ("shoes", "Обувь", "Shoes",
     "Обувь всех видов", "Footwear of all types", "shoes"),
    ("electronics", "Электроника", "Electronics",
     "Электроника и бытовая техника", "Electronics and home appliances", "electronics"),
    ("furniture", "Мебель", "Furniture",
     "Мебель для дома и офиса", "Furniture for home and office", "furniture"),
    ("tableware", "Посуда", "Tableware",
     "Посуда и кухонная утварь", "Tableware and kitchen utensils", "tableware"),
    ("accessories", "Аксессуары", "Accessories",
     "Аксессуары и дополнения", "Accessories and complements", "accessories"),
    ("jewelry", "Украшения", "Jewelry",
     "Ювелирные изделия и бижутерия", "Jewelry and costume jewelry", "jewelry"),
    ("underwear", "Нижнее бельё", "Underwear",
     "Нижнее бельё и домашняя одежда", "Underwear and loungewear", "underwear"),
    ("headwear", "Головные уборы", "Headwear",
     "Головные уборы и аксессуары", "Headwear and accessories", "headwear"),
    ("perfumery", "Парфюмерия", "Perfumery",
     "Парфюмерия и ароматы", "Perfumes and fragrances", "perfumery"),
    ("books", "Книги", "Books",
     "Книги и литература", "Books and literature", "books"),
    ("uslugi", "Услуги", "Services",
     "Услуги различного назначения", "Services of various kinds", "uslugi"),
    ("sports", "Спорттовары", "Sports Goods",
     "Товары для спорта и активного отдыха", "Sports and outdoor goods", "sports"),
    ("auto-parts", "Автозапчасти", "Auto Parts",
     "Автозапчасти и аксессуары", "Auto parts and accessories", "auto-parts"),
    ("islamic-clothing", "Исламская одежда", "Islamic Clothing",
     "Мусульманская одежда и хиджабы", "Islamic clothing and hijabs", "islamic-clothing"),
    ("incense", "Благовония", "Incense",
     "Благовония и ароматические продукты", "Incense and aromatic products", "incense"),
]

# Подкатегории: {parent_slug: [(name_ru, name_en, slug, desc_ru, desc_en), ...]}
SUB_CATEGORIES = {
    "medicines": [
        ("Антибиотики", "Antibiotics", "antibiotics", "Антибактериальные препараты", "Antibacterial drugs"),
        ("Обезболивающие", "Painkillers", "painkillers", "Препараты для снятия боли", "Pain relief medications"),
        ("Кардио", "Cardio", "cardio", "Препараты для сердечно-сосудистой системы", "Cardiovascular medications"),
        ("Дерматология", "Dermatology", "dermatology", "Препараты для кожи", "Skin medications"),
        ("Простуда/ОРВИ", "Cold/Flu", "cold-flu", "Препараты от простуды и гриппа", "Cold and flu medications"),
        ("ЖКТ", "Gastro", "gastro", "Препараты для желудочно-кишечного тракта", "Gastrointestinal medications"),
        ("Эндокринология/Диабет", "Endocrinology/Diabetes", "endocrinology-diabetes", "Препараты при диабете", "Diabetes medications"),
        ("Офтальмология", "Ophthalmology", "ophthalmology", "Препараты для глаз", "Eye medications"),
        ("ЛОР", "ENT", "ent", "Препараты для уха, горла, носа", "ENT medications"),
        ("Ортопедия/Травмы", "Orthopedics/Injuries", "orthopedics", "Препараты при травмах", "Orthopedic and injury medications"),
    ],
    "supplements": [
        ("Витамины", "Vitamins", "vitamins", "Витаминные комплексы", "Vitamin supplements"),
        ("Минералы", "Minerals", "minerals", "Минеральные добавки", "Mineral supplements"),
        ("Омега/рыбий жир", "Omega/Fish Oil", "omega-fish-oil", "Омега-3 и рыбий жир", "Omega-3 and fish oil"),
        ("Протеин/аминокислоты", "Protein/Amino Acids", "protein-amino", "Протеин и аминокислоты", "Protein and amino acids"),
        ("Коллаген", "Collagen", "collagen", "Коллагеновые добавки", "Collagen supplements"),
        ("Пробиотики", "Probiotics", "probiotics", "Пробиотики для кишечника", "Probiotics for gut health"),
        ("Иммунитет", "Immunity", "immunity", "Средства для иммунитета", "Immunity boosters"),
        ("Детские БАДы", "Kids Supplements", "kids-supplements", "БАДы для детей", "Supplements for children"),
    ],
    "medical-equipment": [
        ("Измерительные (тонометры, глюкометры)", "Measuring Devices", "measuring-devices", "Тонометры, глюкометры", "Blood pressure monitors, glucometers"),
        ("Уход/устройства (небулайзеры, ингаляторы)", "Care Devices", "care-devices", "Небулайзеры, ингаляторы", "Nebulizers, inhalers"),
        ("Реабилитация/ортезы", "Rehab/Orthoses", "rehab-orthoses", "Ортезы и реабилитация", "Orthoses and rehabilitation"),
        ("Расходники (маски, перчатки)", "Consumables", "consumables", "Медицинские расходники", "Medical consumables"),
        ("Стоматология — инструменты", "Dentistry Tools", "dentistry-tools", "Стоматологические инструменты", "Dental instruments"),
        ("Стоматология — расходники", "Dentistry Consumables", "dentistry-consumables", "Стоматологические расходники", "Dental consumables"),
    ],
    "tableware": [
        ("Кухонная (сковороды/кастрюли)", "Kitchen Cookware", "kitchen-cookware", "Сковороды, кастрюли", "Pans, pots"),
        ("Сервировка", "Serving", "serving", "Посуда для сервировки", "Serving dishes"),
        ("Хранение", "Storage", "storage", "Посуда для хранения", "Storage containers"),
        ("Материал: медная", "Copper", "copper", "Медная посуда", "Copper cookware"),
        ("Материал: фарфор", "Porcelain", "porcelain", "Фарфоровая посуда", "Porcelain tableware"),
        ("Материал: стекло/керамика", "Glass/Ceramic", "glass-ceramic", "Стеклянная и керамическая посуда", "Glass and ceramic tableware"),
    ],
    "furniture": [
        ("Гостиная", "Living Room", "living-room", "Мебель для гостиной", "Living room furniture"),
        ("Спальня", "Bedroom", "bedroom", "Мебель для спальни", "Bedroom furniture"),
        ("Офис", "Office", "office", "Офисная мебель", "Office furniture"),
        ("Кухня/столовая", "Kitchen/Dining", "kitchen-dining", "Мебель для кухни и столовой", "Kitchen and dining furniture"),
    ],
    "jewelry": [
        ("Кольца", "Rings", "rings", "Кольца", "Rings"),
        ("Цепочки", "Chains", "chains", "Цепочки и ожерелья", "Chains and necklaces"),
        ("Браслеты", "Bracelets", "bracelets", "Браслеты", "Bracelets"),
        ("Серьги", "Earrings", "earrings", "Серьги", "Earrings"),
        ("Подвески", "Pendants", "pendants", "Подвески", "Pendants"),
        ("Обручальные", "Wedding", "wedding", "Обручальные кольца", "Wedding rings"),
        ("Женские", "Women", "women", "Женские украшения", "Women's jewelry"),
        ("Мужские", "Men", "men", "Мужские украшения", "Men's jewelry"),
    ],
    "uslugi": [
        ("Ремонт квартир", "Apartment Renovation", "apartment-renovation", "Ремонт и отделка квартир", "Apartment renovation and finishing"),
        ("Перевозка грузов", "Cargo Transport", "cargo-transport", "Перевозка грузов", "Cargo transportation"),
        ("Карго", "Cargo", "cargo", "Карго и логистика", "Cargo and logistics"),
        ("Клининг", "Cleaning", "cleaning", "Клининговые услуги", "Cleaning services"),
        ("Консультации", "Consultations", "consultations", "Консультационные услуги", "Consultation services"),
        ("Диагностика", "Diagnostics", "diagnostics", "Диагностические услуги", "Diagnostic services"),
    ],
}

# Бренды: {primary_category_slug: [(name, desc_ru, desc_en, website), ...]}
BRANDS_DATA = {
    "medicines": [
        ("Abdi İbrahim", "Ведущий фармпроизводитель Турции.", "Leading Turkish pharmaceutical manufacturer.", "https://www.abdiibrahim.com.tr"),
        ("Deva Holding", "Фармацевтическая группа с широкой линейкой препаратов.", "Pharmaceutical group with a wide range of drugs.", "https://www.deva.com.tr"),
        ("Nobel İlaç", "Производитель препаратов для госпитального сегмента и аптек.", "Manufacturer of drugs for hospitals and pharmacies.", "https://www.nobelilac.com.tr"),
        ("Santa Farma", "Турецкая фармкомпания с историей более 75 лет.", "Turkish pharmaceutical company with over 75 years of history.", "https://www.santafarma.com.tr"),
        ("Bilim İlaç", "Одна из крупнейших фармацевтических компаний Турции.", "One of the largest pharmaceutical companies in Turkey.", "https://www.bilim.com.tr"),
        ("Pfizer", "Глобальный фармацевтический гигант.", "Global pharmaceutical giant.", "https://www.pfizer.com"),
        ("Bayer", "Немецкая фармацевтическая и химическая компания.", "German pharmaceutical and chemical company.", "https://www.bayer.com"),
        ("Sanofi", "Французская фармацевтическая компания.", "French pharmaceutical company.", "https://www.sanofi.com"),
    ],
    "supplements": [
        ("Solgar", "Американский производитель витаминов и БАДов.", "American manufacturer of vitamins and supplements.", "https://www.solgar.com"),
        ("Now Foods", "Производитель натуральных добавок.", "Natural supplements manufacturer.", "https://www.nowfoods.com"),
        ("Nature's Bounty", "Витамины и БАДы.", "Vitamins and dietary supplements.", "https://www.naturesbounty.com"),
    ],
    "clothing": [
        ("LC Waikiki", "Массовый fashion-ретейлер из Стамбула.", "Mass fashion retailer from Istanbul.", "https://www.lcwaikiki.com"),
        ("Mavi", "Деним и casual одежда турецкого происхождения.", "Turkish denim and casual wear.", "https://www.mavi.com"),
        ("Koton", "Сеть магазинов модной одежды.", "Fashion clothing store chain.", "https://www.koton.com"),
        ("DeFacto", "Pop-up fashion бренд для всей семьи.", "Pop-up fashion brand for the whole family.", "https://www.defacto.com.tr"),
        ("Zara", "Испанский бренд быстрой моды.", "Spanish fast fashion brand.", "https://www.zara.com"),
        ("H&M", "Шведский бренд одежды.", "Swedish clothing brand.", "https://www.hm.com"),
    ],
    "shoes": [
        ("Hotiç", "Сеть премиальной обуви и аксессуаров.", "Premium footwear and accessories chain.", "https://www.hotic.com.tr"),
        ("FLO", "Крупнейший обувной ретейлер Турции.", "Largest footwear retailer in Turkey.", "https://www.flo.com.tr"),
        ("Nike", "Американский спортивный бренд.", "American sports brand.", "https://www.nike.com"),
        ("Adidas", "Немецкий спортивный бренд.", "German sports brand.", "https://www.adidas.com"),
    ],
    "electronics": [
        ("Vestel", "Крупнейший производитель электроники и ТВ в Турции.", "Largest electronics and TV manufacturer in Turkey.", "https://www.vestel.com.tr"),
        ("Arçelik", "Производитель техники и электроники.", "Appliances and electronics manufacturer.", "https://www.arcelikglobal.com"),
        ("Beko", "Международный бренд бытовой техники.", "International home appliances brand.", "https://www.beko.com.tr"),
        ("Samsung", "Южнокорейский технологический гигант.", "South Korean technology giant.", "https://www.samsung.com"),
        ("Apple", "Американская технологическая компания.", "American technology company.", "https://www.apple.com"),
    ],
    "furniture": [
        ("Enza Home", "Современная мебель и декор.", "Modern furniture and decor.", "https://www.enzahome.com.tr"),
        ("Yataş", "Мебель и матрасы.", "Furniture and mattresses.", "https://www.yatasbedding.com.tr"),
        ("Doğtaş", "Мебель для дома и офиса.", "Furniture for home and office.", "https://www.dogtas.com"),
        ("IKEA", "Шведский производитель мебели.", "Swedish furniture manufacturer.", "https://www.ikea.com"),
    ],
    "tableware": [
        ("Karaca", "Посуда и товары для дома из Турции.", "Turkish tableware and home goods.", "https://www.karaca.com"),
        ("Paşabahçe", "Стеклянная посуда и бокалы.", "Glass tableware and glasses.", "https://www.pasabahce.com"),
        ("Kütahya Porselen", "Фарфор и сервизы.", "Porcelain and dinnerware sets.", "https://www.kutahyaporselen.com.tr"),
    ],
    "medical-equipment": [
        ("Alvimedica", "Стенты, катетеры и кардиология.", "Stents, catheters and cardiology.", "https://www.alvimedica.com"),
        ("Bıçakcılar", "Медицинские расходники и аппараты.", "Medical consumables and devices.", "https://www.bicakcilar.com"),
        ("Turkuaz Healthcare", "Оборудование и медтехника.", "Equipment and medical technology.", "https://www.turkuazhealthcare.com"),
    ],
    "perfumery": [
        ("Chanel", "Французский дом моды и парфюмерии.", "French fashion and perfume house.", "https://www.chanel.com"),
        ("Dior", "Французский luxury-бренд.", "French luxury brand.", "https://www.dior.com"),
        ("Atelier Rebul", "Турецкая нишевая парфюмерия.", "Turkish niche perfumery.", "https://www.atelierrebul.com"),
        ("Nishane", "Турецкая luxury-парфюмерия из Стамбула.", "Turkish luxury perfumery from Istanbul.", "https://www.nishane.com"),
        ("Ajmal", "Арабская парфюмерия. Oud, мускус.", "Arabian perfumery. Oud, musk.", "https://www.ajmalperfume.com"),
        ("Lattafa", "Популярная арабская парфюмерия.", "Popular Arabian perfumery.", "https://www.lattafa.com"),
    ],
    "sports": [
        ("Lescon", "Спортивная обувь и экипировка.", "Sports footwear and equipment.", "https://www.lescon.com.tr"),
        ("Nike", "Американский спортивный бренд.", "American sports brand.", "https://www.nike.com"),
        ("Adidas", "Немецкий спортивный бренд.", "German sports brand.", "https://www.adidas.com"),
        ("Puma", "Немецкий спортивный бренд.", "German sports brand.", "https://www.puma.com"),
        ("Decathlon", "Спортивные товары.", "Sports goods retailer.", "https://www.decathlon.com"),
    ],
    "auto-parts": [
        ("Tofaş", "Турецкий автопроизводитель.", "Turkish automobile manufacturer.", "https://www.tofas.com.tr"),
        ("Bosch", "Немецкий производитель автозапчастей.", "German auto parts manufacturer.", "https://www.bosch.com"),
        ("Ford Otosan", "Совместное предприятие Ford в Турции.", "Ford joint venture in Turkey.", "https://www.fordotosan.com.tr"),
    ],
    "islamic-clothing": [
        ("Tekbir", "Турецкий бренд исламской одежды.", "Turkish Islamic clothing brand.", ""),
        ("Armine", "Мусульманская одежда и хиджабы.", "Islamic clothing and hijabs.", ""),
    ],
    "incense": [
        ("Al Haramain", "Арабские благовония и oud.", "Arabian incense and oud.", "https://www.alharamainperfumes.com"),
        ("Surrati", "Традиционная арабская парфюмерия.", "Traditional Arabian perfumery.", ""),
    ],
}


def get_or_create_root_category(slug: str):
    """
    Создаёт/возвращает корневую категорию по slug.
    Используется в orders, scrapers, catalog.
    """
    from apps.catalog.models import Category, CategoryType, CategoryTranslation

    # Нормализуем slug (medical_equipment -> medical-equipment для поиска в ROOT_CATEGORIES)
    slug_normalized = slug.replace("_", "-").lower()
    preset = next((r for r in ROOT_CATEGORIES if r[0] == slug_normalized), None)

    if not preset:
        return Category.objects.filter(slug=slug_normalized, parent__isnull=True).first()

    slug_val, name_ru, name_en, desc_ru, desc_en, type_slug = preset
    cat_type = CategoryType.objects.filter(slug=type_slug).first()

    category, created = Category.objects.get_or_create(
        slug=slug_val,
        defaults={
            "name": name_ru,
            "description": desc_ru or name_ru,
            "category_type": cat_type,
            "parent": None,
            "is_active": True,
        },
    )

    if created:
        _ensure_category_translations(category, name_ru, name_en, desc_ru or name_ru, desc_en or name_en)

    return category


def _ensure_category_translations(category, name_ru: str, name_en: str, desc_ru: str, desc_en: str):
    """Создаёт или обновляет переводы категории для ru и en."""
    from apps.catalog.models import CategoryTranslation

    for locale, name, desc in [("ru", name_ru, desc_ru), ("en", name_en, desc_en)]:
        CategoryTranslation.objects.update_or_create(
            category=category,
            locale=locale,
            defaults={"name": name, "description": desc or ""},
        )


def get_root_category_slugs():
    """Возвращает список slug корневых категорий для choices в админке."""
    return [(r[0], r[0]) for r in ROOT_CATEGORIES]
