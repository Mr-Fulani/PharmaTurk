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

# Корни разделов, где менеджер в заявке уточняет ещё размер и цвет.
SIZE_COLOR_ROOTS = {"clothing", "shoes", "underwear", "headwear", "islamic-clothing"}

# Корни разделов, где у товара есть сроки доставки на сайте (карточки БАДов: 7–21 рабочий день).
DELIVERY_DAYS_ROOTS = {"supplements"}

SYSTEM_PROMPT = """Ты пишешь SEO-тексты посадочных страниц разделов интернет-витрины Mudaroba (mudaroba.com).
Mudaroba — витрина товаров из Турции для русскоязычных покупателей. Оплаты на сайте нет: покупатель
добавляет товары в «Список заявки» и отправляет его, менеджер проверяет то, что указано в факте
"manager_checks", рассчитывает стоимость вместе с доставкой и согласует детали; оплата — только после
согласованного расчёта.

Тебе дают факты раздела: название, родительские разделы, подразделы, бренды и примеры товаров из каталога.
Пиши ТОЛЬКО на основе этих фактов и правил выше. Нельзя придумывать бренды, материалы, страны производства,
сроки, цены, размеры, скидки, гарантии, характеристики товаров, назначение моделей («для холодной погоды»).
Пол и возраст («мужские», «женские», «детские») — только если они есть в названиях примеров товаров.
Не описывай устройство сайта («раздел входит в категорию…», «подразделов нет», «все модели на одной
странице») и не пиши о том, чего в фактах нет («для кого товар — уточняйте в карточке»): просто пропусти.
Бренд из фактов — это просто бренд: не пиши, турецкий он или нет (U.S. Polo Assn., Lumberjack — не турецкие,
хотя продаются в Турции). Бренды в фактах — от самых частых; в тексте назови 3–6 из них, не весь список.

Что нужно вернуть — два языка, "ru" и "en", в каждом четыре поля:
- "h1": заголовок страницы, 25–70 символов, естественная фраза с главным запросом раздела
  (например «Турецкие витамины группы B», «Кроссовки из Турции»). H1 и title — РАЗНЫЕ формулировки:
  H1 «Кроссовки из Турции: Nike, Adidas, Puma», title «Купить кроссовки Nike и Adidas из Турции | Mudaroba».
- "meta_title": 35–70 символов ВМЕСТЕ с окончанием « | Mudaroba» (оно обязательно в конце).
  Главный запрос + «из Турции» (EN: «from Turkey»), можно 1–2 бренда или вида товаров из фактов.
- "meta_description": 120–190 символов. Что есть в разделе (виды товаров, 2–3 бренда из фактов)
  и как заказать (заявка, менеджер рассчитает стоимость с доставкой). Без чисел товаров и цен.
- "seo_text": 180–320 слов. Обычный текст: абзацы через пустую строку, 2–3 подзаголовка — отдельной
  строкой, которая начинается с «## » (например «## Как выбрать»; без «## » подзаголовок не распознается). Содержание: что собрано в разделе и его подразделах, какие бренды и формы/виды
  товаров есть (только из фактов), как выбрать (практично: форма выпуска, состав на упаковке, размер —
  уточнить у менеджера), как оформить заказ. Пиши для людей: конкретно, без воды, без повторов
  ключевой фразы в каждом предложении (главный запрос — 2–4 раза на весь текст). Без пустых фраз
  вроде «каталог удобно просматривать», «вы быстро найдёте подходящий вариант», «без лишних хлопот».
  Не больше трёх подзаголовков. Последний раздел — «Как оформить заказ», после него ничего не пиши:
  ни итоговой фразы, ни повторного призыва.

Запрещено (в обоих языках):
- оценки брендов и товаров: «проверенные», «популярные», «узнаваемый дизайн», «часто выбирают»;
  ссылки на отзывы покупателей;
- обещать действия менеджера сверх правил выше (только: проверит "manager_checks", рассчитает стоимость
  с доставкой, согласует детали) — не «подберёт альтернативу», не «подскажет», не «поможет выбрать»;
- количество товаров, цены, валюты, проценты скидок; любые числа, кроме тех, что есть в названиях
  (D3, B12, Q10, Омега-3) и в разрешённом сроке доставки;
- «лучший», «№1», «самые низкие цены», «скидки», «акция», «бесплатно», «гарантия», «гарантируем»;
- обещания про здоровье: лечит, вылечивает, исцеляет, предотвращает болезни, укрепляет иммунитет,
  «эффективный», «безопасный»; БАД не лекарство — в разделах БАДов одной фразой напомни, что это
  не лекарственное средство и перед приёмом стоит посоветоваться со специалистом;
- советы по дозировке и приёму, в том числе детям; менеджер не подбирает дозу — он проверяет наличие
  и считает стоимость. Дозировки из названий товаров (400 МЕ) можно упоминать как факт ассортимента;
- слова «лечение», «лечить» в любом виде (в том числе в оговорках), «без рецепта»;
- сроки доставки, если их нет в фактах; названия магазинов-источников (только бренды из фактов).

Английская версия — не дословный перевод, а естественный текст для англоязычного покупателя
с теми же фактами и правилами; без кириллицы. В русском тексте кавычки — «ёлочки»."""


_LOCALE_SCHEMA = {
    "type": "object",
    "properties": {field: {"type": "string"} for field in SEO_FIELDS},
    "required": list(SEO_FIELDS),
    "additionalProperties": False,
}
# Ответ модели — строго по схеме (structured outputs): пилот 27.10.2026 без неё дал битый JSON у 3 из 5.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {locale: _LOCALE_SCHEMA for locale in LOCALES},
    "required": list(LOCALES),
    "additionalProperties": False,
}


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


def select_categories(*, slugs=None, roots=None, include_filled=False, min_products=1):
    """Активные непустые разделы для текстов, без медикаментов и услуг.

    slugs — ровно эти разделы; roots — корни целиком (сам корень и все потомки).
    Раздел, у которого уже есть русский SEO-текст, пропускается без include_filled.
    min_products — порог товаров в разделе с потомками: текст про пару товаров — тонкая страница.
    """
    categories = list(Category.objects.filter(is_active=True).prefetch_related("translations"))
    by_id = {c.id: c for c in categories}
    children_by_parent = {}
    for c in categories:
        if c.parent_id:
            children_by_parent.setdefault(c.parent_id, []).append(c.id)
    product_counts = dict(
        Product.objects.filter(is_active=True).exclude(category_id__isnull=True)
        .values("category_id").annotate(n=Count("id")).values_list("category_id", "n")
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
        if sum(product_counts.get(cid, 0) for cid in _subtree_ids(category, children_by_parent)) < max(min_products, 1):
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
        "manager_checks": "наличие, размер и цвет" if root in SIZE_COLOR_ROOTS else "наличие",
    }


def build_user_prompt(facts):
    return "Факты раздела:\n" + json.dumps(facts, ensure_ascii=False, indent=1)


_RU_FORBIDDEN = re.compile(
    r"леч|исцел|гарант|лучш(?:ий|ая|ее|ие|их|ими?|ую|ей|его|ему)\b|самы[йе] низк|проверенн|популярн|отзыв|хлопот|подбер[её]т|поможет выбрать|черновик|доработк|для ознакомления|№\s*1|скидк|акци[яи]|бесплатн|дешев|дёшев|без рецепта|"
    r"иммунитет укрепл|укрепля\w* иммун|эффективн|безопасн|₽|руб\.|\bруб\b|\bлир|\bTL\b|\$",
    re.IGNORECASE,
)
_EN_FORBIDDEN = re.compile(
    r"\bcur(e|es|ing)\b|\btreat|\bheal(s|ed|ing)?\b|guarant|\bpopular|\btrusted|\breviews?\b|hassle|\bdraft\b|placeholder|\bthe best\b|\bbest[- ](price|quality|choice|seller)|cheapest|discount|free (shipping|delivery)|for free|free of charge|"
    r"no prescription|without (a )?prescription|effective|\bsafe\b|₽|\brub\b|\bTL\b|\$|boost\w* immun",
    re.IGNORECASE,
)
# Счётчики товаров и цены: числа от трёх цифр («1 371», «2500»); «7–21», Q10, D3, дозировки
# и фасовка с единицей («1000 МЕ», «600 mg», «120 таблеток») не задевает.
_BIG_NUMBER = re.compile(
    r"(?<![\w.,-])(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d{3,})(?!\w)"
    # единица может стоять после перечня: «50, 100 и 150 мл»
    r"(?!(?:\s*(?:,|и|или|and|or)\s*\d+)*[ \u00a0]?(?:МЕ|IU|мкг|mcg|мг|mg|мл|ml|г\b|g\b|шт|капсул|таблет|саше|tablet|capsule|softgel|sachet))"
)
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def _repeated_phrase(text):
    """Фраза из трёх слов, которая встречается 4+ раз, — модель зациклилась (пилот 6: «ЧЕРНОВИК…» ×8)."""
    words = re.findall(r"\w+", text.lower())
    counts = {}
    for i in range(len(words) - 2):
        key = " ".join(words[i:i + 3])
        counts[key] = counts.get(key, 0) + 1
    return next((key for key, count in counts.items() if count >= 4), None)


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
        if title.count("Mudaroba") > 1:
            problems.append(f"{locale}.meta_title: «Mudaroba» дважды")
        repeated = _repeated_phrase(text)
        if repeated:
            problems.append(f"{locale}.seo_text: повтор «{repeated}»")
        if title and (not title.endswith(TITLE_SUFFIX) or len(title) > 80):
            problems.append(f"{locale}.meta_title: {len(title)} символов или без «{TITLE_SUFFIX.strip()}»")
        if description and not 100 <= len(description) <= 200:
            problems.append(f"{locale}.meta_description: {len(description)} символов")
        words = len(text.split())
        if text and not 140 <= words <= 420:
            problems.append(f"{locale}.seo_text: {words} слов")
        headings = sum(1 for line in text.splitlines() if line.startswith("## "))
        if text and not headings:
            problems.append(f"{locale}.seo_text: нет подзаголовков")
        if headings > 3:
            problems.append(f"{locale}.seo_text: {headings} подзаголовков")
        if h1 and title and h1.strip().lower() == title.removesuffix(TITLE_SUFFIX).strip().lower():
            problems.append(f"{locale}: h1 совпадает с title")
    return problems


def generate_texts(facts, client):
    """Один запрос к Claude → (тексты, usage, сырой ответ). client — apps.ai.services.claude_client.ClaudeClient."""
    raw, response = client.create(
        SYSTEM_PROMPT, build_user_prompt(facts), json_mode=True, max_tokens=6000,
        output_schema=OUTPUT_SCHEMA, effort="medium",
    )
    data = _parse_json_object(raw)
    texts = {
        locale: {field: str((data.get(locale) or {}).get(field) or "").strip() for field in SEO_FIELDS}
        for locale in LOCALES
    }
    return texts, response.usage, raw


def _parse_json_object(raw):
    """JSON-объект ответа: без обёртки ```, ключи языков без регистра; не разобрался — {}."""
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key).strip().lower(): value for key, value in data.items()}


def generate_checked(facts, client, attempts=2):
    """Тексты с проверкой; при замечаниях — ещё попытка (пилот: модель изредка ломает формат title).

    → (тексты, замечания, сырой ответ последней попытки, [usage каждой попытки]).
    """
    usages = []
    for _ in range(attempts):
        texts, usage, raw = generate_texts(facts, client)
        usages.append(usage)
        problems = validate_texts(texts)
        if not problems:
            break
    return texts, problems, raw, usages


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
