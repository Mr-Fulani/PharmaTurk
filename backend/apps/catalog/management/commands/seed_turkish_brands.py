"""Создает тестовый набор турецких брендов и базовых товаров для каждой витрины."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import transaction

from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ClothingProduct,
    ShoeProduct,
    ElectronicsProduct,
)


class Command(BaseCommand):
    help = "Создает турецкие бренды и примерные товары для тестовых витрин"

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
        ],
        "medical-equipment": [
            ("Alvimedica", "Стенты, катетеры и кардиология.", "https://www.alvimedica.com"),
            ("Bıçakcılar", "Медицинские расходники и аппараты.", "https://www.bicakcilar.com"),
            ("Turkuaz Healthcare", "Оборудование и медтехника.", "https://www.turkuazhealthcare.com"),
            ("Tıpsan", "Медицинские кровати и оборудование.", "https://www.tipsan.com.tr"),
            ("Ankara Healthcare", "Производитель госпитального оборудования.", "https://www.ankarahealthcare.com"),
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
        self.stdout.write(self.style.NOTICE("Начинаем загрузку турецких брендов..."))
        with transaction.atomic():
            brand_map = self._create_brands()
            self._seed_medicines(brand_map)
            self._seed_tableware(brand_map)
            self._seed_furniture(brand_map)
            self._seed_medical_equipment(brand_map)
            self._seed_clothing(brand_map)
            self._seed_shoes(brand_map)
            self._seed_electronics(brand_map)
        self.stdout.write(self.style.SUCCESS("Турецкие бренды и товары успешно созданы."))

    # --------------------------------------------------------------------- #
    # Helpers

    def _create_brands(self) -> dict[str, Brand]:
        brand_map: dict[str, Brand] = {}
        for product_type, items in self.TURKISH_BRANDS.items():
            for name, description, website in items:
                slug = slugify(name)
                brand, created = Brand.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": description,
                        "website": website,
                        "is_active": True,
                        "external_data": {"product_types": [product_type]},
                    },
                )
                if not created:
                    external = brand.external_data or {}
                    types = set(external.get("product_types", []))
                    types.add(product_type)
                    external["product_types"] = sorted(types)
                    brand.external_data = external
                    if not brand.description:
                        brand.description = description
                    if website and not brand.website:
                        brand.website = website
                    brand.is_active = True
                    brand.save()
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
        category = self._ensure_category(
            "furniture-living",
            {"name": "Мебель для гостиной", "description": "Диваны и мебель для дома", "is_active": True},
        )
        self._create_generic_products("furniture", category, brands)

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
        brand_names = {item[0] for item in self.TURKISH_BRANDS.get(source_type, [])}
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

        for name, _, _ in self.TURKISH_BRANDS["clothing"]:
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
        root, _ = Category.objects.get_or_create(
            slug="unisex-shoes",
            defaults={"name": "Обувь", "gender": "unisex", "shoe_type": "general", "is_active": True, "sort_order": 1},
        )
        sneakers, _ = Category.objects.get_or_create(
            slug="sneakers-turkish",
            defaults={
                "name": "Кроссовки",
                "gender": "unisex",
                "shoe_type": "sneakers",
                "parent": root,
                "is_active": True,
                "sort_order": 2,
            },
        )

        for name, _, _ in self.TURKISH_BRANDS["shoes"]:
            brand = brands.get(name)
            if not brand:
                continue
            for idx, suffix in enumerate(self.PRODUCT_NAME_TEMPLATES["shoes"]):
                product_name = f"{brand.name} {suffix}"
                ShoeProduct.objects.get_or_create(
                    slug=slugify(product_name),
                    defaults={
                        "name": product_name,
                        "category": sneakers if idx % 2 == 0 else root,
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

        for name, _, _ in self.TURKISH_BRANDS["electronics"]:
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

