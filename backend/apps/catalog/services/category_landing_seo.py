"""SEO посадочных страниц разделов через Claude: H1, title, description и SEO-текст RU/EN.

Тексты медикаментов написаны вручную (миграция 0222), здесь — остальные разделы:
БАДы, одежда, обувь, мебель и т.д. Модель пишет только по фактам раздела из базы
(названия, бренды, подразделы, примеры товаров) и по правилам сайта. Код проверяет
длины и запрещённые обещания; запись в базу — отдельным шагом и только в пустые поля
(docs/CATEGORY_LANDING_SEO.md).
"""

import json
import re

from django.db import transaction
from django.db.models import Count

from apps.catalog.models import Category, CategoryTranslation, Product

SEO_FIELDS = ("h1", "meta_title", "meta_description", "seo_text")
LOCALES = ("ru", "en")
TITLE_SUFFIX = " | Mudaroba"

# Разделы с ручными текстами (миграция 0222) и услуги Стамбула — не трогаем.
EXCLUDED_ROOTS = {"medicines", "uslugi"}

# Корни разделов, где у товара есть сроки доставки на сайте (карточки БАДов: 7–21 рабочий день).
DELIVERY_DAYS_ROOTS = {"supplements"}

SYSTEM_PROMPT = """Ты пишешь SEO-тексты посадочных страниц разделов интернет-витрины Mudaroba (mudaroba.com).
Mudaroba — витрина товаров из Турции для русскоязычных покупателей. Оплаты на сайте нет: покупатель
добавляет товары в «Список заявки» и отправляет его, менеджер проверяет наличие (и размер, цвет),
рассчитывает стоимость вместе с доставкой и согласует детали; оплата — только после согласованного расчёта.

Тебе дают факты раздела: название, родительские разделы, подразделы, бренды и примеры товаров из каталога.
Пиши ТОЛЬКО на основе этих фактов и правил выше. Нельзя придумывать бренды, материалы, страны производства,
сроки, цены, размеры, скидки, гарантии, характеристики товаров.

Что нужно вернуть — JSON {"ru": {...}, "en": {...}}, в каждом языке четыре поля:
- "h1": заголовок страницы, 25–70 символов, естественная фраза с главным запросом раздела
  (например «Турецкие витамины группы B», «Кроссовки из Турции»). Не копия title.
- "meta_title": 35–70 символов ВМЕСТЕ с окончанием « | Mudaroba» (оно обязательно в конце).
  Главный запрос + «из Турции» (EN: «from Turkey»), можно 1–2 бренда или вида товаров из фактов.
- "meta_description": 120–190 символов. Что есть в разделе (виды товаров, 2–3 бренда из фактов)
  и как заказать (заявка, менеджер рассчитает стоимость с доставкой). Без чисел товаров и цен.
- "seo_text": 180–320 слов. Обычный текст: абзацы через пустую строку, 2–3 подзаголовка строкой
  с «## » в начале. Содержание: что собрано в разделе и его подразделах, какие бренды и формы/виды
  товаров есть (только из фактов), как выбрать (практично: форма выпуска, состав на упаковке, размер —
  уточнить у менеджера), как оформить заказ. Пиши для людей: конкретно, без воды, без повторов
  ключевой фразы в каждом предложении (главный запрос — 2–4 раза на весь текст).

Запрещено (в обоих языках):
- количество товаров, цены, валюты, проценты скидок; любые числа, кроме тех, что есть в названиях
  (D3, B12, Q10, Омега-3) и в разрешённом сроке доставки;
- «лучший», «№1», «самые низкие цены», «скидки», «акция», «бесплатно», «гарантия», «гарантируем»;
- обещания про здоровье: лечит, вылечивает, исцеляет, предотвращает болезни, укрепляет иммунитет,
  «эффективный», «безопасный»; БАД не лекарство — в разделах БАДов одной фразой напомни, что это
  не лекарственное средство и перед приёмом стоит посоветоваться со специалистом;
- слова «лечение», «лечить» в любом виде (в том числе в оговорках), «без рецепта»;
- сроки доставки, если их нет в фактах; названия магазинов-источников (только бренды из фактов).

Английская версия — не дословный перевод, а естественный текст для англоязычного покупателя
с теми же фактами и правилами; без кириллицы."""


def _subtree_ids(category, children_by_parent):
    ids, stack = [], [category.id]
    while stack:
        current = stack.pop()
        ids.append(current)
        stack.extend(children_by_parent.get(current, []))
    return ids


def _root_slug(category, by_id):
    current = category
    while current.parent_id and current.parent_id in by_id:
        current = by_id[current.parent_id]
    return current.slug


def _translation_names(category):
    names = {t.locale: t.name for t in category.translations.all() if t.name}
    return names.get("ru") or category.name, names.get("en") or ""


def select_categories(*, slugs=None, roots=None, include_filled=False):
    """Активные непустые разделы для текстов, без медикаментов и услуг.

    slugs — ровно эти разделы; roots — корни целиком (сам корень и все потомки).
    Раздел, у которого уже есть русский SEO-текст, пропускается без include_filled.
    """
    categories = list(Category.objects.filter(is_active=True).prefetch_related("translations"))
    by_id = {c.id: c for c in categories}
    children_by_parent = {}
    for c in categories:
        if c.parent_id:
            children_by_parent.setdefault(c.parent_id, []).append(c.id)
    with_products = set(
        Product.objects.filter(is_active=True).exclude(category_id__isnull=True)
        .values_list("category_id", flat=True).distinct()
    )

    wanted_slugs = set(slugs or [])
    wanted_roots = set(roots or [])
    selected = []
    for category in sorted(categories, key=lambda c: (c.parent_id or 0, c.sort_order, c.id)):
        root = _root_slug(category, by_id)
        if root in EXCLUDED_ROOTS:
            continue
        if wanted_slugs and category.slug not in wanted_slugs:
            continue
        if wanted_roots and root not in wanted_roots:
            continue
        if not wanted_slugs and not wanted_roots:
            continue
        if not with_products.intersection(_subtree_ids(category, children_by_parent)):
            continue
        ru = next((t for t in category.translations.all() if t.locale == "ru"), None)
        if ru is not None and ru.seo_text and not include_filled:
            continue
        selected.append(category)
    return selected


def collect_facts(category):
    """Факты раздела для промпта: только то, что видно на сайте."""
    categories = {c.id: c for c in Category.objects.filter(is_active=True).prefetch_related("translations")}
    children_by_parent = {}
    for c in categories.values():
        if c.parent_id:
            children_by_parent.setdefault(c.parent_id, []).append(c.id)
    subtree = _subtree_ids(category, children_by_parent)
    products = Product.objects.filter(is_active=True, category_id__in=subtree)

    nonempty = set(products.values_list("category_id", flat=True).distinct())
    children = []
    for child_id in children_by_parent.get(category.id, []):
        child = categories[child_id]
        if nonempty.intersection(_subtree_ids(child, children_by_parent)):
            children.append(_translation_names(child)[0])

    parents = []
    current = categories.get(category.parent_id)
    while current is not None:
        parents.insert(0, _translation_names(current)[0])
        current = categories.get(current.parent_id)

    brands = [
        row["brand__name"]
        for row in products.exclude(brand__isnull=True)
        .values("brand__name").annotate(n=Count("id")).order_by("-n", "brand__name")[:12]
    ]
    examples = []
    for name in products.order_by("-is_featured", "-id").values_list("name", flat=True)[:300]:
        name = (name or "").strip()
        if name and name not in examples:
            examples.append(name)
        if len(examples) >= 20:
            break

    name_ru, name_en = _translation_names(category)
    root = _root_slug(category, categories)
    return {
        "slug": category.slug,
        "name_ru": name_ru,
        "name_en": name_en,
        "parents": parents,
        "subsections": children,
        "brands": brands,
        "product_examples": examples,
        "is_supplements": root == "supplements",
        "delivery": "доставка 7–21 рабочий день" if root in DELIVERY_DAYS_ROOTS else "",
    }


def build_user_prompt(facts):
    return "Факты раздела:\n" + json.dumps(facts, ensure_ascii=False, indent=1)


_RU_FORBIDDEN = re.compile(
    r"леч|исцел|гарант|лучш|№\s*1|скидк|акци[яи]|бесплатн|дешев|дёшев|без рецепта|"
    r"иммунитет укрепл|укрепля\w* иммун|эффективн|безопасн|₽|руб\.|\bруб\b|\bлир|\bTL\b|\$",
    re.IGNORECASE,
)
_EN_FORBIDDEN = re.compile(
    r"\bcur(e|es|ing)\b|\btreat|\bheal|guarant|\bbest\b|cheapest|discount|free (shipping|delivery)|for free|free of charge|"
    r"no prescription|without (a )?prescription|effective|\bsafe\b|₽|\brub\b|\bTL\b|\$|boost\w* immun",
    re.IGNORECASE,
)
# Счётчики товаров и цены: числа от трёх цифр («1 371», «2500»); «7–21» и Q10, D3 не задевает.
_BIG_NUMBER = re.compile(r"(?<![\w.,-])(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d{3,})(?!\w)")
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def validate_texts(texts):
    """Список проблем ответа модели; пустой — можно показывать на пилоте/писать."""
    problems = []
    for locale in LOCALES:
        values = texts.get(locale) or {}
        forbidden = _RU_FORBIDDEN if locale == "ru" else _EN_FORBIDDEN
        for field in SEO_FIELDS:
            value = (values.get(field) or "").strip()
            if not value:
                problems.append(f"{locale}.{field}: пусто")
                continue
            match = forbidden.search(value)
            if match:
                problems.append(f"{locale}.{field}: запрещено «{match.group(0)}»")
            number = _BIG_NUMBER.search(value)
            if number:
                problems.append(f"{locale}.{field}: число «{number.group(0)}»")
            if locale == "en" and _CYRILLIC.search(value):
                problems.append(f"en.{field}: кириллица")
            if locale == "ru" and field != "seo_text" and not _CYRILLIC.search(value):
                problems.append(f"ru.{field}: нет кириллицы")
        h1 = values.get("h1") or ""
        title = values.get("meta_title") or ""
        description = values.get("meta_description") or ""
        text = values.get("seo_text") or ""
        if h1 and not 15 <= len(h1) <= 80:
            problems.append(f"{locale}.h1: {len(h1)} символов")
        if title and (not title.endswith(TITLE_SUFFIX) or len(title) > 80):
            problems.append(f"{locale}.meta_title: {len(title)} символов или без «{TITLE_SUFFIX.strip()}»")
        if description and not 100 <= len(description) <= 200:
            problems.append(f"{locale}.meta_description: {len(description)} символов")
        words = len(text.split())
        if text and not 140 <= words <= 420:
            problems.append(f"{locale}.seo_text: {words} слов")
        if text and "## " not in text:
            problems.append(f"{locale}.seo_text: нет подзаголовков")
        if h1 and title and h1.strip().lower() == title.removesuffix(TITLE_SUFFIX).strip().lower():
            problems.append(f"{locale}: h1 совпадает с title")
    return problems


def generate_texts(facts, client):
    """Один запрос к Claude → (тексты, usage). client — apps.ai.services.claude_client.ClaudeClient."""
    raw, response = client.create(SYSTEM_PROMPT, build_user_prompt(facts), json_mode=True, max_tokens=2500)
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {}
    texts = {
        locale: {field: str((data.get(locale) or {}).get(field) or "").strip() for field in SEO_FIELDS}
        for locale in LOCALES
    }
    return texts, response.usage


def apply_texts(entries, *, overwrite=False, dry_run=False):
    """Пишет тексты в CategoryTranslation; возвращает (изменения, бэкап прежних значений).

    entries — [{"slug", "texts": {"ru": {...}, "en": {...}}}]. Без overwrite пишутся только
    пустые поля: правки из админки не перетираются. Нет перевода — создаётся с названием
    категории (en — с названием из факта name_en, иначе пропуск: английское имя не выдумываем).
    """
    changes, backup = [], []
    with transaction.atomic():
        for entry in entries:
            category = Category.objects.filter(slug=entry["slug"], is_active=True).first()
            if category is None:
                changes.append({"slug": entry["slug"], "skipped": "нет категории"})
                continue
            for locale in LOCALES:
                values = (entry.get("texts") or {}).get(locale) or {}
                translation = CategoryTranslation.objects.filter(category=category, locale=locale).first()
                if translation is None:
                    name = category.name if locale == "ru" else (entry.get("name_en") or "")
                    if not name:
                        changes.append({"slug": category.slug, "locale": locale, "skipped": "нет перевода"})
                        continue
                    translation = CategoryTranslation(category=category, locale=locale, name=name)
                fields = [
                    field for field in SEO_FIELDS
                    if values.get(field) and (overwrite or not getattr(translation, field))
                    and getattr(translation, field) != values[field]
                ]
                if not fields:
                    continue
                backup.append({
                    "slug": category.slug,
                    "locale": locale,
                    "created": translation.pk is None,
                    **{field: getattr(translation, field) for field in fields},
                })
                for field in fields:
                    setattr(translation, field, values[field])
                if not dry_run:
                    translation.save()
                changes.append({"slug": category.slug, "locale": locale, "fields": fields})
        if dry_run:
            transaction.set_rollback(True)
    return changes, backup
