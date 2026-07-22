from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.catalog.models import (
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
    Service,
    ServiceAttribute,
    ServiceImage,
    ServicePortfolioItem,
    ServicePortfolioMedia,
)


ASSET_DIR = Path("/app/tmp_service_assets")

ATTRIBUTES = [
    ("launch-time", "Срок запуска", "Launch time", "Запуск süresi", "от 3 дней", "from 3 days"),
    ("support", "Поддержка", "Support", "Destek", "30 дней", "30 days"),
    ("work-format", "Формат работы", "Work format", "Çalışma formatı", "удаленно", "remote"),
    (
        "technologies",
        "Технологии",
        "Technologies",
        "Teknolojiler",
        "Python, Django, FastAPI, React",
        "Python, Django, FastAPI, React",
    ),
    (
        "integrations",
        "Интеграции",
        "Integrations",
        "Entegrasyonlar",
        "CRM, API, платежные системы",
        "CRM, API, payment systems",
    ),
]

SERVICES = [
    {
        "key": "sites",
        "id": 9,
        "name": "Разработка сайтов под ключ",
        "slug": "razrabotka-sajtov-pod-klyuch",
        "asset": "web-sites-og-1200x630.png",
        "description": (
            "Разрабатываю сайты под ключ для бизнеса: корпоративные сайты, интернет-магазины, "
            "каталоги, личные кабинеты и веб-сервисы. Беру проект от идеи и прототипа до запуска, "
            "аналитики и дальнейшей поддержки.\n\n"
            "Что входит в работу:\n"
            "• Анализ задачи, структура и прототип\n"
            "• Адаптивный дизайн для смартфонов и компьютеров\n"
            "• Backend на Python, Django или FastAPI\n"
            "• Frontend на React или Vue\n"
            "• Интеграция CRM, платежей, доставки и внешних API\n"
            "• Административная панель и управление контентом\n"
            "• SEO-настройка, аналитика, развертывание и 30 дней поддержки\n\n"
            "В результате вы получаете быстрый и надежный сайт, готовый к продвижению и масштабированию."
        ),
        "meta_title": "Разработка сайтов под ключ | Python, Django, React",
        "meta_description": (
            "Разработка сайтов, интернет-магазинов и веб-приложений под ключ. Python, Django, "
            "FastAPI, React. Интеграция CRM, платежей и API. Запуск и поддержка."
        ),
        "keywords": (
            "разработка сайтов, создание сайтов, разработка сайтов под ключ, разработка интернет магазинов, "
            "веб разработка, python разработчик, django разработчик, fastapi разработчик, "
            "react разработчик, vue разработчик, разработка веб приложений, интеграция crm"
        ),
        "og_title": "Разработка сайтов под ключ",
        "og_description": (
            "Создаю сайты, интернет-магазины и веб-приложения. Интеграции CRM, платежей и API. "
            "От идеи до запуска и поддержки."
        ),
        "case_title": "Корпоративный сайт с системой заявок",
        "case_title_en": "Corporate website with a lead management system",
        "case_summary": (
            "Разработан адаптивный сайт с формой заявок и административной панелью. "
            "Скорость загрузки менее 2 секунд."
        ),
        "case_description": (
            "Клиенту требовался современный корпоративный сайт для привлечения новых клиентов "
            "и автоматизации обработки заявок.\n\n"
            "Был разработан адаптивный интерфейс, интегрирована форма заявок с уведомлениями "
            "в Telegram, настроена SEO-оптимизация и базовая аналитика.\n\n"
            "Результат:\n"
            "• Адаптивная верстка для всех устройств\n"
            "• Загрузка страниц менее 2 секунд\n"
            "• Уведомления о заявках в Telegram\n"
            "• Простая система управления контентом\n"
            "• Готовность к дальнейшему масштабированию"
        ),
        "case_alt": "Разработка корпоративного сайта на Django и React",
    },
    {
        "key": "mini_apps",
        "name": "Разработка Telegram Mini Apps",
        "slug": "razrabotka-telegram-mini-apps",
        "asset": "telegram-mini-apps-og-1200x630.png",
        "description": (
            "Создаю Telegram Mini Apps для продаж, онлайн-заказов, бронирования, личных кабинетов "
            "и автоматизации бизнес-процессов. Мини-приложение открывается прямо в Telegram и не требует установки.\n\n"
            "Что входит в разработку:\n"
            "• Сценарии, прототип и адаптивный интерфейс\n"
            "• Backend на Python, Django или FastAPI\n"
            "• Frontend на React и Telegram Web Apps API\n"
            "• Авторизация через Telegram и безопасная работа с данными\n"
            "• Интеграция CRM, платежей, доставки и внешних API\n"
            "• Административная панель, аналитика и уведомления\n"
            "• Развертывание, тестирование и 30 дней поддержки\n\n"
            "Вы получаете готовый продукт: от идеи и дизайна до запуска и масштабирования."
        ),
        "meta_title": "Разработка Telegram Mini Apps под ключ | Python, React",
        "meta_description": (
            "Разработка Telegram Mini Apps под ключ: каталог, онлайн-заказы, платежи, CRM и API. "
            "Python, Django, FastAPI, React. От прототипа до запуска."
        ),
        "keywords": (
            "разработка telegram mini apps, telegram mini app, telegram web app, создание telegram mini app, "
            "разработка мини приложений telegram, python разработчик, django, fastapi, react, telegram api, "
            "онлайн заказы telegram, платежи telegram"
        ),
        "og_title": "Разработка Telegram Mini Apps под ключ",
        "og_description": (
            "Создаю Telegram Mini Apps для продаж, заказов и автоматизации. "
            "Интеграции CRM, платежей и API. От идеи до запуска."
        ),
        "case_title": "Telegram Mini App для онлайн-заказов",
        "case_title_en": "Telegram Mini App for online orders",
        "case_summary": (
            "Создано Mini App с каталогом, корзиной, онлайн-оплатой и уведомлениями. "
            "Заказ оформляется внутри Telegram."
        ),
        "case_description": (
            "Для бизнеса требовался быстрый канал онлайн-продаж без отдельного мобильного приложения.\n\n"
            "Разработано Telegram Mini App с каталогом, корзиной, оформлением заказа, онлайн-оплатой "
            "и административной панелью. Заказы передаются менеджеру и в CRM, а клиент получает статусы в Telegram.\n\n"
            "Результат:\n"
            "• Покупка без выхода из Telegram\n"
            "• Адаптивный интерфейс на React\n"
            "• Backend и API на Python/Django\n"
            "• Интеграция платежей и CRM\n"
            "• Готовность к росту каталога и нагрузки"
        ),
        "case_alt": "Telegram Mini App для онлайн-заказов на Django и React",
    },
    {
        "key": "bots",
        "name": "Разработка Telegram-ботов",
        "slug": "razrabotka-telegram-botov",
        "asset": "telegram-bots-og-1200x630.png",
        "description": (
            "Разрабатываю Telegram-ботов для продаж, поддержки клиентов, приема заявок, уведомлений "
            "и автоматизации внутренних процессов. Бот работает круглосуточно и интегрируется с вашими сервисами.\n\n"
            "Возможности:\n"
            "• Сценарии диалогов, меню и формы заявок\n"
            "• Каталог, корзина, платежи и подписки\n"
            "• Интеграция CRM, сайта, Google Sheets и внешних API\n"
            "• Уведомления сотрудникам и клиентам\n"
            "• Административная панель и аналитика\n"
            "• Python, Django, FastAPI, PostgreSQL и Redis\n"
            "• Развертывание и 30 дней поддержки\n\n"
            "Подготавливаю архитектуру с учетом безопасности, роста аудитории и дальнейшего развития бота."
        ),
        "meta_title": "Разработка Telegram-ботов под ключ | Python, Django, API",
        "meta_description": (
            "Разработка Telegram-ботов для продаж, поддержки и автоматизации. Python, Django, "
            "FastAPI. Интеграция CRM, платежей, сайта и внешних API."
        ),
        "keywords": (
            "разработка telegram ботов, создание telegram бота, telegram bot, бот для бизнеса, "
            "python telegram bot, django разработчик, fastapi разработчик, интеграция crm, "
            "чат бот telegram, автоматизация telegram, бот для продаж"
        ),
        "og_title": "Разработка Telegram-ботов под ключ",
        "og_description": (
            "Telegram-боты для продаж, поддержки и автоматизации. CRM, платежи и внешние API. "
            "От сценария до запуска."
        ),
        "case_title": "Telegram-бот для приема и обработки заявок",
        "case_title_en": "Telegram bot for lead capture and processing",
        "case_summary": (
            "Бот автоматизировал прием заявок, квалификацию клиентов и передачу данных менеджеру в CRM."
        ),
        "case_description": (
            "Компании требовалось сократить время ответа и перестать терять обращения из Telegram.\n\n"
            "Разработан бот с пошаговой формой, проверкой данных, уведомлениями менеджерам и интеграцией CRM. "
            "Клиент сразу получает подтверждение, а сотрудник — структурированную заявку.\n\n"
            "Результат:\n"
            "• Автоматический прием заявок 24/7\n"
            "• Меньше ручной работы и ошибок\n"
            "• Передача данных в CRM\n"
            "• Уведомления ответственным сотрудникам\n"
            "• Возможность добавлять новые сценарии"
        ),
        "case_alt": "Разработка Telegram-бота для автоматизации заявок на Python",
    },
    {
        "key": "automation",
        "name": "Автоматизация бизнеса на Python",
        "slug": "avtomatizaciya-biznesa-na-python",
        "asset": "python-automation-og-1200x630.png",
        "description": (
            "Автоматизирую повторяющиеся бизнес-процессы на Python: обработку заявок, обмен данными, "
            "отчеты, уведомления, интеграции и работу с внешними сервисами.\n\n"
            "Что можно автоматизировать:\n"
            "• Передачу данных между сайтом, CRM и учетными системами\n"
            "• Формирование отчетов и документов\n"
            "• Обработку заявок, заказов и платежей\n"
            "• Уведомления в Telegram и электронной почте\n"
            "• Сбор и нормализацию данных из API\n"
            "• Фоновые задачи, очереди и расписания\n"
            "• Внутренние панели управления\n\n"
            "Решение документируется, тестируется и разворачивается на вашем сервере с 30 днями поддержки."
        ),
        "meta_title": "Автоматизация бизнеса на Python | CRM, API, интеграции",
        "meta_description": (
            "Автоматизация бизнес-процессов на Python: CRM, API, отчеты, заявки, платежи и уведомления. "
            "Django, FastAPI, PostgreSQL. Внедрение под ключ."
        ),
        "keywords": (
            "автоматизация бизнеса, автоматизация на python, python разработчик, интеграция crm, "
            "интеграция api, автоматизация заявок, автоматизация отчетов, django разработчик, "
            "fastapi разработчик, бизнес процессы, разработка crm"
        ),
        "og_title": "Автоматизация бизнеса на Python",
        "og_description": (
            "Автоматизирую заявки, отчеты, CRM, платежи и обмен данными. "
            "Python, Django, FastAPI и интеграции под ключ."
        ),
        "case_title": "Автоматизация заявок и отчетности",
        "case_title_en": "Lead and reporting automation",
        "case_summary": (
            "Заявки автоматически распределяются, попадают в CRM и включаются в ежедневную отчетность."
        ),
        "case_description": (
            "Сотрудники вручную переносили заявки между сервисами и собирали отчеты в таблицах.\n\n"
            "Разработан Python-сервис, который получает данные через API, проверяет их, создает записи в CRM, "
            "уведомляет ответственных и формирует сводные отчеты по расписанию.\n\n"
            "Результат:\n"
            "• Единый автоматический поток данных\n"
            "• Сокращение ручных операций\n"
            "• Меньше ошибок и потерянных заявок\n"
            "• Регулярная отчетность без участия сотрудников\n"
            "• Логи и мониторинг всех операций"
        ),
        "case_alt": "Автоматизация бизнес-процессов и CRM на Python",
    },
]


def set_attributes(service):
    for order, (slug, ru, en, tr, value_ru, value_en) in enumerate(ATTRIBUTES):
        key, _ = GlobalAttributeKey.objects.get_or_create(slug=slug, defaults={"sort_order": order})
        key.categories.add(service.category)
        for locale, name in (("ru", ru), ("en", en), ("tr", tr)):
            GlobalAttributeKeyTranslation.objects.update_or_create(
                key_obj=key, locale=locale, defaults={"name": name}
            )
        ServiceAttribute.objects.update_or_create(
            service=service,
            attribute_key=key,
            defaults={
                "value": value_ru,
                "value_ru": value_ru,
                "value_en": value_en,
                "sort_order": order,
            },
        )


def upload_main_image(service, asset_name, alt_text):
    data = (ASSET_DIR / asset_name).read_bytes()
    service.main_image_file.save(asset_name, ContentFile(data), save=False)
    service.main_image = ""
    service.save(update_fields=["main_image_file", "main_image", "updated_at"])
    service.og_image_url = default_storage.url(service.main_image_file.name)
    service.save(update_fields=["og_image_url", "updated_at"])
    service.images.update(is_main=False)
    ServiceImage.objects.update_or_create(
        service=service,
        image_file=service.main_image_file.name,
        defaults={"alt_text": alt_text, "sort_order": 0, "is_main": True},
    )


with transaction.atomic():
    original = Service.objects.select_for_update().get(pk=9)
    category = original.category
    price = original.price
    currency = original.currency
    gallery_sources = list(original.images.exclude(image_file="").order_by("id")[:2])
    portfolio_media = original.portfolio_items.filter(pk=17).first()
    source_media = portfolio_media.media_items.order_by("id").first() if portfolio_media else None

    result = []
    for spec in SERVICES:
        if spec.get("id"):
            service = original
        else:
            service, _ = Service.objects.get_or_create(
                slug=spec["slug"], defaults={"name": spec["name"]}
            )

        service.name = spec["name"]
        service.slug = spec["slug"]
        service.description = spec["description"]
        service.category = category
        service.price = price
        service.currency = currency
        service.is_active = True
        service.is_featured = True
        service.meta_title = spec["meta_title"]
        service.meta_description = spec["meta_description"]
        service.meta_keywords = spec["keywords"]
        service.og_title = spec["og_title"]
        service.og_description = spec["og_description"]
        service.save()

        upload_main_image(service, spec["asset"], spec["case_alt"])
        set_attributes(service)

        for index, source in enumerate(gallery_sources, start=1):
            ServiceImage.objects.update_or_create(
                service=service,
                image_file=source.image_file.name,
                defaults={
                    "alt_text": f"{spec['name']}: пример проекта {index}",
                    "sort_order": index,
                    "is_main": False,
                },
            )

        if spec["key"] == "sites":
            case = ServicePortfolioItem.objects.select_for_update().get(pk=17)
            case.title = spec["case_title"]
            case.title_en = spec["case_title_en"]
            case.category = category
            case.service = service
        else:
            case, _ = ServicePortfolioItem.objects.get_or_create(
                service=service,
                title=spec["case_title"],
                defaults={"category": category, "title_en": spec["case_title_en"]},
            )
        case.result_summary = spec["case_summary"]
        case.result_summary_en = spec["case_summary"]
        case.city = "Удаленно"
        case.city_en = "Remote"
        case.description = spec["case_description"]
        case.description_en = spec["case_description"]
        case.alt_text = spec["case_alt"]
        case.alt_text_en = spec["case_alt"]
        case.sort_order = 0
        case.is_active = True
        case.save()

        if source_media and not case.media_items.exists():
            ServicePortfolioMedia.objects.create(
                portfolio_item=case,
                media_type=source_media.media_type,
                badge="none",
                media_file=source_media.media_file.name,
                media_url=source_media.media_url,
                sort_order=0,
            )

        result.append(
            {
                "id": service.pk,
                "name": service.name,
                "slug": service.slug,
                "attributes": service.service_attributes.count(),
                "images": service.images.count(),
                "cases": service.portfolio_items.count(),
                "og": service.og_image_url,
            }
        )

print(result)
