"""Seed AITemplate (category_instruction) по категориям. Идемпотентно.

Шаблон вешается на КОРНЕВУЮ категорию домена — подкатегории наследуют его через
lineage-поиск в ContentGenerator._get_prompt_template. Текст потом можно править в
админке (Админка → AI → AI шаблоны).

Пока заполняется только парфюмерия.

    docker compose -p mudaroba exec backend poetry run python manage.py seed_ai_category_instructions
"""
from django.core.management.base import BaseCommand

from apps.ai.models import AITemplate
from apps.catalog.models import Category


PERFUMERY_INSTRUCTION = """\
Это парфюмерия — пиши описание как для аромата, не для одежды.
- Опирайся на доступные факты: объём (volume), семейство аромата (fragrance_family),
  тип (EDP/EDT/EDC), пол, ноты (top/heart/base), если они есть. НЕ выдумывай ноты,
  стойкость, шлейф и аккорды, которых нет в источнике.
- В сыром описании может быть мусор одёжного шаблона LCW (Kumaş Rehberi, Bakım Bilgileri,
  «Giysilerinizi Nasıl Yıkamalısınız», инструкции по стирке/уходу за одеждой) — полностью
  игнорируй его, не переноси в карточку.
- Тон: лаконичный, чувственный, но фактический. Характер аромата (свежий/древесный/сладкий)
  указывай только если он следует из семейства, Koku Tipi или текста источника.
- Для набора (is_perfume_set / «Paket İçeriği: 2'li Paket») укажи, что это набор, и его
  состав, если он известен.
- Объём и цену не дублируй в название товара.
"""

# slug корневой категории → (имя шаблона, текст)
SEEDS = {
    "perfumery": ("Парфюмерия — инструкция для категории", PERFUMERY_INSTRUCTION),
}


class Command(BaseCommand):
    help = "Создаёт/обновляет category_instruction шаблоны по корневым категориям (пока парфюмерия)."

    def handle(self, *args, **options):
        for slug, (name, content) in SEEDS.items():
            category = Category.objects.filter(slug=slug).first()
            if not category:
                self.stderr.write(self.style.WARNING(f"Категория «{slug}» не найдена — пропуск"))
                continue
            obj, created = AITemplate.objects.update_or_create(
                name=name,
                defaults=dict(
                    template_type="category_instruction",
                    category=category,
                    content=content.strip(),
                    language="ru",
                    is_active=True,
                ),
            )
            verb = "создан" if created else "обновлён"
            self.stdout.write(self.style.SUCCESS(f"Шаблон «{name}» {verb} (категория «{category.name}», #{obj.id})"))
