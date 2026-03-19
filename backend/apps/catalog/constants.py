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
# uslugi использует SERVICES_SUBCATEGORIES (вложенная иерархия), здесь пусто
SUB_CATEGORIES = {
    "uslugi": [],
}

# Услуги: многоуровневая иерархия под uslugi. Формат: (name_ru, name_en, slug, desc_ru, desc_en, children)
SERVICES_SUBCATEGORIES = [
    (
        "Ремонт помещений",
        "Renovation & Repair",
        "svc-renovation",
        "Ремонт и отделка помещений",
        "Renovation and repair of premises",
        [
            (
                "Ремонт квартир",
                "Apartment Renovation",
                "svc-apartment-renovation",
                "Ремонт квартир",
                "Apartment renovation",
                [
                    ("Косметический ремонт", "Cosmetic Repair", "svc-cosmetic-repair", "Косметический ремонт", "Cosmetic repair"),
                    ("Капитальный ремонт", "Major Renovation", "svc-major-renovation", "Капитальный ремонт", "Major renovation"),
                    ("Ремонт под ключ", "Turnkey Renovation", "svc-turnkey-renovation", "Ремонт под ключ", "Turnkey renovation"),
                    (
                        "Ремонт отдельных комнат",
                        "Room-by-Room Repair",
                        "svc-room-repair",
                        "Ремонт отдельных комнат",
                        "Room-by-room repair",
                        [
                            ("Ремонт кухни", "Kitchen Renovation", "svc-kitchen-renovation", "Ремонт кухни", "Kitchen renovation"),
                            ("Ремонт ванной комнаты", "Bathroom Renovation", "svc-bathroom-renovation", "Ремонт ванной", "Bathroom renovation"),
                            ("Ремонт санузла", "Toilet Renovation", "svc-toilet-renovation", "Ремонт санузла", "Toilet renovation"),
                            ("Ремонт спальни", "Bedroom Renovation", "svc-bedroom-renovation", "Ремонт спальни", "Bedroom renovation"),
                            ("Ремонт гостиной", "Living Room Renovation", "svc-living-room-renovation", "Ремонт гостиной", "Living room renovation"),
                            ("Ремонт детской", "Children's Room Renovation", "svc-children-room-renovation", "Ремонт детской", "Children's room renovation"),
                            ("Ремонт коридора", "Hallway Renovation", "svc-hallway-renovation", "Ремонт коридора", "Hallway renovation"),
                        ],
                    ),
                ],
            ),
            (
                "Ремонт домов",
                "House Renovation",
                "svc-house-renovation",
                "Ремонт домов",
                "House renovation",
                [
                    ("Капитальный ремонт дома", "Major House Renovation", "svc-major-house-renovation", "Капитальный ремонт дома", "Major house renovation"),
                    ("Ремонт фасада", "Facade Repair", "svc-facade-repair", "Ремонт фасада", "Facade repair"),
                    ("Ремонт цоколя", "Foundation Repair", "svc-foundation-repair", "Ремонт цоколя", "Foundation repair"),
                    ("Ремонт гаража", "Garage Repair", "svc-garage-repair", "Ремонт гаража", "Garage repair"),
                ],
            ),
            (
                "Ремонт коммерческих помещений",
                "Commercial Renovation",
                "svc-commercial-renovation",
                "Ремонт коммерческих помещений",
                "Commercial renovation",
                [
                    ("Ремонт офиса", "Office Renovation", "svc-office-renovation", "Ремонт офиса", "Office renovation"),
                    ("Ремонт магазина", "Shop Renovation", "svc-shop-renovation", "Ремонт магазина", "Shop renovation"),
                ],
            ),
        ],
    ),
    (
        "Отделочные работы",
        "Finishing Works",
        "svc-finishing",
        "Отделочные работы",
        "Finishing works",
        [
            (
                "Стены",
                "Walls",
                "svc-walls",
                "Отделка стен",
                "Wall finishing",
                [
                    (
                        "Штукатурка",
                        "Plastering",
                        "svc-plastering",
                        "Штукатурные работы",
                        "Plastering",
                        [
                            ("Гипсовая штукатурка", "Gypsum Plastering", "svc-gypsum-plastering", "Гипсовая штукатурка", "Gypsum plastering"),
                            ("Цементная штукатурка", "Cement Plastering", "svc-cement-plastering", "Цементная штукатурка", "Cement plastering"),
                            ("Декоративная штукатурка", "Decorative Plastering", "svc-decorative-plastering", "Декоративная штукатурка", "Decorative plastering"),
                        ],
                    ),
                    (
                        "Шпаклёвка",
                        "Puttying",
                        "svc-puttying",
                        "Шпаклёвочные работы",
                        "Puttying",
                        [
                            ("Стартовая", "Base Coat", "svc-base-coat", "Стартовая шпаклёвка", "Base coat putty"),
                            ("Финишная", "Finish Coat", "svc-finish-coat", "Финишная шпаклёвка", "Finish coat putty"),
                        ],
                    ),
                    (
                        "Покраска стен",
                        "Wall Painting",
                        "svc-wall-painting",
                        "Покраска стен",
                        "Wall painting",
                        [
                            ("Водоэмульсионная", "Emulsion Paint", "svc-emulsion-paint", "Водоэмульсионная краска", "Emulsion paint"),
                            ("Декоративная", "Decorative Paint", "svc-decorative-paint", "Декоративная краска", "Decorative paint"),
                        ],
                    ),
                    (
                        "Поклейка обоев",
                        "Wallpapering",
                        "svc-wallpapering",
                        "Поклейка обоев",
                        "Wallpapering",
                        [
                            ("Бумажные обои", "Paper Wallpaper", "svc-paper-wallpaper", "Бумажные обои", "Paper wallpaper"),
                            ("Виниловые обои", "Vinyl Wallpaper", "svc-vinyl-wallpaper", "Виниловые обои", "Vinyl wallpaper"),
                            ("Флизелиновые обои", "Non-Woven Wallpaper", "svc-nonwoven-wallpaper", "Флизелиновые обои", "Non-woven wallpaper"),
                            ("Жидкие обои", "Liquid Wallpaper", "svc-liquid-wallpaper", "Жидкие обои", "Liquid wallpaper"),
                        ],
                    ),
                    (
                        "Укладка плитки",
                        "Tile Installation",
                        "svc-wall-tile",
                        "Укладка настенной плитки",
                        "Wall tile installation",
                        [
                            ("Кафельная плитка", "Ceramic Tiles", "svc-ceramic-tiles", "Кафельная плитка", "Ceramic tiles"),
                            ("Мозаика", "Mosaic", "svc-mosaic", "Мозаика", "Mosaic"),
                            ("Керамогранит", "Porcelain Stoneware", "svc-porcelain-tile", "Керамогранит", "Porcelain stoneware"),
                        ],
                    ),
                    (
                        "Декоративные панели",
                        "Decorative Panels",
                        "svc-decorative-panels",
                        "Декоративные панели",
                        "Decorative panels",
                        [
                            ("Гипсокартон", "Drywall", "svc-drywall", "Гипсокартон", "Drywall"),
                            ("МДФ панели", "MDF Panels", "svc-mdf-panels", "МДФ панели", "MDF panels"),
                            ("Пластиковые панели", "PVC Panels", "svc-pvc-panels", "Пластиковые панели", "PVC panels"),
                        ],
                    ),
                ],
            ),
            (
                "Потолки",
                "Ceilings",
                "svc-ceilings",
                "Отделка потолков",
                "Ceiling finishing",
                [
                    (
                        "Натяжные потолки",
                        "Stretch Ceilings",
                        "svc-stretch-ceilings",
                        "Натяжные потолки",
                        "Stretch ceilings",
                        [
                            ("Одноуровневые", "Single-Level", "svc-single-level-ceiling", "Одноуровневые натяжные потолки", "Single-level stretch ceiling"),
                            ("Многоуровневые", "Multi-Level", "svc-multi-level-ceiling", "Многоуровневые натяжные потолки", "Multi-level stretch ceiling"),
                        ],
                    ),
                    (
                        "Подвесные потолки",
                        "Suspended Ceilings",
                        "svc-suspended-ceilings",
                        "Подвесные потолки",
                        "Suspended ceilings",
                        [
                            ("Потолок Армстронг", "Armstrong Ceiling", "svc-armstrong-ceiling", "Потолок Армстронг", "Armstrong ceiling"),
                            ("Реечный потолок", "Slatted Ceiling", "svc-slatted-ceiling", "Реечный потолок", "Slatted ceiling"),
                        ],
                    ),
                    ("Покраска потолка", "Ceiling Painting", "svc-ceiling-painting", "Покраска потолка", "Ceiling painting"),
                    ("Шпаклёвка потолка", "Ceiling Puttying", "svc-ceiling-puttying", "Шпаклёвка потолка", "Ceiling puttying"),
                    ("Гипсокартонные потолки", "Drywall Ceilings", "svc-drywall-ceilings", "Гипсокартонные потолки", "Drywall ceilings"),
                ],
            ),
            (
                "Полы",
                "Floors",
                "svc-floors",
                "Отделка полов",
                "Floor finishing",
                [
                    ("Укладка ламината", "Laminate Flooring", "svc-laminate", "Укладка ламината", "Laminate flooring"),
                    (
                        "Укладка паркета",
                        "Parquet Flooring",
                        "svc-parquet",
                        "Укладка паркета",
                        "Parquet flooring",
                        [
                            ("Штучный паркет", "Strip Parquet", "svc-strip-parquet", "Штучный паркет", "Strip parquet"),
                            ("Паркетная доска", "Engineered Parquet", "svc-engineered-parquet", "Паркетная доска", "Engineered parquet"),
                        ],
                    ),
                    (
                        "Укладка плитки",
                        "Floor Tile Installation",
                        "svc-floor-tile",
                        "Укладка напольной плитки",
                        "Floor tile installation",
                        [
                            ("Кафель", "Ceramic Tiles", "svc-floor-ceramic", "Напольный кафель", "Floor ceramic tiles"),
                            ("Керамогранит", "Porcelain Stoneware", "svc-floor-porcelain", "Напольный керамогранит", "Floor porcelain stoneware"),
                        ],
                    ),
                    ("Укладка линолеума", "Linoleum Installation", "svc-linoleum", "Укладка линолеума", "Linoleum installation"),
                    ("Укладка ковролина", "Carpet Installation", "svc-carpet", "Укладка ковролина", "Carpet installation"),
                    (
                        "Наливной пол",
                        "Self-Leveling Floor",
                        "svc-self-leveling",
                        "Наливной пол",
                        "Self-leveling floor",
                        [
                            ("Выравнивающий", "Leveling", "svc-leveling-floor", "Выравнивающий наливной пол", "Leveling self-leveling floor"),
                            ("Декоративный", "Decorative", "svc-decorative-floor", "Декоративный наливной пол", "Decorative self-leveling floor"),
                        ],
                    ),
                    (
                        "Стяжка пола",
                        "Floor Screed",
                        "svc-floor-screed",
                        "Стяжка пола",
                        "Floor screed",
                        [
                            ("Мокрая стяжка", "Wet Screed", "svc-wet-screed", "Мокрая стяжка", "Wet screed"),
                            ("Сухая стяжка", "Dry Screed", "svc-dry-screed", "Сухая стяжка", "Dry screed"),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "Сантехника",
        "Plumbing",
        "svc-plumbing",
        "Сантехнические работы",
        "Plumbing works",
        [
            (
                "Установка и замена",
                "Installation & Replacement",
                "svc-plumbing-install",
                "Установка и замена сантехники",
                "Plumbing installation and replacement",
                [
                    ("Унитаз", "Toilet Installation", "svc-toilet-install", "Установка унитаза", "Toilet installation"),
                    ("Раковина", "Sink Installation", "svc-sink-install", "Установка раковины", "Sink installation"),
                    (
                        "Ванна",
                        "Bathtub Installation",
                        "svc-bathtub-install",
                        "Установка ванны",
                        "Bathtub installation",
                        [
                            ("Чугунная ванна", "Cast Iron Bathtub", "svc-cast-iron-bathtub", "Чугунная ванна", "Cast iron bathtub"),
                            ("Акриловая ванна", "Acrylic Bathtub", "svc-acrylic-bathtub", "Акриловая ванна", "Acrylic bathtub"),
                        ],
                    ),
                    ("Душевая кабина", "Shower Cabin Installation", "svc-shower-cabin", "Установка душевой кабины", "Shower cabin installation"),
                    ("Поддон", "Shower Tray Installation", "svc-shower-tray", "Установка поддона", "Shower tray installation"),
                    ("Смесители", "Faucet Installation", "svc-faucet-install", "Установка смесителей", "Faucet installation"),
                    ("Счётчики воды", "Water Meter Installation", "svc-water-meter", "Установка счётчиков воды", "Water meter installation"),
                    ("Фильтры воды", "Water Filter Installation", "svc-water-filter", "Установка фильтров воды", "Water filter installation"),
                ],
            ),
            (
                "Трубопровод",
                "Piping",
                "svc-piping",
                "Трубопроводные работы",
                "Piping works",
                [
                    (
                        "Прокладка труб",
                        "Pipe Installation",
                        "svc-pipe-install",
                        "Прокладка труб",
                        "Pipe installation",
                        [
                            ("Полипропиленовые", "Polypropylene", "svc-polypropylene-pipes", "Полипропиленовые трубы", "Polypropylene pipes"),
                            ("Металлопластиковые", "Metal-Plastic", "svc-metal-plastic-pipes", "Металлопластиковые трубы", "Metal-plastic pipes"),
                            ("Медные", "Copper", "svc-copper-pipes", "Медные трубы", "Copper pipes"),
                        ],
                    ),
                    ("Замена труб", "Pipe Replacement", "svc-pipe-replacement", "Замена труб", "Pipe replacement"),
                    ("Разводка водоснабжения", "Water Supply Layout", "svc-water-supply-layout", "Разводка водоснабжения", "Water supply layout"),
                ],
            ),
            (
                "Канализация",
                "Sewage",
                "svc-sewage",
                "Канализационные работы",
                "Sewage works",
                [
                    ("Монтаж канализации", "Sewage Installation", "svc-sewage-install", "Монтаж канализации", "Sewage installation"),
                    ("Прочистка канализации", "Drain Cleaning", "svc-drain-cleaning", "Прочистка канализации", "Drain cleaning"),
                ],
            ),
        ],
    ),
    (
        "Электрика",
        "Electrical Works",
        "svc-electrical",
        "Электромонтажные работы",
        "Electrical works",
        [
            (
                "Монтаж проводки",
                "Wiring Installation",
                "svc-wiring",
                "Монтаж электропроводки",
                "Wiring installation",
                [
                    ("Открытая проводка", "Open Wiring", "svc-open-wiring", "Открытая проводка", "Open wiring"),
                    ("Скрытая проводка", "Concealed Wiring", "svc-concealed-wiring", "Скрытая проводка", "Concealed wiring"),
                ],
            ),
            (
                "Установка электроустановок",
                "Electrical Fixtures",
                "svc-electrical-fixtures",
                "Установка электроустановок",
                "Electrical fixtures installation",
                [
                    ("Розетки", "Outlets", "svc-outlets", "Установка розеток", "Outlets"),
                    ("Выключатели", "Switches", "svc-switches", "Установка выключателей", "Switches"),
                    ("Люстры", "Chandeliers", "svc-chandeliers", "Установка люстр", "Chandeliers"),
                    ("Светильники", "Light Fixtures", "svc-light-fixtures", "Установка светильников", "Light fixtures"),
                    ("Прожекторы", "Spotlights", "svc-spotlights", "Установка прожекторов", "Spotlights"),
                    ("Подсветка", "LED Strip Lighting", "svc-led-strip", "Установка LED подсветки", "LED strip lighting"),
                ],
            ),
            (
                "Щитки и автоматы",
                "Electrical Panels",
                "svc-electrical-panels",
                "Щитки и автоматы",
                "Electrical panels",
                [
                    ("Монтаж щитка", "Panel Installation", "svc-panel-install", "Монтаж щитка", "Panel installation"),
                    ("Замена автоматов", "Breaker Replacement", "svc-breaker-replacement", "Замена автоматов", "Breaker replacement"),
                ],
            ),
            ("Заземление", "Grounding", "svc-grounding", "Заземление", "Grounding"),
            ("Монтаж тёплого пола (электрического)", "Electric Underfloor Heating", "svc-electric-floor-heating", "Электрический тёплый пол", "Electric underfloor heating"),
            ("Умный дом", "Smart Home Wiring", "svc-smart-home", "Умный дом", "Smart home wiring"),
        ],
    ),
    (
        "Климатическая техника",
        "Climate Equipment",
        "svc-climate",
        "Климатическое оборудование",
        "Climate equipment",
        [
            (
                "Кондиционеры",
                "Air Conditioners",
                "svc-ac",
                "Услуги по кондиционерам",
                "Air conditioner services",
                [
                    ("Установка кондиционера", "AC Installation", "svc-ac-install", "Установка кондиционера", "AC installation"),
                    ("Демонтаж кондиционера", "AC Removal", "svc-ac-removal", "Демонтаж кондиционера", "AC removal"),
                    ("Перенос кондиционера", "AC Relocation", "svc-ac-relocation", "Перенос кондиционера", "AC relocation"),
                    ("Чистка и обслуживание", "AC Cleaning & Maintenance", "svc-ac-cleaning", "Чистка и обслуживание кондиционера", "AC cleaning and maintenance"),
                    ("Заправка фреоном", "Refrigerant Refill", "svc-refrigerant-refill", "Заправка фреоном", "Refrigerant refill"),
                ],
            ),
            (
                "Тёплый пол",
                "Underfloor Heating",
                "svc-underfloor-heating",
                "Тёплый пол",
                "Underfloor heating",
                [
                    ("Водяной тёплый пол", "Water Underfloor Heating", "svc-water-floor-heating", "Водяной тёплый пол", "Water underfloor heating"),
                    ("Электрический тёплый пол", "Electric Underfloor Heating", "svc-electric-floor-heat", "Электрический тёплый пол", "Electric underfloor heating"),
                    ("Инфракрасный тёплый пол", "Infrared Underfloor Heating", "svc-infrared-floor-heating", "Инфракрасный тёплый пол", "Infrared underfloor heating"),
                ],
            ),
            (
                "Бойлеры",
                "Water Heaters",
                "svc-water-heaters",
                "Бойлеры и водонагреватели",
                "Water heaters",
                [
                    ("Установка бойлера", "Water Heater Installation", "svc-boiler-install", "Установка бойлера", "Water heater installation"),
                    ("Замена бойлера", "Water Heater Replacement", "svc-boiler-replacement", "Замена бойлера", "Water heater replacement"),
                    ("Обслуживание бойлера", "Water Heater Maintenance", "svc-boiler-maintenance", "Обслуживание бойлера", "Water heater maintenance"),
                ],
            ),
            (
                "Обогреватели",
                "Heaters",
                "svc-heaters",
                "Обогреватели",
                "Heaters",
                [
                    ("Установка обогревателя", "Heater Installation", "svc-heater-install", "Установка обогревателя", "Heater installation"),
                    ("Монтаж радиаторов", "Radiator Installation", "svc-radiator-install", "Монтаж радиаторов", "Radiator installation"),
                ],
            ),
            (
                "Вентиляция",
                "Ventilation",
                "svc-ventilation",
                "Вентиляция",
                "Ventilation",
                [
                    ("Монтаж вентиляции", "Ventilation Installation", "svc-ventilation-install", "Монтаж вентиляции", "Ventilation installation"),
                    ("Вытяжки", "Exhaust Fan Installation", "svc-exhaust-fan", "Установка вытяжек", "Exhaust fan installation"),
                    ("Рекуператоры", "Heat Recovery Units", "svc-heat-recovery", "Рекуператоры", "Heat recovery units"),
                ],
            ),
        ],
    ),
    (
        "Кровельные работы",
        "Roofing Works",
        "svc-roofing",
        "Кровельные работы",
        "Roofing works",
        [
            (
                "Монтаж кровли",
                "Roof Installation",
                "svc-roof-install",
                "Монтаж кровли",
                "Roof installation",
                [
                    (
                        "Мягкая кровля",
                        "Soft Roofing",
                        "svc-soft-roofing",
                        "Мягкая кровля",
                        "Soft roofing",
                        [
                            ("Битумная черепица", "Asphalt Shingles", "svc-asphalt-shingles", "Битумная черепица", "Asphalt shingles"),
                            ("Рулонная кровля", "Roll Roofing", "svc-roll-roofing", "Рулонная кровля", "Roll roofing"),
                        ],
                    ),
                    (
                        "Твёрдая кровля",
                        "Hard Roofing",
                        "svc-hard-roofing",
                        "Твёрдая кровля",
                        "Hard roofing",
                        [
                            ("Металлочерепица", "Metal Tiles", "svc-metal-tiles", "Металлочерепица", "Metal tiles"),
                            ("Профнастил", "Corrugated Metal", "svc-corrugated-metal", "Профнастил", "Corrugated metal"),
                            ("Керамическая черепица", "Ceramic Tiles", "svc-ceramic-roof-tiles", "Керамическая черепица", "Ceramic roof tiles"),
                            ("Сланец", "Slate", "svc-slate", "Сланец", "Slate"),
                        ],
                    ),
                    ("Плоская кровля", "Flat Roofing", "svc-flat-roofing", "Плоская кровля", "Flat roofing"),
                ],
            ),
            (
                "Ремонт кровли",
                "Roof Repair",
                "svc-roof-repair",
                "Ремонт кровли",
                "Roof repair",
                [
                    ("Заделка трещин", "Crack Sealing", "svc-crack-sealing", "Заделка трещин", "Crack sealing"),
                    ("Замена повреждённых участков", "Damaged Section Replacement", "svc-damaged-section-replacement", "Замена повреждённых участков", "Damaged section replacement"),
                ],
            ),
            ("Утепление кровли", "Roof Insulation", "svc-roof-insulation", "Утепление кровли", "Roof insulation"),
            (
                "Водосточные системы",
                "Drainage Systems",
                "svc-drainage",
                "Водосточные системы",
                "Drainage systems",
                [
                    ("Монтаж водостока", "Gutter Installation", "svc-gutter-install", "Монтаж водостока", "Gutter installation"),
                    ("Чистка водостока", "Gutter Cleaning", "svc-gutter-cleaning", "Чистка водостока", "Gutter cleaning"),
                ],
            ),
            ("Снегозадержатели", "Snow Guards Installation", "svc-snow-guards", "Снегозадержатели", "Snow guards installation"),
        ],
    ),
    (
        "Окна и балконы",
        "Windows & Balconies",
        "svc-windows-balconies",
        "Окна и балконы",
        "Windows and balconies",
        [
            (
                "Окна",
                "Windows",
                "svc-windows",
                "Окна",
                "Windows",
                [
                    (
                        "Установка окон",
                        "Window Installation",
                        "svc-window-install",
                        "Установка окон",
                        "Window installation",
                        [
                            ("Пластиковые окна", "PVC Windows", "svc-pvc-windows", "Пластиковые окна", "PVC windows"),
                            ("Деревянные окна", "Wooden Windows", "svc-wooden-windows", "Деревянные окна", "Wooden windows"),
                            ("Алюминиевые окна", "Aluminum Windows", "svc-aluminum-windows", "Алюминиевые окна", "Aluminum windows"),
                        ],
                    ),
                    ("Замена стеклопакета", "Glass Unit Replacement", "svc-glass-unit-replacement", "Замена стеклопакета", "Glass unit replacement"),
                    ("Регулировка окон", "Window Adjustment", "svc-window-adjustment", "Регулировка окон", "Window adjustment"),
                    ("Утепление откосов", "Slope Insulation", "svc-slope-insulation", "Утепление откосов", "Slope insulation"),
                ],
            ),
            (
                "Балконы и лоджии",
                "Balconies & Loggias",
                "svc-balconies",
                "Балконы и лоджии",
                "Balconies and loggias",
                [
                    (
                        "Остекление балкона",
                        "Balcony Glazing",
                        "svc-balcony-glazing",
                        "Остекление балкона",
                        "Balcony glazing",
                        [
                            ("Холодное остекление", "Cold Glazing", "svc-cold-glazing", "Холодное остекление", "Cold glazing"),
                            ("Тёплое остекление", "Warm Glazing", "svc-warm-glazing", "Тёплое остекление", "Warm glazing"),
                        ],
                    ),
                    ("Утепление балкона", "Balcony Insulation", "svc-balcony-insulation", "Утепление балкона", "Balcony insulation"),
                    (
                        "Обшивка балкона",
                        "Balcony Cladding",
                        "svc-balcony-cladding",
                        "Обшивка балкона",
                        "Balcony cladding",
                        [
                            ("Вагонка", "Lining Board", "svc-lining-board", "Обшивка вагонкой", "Lining board"),
                            ("МДФ панели", "MDF Panels", "svc-balcony-mdf-panels", "Обшивка МДФ панелями", "MDF panels"),
                        ],
                    ),
                    ("Объединение балкона с комнатой", "Balcony Integration", "svc-balcony-integration", "Объединение балкона с комнатой", "Balcony integration"),
                    ("Ремонт балкона под ключ", "Full Balcony Renovation", "svc-full-balcony-renovation", "Ремонт балкона под ключ", "Full balcony renovation"),
                ],
            ),
            (
                "Двери",
                "Doors",
                "svc-doors",
                "Двери",
                "Doors",
                [
                    (
                        "Установка входной двери",
                        "Front Door Installation",
                        "svc-front-door",
                        "Установка входной двери",
                        "Front door installation",
                        [
                            ("Металлическая", "Metal", "svc-metal-door", "Металлическая дверь", "Metal door"),
                            ("Деревянная", "Wooden", "svc-wooden-door", "Деревянная дверь", "Wooden door"),
                        ],
                    ),
                    ("Установка межкомнатных дверей", "Interior Door Installation", "svc-interior-door", "Установка межкомнатных дверей", "Interior door installation"),
                    ("Установка раздвижных дверей", "Sliding Door Installation", "svc-sliding-door", "Установка раздвижных дверей", "Sliding door installation"),
                    ("Регулировка дверей", "Door Adjustment", "svc-door-adjustment", "Регулировка дверей", "Door adjustment"),
                ],
            ),
        ],
    ),
    (
        "Установка мебели и техники",
        "Furniture & Appliance Installation",
        "svc-furniture-appliance",
        "Установка мебели и техники",
        "Furniture and appliance installation",
        [
            (
                "Сборка мебели",
                "Furniture Assembly",
                "svc-furniture-assembly",
                "Сборка мебели",
                "Furniture assembly",
                [
                    ("Кухонный гарнитур", "Kitchen Cabinet Assembly", "svc-kitchen-cabinet", "Сборка кухонного гарнитура", "Kitchen cabinet assembly"),
                    ("Шкаф-купе", "Sliding Wardrobe Assembly", "svc-sliding-wardrobe", "Сборка шкафа-купе", "Sliding wardrobe assembly"),
                    ("Кровать", "Bed Assembly", "svc-bed-assembly", "Сборка кровати", "Bed assembly"),
                    ("Диван", "Sofa Assembly", "svc-sofa-assembly", "Сборка дивана", "Sofa assembly"),
                    ("Стол и стулья", "Table & Chairs Assembly", "svc-table-chairs-assembly", "Сборка стола и стульев", "Table and chairs assembly"),
                    ("Детская мебель", "Children's Furniture Assembly", "svc-children-furniture", "Сборка детской мебели", "Children's furniture assembly"),
                ],
            ),
            (
                "Установка бытовой техники",
                "Home Appliance Installation",
                "svc-appliance-install",
                "Установка бытовой техники",
                "Home appliance installation",
                [
                    ("Стиральная машина", "Washing Machine Installation", "svc-washing-machine", "Установка стиральной машины", "Washing machine installation"),
                    ("Посудомоечная машина", "Dishwasher Installation", "svc-dishwasher", "Установка посудомоечной машины", "Dishwasher installation"),
                    ("Холодильник", "Refrigerator Installation", "svc-refrigerator", "Установка холодильника", "Refrigerator installation"),
                    ("Духовой шкаф", "Oven Installation", "svc-oven", "Установка духового шкафа", "Oven installation"),
                    (
                        "Варочная поверхность",
                        "Cooktop Installation",
                        "svc-cooktop",
                        "Установка варочной поверхности",
                        "Cooktop installation",
                        [
                            ("Газовая", "Gas", "svc-gas-cooktop", "Газовая варочная поверхность", "Gas cooktop"),
                            ("Электрическая", "Electric", "svc-electric-cooktop", "Электрическая варочная поверхность", "Electric cooktop"),
                        ],
                    ),
                    ("Вытяжка", "Range Hood Installation", "svc-range-hood", "Установка вытяжки", "Range hood installation"),
                    ("Микроволновка", "Microwave Installation", "svc-microwave", "Установка микроволновки", "Microwave installation"),
                    ("Встроенная техника", "Built-In Appliance Installation", "svc-built-in-appliance", "Установка встроенной техники", "Built-in appliance installation"),
                ],
            ),
            (
                "Навеска",
                "Wall Mounting",
                "svc-wall-mounting",
                "Навеска и монтаж",
                "Wall mounting",
                [
                    ("Телевизор", "TV Wall Mounting", "svc-tv-mounting", "Навеска телевизора", "TV wall mounting"),
                    ("Полки", "Shelf Installation", "svc-shelf-install", "Установка полок", "Shelf installation"),
                    ("Картины и зеркала", "Picture & Mirror Hanging", "svc-picture-mirror", "Навеска картин и зеркал", "Picture and mirror hanging"),
                    ("Карнизы", "Curtain Rod Installation", "svc-curtain-rod", "Установка карнизов", "Curtain rod installation"),
                    ("Шторы", "Curtain Hanging", "svc-curtain-hanging", "Навеска штор", "Curtain hanging"),
                ],
            ),
            (
                "Монтаж кухни",
                "Kitchen Installation",
                "svc-kitchen-install",
                "Монтаж кухни",
                "Kitchen installation",
                [
                    ("Сборка и установка гарнитура", "Cabinet Installation", "svc-cabinet-install", "Сборка и установка гарнитура", "Cabinet installation"),
                    ("Установка мойки", "Sink Installation", "svc-kitchen-sink", "Установка мойки", "Sink installation"),
                    ("Подключение техники", "Appliance Connection", "svc-appliance-connection", "Подключение техники", "Appliance connection"),
                ],
            ),
        ],
    ),
    (
        "Утепление и изоляция",
        "Insulation Works",
        "svc-insulation",
        "Утепление и изоляция",
        "Insulation works",
        [
            (
                "Утепление стен",
                "Wall Insulation",
                "svc-wall-insulation",
                "Утепление стен",
                "Wall insulation",
                [
                    ("Наружное утепление", "External Insulation", "svc-external-insulation", "Наружное утепление", "External insulation"),
                    ("Внутреннее утепление", "Internal Insulation", "svc-internal-insulation", "Внутреннее утепление", "Internal insulation"),
                ],
            ),
            ("Утепление пола", "Floor Insulation", "svc-floor-insulation", "Утепление пола", "Floor insulation"),
            ("Утепление потолка", "Ceiling Insulation", "svc-ceiling-insulation", "Утепление потолка", "Ceiling insulation"),
            ("Утепление кровли", "Roof Insulation", "svc-insulation-roof", "Утепление кровли", "Roof insulation"),
            (
                "Шумоизоляция",
                "Soundproofing",
                "svc-soundproofing",
                "Шумоизоляция",
                "Soundproofing",
                [
                    ("Стены", "Walls", "svc-soundproof-walls", "Шумоизоляция стен", "Wall soundproofing"),
                    ("Потолок", "Ceiling", "svc-soundproof-ceiling", "Шумоизоляция потолка", "Ceiling soundproofing"),
                    ("Пол", "Floor", "svc-soundproof-floor", "Шумоизоляция пола", "Floor soundproofing"),
                ],
            ),
            (
                "Гидроизоляция",
                "Waterproofing",
                "svc-waterproofing",
                "Гидроизоляция",
                "Waterproofing",
                [
                    ("Ванной и санузла", "Bathroom", "svc-bathroom-waterproofing", "Гидроизоляция ванной и санузла", "Bathroom waterproofing"),
                    ("Подвала", "Basement", "svc-basement-waterproofing", "Гидроизоляция подвала", "Basement waterproofing"),
                ],
            ),
        ],
    ),
    (
        "Прочие услуги",
        "Other Services",
        "svc-other",
        "Прочие услуги",
        "Other services",
        [
            (
                "Демонтажные работы",
                "Demolition Works",
                "svc-demolition",
                "Демонтажные работы",
                "Demolition works",
                [
                    ("Снос перегородок", "Partition Demolition", "svc-partition-demolition", "Снос перегородок", "Partition demolition"),
                    ("Демонтаж плитки", "Tile Removal", "svc-tile-removal", "Демонтаж плитки", "Tile removal"),
                    ("Демонтаж стяжки", "Screed Removal", "svc-screed-removal", "Демонтаж стяжки", "Screed removal"),
                ],
            ),
            (
                "Перепланировка",
                "Remodeling",
                "svc-remodeling",
                "Перепланировка",
                "Remodeling",
                [
                    ("Возведение перегородок", "Partition Construction", "svc-partition-construction", "Возведение перегородок", "Partition construction"),
                    ("Объединение комнат", "Room Merging", "svc-room-merging", "Объединение комнат", "Room merging"),
                ],
            ),
            ("Уборка после ремонта", "Post-Renovation Cleaning", "svc-post-renovation-cleaning", "Уборка после ремонта", "Post-renovation cleaning"),
            ("Вывоз строительного мусора", "Construction Waste Removal", "svc-construction-waste", "Вывоз строительного мусора", "Construction waste removal"),
        ],
    ),
]

# Обувь: 3 уровня — L2 под shoes, L3 под каждым L2.
# Формат: [(name_ru, name_en, slug, desc_ru, desc_en, children), ...], children = [(name_ru, name_en, slug, desc_ru, desc_en), ...]
SHOE_SUBCATEGORIES = [
    (
        "Сапоги",
        "Boots",
        "boots",
        "Сапоги",
        "Boots",
        [
            ("Сапоги", "Boots", "boots-classic", "Классические сапоги", "Classic boots"),
            ("Полусапоги", "Ankle Boots", "ankle-boots", "Полусапоги", "Ankle boots"),
            ("Угги", "Ugg Boots", "ugg-boots", "Угги", "Ugg boots"),
            ("Резиновые сапоги", "Rain Boots", "rain-boots", "Резиновые сапоги", "Rain boots"),
            ("Валенки", "Felt Boots", "felt-boots", "Валенки", "Felt boots"),
        ],
    ),
    (
        "Туфли",
        "Dress Shoes",
        "dress-shoes",
        "Туфли",
        "Dress shoes",
        [
            ("Оксфорды", "Oxfords", "oxfords", "Оксфорды", "Oxfords"),
            ("Дерби", "Derby Shoes", "derby", "Дерби", "Derby shoes"),
            ("Броги", "Brogues", "brogues", "Броги", "Brogues"),
            ("Монки", "Monk Strap", "monk-strap", "Монки", "Monk strap shoes"),
            ("Лоферы", "Loafers", "loafers", "Лоферы", "Loafers"),
        ],
    ),
    (
        "Повседневная обувь",
        "Casual Shoes",
        "casual-shoes",
        "Повседневная обувь",
        "Casual shoes",
        [
            ("Мокасины", "Moccasins", "moccasins", "Мокасины", "Moccasins"),
            ("Топсайдеры", "Boat Shoes", "boat-shoes", "Топсайдеры", "Boat shoes"),
            ("Слипоны", "Slip-ons", "slip-ons", "Слипоны", "Slip-ons"),
            ("Эспадрильи", "Espadrilles", "espadrilles", "Эспадрильи", "Espadrilles"),
        ],
    ),
    (
        "Кроссовки",
        "Sneakers",
        "sneakers",
        "Кроссовки",
        "Sneakers",
        [
            ("Беговые", "Running Shoes", "running-shoes", "Беговые кроссовки", "Running shoes"),
            ("Баскетбольные", "Basketball Shoes", "basketball-shoes", "Баскетбольные кроссовки", "Basketball shoes"),
            ("Скейт", "Skate Shoes", "skate-shoes", "Скейтборд обувь", "Skate shoes"),
            ("Тренировочные", "Training Shoes", "training-shoes", "Тренировочные кроссовки", "Training shoes"),
        ],
    ),
    (
        "Сандалии",
        "Sandals",
        "sandals",
        "Сандалии",
        "Sandals",
        [
            ("Сандалии", "Sandals", "sandals-classic", "Классические сандалии", "Classic sandals"),
            ("Шлёпанцы", "Flip-flops", "flip-flops", "Шлёпанцы", "Flip-flops"),
            ("Слайды", "Slides", "slides", "Слайды", "Slides"),
            ("Сабо", "Clogs", "clogs", "Сабо", "Clogs"),
        ],
    ),
    (
        "Домашняя обувь",
        "Home Shoes",
        "home-shoes",
        "Домашняя обувь",
        "Home shoes",
        [
            ("Тапочки", "Slippers", "slippers", "Тапочки", "Slippers"),
        ],
    ),
]

# Одежда: 3–4 уровня под clothing. Спортивная одежда и Нижнее бельё — отдельные корни (sports, underwear).
# Формат: [(name_ru, name_en, slug, desc_ru, desc_en, children), ...], children могут иметь своих children (L4).
CLOTHING_SUBCATEGORIES = [
    (
        "Верхняя одежда",
        "Outerwear",
        "outerwear",
        "Верхняя одежда",
        "Outerwear",
        [
            ("Пальто", "Coats", "coats", "Пальто", "Coats"),
            ("Плащи", "Trench Coats", "trench-coats", "Плащи", "Trench coats"),
            (
                "Куртки",
                "Jackets",
                "jackets",
                "Куртки",
                "Jackets",
                [
                    ("Кожаные куртки", "Leather Jackets", "leather-jackets", "Кожаные куртки", "Leather jackets"),
                    ("Джинсовые куртки", "Denim Jackets", "denim-jackets", "Джинсовые куртки", "Denim jackets"),
                    ("Бомберы", "Bomber Jackets", "bomber-jackets", "Бомберы", "Bomber jackets"),
                    ("Ветровки", "Windbreakers", "windbreakers", "Ветровки", "Windbreakers"),
                ],
            ),
            ("Пуховики", "Down Jackets", "down-jackets", "Пуховики", "Down jackets"),
            ("Парки", "Parkas", "parkas", "Парки", "Parkas"),
            ("Жилеты", "Vests", "vests", "Жилеты", "Vests"),
        ],
    ),
    (
        "Верх",
        "Tops",
        "tops",
        "Верхняя одежда",
        "Tops",
        [
            (
                "Футболки",
                "T-Shirts",
                "t-shirts",
                "Футболки",
                "T-Shirts",
                [
                    ("Базовые футболки", "Basic T-Shirts", "basic-tshirts", "Базовые футболки", "Basic T-shirts"),
                    ("Поло", "Polo Shirts", "polo-shirts", "Поло", "Polo shirts"),
                    ("Лонгсливы", "Long Sleeve T-Shirts", "long-sleeve-tshirts", "Лонгсливы", "Long sleeve T-shirts"),
                ],
            ),
            (
                "Рубашки",
                "Shirts",
                "shirts",
                "Рубашки",
                "Shirts",
                [
                    ("Классические рубашки", "Dress Shirts", "dress-shirts", "Классические рубашки", "Dress shirts"),
                    ("Повседневные рубашки", "Casual Shirts", "casual-shirts", "Повседневные рубашки", "Casual shirts"),
                    ("Джинсовые рубашки", "Denim Shirts", "denim-shirts", "Джинсовые рубашки", "Denim shirts"),
                ],
            ),
            ("Блузки", "Blouses", "blouses", "Блузки", "Blouses"),
            ("Топы", "Tops", "tops-items", "Топы", "Tops"),
            ("Майки", "Tank Tops", "tank-tops", "Майки", "Tank tops"),
            ("Кроп-топы", "Crop Tops", "crop-tops", "Кроп-топы", "Crop tops"),
        ],
    ),
    (
        "Трикотаж",
        "Knitwear",
        "knitwear",
        "Трикотаж",
        "Knitwear",
        [
            ("Свитеры", "Sweaters", "sweaters", "Свитеры", "Sweaters"),
            ("Кардиганы", "Cardigans", "cardigans", "Кардиганы", "Cardigans"),
            ("Джемперы", "Jumpers", "jumpers", "Джемперы", "Jumpers"),
            ("Пуловеры", "Pullovers", "pullovers", "Пуловеры", "Pullovers"),
            ("Водолазки", "Turtlenecks", "turtlenecks", "Водолазки", "Turtlenecks"),
            ("Худии", "Hoodies", "hoodies", "Худии", "Hoodies"),
        ],
    ),
    (
        "Низ",
        "Bottoms",
        "bottoms",
        "Низ",
        "Bottoms",
        [
            (
                "Брюки",
                "Pants",
                "pants",
                "Брюки",
                "Pants",
                [
                    ("Классические брюки", "Dress Pants", "dress-pants", "Классические брюки", "Dress pants"),
                    ("Чиносы", "Chinos", "chinos", "Чиносы", "Chinos"),
                    ("Карго", "Cargo Pants", "cargo-pants", "Карго", "Cargo pants"),
                    ("Льняные брюки", "Linen Pants", "linen-pants", "Льняные брюки", "Linen pants"),
                ],
            ),
            (
                "Джинсы",
                "Jeans",
                "jeans",
                "Джинсы",
                "Jeans",
                [
                    ("Skinny Jeans", "Skinny Jeans", "skinny-jeans", "Узкие джинсы", "Skinny jeans"),
                    ("Slim Jeans", "Slim Jeans", "slim-jeans", "Зауженные джинсы", "Slim jeans"),
                    ("Straight Jeans", "Straight Jeans", "straight-jeans", "Прямые джинсы", "Straight jeans"),
                    ("Wide Jeans", "Wide Jeans", "wide-jeans", "Широкие джинсы", "Wide jeans"),
                ],
            ),
            ("Шорты", "Shorts", "shorts", "Шорты", "Shorts"),
            (
                "Юбки",
                "Skirts",
                "skirts",
                "Юбки",
                "Skirts",
                [
                    ("Мини-юбки", "Mini Skirts", "mini-skirts", "Мини-юбки", "Mini skirts"),
                    ("Миди-юбки", "Midi Skirts", "midi-skirts", "Миди-юбки", "Midi skirts"),
                    ("Макси-юбки", "Maxi Skirts", "maxi-skirts", "Макси-юбки", "Maxi skirts"),
                    ("Джинсовые юбки", "Denim Skirts", "denim-skirts", "Джинсовые юбки", "Denim skirts"),
                ],
            ),
            ("Леггинсы", "Leggings", "leggings", "Леггинсы", "Leggings"),
        ],
    ),
    (
        "Платья",
        "Dresses",
        "dresses",
        "Платья",
        "Dresses",
        [
            ("Повседневные платья", "Casual Dresses", "casual-dresses", "Повседневные платья", "Casual dresses"),
            ("Вечерние платья", "Evening Dresses", "evening-dresses", "Вечерние платья", "Evening dresses"),
            ("Коктейльные платья", "Cocktail Dresses", "cocktail-dresses", "Коктейльные платья", "Cocktail dresses"),
            ("Летние платья", "Summer Dresses", "summer-dresses", "Летние платья", "Summer dresses"),
            ("Платья-рубашки", "Shirt Dresses", "shirt-dresses", "Платья-рубашки", "Shirt dresses"),
            ("Макси-платья", "Maxi Dresses", "maxi-dresses", "Макси-платья", "Maxi dresses"),
        ],
    ),
    (
        "Костюмы",
        "Suits",
        "suits",
        "Костюмы",
        "Suits",
        [
            ("Деловые костюмы", "Business Suits", "business-suits", "Деловые костюмы", "Business suits"),
            ("Смокинги", "Tuxedos", "tuxedos", "Смокинги", "Tuxedos"),
            ("Брючные костюмы", "Pantsuits", "pantsuits", "Брючные костюмы", "Pantsuits"),
            ("Спортивные костюмы", "Tracksuits", "tracksuits", "Спортивные костюмы", "Tracksuits"),
        ],
    ),
    (
        "Домашняя одежда",
        "Loungewear",
        "loungewear",
        "Домашняя одежда",
        "Loungewear",
        [
            ("Домашние костюмы", "Lounge Sets", "lounge-sets", "Домашние костюмы", "Lounge sets"),
            ("Халаты", "Robes", "robes", "Халаты", "Robes"),
            ("Домашние брюки", "Lounge Pants", "lounge-pants", "Домашние брюки", "Lounge pants"),
            ("Домашние футболки", "Lounge T-Shirts", "lounge-tshirts", "Домашние футболки", "Lounge T-shirts"),
        ],
    ),
    (
        "Ночная одежда",
        "Sleepwear",
        "sleepwear",
        "Ночная одежда",
        "Sleepwear",
        [
            ("Пижамы", "Pajamas", "pajamas", "Пижамы", "Pajamas"),
            ("Ночные рубашки", "Nightgowns", "nightgowns", "Ночные рубашки", "Nightgowns"),
            ("Пижамные комплекты", "Sleep Sets", "sleep-sets", "Пижамные комплекты", "Sleep sets"),
        ],
    ),
    (
        "Спецодежда",
        "Workwear",
        "workwear",
        "Спецодежда",
        "Workwear",
        [
            ("Рабочие комбинезоны", "Work Overalls", "work-overalls", "Рабочие комбинезоны", "Work overalls"),
            ("Защитные костюмы", "Protective Suits", "protective-suits", "Защитные костюмы", "Protective suits"),
            ("Медицинская одежда", "Medical Scrubs", "medical-scrubs", "Медицинская одежда", "Medical scrubs"),
        ],
    ),
]

# Украшения: 3 уровня — L2 под jewelry, L3 под каждым L2.
# Формат: [(name_ru, name_en, slug, desc_ru, desc_en, children), ...]
JEWELRY_SUBCATEGORIES = [
    (
        "Кольца",
        "Rings",
        "rings",
        "Кольца",
        "Rings",
        [
            ("Обручальные кольца", "Wedding Rings", "wedding-rings", "Обручальные кольца", "Wedding rings"),
            ("Помолвочные кольца", "Engagement Rings", "engagement-rings", "Помолвочные кольца", "Engagement rings"),
            ("Коктейльные кольца", "Cocktail Rings", "cocktail-rings", "Коктейльные кольца", "Cocktail rings"),
            ("Кольца с камнями", "Gemstone Rings", "gemstone-rings", "Кольца с камнями", "Gemstone rings"),
            ("Печатки", "Signet Rings", "signet-rings", "Печатки", "Signet rings"),
            ("Наборные кольца", "Stackable Rings", "stackable-rings", "Наборные кольца", "Stackable rings"),
            ("Открытые кольца", "Open Rings", "open-rings", "Открытые кольца", "Open rings"),
        ],
    ),
    (
        "Серьги",
        "Earrings",
        "earrings",
        "Серьги",
        "Earrings",
        [
            ("Пусеты", "Stud Earrings", "stud-earrings", "Пусеты", "Stud earrings"),
            ("Серьги-кольца", "Hoop Earrings", "hoop-earrings", "Серьги-кольца", "Hoop earrings"),
            ("Длинные серьги", "Drop Earrings", "drop-earrings", "Длинные серьги", "Drop earrings"),
            ("Висячие серьги", "Dangle Earrings", "dangle-earrings", "Висячие серьги", "Dangle earrings"),
            ("Каффы", "Ear Cuffs", "ear-cuffs", "Каффы", "Ear cuffs"),
            ("Клипсы", "Clip-on Earrings", "clip-on-earrings", "Клипсы", "Clip-on earrings"),
            ("Серьги-протяжки", "Threader Earrings", "threader-earrings", "Серьги-протяжки", "Threader earrings"),
        ],
    ),
    (
        "Ожерелья",
        "Necklaces",
        "necklaces",
        "Ожерелья",
        "Necklaces",
        [
            ("Цепочки", "Chains", "chains", "Цепочки", "Chains"),
            ("Колье", "Necklace Pendants", "colliers", "Колье", "Necklace pendants"),
            ("Чокеры", "Chokers", "chokers", "Чокеры", "Chokers"),
            ("Подвески на цепочке", "Pendant Necklaces", "pendant-necklaces", "Подвески на цепочке", "Pendant necklaces"),
            ("Медальоны", "Lockets", "lockets", "Медальоны", "Lockets"),
            ("Многослойные ожерелья", "Layered Necklaces", "layered-necklaces", "Многослойные ожерелья", "Layered necklaces"),
            ("Жемчужные ожерелья", "Pearl Necklaces", "pearl-necklaces", "Жемчужные ожерелья", "Pearl necklaces"),
        ],
    ),
    (
        "Браслеты",
        "Bracelets",
        "bracelets",
        "Браслеты",
        "Bracelets",
        [
            ("Цепочные браслеты", "Chain Bracelets", "chain-bracelets", "Цепочные браслеты", "Chain bracelets"),
            ("Жёсткие браслеты", "Bangles", "bangles", "Жёсткие браслеты", "Bangles"),
            ("Манжеты", "Cuff Bracelets", "cuff-bracelets", "Манжеты", "Cuff bracelets"),
            ("Браслеты с шармами", "Charm Bracelets", "charm-bracelets", "Браслеты с шармами", "Charm bracelets"),
            ("Браслеты из бусин", "Beaded Bracelets", "beaded-bracelets", "Браслеты из бусин", "Beaded bracelets"),
            ("Теннисные браслеты", "Tennis Bracelets", "tennis-bracelets", "Теннисные браслеты", "Tennis bracelets"),
        ],
    ),
    (
        "Броши",
        "Brooches",
        "brooches",
        "Броши",
        "Brooches",
        [
            ("Классические броши", "Classic Brooches", "classic-brooches", "Классические броши", "Classic brooches"),
            ("Булавки", "Pins", "pins", "Булавки", "Pins"),
            ("Декоративные броши", "Decorative Brooches", "decorative-brooches", "Декоративные броши", "Decorative brooches"),
        ],
    ),
    (
        "Подвески и шармы",
        "Pendants & Charms",
        "pendants-charms",
        "Подвески и шармы",
        "Pendants & Charms",
        [
            ("Подвески", "Pendants", "pendants", "Подвески", "Pendants"),
            ("Шармы", "Charms", "charms", "Шармы", "Charms"),
            ("Религиозные подвески", "Religious Pendants", "religious-pendants", "Религиозные подвески", "Religious pendants"),
            ("Именные подвески", "Name Pendants", "name-pendants", "Именные подвески", "Name pendants"),
        ],
    ),
    (
        "Украшения для тела",
        "Body Jewelry",
        "body-jewelry",
        "Украшения для тела",
        "Body Jewelry",
        [
            ("Пирсинг носа", "Nose Rings", "nose-rings", "Пирсинг носа", "Nose rings"),
            ("Пирсинг пупка", "Belly Button Rings", "belly-button-rings", "Пирсинг пупка", "Belly button rings"),
            ("Пирсинг брови", "Eyebrow Rings", "eyebrow-rings", "Пирсинг брови", "Eyebrow rings"),
            ("Пирсинг губы", "Lip Rings", "lip-rings", "Пирсинг губы", "Lip rings"),
            ("Пирсинг уха", "Ear Piercing Jewelry", "ear-piercing-jewelry", "Пирсинг уха", "Ear piercing jewelry"),
        ],
    ),
    (
        "Украшения для волос",
        "Hair Jewelry",
        "hair-jewelry",
        "Украшения для волос",
        "Hair Jewelry",
        [
            ("Заколки", "Hair Clips", "hair-clips", "Заколки", "Hair clips"),
            ("Диадемы", "Tiaras", "tiaras", "Диадемы", "Tiaras"),
            ("Ободки", "Headbands", "headbands", "Ободки", "Headbands"),
            ("Украшения для причёсок", "Hair Pins", "hair-pins", "Украшения для причёсок", "Hair pins"),
        ],
    ),
    (
        "Мужские украшения",
        "Men's Jewelry",
        "mens-jewelry",
        "Мужские украшения",
        "Men's Jewelry",
        [
            ("Мужские кольца", "Men's Rings", "mens-rings", "Мужские кольца", "Men's rings"),
            ("Мужские браслеты", "Men's Bracelets", "mens-bracelets", "Мужские браслеты", "Men's bracelets"),
            ("Мужские цепочки", "Men's Chains", "mens-chains", "Мужские цепочки", "Men's chains"),
            ("Запонки", "Cufflinks", "cufflinks", "Запонки", "Cufflinks"),
        ],
    ),
    (
        "Ювелирные наборы",
        "Jewelry Sets",
        "jewelry-sets",
        "Ювелирные наборы",
        "Jewelry Sets",
        [
            ("Комплекты серьги + колье", "Earring & Necklace Sets", "earring-necklace-sets", "Комплекты серьги + колье", "Earring & necklace sets"),
            ("Комплекты кольцо + серьги", "Ring & Earring Sets", "ring-earring-sets", "Комплекты кольцо + серьги", "Ring & earring sets"),
            ("Полные комплекты", "Full Jewelry Sets", "full-jewelry-sets", "Полные комплекты", "Full jewelry sets"),
        ],
    ),
]

# БАДы: L2 с L3 подкатегориями
SUPPLEMENTS_SUBCATEGORIES = [
    (
        "Витамины",
        "Vitamins",
        "vitamins",
        "Витаминные комплексы",
        "Vitamin supplements",
        [
            ("Витамин A", "Vitamin A", "vitamin-a", "Витамин A", "Vitamin A"),
            ("Витамин B", "Vitamin B Complex", "vitamin-b", "Комплекс витаминов B", "Vitamin B complex"),
            ("Витамин C", "Vitamin C", "vitamin-c", "Витамин C", "Vitamin C"),
            ("Витамин D", "Vitamin D", "vitamin-d", "Витамин D", "Vitamin D"),
            ("Витамин E", "Vitamin E", "vitamin-e", "Витамин E", "Vitamin E"),
            ("Мультивитамины", "Multivitamins", "multivitamins", "Мультивитамины", "Multivitamins"),
            ("Пренатальные витамины", "Prenatal Vitamins", "prenatal-vitamins", "Пренатальные витамины", "Prenatal vitamins"),
        ],
    ),
    (
        "Минералы",
        "Minerals",
        "minerals",
        "Минеральные добавки",
        "Mineral supplements",
        [
            ("Кальций", "Calcium", "calcium", "Кальций", "Calcium"),
            ("Магний", "Magnesium", "magnesium", "Магний", "Magnesium"),
            ("Цинк", "Zinc", "zinc", "Цинк", "Zinc"),
            ("Железо", "Iron", "iron", "Железо", "Iron"),
            ("Селен", "Selenium", "selenium", "Селен", "Selenium"),
            ("Калий", "Potassium", "potassium", "Калий", "Potassium"),
        ],
    ),
    (
        "Иммунитет",
        "Immune Support",
        "immunity",
        "Средства для иммунитета",
        "Immune support",
        [
            ("Иммунные комплексы", "Immune Complexes", "immune-complexes", "Иммунные комплексы", "Immune complexes"),
            ("Пробиотики для иммунитета", "Probiotics", "probiotics-immune", "Пробиотики для иммунитета", "Probiotics for immunity"),
            ("Антиоксиданты", "Antioxidants", "antioxidants", "Антиоксиданты", "Antioxidants"),
            ("Витамин C комплексы", "Vitamin C Complexes", "vitamin-c-complexes", "Комплексы витамина C", "Vitamin C complexes"),
        ],
    ),
    (
        "Пищеварение",
        "Digestive Health",
        "digestive-health",
        "Здоровье пищеварения",
        "Digestive health",
        [
            ("Пробиотики", "Probiotics", "probiotics-digestive", "Пробиотики для пищеварения", "Digestive probiotics"),
            ("Пребиотики", "Prebiotics", "prebiotics", "Пребиотики", "Prebiotics"),
            ("Ферменты", "Digestive Enzymes", "digestive-enzymes", "Пищеварительные ферменты", "Digestive enzymes"),
            ("Средства от изжоги", "Heartburn Relief", "heartburn-relief", "Средства от изжоги", "Heartburn relief"),
        ],
    ),
    (
        "Энергия и тонус",
        "Energy & Vitality",
        "energy-vitality",
        "Энергия и тонус",
        "Energy & vitality",
        [
            ("Коэнзим Q10", "Coenzyme Q10", "coq10", "Коэнзим Q10", "Coenzyme Q10"),
            ("Женьшень", "Ginseng Supplements", "ginseng", "Женьшень", "Ginseng supplements"),
            ("Таурин", "Taurine", "taurine", "Таурин", "Taurine"),
            ("Энергетические комплексы", "Energy Complexes", "energy-complexes", "Энергетические комплексы", "Energy complexes"),
        ],
    ),
    (
        "Спортивное питание",
        "Sports Nutrition",
        "sports-nutrition",
        "Спортивное питание",
        "Sports nutrition",
        [
            ("Протеин", "Protein", "protein", "Протеин", "Protein"),
            ("Аминокислоты", "Amino Acids", "amino-acids", "Аминокислоты", "Amino acids"),
            ("BCAA", "BCAA", "bcaa", "BCAA", "BCAA"),
            ("Креатин", "Creatine", "creatine", "Креатин", "Creatine"),
            ("Гейнеры", "Mass Gainers", "mass-gainers", "Гейнеры", "Mass gainers"),
        ],
    ),
    (
        "Омега и жирные кислоты",
        "Omega & Fatty Acids",
        "omega-fatty-acids",
        "Омега и жирные кислоты",
        "Omega & fatty acids",
        [
            ("Омега-3", "Omega-3", "omega-3", "Омега-3", "Omega-3"),
            ("Рыбий жир", "Fish Oil", "fish-oil", "Рыбий жир", "Fish oil"),
            ("Омега-6", "Omega-6", "omega-6", "Омега-6", "Omega-6"),
            ("Омега-9", "Omega-9", "omega-9", "Омега-9", "Omega-9"),
        ],
    ),
    (
        "Травяные добавки",
        "Herbal Supplements",
        "herbal-supplements",
        "Травяные добавки",
        "Herbal supplements",
        [
            ("Ашваганда", "Ashwagandha", "ashwagandha", "Ашваганда", "Ashwagandha"),
            ("Куркума", "Turmeric", "turmeric", "Куркума", "Turmeric"),
            ("Эхинацея", "Echinacea", "echinacea", "Эхинацея", "Echinacea"),
            ("Чеснок", "Garlic Supplements", "garlic", "Чеснок", "Garlic supplements"),
            ("Растительные комплексы", "Herbal Blends", "herbal-blends", "Растительные комплексы", "Herbal blends"),
        ],
    ),
    (
        "Детские витамины",
        "Children's Supplements",
        "kids-supplements",
        "Детские витамины и БАДы",
        "Children's supplements",
        [
            ("Детские мультивитамины", "Kids Multivitamins", "kids-multivitamins", "Детские мультивитамины", "Kids multivitamins"),
            ("Витамин D для детей", "Vitamin D for Kids", "vitamin-d-kids", "Витамин D для детей", "Vitamin D for kids"),
            ("Омега для детей", "Omega for Kids", "omega-kids", "Омега для детей", "Omega for kids"),
        ],
    ),
]

# Медикаменты: L2 с L3 подкатегориями
MEDICINES_SUBCATEGORIES = [
    (
        "Антибиотики",
        "Antibiotics",
        "antibiotics",
        "Антибактериальные препараты",
        "Antibacterial drugs",
        [],
    ),
    (
        "Обезболивающие",
        "Pain Relief",
        "painkillers",
        "Препараты для снятия боли",
        "Pain relief",
        [
            ("Таблетки от боли", "Pain Relief Tablets", "pain-tablets", "Таблетки от боли", "Pain relief tablets"),
            ("Гели и мази", "Pain Relief Gels", "pain-gels", "Гели и мази от боли", "Pain relief gels"),
            ("Пластыри", "Pain Relief Patches", "pain-patches", "Пластыри от боли", "Pain relief patches"),
        ],
    ),
    (
        "Простуда и грипп",
        "Cold & Flu",
        "cold-flu",
        "Препараты от простуды и гриппа",
        "Cold & flu medications",
        [
            ("Таблетки от простуды", "Cold Tablets", "cold-tablets", "Таблетки от простуды", "Cold tablets"),
            ("Сиропы от кашля", "Cough Syrups", "cough-syrups", "Сиропы от кашля", "Cough syrups"),
            ("Леденцы для горла", "Throat Lozenges", "throat-lozenges", "Леденцы для горла", "Throat lozenges"),
            ("Назальные спреи", "Nasal Sprays", "nasal-sprays", "Назальные спреи", "Nasal sprays"),
        ],
    ),
    (
        "Аллергия",
        "Allergy",
        "allergy",
        "Препараты от аллергии",
        "Allergy medications",
        [
            ("Антигистаминные", "Antihistamines", "antihistamines", "Антигистаминные препараты", "Antihistamines"),
            ("Назальные препараты", "Allergy Nasal Sprays", "allergy-nasal", "Назальные препараты от аллергии", "Allergy nasal sprays"),
            ("Глазные капли", "Allergy Eye Drops", "allergy-eye-drops", "Глазные капли от аллергии", "Allergy eye drops"),
        ],
    ),
    (
        "Сердце и сосуды",
        "Heart & Cardiovascular",
        "heart-cardiovascular",
        "Препараты для сердца и сосудов",
        "Heart & cardiovascular",
        [
            ("Омега-3 комплексы", "Omega-3 Complexes", "omega-3-heart", "Омега-3 для сердца", "Omega-3 complexes"),
            ("Коэнзим Q10", "CoQ10 Supplements", "coq10-heart", "Коэнзим Q10 для сердца", "CoQ10 supplements"),
            ("Холестерин контроль", "Cholesterol Support", "cholesterol-support", "Поддержка холестерина", "Cholesterol support"),
        ],
    ),
    (
        "Сон и стресс",
        "Sleep & Stress",
        "sleep-stress",
        "Средства для сна и снятия стресса",
        "Sleep & stress relief",
        [
            ("Мелатонин", "Melatonin", "melatonin", "Мелатонин", "Melatonin"),
            ("Успокаивающие добавки", "Calming Supplements", "calming-supplements", "Успокаивающие добавки", "Calming supplements"),
            ("Магний для сна", "Magnesium for Sleep", "magnesium-sleep", "Магний для сна", "Magnesium for sleep"),
            ("Антистресс комплексы", "Stress Relief Supplements", "stress-relief", "Антистресс комплексы", "Stress relief supplements"),
        ],
    ),
    (
        "Кардио",
        "Cardio",
        "cardio",
        "Препараты для сердечно-сосудистой системы",
        "Cardiovascular medications",
        [],
    ),
    (
        "Дерматология",
        "Dermatology",
        "dermatology",
        "Препараты для кожи",
        "Skin medications",
        [],
    ),
    (
        "ЖКТ",
        "Gastro",
        "gastro",
        "Препараты для желудочно-кишечного тракта",
        "Gastrointestinal medications",
        [],
    ),
    (
        "Эндокринология/Диабет",
        "Endocrinology/Diabetes",
        "endocrinology-diabetes",
        "Препараты при диабете",
        "Diabetes medications",
        [],
    ),
    (
        "Офтальмология",
        "Ophthalmology",
        "ophthalmology",
        "Препараты для глаз",
        "Eye medications",
        [],
    ),
    (
        "ЛОР",
        "ENT",
        "ent",
        "Препараты для уха, горла, носа",
        "ENT medications",
        [],
    ),
    (
        "Ортопедия/Травмы",
        "Orthopedics/Injuries",
        "orthopedics",
        "Препараты при травмах",
        "Orthopedic medications",
        [],
    ),
]

# Мебель: L2 с L3 подкатегориями
FURNITURE_SUBCATEGORIES = [
    (
        "Гостиная",
        "Living Room",
        "living-room",
        "Мебель для гостиной",
        "Living room furniture",
        [
            ("Диваны", "Sofas", "sofas", "Диваны", "Sofas"),
            ("Кресла", "Armchairs", "armchairs", "Кресла", "Armchairs"),
            ("Журнальные столики", "Coffee Tables", "coffee-tables", "Журнальные столики", "Coffee tables"),
            ("ТВ тумбы", "TV Stands", "tv-stands", "ТВ тумбы", "TV stands"),
            ("Стенки", "Wall Units", "wall-units", "Стенки", "Wall units"),
        ],
    ),
    (
        "Спальня",
        "Bedroom",
        "bedroom",
        "Мебель для спальни",
        "Bedroom furniture",
        [
            ("Кровати", "Beds", "beds", "Кровати", "Beds"),
            ("Матрасы", "Mattresses", "mattresses", "Матрасы", "Mattresses"),
            ("Тумбочки", "Nightstands", "nightstands", "Тумбочки", "Nightstands"),
            ("Комоды", "Dressers", "dressers", "Комоды", "Dressers"),
            ("Шкафы", "Wardrobes", "wardrobes", "Шкафы для спальни", "Wardrobes"),
        ],
    ),
    (
        "Кухня",
        "Kitchen",
        "kitchen-dining",
        "Мебель для кухни",
        "Kitchen furniture",
        [
            ("Обеденные столы", "Dining Tables", "dining-tables", "Обеденные столы", "Dining tables"),
            ("Стулья", "Dining Chairs", "dining-chairs", "Обеденные стулья", "Dining chairs"),
            ("Барные стулья", "Bar Stools", "bar-stools", "Барные стулья", "Bar stools"),
            ("Кухонные шкафы", "Kitchen Cabinets", "kitchen-cabinets", "Кухонные шкафы", "Kitchen cabinets"),
        ],
    ),
    (
        "Офисная мебель",
        "Office Furniture",
        "office",
        "Офисная мебель",
        "Office furniture",
        [
            ("Офисные столы", "Office Desks", "office-desks", "Офисные столы", "Office desks"),
            ("Офисные кресла", "Office Chairs", "office-chairs", "Офисные кресла", "Office chairs"),
            ("Шкафы для документов", "Filing Cabinets", "filing-cabinets", "Шкафы для документов", "Filing cabinets"),
            ("Стеллажи", "Bookcases", "bookcases", "Стеллажи и книжные полки", "Bookcases"),
        ],
    ),
    (
        "Детская мебель",
        "Kids Furniture",
        "kids-furniture",
        "Детская мебель",
        "Kids furniture",
        [
            ("Детские кровати", "Kids Beds", "kids-beds", "Детские кровати", "Kids beds"),
            ("Детские столы", "Kids Desks", "kids-desks", "Детские столы", "Kids desks"),
            ("Детские стулья", "Kids Chairs", "kids-chairs", "Детские стулья", "Kids chairs"),
            ("Игровые шкафы", "Toy Storage", "toy-storage", "Игровые шкафы", "Toy storage"),
        ],
    ),
    (
        "Хранение",
        "Storage Furniture",
        "storage-furniture",
        "Мебель для хранения",
        "Storage furniture",
        [
            ("Шкафы", "Cabinets", "storage-cabinets", "Шкафы для хранения", "Storage cabinets"),
            ("Комоды", "Dressers", "storage-dressers", "Комоды для хранения", "Storage dressers"),
            ("Полки", "Shelves", "shelves", "Полки", "Shelves"),
            ("Стеллажи", "Storage Racks", "storage-racks", "Стеллажи для хранения", "Storage racks"),
        ],
    ),
    (
        "Уличная мебель",
        "Outdoor Furniture",
        "outdoor-furniture",
        "Уличная и садовая мебель",
        "Outdoor furniture",
        [
            ("Садовые столы", "Garden Tables", "garden-tables", "Садовые столы", "Garden tables"),
            ("Садовые кресла", "Garden Chairs", "garden-chairs", "Садовые кресла", "Garden chairs"),
            ("Лежаки", "Sun Loungers", "sun-loungers", "Лежаки", "Sun loungers"),
            ("Комплекты мебели", "Patio Sets", "patio-sets", "Комплекты садовой мебели", "Patio sets"),
        ],
    ),
]

# Автозапчасти: L2 с L3 подкатегориями
AUTO_PARTS_SUBCATEGORIES = [
    (
        "Двигатель",
        "Engine Parts",
        "engine-parts",
        "Запчасти двигателя",
        "Engine parts",
        [
            ("Поршни", "Pistons", "pistons", "Поршни", "Pistons"),
            ("Кольца поршневые", "Piston Rings", "piston-rings", "Поршневые кольца", "Piston rings"),
            ("Коленвал", "Crankshaft", "crankshaft", "Коленчатый вал", "Crankshaft"),
            ("Распредвал", "Camshaft", "camshaft", "Распределительный вал", "Camshaft"),
            ("Клапаны", "Valves", "valves", "Клапаны", "Valves"),
            ("Прокладки двигателя", "Engine Gaskets", "engine-gaskets", "Прокладки двигателя", "Engine gaskets"),
            ("Турбокомпрессоры", "Turbochargers", "turbochargers", "Турбокомпрессоры", "Turbochargers"),
        ],
    ),
    (
        "Тормозная система",
        "Brake System",
        "brake-system",
        "Тормозная система",
        "Brake system",
        [
            ("Тормозные колодки", "Brake Pads", "brake-pads", "Тормозные колодки", "Brake pads"),
            ("Тормозные диски", "Brake Discs", "brake-discs", "Тормозные диски", "Brake discs"),
            ("Тормозные суппорты", "Brake Calipers", "brake-calipers", "Тормозные суппорты", "Brake calipers"),
            ("Тормозные шланги", "Brake Hoses", "brake-hoses", "Тормозные шланги", "Brake hoses"),
            ("Главный тормозной цилиндр", "Brake Master Cylinder", "brake-master-cylinder", "Главный тормозной цилиндр", "Brake master cylinder"),
        ],
    ),
    (
        "Подвеска",
        "Suspension",
        "suspension",
        "Подвеска",
        "Suspension",
        [
            ("Амортизаторы", "Shock Absorbers", "shock-absorbers", "Амортизаторы", "Shock absorbers"),
            ("Пружины", "Springs", "springs", "Пружины подвески", "Springs"),
            ("Рычаги подвески", "Control Arms", "control-arms", "Рычаги подвески", "Control arms"),
            ("Стабилизаторы", "Stabilizer Bars", "stabilizer-bars", "Стабилизаторы", "Stabilizer bars"),
            ("Сайлентблоки", "Bushings", "bushings", "Сайлентблоки", "Bushings"),
        ],
    ),
    (
        "Рулевое управление",
        "Steering System",
        "steering-system",
        "Рулевое управление",
        "Steering system",
        [
            ("Рулевая рейка", "Steering Rack", "steering-rack", "Рулевая рейка", "Steering rack"),
            ("Насос ГУР", "Power Steering Pump", "power-steering-pump", "Насос ГУР", "Power steering pump"),
            ("Рулевые тяги", "Tie Rods", "tie-rods", "Рулевые тяги", "Tie rods"),
            ("Наконечники рулевых тяг", "Tie Rod Ends", "tie-rod-ends", "Наконечники рулевых тяг", "Tie rod ends"),
        ],
    ),
    (
        "Трансмиссия",
        "Transmission",
        "transmission",
        "Трансмиссия",
        "Transmission",
        [
            ("Сцепление", "Clutch Kits", "clutch-kits", "Комплекты сцепления", "Clutch kits"),
            ("Коробка передач", "Gearboxes", "gearboxes", "Коробки передач", "Gearboxes"),
            ("Карданный вал", "Drive Shaft", "drive-shaft", "Карданный вал", "Drive shaft"),
            ("Дифференциал", "Differential", "differential", "Дифференциал", "Differential"),
            ("ШРУС", "CV Joints", "cv-joints", "Шарниры равных угловых скоростей", "CV joints"),
        ],
    ),
    (
        "Электрика",
        "Electrical System",
        "electrical-system",
        "Электрооборудование",
        "Electrical system",
        [
            ("Аккумуляторы", "Car Batteries", "car-batteries", "Автомобильные аккумуляторы", "Car batteries"),
            ("Стартеры", "Starters", "starters", "Стартеры", "Starters"),
            ("Генераторы", "Alternators", "alternators", "Генераторы", "Alternators"),
            ("Датчики", "Sensors", "sensors", "Датчики", "Sensors"),
            ("Предохранители", "Fuses", "fuses", "Предохранители", "Fuses"),
        ],
    ),
    (
        "Система охлаждения",
        "Cooling System",
        "cooling-system",
        "Система охлаждения",
        "Cooling system",
        [
            ("Радиаторы", "Radiators", "radiators", "Радиаторы", "Radiators"),
            ("Водяные насосы", "Water Pumps", "water-pumps", "Водяные насосы", "Water pumps"),
            ("Термостаты", "Thermostats", "thermostats", "Термостаты", "Thermostats"),
            ("Вентиляторы охлаждения", "Cooling Fans", "cooling-fans", "Вентиляторы охлаждения", "Cooling fans"),
        ],
    ),
    (
        "Кузовные детали",
        "Body Parts",
        "body-parts",
        "Кузовные детали",
        "Body parts",
        [
            ("Бамперы", "Bumpers", "bumpers", "Бамперы", "Bumpers"),
            ("Капоты", "Hoods", "hoods", "Капоты", "Hoods"),
            ("Крылья", "Fenders", "fenders", "Крылья", "Fenders"),
            ("Двери", "Doors", "doors", "Двери", "Doors"),
            ("Зеркала", "Mirrors", "mirrors", "Зеркала", "Mirrors"),
        ],
    ),
    (
        "Освещение",
        "Lighting",
        "lighting",
        "Освещение",
        "Lighting",
        [
            ("Фары", "Headlights", "headlights", "Фары", "Headlights"),
            ("Задние фонари", "Tail Lights", "tail-lights", "Задние фонари", "Tail lights"),
            ("Противотуманные фары", "Fog Lights", "fog-lights", "Противотуманные фары", "Fog lights"),
            ("Лампочки", "Bulbs", "bulbs", "Лампочки", "Bulbs"),
        ],
    ),
    (
        "Фильтры",
        "Filters",
        "filters",
        "Фильтры",
        "Filters",
        [
            ("Масляные фильтры", "Oil Filters", "oil-filters", "Масляные фильтры", "Oil filters"),
            ("Воздушные фильтры", "Air Filters", "air-filters", "Воздушные фильтры", "Air filters"),
            ("Топливные фильтры", "Fuel Filters", "fuel-filters", "Топливные фильтры", "Fuel filters"),
            ("Салонные фильтры", "Cabin Filters", "cabin-filters", "Салонные фильтры", "Cabin filters"),
        ],
    ),
]

# Посуда: L2 с L3 (и L4 для Тарелок и Мисок)
TABLEWARE_SUBCATEGORIES = [
    (
        "Кухонная посуда",
        "Cookware",
        "cookware",
        "Кухонная посуда для готовки",
        "Cookware",
        [
            ("Кастрюли", "Pots", "pots", "Кастрюли", "Pots"),
            ("Сковороды", "Frying Pans", "frying-pans", "Сковороды", "Frying pans"),
            ("Сотейники", "Sauté Pans", "saute-pans", "Сотейники", "Sauté pans"),
            ("Ковши", "Sauce Pans", "sauce-pans", "Ковши", "Sauce pans"),
            ("Казаны", "Cauldrons", "cauldrons", "Казаны", "Cauldrons"),
            ("Воки", "Woks", "woks", "Воки", "Woks"),
            ("Пароварки", "Steamers", "steamers", "Пароварки", "Steamers"),
            ("Наборы посуды", "Cookware Sets", "cookware-sets", "Наборы кухонной посуды", "Cookware sets"),
        ],
    ),
    (
        "Посуда для сервировки",
        "Tableware",
        "tableware-serving",
        "Посуда для сервировки",
        "Tableware",
        [
            (
                "Тарелки",
                "Plates",
                "plates",
                "Тарелки",
                "Plates",
                [
                    ("Обеденные тарелки", "Dinner Plates", "dinner-plates", "Обеденные тарелки", "Dinner plates"),
                    ("Десертные тарелки", "Dessert Plates", "dessert-plates", "Десертные тарелки", "Dessert plates"),
                    ("Суповые тарелки", "Soup Plates", "soup-plates", "Суповые тарелки", "Soup plates"),
                    ("Закусочные тарелки", "Appetizer Plates", "appetizer-plates", "Закусочные тарелки", "Appetizer plates"),
                ],
            ),
            (
                "Миски",
                "Bowls",
                "bowls",
                "Миски",
                "Bowls",
                [
                    ("Салатники", "Salad Bowls", "salad-bowls", "Салатники", "Salad bowls"),
                    ("Супницы", "Soup Bowls", "soup-bowls", "Супницы", "Soup bowls"),
                    ("Пиалы", "Small Bowls", "small-bowls", "Пиалы", "Small bowls"),
                ],
            ),
            ("Блюда", "Serving Dishes", "serving-dishes", "Блюда для сервировки", "Serving dishes"),
            ("Соусники", "Sauce Boats", "sauce-boats", "Соусники", "Sauce boats"),
        ],
    ),
    (
        "Стаканы и бокалы",
        "Drinkware",
        "drinkware",
        "Стаканы и бокалы",
        "Drinkware",
        [
            ("Стаканы", "Drinking Glasses", "drinking-glasses", "Стаканы", "Drinking glasses"),
            ("Бокалы для вина", "Wine Glasses", "wine-glasses", "Бокалы для вина", "Wine glasses"),
            ("Бокалы для шампанского", "Champagne Glasses", "champagne-glasses", "Бокалы для шампанского", "Champagne glasses"),
            ("Пивные бокалы", "Beer Glasses", "beer-glasses", "Пивные бокалы", "Beer glasses"),
            ("Кружки", "Mugs", "mugs", "Кружки", "Mugs"),
            ("Чашки", "Cups", "cups", "Чашки", "Cups"),
        ],
    ),
    (
        "Чайная и кофейная посуда",
        "Tea & Coffee Ware",
        "tea-coffee-ware",
        "Чайная и кофейная посуда",
        "Tea & coffee ware",
        [
            ("Чайники", "Teapots", "teapots", "Чайники", "Teapots"),
            ("Кофейники", "Coffee Pots", "coffee-pots", "Кофейники", "Coffee pots"),
            ("Чайные чашки", "Tea Cups", "tea-cups", "Чайные чашки", "Tea cups"),
            ("Кофейные чашки", "Coffee Cups", "coffee-cups", "Кофейные чашки", "Coffee cups"),
            ("Чайные сервизы", "Tea Sets", "tea-sets", "Чайные сервизы", "Tea sets"),
        ],
    ),
    (
        "Формы для выпечки",
        "Bakeware",
        "bakeware",
        "Формы для выпечки",
        "Bakeware",
        [
            ("Формы для тортов", "Cake Pans", "cake-pans", "Формы для тортов", "Cake pans"),
            ("Формы для хлеба", "Bread Pans", "bread-pans", "Формы для хлеба", "Bread pans"),
            ("Формы для маффинов", "Muffin Pans", "muffin-pans", "Формы для маффинов", "Muffin pans"),
            ("Противни", "Baking Trays", "baking-trays", "Противни", "Baking trays"),
            ("Формы для запекания", "Baking Dishes", "baking-dishes", "Формы для запекания", "Baking dishes"),
        ],
    ),
    (
        "Посуда для хранения",
        "Food Storage",
        "food-storage",
        "Посуда для хранения продуктов",
        "Food storage",
        [
            ("Контейнеры", "Food Containers", "food-containers", "Контейнеры для хранения", "Food containers"),
            ("Банки", "Storage Jars", "storage-jars", "Банки для хранения", "Storage jars"),
            ("Ланч-боксы", "Lunch Boxes", "lunch-boxes", "Ланч-боксы", "Lunch boxes"),
            ("Термоконтейнеры", "Thermal Containers", "thermal-containers", "Термоконтейнеры", "Thermal containers"),
        ],
    ),
    (
        "Кухонные аксессуары",
        "Kitchen Accessories",
        "kitchen-accessories",
        "Кухонные аксессуары",
        "Kitchen accessories",
        [
            ("Мерные стаканы", "Measuring Cups", "measuring-cups", "Мерные стаканы", "Measuring cups"),
            ("Мерные ложки", "Measuring Spoons", "measuring-spoons", "Мерные ложки", "Measuring spoons"),
            ("Дуршлаги", "Colanders", "colanders", "Дуршлаги", "Colanders"),
            ("Сита", "Sieves", "sieves", "Сита", "Sieves"),
            ("Кухонные миски", "Mixing Bowls", "mixing-bowls", "Кухонные миски", "Mixing bowls"),
        ],
    ),
    (
        "Наборы посуды",
        "Tableware Sets",
        "tableware-sets",
        "Наборы посуды",
        "Tableware sets",
        [
            ("Столовые сервизы", "Dinner Sets", "dinner-sets", "Столовые сервизы", "Dinner sets"),
            ("Наборы тарелок", "Plate Sets", "plate-sets", "Наборы тарелок", "Plate sets"),
            ("Наборы стаканов", "Glass Sets", "glass-sets", "Наборы стаканов", "Glass sets"),
        ],
    ),
]

# Медтехника: L2 с L3 и L4 подкатегориями
MEDICAL_EQUIPMENT_SUBCATEGORIES = [
    (
        "Диагностическое оборудование",
        "Diagnostic Equipment",
        "diagnostic-equipment",
        "Диагностическое оборудование",
        "Diagnostic equipment",
        [
            (
                "Тонометры",
                "Blood Pressure Monitors",
                "tonometers",
                "Тонометры",
                "Blood pressure monitors",
                [
                    ("Автоматические", "Automatic", "automatic-tonometers", "Автоматические тонометры", "Automatic tonometers"),
                    ("Полуавтоматические", "Semi-Automatic", "semi-automatic-tonometers", "Полуавтоматические тонометры", "Semi-automatic tonometers"),
                    ("Запястные", "Wrist", "wrist-tonometers", "Запястные тонометры", "Wrist tonometers"),
                ],
            ),
            (
                "Глюкометры",
                "Glucometers",
                "glucometers",
                "Глюкометры",
                "Glucometers",
                [
                    ("Классические", "Classic", "classic-glucometers", "Классические глюкометры", "Classic glucometers"),
                    ("Непрерывного мониторинга", "Continuous Glucose Monitors", "cgm", "Системы непрерывного мониторинга глюкозы", "Continuous glucose monitors"),
                ],
            ),
            (
                "Пульсоксиметры",
                "Pulse Oximeters",
                "pulse-oximeters",
                "Пульсоксиметры",
                "Pulse oximeters",
                [
                    ("Пальчиковые", "Fingertip", "fingertip-pulse-oximeters", "Пальчиковые пульсоксиметры", "Fingertip pulse oximeters"),
                    ("Стационарные", "Tabletop", "tabletop-pulse-oximeters", "Стационарные пульсоксиметры", "Tabletop pulse oximeters"),
                ],
            ),
            (
                "Термометры",
                "Thermometers",
                "thermometers",
                "Термометры",
                "Thermometers",
                [
                    ("Электронные", "Digital", "digital-thermometers", "Электронные термометры", "Digital thermometers"),
                    ("Инфракрасные", "Infrared", "infrared-thermometers", "Инфракрасные термометры", "Infrared thermometers"),
                    ("Ушные", "Ear", "ear-thermometers", "Ушные термометры", "Ear thermometers"),
                    ("Бесконтактные", "Non-Contact", "non-contact-thermometers", "Бесконтактные термометры", "Non-contact thermometers"),
                ],
            ),
            (
                "Стетоскопы",
                "Stethoscopes",
                "stethoscopes",
                "Стетоскопы",
                "Stethoscopes",
                [
                    ("Акустические", "Acoustic", "acoustic-stethoscopes", "Акустические стетоскопы", "Acoustic stethoscopes"),
                    ("Электронные", "Electronic", "electronic-stethoscopes", "Электронные стетоскопы", "Electronic stethoscopes"),
                ],
            ),
            (
                "Электрокардиографы",
                "ECG Monitors",
                "ecg-monitors",
                "Электрокардиографы",
                "ECG monitors",
                [
                    ("Портативные", "Portable", "portable-ecg", "Портативные ЭКГ", "Portable ECG"),
                    ("Стационарные", "Stationary", "stationary-ecg", "Стационарные ЭКГ", "Stationary ECG"),
                ],
            ),
            (
                "Весы медицинские",
                "Medical Scales",
                "medical-scales",
                "Весы медицинские",
                "Medical scales",
                [
                    ("Напольные", "Floor Scales", "floor-scales", "Напольные весы", "Floor scales"),
                    ("Детские", "Baby Scales", "baby-scales", "Детские весы", "Baby scales"),
                ],
            ),
            ("Холтеровские мониторы", "Holter Monitors", "holter-monitors", "Холтеровские мониторы", "Holter monitors"),
        ],
    ),
    (
        "Реабилитационное оборудование",
        "Rehabilitation Equipment",
        "rehabilitation-equipment",
        "Реабилитационное оборудование",
        "Rehabilitation equipment",
        [
            (
                "Костыли",
                "Crutches",
                "crutches",
                "Костыли",
                "Crutches",
                [
                    ("Подмышечные", "Axillary", "axillary-crutches", "Подмышечные костыли", "Axillary crutches"),
                    ("Локтевые", "Elbow", "elbow-crutches", "Локтевые костыли", "Elbow crutches"),
                ],
            ),
            (
                "Ходунки",
                "Walkers",
                "walkers",
                "Ходунки",
                "Walkers",
                [
                    ("Стандартные", "Standard", "standard-walkers", "Стандартные ходунки", "Standard walkers"),
                    ("На колёсах", "Wheeled", "wheeled-walkers", "Ходунки на колёсах", "Wheeled walkers"),
                    ("Детские", "Children's", "children-walkers", "Детские ходунки", "Children's walkers"),
                ],
            ),
            (
                "Трости",
                "Walking Canes",
                "walking-canes",
                "Трости",
                "Walking canes",
                [
                    ("Одноопорные", "Single-Point", "single-point-canes", "Трости одноопорные", "Single-point canes"),
                    ("Четырёхопорные", "Quad Canes", "quad-canes", "Трости четырёхопорные", "Quad canes"),
                ],
            ),
            (
                "Инвалидные кресла",
                "Wheelchairs",
                "wheelchairs",
                "Инвалидные кресла",
                "Wheelchairs",
                [
                    ("Механические", "Manual", "manual-wheelchairs", "Механические инвалидные кресла", "Manual wheelchairs"),
                    ("Электрические", "Electric", "electric-wheelchairs", "Электрические инвалидные кресла", "Electric wheelchairs"),
                    ("Детские", "Children's", "children-wheelchairs", "Детские инвалидные кресла", "Children's wheelchairs"),
                ],
            ),
            (
                "Массажёры",
                "Massagers",
                "massagers",
                "Массажёры",
                "Massagers",
                [
                    ("Ручные", "Handheld", "handheld-massagers", "Ручные массажёры", "Handheld massagers"),
                    ("Массажные подушки", "Massage Pillows", "massage-pillows", "Массажные подушки", "Massage pillows"),
                    ("Массажные кресла", "Massage Chairs", "massage-chairs", "Массажные кресла", "Massage chairs"),
                    ("Массажные матрасы", "Massage Mats", "massage-mats", "Массажные матрасы", "Massage mats"),
                ],
            ),
            ("Электростимуляторы", "TENS / EMS Devices", "tens-ems", "Электростимуляторы TENS/EMS", "TENS / EMS devices"),
            (
                "Тренажёры для реабилитации",
                "Rehabilitation Trainers",
                "rehabilitation-trainers",
                "Тренажёры для реабилитации",
                "Rehabilitation trainers",
                [
                    ("Педальные", "Pedal Exercisers", "pedal-exercisers", "Педальные тренажёры", "Pedal exercisers"),
                    ("Тренажёры для рук", "Hand Exercisers", "hand-exercisers", "Тренажёры для рук", "Hand exercisers"),
                ],
            ),
        ],
    ),
    (
        "Ортопедические изделия",
        "Orthopedic Products",
        "orthopedic-products",
        "Ортопедические изделия",
        "Orthopedic products",
        [
            (
                "Ортезы",
                "Orthoses",
                "orthoses",
                "Ортезы",
                "Orthoses",
                [
                    ("Коленные", "Knee Braces", "knee-braces", "Коленные ортезы", "Knee braces"),
                    ("Голеностопные", "Ankle Braces", "ankle-braces", "Голеностопные ортезы", "Ankle braces"),
                    ("Лучезапястные", "Wrist Braces", "wrist-braces", "Лучезапястные ортезы", "Wrist braces"),
                    ("Шейные воротники", "Cervical Collars", "cervical-collars", "Шейные воротники", "Cervical collars"),
                ],
            ),
            (
                "Стельки",
                "Insoles",
                "insoles",
                "Стельки",
                "Insoles",
                [
                    ("Ортопедические", "Orthopedic", "orthopedic-insoles", "Ортопедические стельки", "Orthopedic insoles"),
                    ("Диабетические", "Diabetic", "diabetic-insoles", "Диабетические стельки", "Diabetic insoles"),
                ],
            ),
            (
                "Корсеты",
                "Back Braces",
                "back-braces",
                "Корсеты",
                "Back braces",
                [
                    ("Поясничные", "Lumbar", "lumbar-braces", "Поясничные корсеты", "Lumbar braces"),
                    ("Грудопоясничные", "Thoracic", "thoracic-braces", "Грудопоясничные корсеты", "Thoracic braces"),
                ],
            ),
            (
                "Подушки ортопедические",
                "Orthopedic Pillows",
                "orthopedic-pillows",
                "Подушки ортопедические",
                "Orthopedic pillows",
                [
                    ("Шейные", "Cervical", "cervical-pillows", "Шейные подушки", "Cervical pillows"),
                    ("Ортопедические матрасы", "Orthopedic Mattresses", "orthopedic-mattresses", "Ортопедические матрасы", "Orthopedic mattresses"),
                    ("Подушки для сидения", "Seat Cushions", "seat-cushions", "Подушки для сидения", "Seat cushions"),
                ],
            ),
        ],
    ),
    (
        "Дыхательная техника",
        "Respiratory Equipment",
        "respiratory-equipment",
        "Дыхательная техника",
        "Respiratory equipment",
        [
            (
                "Небулайзеры",
                "Nebulizers",
                "nebulizers",
                "Небулайзеры",
                "Nebulizers",
                [
                    ("Компрессорные", "Compressor", "compressor-nebulizers", "Компрессорные небулайзеры", "Compressor nebulizers"),
                    ("Ультразвуковые", "Ultrasonic", "ultrasonic-nebulizers", "Ультразвуковые небулайзеры", "Ultrasonic nebulizers"),
                    ("Меш-небулайзеры", "Mesh", "mesh-nebulizers", "Меш-небулайзеры", "Mesh nebulizers"),
                ],
            ),
            (
                "Кислородные концентраторы",
                "Oxygen Concentrators",
                "oxygen-concentrators",
                "Кислородные концентраторы",
                "Oxygen concentrators",
                [
                    ("Стационарные", "Stationary", "stationary-oxygen", "Стационарные концентраторы", "Stationary oxygen concentrators"),
                    ("Портативные", "Portable", "portable-oxygen", "Портативные концентраторы", "Portable oxygen concentrators"),
                ],
            ),
            ("CPAP / BiPAP аппараты", "CPAP Machines", "cpap-bipap", "CPAP и BiPAP аппараты", "CPAP Machines"),
            ("Спирометры", "Spirometers", "spirometers", "Спирометры", "Spirometers"),
        ],
    ),
    (
        "Физиотерапия",
        "Physiotherapy Devices",
        "physiotherapy-equipment",
        "Физиотерапия",
        "Physiotherapy devices",
        [
            ("Ультразвуковые аппараты", "Ultrasound Therapy", "ultrasound-therapy", "Ультразвуковая терапия", "Ultrasound therapy"),
            ("Лазерные аппараты", "Laser Therapy", "laser-therapy", "Лазерная терапия", "Laser therapy"),
            ("Магнитотерапия", "Magnetic Therapy", "magnetic-therapy", "Магнитотерапия", "Magnetic therapy"),
            ("Аппараты дарсонваль", "Darsonval Devices", "darsonval", "Аппараты Дарсонваля", "Darsonval devices"),
            ("Миостимуляторы", "Muscle Stimulators", "muscle-stimulators", "Миостимуляторы", "Muscle stimulators"),
            ("Аппараты для прогревания", "Heat Therapy", "heat-therapy", "Аппараты для прогревания", "Heat therapy"),
        ],
    ),
    (
        "Перевязочные материалы и расходники",
        "Wound Care & Consumables",
        "wound-care-consumables",
        "Перевязочные материалы и расходники",
        "Wound care and consumables",
        [
            (
                "Бинты",
                "Bandages",
                "bandages",
                "Бинты",
                "Bandages",
                [
                    ("Эластичные", "Elastic", "elastic-bandages", "Эластичные бинты", "Elastic bandages"),
                    ("Марлевые", "Gauze", "gauze-bandages", "Марлевые бинты", "Gauze bandages"),
                ],
            ),
            ("Пластыри", "Adhesive Bandages", "adhesive-bandages", "Пластыри", "Adhesive bandages"),
            (
                "Компрессионные чулки",
                "Compression Stockings",
                "compression-stockings",
                "Компрессионные чулки",
                "Compression stockings",
                [
                    ("Гольфы", "Knee-High", "compression-knee-high", "Компрессионные гольфы", "Compression knee-high"),
                    ("Чулки", "Thigh-High", "compression-thigh-high", "Компрессионные чулки", "Compression thigh-high"),
                    ("Колготки", "Pantyhose", "compression-pantyhose", "Компрессионные колготки", "Compression pantyhose"),
                ],
            ),
            ("Шприцы", "Syringes", "syringes", "Шприцы", "Syringes"),
            ("Перчатки медицинские", "Medical Gloves", "medical-gloves", "Перчатки медицинские", "Medical gloves"),
            ("Маски медицинские", "Masks", "medical-masks", "Маски медицинские", "Medical masks"),
        ],
    ),
    (
        "Офтальмология",
        "Ophthalmology",
        "ophthalmology-equipment",
        "Офтальмология",
        "Ophthalmology",
        [
            ("Тонометры глазные", "Eye Tonometers", "eye-tonometers", "Тонометры глазные", "Eye tonometers"),
            ("Линзы контактные", "Contact Lenses", "contact-lenses", "Контактные линзы", "Contact lenses"),
            ("Растворы для линз", "Contact Lens Solutions", "contact-lens-solutions", "Растворы для контактных линз", "Contact lens solutions"),
        ],
    ),
    (
        "Слуховые аппараты",
        "Hearing Aids",
        "hearing-aids",
        "Слуховые аппараты",
        "Hearing aids",
        [
            ("Внутриканальные", "In-Canal", "in-canal-hearing-aids", "Внутриканальные", "In-canal hearing aids"),
            ("Заушные", "Behind-the-Ear", "behind-the-ear-hearing-aids", "Заушные", "Behind-the-ear hearing aids"),
            ("Аксессуары", "Accessories", "hearing-aids-accessories", "Аксессуары для слуховых аппаратов", "Hearing aids accessories"),
        ],
    ),
    (
        "Дезинфекция и гигиена",
        "Disinfection & Hygiene",
        "disinfection-hygiene",
        "Дезинфекция и гигиена",
        "Disinfection and hygiene",
        [
            ("Бактерицидные облучатели", "UV Sterilizers", "uv-sterilizers", "Бактерицидные облучатели", "UV sterilizers"),
            ("Стерилизаторы", "Sterilizers", "sterilizers", "Стерилизаторы", "Sterilizers"),
            ("Дезинфицирующие средства", "Disinfectants", "disinfectants", "Дезинфицирующие средства", "Disinfectants"),
            ("Санитайзеры", "Hand Sanitizers", "hand-sanitizers", "Санитайзеры", "Hand sanitizers"),
        ],
    ),
]

# Электроника: L2 с L3 и L4 подкатегориями (рекурсивная структура как у посуды)
ELECTRONICS_SUBCATEGORIES = [
    (
        "Смартфоны и телефоны",
        "Smartphones & Phones",
        "smartphones-phones",
        "Смартфоны и телефоны",
        "Smartphones and phones",
        [
            ("Смартфоны", "Smartphones", "smartphones", "Смартфоны", "Smartphones"),
            ("Кнопочные телефоны", "Feature Phones", "feature-phones", "Кнопочные телефоны", "Feature phones"),
            (
                "Аксессуары для телефонов",
                "Phone Accessories",
                "phone-accessories",
                "Аксессуары для телефонов",
                "Phone accessories",
                [
                    ("Чехлы", "Cases", "phone-cases", "Чехлы для телефонов", "Phone cases"),
                    ("Защитные стёкла", "Screen Protectors", "screen-protectors", "Защитные стёкла", "Screen protectors"),
                    ("Зарядные устройства", "Chargers", "chargers", "Зарядные устройства", "Chargers"),
                    ("Кабели", "Cables", "cables", "Кабели", "Cables"),
                ],
            ),
        ],
    ),
    (
        "Ноутбуки и компьютеры",
        "Laptops & Computers",
        "laptops-computers",
        "Ноутбуки и компьютеры",
        "Laptops and computers",
        [
            ("Ноутбуки", "Laptops", "laptops", "Ноутбуки", "Laptops"),
            ("Нетбуки", "Netbooks", "netbooks", "Нетбуки", "Netbooks"),
            ("Настольные ПК", "Desktop PCs", "desktop-pcs", "Настольные ПК", "Desktop PCs"),
            ("Моноблоки", "All-in-One PCs", "all-in-one-pcs", "Моноблоки", "All-in-One PCs"),
            ("Мини-ПК", "Mini PCs", "mini-pcs", "Мини-ПК", "Mini PCs"),
            ("Серверы", "Servers", "servers", "Серверы", "Servers"),
        ],
    ),
    (
        "Планшеты",
        "Tablets",
        "tablets",
        "Планшеты",
        "Tablets",
        [
            ("Android-планшеты", "Android Tablets", "android-tablets", "Android-планшеты", "Android tablets"),
            ("iPad", "iPads", "ipads", "iPad", "iPads"),
            ("Windows-планшеты", "Windows Tablets", "windows-tablets", "Windows-планшеты", "Windows tablets"),
        ],
    ),
    (
        "Телевизоры и дисплеи",
        "TVs & Displays",
        "tvs-displays",
        "Телевизоры и дисплеи",
        "TVs and displays",
        [
            (
                "Телевизоры",
                "TVs",
                "tvs",
                "Телевизоры",
                "TVs",
                [
                    ("Smart TV", "Smart TV", "smart-tv", "Smart TV", "Smart TV"),
                    ("OLED TV", "OLED TV", "oled-tv", "OLED TV", "OLED TV"),
                    ("QLED TV", "QLED TV", "qled-tv", "QLED TV", "QLED TV"),
                    ("LED TV", "LED TV", "led-tv", "LED TV", "LED TV"),
                ],
            ),
            (
                "Мониторы",
                "Monitors",
                "monitors",
                "Мониторы",
                "Monitors",
                [
                    ("Игровые мониторы", "Gaming Monitors", "gaming-monitors", "Игровые мониторы", "Gaming monitors"),
                    ("Офисные мониторы", "Office Monitors", "office-monitors", "Офисные мониторы", "Office monitors"),
                    ("Профессиональные мониторы", "Professional Monitors", "professional-monitors", "Профессиональные мониторы", "Professional monitors"),
                ],
            ),
            ("Проекторы", "Projectors", "projectors-display", "Проекторы", "Projectors"),
        ],
    ),
    (
        "Аудиотехника",
        "Audio",
        "audio",
        "Аудиотехника",
        "Audio equipment",
        [
            (
                "Наушники",
                "Headphones",
                "headphones",
                "Наушники",
                "Headphones",
                [
                    ("Полноразмерные", "Over-Ear", "over-ear-headphones", "Полноразмерные наушники", "Over-ear headphones"),
                    ("Накладные", "On-Ear", "on-ear-headphones", "Накладные наушники", "On-ear headphones"),
                    ("Вкладыши", "In-Ear", "in-ear-headphones", "Вкладыши", "In-ear headphones"),
                ],
            ),
            ("Беспроводные наушники", "Wireless Earbuds", "wireless-earbuds", "Беспроводные наушники", "Wireless earbuds"),
            (
                "Колонки",
                "Speakers",
                "speakers",
                "Колонки",
                "Speakers",
                [
                    ("Портативные колонки", "Portable Speakers", "portable-speakers", "Портативные колонки", "Portable speakers"),
                    ("Умные колонки", "Smart Speakers", "smart-speakers-audio", "Умные колонки", "Smart speakers"),
                    ("Домашние аудиосистемы", "Home Audio Systems", "home-audio-systems", "Домашние аудиосистемы", "Home audio systems"),
                ],
            ),
            ("Саундбары", "Soundbars", "soundbars", "Саундбары", "Soundbars"),
            ("Микрофоны", "Microphones", "microphones", "Микрофоны", "Microphones"),
        ],
    ),
    (
        "Фото и видео",
        "Photo & Video",
        "photo-video",
        "Фото и видео",
        "Photo and video",
        [
            (
                "Фотоаппараты",
                "Cameras",
                "cameras",
                "Фотоаппараты",
                "Cameras",
                [
                    ("Зеркальные", "DSLR", "dslr", "Зеркальные камеры", "DSLR cameras"),
                    ("Беззеркальные", "Mirrorless", "mirrorless", "Беззеркальные камеры", "Mirrorless cameras"),
                    ("Компактные", "Compact", "compact-cameras", "Компактные камеры", "Compact cameras"),
                    ("Экшн-камеры", "Action Cameras", "action-cameras", "Экшн-камеры", "Action cameras"),
                ],
            ),
            ("Объективы", "Lenses", "lenses", "Объективы", "Lenses"),
            ("Видеокамеры", "Camcorders", "camcorders", "Видеокамеры", "Camcorders"),
            ("Дроны", "Drones", "drones", "Дроны", "Drones"),
            (
                "Аксессуары",
                "Accessories",
                "photo-video-accessories",
                "Аксессуары для фото и видео",
                "Photo and video accessories",
                [
                    ("Штативы", "Tripods", "tripods", "Штативы", "Tripods"),
                    ("Сумки для камер", "Camera Bags", "camera-bags", "Сумки для камер", "Camera bags"),
                    ("Карты памяти", "Memory Cards", "memory-cards", "Карты памяти", "Memory cards"),
                ],
            ),
        ],
    ),
    (
        "Игровая техника",
        "Gaming",
        "gaming",
        "Игровая техника",
        "Gaming equipment",
        [
            ("Игровые консоли", "Game Consoles", "game-consoles", "Игровые консоли", "Game consoles"),
            ("Игровые контроллеры", "Controllers", "gaming-controllers", "Игровые контроллеры", "Gaming controllers"),
            ("Игровые гарнитуры", "Gaming Headsets", "gaming-headsets", "Игровые гарнитуры", "Gaming headsets"),
            ("Игровые клавиатуры", "Gaming Keyboards", "gaming-keyboards", "Игровые клавиатуры", "Gaming keyboards"),
            ("Игровые мыши", "Gaming Mice", "gaming-mice", "Игровые мыши", "Gaming mice"),
            ("VR-гарнитуры", "VR Headsets", "vr-headsets", "VR-гарнитуры", "VR headsets"),
        ],
    ),
    (
        "Умный дом",
        "Smart Home",
        "smart-home",
        "Умный дом",
        "Smart home",
        [
            ("Умные колонки", "Smart Speakers", "smart-speakers-home", "Умные колонки", "Smart speakers"),
            ("Умные лампочки", "Smart Bulbs", "smart-bulbs", "Умные лампочки", "Smart bulbs"),
            ("Умные розетки", "Smart Plugs", "smart-plugs", "Умные розетки", "Smart plugs"),
            ("IP-камеры", "IP Cameras", "ip-cameras", "IP-камеры", "IP cameras"),
            ("Умные замки", "Smart Locks", "smart-locks", "Умные замки", "Smart locks"),
            ("Умные термостаты", "Smart Thermostats", "smart-thermostats", "Умные термостаты", "Smart thermostats"),
        ],
    ),
    (
        "Носимая электроника",
        "Wearables",
        "wearables",
        "Носимая электроника",
        "Wearables",
        [
            ("Умные часы", "Smartwatches", "smartwatches", "Умные часы", "Smartwatches"),
            ("Фитнес-трекеры", "Fitness Trackers", "fitness-trackers", "Фитнес-трекеры", "Fitness trackers"),
            ("Умные очки", "Smart Glasses", "smart-glasses", "Умные очки", "Smart glasses"),
        ],
    ),
    (
        "Компьютерные комплектующие",
        "PC Components",
        "pc-components",
        "Компьютерные комплектующие",
        "PC components",
        [
            ("Процессоры", "CPUs", "cpus", "Процессоры", "CPUs"),
            ("Видеокарты", "GPUs", "gpus", "Видеокарты", "GPUs"),
            ("Материнские платы", "Motherboards", "motherboards", "Материнские платы", "Motherboards"),
            ("Оперативная память", "RAM", "pc-ram", "Оперативная память", "RAM"),
            (
                "Накопители",
                "Storage",
                "pc-storage",
                "Накопители",
                "Storage",
                [
                    ("SSD", "SSD", "ssd", "SSD накопители", "SSD drives"),
                    ("HDD", "HDD", "hdd", "HDD накопители", "HDD drives"),
                    ("NVMe", "NVMe", "nvme", "NVMe накопители", "NVMe drives"),
                ],
            ),
            ("Блоки питания", "Power Supplies", "power-supplies", "Блоки питания", "Power supplies"),
            ("Корпуса", "PC Cases", "pc-cases", "Корпуса ПК", "PC cases"),
        ],
    ),
    (
        "Сетевое оборудование",
        "Networking",
        "networking",
        "Сетевое оборудование",
        "Networking equipment",
        [
            ("Роутеры", "Routers", "routers", "Роутеры", "Routers"),
            ("Wi-Fi усилители", "Wi-Fi Extenders", "wifi-extenders", "Wi-Fi усилители", "Wi-Fi extenders"),
            ("Коммутаторы", "Switches", "network-switches", "Коммутаторы", "Network switches"),
            ("Сетевые карты", "Network Cards", "network-cards", "Сетевые карты", "Network cards"),
        ],
    ),
    (
        "Офисная техника",
        "Office Equipment",
        "office-equipment",
        "Офисная техника",
        "Office equipment",
        [
            ("Принтеры", "Printers", "printers", "Принтеры", "Printers"),
            ("Сканеры", "Scanners", "scanners", "Сканеры", "Scanners"),
            ("МФУ", "Multifunction Printers", "mfu", "Многофункциональные устройства", "Multifunction printers"),
            ("Проекторы", "Projectors", "projectors-office", "Проекторы для офиса", "Office projectors"),
            ("Уничтожители бумаг", "Shredders", "shredders", "Уничтожители бумаг", "Shredders"),
        ],
    ),
    (
        "Аксессуары и периферия",
        "Accessories & Peripherals",
        "accessories-peripherals",
        "Аксессуары и периферия",
        "Accessories and peripherals",
        [
            ("Клавиатуры", "Keyboards", "keyboards", "Клавиатуры", "Keyboards"),
            ("Мышки", "Mice", "mice", "Мышки", "Mice"),
            ("Веб-камеры", "Webcams", "webcams", "Веб-камеры", "Webcams"),
            ("USB-хабы", "USB Hubs", "usb-hubs", "USB-хабы", "USB hubs"),
            ("Внешние аккумуляторы", "Power Banks", "power-banks", "Внешние аккумуляторы", "Power banks"),
            ("Сетевые фильтры", "Surge Protectors", "surge-protectors", "Сетевые фильтры", "Surge protectors"),
        ],
    ),
]

# Спорттовары: L2 с L3 и L4 подкатегориями
SPORTS_SUBCATEGORIES = [
    (
        "Фитнес и тренажёры",
        "Fitness & Gym Equipment",
        "fitness-gym",
        "Фитнес и тренажёры",
        "Fitness and gym equipment",
        [
            (
                "Кардиотренажёры",
                "Cardio Equipment",
                "cardio-equipment",
                "Кардиотренажёры",
                "Cardio equipment",
                [
                    ("Беговые дорожки", "Treadmills", "treadmills", "Беговые дорожки", "Treadmills"),
                    ("Велотренажёры", "Exercise Bikes", "exercise-bikes", "Велотренажёры", "Exercise bikes"),
                    ("Эллиптические тренажёры", "Ellipticals", "ellipticals", "Эллиптические тренажёры", "Ellipticals"),
                    ("Гребные тренажёры", "Rowing Machines", "rowing-machines", "Гребные тренажёры", "Rowing machines"),
                    ("Степперы", "Steppers", "steppers", "Степперы", "Steppers"),
                ],
            ),
            (
                "Силовые тренажёры",
                "Strength Equipment",
                "strength-equipment",
                "Силовые тренажёры",
                "Strength equipment",
                [
                    ("Штанги", "Barbells", "barbells", "Штанги", "Barbells"),
                    ("Гантели", "Dumbbells", "dumbbells", "Гантели", "Dumbbells"),
                    ("Гири", "Kettlebells", "kettlebells", "Гири", "Kettlebells"),
                    ("Силовые рамы", "Power Racks", "power-racks", "Силовые рамы", "Power racks"),
                    ("Скамьи", "Benches", "weight-benches", "Скамьи для жима", "Weight benches"),
                    ("Тросовые тренажёры", "Cable Machines", "cable-machines", "Тросовые тренажёры", "Cable machines"),
                ],
            ),
            (
                "Аксессуары для фитнеса",
                "Fitness Accessories",
                "fitness-accessories",
                "Аксессуары для фитнеса",
                "Fitness accessories",
                [
                    ("Коврики для йоги", "Yoga Mats", "yoga-mats", "Коврики для йоги", "Yoga mats"),
                    ("Эспандеры", "Resistance Bands", "resistance-bands", "Эспандеры", "Resistance bands"),
                    ("Ролики для пресса", "Ab Rollers", "ab-rollers", "Ролики для пресса", "Ab rollers"),
                    ("Скакалки", "Jump Ropes", "jump-ropes", "Скакалки", "Jump ropes"),
                    ("Пояса для тяжёлой атлетики", "Weightlifting Belts", "weightlifting-belts", "Пояса для тяжёлой атлетики", "Weightlifting belts"),
                    ("Перчатки для фитнеса", "Fitness Gloves", "fitness-gloves", "Перчатки для фитнеса", "Fitness gloves"),
                ],
            ),
            (
                "Спортивное питание",
                "Sports Nutrition",
                "sports-sports-nutrition",
                "Спортивное питание",
                "Sports nutrition",
                [
                    ("Протеин", "Protein", "sports-protein", "Протеин", "Sports protein"),
                    ("Креатин", "Creatine", "sports-creatine", "Креатин", "Sports creatine"),
                    ("Аминокислоты", "Amino Acids", "sports-amino-acids", "Аминокислоты", "Sports amino acids"),
                    ("Энергетики", "Energy Drinks", "sports-energy-drinks", "Энергетики", "Sports energy drinks"),
                ],
            ),
        ],
    ),
    (
        "Командные виды спорта",
        "Team Sports",
        "team-sports",
        "Командные виды спорта",
        "Team sports",
        [
            (
                "Футбол",
                "Football (Soccer)",
                "football",
                "Футбол",
                "Football (Soccer)",
                [
                    ("Футбольные мячи", "Balls", "football-balls", "Футбольные мячи", "Football balls"),
                    ("Ворота", "Goals", "football-goals", "Футбольные ворота", "Football goals"),
                    ("Щитки", "Shin Guards", "shin-guards", "Щитки", "Shin guards"),
                    ("Форма", "Kits", "football-kits", "Футбольная форма", "Football kits"),
                ],
            ),
            (
                "Баскетбол",
                "Basketball",
                "basketball",
                "Баскетбол",
                "Basketball",
                [
                    ("Баскетбольные мячи", "Balls", "basketball-balls", "Баскетбольные мячи", "Basketball balls"),
                    ("Кольца и стойки", "Hoops & Stands", "basketball-hoops", "Кольца и стойки", "Basketball hoops & stands"),
                    ("Форма", "Uniforms", "basketball-uniforms", "Баскетбольная форма", "Basketball uniforms"),
                ],
            ),
            (
                "Волейбол",
                "Volleyball",
                "volleyball",
                "Волейбол",
                "Volleyball",
                [
                    ("Волейбольные мячи", "Balls", "volleyball-balls", "Волейбольные мячи", "Volleyball balls"),
                    ("Сетки", "Nets", "volleyball-nets", "Волейбольные сетки", "Volleyball nets"),
                    ("Наколенники", "Knee Pads", "volleyball-knee-pads", "Наколенники для волейбола", "Volleyball knee pads"),
                ],
            ),
            ("Регби", "Rugby", "rugby", "Регби", "Rugby"),
            (
                "Хоккей",
                "Hockey",
                "hockey",
                "Хоккей",
                "Hockey",
                [
                    ("Клюшки", "Sticks", "hockey-sticks", "Хоккейные клюшки", "Hockey sticks"),
                    ("Шайбы", "Pucks", "hockey-pucks", "Шайбы", "Hockey pucks"),
                    ("Защита", "Protective Gear", "hockey-protective-gear", "Хоккейная защита", "Hockey protective gear"),
                ],
            ),
        ],
    ),
    (
        "Ракеточные виды спорта",
        "Racket Sports",
        "racket-sports",
        "Ракеточные виды спорта",
        "Racket sports",
        [
            (
                "Теннис",
                "Tennis",
                "tennis",
                "Теннис",
                "Tennis",
                [
                    ("Ракетки", "Rackets", "tennis-rackets", "Теннисные ракетки", "Tennis rackets"),
                    ("Мячи", "Balls", "tennis-balls", "Теннисные мячи", "Tennis balls"),
                    ("Сетки", "Nets", "tennis-nets", "Теннисные сетки", "Tennis nets"),
                ],
            ),
            (
                "Бадминтон",
                "Badminton",
                "badminton",
                "Бадминтон",
                "Badminton",
                [
                    ("Ракетки", "Rackets", "badminton-rackets", "Ракетки для бадминтона", "Badminton rackets"),
                    ("Воланы", "Shuttlecocks", "shuttlecocks", "Воланы", "Shuttlecocks"),
                ],
            ),
            (
                "Настольный теннис",
                "Table Tennis",
                "table-tennis",
                "Настольный теннис",
                "Table tennis",
                [
                    ("Ракетки", "Paddles", "table-tennis-paddles", "Ракетки для настольного тенниса", "Table tennis paddles"),
                    ("Мячи", "Balls", "table-tennis-balls", "Мячи для настольного тенниса", "Table tennis balls"),
                    ("Столы", "Tables", "table-tennis-tables", "Столы для настольного тенниса", "Table tennis tables"),
                ],
            ),
        ],
    ),
    (
        "Боевые искусства и единоборства",
        "Martial Arts & Combat Sports",
        "martial-arts",
        "Боевые искусства и единоборства",
        "Martial arts & combat sports",
        [
            ("Боксёрские перчатки", "Boxing Gloves", "boxing-gloves", "Боксёрские перчатки", "Boxing gloves"),
            ("Боксёрские груши", "Punching Bags", "punching-bags", "Боксёрские груши", "Punching bags"),
            (
                "Защита",
                "Protective Gear",
                "martial-arts-protective-gear",
                "Защитная экипировка",
                "Martial arts protective gear",
                [
                    ("Шлемы", "Helmets", "martial-arts-helmets", "Шлемы для единоборств", "Martial arts helmets"),
                    ("Капы", "Mouthguards", "mouthguards", "Капы", "Mouthguards"),
                    ("Бандажи", "Hand Wraps", "hand-wraps", "Бандажи для рук", "Hand wraps"),
                ],
            ),
            ("Кимоно", "Gi / Kimonos", "gi-kimonos", "Кимоно", "Gi / Kimonos"),
            ("Татами", "Tatami Mats", "tatami-mats", "Татами", "Tatami mats"),
        ],
    ),
    (
        "Водные виды спорта",
        "Water Sports",
        "water-sports",
        "Водные виды спорта",
        "Water sports",
        [
            (
                "Плавание",
                "Swimming",
                "swimming",
                "Плавание",
                "Swimming",
                [
                    ("Купальники", "Swimwear", "swimming-swimwear", "Купальники для плавания", "Swimming swimwear"),
                    ("Очки для плавания", "Goggles", "swimming-goggles", "Очки для плавания", "Swimming goggles"),
                    ("Шапочки", "Swim Caps", "swim-caps", "Шапочки для плавания", "Swim caps"),
                    ("Ласты", "Fins", "swim-fins", "Ласты", "Swim fins"),
                    ("Доски для плавания", "Kickboards", "kickboards", "Доски для плавания", "Kickboards"),
                ],
            ),
            (
                "Дайвинг",
                "Diving",
                "diving",
                "Дайвинг",
                "Diving",
                [
                    ("Маски", "Masks", "diving-masks", "Маски для дайвинга", "Diving masks"),
                    ("Трубки", "Snorkels", "snorkels", "Трубки", "Snorkels"),
                    ("Гидрокостюмы", "Wetsuits", "wetsuits", "Гидрокостюмы", "Wetsuits"),
                ],
            ),
            (
                "Серфинг и SUP",
                "Surfing & SUP",
                "surfing-sup",
                "Серфинг и SUP",
                "Surfing & SUP",
                [
                    ("Доски", "Boards", "surf-boards", "Доски для серфинга и SUP", "Surf and SUP boards"),
                    ("Вёсла", "Paddles", "sup-paddles", "Вёсла для SUP", "SUP paddles"),
                ],
            ),
        ],
    ),
    (
        "Зимние виды спорта",
        "Winter Sports",
        "winter-sports",
        "Зимние виды спорта",
        "Winter sports",
        [
            ("Лыжи", "Skis", "skis", "Лыжи", "Skis"),
            ("Сноуборды", "Snowboards", "snowboards", "Сноуборды", "Snowboards"),
            ("Лыжные ботинки", "Ski Boots", "ski-boots", "Лыжные ботинки", "Ski boots"),
            ("Лыжные палки", "Ski Poles", "ski-poles", "Лыжные палки", "Ski poles"),
            ("Коньки", "Ice Skates", "ice-skates", "Коньки", "Ice skates"),
            (
                "Защита",
                "Protective Gear",
                "winter-protective-gear",
                "Защитная экипировка",
                "Winter protective gear",
                [
                    ("Шлемы", "Helmets", "winter-helmets", "Шлемы для зимнего спорта", "Winter sports helmets"),
                    ("Маски", "Goggles", "winter-goggles", "Горнолыжные очки", "Ski goggles"),
                    ("Наколенники", "Knee Pads", "winter-knee-pads", "Наколенники для зимнего спорта", "Winter knee pads"),
                ],
            ),
        ],
    ),
    (
        "Велоспорт",
        "Cycling",
        "cycling",
        "Велоспорт",
        "Cycling",
        [
            (
                "Велосипеды",
                "Bicycles",
                "bicycles",
                "Велосипеды",
                "Bicycles",
                [
                    ("Горные", "Mountain Bikes", "mountain-bikes", "Горные велосипеды", "Mountain bikes"),
                    ("Шоссейные", "Road Bikes", "road-bikes", "Шоссейные велосипеды", "Road bikes"),
                    ("Городские", "City Bikes", "city-bikes", "Городские велосипеды", "City bikes"),
                    ("BMX", "BMX", "bmx", "BMX велосипеды", "BMX bikes"),
                    ("Электровелосипеды", "E-Bikes", "e-bikes", "Электровелосипеды", "E-bikes"),
                ],
            ),
            (
                "Аксессуары для велосипеда",
                "Cycling Accessories",
                "cycling-accessories",
                "Аксессуары для велосипеда",
                "Cycling accessories",
                [
                    ("Шлемы", "Helmets", "cycling-helmets", "Велосипедные шлемы", "Cycling helmets"),
                    ("Замки", "Locks", "bike-locks", "Замки для велосипеда", "Bike locks"),
                    ("Насосы", "Pumps", "bike-pumps", "Насосы для велосипеда", "Bike pumps"),
                    ("Фонари", "Lights", "bike-lights", "Фонари для велосипеда", "Bike lights"),
                    ("Фляги", "Water Bottles", "bike-water-bottles", "Велосипедные фляги", "Bike water bottles"),
                ],
            ),
            (
                "Запчасти",
                "Parts",
                "cycling-parts",
                "Запчасти для велосипеда",
                "Cycling parts",
                [
                    ("Покрышки", "Tires", "bike-tires", "Велосипедные покрышки", "Bike tires"),
                    ("Тормоза", "Brakes", "bike-brakes", "Велосипедные тормоза", "Bike brakes"),
                    ("Педали", "Pedals", "bike-pedals", "Велосипедные педали", "Bike pedals"),
                ],
            ),
        ],
    ),
    (
        "Бег и ходьба",
        "Running & Walking",
        "running-walking",
        "Бег и ходьба",
        "Running and walking",
        [
            ("Кроссовки для бега", "Running Shoes", "sports-running-shoes", "Кроссовки для бега", "Sports running shoes"),
            ("Беговая одежда", "Running Apparel", "running-apparel", "Беговая одежда", "Running apparel"),
            ("Пульсометры", "Heart Rate Monitors", "heart-rate-monitors", "Пульсометры", "Heart rate monitors"),
            ("GPS-часы", "GPS Watches", "gps-watches", "GPS-часы для бега", "GPS watches for running"),
            ("Беговые пояса", "Running Belts", "running-belts", "Беговые пояса", "Running belts"),
        ],
    ),
    (
        "Туризм и активный отдых",
        "Outdoor & Hiking",
        "outdoor-hiking",
        "Туризм и активный отдых",
        "Outdoor and hiking",
        [
            ("Рюкзаки", "Backpacks", "hiking-backpacks", "Туристические рюкзаки", "Hiking backpacks"),
            ("Палатки", "Tents", "tents", "Палатки", "Tents"),
            ("Спальные мешки", "Sleeping Bags", "sleeping-bags", "Спальные мешки", "Sleeping bags"),
            ("Треккинговые палки", "Trekking Poles", "trekking-poles", "Треккинговые палки", "Trekking poles"),
            ("Туристические ботинки", "Hiking Boots", "hiking-boots", "Туристические ботинки", "Hiking boots"),
            ("Фонари", "Flashlights", "flashlights", "Фонари", "Flashlights"),
        ],
    ),
    (
        "Спортивная одежда и обувь",
        "Sportswear & Footwear",
        "sportswear-footwear",
        "Спортивная одежда и обувь",
        "Sportswear and footwear",
        [
            ("Футболки", "T-Shirts", "sports-tshirts", "Спортивные футболки", "Sports T-shirts"),
            ("Шорты", "Shorts", "sports-shorts", "Спортивные шорты", "Sports shorts"),
            ("Леггинсы", "Leggings", "sports-leggings", "Спортивные леггинсы", "Sports leggings"),
            ("Спортивные костюмы", "Tracksuits", "tracksuits", "Спортивные костюмы", "Tracksuits"),
            ("Куртки", "Jackets", "sports-jackets", "Спортивные куртки", "Sports jackets"),
            ("Кроссовки", "Sneakers", "sports-sneakers", "Спортивные кроссовки", "Sports sneakers"),
            ("Компрессионная одежда", "Compression Wear", "compression-wear", "Компрессионная одежда", "Compression wear"),
        ],
    ),
]

# Исламская одежда: L2 с L3 подкатегориями
ISLAMIC_CLOTHING_SUBCATEGORIES = [
    # Женская одежда
    (
        "Хиджабы",
        "Hijabs",
        "hijabs",
        "Хиджабы",
        "Hijabs",
        [
            ("Классический хиджаб", "Classic Hijab", "classic-hijab", "Классический хиджаб", "Classic hijab"),
            ("Шаль-хиджаб", "Shawl Hijab", "shawl-hijab", "Шаль-хиджаб", "Shawl hijab"),
            ("Тюрбан-хиджаб", "Turban Hijab", "turban-hijab", "Тюрбан-хиджаб", "Turban hijab"),
            ("Практичный хиджаб", "Practical Hijab", "practical-hijab", "Практичный хиджаб", "Practical hijab"),
            ("Спортивный хиджаб", "Sport Hijab", "sport-hijab", "Спортивный хиджаб", "Sport hijab"),
        ],
    ),
    (
        "Абайи",
        "Abayas",
        "abayas",
        "Абайи",
        "Abayas",
        [
            ("Классическая абайя", "Classic Abaya", "classic-abaya", "Классическая абайя", "Classic abaya"),
            ("Вышитая абайя", "Embroidered Abaya", "embroidered-abaya", "Вышитая абайя", "Embroidered abaya"),
            ("Открытая абайя", "Open-Front Abaya", "open-front-abaya", "Открытая абайя", "Open-front abaya"),
            ("Абайя с поясом", "Belted Abaya", "belted-abaya", "Абайя с поясом", "Belted abaya"),
            ("Спортивная абайя", "Sport Abaya", "sport-abaya", "Спортивная абайя", "Sport abaya"),
        ],
    ),
    (
        "Джилбабы",
        "Jilbabs",
        "jilbabs",
        "Джилбабы",
        "Jilbabs",
        [
            ("Двусоставный джилбаб", "Two-Piece Jilbab", "two-piece-jilbab", "Двусоставный джилбаб", "Two-piece jilbab"),
            ("Однобортный джилбаб", "Single-Piece Jilbab", "single-piece-jilbab", "Однобортный джилбаб", "Single-piece jilbab"),
        ],
    ),
    (
        "Никабы",
        "Niqabs",
        "niqabs",
        "Никабы",
        "Niqabs",
        [
            ("Полный никаб", "Full Niqab", "full-niqab", "Полный никаб", "Full niqab"),
            ("Половинный никаб", "Half Niqab", "half-niqab", "Половинный никаб", "Half niqab"),
        ],
    ),
    (
        "Платья",
        "Dresses",
        "islamic-dresses",
        "Исламские платья",
        "Islamic dresses",
        [
            ("Макси-платья", "Maxi Dresses", "maxi-dresses", "Макси-платья", "Maxi dresses"),
            ("Повседневные платья", "Casual Dresses", "casual-dresses", "Повседневные платья", "Casual dresses"),
            ("Праздничные платья", "Festive Dresses", "festive-dresses", "Праздничные платья", "Festive dresses"),
        ],
    ),
    (
        "Верхняя одежда",
        "Outerwear",
        "islamic-outerwear-women",
        "Верхняя одежда для женщин",
        "Women's outerwear",
        [
            ("Пальто", "Coats", "islamic-coats", "Пальто", "Coats"),
            ("Плащи", "Cloaks", "islamic-cloaks", "Плащи", "Cloaks"),
        ],
    ),
    (
        "Комплекты",
        "Sets",
        "islamic-sets",
        "Комплекты исламской одежды",
        "Islamic clothing sets",
        [
            ("Костюм с хиджабом", "Hijab Set", "hijab-set", "Костюм с хиджабом", "Hijab set"),
            ("Абайя + хиджаб", "Abaya + Hijab Set", "abaya-hijab-set", "Абайя + хиджаб", "Abaya + hijab set"),
        ],
    ),
    # Мужская одежда
    (
        "Тобы",
        "Thobes",
        "thobes",
        "Тобы",
        "Thobes",
        [
            ("Арабский тоб", "Arabic Thobe", "arabic-thobe", "Арабский тоб", "Arabic thobe"),
            ("Пакистанский тоб", "Pakistani Thobe", "pakistani-thobe", "Пакистанский тоб", "Pakistani thobe"),
            ("Марокканский тоб", "Moroccan Thobe", "moroccan-thobe", "Марокканский тоб", "Moroccan thobe"),
            ("Праздничный тоб", "Festive Thobe", "festive-thobe", "Праздничный тоб", "Festive thobe"),
        ],
    ),
    (
        "Куртасы",
        "Kurthas",
        "kurthas",
        "Куртасы",
        "Kurthas",
        [
            ("Длинный куртас", "Long Kurtha", "long-kurtha", "Длинный куртас", "Long kurtha"),
            ("Короткий куртас", "Short Kurtha", "short-kurtha", "Короткий куртас", "Short kurtha"),
        ],
    ),
    (
        "Шаровары",
        "Shalwar",
        "shalwar",
        "Шаровары",
        "Shalwar",
        [
            ("Классические шаровары", "Classic Shalwar", "classic-shalwar", "Классические шаровары", "Classic shalwar"),
            ("Зауженные шаровары", "Tapered Shalwar", "tapered-shalwar", "Зауженные шаровары", "Tapered shalwar"),
        ],
    ),
    (
        "Головные уборы",
        "Headwear",
        "islamic-headwear",
        "Головные уборы",
        "Islamic headwear",
        [
            ("Куфия", "Kufiya", "kufiya", "Куфия", "Kufiya"),
            ("Тюбетейка", "Kufi Cap", "kufi-cap", "Тюбетейка", "Kufi cap"),
            ("Тагия", "Taqiyah", "taqiyah", "Тагия", "Taqiyah"),
            ("Чалма", "Turban", "islamic-turban", "Чалма", "Turban"),
        ],
    ),
    (
        "Верхняя одежда мужская",
        "Men's Outerwear",
        "islamic-outerwear-men",
        "Верхняя одежда для мужчин",
        "Men's outerwear",
        [
            ("Бишт", "Bisht", "bisht", "Бишт", "Bisht"),
            ("Фараджийя", "Farajiyya", "farajiyya", "Фараджийя", "Farajiyya"),
        ],
    ),
    # Одежда для намаза
    (
        "Одежда для намаза",
        "Prayer Clothing",
        "prayer-clothing",
        "Одежда для намаза",
        "Prayer clothing",
        [
            ("Молитвенные платья", "Prayer Dresses", "prayer-dresses", "Молитвенные платья", "Prayer dresses"),
            ("Молитвенные накидки", "Prayer Capes", "prayer-capes", "Молитвенные накидки", "Prayer capes"),
            ("Молитвенные коврики", "Prayer Rugs", "prayer-rugs", "Молитвенные коврики", "Prayer rugs"),
            ("Тасбихи", "Tasbih Beads", "tasbih-beads", "Тасбихи", "Tasbih beads"),
        ],
    ),
    (
        "Праздничная одежда",
        "Festive & Occasion Wear",
        "festive-occasion-wear",
        "Праздничная исламская одежда",
        "Festive & occasion wear",
        [
            ("Одежда для Рамадана", "Ramadan Wear", "ramadan-wear", "Одежда для Рамадана", "Ramadan wear"),
            ("Одежда для Eid", "Eid Wear", "eid-wear", "Одежда для Eid", "Eid wear"),
            ("Свадебная одежда", "Wedding Wear", "wedding-wear", "Свадебная исламская одежда", "Wedding wear"),
        ],
    ),
]

# Аксессуары: L2 с L3 и L4 подкатегориями
ACCESSORIES_SUBCATEGORIES = [
    (
        "Сумки и кошельки",
        "Bags & Wallets",
        "bags-wallets",
        "Сумки и кошельки",
        "Bags and wallets",
        [
            (
                "Женские сумки",
                "Women's Bags",
                "womens-bags",
                "Женские сумки",
                "Women's bags",
                [
                    ("Сумки через плечо", "Shoulder Bags", "shoulder-bags", "Сумки через плечо", "Shoulder bags"),
                    ("Клатчи", "Clutches", "clutches", "Клатчи", "Clutches"),
                    ("Шоперы", "Tote Bags", "tote-bags", "Шоперы", "Tote bags"),
                    ("Рюкзаки", "Backpacks", "acc-womens-backpacks", "Женские рюкзаки", "Women's backpacks"),
                    ("Поясные сумки", "Belt Bags", "acc-belt-bags", "Поясные сумки", "Belt bags"),
                    ("Мини-сумки", "Mini Bags", "mini-bags", "Мини-сумки", "Mini bags"),
                ],
            ),
            (
                "Мужские сумки",
                "Men's Bags",
                "mens-bags",
                "Мужские сумки",
                "Men's bags",
                [
                    ("Портфели", "Briefcases", "briefcases", "Портфели", "Briefcases"),
                    ("Мессенджеры", "Messenger Bags", "messenger-bags", "Мессенджеры", "Messenger bags"),
                    ("Рюкзаки", "Backpacks", "acc-mens-backpacks", "Мужские рюкзаки", "Men's backpacks"),
                    ("Поясные сумки", "Belt Bags", "acc-mens-belt-bags", "Мужские поясные сумки", "Men's belt bags"),
                ],
            ),
            (
                "Кошельки",
                "Wallets",
                "wallets",
                "Кошельки",
                "Wallets",
                [
                    ("Портмоне", "Bifold Wallets", "bifold-wallets", "Портмоне", "Bifold wallets"),
                    ("Кардхолдеры", "Card Holders", "card-holders", "Кардхолдеры", "Card holders"),
                    ("Монетницы", "Coin Purses", "coin-purses", "Монетницы", "Coin purses"),
                    ("Клатч-кошельки", "Clutch Wallets", "clutch-wallets", "Клатч-кошельки", "Clutch wallets"),
                ],
            ),
            (
                "Дорожные сумки",
                "Travel Bags",
                "travel-bags",
                "Дорожные сумки",
                "Travel bags",
                [
                    ("Чемоданы", "Suitcases", "suitcases", "Чемоданы", "Suitcases"),
                    ("Дорожные сумки", "Duffle Bags", "duffle-bags", "Дорожные сумки", "Duffle bags"),
                    ("Органайзеры для путешествий", "Travel Organizers", "travel-organizers", "Органайзеры для путешествий", "Travel organizers"),
                ],
            ),
        ],
    ),
    (
        "Ювелирные украшения",
        "Jewelry",
        "acc-jewelry",
        "Ювелирные украшения",
        "Jewelry",
        [
            (
                "Кольца",
                "Rings",
                "acc-rings",
                "Кольца",
                "Rings",
                [
                    ("Обручальные", "Wedding Rings", "acc-wedding-rings", "Обручальные кольца", "Wedding rings"),
                    ("Помолвочные", "Engagement Rings", "acc-engagement-rings", "Помолвочные кольца", "Engagement rings"),
                    ("Коктейльные", "Cocktail Rings", "acc-cocktail-rings", "Коктейльные кольца", "Cocktail rings"),
                ],
            ),
            (
                "Серьги",
                "Earrings",
                "acc-earrings",
                "Серьги",
                "Earrings",
                [
                    ("Пусеты", "Studs", "acc-stud-earrings", "Пусеты", "Stud earrings"),
                    ("Подвески", "Drop Earrings", "acc-drop-earrings", "Серьги-подвески", "Drop earrings"),
                    ("Кольца", "Hoop Earrings", "acc-hoop-earrings", "Серьги-кольца", "Hoop earrings"),
                    ("Клипсы", "Clip-On Earrings", "acc-clip-earrings", "Клипсы", "Clip-on earrings"),
                ],
            ),
            (
                "Ожерелья и цепочки",
                "Necklaces & Chains",
                "acc-necklaces",
                "Ожерелья и цепочки",
                "Necklaces and chains",
                [
                    ("Колье", "Collar Necklaces", "acc-collar-necklaces", "Колье", "Collar necklaces"),
                    ("Цепочки", "Chains", "acc-chains", "Цепочки", "Chains"),
                    ("Подвески", "Pendants", "acc-pendants", "Подвески", "Pendants"),
                ],
            ),
            (
                "Браслеты",
                "Bracelets",
                "acc-bracelets",
                "Браслеты",
                "Bracelets",
                [
                    ("Жёсткие", "Bangles", "acc-bangles", "Жёсткие браслеты", "Bangles"),
                    ("Цепочки", "Chain Bracelets", "acc-chain-bracelets", "Цепочные браслеты", "Chain bracelets"),
                    ("Кожаные", "Leather Bracelets", "acc-leather-bracelets", "Кожаные браслеты", "Leather bracelets"),
                ],
            ),
            ("Броши", "Brooches", "acc-brooches", "Броши", "Brooches"),
        ],
    ),
    (
        "Бижутерия",
        "Fashion Jewelry",
        "fashion-jewelry",
        "Бижутерия",
        "Fashion jewelry",
        [
            ("Кольца", "Rings", "bijou-rings", "Бижутерия кольца", "Fashion jewelry rings"),
            ("Серьги", "Earrings", "bijou-earrings", "Бижутерия серьги", "Fashion jewelry earrings"),
            ("Колье", "Necklaces", "bijou-necklaces", "Бижутерия колье", "Fashion jewelry necklaces"),
            ("Браслеты", "Bracelets", "bijou-bracelets", "Бижутерия браслеты", "Fashion jewelry bracelets"),
            ("Наборы бижутерии", "Jewelry Sets", "bijou-sets", "Наборы бижутерии", "Fashion jewelry sets"),
        ],
    ),
    (
        "Часы",
        "Watches",
        "watches",
        "Часы",
        "Watches",
        [
            (
                "Мужские часы",
                "Men's Watches",
                "mens-watches",
                "Мужские часы",
                "Men's watches",
                [
                    ("Классические", "Classic", "mens-classic-watches", "Классические мужские часы", "Classic men's watches"),
                    ("Спортивные", "Sport", "mens-sport-watches", "Спортивные мужские часы", "Sport men's watches"),
                    ("Смарт-часы", "Smartwatches", "mens-smartwatches", "Мужские смарт-часы", "Men's smartwatches"),
                ],
            ),
            (
                "Женские часы",
                "Women's Watches",
                "womens-watches",
                "Женские часы",
                "Women's watches",
                [
                    ("Классические", "Classic", "womens-classic-watches", "Классические женские часы", "Classic women's watches"),
                    ("Модные", "Fashion", "womens-fashion-watches", "Модные женские часы", "Fashion women's watches"),
                    ("Смарт-часы", "Smartwatches", "womens-smartwatches", "Женские смарт-часы", "Women's smartwatches"),
                ],
            ),
            ("Детские часы", "Children's Watches", "childrens-watches", "Детские часы", "Children's watches"),
        ],
    ),
    (
        "Пояса и ремни",
        "Belts",
        "belts",
        "Пояса и ремни",
        "Belts",
        [
            (
                "Мужские ремни",
                "Men's Belts",
                "mens-belts",
                "Мужские ремни",
                "Men's belts",
                [
                    ("Классические", "Classic", "mens-classic-belts", "Классические мужские ремни", "Classic men's belts"),
                    ("Джинсовые", "Casual", "mens-casual-belts", "Джинсовые ремни", "Casual men's belts"),
                ],
            ),
            (
                "Женские ремни",
                "Women's Belts",
                "womens-belts",
                "Женские ремни",
                "Women's belts",
                [
                    ("Тонкие", "Thin", "womens-thin-belts", "Тонкие женские ремни", "Thin women's belts"),
                    ("Широкие", "Wide", "womens-wide-belts", "Широкие женские ремни", "Wide women's belts"),
                ],
            ),
        ],
    ),
    (
        "Головные уборы",
        "Headwear",
        "acc-headwear",
        "Головные уборы",
        "Headwear",
        [
            ("Шапки", "Beanies", "beanies", "Шапки", "Beanies"),
            (
                "Кепки",
                "Caps",
                "acc-caps",
                "Кепки",
                "Caps",
                [
                    ("Бейсболки", "Baseball Caps", "baseball-caps", "Бейсболки", "Baseball caps"),
                    ("Панамы", "Bucket Hats", "bucket-hats", "Панамы", "Bucket hats"),
                ],
            ),
            (
                "Шляпы",
                "Hats",
                "acc-hats",
                "Шляпы",
                "Hats",
                [
                    ("Фетровые", "Fedora", "fedora-hats", "Фетровые шляпы", "Fedora hats"),
                    ("Соломенные", "Straw Hats", "straw-hats", "Соломенные шляпы", "Straw hats"),
                ],
            ),
            ("Береты", "Berets", "berets", "Береты", "Berets"),
            ("Платки и банданы", "Scarves & Bandanas", "scarves-bandanas", "Платки и банданы", "Scarves and bandanas"),
        ],
    ),
    (
        "Шарфы и платки",
        "Scarves & Shawls",
        "scarves-shawls",
        "Шарфы и платки",
        "Scarves and shawls",
        [
            ("Шарфы", "Scarves", "scarves", "Шарфы", "Scarves"),
            ("Платки", "Shawls", "shawls", "Платки", "Shawls"),
            ("Палантины", "Stoles", "stoles", "Палантины", "Stoles"),
            ("Снуды", "Snoods", "snoods", "Снуды", "Snoods"),
        ],
    ),
    (
        "Перчатки",
        "Gloves",
        "acc-gloves",
        "Перчатки",
        "Gloves",
        [
            (
                "Зимние перчатки",
                "Winter Gloves",
                "winter-gloves",
                "Зимние перчатки",
                "Winter gloves",
                [
                    ("Кожаные", "Leather", "leather-gloves", "Кожаные перчатки", "Leather gloves"),
                    ("Вязаные", "Knitted", "knitted-gloves", "Вязаные перчатки", "Knitted gloves"),
                ],
            ),
            ("Перчатки без пальцев", "Fingerless Gloves", "fingerless-gloves", "Перчатки без пальцев", "Fingerless gloves"),
        ],
    ),
    (
        "Очки",
        "Eyewear",
        "eyewear",
        "Очки",
        "Eyewear",
        [
            (
                "Солнцезащитные очки",
                "Sunglasses",
                "sunglasses",
                "Солнцезащитные очки",
                "Sunglasses",
                [
                    ("Мужские", "Men's", "mens-sunglasses", "Мужские солнцезащитные очки", "Men's sunglasses"),
                    ("Женские", "Women's", "womens-sunglasses", "Женские солнцезащитные очки", "Women's sunglasses"),
                    ("Детские", "Children's", "childrens-sunglasses", "Детские солнцезащитные очки", "Children's sunglasses"),
                ],
            ),
            ("Имиджевые очки", "Fashion Glasses", "fashion-glasses", "Имиджевые очки", "Fashion glasses"),
        ],
    ),
    (
        "Аксессуары для волос",
        "Hair Accessories",
        "hair-accessories",
        "Аксессуары для волос",
        "Hair accessories",
        [
            ("Заколки", "Hair Clips", "acc-hair-clips", "Заколки", "Hair clips"),
            ("Резинки", "Hair Ties", "hair-ties", "Резинки для волос", "Hair ties"),
            ("Ободки", "Headbands", "acc-headbands", "Ободки", "Headbands"),
            ("Шпильки", "Bobby Pins", "bobby-pins", "Шпильки", "Bobby pins"),
            ("Повязки", "Hair Wraps", "hair-wraps", "Повязки для волос", "Hair wraps"),
        ],
    ),
    (
        "Зонты",
        "Umbrellas",
        "umbrellas",
        "Зонты",
        "Umbrellas",
        [
            ("Складные", "Folding", "folding-umbrellas", "Складные зонты", "Folding umbrellas"),
            ("Автоматические", "Automatic", "automatic-umbrellas", "Автоматические зонты", "Automatic umbrellas"),
            ("Трости", "Stick Umbrellas", "stick-umbrellas", "Зонты-трости", "Stick umbrellas"),
        ],
    ),
    (
        "Галстуки и платки для пиджака",
        "Ties & Pocket Squares",
        "ties-pocket-squares",
        "Галстуки и платки для пиджака",
        "Ties and pocket squares",
        [
            ("Галстуки", "Neckties", "neckties", "Галстуки", "Neckties"),
            ("Галстуки-бабочки", "Bow Ties", "bow-ties", "Галстуки-бабочки", "Bow ties"),
            ("Платки для кармана", "Pocket Squares", "pocket-squares", "Платки для кармана", "Pocket squares"),
        ],
    ),
    (
        "Аксессуары для телефона",
        "Phone Accessories (Fashion)",
        "acc-phone-accessories",
        "Аксессуары для телефона",
        "Phone accessories (fashion)",
        [
            ("Чехлы", "Phone Cases", "acc-phone-cases", "Чехлы для телефона", "Phone cases"),
            ("Попсокеты", "Popsockets", "popsockets", "Попсокеты", "Popsockets"),
            ("Ремешки для телефона", "Phone Straps", "phone-straps", "Ремешки для телефона", "Phone straps"),
        ],
    ),
]

# Парфюмерия: L2 с L3 и L4 подкатегориями
PERFUMERY_SUBCATEGORIES = [
    (
        "Духи и туалетная вода",
        "Fragrances",
        "fragrances",
        "Духи и туалетная вода",
        "Fragrances",
        [
            (
                "Женские ароматы",
                "Women's Fragrances",
                "womens-fragrances",
                "Женские ароматы",
                "Women's fragrances",
                [
                    ("Духи", "Parfum (EDP)", "parfum-edp", "Духи Parfum", "Parfum (EDP)"),
                    ("Туалетная вода", "Eau de Toilette (EDT)", "eau-de-toilette", "Туалетная вода EDT", "Eau de Toilette (EDT)"),
                    ("Одеколон", "Eau de Cologne (EDC)", "eau-de-cologne", "Одеколон EDC", "Eau de Cologne (EDC)"),
                    ("Мист для тела", "Body Mist", "body-mist", "Мист для тела", "Body mist"),
                ],
            ),
            (
                "Мужские ароматы",
                "Men's Fragrances",
                "mens-fragrances",
                "Мужские ароматы",
                "Men's fragrances",
                [
                    ("Духи", "Parfum (EDP)", "mens-parfum-edp", "Мужские духи Parfum", "Men's Parfum (EDP)"),
                    ("Туалетная вода", "Eau de Toilette (EDT)", "mens-edt", "Мужская туалетная вода EDT", "Men's Eau de Toilette (EDT)"),
                    ("Одеколон", "Eau de Cologne (EDC)", "mens-edc", "Мужской одеколон EDC", "Men's Eau de Cologne (EDC)"),
                ],
            ),
            ("Унисекс ароматы", "Unisex Fragrances", "unisex-fragrances", "Унисекс ароматы", "Unisex fragrances"),
            ("Детские ароматы", "Children's Fragrances", "childrens-fragrances", "Детские ароматы", "Children's fragrances"),
            (
                "Нишевая парфюмерия",
                "Niche Perfumery",
                "niche-perfumery",
                "Нишевая парфюмерия",
                "Niche perfumery",
                [
                    ("Арабская парфюмерия", "Arabic Perfumery", "arabic-perfumery", "Арабская парфюмерия", "Arabic perfumery"),
                    ("Авторская парфюмерия", "Artisan Perfumery", "artisan-perfumery", "Авторская парфюмерия", "Artisan perfumery"),
                ],
            ),
        ],
    ),
    (
        "Масляные духи",
        "Oil Perfumes",
        "oil-perfumes",
        "Масляные духи",
        "Oil perfumes",
        [
            ("Роликовые", "Roll-On", "roll-on-oil", "Роликовые масляные духи", "Roll-on oil perfumes"),
            ("Флаконные", "Bottle", "bottle-oil-perfumes", "Флаконные масляные духи", "Bottle oil perfumes"),
            ("Арабские масляные духи", "Arabic Oil Perfumes", "arabic-oil-perfumes", "Арабские масляные духи", "Arabic oil perfumes"),
        ],
    ),
    (
        "Парфюмированные средства",
        "Scented Products",
        "scented-products",
        "Парфюмированные средства",
        "Scented products",
        [
            (
                "Дезодоранты",
                "Deodorants",
                "perfumed-deodorants",
                "Парфюмированные дезодоранты",
                "Perfumed deodorants",
                [
                    ("Спрей", "Spray", "deodorant-spray", "Дезодорант спрей", "Deodorant spray"),
                    ("Стик", "Stick", "deodorant-stick", "Дезодорант стик", "Deodorant stick"),
                    ("Ролик", "Roll-On", "deodorant-roll-on", "Дезодорант ролик", "Deodorant roll-on"),
                    ("Шариковый", "Ball", "deodorant-ball", "Шариковый дезодорант", "Ball deodorant"),
                ],
            ),
            ("Парфюмированные лосьоны", "Scented Lotions", "scented-lotions", "Парфюмированные лосьоны", "Scented lotions"),
            ("Парфюмированные кремы", "Scented Creams", "scented-creams", "Парфюмированные кремы", "Scented creams"),
            ("Парфюмированные спреи для тела", "Body Sprays", "body-sprays", "Парфюмированные спреи для тела", "Body sprays"),
        ],
    ),
    (
        "Миниатюры и пробники",
        "Miniatures & Samples",
        "miniatures-samples",
        "Миниатюры и пробники",
        "Miniatures and samples",
        [
            ("Миниатюры", "Miniatures", "perfume-miniatures", "Миниатюры духов", "Perfume miniatures"),
            ("Пробники", "Samples", "perfume-samples", "Пробники духов", "Perfume samples"),
            ("Подарочные наборы миниатюр", "Gift Sets", "miniature-gift-sets", "Подарочные наборы миниатюр", "Miniature gift sets"),
        ],
    ),
    (
        "Подарочные наборы",
        "Gift Sets",
        "perfumery-gift-sets",
        "Подарочные наборы",
        "Perfumery gift sets",
        [
            ("Женские наборы", "Women's Sets", "womens-perfume-sets", "Женские парфюмерные наборы", "Women's perfume sets"),
            ("Мужские наборы", "Men's Sets", "mens-perfume-sets", "Мужские парфюмерные наборы", "Men's perfume sets"),
            ("Унисекс наборы", "Unisex Sets", "unisex-perfume-sets", "Унисекс парфюмерные наборы", "Unisex perfume sets"),
        ],
    ),
]

# Благовония: L2 с L3 и L4 подкатегориями
INCENSE_SUBCATEGORIES = [
    (
        "Аромасвечи",
        "Scented Candles",
        "scented-candles",
        "Аромасвечи",
        "Scented candles",
        [
            ("Соевые свечи", "Soy Candles", "soy-candles", "Соевые свечи", "Soy candles"),
            ("Восковые свечи", "Wax Candles", "wax-candles", "Восковые свечи", "Wax candles"),
            ("Пальмовые свечи", "Palm Wax Candles", "palm-wax-candles", "Пальмовые свечи", "Palm wax candles"),
            ("Кокосовые свечи", "Coconut Wax Candles", "coconut-wax-candles", "Кокосовые свечи", "Coconut wax candles"),
            ("Гелевые свечи", "Gel Candles", "gel-candles", "Гелевые свечи", "Gel candles"),
            ("Свечи в стакане", "Container Candles", "container-candles", "Свечи в стакане", "Container candles"),
        ],
    ),
    (
        "Ароматические палочки",
        "Incense Sticks",
        "incense-sticks",
        "Ароматические палочки",
        "Incense sticks",
        [
            (
                "Индийские благовония",
                "Indian Incense",
                "indian-incense",
                "Индийские благовония",
                "Indian incense",
                [
                    ("Безосновные", "Masala Incense", "masala-incense", "Безосновные масала", "Masala incense"),
                    ("На бамбуковой основе", "Bamboo Core Incense", "bamboo-core-incense", "На бамбуковой основе", "Bamboo core incense"),
                ],
            ),
            ("Японские благовония", "Japanese Incense", "japanese-incense", "Японские благовония", "Japanese incense"),
            ("Тибетские благовония", "Tibetan Incense", "tibetan-incense", "Тибетские благовония", "Tibetan incense"),
            ("Арабские благовония", "Arabic Incense", "arabic-incense", "Арабские благовония", "Arabic incense"),
            ("Натуральные палочки", "Natural Incense", "natural-incense", "Натуральные палочки", "Natural incense"),
        ],
    ),
    (
        "Аромаконусы",
        "Incense Cones",
        "incense-cones",
        "Аромаконусы",
        "Incense cones",
        [
            ("Обычные конусы", "Regular Cones", "regular-cones", "Обычные конусы", "Regular cones"),
            ("Конусы с обратным дымом", "Backflow Cones", "backflow-cones", "Конусы с обратным дымом", "Backflow cones"),
        ],
    ),
    (
        "Смолы и благовония сыпучие",
        "Resins & Loose Incense",
        "resins-loose-incense",
        "Смолы и благовония сыпучие",
        "Resins and loose incense",
        [
            ("Ладан", "Frankincense", "frankincense", "Ладан", "Frankincense"),
            ("Мирра", "Myrrh", "myrrh", "Мирра", "Myrrh"),
            ("Сандал", "Sandalwood", "sandalwood", "Сандал", "Sandalwood"),
            ("Уд (агаровое дерево)", "Oud", "oud", "Уд агаровое дерево", "Oud"),
            ("Копал", "Copal", "copal", "Копал", "Copal"),
        ],
    ),
    (
        "Эфирные масла",
        "Essential Oils",
        "essential-oils",
        "Эфирные масла",
        "Essential oils",
        [
            (
                "Одиночные масла",
                "Single Oils",
                "single-essential-oils",
                "Одиночные эфирные масла",
                "Single essential oils",
                [
                    ("Лавандовое", "Lavender", "lavender-oil", "Лавандовое масло", "Lavender oil"),
                    ("Мятное", "Peppermint", "peppermint-oil", "Мятное масло", "Peppermint oil"),
                    ("Эвкалиптовое", "Eucalyptus", "eucalyptus-oil", "Эвкалиптовое масло", "Eucalyptus oil"),
                    ("Розовое", "Rose", "rose-oil", "Розовое масло", "Rose oil"),
                    ("Чайное дерево", "Tea Tree", "tea-tree-oil", "Масло чайного дерева", "Tea tree oil"),
                ],
            ),
            (
                "Смеси масел",
                "Blended Oils",
                "blended-oils",
                "Смеси эфирных масел",
                "Blended essential oils",
                [
                    ("Для сна", "Sleep Blend", "sleep-blend", "Смесь для сна", "Sleep blend"),
                    ("Для энергии", "Energy Blend", "energy-blend", "Смесь для энергии", "Energy blend"),
                    ("Для релаксации", "Relaxation Blend", "relaxation-blend", "Смесь для релаксации", "Relaxation blend"),
                ],
            ),
            ("Синтетические ароматические масла", "Fragrance Oils", "fragrance-oils", "Синтетические ароматические масла", "Fragrance oils"),
        ],
    ),
    (
        "Аромадиффузоры",
        "Aroma Diffusers",
        "aroma-diffusers",
        "Аромадиффузоры",
        "Aroma diffusers",
        [
            ("Ультразвуковые диффузоры", "Ultrasonic Diffusers", "ultrasonic-diffusers", "Ультразвуковые диффузоры", "Ultrasonic diffusers"),
            ("Небулайзерные диффузоры", "Nebulizing Diffusers", "nebulizing-diffusers", "Небулайзерные диффузоры", "Nebulizing diffusers"),
            ("Тростниковые диффузоры", "Reed Diffusers", "reed-diffusers", "Тростниковые диффузоры", "Reed diffusers"),
            ("Электрические диффузоры", "Electric Diffusers", "electric-diffusers", "Электрические диффузоры", "Electric diffusers"),
            ("Аромалампы", "Aroma Lamps", "aroma-lamps", "Аромалампы", "Aroma lamps"),
        ],
    ),
    (
        "Ароматические саше и спреи",
        "Sachets & Sprays",
        "sachets-sprays",
        "Ароматические саше и спреи",
        "Sachets and sprays",
        [
            ("Саше для шкафа", "Wardrobe Sachets", "wardrobe-sachets", "Саше для шкафа", "Wardrobe sachets"),
            ("Саше для автомобиля", "Car Sachets", "car-sachets", "Саше для автомобиля", "Car sachets"),
            ("Аромаспреи для дома", "Home Sprays", "home-sprays", "Аромаспреи для дома", "Home sprays"),
        ],
    ),
    (
        "Аксессуары для благовоний",
        "Incense Accessories",
        "incense-accessories",
        "Аксессуары для благовоний",
        "Incense accessories",
        [
            (
                "Подставки для палочек",
                "Incense Holders",
                "incense-holders",
                "Подставки для палочек",
                "Incense holders",
                [
                    ("Лодочки", "Boat Holders", "boat-holders", "Лодочки для палочек", "Boat holders"),
                    ("Пепельницы", "Ash Catchers", "ash-catchers", "Пепельницы для благовоний", "Ash catchers"),
                    ("Каскадные подставки", "Backflow Holders", "backflow-holders", "Каскадные подставки", "Backflow holders"),
                ],
            ),
            (
                "Горелки для смол",
                "Resin Burners",
                "resin-burners",
                "Горелки для смол",
                "Resin burners",
                [
                    ("Электрические", "Electric", "electric-resin-burners", "Электрические горелки", "Electric resin burners"),
                    ("На углях", "Charcoal", "charcoal-resin-burners", "Горелки на углях", "Charcoal resin burners"),
                ],
            ),
            ("Уголь для благовоний", "Charcoal Discs", "charcoal-discs", "Уголь для благовоний", "Charcoal discs"),
        ],
    ),
]

# Головные уборы (headwear): 3–4 уровня. Префикс hw- для избежания конфликтов с acc-headwear.
HEADWEAR_SUBCATEGORIES = [
    (
        "Зимние головные уборы",
        "Winter Headwear",
        "hw-winter-headwear",
        "Зимние головные уборы",
        "Winter headwear",
        [
            (
                "Шапки",
                "Beanies & Winter Hats",
                "hw-beanies",
                "Шапки",
                "Beanies and winter hats",
                [
                    ("Вязаные шапки", "Knitted Beanies", "hw-knitted-beanies", "Вязаные шапки", "Knitted beanies"),
                    ("Флисовые шапки", "Fleece Hats", "hw-fleece-hats", "Флисовые шапки", "Fleece hats"),
                    ("Помпон-шапки", "Pom-Pom Hats", "hw-pom-pom-hats", "Помпон-шапки", "Pom-pom hats"),
                    ("Шапки-ушанки", "Ushanka Hats", "hw-ushanka-hats", "Шапки-ушанки", "Ushanka hats"),
                ],
            ),
            (
                "Шапки-шлемы",
                "Balaclavas",
                "hw-balaclavas",
                "Шапки-шлемы",
                "Balaclavas",
                [
                    ("Полная балаклава", "Full Balaclava", "hw-full-balaclava", "Полная балаклава", "Full balaclava"),
                    ("Открытая", "Open-Face", "hw-open-face-balaclava", "Открытая балаклава", "Open-face balaclava"),
                ],
            ),
            (
                "Меховые шапки",
                "Fur Hats",
                "hw-fur-hats",
                "Меховые шапки",
                "Fur hats",
                [
                    ("Из натурального меха", "Real Fur", "hw-real-fur-hats", "Из натурального меха", "Real fur hats"),
                    ("Из искусственного меха", "Faux Fur", "hw-faux-fur-hats", "Из искусственного меха", "Faux fur hats"),
                ],
            ),
        ],
    ),
    (
        "Летние головные уборы",
        "Summer Headwear",
        "hw-summer-headwear",
        "Летние головные уборы",
        "Summer headwear",
        [
            (
                "Панамы",
                "Bucket Hats",
                "hw-bucket-hats",
                "Панамы",
                "Bucket hats",
                [
                    ("Классические", "Classic", "hw-classic-bucket-hats", "Классические панамы", "Classic bucket hats"),
                    ("Детские", "Children's", "hw-childrens-bucket-hats", "Детские панамы", "Children's bucket hats"),
                ],
            ),
            (
                "Соломенные шляпы",
                "Straw Hats",
                "hw-straw-hats",
                "Соломенные шляпы",
                "Straw hats",
                [
                    ("Федора", "Fedora", "hw-straw-fedora", "Соломенная федора", "Straw fedora"),
                    ("Шляпа-борсалино", "Borsalino", "hw-borsalino", "Шляпа-борсалино", "Borsalino hat"),
                    ("Широкополые", "Wide-Brim", "hw-wide-brim-straw", "Широкополые соломенные шляпы", "Wide-brim straw hats"),
                ],
            ),
            ("Кепи и козырьки", "Visors", "hw-visors", "Кепи и козырьки", "Visors"),
            ("Повязки на голову", "Headbands", "hw-headbands", "Повязки на голову", "Headbands"),
        ],
    ),
    (
        "Кепки",
        "Caps",
        "hw-caps",
        "Кепки",
        "Caps",
        [
            (
                "Бейсболки",
                "Baseball Caps",
                "hw-baseball-caps",
                "Бейсболки",
                "Baseball caps",
                [
                    ("С прямым козырьком", "Flat Brim", "hw-flat-brim-caps", "С прямым козырьком", "Flat brim caps"),
                    ("С изогнутым козырьком", "Curved Brim", "hw-curved-brim-caps", "С изогнутым козырьком", "Curved brim caps"),
                ],
            ),
            ("Снэпбеки", "Snapbacks", "hw-snapbacks", "Снэпбеки", "Snapbacks"),
            ("Дальнобойщики", "Trucker Caps", "hw-trucker-caps", "Дальнобойщики", "Trucker caps"),
            ("Гольф-кепки", "Golf Caps", "hw-golf-caps", "Гольф-кепки", "Golf caps"),
            ("Пятипанельные", "Five-Panel Caps", "hw-five-panel-caps", "Пятипанельные кепки", "Five-panel caps"),
        ],
    ),
    (
        "Шляпы",
        "Hats",
        "hw-hats",
        "Шляпы",
        "Hats",
        [
            ("Федора", "Fedora", "hw-fedora", "Федора", "Fedora"),
            ("Трилби", "Trilby", "hw-trilby", "Трилби", "Trilby"),
            ("Котелок", "Bowler Hat", "hw-bowler", "Котелок", "Bowler hat"),
            ("Цилиндр", "Top Hat", "hw-top-hat", "Цилиндр", "Top hat"),
            ("Ковбойская шляпа", "Cowboy Hat", "hw-cowboy-hat", "Ковбойская шляпа", "Cowboy hat"),
            ("Клош", "Cloche", "hw-cloche", "Клош", "Cloche"),
        ],
    ),
    (
        "Береты",
        "Berets",
        "hw-berets",
        "Береты",
        "Berets",
        [
            ("Классические", "Classic", "hw-classic-berets", "Классические береты", "Classic berets"),
            ("Военные", "Military", "hw-military-berets", "Военные береты", "Military berets"),
        ],
    ),
    (
        "Тюрбаны и чалмы",
        "Turbans",
        "hw-turbans",
        "Тюрбаны и чалмы",
        "Turbans",
        [
            ("Тюрбан", "Turban", "hw-turban", "Тюрбан", "Turban"),
            ("Чалма", "Wrapped Turban", "hw-wrapped-turban", "Чалма", "Wrapped turban"),
        ],
    ),
    (
        "Спортивные головные уборы",
        "Sport Headwear",
        "hw-sport-headwear",
        "Спортивные головные уборы",
        "Sport headwear",
        [
            ("Беговые шапки", "Running Caps", "hw-running-caps", "Беговые шапки", "Running caps"),
            ("Велосипедные кепки", "Cycling Caps", "hw-cycling-caps", "Велосипедные кепки", "Cycling caps"),
            ("Спортивные повязки", "Sport Headbands", "hw-sport-headbands", "Спортивные повязки", "Sport headbands"),
        ],
    ),
    (
        "Детские головные уборы",
        "Children's Headwear",
        "hw-children-headwear",
        "Детские головные уборы",
        "Children's headwear",
        [
            ("Детские шапки", "Children's Beanies", "hw-childrens-beanies", "Детские шапки", "Children's beanies"),
            ("Детские кепки", "Children's Caps", "hw-childrens-caps", "Детские кепки", "Children's caps"),
            ("Детские панамы", "Children's Bucket Hats", "hw-childrens-panamas", "Детские панамы", "Children's bucket hats"),
            ("Шапки для новорождённых", "Newborn Hats", "hw-newborn-hats", "Шапки для новорождённых", "Newborn hats"),
        ],
    ),
]

# Нижнее бельё (underwear): 3–4 уровня. Префикс uw- для уникальности.
UNDERWEAR_SUBCATEGORIES = [
    (
        "Женское нижнее бельё",
        "Women's Underwear",
        "uw-womens-underwear",
        "Женское нижнее бельё",
        "Women's underwear",
        [
            (
                "Трусы",
                "Panties",
                "uw-panties",
                "Трусы",
                "Panties",
                [
                    ("Слипы", "Briefs", "uw-briefs", "Слипы", "Briefs"),
                    ("Бикини", "Bikini", "uw-bikini", "Бикини", "Bikini"),
                    ("Бразилиана", "Brazilians", "uw-brazilians", "Бразилиана", "Brazilians"),
                    ("Танга", "Thongs", "uw-thongs", "Танга", "Thongs"),
                    ("Стринги", "G-Strings", "uw-g-strings", "Стринги", "G-strings"),
                    ("Хипстеры", "Hipsters", "uw-hipsters", "Хипстеры", "Hipsters"),
                    ("Шорты", "Boy Shorts", "uw-boy-shorts", "Шорты", "Boy shorts"),
                ],
            ),
            (
                "Бюстгальтеры",
                "Bras",
                "uw-bras",
                "Бюстгальтеры",
                "Bras",
                [
                    ("С косточками", "Underwired Bras", "uw-underwired-bras", "Бюстгальтеры с косточками", "Underwired bras"),
                    ("Без косточек", "Non-Wired Bras", "uw-non-wired-bras", "Бюстгальтеры без косточек", "Non-wired bras"),
                    ("Спортивные бюстгальтеры", "Sports Bras", "uw-sports-bras", "Спортивные бюстгальтеры", "Sports bras"),
                    ("Бралетты", "Bralettes", "uw-bralettes", "Бралетты", "Bralettes"),
                    ("Бюстгальтеры для кормления", "Nursing Bras", "uw-nursing-bras", "Бюстгальтеры для кормления", "Nursing bras"),
                    ("Корсеты", "Corsets", "uw-corsets", "Корсеты", "Corsets"),
                    ("Бюстье", "Bustiers", "uw-bustiers", "Бюстье", "Bustiers"),
                ],
            ),
            (
                "Комплекты нижнего белья",
                "Lingerie Sets",
                "uw-lingerie-sets",
                "Комплекты нижнего белья",
                "Lingerie sets",
                [
                    ("Классические комплекты", "Classic Sets", "uw-classic-lingerie-sets", "Классические комплекты", "Classic lingerie sets"),
                    ("Сексуальное бельё", "Sexy Lingerie Sets", "uw-sexy-lingerie-sets", "Сексуальное бельё", "Sexy lingerie sets"),
                ],
            ),
            (
                "Корректирующее бельё",
                "Shapewear",
                "uw-shapewear",
                "Корректирующее бельё",
                "Shapewear",
                [
                    ("Корректирующие трусы", "Shaping Panties", "uw-shaping-panties", "Корректирующие трусы", "Shaping panties"),
                    ("Корсеты-боди", "Shaping Bodysuits", "uw-shaping-bodysuits", "Корсеты-боди", "Shaping bodysuits"),
                    ("Корректирующие шорты", "Shaping Shorts", "uw-shaping-shorts", "Корректирующие шорты", "Shaping shorts"),
                    ("Утягивающие майки", "Shaping Tops", "uw-shaping-tops", "Утягивающие майки", "Shaping tops"),
                ],
            ),
            (
                "Пояса и подвязки",
                "Garters & Suspenders",
                "uw-garters-suspenders",
                "Пояса и подвязки",
                "Garters and suspenders",
                [
                    ("Пояс для чулок", "Garter Belts", "uw-garter-belts", "Пояс для чулок", "Garter belts"),
                    ("Чулки", "Stockings", "uw-garter-stockings", "Чулки для пояса", "Stockings for garter"),
                ],
            ),
        ],
    ),
    (
        "Мужское нижнее бельё",
        "Men's Underwear",
        "uw-mens-underwear",
        "Мужское нижнее бельё",
        "Men's underwear",
        [
            (
                "Трусы-боксеры",
                "Boxers",
                "uw-boxers",
                "Трусы-боксеры",
                "Boxers",
                [
                    ("Свободные", "Loose Boxers", "uw-loose-boxers", "Свободные боксеры", "Loose boxers"),
                    ("Облегающие", "Fitted Boxers", "uw-fitted-boxers", "Облегающие боксеры", "Fitted boxers"),
                ],
            ),
            (
                "Брифы",
                "Briefs",
                "uw-mens-briefs",
                "Брифы",
                "Briefs",
                [
                    ("Классические", "Classic Briefs", "uw-classic-briefs", "Классические брифы", "Classic briefs"),
                    ("Слипы", "Slips", "uw-mens-slips", "Слипы", "Slips"),
                ],
            ),
            ("Боксер-брифы", "Boxer Briefs", "uw-boxer-briefs", "Боксер-брифы", "Boxer briefs"),
            ("Тонги", "Thongs", "uw-mens-thongs", "Мужские тонги", "Men's thongs"),
            ("Спортивное бельё", "Athletic Underwear", "uw-athletic-underwear", "Спортивное бельё", "Athletic underwear"),
        ],
    ),
    (
        "Детское нижнее бельё",
        "Children's Underwear",
        "uw-children-underwear",
        "Детское нижнее бельё",
        "Children's underwear",
        [
            (
                "Для девочек",
                "Girls",
                "uw-girls-underwear",
                "Нижнее бельё для девочек",
                "Girls underwear",
                [
                    ("Трусы", "Panties", "uw-girls-panties", "Детские трусы", "Girls panties"),
                    ("Майки", "Undershirts", "uw-girls-undershirts", "Детские майки", "Girls undershirts"),
                ],
            ),
            (
                "Для мальчиков",
                "Boys",
                "uw-boys-underwear",
                "Нижнее бельё для мальчиков",
                "Boys underwear",
                [
                    ("Трусы", "Briefs & Boxers", "uw-boys-briefs", "Детские трусы", "Boys briefs and boxers"),
                    ("Майки", "Undershirts", "uw-boys-undershirts", "Детские майки", "Boys undershirts"),
                ],
            ),
        ],
    ),
    (
        "Термобельё",
        "Thermal Underwear",
        "uw-thermal-underwear",
        "Термобельё",
        "Thermal underwear",
        [
            ("Термофутболки", "Thermal Tops", "uw-thermal-tops", "Термофутболки", "Thermal tops"),
            ("Термолеггинсы", "Thermal Leggings", "uw-thermal-leggings", "Термолеггинсы", "Thermal leggings"),
            (
                "Комплекты термобелья",
                "Thermal Sets",
                "uw-thermal-sets",
                "Комплекты термобелья",
                "Thermal sets",
                [
                    ("Тонкие", "Light", "uw-thermal-light", "Тонкое термобельё", "Light thermal"),
                    ("Средние", "Medium", "uw-thermal-medium", "Среднее термобельё", "Medium thermal"),
                    ("Тёплые", "Heavy", "uw-thermal-heavy", "Тёплое термобельё", "Heavy thermal"),
                ],
            ),
        ],
    ),
    (
        "Ночное бельё",
        "Sleepwear",
        "uw-sleepwear",
        "Ночное бельё",
        "Sleepwear",
        [
            (
                "Пижамы",
                "Pajamas",
                "uw-pajamas",
                "Пижамы",
                "Pajamas",
                [
                    ("Женские", "Women's", "uw-womens-pajamas", "Женские пижамы", "Women's pajamas"),
                    ("Мужские", "Men's", "uw-mens-pajamas", "Мужские пижамы", "Men's pajamas"),
                    ("Детские", "Children's", "uw-childrens-pajamas", "Детские пижамы", "Children's pajamas"),
                ],
            ),
            ("Ночные рубашки", "Nightgowns", "uw-nightgowns", "Ночные рубашки", "Nightgowns"),
            (
                "Халаты",
                "Robes",
                "uw-robes",
                "Халаты",
                "Robes",
                [
                    ("Банные", "Bath Robes", "uw-bath-robes", "Банные халаты", "Bath robes"),
                    ("Шёлковые", "Silk Robes", "uw-silk-robes", "Шёлковые халаты", "Silk robes"),
                ],
            ),
            ("Сорочки", "Slips", "uw-slips", "Сорочки", "Slips"),
        ],
    ),
    (
        "Носки и колготки",
        "Socks & Hosiery",
        "uw-socks-hosiery",
        "Носки и колготки",
        "Socks and hosiery",
        [
            (
                "Носки",
                "Socks",
                "uw-socks",
                "Носки",
                "Socks",
                [
                    ("Классические", "Classic", "uw-classic-socks", "Классические носки", "Classic socks"),
                    ("Спортивные", "Sport", "uw-sport-socks", "Спортивные носки", "Sport socks"),
                    ("Следки", "No-Show", "uw-no-show-socks", "Следки", "No-show socks"),
                    ("Гольфы", "Knee-High Socks", "uw-knee-high-socks", "Гольфы", "Knee-high socks"),
                ],
            ),
            (
                "Колготки",
                "Tights",
                "uw-tights",
                "Колготки",
                "Tights",
                [
                    ("Капроновые", "Sheer", "uw-sheer-tights", "Капроновые колготки", "Sheer tights"),
                    ("Плотные", "Opaque", "uw-opaque-tights", "Плотные колготки", "Opaque tights"),
                    ("Матовые", "Matte", "uw-matte-tights", "Матовые колготки", "Matte tights"),
                    ("Компрессионные", "Compression", "uw-compression-tights", "Компрессионные колготки", "Compression tights"),
                ],
            ),
            (
                "Чулки",
                "Stockings",
                "uw-stockings",
                "Чулки",
                "Stockings",
                [
                    ("Самоудерживающиеся", "Hold-Ups", "uw-hold-ups", "Самоудерживающиеся чулки", "Hold-up stockings"),
                    ("На поясе", "Suspender Stockings", "uw-suspender-stockings", "Чулки на поясе", "Suspender stockings"),
                ],
            ),
        ],
    ),
]

# E-commerce атрибуты: [(slug, name_ru, name_en, sort_order, [category_slugs]), ...]
# Один slug может быть привязан к нескольким категориям (например, size для jewelry, clothing, shoes)
ECOMMERCE_ATTRIBUTES = [
    # Jewelry / Украшения
    ("material", "Материал", "Material", 1, ["jewelry", "shoes", "furniture", "accessories", "auto-parts", "tableware", "islamic-clothing", "sports", "medical-equipment", "headwear", "underwear"]),
    ("metal", "Металл", "Metal", 2, ["jewelry"]),
    ("gemstone", "Камень", "Gemstone", 3, ["jewelry"]),
    ("weight", "Вес", "Weight", 4, ["jewelry", "furniture", "auto-parts", "tableware", "electronics", "sports"]),
    ("length", "Длина", "Length", 5, ["jewelry", "furniture", "auto-parts", "tableware", "accessories"]),
    ("size", "Размер", "Size", 6, ["jewelry", "clothing", "shoes", "islamic-clothing", "sports", "medical-equipment", "accessories", "headwear", "underwear"]),
    ("plating", "Покрытие", "Plating", 7, ["jewelry"]),
    ("stone-cut", "Огранка камня", "Stone Cut", 8, ["jewelry"]),
    # Clothing / Одежда
    ("fabric", "Ткань", "Fabric", 10, ["clothing", "islamic-clothing"]),
    ("fit", "Посадка", "Fit", 11, ["clothing", "islamic-clothing"]),
    ("sleeve-length", "Длина рукава", "Sleeve Length", 12, ["clothing"]),
    ("pattern", "Узор", "Pattern", 13, ["clothing", "islamic-clothing"]),
    ("season", "Сезон", "Season", 14, ["clothing", "shoes", "islamic-clothing", "sports", "accessories", "perfumery", "headwear", "underwear"]),
    ("gender", "Пол", "Gender", 15, ["clothing", "shoes", "islamic-clothing", "underwear"]),
    ("color", "Цвет", "Color", 16, ["clothing", "shoes", "jewelry", "accessories", "furniture", "tableware", "islamic-clothing", "electronics", "sports", "headwear", "underwear"]),
    # Shoes / Обувь
    ("sole-material", "Материал подошвы", "Sole Material", 20, ["shoes"]),
    ("heel-height", "Высота каблука", "Heel Height", 21, ["shoes"]),
    ("closure-type", "Тип застёжки", "Closure Type", 22, ["shoes", "accessories", "underwear"]),
    ("shoe-width", "Ширина обуви", "Shoe Width", 23, ["shoes"]),
    ("insole-type", "Тип стельки", "Insole Type", 24, ["shoes"]),
    # Electronics / Электроника
    ("cpu", "Процессор", "CPU", 30, ["electronics"]),
    ("gpu", "Видеокарта", "GPU", 31, ["electronics"]),
    ("ram", "Оперативная память", "RAM", 32, ["electronics"]),
    ("storage", "Накопитель", "Storage", 33, ["electronics"]),
    ("screen-size", "Размер экрана", "Screen Size", 34, ["electronics"]),
    ("battery-capacity", "Ёмкость батареи", "Battery Capacity", 35, ["electronics"]),
    ("operating-system", "Операционная система", "Operating System", 36, ["electronics"]),
    ("connectivity", "Подключения", "Connectivity", 37, ["electronics"]),
    ("camera", "Камера", "Camera", 38, ["electronics"]),
    ("sim-type", "Тип SIM", "SIM Type", 39, ["electronics"]),
    ("storage-type", "Тип накопителя", "Storage Type", 40, ["electronics"]),
    ("ports", "Порты", "Ports", 41, ["electronics"]),
    ("warranty", "Гарантия", "Warranty", 42, ["electronics", "auto-parts", "sports", "medical-equipment"]),
    ("screen-resolution", "Разрешение экрана", "Screen Resolution", 43, ["electronics"]),  # HD, Full HD, 2K, 4K
    ("screen-type", "Тип экрана", "Screen Type", 44, ["electronics"]),  # IPS, AMOLED, OLED, TN
    ("refresh-rate", "Частота обновления", "Refresh Rate", 45, ["electronics"]),  # Hz
    ("power-w", "Мощность", "Power", 46, ["electronics", "sports"]),  # W
    ("wireless", "Беспроводные технологии", "Wireless", 47, ["electronics"]),  # Wi-Fi, Bluetooth, NFC
    ("cpu-cores", "Количество ядер", "CPU Cores", 48, ["electronics"]),
    ("cpu-clock-speed", "Частота процессора", "Clock Speed", 49, ["electronics"]),  # GHz
    ("compatibility", "Совместимость", "Compatibility", 50, ["electronics"]),  # Platform, Region
    # Furniture / Мебель
    ("width", "Ширина", "Width", 50, ["furniture", "accessories", "auto-parts", "tableware", "electronics", "sports"]),
    ("height", "Высота", "Height", 51, ["furniture", "accessories", "tableware", "electronics", "sports"]),
    ("depth", "Глубина", "Depth", 52, ["furniture", "accessories", "tableware", "electronics", "sports"]),
    ("weight-capacity", "Максимальная нагрузка", "Weight Capacity", 53, ["furniture", "sports"]),
    ("assembly-required", "Сборка", "Assembly", 54, ["furniture"]),  # Требуется сборка / Собранный
    ("style", "Стиль", "Style", 55, ["furniture", "islamic-clothing", "accessories", "headwear", "underwear"]),
    ("room-type", "Тип помещения", "Room Type", 56, ["furniture"]),
    # Beauty / Косметика (perfumery)
    ("skin-type", "Тип кожи", "Skin Type", 60, ["perfumery"]),
    ("volume", "Объём", "Volume", 61, ["perfumery", "incense"]),
    ("ingredients", "Состав", "Ingredients", 62, ["perfumery"]),
    ("effect", "Эффект", "Effect", 63, ["perfumery"]),
    ("spf", "Защита SPF", "SPF", 64, ["perfumery"]),
    ("scent-type", "Тип аромата", "Scent Type", 66, ["perfumery"]),
    # Perfumery / Парфюмерия (расширенные атрибуты)
    ("concentration", "Концентрация", "Concentration", 84, ["perfumery"]),  # Parfum, EDP, EDT, EDC, Body Mist
    ("fragrance-family", "Семейство аромата", "Fragrance Family", 85, ["perfumery"]),  # Floral, Woody, Oriental, etc.
    ("top-notes", "Верхние ноты", "Top Notes", 86, ["perfumery"]),
    ("heart-notes", "Средние ноты", "Heart Notes", 87, ["perfumery"]),
    ("base-notes", "Базовые ноты", "Base Notes", 88, ["perfumery"]),
    ("longevity", "Стойкость", "Longevity", 89, ["perfumery"]),  # Weak, Moderate, Strong
    ("sillage", "Шлейф", "Sillage", 90, ["perfumery"]),  # Light, Moderate, Heavy
    ("bottle-type", "Тип флакона", "Bottle Type", 91, ["perfumery"]),  # Spray, Roll-On, Splash
    # Watches / Часы (accessories)
    ("movement", "Механизм", "Movement", 70, ["accessories", "jewelry"]),
    ("case-material", "Материал корпуса", "Case Material", 71, ["accessories", "jewelry"]),
    ("strap-material", "Материал ремешка", "Strap Material", 72, ["accessories"]),
    ("case-diameter", "Диаметр корпуса", "Case Diameter", 73, ["accessories"]),
    ("water-resistance", "Водозащита", "Water Resistance", 74, ["accessories"]),
    ("glass-type", "Тип стекла", "Glass Type", 75, ["accessories"]),
    # Bags / Сумки (accessories)
    ("strap-type", "Тип ремня", "Strap Type", 80, ["accessories"]),
    ("capacity", "Вместимость", "Capacity", 81, ["accessories"]),
    ("metal-hallmark", "Проба металла", "Metal Hallmark", 82, ["accessories", "jewelry"]),  # 585, 750, 925
    ("gemstones", "Вставки", "Gemstones", 83, ["accessories", "jewelry"]),  # Diamond, Ruby, Sapphire, etc.
    ("set-contents", "Комплектация", "Set Contents", 84, ["accessories"]),  # Single Item, Set
    # Supplements & Medicines / БАДы и медикаменты
    ("active-ingredient", "Активное вещество", "Active Ingredient", 90, ["medicines", "supplements"]),
    ("dosage", "Дозировка", "Dosage", 91, ["medicines", "supplements"]),
    ("dosage-unit", "Единица дозировки", "Dosage Unit", 92, ["medicines", "supplements"]),  # mg, g, IU
    ("form", "Форма выпуска", "Form", 93, ["medicines", "supplements"]),  # Tablets, Capsules, Powder, Liquid, Syrup, Gummies
    ("package-quantity", "Количество в упаковке", "Package Quantity", 94, ["medicines", "supplements"]),  # Tablets count, Capsule count, Volume
    ("purpose", "Назначение", "Purpose", 95, ["medicines", "supplements"]),  # Immunity, Energy, Sleep, Digestion, Heart Health
    ("age-group", "Возраст", "Age Group", 96, ["medicines", "supplements", "headwear", "underwear"]),  # Adults, Kids, Seniors
    ("dietary-type", "Тип диеты", "Dietary Type", 97, ["medicines", "supplements"]),  # Vegan, Vegetarian, Gluten Free, Sugar Free
    ("country-of-origin", "Страна производства", "Country of Origin", 98, ["medicines", "supplements", "perfumery", "incense"]),
    ("expiration-date", "Срок годности", "Expiration Date", 99, ["medicines", "supplements", "perfumery"]),
    ("storage-conditions", "Условия хранения", "Storage Conditions", 100, ["medicines", "supplements"]),
    # Islamic Clothing / Исламская одежда
    ("cut-type", "Тип покроя", "Cut Type", 85, ["islamic-clothing"]),  # Loose, Fitted
    ("embroidery", "Наличие вышивки", "Embroidery", 86, ["islamic-clothing"]),
    ("target-audience", "Целевая аудитория", "Target Audience", 87, ["islamic-clothing", "sports"]),  # Women, Men, Children
    ("clothing-purpose", "Назначение", "Purpose", 88, ["islamic-clothing"]),  # Casual, Prayer, Festive
    ("garment-length", "Длина изделия", "Garment Length", 89, ["islamic-clothing"]),  # cm
    # Sports / Спорттовары
    ("sport-type", "Вид спорта", "Sport Type", 120, ["sports"]),
    ("skill-level", "Уровень подготовки", "Skill Level", 121, ["sports"]),  # Beginner, Amateur, Professional
    ("usage-type", "Тип использования", "Usage Type", 122, ["sports"]),  # Indoor, Outdoor
    ("power-source", "Питание", "Power Source", 123, ["sports"]),  # No Power, Electric, Battery
    ("package-contents", "Комплектация", "Package Contents", 124, ["sports", "medical-equipment"]),
    # Medical Equipment / Медтехника
    ("device-type", "Тип устройства", "Device Type", 130, ["medical-equipment"]),
    ("medical-purpose", "Назначение", "Purpose", 131, ["medical-equipment"]),  # Diagnostics, Treatment, Rehabilitation, Prevention
    ("medical-user", "Пользователь", "User", 132, ["medical-equipment"]),  # Adults, Children, Elderly
    ("medical-usage-type", "Тип использования", "Usage Type", 133, ["medical-equipment"]),  # Home Use, Clinical Use
    ("medical-power-source", "Питание", "Power Source", 134, ["medical-equipment"]),  # AC, Rechargeable, Batteries
    ("medical-wireless", "Беспроводное подключение", "Wireless", 135, ["medical-equipment"]),  # Bluetooth, Wi-Fi
    ("app-compatible", "Приложение", "App Compatible", 136, ["medical-equipment"]),
    ("measurement-memory", "Память", "Memory", 137, ["medical-equipment"]),  # measurement count
    ("cuff-size", "Манжета", "Cuff Size", 138, ["medical-equipment"]),  # cm for tonometers
    ("measurement-range", "Диапазон измерений", "Measurement Range", 139, ["medical-equipment"]),
    ("accuracy", "Точность", "Accuracy", 140, ["medical-equipment"]),
    ("compression-class", "Степень компрессии", "Compression Class", 141, ["medical-equipment", "underwear"]),  # Class 1, 2, 3
    ("certification", "Сертификация", "Certification", 142, ["medical-equipment"]),  # CE, FDA, GOST
    # Tableware / Посуда
    ("capacity-ml", "Объём", "Capacity", 100, ["tableware"]),  # ml, L, Cups
    ("dishwasher-safe", "Можно в посудомойку", "Dishwasher Safe", 101, ["tableware"]),
    ("coating", "Покрытие", "Coating", 102, ["tableware"]),  # Non-stick, Ceramic, Enamel
    ("heat-resistance", "Термостойкость", "Heat Resistance", 103, ["tableware"]),
    ("microwave-safe", "Можно в микроволновке", "Microwave Safe", 104, ["tableware"]),
    ("oven-safe", "Можно в духовке", "Oven Safe", 105, ["tableware"]),
    ("induction-compatible", "Подходит для индукции", "Induction Compatible", 106, ["tableware"]),
    ("set-size", "Количество предметов", "Set Size", 107, ["tableware"]),
    ("usage", "Назначение", "Usage", 108, ["tableware"]),  # Cooking, Serving, Storage
    # Auto Parts / Автозапчасти
    ("vehicle-brand", "Марка автомобиля", "Vehicle Brand", 110, ["auto-parts"]),
    ("vehicle-model", "Модель", "Vehicle Model", 111, ["auto-parts"]),
    ("vehicle-year", "Год выпуска", "Vehicle Year", 112, ["auto-parts"]),
    ("engine-type", "Тип двигателя", "Engine Type", 113, ["auto-parts"]),
    ("part-number", "Номер детали", "Part Number", 114, ["auto-parts"]),
    ("oem-number", "OEM номер", "OEM Number", 115, ["auto-parts"]),
    ("replacement-part", "Аналог", "Replacement Part", 116, ["auto-parts"]),
    ("diameter", "Диаметр", "Diameter", 117, ["auto-parts", "tableware"]),
    ("position", "Расположение", "Position", 118, ["auto-parts"]),  # Front, Rear, Left, Right
    ("condition", "Состояние", "Condition", 119, ["auto-parts"]),  # New, Used
    # Incense / Благовония
    ("incense-product-type", "Тип изделия", "Product Type", 150, ["incense"]),
    ("incense-scent", "Аромат", "Scent", 151, ["incense"]),  # Floral, Woody, Oriental, Citrus, Mint, Musky, Spicy
    ("incense-composition", "Состав", "Composition", 152, ["incense"]),  # Natural, Synthetic, Mixed
    ("pack-quantity", "Количество в упаковке", "Pack Quantity", 153, ["incense"]),  # Sticks count, Resin weight g
    ("burn-time", "Время горения", "Burn Time", 154, ["incense"]),  # Candles hours, Sticks minutes
    ("incense-purpose", "Назначение", "Purpose", 155, ["incense"]),  # Meditation, Relaxation, Air Purification, Religious
    ("incense-safety", "Безопасность", "Safety", 156, ["incense"]),  # Non-Toxic, Hypoallergenic
    # Headwear / Головные уборы
    ("lining", "Наличие подкладки", "Lining", 160, ["headwear"]),  # Lined / Unlined
    ("adjustable", "Регулировка", "Adjustable", 161, ["headwear"]),  # Adjustable / Fixed Size
    ("care-instructions", "Уход", "Care Instructions", 162, ["headwear", "underwear"]),  # Machine Washable / Hand Wash Only
    # Underwear / Нижнее бельё
    ("hosiery-density", "Степень плотности", "Density", 163, ["underwear"]),  # Den 20/40/60/80/100+ для колготок
    ("support-level", "Степень поддержки", "Support Level", 164, ["underwear"]),  # Light / Medium / High для бюстгальтеров
    # Services / Услуги
    ("service-type", "Тип услуги", "Service Type", 170, ["uslugi"]),  # Installation, Repair, Replacement, Maintenance, Removal
    ("premises-type", "Тип помещения", "Premises Type", 171, ["uslugi"]),  # Apartment, Private House, Office, Commercial, Dacha
    ("area-sqm", "Площадь", "Area", 172, ["uslugi"]),  # м²
    ("floor", "Этаж", "Floor", 173, ["uslugi"]),
    ("urgency", "Срочность", "Urgency", 174, ["uslugi"]),  # Standard, Urgent, Weekend
    ("work-warranty", "Гарантия на работу", "Work Warranty", 175, ["uslugi"]),  # months
    ("materials-provider", "Материалы", "Materials", 176, ["uslugi"]),  # Customer Provides / Contractor Provides
    ("master-visit", "Выезд мастера", "Master Visit", 177, ["uslugi"]),  # Free Measurement / Paid Visit
    ("payment-method", "Форма оплаты", "Payment Method", 178, ["uslugi"]),  # Cash, Bank Transfer, By Contract
    ("rooms-count", "Количество комнат", "Number of Rooms", 179, ["uslugi"]),
    ("master-experience", "Опыт мастера", "Master's Experience", 180, ["uslugi"]),  # years
    ("rating", "Рейтинг", "Rating", 181, ["uslugi"]),
]

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
    "jewelry": [
        ("Cartier", "Французский ювелирный дом класса люкс.", "French luxury jewelry house.", "https://www.cartier.com"),
        ("Tiffany & Co.", "Американский бренд ювелирных изделий.", "American luxury jewelry brand.", "https://www.tiffany.com"),
        ("Bvlgari", "Итальянский ювелирный дом и часы.", "Italian jewelry and watch house.", "https://www.bulgari.com"),
        ("Pandora", "Датский бренд украшений и браслетов.", "Danish jewelry and charm brand.", "https://www.pandora.net"),
        ("Swarovski", "Австрийский бренд кристаллов и украшений.", "Austrian crystal and jewelry brand.", "https://www.swarovski.com"),
        ("Chopard", "Швейцарский ювелирный и часовой дом.", "Swiss jewelry and watch maison.", "https://www.chopard.com"),
        ("Van Cleef & Arpels", "Французский дом высокой ювелирии.", "French high jewelry maison.", "https://www.vancleefarpels.com"),
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
