"""Создает тестовый набор турецких и мировых брендов и базовых товаров для каждой витрины."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import transaction

from apps.catalog.models import (
    Brand,
    BrandTranslation,
    Category,
    Product,
    ClothingProduct,
    ShoeProduct,
    ElectronicsProduct,
    FurnitureProduct,
)


class Command(BaseCommand):
    help = "Создает турецкие и мировые бренды и примерные товары для тестовых витрин"

    PRODUCT_TYPE_LABELS = {
        "medicines": "pharmaceutical",
        "clothing": "fashion",
        "shoes": "footwear",
        "electronics": "electronics",
        "tableware": "tableware",
        "furniture": "furniture",
        "medical-equipment": "medical equipment",
    }

    TURKISH_BRANDS = {
        "medicines": [
            ("Abdi İbrahim", "Ведущий фармпроизводитель Турции.", "https://www.abdiibrahim.com.tr"),
            ("Deva Holding", "Фармацевтическая группа с широкой линейкой препаратов.", "https://www.deva.com.tr"),
            ("Nobel İlaç", "Производитель препаратов для госпитального сегмента и аптек.", "https://www.nobelilac.com.tr"),
            ("Santa Farma", "Турецкая фармкомпания с историей более 75 лет.", "https://www.santafarma.com.tr"),
            ("Bilim İlaç", "Одна из крупнейших фармацевтических компаний Турции.", "https://www.bilim.com.tr"),
            ("Atabay İlaç", "Локальный производитель API и готовых лекарственных форм.", "https://www.atabay.com"),
            ("İ.E. Ulagay", "Старейшая фармкомпания Турции, основана в 1903 году.", "https://www.ieulagay.com.tr"),
            ("Centurion Pharma", "Компания-экспортер лекарств и медпродукции.", "https://www.centurion.com.tr"),
            ("Sanovel", "Фармацевтический холдинг с широкой линейкой препаратов.", "https://www.sanovel.com.tr"),
            ("Drogsan", "Производитель лекарственных средств и БАД.", "https://www.drogsan.com.tr"),
            ("İlko İlaç", "Фармацевтическая компания с широким портфелем.", "https://www.ilko.com.tr"),
        ],
        "clothing": [
            ("LC Waikiki", "Массовый fashion-ретейлер из Стамбула.", "https://www.lcwaikiki.com"),
            ("Mavi", "Деним и casual одежда турецкого происхождения.", "https://www.mavi.com"),
            ("Koton", "Сеть магазинов модной одежды.", "https://www.koton.com"),
            ("DeFacto", "Pop-up fashion бренд для всей семьи.", "https://www.defacto.com.tr"),
            ("Vakko", "Премиальный дом моды из Турции.", "https://www.vakko.com"),
            ("Beymen", "Люксовый fashion-ретейлер и дом моды.", "https://www.beymen.com"),
            ("İpekyol", "Женская одежда и аксессуары.", "https://www.ipekyol.com.tr"),
            ("Kiğılı", "Мужская классическая одежда.", "https://www.kigili.com"),
            ("Damat Tween", "Мужские костюмы и smart casual.", "https://www.damattween.com"),
            ("Penti", "Нижнее белье и домашняя одежда.", "https://www.penti.com"),
            ("Colin's", "Городской casual бренд.", "https://www.colins.com.tr"),
            ("Twist", "Современная женская одежда.", "https://www.twist.com.tr"),
            ("Sarar", "Классическая одежда и костюмы.", "https://www.sarar.com"),
            ("Modanisa", "Онлайн-бренд модной одежды.", "https://www.modanisa.com"),
        ],
        "shoes": [
            ("Hotiç", "Сеть премиальной обуви и аксессуаров.", "https://www.hotic.com.tr"),
            ("FLO", "Крупнейший обувной ретейлер Турции.", "https://www.flo.com.tr"),
            ("Greyder", "Производитель повседневной обуви.", "https://www.greyder.com"),
            ("Polaris", "Обувной бренд сети FLO.", "https://www.polarisshoes.com"),
            ("İnci", "Исторический бренд кожаной обуви.", "https://www.inci.com.tr"),
            ("Derimod", "Кожаная обувь и аксессуары.", "https://www.derimod.com.tr"),
            ("Lescon", "Спортивная обувь и экипировка.", "https://www.lescon.com.tr"),
            ("Hammer Jack", "Обувь повседневного стиля.", "https://www.hammerjack.com.tr"),
            ("Kemal Tanca", "Классическая и повседневная обувь.", "https://www.kemaltanca.com.tr"),
            ("Matraş", "Обувь и аксессуары из кожи.", "https://www.matras.com.tr"),
            ("Divarese", "Городская обувь и аксессуары.", "https://www.divarese.com.tr"),
        ],
        "electronics": [
            ("Vestel", "Крупнейший производитель электроники и ТВ в Турции.", "https://www.vestel.com.tr"),
            ("Arçelik", "Производитель техники и электроники.", "https://www.arcelikglobal.com"),
            ("Beko", "Международный бренд бытовой техники (группа Arçelik).", "https://www.beko.com.tr"),
            ("Casper", "Турецкий бренд ноутбуков и смартфонов.", "https://www.casper.com.tr"),
            ("Reeder", "Производитель смартфонов и планшетов.", "https://www.reeder.com.tr"),
            ("General Mobile", "Смартфоны программы Android One.", "https://www.generalmobile.com.tr"),
            ("Profilo", "Бытовая техника для дома.", "https://www.profilo.com.tr"),
            ("Sunny", "Бытовая электроника и ТВ.", "https://www.sunny.com.tr"),
            ("Altus", "Бытовая техника для дома.", "https://www.altus.com.tr"),
            ("Regal", "Техника и электроника для дома.", "https://www.regal.com.tr"),
            ("Awox", "Электроника и товары для дома.", "https://www.awox.com.tr"),
        ],
        "tableware": [
            ("Karaca", "Посуда и товары для дома из Турции.", "https://www.karaca.com"),
            ("Paşabahçe", "Стеклянная посуда и бокалы.", "https://www.pasabahce.com"),
            ("Kütahya Porselen", "Фарфор и сервизы.", "https://www.kutahyaporselen.com.tr"),
            ("Güral Porselen", "Фарфоровая посуда.", "https://www.guralporselen.com.tr"),
            ("Porland", "Профессиональная и домашняя посуда.", "https://www.porland.com.tr"),
            ("Hisar", "Столовые приборы и посуда.", "https://www.hisar.com.tr"),
            ("Emsan", "Посуда и кухонные аксессуары.", "https://www.emsan.com.tr"),
            ("Tantitoni", "Посуда и кухонные гаджеты в ярком стиле.", "https://www.tantitoni.com"),
            ("Korkmaz", "Посуда и кухонные аксессуары.", "https://www.korkmaz.com.tr"),
            ("Schafer", "Посуда и бытовые товары.", "https://www.schafer.com.tr"),
            ("Aryıldız", "Посуда и сервизы.", "https://www.aryildiz.com.tr"),
        ],
        "furniture": [
            ("Enza Home", "Современная мебель и декор (Yataş Group).", "https://www.enzahome.com.tr"),
            ("Yataş", "Мебель и матрасы.", "https://www.yatasbedding.com.tr"),
            ("Doğtaş", "Мебель для дома и офиса.", "https://www.dogtas.com"),
            ("Kelebek", "Один из старейших мебельных брендов.", "https://www.kelebek.com"),
            ("Bellona", "Мебель и текстиль для дома.", "https://www.bellona.com.tr"),
            ("Lazzoni", "Современная мебель ручной работы.", "https://www.lazzoni.com"),
            ("Nill's", "Премиальная мебель из Измира.", "https://www.nillsfurniture.com.tr"),
            ("İder", "Модульная мебель и декор.", "https://www.ider.com.tr"),
            ("İstikbal", "Мебель и товары для дома.", "https://www.istikbal.com.tr"),
            ("Mondi", "Современная мебель и текстиль.", "https://www.mondi.com.tr"),
            ("Alfemo", "Мебель для дома и офиса.", "https://www.alfemo.com.tr"),
            ("Modalife", "Мебель и аксессуары для дома.", "https://www.modalife.com.tr"),
        ],
        "medical-equipment": [
            ("Alvimedica", "Стенты, катетеры и кардиология.", "https://www.alvimedica.com"),
            ("Bıçakcılar", "Медицинские расходники и аппараты.", "https://www.bicakcilar.com"),
            ("Turkuaz Healthcare", "Оборудование и медтехника.", "https://www.turkuazhealthcare.com"),
            ("Tıpsan", "Медицинские кровати и оборудование.", "https://www.tipsan.com.tr"),
            ("Ankara Healthcare", "Производитель госпитального оборудования.", "https://www.ankarahealthcare.com"),
            ("Kardelen Medical", "Оборудование для клиник и лабораторий.", "https://www.kardelenmedikal.com"),
            ("TecoMed", "Медицинское оборудование и расходники.", "https://www.tecomed.com.tr"),
        ],
    }

    WORLD_BRANDS = {
        "medicines": [
            ("Pfizer", "Международная фармкомпания, инновационные препараты.", "Global pharmaceutical company focused on innovation.", "https://www.pfizer.com"),
            ("Bayer", "Немецкая компания в сфере здравоохранения.", "German healthcare and pharmaceuticals company.", "https://www.bayer.com"),
            ("Novartis", "Швейцарская фармкомпания с широким портфелем.", "Swiss pharmaceutical company with a broad portfolio.", "https://www.novartis.com"),
            ("Sanofi", "Французская фармкомпания.", "French pharmaceutical company.", "https://www.sanofi.com"),
            ("AstraZeneca", "Глобальная биофармацевтическая компания.", "Global biopharmaceutical company.", "https://www.astrazeneca.com"),
        ],
        "clothing": [
            ("Zara", "Испанский бренд одежды масс-маркета.", "Spanish fast-fashion brand.", "https://www.zara.com"),
            ("H&M", "Шведский fashion-ритейлер.", "Swedish fashion retailer.", "https://www2.hm.com"),
            ("Uniqlo", "Японский бренд базовой одежды.", "Japanese brand of everyday apparel.", "https://www.uniqlo.com"),
            ("Massimo Dutti", "Бренд одежды и аксессуаров.", "Fashion brand for apparel and accessories.", "https://www.massimodutti.com"),
            ("Tommy Hilfiger", "Международный fashion бренд.", "Global fashion brand.", "https://www.tommy.com"),
        ],
        "shoes": [
            ("Nike", "Глобальный бренд спортивной обуви.", "Global sports footwear brand.", "https://www.nike.com"),
            ("Adidas", "Немецкий бренд спортивной обуви и одежды.", "German sportswear and footwear brand.", "https://www.adidas.com"),
            ("Puma", "Бренд спортивной обуви и lifestyle.", "Sports and lifestyle footwear brand.", "https://www.puma.com"),
            ("New Balance", "Спортивная обувь и одежда.", "Athletic footwear and apparel brand.", "https://www.newbalance.com"),
            ("Skechers", "Повседневная и спортивная обувь.", "Casual and athletic footwear brand.", "https://www.skechers.com"),
        ],
        "electronics": [
            ("Samsung", "Южнокорейский производитель электроники.", "Korean consumer electronics manufacturer.", "https://www.samsung.com"),
            ("Apple", "Производитель смартфонов и электроники.", "Consumer electronics and smartphone maker.", "https://www.apple.com"),
            ("Sony", "Японский бренд электроники и медиа.", "Japanese electronics and media brand.", "https://www.sony.com"),
            ("LG", "Производитель бытовой электроники.", "Consumer electronics manufacturer.", "https://www.lg.com"),
            ("Xiaomi", "Смартфоны и умные устройства.", "Smartphones and smart devices.", "https://www.mi.com"),
        ],
        "tableware": [
            ("Villeroy & Boch", "Немецкая посуда и фарфор.", "German tableware and porcelain brand.", "https://www.villeroy-boch.com"),
            ("Tefal", "Бренд посуды и кухонной техники.", "Cookware and kitchen appliance brand.", "https://www.tefal.com"),
            ("Le Creuset", "Премиальная посуда и кухонные аксессуары.", "Premium cookware brand.", "https://www.lecreuset.com"),
            ("WMF", "Немецкий бренд посуды и аксессуаров.", "German cookware and accessories brand.", "https://www.wmf.com"),
        ],
        "furniture": [
            ("IKEA", "Мировой бренд мебели и товаров для дома.", "Global home furnishing brand.", "https://www.ikea.com"),
            ("Ashley", "Американский производитель мебели.", "US furniture manufacturer.", "https://www.ashleyfurniture.com"),
            ("BoConcept", "Датский бренд современной мебели.", "Danish modern furniture brand.", "https://www.boconcept.com"),
            ("Herman Miller", "Премиальная мебель и офисные решения.", "Premium furniture and office solutions.", "https://www.hermanmiller.com"),
            ("HAY", "Скандинавский дизайн и мебель.", "Scandinavian design and furniture.", "https://www.hay.dk"),
        ],
        "medical-equipment": [
            ("Medtronic", "Медицинская техника и импланты.", "Medical technology and devices company.", "https://www.medtronic.com"),
            ("Philips Healthcare", "Медтехника и клинические решения.", "Healthcare technology company.", "https://www.philips.com/healthcare"),
            ("GE Healthcare", "Медицинское оборудование и решения.", "Medical equipment and solutions.", "https://www.gehealthcare.com"),
            ("Siemens Healthineers", "Медицинская техника и диагностика.", "Medical technology and diagnostics.", "https://www.siemens-healthineers.com"),
        ],
    }

    PRODUCT_NAME_TEMPLATES = {
        "medicines": ["Парацетамол 500 мг", "Витамин C шипучий"],
        "tableware": ["Сервиз на 12 персон", "Набор стаканов"],
        "furniture": ["Диван 3-местный", "Комплект стол+стулья"],
        "medical-equipment": ["Электронный тонометр", "Набор хирургических инструментов"],
        "clothing": ["Базовая футболка", "Классическая рубашка"],
        "shoes": ["Кроссовки повседневные", "Кожаные лоферы"],
        "electronics": ["Смартфон серии X", "Умный телевизор 55\""],
    }

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Начинаем загрузку брендов..."))
        with transaction.atomic():
            brand_map = self._create_brands()
            self._seed_medicines(brand_map)
            self._seed_tableware(brand_map)
            self._seed_furniture(brand_map)
            self._seed_medical_equipment(brand_map)
            self._seed_clothing(brand_map)
            self._seed_shoes(brand_map)
            self._seed_electronics(brand_map)
        self.stdout.write(self.style.SUCCESS("Бренды и товары успешно созданы."))

    # --------------------------------------------------------------------- #
    # Helpers

    def _default_en_desc(self, product_type: str, origin: str) -> str:
        label = self.PRODUCT_TYPE_LABELS.get(product_type, "brand")
        prefix = "Turkish" if origin == "turkey" else "Global"
        return f"{prefix} {label} brand."

    def _iter_brand_items(self):
        for product_type, items in self.TURKISH_BRANDS.items():
            for name, desc_ru, website in items:
                yield product_type, name, desc_ru, self._default_en_desc(product_type, "turkey"), website, "turkey"
        for product_type, items in self.WORLD_BRANDS.items():
            for name, desc_ru, desc_en, website in items:
                yield product_type, name, desc_ru, desc_en, website, "global"

    def _ensure_brand_translations(self, brand: Brand, desc_ru: str, desc_en: str):
        for locale, desc in [("ru", desc_ru), ("en", desc_en)]:
            BrandTranslation.objects.update_or_create(
                brand=brand,
                locale=locale,
                defaults={"name": brand.name, "description": desc or ""},
            )

    def _get_brand_names(self, product_type: str) -> set[str]:
        names = {item[0] for item in self.TURKISH_BRANDS.get(product_type, [])}
        names.update({item[0] for item in self.WORLD_BRANDS.get(product_type, [])})
        return names

    def _create_brands(self) -> dict[str, Brand]:
        brand_map: dict[str, Brand] = {}
        for product_type, name, desc_ru, desc_en, website, origin in self._iter_brand_items():
            slug = slugify(name)
            brand, created = Brand.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": desc_ru,
                    "website": website,
                    "is_active": True,
                    "external_data": {"product_types": [product_type], "origin": origin},
                },
            )
            if not created:
                external = brand.external_data or {}
                types = set(external.get("product_types", []))
                types.add(product_type)
                external["product_types"] = sorted(types)
                if not external.get("origin"):
                    external["origin"] = origin
                brand.external_data = external
                if not brand.description:
                    brand.description = desc_ru
                if website and not brand.website:
                    brand.website = website
                brand.is_active = True
                brand.save()
            self._ensure_brand_translations(brand, desc_ru, desc_en)
            brand_map.setdefault(name, brand)
            self.stdout.write(f"✓ Бренд {name} ({product_type})")
        return brand_map

    def _ensure_category(self, slug: str, defaults: dict) -> Category:
        category, _ = Category.objects.get_or_create(slug=slug, defaults=defaults)
        return category

    # --------------------------------------------------------------------- #
    # Generic products (Product model)

    def _seed_medicines(self, brands: dict[str, Brand]):
        category = self._ensure_category(
            "medicines-general",
            {"name": "Медикаменты", "description": "Базовая категория лекарств", "is_active": True},
        )
        self._create_generic_products("medicines", category, brands)

    def _seed_tableware(self, brands: dict[str, Brand]):
        category = self._ensure_category(
            "tableware-serveware",
            {"name": "Посуда", "description": "Столовая посуда и сервировка", "is_active": True},
        )
        self._create_generic_products("tableware", category, brands)

    def _seed_furniture(self, brands: dict[str, Brand]):
        root = self._ensure_category(
            "furniture",
            {"name": "Мебель", "description": "Мебель для дома и офиса", "is_active": True},
        )
        category = self._ensure_category(
            "furniture-living",
            {"name": "Мебель для гостиной", "description": "Диваны и мебель для дома", "is_active": True, "parent": root},
        )
        if category.parent_id != root.id:
            category.parent = root
            category.save(update_fields=["parent"])
        garden = self._ensure_category(
            "furniture-garden",
            {"name": "Мебель для сада", "description": "Садовая мебель и аксессуары", "is_active": True, "parent": root},
        )
        if garden.parent_id != root.id:
            garden.parent = root
            garden.save(update_fields=["parent"])
        self._create_furniture_products(category, brands)
        self._create_furniture_products(garden, brands, name_prefix="Садовая ")

    def _seed_medical_equipment(self, brands: dict[str, Brand]):
        category = self._ensure_category(
            "medical-equipment",
            {"name": "Медицинское оборудование", "description": "Оборудование для клиник", "is_active": True},
        )
        self._create_generic_products("medical-equipment", category, brands)

    def _create_generic_products(
        self,
        product_type: str,
        category: Category,
        brands: dict[str, Brand],
        brand_subset: str | None = None,
    ):
        name_suffixes = self.PRODUCT_NAME_TEMPLATES[product_type]
        source_type = brand_subset or product_type
        brand_names = self._get_brand_names(source_type)
        for brand_name in brand_names:
            brand = brands.get(brand_name)
            if not brand:
                continue
            for idx, suffix in enumerate(name_suffixes):
                product_name = f"{brand.name} {suffix}"
                Product.objects.get_or_create(
                    slug=slugify(product_name),
                    defaults={
                        "name": product_name,
                        "category": category,
                        "brand": brand,
                        "price": 150 + idx * 25,
                        "currency": "TRY",
                        "is_active": True,
                        "is_available": True,
                        "description": f"Тестовая позиция бренда {brand.name} ({product_type}).",
                    },
                )

    def _create_furniture_products(self, category: Category, brands: dict[str, Brand], name_prefix: str = ""):
        name_suffixes = self.PRODUCT_NAME_TEMPLATES["furniture"]
        brand_names = self._get_brand_names("furniture")
        materials = ["Дерево", "Ткань"]
        types = ["sofas", "tables", "chairs", "wardrobes"]
        dimensions = ["200x90x80 см", "160x90x75 см"]

        for brand_name in brand_names:
            brand = brands.get(brand_name)
            if not brand:
                continue
            for idx, suffix in enumerate(name_suffixes):
                product_name = f"{brand.name} {name_prefix}{suffix}".strip()
                FurnitureProduct.objects.get_or_create(
                    slug=slugify(product_name),
                    defaults={
                        "name": product_name,
                        "category": category,
                        "brand": brand,
                        "price": 9999 + idx * 1500,
                        "currency": "TRY",
                        "material": materials[idx % len(materials)],
                        "furniture_type": types[idx % len(types)],
                        "dimensions": dimensions[idx % len(dimensions)],
                        "is_active": True,
                        "is_available": True,
                        "description": f"Тестовая мебель от {brand.name}.",
                    },
                )

    # --------------------------------------------------------------------- #
    # Clothing

    def _seed_clothing(self, brands: dict[str, Brand]):
        root, _ = Category.objects.get_or_create(
            slug="women-fashion",
            defaults={"name": "Одежда", "gender": "women", "clothing_type": "general", "is_active": True, "sort_order": 1},
        )
        dresses, _ = Category.objects.get_or_create(
            slug="dresses-turkish",
            defaults={
                "name": "Платья",
                "gender": "women",
                "clothing_type": "dresses",
                "parent": root,
                "is_active": True,
                "sort_order": 2,
            },
        )

        for name in self._get_brand_names("clothing"):
            brand = brands.get(name)
            if not brand:
                continue
            for idx, suffix in enumerate(self.PRODUCT_NAME_TEMPLATES["clothing"]):
                product_name = f"{brand.name} {suffix}"
                ClothingProduct.objects.get_or_create(
                    slug=slugify(product_name),
                    defaults={
                        "name": product_name,
                        "category": dresses if idx % 2 == 0 else root,
                        "brand": brand,
                        "price": 799 + idx * 150,
                        "currency": "TRY",
                        "size": "M",
                        "color": "Бежевый" if idx % 2 == 0 else "Черный",
                        "material": "Хлопок",
                        "season": "Всесезон",
                        "is_active": True,
                        "is_available": True,
                        "description": f"Коллекция {brand.name}, тестовая позиция.",
                    },
                )

    # --------------------------------------------------------------------- #
    # Shoes

    def _seed_shoes(self, brands: dict[str, Brand]):
        root_category, _ = Category.objects.get_or_create(
            slug="shoes",
            defaults={"name": "Обувь", "is_active": True, "sort_order": 0},
        )
        women, _ = Category.objects.get_or_create(
            slug="women-shoes",
            defaults={"name": "Женская обувь", "gender": "women", "is_active": True, "sort_order": 1, "parent": root_category},
        )
        if women.parent_id != root_category.id:
            women.parent = root_category
            women.save(update_fields=["parent"])
        men, _ = Category.objects.get_or_create(
            slug="men-shoes",
            defaults={"name": "Мужская обувь", "gender": "men", "is_active": True, "sort_order": 2, "parent": root_category},
        )
        if men.parent_id != root_category.id:
            men.parent = root_category
            men.save(update_fields=["parent"])
        kids, _ = Category.objects.get_or_create(
            slug="kids-shoes",
            defaults={"name": "Детская обувь", "gender": "kids", "is_active": True, "sort_order": 3, "parent": root_category},
        )
        if kids.parent_id != root_category.id:
            kids.parent = root_category
            kids.save(update_fields=["parent"])
        root, _ = Category.objects.get_or_create(
            slug="unisex-shoes",
            defaults={"name": "Обувь", "gender": "unisex", "is_active": True, "sort_order": 1, "parent": root_category},
        )
        if root.parent_id != root_category.id:
            root.parent = root_category
            root.save(update_fields=["parent"])
        sneakers, _ = Category.objects.get_or_create(
            slug="sneakers-turkish",
            defaults={
                "name": "Кроссовки",
                "gender": "unisex",
                "parent": root,
                "is_active": True,
                "sort_order": 2,
            },
        )

        for name in self._get_brand_names("shoes"):
            brand = brands.get(name)
            if not brand:
                continue
            for idx, suffix in enumerate(self.PRODUCT_NAME_TEMPLATES["shoes"]):
                product_name = f"{brand.name} {suffix}"
                category_pool = [women, men, kids, root]
                picked_category = category_pool[idx % len(category_pool)]
                ShoeProduct.objects.get_or_create(
                    slug=slugify(product_name),
                    defaults={
                        "name": product_name,
                        "category": sneakers if idx % 2 == 0 else picked_category,
                        "brand": brand,
                        "price": 1299 + idx * 200,
                        "currency": "TRY",
                        "size": "42",
                        "color": "Белый" if idx % 2 == 0 else "Коричневый",
                        "material": "Натуральная кожа",
                        "heel_height": "3 см",
                        "sole_type": "Резина",
                        "is_active": True,
                        "is_available": True,
                        "description": f"Обувь {brand.name}, тестовый SKU.",
                    },
                )

    # --------------------------------------------------------------------- #
    # Electronics

    def _seed_electronics(self, brands: dict[str, Brand]):
        phones, _ = Category.objects.get_or_create(
            slug="smartphones-tr",
            defaults={"name": "Смартфоны", "device_type": "phones", "is_active": True, "sort_order": 1},
        )
        tvs, _ = Category.objects.get_or_create(
            slug="smart-tv",
            defaults={"name": "Умные телевизоры", "device_type": "tv", "is_active": True, "sort_order": 2},
        )

        for name in self._get_brand_names("electronics"):
            brand = brands.get(name)
            if not brand:
                continue
            for idx, suffix in enumerate(self.PRODUCT_NAME_TEMPLATES["electronics"]):
                product_name = f"{brand.name} {suffix}"
                ElectronicsProduct.objects.get_or_create(
                    slug=slugify(product_name),
                    defaults={
                        "name": product_name,
                        "category": phones if idx % 2 == 0 else tvs,
                        "brand": brand,
                        "price": 8999 + idx * 2500,
                        "currency": "TRY",
                        "model": f"{brand.name[:4].upper()}-{idx + 1}",
                        "specifications": {"storage": "128GB", "ram": "8GB"},
                        "warranty": "2 года",
                        "power_consumption": "A",
                        "is_active": True,
                        "is_available": True,
                        "description": f"Флагманский продукт {brand.name}.",
                    },
                )
